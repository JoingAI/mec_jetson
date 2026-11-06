#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""y309ctl.py - Y309 MCU 版本查询 / 命令发送 / 固件 OTA 升级工具

纯标准库(POSIX termios), 不需要 pyserial。端口默认 /dev/ttyTHS1, 不用每次写。

用法(在 Orin 的 Linux 下):
    python3 y309ctl.py ver              # 查版本
    python3 y309ctl.py boot             # 查 bootloader 是否已烧
    python3 y309ctl.py status           # 查运行状态
    python3 y309ctl.py ota              # 让 MCU 进入升级模式
    python3 y309ctl.py freq 30          # 发任意命令(多个参数自动拼空格)
    python3 y309ctl.py update Y309.hex  # 升级固件
    python3 y309ctl.py update Y309.hex boot   # 设备已在 bootloader 时升级

抗干扰措施(这就是为什么不要用 echo/cat 直接怼串口):
    1) 打开时加 TIOCEXCL 独占锁 -> 别的程序打不开同一个口
    2) 每条命令前后都清空收发缓冲 -> 不会读到上一次的残留
    3) 关掉行缓冲/回显/软流控 -> 原始二进制块不会被改写
    4) 协议自带两级校验: 每块 8 位 SUM + 整包 CRC16 -> 干扰会被发现并重发

退出码: 0 成功, 1 失败, 2 参数/文件错误
"""

import argparse
import os
import select
import sys
import time

# ============================ 默认端口 ============================
# 你的板子固定是 ttyTHS1, 所以内置为默认值; 换口用 --port 覆盖
DEFAULT_PORT = "/dev/ttyTHS1"

# 命令前缀: MCU 只响应以此开头的行(与 RS485 共用串口时的保护), 工具自动添加。
# 手工用串口助手时需要自己敲, 例如: #Y309:ver
CMD_PREFIX = "#Y309:"

# ---- 预留: 开机自动升级服务(默认不启用) ----
# 原理: systemd 在开机时执行 `y309ctl.py auto`; 若发现 pending 固件, 且 MCU 停在
# bootloader, 就自动完成升级, 然后删掉 pending 文件。
# 这样用户只需要: 执行一次 update(写请求) + 断电上电, 剩下全自动。
PENDING_FILE = "/home/nvidia/y309_mcu_ota/y309_pending.hex"

# ---------------- 终端颜色 ----------------
_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code, text):
    if not _USE_COLOR:
        return text
    return "\033[%sm%s\033[0m" % (code, text)


def c_title(t):   return _c("1;36", t)      # 亮青
def c_ok(t):      return _c("1;32", t)      # 亮绿
def c_warn(t):    return _c("1;33", t)      # 亮黄
def c_err(t):     return _c("1;31", t)      # 亮红
def c_hl(t):      return _c("1;35", t)      # 亮紫
SERVICE_NAME = "y309-ota-auto"
SERVICE_PATH = "/etc/systemd/system/%s.service" % SERVICE_NAME

# ============================ 协议常量(必须与 Inc/ota.h 一致) ============================
BAUD_DEFAULT   = 38400      # 与 CFG_UART_BAUD 一致
PAGE_SIZE      = 128        # OTA_PAGE_SIZE
BLOCK_MAGIC    = 0xA5       # OTA_BLOCK_MAGIC
CRC_INIT       = 0xFFFF     # OTA_CRC_INIT
CRC_POLY       = 0x1021     # OTA_CRC_POLY  (CRC16-CCITT/FALSE)

# 分区上限: 由 LDROM 大小决定, 必须与 Inc/ota.h 的 OTA_LDROM_KB 一致
OTA_LDROM_KB   = 3
APROM_END      = 0x4000 - OTA_LDROM_KB * 1024        # 0x3000
OTA_APP_MAX    = APROM_END - 2 * PAGE_SIZE           # 0x2F00 = 12032
OTA_REQ_ADDR   = APROM_END - 2 * PAGE_SIZE
OTA_META_ADDR  = APROM_END - PAGE_SIZE


# ============================ CRC16-CCITT/FALSE ============================
def crc16(data, crc=CRC_INIT):
    """与 bootloader 的 crc16() 完全一致: 初值 0xFFFF, 多项式 0x1021, 不反转, 无输出异或"""
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


# ============================ 固件文件解析 ============================
def load_intel_hex(path):
    mem = {}
    eof = False
    skipped = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise ValueError("第 %d 行不是 Intel HEX 记录" % lineno)
            try:
                rec = bytes.fromhex(line[1:])
            except ValueError:
                raise ValueError("第 %d 行有非法十六进制字符" % lineno)
            if len(rec) < 5:
                raise ValueError("第 %d 行记录太短" % lineno)
            n, addr, rtype = rec[0], (rec[1] << 8) | rec[2], rec[3]
            data = rec[4:4 + n]
            chk = rec[4 + n] if len(rec) > 4 + n else None
            if chk is None or (sum(rec[:4 + n]) + chk) & 0xFF:
                raise ValueError("第 %d 行校验和错误" % lineno)
            if rtype == 0x00:
                for i, b in enumerate(data):
                    a = addr + i
                    # 元数据页/请求页不属于应用镜像, 跳过。
                    # 这样"已封印"的 hex(比镜像多一条 0x3380 记录)也能直接用于 OTA。
                    if a >= OTA_REQ_ADDR:
                        skipped += 1
                        continue
                    mem[a] = b
            elif rtype == 0x01:
                eof = True
                break
    if not mem:
        raise ValueError("HEX 文件里没有数据记录")
    if not eof:
        sys.stderr.write("[warn] HEX 文件没有 EOF 记录(可能被截断)\n")
    if skipped:
        print("(该文件通用: 烧录器与串口升级共用, 已自动跳过 %d 字节附加信息)" % skipped)
    lo, hi = min(mem), max(mem)
    img = bytearray(b"\xFF" * (hi + 1))
    for a, b in mem.items():
        img[a] = b
    return bytes(img), lo


def load_firmware(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".hex", ".ihx"):
        return load_intel_hex(path)
    with open(path, "rb") as f:
        return f.read(), 0


# ============================ 串口(POSIX termios) ============================
class Port:
    def __init__(self, path, baud):
        import termios
        self.termios = termios
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            # ★ 独占锁: 其它进程再 open 会失败, 避免两个程序抢同一个串口
            import fcntl
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
        except Exception:
            pass
        speed = getattr(termios, "B%d" % baud, None)
        if speed is None:
            raise ValueError("系统不支持波特率 %d" % baud)
        a = termios.tcgetattr(self.fd)
        iflag = 0
        oflag = 0
        cflag = a[2] & ~(termios.CSIZE | termios.PARENB | termios.CSTOPB |
                         termios.CRTSCTS | termios.HUPCL)
        cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
        lflag = 0
        cc = list(a[6])
        cc[termios.VMIN] = 0
        cc[termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW,
                          [iflag, oflag, cflag, lflag, speed, speed, cc])
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        try:
            import termios
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except Exception:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass

    def flush_in(self):
        # 只清接收侧, 避免影响已排队的发送数据
        try:
            self.termios.tcflush(self.fd, self.termios.TCIFLUSH)
        except Exception:
            pass

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("ascii")
        view = memoryview(data)
        while view:
            try:
                n = os.write(self.fd, view)
                view = view[n:]
            except BlockingIOError:
                select.select([], [self.fd], [], 0.5)

    def read(self, n=256, timeout=0.05):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return b""
        try:
            return os.read(self.fd, n)
        except BlockingIOError:
            return b""

    def read_until(self, targets, timeout=2.0):
        if isinstance(targets, bytes):
            targets = [targets]
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            chunk = self.read(256, 0.02)
            if chunk:
                buf += chunk
                for t in targets:
                    if t in buf:
                        return buf, t
        return buf, None

    def read_quiet(self, first_timeout=0.4, quiet=0.25, maxtime=3.0):
        """读到线路安静为止(用于收一条命令的全部回应)"""
        buf = b""
        end = time.time() + maxtime
        t0 = time.time() + first_timeout
        while time.time() < end:
            chunk = self.read(256, quiet)
            if chunk:
                buf += chunk
                t0 = time.time() + first_timeout
            elif time.time() > t0:
                break
        return buf


# ============================ 动作 ============================
def send_cmd(port, text, timeout=2.0):
    port.flush_in()                 # ★ 清掉残留, 防止把上一次的回应当成本次结果
    port.write(CMD_PREFIX + text + "\r\n")
    buf, hit = port.read_until([b"OK", b"ERR"], timeout)
    return hit == b"OK", buf


def filter_heartbeat(text):
    """去掉心跳行(HB ...): 它每秒一行, 会粘在命令回应后面"""
    keep = []
    for line in text.splitlines():
        if line.startswith("HB "):
            continue
        keep.append(line)
    return "\n".join(keep).strip()


def run_cmd(port, text):
    """发一条普通命令, 打印全部回应(自动过滤心跳行)"""
    port.flush_in()
    port.write(CMD_PREFIX + text + "\r\n")
    data = port.read_quiet(first_timeout=0.5, quiet=0.3)
    text_out = filter_heartbeat(data.decode("ascii", "replace"))
    if not text_out:
        print("(无响应)")
        print("  可能原因:")
        print("   1) MCU 停在 bootloader 模式(此时不会回应 ver/status, 只会打印 OTA1)")
        print("   2) 波特率不对(应 38400)")
        print("   3) ttyTHS1 上有别的程序/控制台占用")
        print("   4) TX/RX 接反或没共地")
        return False
    print(text_out)
    return True


def prepare_bootloader(port):
    """第一阶段: 让运行中的 APP 写好升级请求(不复位), 然后提示用户断电上电。

    为什么不在这一步直接切 bootloader:
      APP -> bootloader 需要 MCU 软复位; 复位瞬间 P0.3(Orin 电源使能)会变弱上拉,
      外部只有 100K 下拉 -> Orin 掉电 -> 升级通道(Orin 串口)断开, 升级必然失败。
      所以这一步只做"打标记", 由用户主动断电上电来切换, 上电时不会影响 Orin。
    """
    port.flush_in()
    port.write(CMD_PREFIX + "ota\r\n")
    buf, hit = port.read_until([b"ready", b"OK", b"ERR"], 3.0)
    if hit:
        # 命中后把这一行剩下的字符也读完, 否则只显示到 "OK OTA ready, po"
        more = port.read(128, 0.3)
        buf += more
    txt = buf.decode("ascii", "replace").strip()
    return txt


def probe_bootloader(port):
    """第二阶段用: 确认 MCU 已经在 bootloader 里"""
    ok, _ = send_cmd(port, "OTA:START", timeout=1.5)
    return ok


def send_block(port, addr, data):
    frame = bytearray()
    frame.append(BLOCK_MAGIC)
    frame.append(addr & 0xFF)
    frame.append((addr >> 8) & 0xFF)
    frame.append(len(data))
    frame.extend(data)
    frame.append(sum(frame[1:]) & 0xFF)      # AL + AH + LEN + DATA
    port.write(bytes(frame))
    _, hit = port.read_until([b"OK", b"ERR"], 2.0)
    return hit == b"OK"


def update_once(port, image):
    n = len(image)
    c = crc16(image)

    if not send_cmd(port, "OTA:START")[0]:
        print("  START 失败"); return False
    if not send_cmd(port, "OTA:SIZE:%d" % n)[0]:
        print("  SIZE 失败"); return False

    pages = (n + PAGE_SIZE - 1) // PAGE_SIZE
    print("  擦除 %d 页(约 %.1f 秒)..." % (pages, pages * 0.005 + 0.3))
    if not send_cmd(port, "OTA:ERASE", timeout=8.0)[0]:
        print("  ERASE 失败"); return False

    t0 = time.time()
    for i, off in enumerate(range(0, n, PAGE_SIZE)):
        chunk = image[off:off + PAGE_SIZE]
        ok = False
        for attempt in range(3):
            if send_block(port, off, chunk):
                ok = True
                break
            print("    块 %d 重试 %d" % (i, attempt + 1))
        if not ok:
            print("  块 %d (地址 0x%04X) 发送失败" % (i, off))
            return False
        if (i + 1) % 16 == 0 or i + 1 == pages:
            print("    %d/%d 块 (%d%%)" % (i + 1, pages, (i + 1) * 100 // pages))

    print("  传输完成, 用时 %.1f 秒; 校验整包 CRC16=0x%04X ..." % (time.time() - t0, c))
    if not send_cmd(port, "OTA:FINAL:%d" % c, timeout=8.0)[0]:
        print("  FINAL 校验失败(CRC 不符)")
        return False
    return True


def do_update(port, image, already_in_boot, fw_name='', attempts=2):
    if len(image) > OTA_APP_MAX:
        print("固件 %d 字节, 超过上限 %d 字节(LDROM=%dKB)" %
              (len(image), OTA_APP_MAX, OTA_LDROM_KB))
        return False

    if not already_in_boot:
        print("第 1 步: 通知 APP 准备升级 ...")
        txt = prepare_bootloader(port)
        if "ready" in txt or "OK" in txt:
            print("  " + c_ok("准备完成"))
            print("  " + txt)
            print()
            print(c_title("=" * 60))
            print("  " + c_warn("第 1 步完成, 现在需要重启一次 MCU"))
            print()
            print("  请按顺序操作:")
            print("    1) " + c_hl("sudo poweroff") + "   关闭 Orin")
            print("    2) 等关机完成后, 给" + c_hl("整板断电") + " 3 秒")
            print("    3) 重新上电, 等 Orin 进入系统")
            print("    4) 再执行下面这条命令:")
            print()
            print("       " + c_hl("python3 %s update %s boot" %
                  (os.path.basename(sys.argv[0]), fw_name)))
            print(c_title("=" * 60))
            return None                       # None = 只完成了准备阶段
        print("  失败: APP 没有响应 ota 命令")
        print("  ① 先发 boot 确认 bootloader 已烧(应回 BOOT present)")
        print("  ② 若 APP 已坏, 直接断电上电会停在 bootloader, 加 boot 参数再升级")
        return False

    for k in range(attempts):
        if k:
            print("第 %d 次重试 ..." % (k + 1))
        if update_once(port, image):
            print()
            print(c_ok("=" * 60))
            print(c_ok("  固件已写入并校验通过"))
            print(c_ok("=" * 60))
            print()
            print("  请按顺序操作:")
            print("    1) " + c_hl("sudo poweroff") + "   关闭 Orin")
            print("    2) 给" + c_hl("整板断电") + " 3 秒, 再重新上电")
            print("    3) 上电后新固件自动生效")
            print()
            print("  验证版本: " + c_hl("python3 %s ver" % os.path.basename(sys.argv[0])))
            print(c_ok("=" * 60))
            return True
        time.sleep(0.5)
    print("\n升级失败。设备停在 bootloader(不会变砖), 可直接重跑本命令。")
    return False


# ============================ 开机自动升级(预留功能) ============================
def do_mode(port, val=None):
    """查询/设置触发源: pps(仅 PPS) / free(自由输出) / auto(自由输出+PPS对齐)"""
    if val is None:
        port.flush_in()
        port.write(CMD_PREFIX + "mode\r\n")
        data = port.read_quiet(first_timeout=0.5, quiet=0.3)
        txt = filter_heartbeat(data.decode("ascii", "replace"))
        print(txt if txt else "(无响应)")
        return bool(txt)

    v = val.strip().lower()
    if v not in ("pps", "free", "auto", "0", "1", "2"):
        print("mode 只能是 pps / free / auto (或 0/1/2)")
        return False
    ok, buf = send_cmd(port, "mode " + v)
    txt = filter_heartbeat(buf.decode("ascii", "replace"))
    print(txt if txt else ("OK" if ok else "ERR"))
    return ok


def do_auto(port):
    """开机自检: 若存在 pending 固件且 MCU 停在 bootloader, 自动升级"""
    if not os.path.exists(PENDING_FILE):
        return True                     # 没有待升级固件, 什么都不做

    print("发现待升级固件: %s" % PENDING_FILE)
    ok, _ = send_cmd(port, "OTA:START", timeout=1.5)
    if not ok:
        print("MCU 不在 bootloader(可能正常运行中), 本次跳过")
        return True
    print("MCU 在 bootloader, 开始自动升级 ...")
    image, _ = load_firmware(PENDING_FILE)
    if update_once(port, image):
        os.remove(PENDING_FILE)
        print("自动升级完成, 已删除 pending 文件。请断电上电使新固件生效。")
        return True
    print("自动升级失败, 保留 pending 文件, 下次开机再试")
    return False


def service_status():
    if os.path.exists(SERVICE_PATH):
        print("自启动服务: 已安装 (%s)" % SERVICE_PATH)
        print("  启用状态: 由 systemctl is-enabled 查看")
    else:
        print("自启动服务: 未安装(默认不启用)")
    return 0


def service_install():
    unit = """[Unit]
Description=Y309 MCU OTA auto-update on boot
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/nvidia/y309_mcu_ota/Tools/y309ctl.py auto
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""
    print("将写入 %s" % SERVICE_PATH)
    try:
        with open(SERVICE_PATH, "w") as f:
            f.write(unit)
    except PermissionError:
        print("权限不足, 请用 sudo 运行: sudo python3 %s service install" % os.path.basename(sys.argv[0]))
        return 1
    os.system("systemctl daemon-reload")
    os.system("systemctl enable %s" % SERVICE_NAME)
    print("已安装并设为开机启用。卸载: sudo python3 %s service remove" % os.path.basename(sys.argv[0]))
    print()
    print("使用方式:")
    print("  ① 把要升级的固件拷成: %s" % PENDING_FILE)
    print("  ② 执行一次: python3 %s update <固件>" % os.path.basename(sys.argv[0]))
    print("  ③ 断电上电 -> 开机自动完成升级 -> 再断电上电生效")
    return 0


def service_remove():
    try:
        if os.path.exists(SERVICE_PATH):
            os.remove(SERVICE_PATH)
    except PermissionError:
        print("权限不足, 请用 sudo")
        return 1
    os.system("systemctl disable %s 2>/dev/null" % SERVICE_NAME)
    os.system("systemctl daemon-reload")
    print("已卸载自启动服务")
    return 0


# ============================ main ============================
def main():
    ap = argparse.ArgumentParser(
        description="Y309 MCU 工具: 查版本 / 发命令 / OTA 升级 (默认端口 %s)" % DEFAULT_PORT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  %(prog)s ver\n"
               "  %(prog)s boot\n"
               "  %(prog)s ota\n"
               "  %(prog)s freq 30\n"
               "  %(prog)s mode            # 查询当前触发源\n"
               "  %(prog)s mode free       # 不依赖 PPS, 自由输出(pps/free/auto)\n"
               "  %(prog)s update Y309.hex\n"
               "  %(prog)s update Y309.hex boot     # 设备已在 bootloader\n")
    ap.add_argument("args", nargs="*",
                    help="命令: ver / boot / status / ota / freq 30 / mode [pps|free|auto] / "
                         "update <文件> [boot] / service status|install|remove / auto")
    ap.add_argument("--port", default=DEFAULT_PORT, help="串口, 默认 %s" % DEFAULT_PORT)
    ap.add_argument("--baud", type=int, default=BAUD_DEFAULT, help="波特率, 默认 38400")
    a = ap.parse_args()

    if not a.args:
        ap.print_help()
        return 2

    first = a.args[0].lower()
    image = None
    already = False

    if first == "service":
        sub = a.args[1].lower() if len(a.args) > 1 else "status"
        if sub == "install":
            return service_install()
        if sub == "remove":
            return service_remove()
        return service_status()

    if first == "auto":
        try:
            port = Port(a.port, a.baud)
        except Exception as e:
            print("打开串口失败: %s" % e)
            return 1
        try:
            return 0 if do_auto(port) else 1
        finally:
            port.close()

    if first == "update":
        if len(a.args) < 2:
            print("用法: update <固件.hex|.bin> [boot]")
            return 2
        fw = a.args[1]
        already = (len(a.args) > 2 and a.args[2].lower() == "boot")
        try:
            image, lo = load_firmware(fw)
        except Exception as e:
            print("读取固件失败: %s" % e)
            return 2
        print("固件: %s" % fw)
        print("  %d 字节, 起始 0x%04X, %d 块, CRC16=0x%04X" %
              (len(image), lo, (len(image) + PAGE_SIZE - 1) // PAGE_SIZE, crc16(image)))
        if lo != 0:
            print("  [warn] 固件不是从 0x0000 开始")
        if len(image) > OTA_APP_MAX:
            print("  超过上限 %d 字节, 中止" % OTA_APP_MAX)
            return 2

    # (service 已在上面处理, 这里只需打开串口)

    if not os.path.exists(a.port):
        print("串口 %s 不存在。可用 --port 指定。" % a.port)
        return 2

    try:
        port = Port(a.port, a.baud)
    except PermissionError:
        print("打开 %s 权限不足。试: sudo usermod -aG dialout $USER  然后重新登录" % a.port)
        return 2
    except Exception as e:
        print("打开串口失败: %s" % e)
        return 2

    try:
        if first == "auto":
            return 0 if do_auto(port) else 1
        if first == "update":
            r = do_update(port, image, already, os.path.basename(a.args[1]))
            return 0 if (r is None or r) else 1
        if first == "mode":
            return 0 if do_mode(port, a.args[1] if len(a.args) > 1 else None) else 1
        return 0 if run_cmd(port, " ".join(a.args)) else 1
    finally:
        port.close()


if __name__ == "__main__":
    sys.exit(main())

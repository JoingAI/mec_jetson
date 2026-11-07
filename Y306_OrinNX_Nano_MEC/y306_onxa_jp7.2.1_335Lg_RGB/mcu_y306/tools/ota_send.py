#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ota_send.py —— 从 Orin NX（Linux）通过串口将 STM32 固件发送给 MCU 完成 OTA 升级。

零第三方依赖，仅使用 Python 标准库（os / sys / glob / time / select / struct /
argparse / termios 等）。禁止 import pyserial。
"""

import os
import sys
import glob
import time
import select
import struct
import argparse
import termios

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SLOT_SIZE = 16384          # 每槽 16KB
BLOCK_SIZE = 1024          # 块大小 1024 字节
BLOCK_COUNT = 16           # 16384 / 1024 = 16 块
FLASH_BASE = 0x08000000
SLOT_A_BASE = 0x08004000
SLOT_B_BASE = 0x08008000

OTA_PASSWORD = 'OTA:START:F306OTA'

SETTLE_SECONDS = 1.0        # 打开串口后的稳定延时(覆盖 DTR 复位 / USB-CDC 枚举时序)
HANDSHAKE_RETRY = 3         # 握手重试次数(首次上电后第一帧易丢失)


# ---------------------------------------------------------------------------
# CRC（纯 Python 实现，逐 byte 位运算）
# ---------------------------------------------------------------------------
def crc16_modbus(data):
    """MODBUS CRC16：反射多项式 0xA001，初值 0xFFFF（用于每个 1024 字节块）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc32_reflected(data):
    """zlib 反射型 CRC32：多项式 0xEDB88320，初值 0xFFFFFFFF，结果异或 0xFFFFFFFF。

    对整片 16384 字节计算，用于 OTA:FINAL。
    """
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return crc ^ 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Intel HEX 解析
# ---------------------------------------------------------------------------
def parse_hex(path):
    """解析 Intel HEX，返回 (records, saw_ext)。

    records : [(绝对地址, 数据 bytes), ...]
    saw_ext : 是否出现过 type 04 扩展线性地址记录。
    """
    records = []
    linear_base = 0
    saw_ext = False
    with open(path, 'r', encoding='ascii') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            if not line.startswith(':'):
                raise ValueError('%s:%d 不是合法的 HEX 行（缺少 ":" 前缀）' % (path, lineno))
            try:
                b = bytes.fromhex(line[1:])
            except ValueError:
                raise ValueError('%s:%d HEX 解码失败' % (path, lineno))
            if len(b) < 5:
                raise ValueError('%s:%d 记录过短' % (path, lineno))
            rec_len = b[0]
            rec_addr = (b[1] << 8) | b[2]
            rec_type = b[3]
            if 4 + rec_len + 1 != len(b):
                raise ValueError('%s:%d 记录长度字段与内容不一致' % (path, lineno))
            if sum(b) & 0xFF != 0:
                raise ValueError('%s:%d 校验和错误' % (path, lineno))
            rec_data = b[4:4 + rec_len]

            if rec_type == 0x00:                        # 数据记录
                records.append(((linear_base << 16) + rec_addr, rec_data))
            elif rec_type == 0x01:                      # EOF 记录 :00000001FF
                break
            elif rec_type == 0x04:                      # 扩展线性地址记录
                if rec_len != 2:
                    raise ValueError('%s:%d 扩展线性地址记录长度错误' % (path, lineno))
                linear_base = (rec_data[0] << 8) | rec_data[1]
                saw_ext = True
            elif rec_type in (0x02, 0x03, 0x05):        # 段地址 / 起始地址记录，忽略
                continue
            else:
                raise ValueError('%s:%d 未知记录类型 0x%02X' % (path, lineno, rec_type))

    if not records:
        raise ValueError('%s: 未解析到任何数据记录' % path)
    return records, saw_ext


def build_blob(records, saw_ext, tgt):
    """把 HEX 数据组装为 16384 字节固件字节流，并做链接基址校验。"""
    slot = 'A' if tgt == 0 else 'B'
    slot_base = SLOT_A_BASE if tgt == 0 else SLOT_B_BASE

    norm = []
    for addr, data in records:
        a = addr
        # 若全程没有扩展线性地址记录（I16HEX），把 16 位地址按 0x08000000 基准归一化
        if not saw_ext and a < FLASH_BASE:
            a |= FLASH_BASE
        norm.append((a, data))
    norm.sort()

    min_addr = norm[0][0]
    if min_addr != slot_base:
        raise ValueError(
            'hex 链接槽与目标槽不匹配：最低地址 0x%08X 不等于目标槽 %s 的基址 0x%08X'
            '（防止把 A 槽固件写进 B 槽）' % (min_addr, slot, slot_base)
        )

    blob = bytearray(b'\xFF' * SLOT_SIZE)
    for a, data in norm:
        off = a - slot_base
        if off < 0 or off + len(data) > SLOT_SIZE:
            raise ValueError('固件数据超出 16KB 槽范围（地址 0x%08X 长度 %d）' % (a, len(data)))
        blob[off:off + len(data)] = data
    return bytes(blob)


# ---------------------------------------------------------------------------
# 串口
# ---------------------------------------------------------------------------
def get_baud_const(baud):
    c = getattr(termios, 'B%d' % baud, None)
    if c is None:
        raise ValueError(
            '不支持的波特率 %d（常见：9600/19200/38400/57600/115200/230400/460800/921600）' % baud
        )
    return c


def try_open(path, baud):
    """以 O_RDWR|O_NOCTTY|O_NONBLOCK 打开并设为 raw 8N1。失败抛 OSError。"""
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        new = termios.tcgetattr(fd)
        # raw 模式: 手动设置标志位(部分平台的 termios 无 cfmakeraw)
        new[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                    termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
        new[1] &= ~termios.OPOST
        new[2] &= ~(termios.CSIZE | termios.PARENB)
        new[2] |= termios.CS8
        new[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
        new[2] = (new[2] & ~(termios.CSTOPB | termios.CRTSCTS)) | termios.CREAD | termios.CLOCAL
        bconst = get_baud_const(baud)
        new[4] = bconst                                         # ispeed
        new[5] = bconst                                         # ospeed
        termios.tcsetattr(fd, termios.TCSANOW, new)
        termios.tcflush(fd, termios.TCIFLUSH)                   # 清空输入缓冲
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return fd


class OtaSender(object):
    def __init__(self, args):
        self.args = args
        self.fd = None
        self.port = None
        self.rxbuf = b''
        self.aborted = False

    # ---- 打开 / 关闭 ----
    def open(self):
        candidates = [self.args.port]
        if self.args.port == '/dev/ttyACM0':
            for pat in ('/dev/ttyACM*', '/dev/ttyUSB*'):
                candidates.extend(sorted(glob.glob(pat)))
        seen = set()
        for p in candidates:
            if p in seen:
                continue
            seen.add(p)
            print('[串口] 尝试打开 %s ...' % p)
            try:
                fd = try_open(p, self.args.baud)
            except (OSError, ValueError) as e:
                print('[串口] 打开 %s 失败: %s' % (p, e))
                continue
            self.fd = fd
            self.port = p
            print('[串口] 已打开 %s（%d 8N1）' % (p, self.args.baud))
            return
        raise OSError('未找到可用串口（/dev/ttyACM* 或 /dev/ttyUSB*）')

    def close(self):
        if self.fd is None:
            return
        try:
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.fd = None

    # ---- 基础读写 ----
    def write_all(self, data):
        mv = memoryview(data)
        while mv:
            _, w, _ = select.select([], [self.fd], [], None)
            if self.fd not in w:
                continue
            n = os.write(self.fd, mv)
            if n <= 0:
                raise OSError('串口写入失败')
            mv = mv[n:]

    def send_cmd(self, cmd):
        self.write_all((cmd + '\r\n').encode('ascii'))

    def read_line(self, timeout):
        """读取一行（以 \\n 结尾），带 select 轮询 + 累计超时，去掉 \\r\\n 后返回。"""
        deadline = time.monotonic() + timeout
        data = self.rxbuf
        self.rxbuf = b''
        while True:
            idx = data.find(b'\n')
            if idx >= 0:
                line = data[:idx].rstrip(b'\r')
                self.rxbuf = data[idx + 1:]
                return line.decode('ascii', errors='replace')
            remain = deadline - time.monotonic()
            if remain <= 0:
                self.rxbuf = data
                raise TimeoutError('等待 MCU 应答超时（> %gs）' % timeout)
            r, _, _ = select.select([self.fd], [], [], remain)
            if self.fd in r:
                chunk = os.read(self.fd, 1024)
                if not chunk:
                    raise OSError('串口无数据（设备可能已断开）')
                data += chunk

    # ---- 中止 ----
    def abort(self):
        if self.fd is None or self.aborted:
            return
        self.aborted = True
        try:
            self.write_all(b'OTA:ABORT\r\n')
            print('[中止] 已发送 OTA:ABORT')
        except OSError:
            pass

    # ---- 握手 ----
    def handshake(self):
        # 首跑常因串口打开瞬间 DTR/RTS 抖动复位 MCU 或 USB-CDC 枚举时序,
        # 导致第一次 OTA:START 丢失。清缓冲后重试握手, 直到收到 OTA:READY。
        for attempt in range(1, HANDSHAKE_RETRY + 1):
            try:
                termios.tcflush(self.fd, termios.TCIOFLUSH)
            except OSError:
                pass
            self.rxbuf = b''
            self.send_cmd(OTA_PASSWORD)
            print('[握手] 已发送 %s（第 %d/%d 次）' % (OTA_PASSWORD, attempt, HANDSHAKE_RETRY))
            deadline = time.monotonic() + self.args.timeout
            while True:
                try:
                    line = self.read_line(max(0.05, deadline - time.monotonic()))
                except TimeoutError:
                    break
                print('[握手] 收到: %s' % line)
                if line == 'OTA:DENY':
                    raise ValueError('握手被拒绝（OTA:DENY，口令错误）')
                if line.startswith('OTA:READY:'):
                    parts = line.split(':')
                    if len(parts) != 5:
                        raise ValueError('OTA:READY 格式异常: %s' % line)
                    try:
                        act = int(parts[2])
                        tgt = int(parts[3])
                        tgt_max = int(parts[4])
                    except ValueError:
                        raise ValueError('OTA:READY 字段无法解析: %s' % line)
                    if tgt_max != SLOT_SIZE:
                        raise ValueError('MCU 槽大小 %d 与预期 %d 不一致' % (tgt_max, SLOT_SIZE))
                    print('[握手] 目标槽: 槽 %s（act=%d, tgt=%d, max=%d）' % ('A' if tgt == 0 else 'B', act, tgt, tgt_max))
                    return tgt
                # 非 READY 行(如开机版本行/空行): 跳过继续等, 直到本次超时
        raise TimeoutError('等待 MCU 应答超时（已重试 %d 次，单次 > %gs）' % (HANDSHAKE_RETRY, self.args.timeout))

    # ---- 选择并解析文件 ----
    def load_firmware(self, tgt):
        if tgt == 0:
            path, slot, base, flag = self.args.hex_a, 'A', SLOT_A_BASE, '--a'
        elif tgt == 1:
            path, slot, base, flag = self.args.hex_b, 'B', SLOT_B_BASE, '--b'
        else:
            raise ValueError('无效的目标槽 %d' % tgt)
        if not path:
            raise ValueError('目标槽是槽 %s，请提供 %s 指定的 .hex 文件' % (slot, flag))
        if not os.path.isfile(path):
            raise ValueError('HEX 文件不存在: %s' % path)
        print('[文件] 使用 %s 槽固件: %s' % (slot, path))
        records, saw_ext = parse_hex(path)
        blob = build_blob(records, saw_ext, tgt)
        print('[文件] 解析完成，固件 %d 字节，链接基址 0x%08X' % (SLOT_SIZE, base))
        return blob

    # ---- SIZE / ERASE ----
    def send_size(self):
        self.send_cmd('OTA:SIZE:%d' % SLOT_SIZE)
        line = self.read_line(self.args.timeout)
        print('[SIZE ] 收到: %s' % line)
        if line != 'OTA:SIZE_OK':
            raise ValueError('SIZE 校验失败，MCU 返回 %s' % line)

    def send_erase(self):
        self.send_cmd('OTA:ERASE')
        line = self.read_line(self.args.timeout)
        print('[ERASE] 收到: %s' % line)
        if line != 'OTA:ERASED':
            raise ValueError('擦除失败，MCU 返回 %s' % line)

    # ---- 分块发送 ----
    def send_blocks(self, blob):
        for seq in range(BLOCK_COUNT):
            payload = blob[seq * BLOCK_SIZE:(seq + 1) * BLOCK_SIZE]
            frame = (b'\xA5'
                     + struct.pack('<H', seq)
                     + struct.pack('<H', len(payload))
                     + payload
                     + struct.pack('<H', crc16_modbus(payload)))
            ok = False
            for attempt in range(self.args.retry + 1):
                self.write_all(frame)
                line = self.read_line(self.args.timeout)
                if line == 'ACK:%d' % seq:
                    print('[分块] [%2d/%d] ACK' % (seq + 1, BLOCK_COUNT))
                    ok = True
                    break
                if line == 'NAK:%d' % seq:
                    if attempt + 1 > self.args.retry:
                        raise ValueError('块 %d 重传超过上限 %d 次，仍收到 NAK' % (seq, self.args.retry))
                    print('[分块] [%2d/%d] NAK，重传（%d/%d）' % (seq + 1, BLOCK_COUNT, attempt + 1, self.args.retry))
                    continue
                if line == 'OTA:ABORTED':
                    raise ValueError('块 %d 传输期间 MCU 已中止（OTA:ABORTED）' % seq)
                raise ValueError('块 %d 收到异常应答: %s' % (seq, line))
            if not ok:
                raise ValueError('块 %d 发送失败' % seq)

    # ---- FINAL ----
    def send_final(self, blob):
        crc = crc32_reflected(blob)
        print('[CRC ] 整片 crc32 = %d' % crc)
        self.send_cmd('OTA:FINAL:%d' % crc)
        line = self.read_line(self.args.timeout)
        print('[FINAL] 收到: %s' % line)
        if line != 'OTA:OK':
            raise ValueError('FINAL 校验失败，MCU 返回 %s' % line)

    # ---- 总流程 ----
    def do_upgrade(self):
        tgt = self.handshake()
        blob = self.load_firmware(tgt)
        self.send_size()
        self.send_erase()
        self.send_blocks(blob)
        self.send_final(blob)
        print('[结果] OTA 升级成功！')
        print('[提示] 新固件已写入空闲槽，下次自然上电（断电后再上电）生效；'
              'MCU 当前仍在运行旧固件，无需烧录器。')


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(description='STM32 串口 OTA 升级工具（零第三方依赖）')
    p.add_argument('--a', dest='hex_a', default=None, help='槽 A 链接的 .hex 文件路径（目标槽为 A 时必填）')
    p.add_argument('--b', dest='hex_b', default=None, help='槽 B 链接的 .hex 文件路径（目标槽为 B 时必填）')
    p.add_argument('--port', default='/dev/ttyACM0', help='串口设备，默认 /dev/ttyACM0（失败时自动扫描 ttyACM*/ttyUSB*）')
    p.add_argument('--baud', type=int, default=115200, help='波特率，默认 115200')
    p.add_argument('--timeout', type=float, default=5.0, help='单个应答等待超时秒数，默认 5')
    p.add_argument('--retry', type=int, default=5, help='每块 NAK 最大重传次数，默认 5')
    return p.parse_args(argv)


def run(args):
    get_baud_const(args.baud)          # 提前校验波特率
    s = OtaSender(args)
    s.open()
    # 稳定延时: 打开串口瞬间 DTR/RTS 抖动可能复位 MCU 或触发 USB-CDC 重枚举,
    # 若立刻发 OTA:START 会在 MCU 尚未完成上电初始化时被丢弃。等待其重新就绪。
    time.sleep(SETTLE_SECONDS)
    try:
        s.do_upgrade()
    except BaseException:
        s.abort()
        raise
    finally:
        s.close()


def main(argv=None):
    args = parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print('\n[中断] 用户中止', file=sys.stderr)
        return 2
    except Exception as e:
        print('[错误] %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
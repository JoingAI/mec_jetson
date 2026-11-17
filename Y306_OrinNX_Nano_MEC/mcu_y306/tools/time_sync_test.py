#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
time_sync_test.py —— F306 MCU 与 Orin NX 时间同步 / 触发时刻上报 / 相机帧对齐测试脚本。

零第三方依赖，仅使用 Python 标准库（os / glob / select / statistics / bisect /
struct / fcntl / mmap / argparse / termios 等）。禁止 import pyserial。

协议见 TIME_SYNC.md 第三、四节；指令表见 DELIVERY.md 第三节。

用法（Orin 侧）:
    python3 time_sync_test.py status                      # 固件版本 + GPS/喂狗状态
    python3 time_sync_test.py sync   --sync-n 16          # 0x08 偏移估算: 看重复性
    python3 time_sync_test.py report --duration 10        # 0x0A 上报: 周期/延迟/丢包
    python3 time_sync_test.py all                         # 依次跑上面三项并给结论

    # 相机帧对齐：标定「触发 -> 曝光 -> 出图」延迟，验证触发时刻能与实际帧对上
    python3 time_sync_test.py align --frames v4l2 --device /dev/video0 --duration 10
    your_grabber | python3 time_sync_test.py align --frames fifo --frame-path -

测试项与判据:
  1) 时间偏移重复性 —— 同一时刻连测 N 次，off24 的极差应 < 1ms（链路稳定）
  2) 上报速率       —— 应与 PWM 触发频率一致（--freq，默认 30Hz）
  3) 触发周期抖动   —— 相邻上报时间戳之差应≈触发周期，抖动在 MCU 晶振级别（<100us）
  4) 投递延迟       —— 收到上报帧时刻 - 该帧触发时刻，应落在主循环周期内
                       （ACC 版 100ms / 非 ACC 版 500ms，最坏不超过约 1.1s）
  5) 丢帧估计       —— 上报时间戳间隔与触发周期比对，正常应为 0
  6) 偏移漂移       —— 运行期重跑 0x08，观察 MCU 晶振相对 Orin 的漂移
  7) 帧对齐（align）—— 每帧与"不晚于它的最近一次触发"配对，延迟 L = t_帧 - t_触发：
                       · 匹配率应 ~100%（有帧没配上触发 = 触发丢失或时基不对）
                       · 帧/触发应 ~1:1（远大于 1 = 相机在自由运行，没被触发驱动）
                       · L 的极差 < 2ms 才能认为映射稳定

时基说明: 本脚本用 CLOCK_MONOTONIC（与相机/PPS 时间戳常用时基一致）。
若要与取帧代码对齐，请确认取帧用的是同一个时钟。
"""

import os
import sys
import re
import glob
import time
import fcntl
import mmap
import errno
import select
import bisect
import struct
import argparse
import statistics
import termios

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEV_DEFAULT = '/dev/ttyACM0'
BAUD_DEFAULT = 115200

FRAME_LEN = 7
HEAD = 0xAA
TAIL = 0x55

CMD_STATUS = 0x02      # 应答帧
CMD_SYNC = 0x08        # 时钟同步（应答 24 位 MCU 时间戳）
CMD_QUERY = 0x09       # 查询最近一次触发时刻
CMD_REPORT = 0x0A      # 触发上报（MCU -> Orin）
CMD_ACK = 0x0B         # 上报累计确认（Orin -> MCU）
CMD_REPMODE = 0x0C     # 上报开关

MASK24 = 0xFFFFFF
D_CABLE = 608          # 7 字节 @115200-8N1 单向传输时间 (us)

ACK_INTERVAL = 0.10    # 确认周期 (s)，必须 <= 1s，否则 MCU 自动关闭上报

# --- V4L2 直接采集（--frames v4l2）-----------------------------------------
# ioctl 号按"64 位 Linux 结构体大小"编码，Orin NX(aarch64) 适用；仅单平面 MMAP。
VIDIOC_S_FMT = 0xC0D05605        # _IOWR('V', 5, struct v4l2_format)  208 字节
VIDIOC_REQBUFS = 0xC0145608      # _IOWR('V', 8, struct v4l2_requestbuffers) 20 字节
VIDIOC_QUERYBUF = 0xC0585609     # _IOWR('V', 9, struct v4l2_buffer) 88 字节
VIDIOC_QBUF = 0xC058560F         # _IOWR('V', 15, struct v4l2_buffer)
VIDIOC_DQBUF = 0xC0585611        # _IOWR('V', 17, struct v4l2_buffer)
VIDIOC_STREAMON = 0x40045612     # _IOW('V', 18, int)
VIDIOC_STREAMOFF = 0x40045613    # _IOW('V', 19, int)

V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_MEMORY_MMAP = 1
V4L2_BUFFER_SIZE = 88            # sizeof(struct v4l2_buffer)
V4L2_FORMAT_SIZE = 208           # sizeof(struct v4l2_format)
OFF_INDEX = 0
OFF_TYPE = 4
OFF_FLAGS = 12
OFF_TS_SEC = 24                  # struct timeval { long sec; long usec; }
OFF_TS_USEC = 32
OFF_MEMORY = 60
OFF_M_OFFSET = 64                # 联合体 m 的低 4 字节 = offset
OFF_LENGTH = 72
V4L2_BUF_FLAG_TIMESTAMP_MASK = 0x0000000E   # 位1~3 是时间戳类型; 0x01 是 MAPPED
V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC = 0x00000002

FRAME_UNIT_SCALE = {'us': 1.0, 'ms': 1000.0, 's': 1000000.0}


# ---------------------------------------------------------------------------
# 时基与帧
# ---------------------------------------------------------------------------
def now_us():
    """单调时钟微秒（CLOCK_MONOTONIC）。"""
    return int(time.clock_gettime(time.CLOCK_MONOTONIC) * 1000000)


def build_frame(cmd, p1=0, p2=0, p3=0):
    return bytes([HEAD, cmd, p1, p2, p3,
                  (HEAD + cmd + p1 + p2 + p3) & 0xFF, TAIL])


def frame_ok(f):
    return (len(f) == FRAME_LEN and f[0] == HEAD and f[6] == TAIL and
            f[5] == (sum(f[:5]) & 0xFF))


def ts24_of(p1, p2, p3):
    return (p1 << 16) | (p2 << 8) | p3


def signed24(delta):
    """把 24 位域的差值折算到 ±8.4s 内（用于偏移漂移比较）。"""
    return ((delta + (1 << 23)) & MASK24) - (1 << 23)


def to_jetson(ts24, t_recv_us, off24):
    """MCU 上报的 24 位触发时刻 -> Orin 时域微秒。

    上报延迟（<= 主循环周期，最坏约 1s）远小于 16.78s 的半周期，
    因此"收到时刻之前最近的同余值"就是唯一解（TIME_SYNC.md 3.4）。
    """
    d = (ts24 - off24) & MASK24
    return t_recv_us - ((t_recv_us - d) & MASK24)


# ---------------------------------------------------------------------------
# 串口
# ---------------------------------------------------------------------------
def _baud_const(baud):
    c = getattr(termios, 'B%d' % baud, None)
    if c is None:
        raise OSError('本机 termios 不支持波特率 %d' % baud)
    return c


def open_port(port, baud=BAUD_DEFAULT, settle=0.2):
    """打开串口（raw 模式）；port 为默认值时自动扫描 ttyACM*/ttyUSB*。"""
    cands = [port]
    if port == DEV_DEFAULT:
        cands = []
        for pat in ('/dev/ttyACM*', '/dev/ttyUSB*'):
            cands.extend(sorted(glob.glob(pat)))
    if not cands:
        raise OSError('未找到串口设备（%s / ttyACM* / ttyUSB*）' % DEV_DEFAULT)

    last_err = None
    for path in cands:
        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as e:
            last_err = e
            continue
        try:
            new = termios.tcgetattr(fd)
            new[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                        termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
            new[1] &= ~termios.OPOST
            new[2] &= ~(termios.CSIZE | termios.PARENB)
            new[2] |= termios.CS8
            new[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
                        termios.ISIG | termios.IEXTEN)
            new[2] = (new[2] & ~(termios.CSTOPB | termios.CRTSCTS)) | termios.CREAD | termios.CLOCAL
            new[4] = new[5] = _baud_const(baud)
            new[6][termios.VMIN] = 0
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new)
            termios.tcflush(fd, termios.TCIOFLUSH)
        except Exception:
            os.close(fd)
            raise
        time.sleep(settle)          # 覆盖 USB-CDC 打开瞬间的枚举抖动
        termios.tcflush(fd, termios.TCIFLUSH)
        return fd, path

    raise OSError('串口打开失败: %s' % last_err)


class Link(object):
    """0xAA…0x55 帧的收发。读侧自动丢弃噪声字节并重新同步到 0xAA。"""

    def __init__(self, fd):
        self.fd = fd
        self.buf = b''

    def send(self, cmd, p1=0, p2=0, p3=0):
        os.write(self.fd, build_frame(cmd, p1, p2, p3))

    def send_ts24(self, cmd, ts24):
        self.send(cmd, (ts24 >> 16) & 0xFF, (ts24 >> 8) & 0xFF, ts24 & 0xFF)

    def read_frames(self, timeout, stop_cmd=None):
        """返回 [(cmd, d1, d2, d3, t_recv_us), ...]，d1~d3 是帧里的 3 个数据字节。

        应答帧布局为 `AA 02 STATUS P1 P2 CS 55`：多数指令 d1=STATUS(u8状态码)、
        d2=P1、d3=P2；而 0x08/0x09 把 STATUS 当作时间戳最高字节，
        即 d1d2d3 = ts[23:0]（见 cmd_link.h）。

        t_recv_us 取"读到该批字节的时刻"。请求-应答模式必须传 stop_cmd
        （收到该指令的应答立即返回），否则会读到 timeout 用完才返回，
        T4 被整体推迟一个窗口，offset 会失真。

        同一次 read 里收到的多帧共用同一时刻，故流式场景（report/align）
        的投递延迟分辨率受轮询粒度限制（脚本里 20~50ms，够用）。
        """
        out = []
        end = time.monotonic() + timeout
        while True:
            remain = end - time.monotonic()
            if remain <= 0:
                break
            r, _, _ = select.select([self.fd], [], [], remain)
            if not r:
                break
            try:
                chunk = os.read(self.fd, 512)
            except BlockingIOError:
                continue
            if not chunk:
                break
            t_recv = now_us()
            self.buf += chunk

            hit = False
            while True:
                i = self.buf.find(bytes([HEAD]))
                if i < 0:
                    self.buf = b''
                    break
                self.buf = self.buf[i:]
                if len(self.buf) < FRAME_LEN:
                    break
                cand = self.buf[:FRAME_LEN]
                if frame_ok(cand):
                    self.buf = self.buf[FRAME_LEN:]
                    out.append((cand[1], cand[2], cand[3], cand[4], t_recv))
                    if stop_cmd is not None and cand[1] == stop_cmd:
                        hit = True
                        break
                else:
                    self.buf = self.buf[1:]     # 丢弃首字节后重新找 0xAA
            if hit:
                break
        return out

    def wait_status(self, timeout=2.0):
        """等待一帧 0x02 应答，返回 (d1, d2, d3, t_recv_us)；收到即返回。"""
        for cmd, d1, d2, d3, t in self.read_frames(timeout, stop_cmd=CMD_STATUS):
            if cmd == CMD_STATUS:
                return d1, d2, d3, t
        raise TimeoutError('未收到应答帧（可能处于 OTA 会话中，或未按 115200-8N1 连接）')

    # --- 指令封装 ---------------------------------------------------------
    def probe(self, retries=3, timeout=2.0):
        """握手探测: 打开串口瞬间的 DTR/RTS 抖动可能让 MCU 复位, 重试几次直到有应答。"""
        for _ in range(retries):
            self.send(CMD_STATUS)
            try:
                p1, p2, _p3, _t = self.wait_status(timeout)
                return True, p1, p2
            except TimeoutError:
                time.sleep(0.5)
        return False, 0, 0

    def firmware(self, timeout=2.0):
        """ASCII 命令 MCU_VER?（与 OTA 共用同一串口）。"""
        os.write(self.fd, b'MCU_VER?\r\n')
        buf = b''
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    buf += os.read(self.fd, 256)
                except BlockingIOError:
                    pass
            for line in buf.replace(b'\r', b'').split(b'\n'):
                if b'MCU_VER:' in line:
                    return line.decode('ascii', 'replace').strip()
        return None

    def status(self):
        """0x02 状态查询: 应答 `AA 02 STATUS P1 P2`，返回 (STATUS, GPS 锁定, 喂狗状态)。"""
        self.send(CMD_STATUS)
        st, p1, p2, _t = self.wait_status()
        return st, p1, p2

    def report_enable(self, on):
        """0x0C 上报开关: 应答 `AA 02 STATUS P1 P2`，返回 (STATUS, 开关状态, 丢帧计数)。"""
        self.send(CMD_REPMODE, 1 if on else 0)
        st, p1, p2, _t = self.wait_status()
        return st, p1, p2

    def sync_sample(self):
        """0x08: 返回 (T2, T4, off24)。仅在未开启上报时调用。"""
        self.send(CMD_SYNC)
        d1, d2, d3, t_recv = self.wait_status()
        t2 = ts24_of(d1, d2, d3)          # 0x08 把 STATUS 用作 ts[23:16]
        return t2, t_recv, t2 - t_recv + D_CABLE

    def query_trigger(self):
        """0x09: 返回 (最近一次触发时刻 ts24, t_recv)。"""
        self.send(CMD_QUERY)
        d1, d2, d3, t_recv = self.wait_status()
        return ts24_of(d1, d2, d3), t_recv


# ---------------------------------------------------------------------------
# 帧时间戳来源（align 模式）
# ---------------------------------------------------------------------------
def _first_number(line):
    """取一行里第一个可解析的数值（允许逗号/空格分隔）。"""
    for tok in line.replace(b',', b' ').replace(b'\t', b' ').split():
        try:
            return float(tok)
        except ValueError:
            continue
    return None


class FrameSource(object):
    """帧时间戳来源基类。时间戳统一为 CLOCK_MONOTONIC 微秒。"""

    name = 'none'
    soft_ts = False                     # True 表示时间戳不是驱动给的

    def start(self):
        pass

    def poll(self, timeout):
        """返回本次新增的帧时间戳列表（us）。"""
        return []

    def stop(self):
        pass

    def describe(self):
        return self.name


class FrameSourceFifo(FrameSource):
    """从 FIFO / 文件 / stdin 读帧时间戳：每行取第一个数值（单位见 --frame-unit）。

    适配任意取帧栈（GStreamer appsink / Argus / ROS / 自研取帧程序），
    只要把"帧到达时刻"按行写进来即可：
        mkfifo /tmp/frames.fifo
        python3 your_grabber.py > /tmp/frames.fifo &     # 每帧打印一个 CLOCK_MONOTONIC us
        python3 time_sync_test.py align --frames fifo --frame-path /tmp/frames.fifo
    """

    def __init__(self, path, scale=1.0):
        self.path = path
        self.scale = scale
        self.fd = None
        self.buf = b''
        self.name = 'fifo:%s' % path

    def start(self):
        if self.path == '-':
            self.fd = sys.stdin.fileno()
        else:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        self.buf = b''

    def poll(self, timeout):
        if self.fd is None:
            return []
        out = []
        r, _, _ = select.select([self.fd], [], [], timeout)
        if r:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                chunk = b''
            if not chunk:
                # EOF（管道/文件末尾）: 若写入方继续追加仍可读到, 这里小睡避免空转
                time.sleep(min(timeout, 0.01))
            else:
                self.buf += chunk
        while b'\n' in self.buf:
            line, self.buf = self.buf.split(b'\n', 1)
            ts = _first_number(line)
            if ts is not None:
                out.append(int(ts * self.scale))
        return out

    def stop(self):
        if self.fd is not None and self.path != '-':
            os.close(self.fd)
        self.fd = None


class FrameSourceV4L2(FrameSource):
    """直接采集 V4L2 节点，用**驱动给的单帧时间戳**（比软件打戳可靠得多）。

    实测两类驱动行为：
      1) 标了 V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC -> 直接可用
      2) 时间戳类型标 UNKNOWN，但数值与 CLOCK_MONOTONIC **有固定偏差**
         （本板 /dev/video0 实测恒定 +26.9s，量级与 BOOTTIME-MONOTONIC 之差一致）
         此时前 4 帧采样偏差：稳定（极差 < 1ms）就锁定并折算，否则退回软件打戳
    """

    def __init__(self, device, nbuf=4, width=0, height=0, pixfmt=0):
        self.dev = device
        self.nbuf = nbuf
        self.width = width
        self.height = height
        self.pixfmt = pixfmt
        self.name = 'v4l2:%s' % device
        self.fd = None
        self.maps = []
        self.ts_mode = 'soft'
        self.ts_note = ''
        self._drv_off = None

    @property
    def soft_ts(self):
        return self.ts_mode == 'soft'

    def _frame_ts(self, drv, mon):
        """把驱动时间戳折算到 CLOCK_MONOTONIC 域（偏差已在 _warmup 里锁定）。"""
        if self.ts_mode == 'soft':
            return now_us()
        if self.ts_mode == 'driver':
            return drv
        return drv - self._drv_off

    def _warmup(self):
        """STREAMON 后先排掉驱动里早已采好的陈旧缓冲，并锁定驱动时间戳的固定偏差。

        刚 STREAMON 时队列里的缓冲可能是很久以前采的，其时间戳与"现在"的偏差
        和稳态不一致；用"连续两帧偏差一致(<1ms)"作为锁定条件，稳态才认。
        """
        last = None
        for _ in range(12):
            r, _, _ = select.select([self.fd], [], [], 0.5)
            if not r:
                break
            buf = self._buf()
            try:
                fcntl.ioctl(self.fd, VIDIOC_DQBUF, buf)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EINTR):
                    continue
                raise
            idx = struct.unpack_from('@I', buf, OFF_INDEX)[0]
            flags = struct.unpack_from('@I', buf, OFF_FLAGS)[0]
            sec = struct.unpack_from('@Q', buf, OFF_TS_SEC)[0]
            usec = struct.unpack_from('@Q', buf, OFF_TS_USEC)[0]
            fcntl.ioctl(self.fd, VIDIOC_QBUF, self._buf(idx))

            mon = (flags & V4L2_BUF_FLAG_TIMESTAMP_MASK) == V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC
            drv = sec * 1000000 + usec
            if mon:
                self.ts_mode = 'driver'
                self.ts_note = '使用驱动时间戳（已标 MONOTONIC）'
                return
            if drv == 0:
                continue
            cand = drv - now_us()
            if last is not None and abs(cand - last) < 1000:
                self._drv_off = cand
                self.ts_mode = 'driver_offset'
                self.ts_note = ('驱动时间戳未标 MONOTONIC，但与 CLOCK_MONOTONIC 偏差恒定 '
                                '%+d us，已折算' % cand)
                return
            last = cand

        self.ts_mode = 'soft'
        self.ts_note = ('驱动时间戳不可用或偏差不稳定，已退回"取到帧的时刻"'
                        '（标定值只能当上界）')

    def _buf(self, index=None):
        b = bytearray(V4L2_BUFFER_SIZE)
        if index is not None:
            struct.pack_into('@I', b, OFF_INDEX, index)
        struct.pack_into('@I', b, OFF_TYPE, V4L2_BUF_TYPE_VIDEO_CAPTURE)
        struct.pack_into('@I', b, OFF_MEMORY, V4L2_MEMORY_MMAP)
        return b

    def start(self):
        self.fd = os.open(self.dev, os.O_RDWR | os.O_NONBLOCK)
        try:
            if self.width > 0 and self.height > 0:
                f = bytearray(V4L2_FORMAT_SIZE)
                struct.pack_into('@I', f, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
                struct.pack_into('@III', f, 8, self.width, self.height, self.pixfmt)
                fcntl.ioctl(self.fd, VIDIOC_S_FMT, f)
                self.width, self.height, self.pixfmt = struct.unpack_from('@III', f, 8)

            req = bytearray(20)
            struct.pack_into('@IIIII', req, 0, self.nbuf, V4L2_BUF_TYPE_VIDEO_CAPTURE,
                             V4L2_MEMORY_MMAP, 0, 0)
            # 注意: 传可变缓冲区(buf)时 ioctl 返回的是返回值(int), 缓冲区是原地修改,
            # 必须从传入的对象里取回填结果, 不能用返回值
            fcntl.ioctl(self.fd, VIDIOC_REQBUFS, req)
            count = struct.unpack_from('@I', req, 0)[0]
            if count < 1:
                raise OSError('%s: 驱动未分配缓冲区' % self.dev)

            for i in range(count):
                q = self._buf(i)
                fcntl.ioctl(self.fd, VIDIOC_QUERYBUF, q)
                length = struct.unpack_from('@I', q, OFF_LENGTH)[0]
                offset = struct.unpack_from('@I', q, OFF_M_OFFSET)[0]
                self.maps.append(mmap.mmap(self.fd, length,
                                           prot=mmap.PROT_READ | mmap.PROT_WRITE,
                                           flags=mmap.MAP_SHARED, offset=offset))

            for i in range(count):
                fcntl.ioctl(self.fd, VIDIOC_QBUF, self._buf(i))
            fcntl.ioctl(self.fd, VIDIOC_STREAMON,
                        struct.pack('@I', V4L2_BUF_TYPE_VIDEO_CAPTURE))
            self._warmup()          # 排陈旧缓冲 + 锁定驱动时间戳偏差
            self.name = 'v4l2:%s (%dx%d, %d 缓冲, ts=%s)' % (
                self.dev, self.width, self.height, count, self.ts_mode)
        except Exception:
            self.stop()
            raise

    def poll(self, timeout):
        if self.fd is None:
            return []
        out = []
        while True:
            r, _, _ = select.select([self.fd], [], [], timeout)
            if not r:
                break
            buf = self._buf()          # DQBUF 要求应用填好 type(和 memory)
            try:
                fcntl.ioctl(self.fd, VIDIOC_DQBUF, buf)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EINTR):
                    break
                raise
            idx = struct.unpack_from('@I', buf, OFF_INDEX)[0]
            flags = struct.unpack_from('@I', buf, OFF_FLAGS)[0]
            sec = struct.unpack_from('@Q', buf, OFF_TS_SEC)[0]
            usec = struct.unpack_from('@Q', buf, OFF_TS_USEC)[0]
            mon = (flags & V4L2_BUF_FLAG_TIMESTAMP_MASK) == V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC
            out.append(self._frame_ts(sec * 1000000 + usec, mon))
            fcntl.ioctl(self.fd, VIDIOC_QBUF, self._buf(idx))   # 立刻回队
            timeout = 0                                          # 还有就继续取
        return out

    def stop(self):
        if self.fd is None:
            return
        try:
            fcntl.ioctl(self.fd, VIDIOC_STREAMOFF,
                        struct.pack('@I', V4L2_BUF_TYPE_VIDEO_CAPTURE))
        except OSError:
            pass
        for m in self.maps:
            try:
                m.close()
            except Exception:
                pass
        self.maps = []
        os.close(self.fd)
        self.fd = None


def make_frame_source(args):
    if args.frames == 'v4l2':
        return FrameSourceV4L2(args.device, width=args.width, height=args.height,
                               pixfmt=args.pixfmt)
    if args.frames == 'fifo':
        return FrameSourceFifo(args.frame_path, FRAME_UNIT_SCALE[args.frame_unit])
    return None


# ---------------------------------------------------------------------------
# 测试项 1: 固件与状态
# ---------------------------------------------------------------------------
def fw_at_least(ver_line, want=(1, 2, 3)):
    """从 `MCU_VER: F306_MCU_A_ACC_V1.2_3` 解析版本号并与 want 比较；解析不到返回 None。"""
    if not ver_line:
        return None
    m = re.search(r'V(\d+)\.(\d+)_(\d+)', ver_line)
    if not m:
        return None
    return tuple(int(x) for x in m.groups()) >= want


def run_status(link):
    print('=== 1. 固件与状态 ===')
    fw = link.firmware()
    new_fw = fw_at_least(fw)
    if fw:
        print('  固件版本: %s' % fw)
        if new_fw is False:
            print('  [注意] 该版本不含 0x08/0x09/0x0A/0x0B/0x0C（需 >= V1.2_3），后续测试不适用')
    else:
        print('  [警告] MCU_VER? 无应答（ASCII 通道不通）；下面用二进制指令继续探测')

    st, gps, wdog = link.status()
    print('  0x02 状态: STATUS=%d  GPS 锁定=%s  喂狗=%s'
          % (st, gps, {0: '关闭', 1: '运行', 2: '超时'}.get(wdog, wdog)))
    if new_fw is False:
        return False
    print('  0x09 最近触发时刻: ts24=0x%06X' % link.query_trigger()[0])
    return True


# ---------------------------------------------------------------------------
# 测试项 2: 时间偏移重复性
# ---------------------------------------------------------------------------
def run_sync(link, n=16):
    print('=== 2. 时间偏移（0x08，单向公式 offset = T2 - T4 + %dus）===' % D_CABLE)
    samples = []
    for i in range(n):
        t2, t4, off = link.sync_sample()
        samples.append(off)
        print('  [%2d] T2=%6d us  T4=%-12d  off24=%d' % (i + 1, t2, t4, off))
        time.sleep(0.05)

    spread = max(samples) - min(samples)
    med = statistics.median(samples)
    best = max(samples)             # 读取延迟单向非负 -> 取 max 最接近真值

    print('  样本数 %d，极差 %.0f us，中位数 %d us' % (n, spread, med))
    print('  推荐取值 max(T2-T4) = %d us（最小读取延迟样本）' % best)

    if spread <= 1000:
        print('  [通过] 极差 <= 1ms，链路稳定，可直接用 max 作为 off24')
    elif spread <= 5000:
        print('  [可用] 极差 1~5ms：Orin 侧调度有抖动，建议改用 max，或提高进程优先级')
    else:
        print('  [失败] 极差 > 5ms：检查是否与上报/OTA 抢占串口，或 Orin 负载过高')
    return best, spread


# ---------------------------------------------------------------------------
# 测试项 3: 触发上报
# ---------------------------------------------------------------------------
def run_report(link, duration=10.0, freq=30, resync=5.0, off24=None):
    print('=== 3. 触发上报（0x0A/0x0B，时长 %.0fs，期望 %dHz）===' % (duration, freq))
    period_exp = 1000000.0 / freq

    if off24 is None:
        off24 = max(link.sync_sample()[2] for _ in range(8))
        print('  初始 off24 = %d us（0x08 连测 8 次取 max）' % off24)

    st, on, lost = link.report_enable(True)
    if st != 0 or on != 1:
        print('  [失败] 开启上报失败（STATUS=%d, on=%d）：确认固件 >= V1.2_3' % (st, on))
        try:
            link.report_enable(False)
        except Exception:
            pass
        return False
    print('  上报已开启（窗口满丢帧计数 = %d）；按 Ctrl-C 可提前结束' % lost)

    total_rx = 0
    uniq = []          # [(ts24, t_recv)] 只记"首次出现"的帧
    seen = set()
    drift = 0
    last_ts = None
    t_end = time.monotonic() + duration
    next_ack = 0.0
    next_sync = (time.monotonic() + resync) if resync > 0 else None

    try:
        while time.monotonic() < t_end:
            for cmd, d1, d2, d3, t_recv in link.read_frames(0.05):
                if cmd == CMD_REPORT:
                    ts24 = ts24_of(d1, d2, d3)
                    total_rx += 1
                    # 未确认帧会重发, 重传帧时间戳偏旧且会乱序, 统计一律按首次出现去重
                    if ts24 not in seen:
                        seen.add(ts24)
                        uniq.append((ts24, t_recv))
                    last_ts = ts24
                elif cmd == CMD_STATUS:
                    # 运行期重同步（0x08 应答，此时 STATUS 是时间戳高字节）
                    new_off = ts24_of(d1, d2, d3) - t_recv + D_CABLE
                    d = signed24(new_off - off24)
                    drift += d
                    off24 = off24 + d
                    print('  [重同步] 漂移累计 %+d us（本次 %+d us）' % (drift, d))

            if last_ts is not None and time.monotonic() >= next_ack:
                link.send_ts24(CMD_ACK, last_ts)
                next_ack = time.monotonic() + ACK_INTERVAL
            if next_sync is not None and time.monotonic() >= next_sync:
                link.send(CMD_SYNC)
                next_sync = time.monotonic() + resync
    except KeyboardInterrupt:
        print('  [中断] 用户提前结束')
    finally:
        try:
            link.report_enable(False)
            print('  上报已关闭')
        except Exception as e:
            print('  [警告] 关闭上报失败: %s（MCU 会在 1s 无确认后自动关闭）' % e)

    count = len(uniq)
    if count == 0:
        print('  [失败] 未收到任何 0x0A 上报帧：确认固件 >= V1.2_3、PWM 触发在运行')
        return False

    latencies = [tr - to_jetson(ts, tr, off24) for ts, tr in uniq]
    periods = [(b - a) & MASK24 for (a, _), (b, _) in zip(uniq, uniq[1:])]
    lost_est = sum(max(0, int(round(d / period_exp)) - 1) for d in periods)
    # 速率用"触发时域"算（各帧时间戳之和），与投递时刻无关
    span = sum(periods) / 1000000.0
    rate = ((count - 1) / span) if (count > 1 and span > 0) else 0.0

    print('  收到 %d 帧（去重后 %d 帧，重传/重复 %d 帧）' % (total_rx, count, total_rx - count))
    print('  实测速率 %.2f Hz（期望 %dHz，按时长 %.1fs 应收 %d 帧）'
          % (rate, freq, span, round(freq * span)))
    if periods:
        print('  触发周期: 均值 %.1f us / 最小 %d / 最大 %d / 极差 %d us（期望 %.1f us）'
              % (statistics.mean(periods), min(periods), max(periods),
                 max(periods) - min(periods), period_exp))
    if latencies:
        print('  投递延迟: 最小 %d / 均值 %.0f / 最大 %d us（收到时刻 - 该帧触发时刻）'
              % (min(latencies), statistics.mean(latencies), max(latencies)))
    print('  估计丢帧: %d 帧    偏移漂移: %+d us' % (lost_est, drift))

    ok = True
    if abs(rate - freq) > max(0.5, freq * 0.02):
        print('  [失败] 上报速率与触发频率不符：检查 PWM 档位是否与 --freq 一致')
        ok = False
    if periods and (max(periods) - min(periods)) > 1000:
        print('  [注意] 触发周期极差 > 1ms：正常应在百 us 量级（MCU 晶振 + 中断抖动）')
    if latencies:
        if min(latencies) < 0:
            print('  [失败] 出现负延迟：off24 偏大（触发时刻被算到收到时刻之后）')
            ok = False
        if max(latencies) > 1100 * 1000:
            print('  [失败] 最大投递延迟 > 1.1s：超过主循环周期上限，检查 MCU 是否被 OTA 占用')
            ok = False
        else:
            print('  [通过] 投递延迟落在主循环周期内（ACC 版 ~100ms / 非 ACC 版 ~500ms）')
    if lost_est > 0:
        print('  [注意] 估计丢帧 %d：0x0A 上报有重发机制，丢帧说明重发也没能送达' % lost_est)
    return ok


# ---------------------------------------------------------------------------
# 测试项 4: 相机帧对齐（触发时刻 ↔ 实际取帧时刻）
# ---------------------------------------------------------------------------
def run_align(link, args):
    print('=== 4. 相机帧对齐（触发时刻 ↔ 实际取帧时刻）===')
    period_exp = 1000000.0 / args.freq

    src = make_frame_source(args)
    if src is None:
        print('  [跳过] 未指定帧时间戳来源（--frames v4l2|fifo）')
        return None

    try:
        src.start()
    except Exception as e:
        print('  [失败] 打开帧来源失败: %s' % e)
        print('         若不好直接用 V4L2，请把取帧时间戳按行喂给 --frames fifo（见脚本头注释）')
        return False
    print('  帧来源: %s' % src.describe())

    off24 = max(link.sync_sample()[2] for _ in range(8))
    print('  off24 = %d us（0x08 连测 8 次取 max）' % off24)

    st, on, lost = link.report_enable(True)
    if st != 0 or on != 1:
        print('  [失败] 开启上报失败（STATUS=%d, on=%d）：确认固件 >= V1.2_3' % (st, on))
        try:
            link.report_enable(False)
        except Exception:
            pass
        src.stop()
        return False
    print('  上报已开启，采集 %.0fs ...' % args.duration)

    triggers = []
    frames = []
    seen = set()
    try:
        t_end = time.monotonic() + args.duration
        next_ack = 0.0
        last_ts = None
        while time.monotonic() < t_end:
            frames.extend(src.poll(0.02))
            for cmd, d1, d2, d3, t_recv in link.read_frames(0.02):
                if cmd == CMD_REPORT:
                    ts24 = ts24_of(d1, d2, d3)
                    if ts24 not in seen:            # 重传帧去重, 避免重复触发时刻
                        seen.add(ts24)
                        triggers.append(to_jetson(ts24, t_recv, off24))
                    last_ts = ts24
            if last_ts is not None and time.monotonic() >= next_ack:
                link.send_ts24(CMD_ACK, last_ts)
                next_ack = time.monotonic() + ACK_INTERVAL
    except KeyboardInterrupt:
        print('  [中断] 用户提前结束')
    finally:
        src.stop()
        try:
            link.report_enable(False)
            print('  上报已关闭')
        except Exception as e:
            print('  [警告] 关闭上报失败: %s' % e)

    if getattr(src, 'ts_note', ''):
        print('  [时间戳] %s' % src.ts_note)
    if src.soft_ts:
        print('  [注意] 帧时间戳是软件打戳（取到帧的时刻）：延迟会整体偏大且抖动明显，'
              '标定值仅作上界参考')

    return analyse_align(triggers, frames, period_exp, args.duration)


def analyse_align(triggers, frames, period_exp, duration=0.0):
    print('  触发 %d 条，帧 %d 条' % (len(triggers), len(frames)))
    if not triggers or not frames:
        print('  [失败] %s：确认 PWM 在输出、相机在出图、帧来源有数据'
              % ('未收到触发时刻' if not triggers else '未收到帧时间戳'))
        return False

    triggers.sort()
    frames.sort()

    # 只在"首个触发 ~ 末个触发 + 1.5 周期"这段公共窗口里配对：
    # 开采集时相机可能还有上一轮的帧在途，收尾时也可能多出几帧，都不算异常
    f_lo = triggers[0]
    f_hi = triggers[-1] + 1.5 * period_exp
    spans = [f for f in frames if f_lo <= f <= f_hi]
    pre = sum(1 for f in frames if f < f_lo)
    post = sum(1 for f in frames if f > f_hi)
    if pre or post:
        print('  参与配对 %d 帧（启动前忽略 %d，收尾忽略 %d）' % (len(spans), pre, post))
    if not spans:
        print('  [失败] 没有帧落在采集窗口内：帧时间戳的时基可能不是 CLOCK_MONOTONIC，'
              '或触发时刻换算有误')
        return False

    # 每帧配"不晚于它的最近一次触发"；间隔超过 1.5 个触发周期视为没有对应触发
    pairs = []
    unmatched = 0
    for tf in spans:
        i = bisect.bisect_right(triggers, tf) - 1
        if i < 0 or (tf - triggers[i]) > 1.5 * period_exp:
            unmatched += 1
            continue
        pairs.append((i, tf - triggers[i]))

    if not pairs:
        print('  [失败] 没有帧能配上触发：帧时间戳的时基可能不是 CLOCK_MONOTONIC，'
              '或触发时刻换算有误')
        return False

    lats = sorted(l for _, l in pairs)
    n = len(lats)
    med = lats[n // 2]
    mean = sum(lats) / n
    spread = lats[-1] - lats[0]
    p5 = lats[int(n * 0.05)]
    p95 = lats[min(n - 1, int(n * 0.95))]
    # 大延迟样本: 超过中位 +5ms。PWM 每秒一次的 PPS 相位对齐会让触发网格跳一次,
    # 跳变前后各有一帧被配到相邻触发上 -> 表现为约 1/s 的"大延迟 + 一号双帧"
    outliers = sum(1 for l in lats if l > med + 5000)

    per_trig = {}
    for i, _ in pairs:
        per_trig[i] = per_trig.get(i, 0) + 1
    multi = [k for k, v in per_trig.items() if v > 1]

    ratio = len(spans) / float(len(triggers))
    print('  匹配率: %d/%d = %.1f%%（未匹配 %d 帧）'
          % (len(pairs), len(spans), 100.0 * len(pairs) / len(spans), unmatched))
    print('  帧/触发 = %.2f（≈1 表示相机确实被触发驱动；远大于 1 说明在自由运行）' % ratio)
    print('  触发->帧 延迟 L: 最小 %d / 中位 %d / p95 %d / 均值 %.0f / 最大 %d us'
          % (lats[0], med, p95, mean, lats[-1]))
    print('  延迟极差 %d us，标准差 %.0f us，超中位+5ms 的样本 %d 个（%.1f/s）'
          % (spread, statistics.pstdev(lats), outliers,
             outliers / duration if duration > 0 else 0.0))

    gaps = [b - a for a, b in zip(spans, spans[1:])]
    if gaps:
        big = sum(1 for g in gaps if g > 1.5 * period_exp)
        print('  帧间隔: 均值 %.0f us（期望触发周期 %.1f us）/ 极差 %d us / 超周期缺口 %d 处'
              % (sum(gaps) / len(gaps), period_exp, max(gaps) - min(gaps), big))
    else:
        big = 0

    print('  前 3 组样本（触发时刻 -> 帧时刻，延迟）:')
    for i, lat in pairs[:3]:
        print('    trig @%d  ->  +%d us' % (triggers[i], lat))

    # 每秒一次的 PPS 相位对齐会造成约 1/s 的异常样本; 用它把"真异常"和"对齐跳变"分开
    realign_like = (duration > 0 and multi and len(multi) <= duration * 1.5 + 2)

    ok = True
    if unmatched > 0:
        print('  [失败] 有 %d 帧配不上触发：相机可能不在触发模式（自由运行），'
              '或触发信号未真正到达相机' % unmatched)
        ok = False
    if multi:
        if realign_like:
            print('  [注意] 有 %d 个触发对应了多帧、%d 处超周期缺口：数量与 PWM 每秒一次的'
                  'PPS 相位对齐跳变吻合（跳变会把相邻一帧配到隔壁触发上），属正常'
                  % (len(multi), big))
        else:
            print('  [失败] 有 %d 个触发对应了多帧：相机很可能在自由运行，'
                  '或触发脉宽 > 帧周期导致一次触发出多帧' % len(multi))
            ok = False
    if ratio > 1.2:
        print('  [失败] 帧数明显多于触发数（%.2f 帧/触发）：相机未受触发控制' % ratio)
        ok = False
    if ratio < 0.8:
        print('  [注意] 帧数明显少于触发数：相机出图跟不上触发，'
              '检查曝光时间是否过长、或触发脉宽/极性是否满足相机要求')
    if big > 0 and not realign_like:
        print('  [注意] 有 %d 处帧间隔超过 1.5 个触发周期：存在丢触发或相机丢帧' % big)
    if p95 - p5 <= 2000:
        print('  [通过] p95-p5 = %d us <= 2ms：延迟很稳定（p5 %d / 中位 %d / p95 %d us），'
              '可用中位数做帧对齐' % (p95 - p5, p5, med, p95))
    else:
        print('  [注意] p95-p5 = %d us 偏大：确认帧时间戳来自驱动而非软件打戳' % (p95 - p5))

    print('  标定结果: t_帧到达 ≈ t_触发 + %d us（中位数，含曝光+读出+CSI 传输+驱动）' % med)
    if duration > 0:
        print('  注: 复测时可用指令 0x07 00 临时关闭 PWM-PPS 相位对齐，'
              '以消除每秒一次的对齐跳变（测完用 0x07 01 恢复）')
    return ok


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(
        description='F306 MCU <-> Orin 时间同步 / 触发上报测试（零第三方依赖）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='示例:\n'
               '  python3 time_sync_test.py all\n'
               '  python3 time_sync_test.py sync --sync-n 32\n'
               '  python3 time_sync_test.py report --duration 20 --freq 30\n'
               '  python3 time_sync_test.py align --frames v4l2 --device /dev/video0\n'
               '  your_grabber | python3 time_sync_test.py align --frames fifo --frame-path -\n')
    p.add_argument('mode', choices=['status', 'sync', 'report', 'align', 'all'],
                   help='status 状态 / sync 偏移估算 / report 上报统计 / '
                        'align 相机帧对齐 / all 全部（align 需指定 --frames）')
    p.add_argument('--port', default=DEV_DEFAULT,
                   help='串口设备，默认 %s（失败时自动扫描 ttyACM*/ttyUSB*）' % DEV_DEFAULT)
    p.add_argument('--baud', type=int, default=BAUD_DEFAULT, help='波特率，默认 115200')
    p.add_argument('--sync-n', type=int, default=16, help='0x08 连测次数，默认 16')
    p.add_argument('--duration', type=float, default=10.0, help='report 模式时长(秒)，默认 10')
    p.add_argument('--freq', type=int, default=30, help='PWM 触发频率(Hz)，默认 30')
    p.add_argument('--resync', type=float, default=5.0,
                   help='report 模式运行期重跑 0x08 的间隔(秒)，0=不重跑，默认 5')
    p.add_argument('--frames', choices=['none', 'v4l2', 'fifo'], default='none',
                   help='align 模式的帧时间戳来源：v4l2 直接采集节点 / fifo 读外部时间戳 / '
                        'none 不测帧对齐')
    p.add_argument('--device', default='/dev/video0', help='--frames v4l2 的采集节点')
    p.add_argument('--frame-path', default='/tmp/frames.fifo',
                   help='--frames fifo 的时间戳来源（FIFO/文件，- 表示 stdin）')
    p.add_argument('--frame-unit', choices=['us', 'ms', 's'], default='us',
                   help='--frames fifo 的时间戳单位，默认 us')
    p.add_argument('--width', type=int, default=0,
                   help='--frames v4l2 显式设置格式时的宽（0=不改驱动当前格式）')
    p.add_argument('--height', type=int, default=0,
                   help='--frames v4l2 显式设置格式时的高（0=不改驱动当前格式）')
    p.add_argument('--pixfmt', type=lambda s: int(s, 0), default=0,
                   help='--frames v4l2 的 fourcc（如 0x56595559=YUYV），默认 0')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    fd, dev = open_port(args.port, args.baud)
    print('串口已打开 %s（%d 8N1），时基 CLOCK_MONOTONIC\n' % (dev, args.baud))
    link = Link(fd)
    results = {}

    try:
        if not link.probe()[0]:
            print('[警告] 未收到 0x02 应答：检查接线，或 MCU 正处于 OTA 会话中\n')

        if args.mode in ('status', 'all'):
            results['status'] = run_status(link)
            if args.mode == 'all':
                print('')

        off24 = None
        if args.mode in ('sync', 'all'):
            off24, spread = run_sync(link, args.sync_n)
            results['sync'] = spread <= 5000
            if args.mode == 'all':
                print('')

        if args.mode in ('report', 'all'):
            results['report'] = run_report(link, args.duration, args.freq,
                                           args.resync, off24)
            if args.mode == 'all' and args.frames != 'none':
                print('')

        if args.mode == 'align' or (args.mode == 'all' and args.frames != 'none'):
            r = run_align(link, args)
            if r is not None:
                results['align'] = r
    finally:
        os.close(fd)

    if len(results) > 1:
        print('\n=== 汇总 ===')
        for k, v in results.items():
            print('  %-8s %s' % (k, '通过' if v else '失败'))
        print('  总结果: %s' % ('通过' if all(results.values()) else '存在失败项'))
    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except OSError as e:
        print('错误: %s' % e)
        raise SystemExit(2)
    except KeyboardInterrupt:
        print('\n已中断')
        raise SystemExit(130)

#!/usr/bin/env python3
"""查询 MCU 固件版本（打开串口会 DTR 复位 MCU，必须等 1.6 s 再发）

用法: sudo mcu_ver.py [--port /dev/ttyACM0] [--retry 3]
输出示例: MCU_VER: F306_MCU_A_NOACC_V1.2_10
"""
import os, sys, time, select, termios

port = "/dev/ttyACM0"
retry = 3
args = sys.argv[1:]
for i, a in enumerate(args):
    if a == "--port" and i + 1 < len(args):
        port = args[i + 1]
    if a == "--retry" and i + 1 < len(args):
        retry = int(args[i + 1])

try:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
except OSError as e:
    print("open %s failed: %s" % (port, e))
    sys.exit(2)

a = termios.tcgetattr(fd)
a[4] = a[5] = termios.B115200
a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
a[0] = a[1] = a[3] = 0
a[6][termios.VMIN] = 0
a[6][termios.VTIME] = 0
termios.tcsetattr(fd, termios.TCSANOW, a)
time.sleep(1.6)
termios.tcflush(fd, termios.TCIOFLUSH)

for _ in range(retry):
    os.write(fd, b"MCU_VER?\n")
    buf = b""
    end = time.time() + 1.0
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            buf += os.read(fd, 256)
    if buf:
        print(buf.decode(errors="replace").strip())
        os.close(fd)
        sys.exit(0)
print("(no reply) MCU 无应答：检查 /dev/ttyACM0 是否存在、是否被其它进程占用")
os.close(fd)
sys.exit(1)

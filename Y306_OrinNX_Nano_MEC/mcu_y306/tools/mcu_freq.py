#!/usr/bin/env python3
"""通过串口下发 MCU 触发频率 / 占空比（0xAA…0x55 帧）

用法: sudo y306_mcu_freq.py [freq_hz] [duty_pct]
默认 10 Hz / 10%。

注意：打开串口会用 DTR 复位 MCU，必须等 ~1.6 s 让固件启动，否则发出的帧会被丢弃
（现象是"发得出去、没有应答"）。
"""
import os, sys, time, select, termios

PORT = "/dev/ttyACM0"
BAUD = 115200


def build(freq, duty):
    p = (freq * 100) & 0xFFFF
    cs = (0xAA + 0x01 + ((p >> 8) & 0xFF) + (p & 0xFF) + duty) & 0xFF
    return bytes([0xAA, 0x01, (p >> 8) & 0xFF, p & 0xFF, duty, cs, 0x55])


def main():
    freq = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    duty = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    frame = build(freq, duty)
    try:
        fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError as e:
        print("open %s failed: %s" % (PORT, e))
        return 2
    a = termios.tcgetattr(fd)
    a[4] = a[5] = termios.B115200
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[0] = a[1] = a[3] = 0
    a[6][termios.VMIN] = 0
    a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    time.sleep(1.6)                     # DTR 复位后等固件起来
    termios.tcflush(fd, termios.TCIOFLUSH)

    reply = b""
    for attempt in range(3):
        os.write(fd, frame)
        end = time.time() + 0.6
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                reply += os.read(fd, 64)
        if reply.startswith(b"\xaa"):
            break
        time.sleep(0.3)
    os.close(fd)
    print("TX %s" % frame.hex())
    print("RX %s" % reply[:7].hex())
    return 0 if reply.startswith(b"\xaa\x02") else 1


if __name__ == "__main__":
    sys.exit(main())

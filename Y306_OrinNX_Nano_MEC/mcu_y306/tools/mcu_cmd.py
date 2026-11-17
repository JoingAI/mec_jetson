#!/usr/bin/env python3
"""mcu_cmd.py — F306 MCU (V1.2.11) 命令行工具

用法:
  sudo python3 mcu_cmd.py ver                      # 版本 + 平台
  sudo python3 mcu_cmd.py status                   # 0x02: P1=PPS锁定 P2=喂狗
  sudo python3 mcu_cmd.py trig on --hz 30 --duty 10
  sudo python3 mcu_cmd.py trig off                 # 关闭触发 (duty=0)
  sudo python3 mcu_cmd.py trig preset 3            # 0x05 预设 (0..4)
  sudo python3 mcu_cmd.py ts                       # 0x09 最近触发时间戳
  sudo python3 mcu_cmd.py sync                     # 0x08 MCU 时间戳
  sudo python3 mcu_cmd.py wdog on --hz 5 --timeout 10
  sudo python3 mcu_cmd.py wdog off
  sudo python3 mcu_cmd.py align 1                  # 0=off 1=rising 2=falling
  sudo python3 mcu_cmd.py report on|off            # 0x0C
  sudo python3 mcu_cmd.py raw AA 01 03 E8 0A      # 自定义帧(自动补 CS/55)

  --port 默认 /dev/ttyACM0
"""
import argparse, sys, time

try:
    import serial
except ImportError:
    sys.exit('需要 pyserial: sudo apt install python3-serial')

PORT = '/dev/ttyACM0'


def frame(cmd, p1=0, p2=0, p3=0):
    f = [0xAA, cmd, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF]
    f += [sum(f) & 0xFF, 0x55]
    return bytes(f)


def send_usb(cmd, p1=0, p2=0, p3=0, wait=0.35):
    s = serial.Serial(PORT, 115200, timeout=0.4)
    time.sleep(0.15)
    s.reset_input_buffer()
    s.write(frame(cmd, p1, p2, p3))
    s.flush()
    time.sleep(wait)
    d = s.read(128)
    s.close()
    return d


def parse(d):
    for i in range(len(d) - 6):
        if d[i] == 0xAA and d[i + 1] == 0x02 and d[i + 6] == 0x55:
            if (sum(d[i:i + 5]) & 0xFF) == d[i + 5]:
                return {'status': d[i + 2], 'p1': d[i + 3], 'p2': d[i + 4]}
    return None


def ts24(d):
    r = parse(d)
    if not r or r['status'] != 0:
        return None
    return (r['p1'] << 16) | (r['p2'] << 8)


def main():
    global PORT
    ap = argparse.ArgumentParser(description='F306 MCU 命令工具')
    ap.add_argument('--port', default=PORT)
    sub = ap.add_subparsers(dest='act', required=True)

    sub.add_parser('ver')
    sub.add_parser('status')
    sub.add_parser('ts')
    sub.add_parser('sync')

    t = sub.add_parser('trig')
    t.add_argument('mode', choices=['on', 'off', 'preset'])
    t.add_argument('--hz', type=float, default=30.0)
    t.add_argument('--duty', type=int, default=10)
    t.add_argument('preset', nargs='?', type=int)

    w = sub.add_parser('wdog')
    w.add_argument('mode', choices=['on', 'off', 'param'])
    w.add_argument('--hz', type=int, default=5)
    w.add_argument('--timeout', type=int, default=10)

    a = sub.add_parser('align')
    a.add_argument('mode', type=int, choices=[0, 1, 2])

    r = sub.add_parser('report')
    r.add_argument('mode', choices=['on', 'off'])

    raw = sub.add_parser('raw')
    raw.add_argument('bytes', nargs='+', help='AA CMD P1 P2 P3（不含 CS/55）')

    args = ap.parse_args()
    PORT = args.port

    if args.act == 'ver':
        s = serial.Serial(PORT, 115200, timeout=0.5)
        time.sleep(0.2)
        s.reset_input_buffer()
        for _ in range(3):
            s.write(b'MCU_VER?\n'); s.flush(); time.sleep(0.6)
            d = s.read(200)
            if d:
                print(d.decode(errors='ignore').strip()); s.close(); return
        s.close(); print('无响应')

    elif args.act == 'raw':
        vals = [int(x, 16) for x in args.bytes]
        cmd, p1, p2, p3 = (vals + [0, 0, 0, 0])[:4]
        d = send_usb(cmd, p1, p2, p3)
        print('TX:', frame(cmd, p1, p2, p3).hex(' '))
        print('RX:', d.hex(' '), parse(d))

    else:
        cmd = p1 = p2 = p3 = 0
        if args.act == 'status':
            cmd = 0x02
        elif args.act == 'sync':
            cmd = 0x08
        elif args.act == 'ts':
            cmd = 0x09
        elif args.act == 'trig':
            if args.mode == 'preset':
                idx = args.preset if args.preset is not None else 3
                cmd, p1 = 0x05, idx
            elif args.mode == 'on':
                val = int(round(args.hz * 100))
                cmd, p1, p2, p3 = 0x01, (val >> 8) & 0xFF, val & 0xFF, args.duty
            else:
                cmd, p1, p2, p3 = 0x01, 0x0B, 0xB8, 0x00   # off: 30Hz duty=0
        elif args.act == 'wdog':
            if args.mode == 'off':
                cmd, p1 = 0x04, 0x00
            elif args.mode == 'on':
                cmd, p1, p2 = 0x04, 0x01, args.hz
            else:
                cmd, p1, p2, p3 = 0x04, 0x02, args.hz, args.timeout
        elif args.act == 'align':
            cmd, p1 = 0x07, args.mode
        elif args.act == 'report':
            cmd, p1 = 0x0C, (1 if args.mode == 'on' else 0)

        d = send_usb(cmd, p1, p2, p3)
        print('TX:', frame(cmd, p1, p2, p3).hex(' '))
        print('RX:', d.hex(' '), parse(d))


if __name__ == '__main__':
    main()

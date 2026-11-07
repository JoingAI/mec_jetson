#!/usr/bin/env python3
"""Y306 相机节点枚举：列出每个 /dev/videoN 对应的相机（i2c 地址/链路）并探测是否有图。

用法: sudo y306_list_cams.py [--probe] [--probe-sec 1.5]
不带 --probe 时只打印映射表（快）。
"""
import os, re, sys, glob, subprocess, time

LINK = {0x3a: "A", 0x3b: "B", 0x3c: "C", 0x3d: "D"}
G300 = {0x66: "Depth", 0x67: "Color", 0x68: "IR_L", 0x69: "IR_R"}


def read_name(v):
    p = "/sys/class/video4linux/%s/name" % v
    try:
        return open(p).read().strip()
    except OSError:
        return ""


def parse(name):
    m = re.search(r"fzcam (\d+)-([0-9a-f]{4})", name)
    if m:
        addr = int(m.group(2), 16)
        return ("RGB", "0x%02x" % addr, "Link %s" % LINK.get(addr, "?"))
    m = re.search(r"G300 (\w+) (\d+)-([0-9a-f]{4})", name, re.I)
    if m:
        stream, addr = m.group(1), int(m.group(3), 16)
        return ("335Lg", "0x%02x" % addr, "stream=%s" % stream)
    return ("?", "-", "-")


def probe(dev, sec):
    p = subprocess.Popen(["v4l2-ctl", "-d", dev, "--stream-mmap", "--verbose"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(sec)
    p.terminate()
    try:
        out, _ = p.communicate(timeout=4)
    except Exception:
        p.kill(); out = ""
    ts = [float(x) for x in re.findall(r'ts:\s*([0-9.]+)', out) if float(x) > 0]
    if len(ts) < 3:
        return None
    ts.sort()
    d = sorted((ts[i+1]-ts[i]) for i in range(len(ts)-1))
    d = [x for x in d if 0.001 < x < 1.0]
    return (1.0 / (sum(d)/len(d))) if d else None


def main():
    do_probe = "--probe" in sys.argv
    sec = 1.5
    if "--probe-sec" in sys.argv:
        sec = float(sys.argv[sys.argv.index("--probe-sec") + 1])
    rows = []
    for v in sorted(glob.glob("/dev/video*"), key=lambda p: int(re.sub(r"\D", "", p) or 0)):
        name = read_name(os.path.basename(v))
        kind, addr, extra = parse(name)
        fps = probe(v, sec) if do_probe else None
        rows.append((os.path.basename(v), kind, addr, extra, fps))
    w = max(len(r[0]) for r in rows) if rows else 8
    print("%-*s  %-6s %-6s %-8s %s" % (w, "node", "type", "addr", "port", "status"))
    live = 0
    for node, kind, addr, extra, fps in rows:
        if fps is None:
            st = "no signal" if do_probe else "-"
        else:
            st = "%.2f fps" % fps
            live += 1
        print("%-*s  %-6s %-6s %-8s %s" % (w, node, kind, addr, extra, st))
    if do_probe:
        print("\nlive=%d / %d" % (live, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

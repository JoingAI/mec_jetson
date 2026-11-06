import os, fcntl, struct, time, sys

BATCH_N = 32
SLOT = struct.Struct("<QQiIQ")           # tsc, seq, level, flags, ktime
BATCH_HDR = struct.Struct("<II")
BATCH_SIZE = BATCH_HDR.size + SLOT.size * BATCH_N

def ioc(dir, type_, nr, size):
    return (dir << 30) | (size << 16) | (ord(type_) << 8) | nr

GET_BATCH = ioc(3, 'Y', 1, BATCH_SIZE)   # _IOWR

fd = os.open("/dev/y306_fsync", os.O_RDWR)
buf = bytearray(BATCH_SIZE)
end = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 3)
edges = []
while time.time() < end:
    fcntl.ioctl(fd, GET_BATCH, buf, True)
    cnt, over = BATCH_HDR.unpack_from(buf, 0)
    off = BATCH_HDR.size
    for i in range(cnt):
        tsc, seq, level, flags, ktime = SLOT.unpack_from(buf, off + i*SLOT.size)
        edges.append((tsc, seq, level, flags, ktime))
    time.sleep(0.02)
os.close(fd)
print("edges=%d overrun=%d" % (len(edges), over))
if len(edges) > 2:
    ring = sum(1 for e in edges if e[2] == 1)
    t = [e[0] for e in edges]
    d = [(t[i+1]-t[i]) for i in range(len(t)-1)]
    d = [x for x in d if 0 < x < 2_000_000_000]
    if d:
        print("tsc 间隔 ns: mean=%.0f min=%d max=%d  -> %.4f Hz" % (sum(d)/len(d), min(d), max(d), 1e9/(sum(d)/len(d))))
    print("rising=%d  first tsc=%d last tsc=%d" % (ring, t[0], t[-1]))
    print("ktime 与 tsc 的一次采样: tsc=%d ktime=%d flags=0x%x" % (edges[0][0], edges[0][4], edges[0][3]))

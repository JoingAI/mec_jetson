import os, fcntl, struct, subprocess, sys, time, re, statistics

SLOT=struct.Struct("<QQiIQ"); HDR=struct.Struct("<II")
SIZE=HDR.size+SLOT.size*32
GET_BATCH=((3<<30)|(SIZE<<16)|(ord('Y')<<8)|1)

dev = sys.argv[1] if len(sys.argv)>1 else "/dev/video0"
dur = float(sys.argv[2]) if len(sys.argv)>2 else 10.0

proc = subprocess.Popen(["v4l2-ctl","-d",dev,"--stream-mmap","--verbose"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
fd=os.open("/dev/y306_fsync", os.O_RDWR)
buf=bytearray(SIZE); edges=[]
t0=time.time(); end=t0+dur
while time.time() < end:
    fcntl.ioctl(fd, GET_BATCH, buf, True)
    cnt,_=HDR.unpack_from(buf,0); off=HDR.size
    for i in range(cnt):
        e=SLOT.unpack_from(buf,off+i*SLOT.size)
        edges.append((e[0], e[4]))          # tsc ns, ktime ns
    time.sleep(0.005)
proc.terminate()
try: out,_=proc.communicate(timeout=3)
except Exception: proc.kill(); out=""
os.close(fd)

frames=[]
for line in out.splitlines():
    m=re.search(r'seq:\s*(\d+).*?ts:\s*([0-9.]+)', line)
    if m: frames.append((int(m.group(1)), float(m.group(2))*1e9))
frames=[f for f in frames if f[1]>0]
edges.sort()
if not frames or not edges:
    print("frames=%d edges=%d 数据不足" % (len(frames), len(edges))); sys.exit(0)

etsc=[e[0] for e in edges]
lat=[]
for seq, fts in frames:
    import bisect
    i=bisect.bisect_left(etsc, fts)-1
    if i < 0: continue
    lat.append((seq, fts, etsc[i], fts-etsc[i]))
if not lat:
    print("无配对"); sys.exit(0)
L=sorted(x[3]/1e6 for x in lat)
p=lambda q: L[min(len(L)-1,int(len(L)*q))]
print("dev=%s  帧=%d  边沿=%d  配对=%d  比例=%.4f" % (dev, len(frames), len(edges), len(lat), len(frames)/len(edges)))
print("延迟 ms: p5=%.3f p50=%.3f p95=%.3f  spread(p95-p5)=%.3f" % (p(0.05), p(0.5), p(0.95), p(0.95)-p(0.05)))
print("样例: seq=%d 帧tsc=%.6f 触发tsc=%.6f 延迟=%.3f ms" % (lat[0][0], lat[0][1]/1e9, lat[0][2]/1e9, lat[0][3]/1e6))

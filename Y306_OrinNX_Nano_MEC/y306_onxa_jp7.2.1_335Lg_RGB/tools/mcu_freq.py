import os, sys, time, select
def frame(cmd, p1, p2, p3):
    b = [0xAA, cmd, p1, p2, p3]
    b.append(sum(b) & 0xFF)
    b.append(0x55)
    return bytes(b)
freq_hz = int(sys.argv[1]) if len(sys.argv) > 1 else 60
duty = int(sys.argv[2]) if len(sys.argv) > 2 else 10
p = frame(0x01, (freq_hz*100 >> 8) & 0xFF, (freq_hz*100) & 0xFF, duty)
print("TX", p.hex())
fd = os.open("/dev/ttyACM0", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
os.write(fd, p)
time.sleep(0.3)
end = time.time() + 1.5
buf = b""
while time.time() < end:
    r, _, _ = select.select([fd], [], [], 0.2)
    if r:
        try: buf += os.read(fd, 256)
        except OSError: pass
print("RX", buf.hex()[:120])
os.close(fd)

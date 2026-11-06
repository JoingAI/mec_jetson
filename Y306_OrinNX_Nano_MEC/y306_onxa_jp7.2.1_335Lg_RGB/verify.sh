#!/bin/bash
# 按当前 profile 验证：节点、链路、触发同步、时间戳
set -uo pipefail
[ "$(id -u)" -eq 0 ] || { echo "请用 sudo 运行"; exit 1; }

PROF=$(cat /etc/y306-sync-profile 2>/dev/null || echo "?")
FRAMES=${1:-60}
FAIL=0
pass() { echo "  [PASS] $*"; }
fail() { echo "  [FAIL] $*"; FAIL=1; }

echo "===== 0. 环境"
echo "  $(date -Is)  kernel=$(uname -r)  profile=$PROF"
grep ^DEFAULT /boot/extlinux/extlinux.conf | sed 's/^/  /'
grep -E '^TRIGGER_HZ' /etc/y306-sync.conf 2>/dev/null | sed 's/^/  /'

echo "===== 1. 设备树"
if ls /proc/device-tree/bus@0/i2c@3180000/ 2>/dev/null | grep -q max; then
    ls /proc/device-tree/bus@0/i2c@3180000/ | grep -E 'max|fzcam|g2m' | sed 's/^/  /'
    pass "DT 已应用"
else
    fail "DT 未应用"
fi

echo "===== 2. 触发服务"
S=$(systemctl is-active y306-orbbec-trigger.service 2>/dev/null)
[ "$S" = "active" ] && pass "y306-orbbec-trigger active" || fail "y306-orbbec-trigger: $S"
journalctl -u y306-orbbec-trigger --no-pager -n 8 2>/dev/null | grep -E "y306-sync" | tail -3 | sed 's/^/  /'

echo "===== 3. FSYNC 边沿（HTE）"
if [ -e /dev/y306_fsync ]; then
    R=$(python3 /usr/local/bin/y306_fsync_read.py 3 2>/dev/null | grep -E "tsc 间隔|edges" | head -2)
    echo "$R" | sed 's/^/  /'
    echo "$R" | grep -q "10.0\||9.9\|10.00" && pass "边沿频率正常" || true
else
    fail "没有 /dev/y306_fsync"
fi

echo "===== 4. video 节点"
N=$(ls /dev/video* 2>/dev/null | wc -l)
echo "  节点数: $N"
case "$PROF" in
  a) [ "$N" -eq 6 ] && pass "6 路（2 RGB + 335Lg 4 流）" || fail "期望 6 路" ;;
  b) [ "$N" -eq 8 ] && pass "8 路（4 RGB + 335Lg 4 流）" || fail "期望 8 路" ;;
  c) [ "$N" -eq 8 ] && pass "8 路（2×335Lg）" || fail "期望 8 路" ;;
esac

echo "===== 5. 逐路取流"
dmesg -C
for v in $(ls /dev/video* | sort -V); do
    id=${v#/dev/video}
    pmt=$(v4l2-ctl -d "$v" --list-formats-ext 2>/dev/null | grep -m1 -oP "(?<=\[0\]: ')[^']+")
    case "$pmt" in
        UYVY) ARGS="--set-fmt-video=width=1920,height=1536,pixelformat=UYVY" ;;
        *)    ARGS="" ;;
    esac
    timeout 40 v4l2-ctl -d "$v" $ARGS --stream-mmap --stream-count="$FRAMES" --verbose > "/tmp/y306v$id.log" 2>&1
    rc=$?
    n=$(grep -c dqbuf "/tmp/y306v$id.log")
    bytes=$(grep -oP 'bytesused: \K[0-9]+' "/tmp/y306v$id.log" | tail -1)
    if [ "$rc" -eq 0 ] && [ "$n" -ge 1 ]; then
        pass "video$id ($pmt) $n 帧, ${bytes:-?} B/帧"
    else
        fail "video$id ($pmt) rc=$rc frames=$n"
    fi
done

echo "===== 6. 错误计数"
CE=$(dmesg | grep -cw corr_err || true)
UE=$(dmesg | grep -cw uncorr_err || true)
echo "  corr_err=$CE  uncorr_err=$UE"
[ "$UE" -eq 0 ] && pass "无 uncorr_err" || fail "出现 uncorr_err"

echo "===== 7. 触发同步（帧周期应等于触发周期）"
if python3 - "$PROF" <<'PY2'
import subprocess, re, statistics, sys, time
prof = sys.argv[1]
dev = "/dev/video5" if prof in ("a", "c") else "/dev/video0"
p = subprocess.Popen(["v4l2-ctl", "-d", dev, "--stream-mmap", "--verbose"],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(4)
p.terminate()
try:
    out, _ = p.communicate(timeout=5)
except Exception:
    p.kill(); out = ""
ts = [float(m) for m in re.findall(r'ts:\s*([0-9.]+)', out) if float(m) > 0]
if len(ts) < 20:
    print("  [FAIL] 取流帧数不足 (%d)" % len(ts)); sys.exit(1)
d = sorted((ts[i+1]-ts[i])*1e6 for i in range(len(ts)-1))
d = [x for x in d if 5000 < x < 500000]
if not d:
    print("  [FAIL] 帧间隔异常"); sys.exit(1)
med = statistics.median(d)
print("  %s 帧周期 median=%.1f us" % (dev, med))
if abs(med - 100000) < 2000:
    print("  [PASS] 跟随 10 Hz 触发（100 ms）"); sys.exit(0)
if abs(med - 50000) < 1500 or abs(med - 66667) < 1500 or abs(med - 33333) < 1500:
    print("  [PASS] 跟随触发（%.1f ms 分频）" % (med/1000)); sys.exit(0)
print("  [FAIL] 帧周期 %.1f us 与触发不匹配（可能自由运行）" % med); sys.exit(1)
PY2
then pass "帧周期与触发一致"; else fail "帧周期与触发不一致"; fi

echo "===== 8. 时间戳"
if [ -e /dev/y306_fsync ]; then
    python3 /usr/local/bin/y306_frame_ts.py --dev "$( [ "$PROF" = b ] && echo /dev/video0 || echo /dev/video5 )" \
        --duration 5 --out /tmp/y306_ts.csv 2>/dev/null | grep -E "延迟|重锁|outlier" | sed 's/^/  /'
    [ -s /tmp/y306_ts.csv ] && pass "每帧时间戳 CSV: /tmp/y306_ts.csv" || fail "时间戳工具失败"
else
    fail "缺少 /dev/y306_fsync，无法取时间戳"
fi

echo
if [ "$FAIL" -eq 0 ]; then echo "===== 结果：PASS ====="; else echo "===== 结果：FAIL ====="; fi
exit "$FAIL"

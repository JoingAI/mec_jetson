#!/bin/bash
# Y309 mixed acceptance: 20 Hz, 8 streams (4xISX031F + 335Lg 4流)
set -u
DUR=${1:-30}; MIN_FPS=19; MAX_FPS=21
D=/home/nvidia/accept-mixed-$(date +%Y%m%d-%H%M%S); mkdir -p "$D/videos"; LOG="$D/console.log"
say(){ echo "$*" | tee -a "$LOG"; }
say "== Y309 mixed acceptance $(date) duration=${DUR}min"
fail=0
[ -e /dev/video7 ] || { say "FAIL: /dev/video* missing"; exit 2; }
lsmod | grep -q "^g300" || { say "FAIL: g300 not loaded"; exit 2; }
ST=$(python3 /home/nvidia/y309_onxa_jp7.2.1_8xyuv/mcu_y309/y309ctl.py status 2>/dev/null); say "MCU: $ST"
case "$ST" in *en=1*) ;; *) say "FAIL: MCU trigger off"; exit 2;; esac
pids=""
for n in 0 1 2 3; do ( timeout $((DUR*60+60)) v4l2-ctl -d /dev/video$n --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap --stream-count=$((DUR*60*20+200)) --stream-to=/dev/null >$D/videos/v$n.log 2>&1 ) & pids="$pids $!"; done
for n in 4 5; do ( timeout $((DUR*60+60)) v4l2-ctl -d /dev/video$n --set-fmt-video=width=848,height=480,pixelformat=GREY --stream-mmap --stream-count=$((DUR*60*20+200)) --stream-to=/dev/null >$D/videos/v$n.log 2>&1 ) & pids="$pids $!"; done
( timeout $((DUR*60+60)) v4l2-ctl -d /dev/video6 --set-fmt-video=width=1280,height=720,pixelformat=YUYV --stream-mmap --stream-count=$((DUR*60*20+200)) --stream-to=/dev/null >$D/videos/v6.log 2>&1 ) & pids="$pids $!"
( timeout $((DUR*60+60)) v4l2-ctl -d /dev/video7 --stream-mmap --stream-count=$((DUR*60*20+200)) --stream-to=/dev/null >$D/videos/v7.log 2>&1 ) & pids="$pids $!"
say "streams started $(date +%T); settle 10s"; sleep 10; dmesg -C 2>/dev/null; T0=$(date +%s); sleep $((DUR*60)); T1=$(date +%s)
CORR=$(dmesg|grep -c corr_err); UNC=$(dmesg|grep -c uncorr_err); TO=$(dmesg|grep -c "request timed out")
wait $pids; say "streams stopped $(date +%T)"
{ echo "duration_s=$((T1-T0))"; echo "corr_err=$CORR"; echo "uncorr_err=$UNC"; echo "request_timed_out=$TO"; } | tee "$D/summary.txt"
for n in 0 1 2 3 4 5 6 7; do fps=$(grep -o '[0-9.]* fps' $D/videos/v$n.log | tail -1 | awk '{print $1}'); echo "video$n fps=$fps" | tee -a "$D/summary.txt"; [ -n "$fps" ] && awk -v f=$fps -v lo=$MIN_FPS -v hi=$MAX_FPS 'BEGIN{exit !(f>=lo&&f<=hi)}' || fail=1; done
[ "$CORR" = 0 ] || fail=1; [ "$UNC" = 0 ] || fail=1; [ "$TO" = 0 ] || fail=1
echo "RESULT: $([ $fail = 0 ] && echo PASS || echo FAIL)" | tee -a "$D/summary.txt"
dmesg > "$D/dmesg.log" 2>/dev/null || true
exit $fail

#!/bin/bash
# Y306 同步栈开机初始化
#   1) 触发源：MCU（默认）/ SoC 生成 / 自动探测，并下发频率
#   2) 335Lg 设硬件触发模式（SDK），失败重试 + 回读校验
CONF=/etc/y306-sync.conf
TRIGGER_HZ=10
FRAMES_PER_TRIGGER=1
TRIGGER_SOURCE=mcu
[ -r "$CONF" ] && . "$CONF"

log() { echo "[y306-sync] $*"; }
KO=/lib/modules/$(uname -r)/updates/y306-fsync/y306_fsync_cap.ko
MCULOG=/tmp/y306-mcu.log

# 下发 MCU 触发频率（0xAA 帧），成功返回 0
send_mcu() {
    [ -e /dev/ttyACM0 ] || return 1
    python3 /usr/local/bin/y306_mcu_freq.py "$TRIGGER_HZ" 10 >"$MCULOG" 2>&1
    grep -q "RX aa" "$MCULOG"
}

# --- 1) 触发源 ---
mcu_rx=""
case "$TRIGGER_SOURCE" in
  soc)
    want=1 ;;
  mcu)
    want=0
    for i in 1 2 3; do
        if send_mcu; then mcu_rx=$(grep -o 'RX .*' "$MCULOG" | head -1); break; fi
        sleep 2
    done ;;
  *)
    for i in 1 2 3 4 5; do [ -e /dev/ttyACM0 ] && break; sleep 1; done
    if send_mcu; then want=0; mcu_rx=$(grep -o 'RX .*' "$MCULOG" | head -1)
    else want=1; fi ;;
esac

gen=$(cat /sys/module/y306_fsync_cap/parameters/gen_hz 2>/dev/null || echo 0)
if [ "$want" = "1" ]; then
    if [ "${gen:-0}" != "$TRIGGER_HZ" ] && [ -f "$KO" ]; then
        modprobe -r y306_fsync_cap 2>/dev/null
        insmod "$KO" gen_hz="$TRIGGER_HZ" gen_duty=10 || log "WARN: 生成模式加载失败"
        for i in $(seq 1 20); do [ -e /dev/y306_fsync ] && break; sleep 0.2; done
    fi
    gen=$(cat /sys/module/y306_fsync_cap/parameters/gen_hz 2>/dev/null || echo 0)
    log "trigger source: SoC generator @ ${TRIGGER_HZ} Hz (gen_hz=${gen:-?})"
else
    if [ "${gen:-0}" != "0" ]; then
        modprobe -r y306_fsync_cap 2>/dev/null
        insmod "$KO" gen_hz=0 2>/dev/null
        for i in $(seq 1 20); do [ -e /dev/y306_fsync ] && break; sleep 0.2; done
    fi
    if [ -n "$mcu_rx" ]; then
        log "trigger source: MCU @ ${TRIGGER_HZ} Hz ($mcu_rx)"
    else
        log "WARN: MCU 未应答（无触发，相机不会出图）"
    fi
fi
sleep 0.3

# --- 2) 335Lg 硬件触发 ---
ok=0
for i in 1 2 3 4 5; do
    out=$(/usr/local/bin/y306_orb_trigger --frames-per-trigger "$FRAMES_PER_TRIGGER" 2>&1)
    if echo "$out" | grep -q "set syncMode=0x40"; then
        log "335Lg -> hardware triggering OK (attempt $i)"
        ok=1
        break
    fi
    log "WARN: attempt $i: $(echo "$out" | tail -1)"
    sleep 2
done
[ "$ok" = "1" ] || log "ERROR: 335Lg 触发模式设置失败，最后一次: $out"
exit 0

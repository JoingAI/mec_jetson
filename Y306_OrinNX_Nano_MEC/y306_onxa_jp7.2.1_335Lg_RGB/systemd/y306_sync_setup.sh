#!/bin/bash
# Y306 同步栈开机初始化：
#   1) 下发 MCU 触发频率（默认 10 Hz）
#   2) 把 335Lg 设为硬件触发模式（SDK）
# 参数来自 /etc/y306-sync.conf（TRIGGER_HZ / FRAMES_PER_TRIGGER）
CONF=/etc/y306-sync.conf
TRIGGER_HZ=10
FRAMES_PER_TRIGGER=1
[ -r "$CONF" ] && . "$CONF"

log() { echo "[y306-sync] $*"; }

# 1) MCU
if [ -e /dev/ttyACM0 ]; then
    if python3 /usr/local/bin/y306_mcu_freq.py "$TRIGGER_HZ" 10 >/tmp/y306-mcu.log 2>&1; then
        log "MCU trigger set to ${TRIGGER_HZ} Hz: $(grep -o 'RX .*' /tmp/y306-mcu.log | head -1)"
    else
        log "WARN: MCU 触发频率设置失败（见 /tmp/y306-mcu.log）"
    fi
else
    log "WARN: /dev/ttyACM0 不存在，跳过 MCU 设置"
fi
sleep 0.3

# 2) 335Lg 硬件触发
if command -v /usr/local/bin/y306_orb_trigger >/dev/null 2>&1; then
    if out=$(/usr/local/bin/y306_orb_trigger --frames-per-trigger "$FRAMES_PER_TRIGGER" 2>&1); then
        log "$out"
        echo "$out" | grep -q "set syncMode=0x40" && log "335Lg -> hardware triggering OK" \
            || log "WARN: 335Lg 触发模式未确认"
    else
        log "WARN: 335Lg 触发设置失败: $out"
    fi
else
    log "WARN: /usr/local/bin/y306_orb_trigger 不存在"
fi
exit 0

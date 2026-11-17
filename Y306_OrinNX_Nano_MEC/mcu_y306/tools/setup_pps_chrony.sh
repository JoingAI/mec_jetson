#!/bin/bash
# ============================================================================
# setup_pps_chrony.sh —— 无 GPS 场景「方案 A」Jetson 侧实施脚本
#
#   原理: MCU 在没有 GPS 时用 TIM1 输出内部 1Hz PPS (PB13/PB14), 并把相机 PWM
#         触发沿每秒复位一次对齐到该 PPS。把 PB13 接到 Jetson 的 PPS 输入脚,
#         Jetson 用 chrony 锁定到该 PPS 后:
#           - Jetson 时钟的"频率"被锁到 MCU 晶振 -> MCU 触发时刻与 Jetson 时基的
#             偏移不再漂移, 0x08 只需测一次
#           - 每个 PPS 沿 = 触发网格的秒边界, 可直接推算任意触发的时刻
#         注意 MCU 的内部 PPS 是自由跑的 1Hz, 绝对秒是任意的(非 UTC), 所以
#         Jetson 时钟会被锁到 MCU 的"秒网格"上 —— 这对跨设备对齐完全够用,
#         因为两边的时间偏移由 0x08 一次性测得, 与绝对时间无关。
#
#   用法(在 Jetson/Orin 上, 需 root):
#     sudo bash setup_pps_chrony.sh                 # 自动挑非 ktimer 的 pps 设备
#     sudo bash setup_pps_chrony.sh /dev/pps1
#     sudo bash setup_pps_chrony.sh --dry-run       # 只检测不改配置
#
#   接线: MCU PB13(模拟PPS输出1) -> Jetson PPS 输入脚
#         本板实测 pps-gpio 已配在 PCC.03 (gpio-331, DT 节点 /bus@0/pps),
#         接好后 /sys/class/pps/pps1/assert 的计数应以 1Hz 递增。
# ============================================================================
set -u

DRY=0
DEV=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    /dev/pps*) DEV="$a" ;;
    *) echo "未知参数: $a"; exit 2 ;;
  esac
done

die()  { echo "[错误] $*" >&2; exit 1; }
info() { echo "[信息] $*"; }
warn() { echo "[注意] $*"; }

[ "$(id -u)" = "0" ] || die "需要 root（sudo bash $0）"

# ---------------------------------------------------------------------------
# 1. 找 PPS 设备: ktimer 是内核合成源，必须排除
# ---------------------------------------------------------------------------
if [ -z "$DEV" ]; then
  for d in /dev/pps*; do
    [ -e "$d" ] || continue
    n=$(cat "/sys/class/pps/$(basename "$d")/name" 2>/dev/null || echo "")
    if [ "$n" != "ktimer" ]; then DEV="$d"; break; fi
  done
fi
[ -n "$DEV" ] || die "没找到 PPS 设备（只有 ktimer）。需在设备树里加 pps-gpio 节点后重启"
PPS_NAME=$(cat "/sys/class/pps/$(basename "$DEV")/name" 2>/dev/null || echo "?")
info "使用 $DEV （source=$PPS_NAME）"

# ---------------------------------------------------------------------------
# 2. 检查 PPS 是否真的在来沿（@1Hz）——没接线时这里就会失败
# ---------------------------------------------------------------------------
a0=$(cat "/sys/class/pps/$(basename "$DEV")/assert" 2>/dev/null | cut -d'#' -f2 | cut -d: -f1)
l0=$(cat "/sys/class/pps/$(basename "$DEV")/assert" 2>/dev/null | sed 's/.*: //')
sleep 3
a1=$(cat "/sys/class/pps/$(basename "$DEV")/assert" 2>/dev/null | cut -d'#' -f2 | cut -d: -f1)
l1=$(cat "/sys/class/pps/$(basename "$DEV")/assert" 2>/dev/null | sed 's/.*: //')
[ -n "${a0:-}" ] || die "读不到 $DEV/assert"
d=$(( a1 - a0 ))
info "3 秒内 PPS 沿数 = $d （期望 2~3）"
if [ "$d" -lt 1 ]; then
  die "没收到 PPS 沿：请确认 MCU 的 PB13 已接到 PCC.03，且 MCU 在输出模拟 PPS
       （GPS 锁定时 MCU 会关闭模拟 PPS，无 GPS 场景下应常开）"
fi
[ "$d" -ge 2 ] && [ "$d" -le 4 ] || warn "沿数异常($d/3s)，检查 MCU 是否 1Hz、有无抖动"

# PPS 沿在"系统秒"里的相位: assert 的 .nsec 部分
ns=$(echo "$l1" | awk -F. '{printf "%d", substr($2"000000000",1,9)}')
phase_us=$(( ns / 1000 ))
info "PPS 沿落在系统秒内 $phase_us us 处（用于粗对齐，chrony 需 <500ms 才能关联）"

# ---------------------------------------------------------------------------
# 3. 安装 chrony（无 GPS 场景下它是唯一 PPS 驯服手段）
# ---------------------------------------------------------------------------
if ! command -v chronyd >/dev/null 2>&1; then
  if [ "$DRY" = "1" ]; then
    warn "未安装 chrony（dry-run 不安装）"
  else
    info "安装 chrony ..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y chrony >/dev/null 2>&1 || \
      die "apt-get install chrony 失败（离线环境请离线包安装）"
  fi
fi
if systemctl is-active --quiet systemd-timesyncd 2>/dev/null; then
  if [ "$DRY" = "0" ]; then
    info "停用 systemd-timesyncd（与 chrony 互斥）"
    systemctl disable --now systemd-timesyncd >/dev/null 2>&1 || true
  fi
fi

# ---------------------------------------------------------------------------
# 4. 写 chrony 配置
# ---------------------------------------------------------------------------
CONF=/etc/chrony/chrony.conf
if [ "$DRY" = "1" ]; then
  info "dry-run: 跳过写 $CONF / 对时 / 重启 chrony"
  exit 0
fi

[ -f "$CONF" ] && [ ! -f "$CONF.f306.bak" ] && cp -a "$CONF" "$CONF.f306.bak" && info "已备份原配置到 $CONF.f306.bak"

cat > "$CONF" <<EOF
# F306 无 GPS 时间同步（由 tools/setup_pps_chrony.sh 生成）
# MCU 内部 1Hz PPS -> $DEV，chrony 据此锁频；绝对秒由 MCU 自由跑的网格决定

refclock PPS $DEV refid PPS poll 3 dpoll -2 offset 0.0 prefer
# 若有 LAN 内 NTP 可解注下面一行做粗同步（无网络时不需要，见脚本第 3 步的相位粗对齐）
# pool ntp.ubuntu.com iburst maxsources 2

makestep 0.5 3
rtcsync
driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
EOF
info "已写 $CONF"

# ---------------------------------------------------------------------------
# 5. 相位粗对齐: 把系统秒边界挪到 PPS 沿之前，使 chrony 能关联到秒
#    只做一次小步进(<=0.5s)，之后频率由 chrony 维持
# ---------------------------------------------------------------------------
if [ "$phase_us" -gt 500000 ]; then
  step=$(awk -v us="$phase_us" 'BEGIN{printf "%.6f", (us-1000)/1e6}')
  info "相位粗对齐: 系统时钟回拨 ${step}s（把 PPS 沿挪到秒边界附近）"
  date -s "-${step} seconds" >/dev/null 2>&1 || warn "date -s 失败，可手动对齐"
fi

systemctl enable chrony >/dev/null 2>&1 || true
systemctl restart chrony || die "chrony 启动失败，看 journalctl -u chrony"
sleep 6

echo
echo "================= 结果 ================="
chronyc tracking 2>&1 | sed -n '1,12p'
echo "--- sources ---"
chronyc sources 2>&1 | sed -n '1,8p'
echo
cat <<'TIP'
判读要点:
  · chronyc tracking 的 "Reference ID" 应为 PPS；"Frequency" 是相对理想 1Hz 的
    频偏(ppm)，稳定在几十 ppm 内即说明已锁到 MCU 晶振
  · "System time" 的偏移应逐步收敛到 us 量级
  · 之后 MCU 侧的 0x08 偏移量应基本不漂移（原来 ~200ppm，约 2ms/10s）
复测: python3 time_sync_test.py report --duration 30 --resync 5
      （看 "偏移漂移" 字段，方案 A 生效后应远小于之前的 ms 量级）
TIP

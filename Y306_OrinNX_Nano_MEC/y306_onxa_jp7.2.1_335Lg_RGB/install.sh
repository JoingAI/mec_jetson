#!/bin/bash
# Y306 同步相机套件安装（全新整机可用）
#   profile a: MAX9296 = 2x ISX031F (RGB)  + MAX96724 = 1x Gemini 335Lg
#   profile b: MAX96724 = 4x ISX031F (RGB) + MAX9296 = 1x Gemini 335Lg
#   profile c: MAX9296 + MAX96724 各 1x Gemini 335Lg（无 RGB）
#
# 用法: sudo bash install.sh --profile a|b|c [--no-reboot] [--trigger-hz N]
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
PROFILE=""
REBOOT=1
TRIGGER_HZ=10

usage() {
    cat <<EOF
用法: sudo bash install.sh --profile a|b|c [--no-reboot] [--trigger-hz N]

  a = 2x RGB/YUV (MAX9296)  + 1x Gemini 335Lg (MAX96724)   6 路 video 节点
  b = 4x RGB/YUV (MAX96724) + 1x Gemini 335Lg (MAX9296)    8 路 video 节点
  c = 1x 335Lg (MAX9296) + 1x 335Lg (MAX96724)             8 路 video 节点

  --trigger-hz N   硬件触发频率（默认 10），需 <= 相机流帧率/2
  --no-reboot      安装完不自动重启（DT 仍需重启生效）
EOF
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --profile|-p) PROFILE="${2:-}"; shift 2 ;;
        --trigger-hz) TRIGGER_HZ="${2:-10}"; shift 2 ;;
        --no-reboot)  REBOOT=0; shift ;;
        -h|--help)    usage ;;
        *) echo "未知参数: $1"; usage ;;
    esac
done

case "$PROFILE" in a|b|c) ;; *) usage ;; esac
[ "$(id -u)" -eq 0 ] || { echo "请用 sudo 运行"; exit 1; }

KVER=$(uname -r)
MODDIR="/lib/modules/$KVER/updates/y306-obc"
FSYNCDIR="/lib/modules/$KVER/updates/y306-fsync"
CAMDIR="/lib/modules/$KVER/updates/drivers/media/platform/tegra/camera"
DTBO="/boot/tegra234-p3767-camera-p3768-y306-mixed-$PROFILE.dtbo"
BAKDIR="/root/y306-sync-backup"

say() { echo "[$(date +%H:%M:%S)] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

say "0/9 环境检查"
[ -f "$HERE/artifacts/dtbo/tegra234-p3767-camera-p3768-y306-mixed-$PROFILE.dtbo" ] \
    || die "缺少 profile $PROFILE 的 dtbo"
for k in g300 obc_max9296 obc_max96712 obcam fzcam tegra-camera y306_fsync_cap; do
    [ -f "$HERE/artifacts/modules/$k.ko" ] || die "缺少模块 $k.ko"
done
[ -f "$HERE/artifacts/sdk/y306_orb_trigger" ] || die "缺少 y306_orb_trigger"
[ -f "$HERE/artifacts/sdk/libOrbbecSDK.so.2.7.6" ] || die "缺少 libOrbbecSDK"

mkdir -p "$BAKDIR"
cp -n /boot/extlinux/extlinux.conf "$BAKDIR/extlinux.conf.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
cp -n /etc/fzcam_cfg.ini "$BAKDIR/fzcam_cfg.ini.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

say "1/9 安装 dtbo -> $DTBO"
install -m 644 "$HERE/artifacts/dtbo/tegra234-p3767-camera-p3768-y306-mixed-$PROFILE.dtbo" "$DTBO"

say "2/9 安装内核模块"
mkdir -p "$MODDIR" "$FSYNCDIR" "$CAMDIR"
for k in g300 obc_max9296 obc_max96712 obcam fzcam; do
    install -m 644 "$HERE/artifacts/modules/$k.ko" "$MODDIR/$k.ko"
done
install -m 644 "$HERE/artifacts/modules/y306_fsync_cap.ko" "$FSYNCDIR/y306_fsync_cap.ko"
if [ -f "$CAMDIR/tegra-camera.ko" ] && [ ! -f "$CAMDIR/tegra-camera.ko.orig" ]; then
    cp "$CAMDIR/tegra-camera.ko" "$CAMDIR/tegra-camera.ko.orig"
fi
install -m 644 "$HERE/artifacts/modules/tegra-camera.ko" "$CAMDIR/tegra-camera.ko"
depmod -a "$KVER"

say "3/9 安装 Orbbec SDK 运行库 + 触发设置工具"
mkdir -p /opt/orbbec-sdk/lib
install -m 644 "$HERE/artifacts/sdk/libOrbbecSDK.so.2.7.6" /opt/orbbec-sdk/lib/
ln -sf libOrbbecSDK.so.2.7.6 /opt/orbbec-sdk/lib/libOrbbecSDK.so.2
ln -sf libOrbbecSDK.so.2.7.6 /opt/orbbec-sdk/lib/libOrbbecSDK.so
install -m 755 "$HERE/artifacts/sdk/y306_orb_trigger" /usr/local/bin/y306_orb_trigger
echo /opt/orbbec-sdk/lib > /etc/ld.so.conf.d/orbbec-sdk.conf
ldconfig

say "4/9 安装同步工具"
install -m 755 "$HERE/tools/y306_frame_ts.py" /usr/local/bin/y306_frame_ts.py
install -m 755 "$HERE/tools/fsync_read.py"   /usr/local/bin/y306_fsync_read.py
install -m 755 "$HERE/tools/mcu_freq.py"     /usr/local/bin/y306_mcu_freq.py
install -m 755 "$HERE/tools/y306_list_cams.py" /usr/local/bin/y306_list_cams.py
# MCU 固件与 OTA 工具（常驻 /opt/y306-sync/mcu，便于现场二次升级）
install -d /opt/y306-sync
rm -rf /opt/y306-sync/mcu
cp -r "$HERE/mcu" /opt/y306-sync/mcu
chmod +x /opt/y306-sync/mcu/upgrade.sh /opt/y306-sync/mcu/tools/*.py
install -m 755 "$HERE/mcu/tools/mcu_ver.py" /usr/local/bin/y306_mcu_ver.py
install -m 755 "$HERE/systemd/y306_sync_setup.sh" /usr/local/bin/y306_sync_setup.sh

say "5/9 配置 fzcam（RGB 侧）"
install -m 644 "$HERE/conf/fzcam_cfg-$PROFILE.ini" /etc/fzcam_cfg.ini

say "6/9 配置 systemd 服务"
cat > /etc/y306-sync.conf <<EOF
TRIGGER_HZ=$TRIGGER_HZ
FRAMES_PER_TRIGGER=1
EOF
install -m 755 "$HERE/systemd/y306-obc-load.sh" /usr/local/sbin/y306-obc-load.sh
install -m 644 "$HERE/systemd/y306-obc-camera.service" /etc/systemd/system/
install -m 644 "$HERE/systemd/y306-orbbec-trigger.service" /etc/systemd/system/
install -m 644 "$HERE/systemd/y306-orbbec-trigger-late.service" /etc/systemd/system/
install -m 644 "$HERE/systemd/y306-orbbec-trigger-late.timer" /etc/systemd/system/
mkdir -p /etc/systemd/system/fzcam_cfg.service.d
install -m 644 "$HERE/systemd/fzcam-order.conf" /etc/systemd/system/fzcam_cfg.service.d/10-y306-obc.conf
cat > /etc/modprobe.d/y306-obc-manual.conf <<EOF
install obc_max9296 /bin/false
install obc_max96712 /bin/false
install g300 /bin/false
install obcam /bin/false
EOF
systemctl daemon-reload
systemctl enable y306-obc-camera.service y306-orbbec-trigger.service y306-orbbec-trigger-late.timer >/dev/null 2>&1

say "7/9 设置启动项"
python3 "$HERE/extlinux-add.py" "$PROFILE" || die "启动项设置失败"

say "8/9 记录 profile"
echo "$PROFILE" > /etc/y306-sync-profile
sync

say "9/9 完成"
echo
echo "  当前 profile : $PROFILE"
echo "  触发频率     : $TRIGGER_HZ Hz"
echo "  默认启动项   : $(grep ^DEFAULT /boot/extlinux/extlinux.conf)"
echo
if [ "$REBOOT" = "1" ]; then
    echo "  DT 与模块需重启生效，建议执行：sudo reboot"
else
    echo "  已跳过重启（DT 需重启生效）"
fi
echo "  MCU 版本：sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc --check"
echo "  MCU 升级：sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc"
echo "  验证：sudo bash $HERE/verify.sh"
echo "  回滚：sudo bash $HERE/uninstall.sh"

#!/bin/bash
# 回滚：移除同步套件，恢复 JetsonIO（工厂 6 路 RGB）启动项
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "请用 sudo 运行"; exit 1; }

KVER=$(uname -r)
MODDIR="/lib/modules/$KVER/updates/y306-obc"
FSYNCDIR="/lib/modules/$KVER/updates/y306-fsync"
CAMDIR="/lib/modules/$KVER/updates/drivers/media/platform/tegra/camera"
BAKDIR="/root/y306-sync-backup"

systemctl disable --now y306-orbbec-trigger.service >/dev/null 2>&1 || true
systemctl disable --now y306-obc-camera.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/y306-orbbec-trigger.service \
      /etc/systemd/system/y306-obc-camera.service \
      /etc/systemd/system/fzcam_cfg.service.d/10-y306-obc.conf \
      /usr/local/sbin/y306-obc-load.sh \
      /usr/local/bin/y306_sync_setup.sh \
      /usr/local/bin/y306_orb_trigger \
      /usr/local/bin/y306_frame_ts.py \
      /usr/local/bin/y306_fsync_read.py \
      /usr/local/bin/y306_mcu_freq.py \
      /usr/local/bin/y306_mcu_ver.py \
      /etc/y306-sync.conf /etc/y306-sync-profile \
      /etc/ld.so.conf.d/orbbec-sdk.conf
rmdir /etc/systemd/system/fzcam_cfg.service.d 2>/dev/null || true
systemctl daemon-reload 2>/dev/null || true
ldconfig 2>/dev/null || true

rm -rf "$MODDIR" "$FSYNCDIR"
rm -f /etc/modprobe.d/y306-obc-manual.conf
rm -rf /opt/orbbec-sdk /opt/y306-sync

if [ -f "$CAMDIR/tegra-camera.ko.orig" ]; then
    cp -f "$CAMDIR/tegra-camera.ko.orig" "$CAMDIR/tegra-camera.ko"
else
    rm -f "$CAMDIR/tegra-camera.ko"
fi
depmod -a "$KVER"

rm -f /boot/tegra234-p3767-camera-p3768-y306-mixed-*.dtbo

if ls "$BAKDIR"/extlinux.conf.* >/dev/null 2>&1; then
    cp -f "$(ls -t "$BAKDIR"/extlinux.conf.* | head -1)" /boot/extlinux/extlinux.conf
else
    sed -i 's/^DEFAULT .*/DEFAULT JetsonIO/' /boot/extlinux/extlinux.conf
fi
if ls "$BAKDIR"/fzcam_cfg.ini.* >/dev/null 2>&1; then
    cp -f "$(ls -t "$BAKDIR"/fzcam_cfg.ini.* | head -1)" /etc/fzcam_cfg.ini
fi

sync
echo "已回滚，请重启：sudo reboot"
grep ^DEFAULT /boot/extlinux/extlinux.conf

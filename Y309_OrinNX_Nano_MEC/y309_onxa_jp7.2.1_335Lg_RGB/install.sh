#!/bin/bash
# Y309 mixed installer: 1x335Lg + 4xISX031F (dtbo + camera chain + board modules + fzcam ini + service).
set -e
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
HERE=$(cd "$(dirname "$0")" && pwd)
KREL=$(uname -r)
[ "$KREL" = "6.8.12-1021-tegra" ] || echo "WARN: kernel $KREL != 6.8.12-1021-tegra"
MODDIR=/lib/modules/$KREL
U=$MODDIR/updates
STAMP=$(date +%Y%m%d-%H%M%S)
B=/root/y309-mixed-backup/$STAMP
mkdir -p "$B"

echo "[1/8] backup -> $B"
cp -a /boot/extlinux/extlinux.conf "$B/" 2>/dev/null || true
for f in tegra234-p3767-camera-p3768-y309-mixed.dtbo tegra234-p3767-0000-y309-board.dtbo tegra234-p3767-camera-p3768-y309-8xRGB.dtbo; do cp -a /boot/$f "$B/" 2>/dev/null || true; done
cp -a /etc/fzcam_cfg.ini "$B/" 2>/dev/null || true
tar czf "$B/modules-updates.tgz" -C "$U" . 2>/dev/null || true

echo "[2/8] boot dtbo"
for d in "$HERE"/boot/*.dtbo; do install -D -m 644 "$d" /boot/$(basename "$d"); done

echo "[3/8] camera modules"
install -D -m 644 "$HERE/modules/camera/tegra-camera.ko"      "$U/drivers/media/platform/tegra/camera/tegra-camera.ko"
install -D -m 644 "$HERE/modules/camera/tegra-capture-isp.ko" "$U/drivers/media/platform/tegra/camera/tegra-capture-isp.ko"
install -D -m 644 "$HERE/modules/camera/nvhost-nvcsi.ko"      "$U/drivers/video/tegra/host/nvcsi/nvhost-nvcsi.ko"
install -D -m 644 "$HERE/modules/camera/nvhost-vi5.ko"        "$U/drivers/video/tegra/host/vi/nvhost-vi5.ko"
install -D -m 644 "$HERE/modules/camera/fzcam.ko"             "$U/drivers/media/i2c/fzcam.ko"
install -D -m 644 "$HERE/modules/camera/g300.ko"              "$U/y309-obc/g300.ko"
install -D -m 644 "$HERE/modules/camera/obc_max96712.ko"      "$U/y309-obc/obc_max96712.ko"
install -D -m 644 "$HERE/modules/camera/obc_cam_sync.ko"      "$U/y309-obc/obc_cam_sync.ko"
install -D -m 644 "$HERE/modules/y309_fsync_cap.ko"           "$U/y309_fsync_cap.ko"

echo "[4/8] board modules (5G/CAN/SPI/audio/ethernet)"
if [ -d "$HERE/modules/kernel" ]; then
  (cd "$HERE/modules/kernel" && find . -name '*.ko' -print0 | while IFS= read -r -d '' m; do
      install -D -m 644 "$m" "$MODDIR/kernel/${m#./}"; done)
fi

echo "[5/8] fzcam config + tools"
install -D -m 644 "$HERE/etc/fzcam_cfg.ini" /etc/fzcam_cfg.ini
mkdir -p /etc/systemd/system/fzcam_cfg.service.d
install -D -m 644 "$HERE/etc/systemd/fzcam_cfg.service.d/10-y309-obc.conf" /etc/systemd/system/fzcam_cfg.service.d/10-y309-obc.conf
install -D -m 755 "$HERE/tools/y309_orb_trigger" /home/nvidia/y309_orb_trigger
install -D -m 755 "$HERE/tools/fzcam_cfg" /usr/local/bin/fzcam_cfg

echo "[6/8] modules-load.d + systemd"
install -D -m 644 "$HERE/config/modules-load.d/mcp251xfd.conf" /etc/modules-load.d/mcp251xfd.conf
install -D -m 644 "$HERE/config/modules-load.d/y309-5g.conf"   /etc/modules-load.d/y309-5g.conf
install -D -m 644 "$HERE/systemd/y309-obc-camera.service" /etc/systemd/system/y309-obc-camera.service
systemctl daemon-reload
systemctl enable y309-obc-camera.service >/dev/null 2>&1 || true

echo "[7/8] boot label"
CONF=/boot/extlinux/extlinux.conf
if ! grep -q "^LABEL y309-mixed" "$CONF"; then
  APPEND=$(awk '/^LABEL /{blk=$2} blk=="primary" && /APPEND/{sub(/^[ \t]*APPEND[ \t]*/,""); print; exit}' "$CONF")
  [ -n "$APPEND" ] || APPEND='${cbootargs}'
  cat >> "$CONF" <<EOF

LABEL y309-mixed
      MENU LABEL Y309 mixed 335Lg(bus0) + 4x ISX031F(bus2)
      LINUX /boot/Image
      FDT /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb
      INITRD /boot/initrd
      APPEND $APPEND
      OVERLAYS /boot/tegra234-p3767-camera-p3768-y309-mixed.dtbo,/boot/tegra234-p3767-0000-y309-board.dtbo
EOF
fi
sed -i 's/^DEFAULT .*/DEFAULT y309-mixed/' "$CONF"

echo "[8/8] depmod + sync"
depmod -a "$KREL"
cat > "$B/rollback.sh" <<ROLL
#!/bin/bash
set -e
install -m 644 "$B/extlinux.conf" /boot/extlinux/extlinux.conf
for f in "$B"/*.dtbo; do [ -f "\$f" ] && install -m 644 "\$f" /boot/\$(basename "\$f"); done
[ -f "$B/fzcam_cfg.ini" ] && install -m 644 "$B/fzcam_cfg.ini" /etc/fzcam_cfg.ini
[ -f "$B/modules-updates.tgz" ] && tar xzf "$B/modules-updates.tgz" -C "$U"
systemctl disable y309-obc-camera.service 2>/dev/null || true
depmod -a \$(uname -r); sync
echo "rolled back; reboot to previous profile"
ROLL
chmod +x "$B/rollback.sh"
sync
echo "OK. rollback: $B/rollback.sh"
echo "next: reboot; then per README step 3 (MCU 20Hz + y309_orb_trigger)"

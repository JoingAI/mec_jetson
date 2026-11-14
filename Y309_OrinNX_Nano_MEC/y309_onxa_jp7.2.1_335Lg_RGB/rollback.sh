#!/bin/bash
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
sed -i 's/^DEFAULT .*/DEFAULT JetsonIO/' /boot/extlinux/extlinux.conf
systemctl disable y309-obc-camera.service 2>/dev/null || true
sync
echo "DEFAULT -> JetsonIO; reboot to restore the 8x fzcam profile"

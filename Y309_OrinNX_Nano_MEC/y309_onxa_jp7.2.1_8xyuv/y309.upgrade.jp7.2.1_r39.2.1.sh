#!/bin/bash
<<COMMENT
#
# R39.2.1 Y309 固件升级脚本
# 在 Jetson (Orin NX/Nano, tegra234) 上执行
# 从 cp.y309.sh 生成的固件目录 (Y309_Image/<日期时间>) 拷贝镜像到系统
#
# 用法: 进入固件目录后执行  sudo ./y309.upgrade.R39.2.1.sh
#
COMMENT

red_print() {
    echo -e "\e[1;31m$1\e[0m"
}

green_print() {
    echo -e "\e[1;32m$1\e[0m"
}

green_print "------------ Orin NX/Nano Y309 R39.2.1 Firmware Upgrade 固件升级 --------------"
echo ''

# ---- 版本检查 ----
str=$(cat /etc/nv_tegra_release)
if [[ $str != *"R39"* ]] || [[ $str != *"2.1"* ]]; then
    red_print "JetPack 版本不匹配，需要 R39.2.1, 当前版本:"
    echo "$str"
    exit 1
fi
green_print 'JetPack R39.2.1 版本匹配，继续升级'
echo ''

KERNEL_VER=$(uname -r)
MOD_DIR=/lib/modules/$KERNEL_VER
echo "内核版本: $KERNEL_VER"
echo ''

# ---- 定位固件目录（脚本所在目录，即 y309_fw） ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FW="$SCRIPT_DIR"
if [ ! -f "$FW/boot/Image" ]; then
    red_print "未找到 Image，请确保本脚本位于 y309_fw 目录内再执行"
    exit 1
fi
green_print "固件目录: $FW"
echo ''

# ---- 拷贝 Image ----
if [ ! -f "/boot/Image.orig" ]; then
    echo "备份 Image"
    sudo cp /boot/Image /boot/Image.orig
fi
sudo cp "$FW/boot/Image" /boot/
green_print 'Image 已更新'

# ---- 拷贝 DTB (kernel_ 前缀) ----
if [ ! -d /boot/dtb ]; then
    sudo mkdir -p /boot/dtb
fi
for dtb in "$FW"/boot/dtb/*.dtb; do
    [ -f "$dtb" ] || continue
    name=$(basename "$dtb")
    sudo cp "$dtb" "/boot/dtb/kernel_$name"
done
green_print 'DTB 已更新 (/boot/dtb/kernel_*.dtb)'

# ---- 拷贝 y309 DTBO ----
for dtbo in "$FW"/boot/*.dtbo; do
    [ -f "$dtbo" ] || continue
    sudo cp "$dtbo" /boot/
done
green_print 'y309 DTBO 已更新'

# ---- 拷贝 ko 模块 ----
# in-tree 模块 → kernel/
if [ -d "$FW/kernel" ]; then
    sudo cp -r "$FW/kernel/." "$MOD_DIR/kernel/"
fi
# OOT 模块 → updates/
if [ -d "$FW/updates" ]; then
    sudo cp -r "$FW/updates/." "$MOD_DIR/updates/"
fi
green_print 'ko 模块已更新'

# SPI-CAN 开机自动加载
echo "mcp251xfd" | sudo tee /etc/modules-load.d/mcp251xfd.conf > /dev/null

# ---- 配置 extlinux.conf (参考 R36: 新增 LABEL JetsonIO) ----
TARGET_FILE="/boot/extlinux/extlinux.conf"
FDT_DTB="/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb"
MLABEL="Custom Header Config: <CSI Camera Y309x8RGB>"

if [ ! -f "$TARGET_FILE" ]; then
    red_print "未找到 $TARGET_FILE"
    exit 1
fi

if [ ! -f "$TARGET_FILE.orig" ]; then
    echo "备份 extlinux.conf"
    sudo cp "$TARGET_FILE" "$TARGET_FILE.orig"
fi

# 提取 primary 的 LINUX/INITRD/APPEND
LINUX_LINE=$(grep -E '^[[:space:]]*LINUX[[:space:]]' "$TARGET_FILE" | head -n 1)
INITRD_LINE=$(grep -E '^[[:space:]]*INITRD[[:space:]]' "$TARGET_FILE" | head -n 1)
APPEND_LINE=$(grep -E '^[[:space:]]*APPEND[[:space:]]' "$TARGET_FILE" | head -n 1)

# 删除旧的 JetsonIO 条目、清理旧 FDT/OVERLAYS 行，并把 DEFAULT 改为 JetsonIO
sudo awk '
    /^LABEL JetsonIO$/ { skip = 1; next }
    skip && /^LABEL[[:space:]]/ { skip = 0 }
    skip { next }
    /^[[:space:]]*FDT[[:space:]]/ { next }
    /^[[:space:]]*OVERLAYS[[:space:]]/ { next }
    { sub(/^DEFAULT[[:space:]].*/, "DEFAULT JetsonIO"); print }
' "$TARGET_FILE" > /tmp/extlinux.new && sudo mv /tmp/extlinux.new "$TARGET_FILE"

# 追加 LABEL JetsonIO 条目
{
    echo ""
    echo "LABEL JetsonIO"
    echo "      MENU LABEL $MLABEL"
    printf '%s\n' "$LINUX_LINE"
    echo "      FDT $FDT_DTB"
    printf '%s\n' "$INITRD_LINE"
    printf '%s\n' "$APPEND_LINE"
    echo "      OVERLAYS /boot/tegra234-p3767-camera-p3768-y309-8xRGB.dtbo"
} | sudo tee -a "$TARGET_FILE" > /dev/null

# 参考 R36：把 camera OVERLAYS 追加 board dtbo
OLD_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-y309-8xRGB.dtbo"
NEW_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-y309-8xRGB.dtbo,/boot/tegra234-p3767-0000-y309-board.dtbo"
NEW_REGEX_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-y309-8xRGB.dtbo.*"
sudo sed -i "s#${NEW_REGEX_TEXT}#${NEW_TEXT}#" "$TARGET_FILE"
if grep -q "$NEW_TEXT" "$TARGET_FILE"; then
    grep "$NEW_TEXT" "$TARGET_FILE"
else
    red_print "Failed to modify extlinux.conf"
    exit 1
fi
green_print 'extlinux.conf 已配置 (LABEL JetsonIO + FDT + OVERLAYS)'

# ---- 更新模块依赖 ----
sudo depmod -a
green_print 'depmod 完成'

# ---- FSYNC/HTE 模块开机自加载 ----
if [ -f "$MOD_DIR/updates/y309_fsync_cap.ko" ] ; then
    echo y309_fsync_cap | sudo tee /etc/modules-load.d/y309_fsync.conf > /dev/null
    sudo modprobe y309_fsync_cap 2>/dev/null && green_print 'y309_fsync_cap 加载成功' || red_print 'y309_fsync_cap 加载失败'
    green_print '已配置 /etc/modules-load.d/y309_fsync.conf'
else
    red_print '缺 updates/y309_fsync_cap.ko，跳过 FSYNC 模块'
fi

# ---- 验证 fzcam ko ----
if [ -f "$MOD_DIR/updates/drivers/media/i2c/fzcam.ko" ] ; then
    green_print 'fzcam ko 已部署 (fzcam.ko)'
    sudo modprobe fzcam 2>/dev/null && green_print 'fzcam 加载成功' || red_print 'fzcam 加载失败(可能无相机硬件)'
else
    red_print 'fzcam ko 部署缺失，请检查固件包'
fi

# ---- 相机应用 fzcam_app ----
if [ -d "$FW/fzcam_app" ]; then
    sudo pkill fzcam_ui 2>/dev/null
    sudo cp "$FW/fzcam_app/etc/fzcam_cfg.ini" /etc/
    sudo cp "$FW/fzcam_app/usr/local/bin/fzcam_cfg" /usr/local/bin/
    sudo cp "$FW/fzcam_app/usr/local/bin/fzcam_ui" /usr/local/bin/
    sudo chmod +x /usr/local/bin/fzcam_ui
    sudo chmod +x /usr/local/bin/fzcam_cfg
    sudo cp "$FW/fzcam_app/fzcam_cfg.service" /etc/systemd/system/
    sudo chmod 644 /etc/systemd/system/fzcam_cfg.service
    sudo systemctl enable /etc/systemd/system/fzcam_cfg.service 2>/dev/null
    #No ACC Monitor
    #sudo cp "$FW/fzcam_app/usr/local/bin/acc_check.sh" /usr/local/bin/
    #sudo cp "$FW/fzcam_app/usr/local/bin/acc_monitor.sh" /usr/local/bin/
    #sudo cp "$FW/fzcam_app/acc_monitor.service" /etc/systemd/system/
    #sudo chmod 644 /etc/systemd/system/acc_monitor.service
    #sudo systemctl enable /etc/systemd/system/acc_monitor.service 2>/dev/null
    sudo systemctl daemon-reload
    green_print 'fzcam_app 相机应用已部署'
else
    red_print 'fzcam_app 目录缺失，跳过相机应用部署'
fi

green_print 'Y309 R39.2.1 升级完成，按回车重启 Jetson'
read key

sudo reboot

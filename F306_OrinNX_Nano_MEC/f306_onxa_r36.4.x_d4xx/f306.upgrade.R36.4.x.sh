#!/bin/bash
<<COMMENT
#
# 2024-06-30 Orin NX/Nano and CVB F30X  Orin firmware upgrade shell v1.0 
# 2024-06-30 Orin NX/Nano and CVB F30X  Orin 固件升级脚本V1.0 
#
COMMENT

clear
str_ver0="# R36 (release), REVISION: 4.0"
str_ver3="# R36 (release), REVISION: 4.3"
str_ver4="# R36 (release), REVISION: 4.4"
str_ver7="# R36 (release), REVISION: 4.7"

red_print() {
    echo -e "\e[1;31m$1\e[0m"
}

green_print() {
    echo -e "\e[1;32m$1\e[0m"
}

red_print "------------Orin NX-16/8GB and Nano-8/4GB F30X Firmware Upgrade 固件升级----------------------"
echo ''

str=$(cat /etc/nv_tegra_release)
if [[ $str == *$str_ver0* ]]; then
	echo $str_ver
	green_print 'JetPack is corret, JetPack版本匹配自动升级'
else
	if [[ $str == *$str_ver3* ]]; then
		echo $str_ver
		green_print 'JetPack R36.4.3 is corret, JetPack版本匹配自动升级'
	else
		if [[ $str == *$str_ver4* ]]; then
			echo $str_ver
			green_print 'JetPack R36.4.4 is corret, JetPack版本匹配自动升级'
		else
			if [[ $str == *$str_ver7* ]]; then
				echo $str_ver
				green_print 'JetPack R36.4.7 is corret, JetPack版本匹配自动升级'
			else
				red_print 'JetPack is not corret check and run again, JetPack版本不匹配,检查后再运行'
				exit
			fi
		fi
fi
fi

# ----------------------------------------------------
# 交互式相机配置选择
# ----------------------------------------------------
red_print "请选择相机配置 (Select Camera Configuration):"
echo "  1) 1x D4XX + 2x RGB (MAX96724 LinkA (CAM1))"
echo "  2) 2x D4XX + 2x RGB (MAX96724 LinkA+B (CAM1/CAM2))"
echo "  3) 1x D4XX + 4x RGB (MAX9296 LinkA (CAM4))"
echo "  4) 2x D4XX + 4x RGB (MAX9296 LinkA+B (CAM4/CAM5 not support))"
echo ""
read -p "Enter choice [1-4] (default: 2): " choice
choice="${choice:-2}"

case "$choice" in
    1)
        CAM_DTBO="tegra234-p3767-camera-p3768-f306-1xd4xx-2xrgb.dtbo"
        HW_CONFIG="Camera F306_1xD4XX_2xRGB"
        MENU_LABEL="Custom Header Config: <CSI Camera F306_1xD4XX_2xRGB>"
        ;;
    3)
        CAM_DTBO="tegra234-p3767-camera-p3768-f306-1xd4xx-4xrgb.dtbo"
        HW_CONFIG="Camera F306_1xD4XX_4xRGB"
        MENU_LABEL="Custom Header Config: <CSI Camera F306_1xD4XX_4xRGB>"
        ;;
    4)
        CAM_DTBO="tegra234-p3767-camera-p3768-f306-2xd4xx-4xrgb.dtbo"
        HW_CONFIG="Camera F306_2xD4XX_4xRGB"
        MENU_LABEL="Custom Header Config: <CSI Camera F306_2xD4XX_4xRGB>"
        ;;
    2)
        CAM_DTBO="tegra234-p3767-camera-p3768-f306-2xd4xx-2xrgb.dtbo"
        HW_CONFIG="Camera F306_2xD4XX_2xRGB"
        MENU_LABEL="Custom Header Config: <CSI Camera F306_2xD4XX_2xRGB>"
        ;;
    *)
        red_print "错误: 无效选项 '$choice'，请输入 1-4"
        exit 1
        ;;
esac

green_print "Selected: $HW_CONFIG"
echo "DTBO: $CAM_DTBO"
echo ""

# copy dtb files
if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb.orig" ];then
	echo "bakckup DTB"
	sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0000-nv.dtb ]; then
	sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0000-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv.dtb
	fi
fi
if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0000-nv-super.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0000-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0000-nv-super.dtb
	fi
fi

if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0001-nv.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0001-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv.dtb
	fi
fi
if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv-super.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv-super.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv-super.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0001-nv-super.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0001-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0001-nv-super.dtb
	fi
fi

if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0003-nv.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0003-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv.dtb
	fi
fi
if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv-super.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv-super.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv-super.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0003-nv-super.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0003-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0003-nv-super.dtb
	fi
fi

if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0004-nv.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0004-nv.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv.dtb
	fi
fi

if [ -e /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv-super.dtb ]; then
	if [ ! -f "/boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv-super.dtb.orig" ];then
		echo "bakckup DTB"
		sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv-super.dtb.orig
	fi
	if [ -e $PWD/tegra234-p3768-0000+p3767-0004-nv-super.dtb ]; then
		sudo cp rootfs/boot/tegra234-p3768-0000+p3767-0004-nv-super.dtb /boot/dtb/kernel_tegra234-p3768-0000+p3767-0004-nv-super.dtb
	fi
fi

# Modified /boot/extlinux/extlinux.conf to add following DTBO entries
sudo cp "rootfs/boot/${CAM_DTBO}" /boot/
sudo cp rootfs/boot/tegra234-p3767-0000-f306-board.dtbo /boot/
sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2="${HW_CONFIG}"

###############################################Replace
NEW_TEXT="${MENU_LABEL} <HDR40 Jetson F306 BOARD CONFIG>"
TARGET_FILE="/boot/extlinux/extlinux.conf"
echo ''
if [ -z "$TARGET_FILE" ]; then
	echo "Failed to get extlinux.conf" >&2
	exit 1
fi
if [ ! -f "$TARGET_FILE" ]; then
	echo "Failed to set extlinux.conf" >&2
	exit 1
fi

# Replace entire MENU LABEL line
NEW_REGEX_TEXT="MENU LABEL Custom Header Config:.*"
sed -i "s#${NEW_REGEX_TEXT}#${NEW_TEXT}#" "$TARGET_FILE"
if grep -qF "$NEW_TEXT" "$TARGET_FILE"; then
	grep -F "$NEW_TEXT" "$TARGET_FILE"
else
	echo "Failed to set MENU LABEL" >&2
	exit 1
fi

# Replace OVERLAYS line
OLD_OVERLAYS="OVERLAYS /boot/${CAM_DTBO}"
NEW_OVERLAYS="OVERLAYS /boot/${CAM_DTBO},/boot/tegra234-p3767-0000-f306-board.dtbo"
NEW_OVERLAYS_REGEX="OVERLAYS /boot/${CAM_DTBO}.*"
sed -i "s#${NEW_OVERLAYS_REGEX}#${NEW_OVERLAYS}#" "$TARGET_FILE"
if grep -q "$NEW_OVERLAYS" "$TARGET_FILE"; then
	grep "$NEW_OVERLAYS" "$TARGET_FILE"
else
	echo "Failed to modify extlinux.conf" >&2
	exit 1
fi

#################################### Image and ko ###################################################
## copy Image file ##
if [ ! -f "/boot/Image.orig" ];then
	echo "bakckup Image"
	sudo cp /boot/Image /boot/Image.orig
fi
sudo cp rootfs/boot/Image /boot/ 

## copy tegra-camera.ko file ##
tegra_camera_dir=/lib/modules/$(uname -r)/updates/drivers/media/platform/tegra/camera
if [ ! -f $tegra_camera_dir/tegra-camera.ko.orig ];then
    echo "bakckup tegra-camera.ko"
    sudo cp $tegra_camera_dir/tegra-camera.ko $tegra_camera_dir/tegra-camera.ko.orig
fi
sudo cp rootfs/$tegra_camera_dir/tegra-camera.ko $tegra_camera_dir

# Video ko
## copy videodev.ko file enable metadata ##
videodev_dir=/lib/modules/$(uname -r)/kernel/drivers/media/v4l2-core
if [ ! -f $videodev_dir/videodev.ko.orig ];then
	echo "bakckup videodev.ko"
	sudo cp $videodev_dir/videodev.ko $videodev_dir/videodev.ko.orig
fi
sudo cp rootfs/$videodev_dir/videodev.ko $videodev_dir

## copy capture-ivc.ko file ##
capture_ivc_dir=/lib/modules/$(uname -r)/updates/drivers/platform/tegra/rtcpu
if [ ! -f $capture_ivc_dir/capture-ivc.ko.orig ];then
    echo "bakckup capture-ivc.ko"
    sudo cp $capture_ivc_dir/capture-ivc.ko $capture_ivc_dir/capture-ivc.ko.orig
fi
sudo cp rootfs/$capture_ivc_dir/capture-ivc.ko $capture_ivc_dir

## copy nvhost-nvcsi-t194.ko file ##
nvhost_nvcsi_t194_dir=/lib/modules/$(uname -r)/updates/drivers/video/tegra/host/nvcsi/
if [ ! -f $nvhost_nvcsi_t194_dir/nvhost-nvcsi-t194.ko.orig ];then
    echo "bakckup nvhost-nvcsi-t194.ko"
    sudo cp $nvhost_nvcsi_t194_dir/nvhost-nvcsi-t194.ko $nvhost_nvcsi_t194_dir/nvhost-nvcsi-t194.ko.orig
fi
sudo cp rootfs/$nvhost_nvcsi_t194_dir/nvhost-nvcsi-t194.ko $nvhost_nvcsi_t194_dir

#Video 335Lg+FZCAM/fzcam.ko
videodev_dir=/lib/modules/$(uname -r)/updates/drivers/media/i2c
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcama.ko ];then
	sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcama.ko
fi
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcamb.ko ];then
	sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcamb.ko
fi

###################################################################
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/d4xx.ko ];then
    sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/d4xx.ko
fi
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcam.ko ];then
    sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcam.ko
fi

## copy max9296.ko file ##
## copy max9295.ko file ##
sudo cp rootfs/$videodev_dir/max9295.ko $videodev_dir
sudo cp rootfs/$videodev_dir/max9296.ko $videodev_dir
sudo cp rootfs/$videodev_dir/max96712.ko $videodev_dir
sudo cp rootfs/$videodev_dir/max96717.ko $videodev_dir
sudo cp rootfs/$videodev_dir/d4xx.ko 	$videodev_dir
sudo cp rootfs/$videodev_dir/fzcam.ko 	$videodev_dir
#sudo cp serdes.ko 	$videodev_dir

# Add softdep to ensure fzcam loads before g300
echo "softdep fzcam pre: d4xx" | sudo tee /etc/modprobe.d/d4xx.conf

# Sound
videodev_dir=/lib/modules/$(uname -r)/kernel/sound/soc/codecs
if [ -e $videodev_dir/snd-soc-nau8822.ko ];then
	sudo rm $videodev_dir/snd-soc-nau8822.ko
fi
sudo cp rootfs/$videodev_dir/snd-soc-nau8822.ko $videodev_dir

# RTL Ethernet
## copy r8168.ko file ##
r8168_dir=/lib/modules/$(uname -r)/updates/drivers/net/ethernet/realtek/r8168
if [ ! -f $r8168_dir/r8168.ko.orig ];then
	echo "bakckup r8168.ko"
	sudo cp $r8168_dir/r8168.ko $r8168_dir/r8168.ko.orig
fi
sudo cp rootfs/$r8168_dir/r8168.ko $r8168_dir

# SPI-CAN
## copy spidev.ko file ##
spidev_dir=/lib/modules/$(uname -r)/kernel/drivers/spi
if [ ! -f $spidev_dir/spidev.ko.orig ];then
	echo "bakckup spidev.ko"
	sudo cp $spidev_dir/spidev.ko $spidev_dir/spidev.ko.orig
fi
sudo cp rootfs/$spidev_dir/spidev.ko $spidev_dir

spidev_dir=/lib/modules/$(uname -r)/kernel/drivers/spi/
if [ ! -f $spidev_dir/spi-tegra114.ko.orig ];then
	echo "bakckup spi-tegra114.ko"
	sudo cp $spidev_dir/spi-tegra114.ko $spidev_dir/spi-tegra114.ko.orig
fi
sudo cp rootfs/$spidev_dir/spi-tegra114.ko $spidev_dir

spican_dir=/lib/modules/$(uname -r)/updates/drivers/net/can/spi/
if [ ! -f $spican_dir ];then
	sudo mkdir -p $spican_dir
fi
sudo cp rootfs/$spican_dir/mcp251xfd.ko $spican_dir
echo "mcp251xfd" | sudo tee /etc/modules-load.d/mcp251xfd.conf

# Mobilenet 4G/5G ko
## copy usb_wwan.ko file ##
green_print "4G/5G modules devices"
mobiledev_dir=/lib/modules/$(uname -r)/kernel/drivers/usb/serial
if [ ! -f $mobiledev_dir/usb_wwan.ko.orig ];then
	echo "bakckup usb_wwan.ko"
	sudo cp $mobiledev_dir/usb_wwan.ko $mobiledev_dir/usb_wwan.ko.orig
fi
sudo cp rootfs/$mobiledev_dir/usb_wwan.ko $mobiledev_dir
## copy option.ko file ##
mobiledev_dir=/lib/modules/$(uname -r)/kernel/drivers/usb/serial
if [ ! -f $mobiledev_dir/option.ko.orig ];then
	echo "bakckup option.ko"
	sudo cp $mobiledev_dir/option.ko $mobiledev_dir/option.ko.orig
fi
sudo cp rootfs/$mobiledev_dir/option.ko   $mobiledev_dir

## copy usbnet.ko file ##
mobiledev_dir=/lib/modules/$(uname -r)/kernel/drivers/net/usb
if [ ! -f $mobiledev_dir/usbnet.ko.orig ];then
	echo "bakckup usbnet.ko"
	sudo cp $mobiledev_dir/usbnet.ko $mobiledev_dir/usbnet.ko.orig
fi
sudo cp rootfs/$mobiledev_dir/usbnet.ko      $mobiledev_dir
## copy cdc-wdm.ko file ##
mobiledev_dir=/lib/modules/$(uname -r)/kernel/drivers/net/usb/
if [ ! -f $mobiledev_dir/cdc-wdm.ko.orig ];then
	echo "bakckup cdc-wdm.ko"
	sudo cp $mobiledev_dir/cdc-wdm.ko $mobiledev_dir/cdc-wdm.ko.orig
fi
sudo cp rootfs/$mobiledev_dir/cdc-wdm.ko     $mobiledev_dir
## copy qmi_wwan_q.ko file ##
mobiledev_dir=/lib/modules/$(uname -r)/kernel/drivers/net/usb
if [ ! -f $mobiledev_dir/qmi_wwan_q.ko.orig ];then
	echo "bakckup qmi_wwan_q.ko"
	sudo cp $mobiledev_dir/qmi_wwan_q.ko $mobiledev_dir/qmi_wwan_q.ko.orig
fi
sudo cp rootfs/$mobiledev_dir/qmi_wwan_q.ko  $mobiledev_dir

# WIFI modules
## copy rtl8852be.ko file ##
green_print "BL WIFI Modules"
wifi_dir=/lib/modules/$(uname -r)/updates/drivers/net/wireless/realtek/rtl8852be
if [ ! -f $wifi_dir/rtl8852be.ko.orig ];then
	echo "bakckup rtl8852be.ko"
	sudo mkdir -p /lib/modules/$(uname -r)/updates/drivers/net/wireless/realtek/rtl8852be/
	sudo cp $wifi_dir/rtl8852be.ko $wifi_dir/rtl8852be.ko.orig
fi
sudo cp rootfs/$wifi_dir/rtl8852be.ko $wifi_dir
sudo modprobe cfg80211
sudo modprobe rtl8852be

sudo depmod -a

# Enable camera service
## copy camera service and enable service ##
echo 'Copy and config camera service'
sudo pkill fzcam_ui
sudo cp fzcam_app/etc/fzcam_cfg.ini /etc/
sudo cp fzcam_app/usr/local/bin/fzcam_cfg /usr/local/bin/
sudo cp fzcam_app/usr/local/bin/fzcam_ui /usr/local/bin/
sudo chmod +x /usr/local/bin/fzcam_ui
sudo chmod +x /usr/local/bin/fzcam_cfg

sudo cp fzcam_app/fzcam_cfg.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/fzcam_cfg.service 
sudo systemctl enable  /etc/systemd/system/fzcam_cfg.service 

# ACC Monitor
## acc monitor and check
sudo cp fzcam_app/usr/local/bin/acc_check.sh /usr/local/bin/
sudo cp fzcam_app/usr/local/bin/acc_monitor.sh /usr/local/bin/
sudo cp fzcam_app/acc_monitor.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/acc_monitor.service
sudo systemctl enable  /etc/systemd/system/acc_monitor.service
sudo systemctl daemon-reload

##############################################################################################
green_print 'Upgrade success, Press Enter to reboot Jetson or Ctrl+C cancel and reboot later'
read key

sudo reboot

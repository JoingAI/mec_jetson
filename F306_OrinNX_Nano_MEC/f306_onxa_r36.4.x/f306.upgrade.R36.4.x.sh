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

# copy dtb
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
sudo cp rootfs/boot/tegra234-p3767-camera-p3768-f306.dtbo /boot/
sudo cp rootfs/boot/tegra234-p3767-0000-f306-board.dtbo /boot/
sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2="Camera F306x6RGB"

###############################################Replace
OLD_TEXT="MENU LABEL Custom Header Config: <CSI Camera F306x6RGB>"
NEW_TEXT="MENU LABEL Custom Header Config: <CSI Camera F306x6RGB> <HDR40 Jetson F306 BOARD CONFIG>"
TARGET_FILE="/boot/extlinux/extlinux.conf"
#cat $TARGET_FILE
echo ''
if [ -z "$TARGET_FILE" ]; then
	echo "Failed to get extlinux.conf" >&2
	exit 1
fi
if [ ! -f "$TARGET_FILE" ]; then
	echo "Failed to set extlinux.conf" >&2
	exit 1
fi

sed -i.bak "s#^${OLD_TEXT}\$#${NEW_TEXT}#" "$TARGET_FILE"
NEW_REGEX_TEXT="MENU LABEL Custom Header Config:.*"
sed -i "s#${NEW_REGEX_TEXT}#${NEW_TEXT}#" "$TARGET_FILE"
if grep -qF "$NEW_TEXT" "$TARGET_FILE"; then
	grep -F "$NEW_TEXT" "$TARGET_FILE"
else
	echo "Failed to set MENU LABEL" >&2
	exit 1
fi
OLD_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-f306.dtbo"
NEW_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-f306.dtbo,/boot/tegra234-p3767-0000-f306-board.dtbo"
NEW_REGEX_TEXT="OVERLAYS /boot/tegra234-p3767-camera-p3768-f306.dtbo.*"
sed -i "s#${NEW_REGEX_TEXT}#${NEW_TEXT}#" "$TARGET_FILE"
if grep -q "$NEW_TEXT" "$TARGET_FILE"; then
	grep "$NEW_TEXT" "$TARGET_FILE"
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

# Sound
## copy fzcam.ko file ##
videodev_dir=/lib/modules/$(uname -r)/kernel/sound/soc/codecs
if [ -e $videodev_dir/snd-soc-nau8822.ko ];then
	sudo rm $videodev_dir/snd-soc-nau8822.ko
fi
sudo cp rootfs/$videodev_dir/snd-soc-nau8822.ko $videodev_dir

# Video ko
## copy videodev.ko file ##
videodev_dir=/lib/modules/$(uname -r)/kernel/drivers/media/v4l2-core
if [ ! -f $videodev_dir/videodev.ko.orig ];then
	echo "bakckup videodev.ko"
	sudo cp $videodev_dir/videodev.ko $videodev_dir/videodev.ko.orig
fi
sudo cp rootfs/$videodev_dir/videodev.ko $videodev_dir

## copy fzcam.ko file ##
videodev_dir=/lib/modules/$(uname -r)/updates/drivers/media/i2c
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcama.ko ];then
	sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcama.ko
fi
if [ -e /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcamb.ko ];then
	sudo rm /lib/modules/$(uname -r)/updates/drivers/media/i2c/fzcamb.ko
fi
sudo cp rootfs/$videodev_dir/fzcama.ko $videodev_dir
sudo cp rootfs/$videodev_dir/fzcamb.ko $videodev_dir

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
sudo cp rootfs/lib/modules/$(uname -r)/kernel/drivers/spi/spidev.ko  $spidev_dir
spidev_dir=/lib/modules/$(uname -r)/kernel/drivers/spi/
if [ ! -f $spidev_dir/spi-tegra114.ko.orig ];then
	echo "bakckup spi-tegra114.ko"
	sudo cp $spidev_dir/spi-tegra114.ko $spidev_dir/spi-tegra114.ko.orig
fi
sudo cp rootfs/lib/modules/$(uname -r)/kernel/drivers/spi/spi-tegra114.ko $spidev_dir

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
green_print 'Upgrade F30x firmware success, Press Enter to reboot Jetson'
read key

sudo reboot

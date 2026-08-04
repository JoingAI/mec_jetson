# F306 Orin NX/Nano D4XX Firmware Package

> NVIDIA JetPack 6.2 (R36.4.x) BSP firmware for F306 carrier board with Intel RealSense D4XX cameras

---

## English

### Overview

This firmware package supports the F306 carrier board (Orin NX 16/8GB, Nano 8/4GB) with Intel RealSense D4XX depth cameras and RGB cameras. It includes kernel modules, device tree overlays, kernel image, camera applications, and a one-click upgrade script.

### Supported JetPack Versions

- R36.4.0 / R36.4.3 / R36.4.4 / R36.4.7

### Camera Configurations

| Option | Configuration | Deserializer | Link | Status |
|--------|--------------|--------------|------|--------|
| 1 | 1x D4XX + 2x RGB | MAX96724 | LinkA (CAM1) | Supported |
| 2 | 2x D4XX + 2x RGB | MAX96724 | LinkA+B (CAM1/CAM2) | Supported |
| 3 | 1x D4XX + 4x RGB | MAX9296 | LinkA (CAM4) | Supported |
| 4 | 2x D4XX + 4x RGB | MAX9296 | LinkA+B (CAM4/CAM5) | Not supported |

### Directory Structure

```
f306_onxa_r36.4.x_d4xx/
├── f306.upgrade.R36.4.x.sh          # Firmware upgrade script (one-click)
├── README.md                         # This file
├── rootfs/
│   └── boot/
│       ├── Image                     # Kernel image (5.15.148-tegra)
│       ├── dtb/                      # Base board DTB files (10 files)
│       │   ├── tegra234-p3768-0000+p3767-0000-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0000-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0001-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0001-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0003-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0003-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0004-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0004-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0005-nv.dtb
│       │   └── tegra234-p3768-0000+p3767-0005-nv-super.dtb
│       ├── tegra234-p3767-0000-f306-board.dtbo   # F306 board config overlay
│       ├── tegra234-p3767-camera-p3768-f306-1xd4xx-2xrgb.dtbo
│       ├── tegra234-p3767-camera-p3768-f306-2xd4xx-2xrgb.dtbo
│       └── tegra234-p3767-camera-p3768-f306-1xd4xx-4xrgb.dtbo
│   └── lib/modules/5.15.148-tegra/
│       ├── updates/drivers/media/i2c/
│       │   ├── d4xx.ko               # Intel RealSense D4XX camera driver
│       │   ├── fzcam.ko              # FZ camera driver
│       │   ├── max9295.ko            # GMSL serializer (MAX9295)
│       │   ├── max9296.ko            # GMSL deserializer (MAX9296)
│       │   ├── max96712.ko           # GMSL deserializer (MAX96724)
│       │   └── max96717.ko           # GMSL serializer (MAX96717)
│       ├── updates/drivers/media/platform/tegra/camera/
│       │   └── tegra-camera.ko       # Tegra camera framework
│       ├── updates/drivers/platform/tegra/rtcpu/
│       │   └── capture-ivc.ko        # Capture IVC driver
│       ├── updates/drivers/video/tegra/host/nvcsi/
│       │   └── nvhost-nvcsi-t194.ko  # NVCSI host driver
│       ├── updates/drivers/misc/
│       │   └── obc_cam_sync.ko       # Camera sync module
│       ├── updates/drivers/net/
│       │   ├── ethernet/realtek/r8168/r8168.ko      # Realtek Ethernet (2.5G)
│       │   ├── can/spi/mcp251xfd.ko                  # SPI CAN controller
│       │   └── wireless/realtek/rtl8852be/rtl8852be.ko  # Realtek WiFi
│       ├── kernel/drivers/media/v4l2-core/
│       │   └── videodev.ko           # V4L2 video device (metadata enabled)
│       ├── kernel/drivers/spi/
│       │   ├── spidev.ko             # SPI device driver
│       │   └── spi-tegra114.ko       # Tegra SPI controller
│       ├── kernel/drivers/usb/serial/
│       │   ├── option.ko             # USB serial (4G/5G modem)
│       │   └── usb_wwan.ko           # USB WWAN driver
│       ├── kernel/drivers/net/usb/
│       │   ├── usbnet.ko             # USB networking
│       │   ├── cdc-wdm.ko            # CDC WDM driver
│       │   └── qmi_wwan_q.ko         # QMI WWAN driver
│       └── kernel/sound/soc/codecs/
│           └── snd-soc-nau8822.ko    # Audio codec (NAU8822)
└── fzcam_app/                         # Camera applications and services
    ├── etc/fzcam_cfg.ini              # Camera link configuration
    ├── usr/local/bin/fzcam_cfg        # Camera & Serdes configuration tool
    ├── usr/local/bin/fzcam_ui         # Qt GUI application
    ├── usr/local/bin/acc_check.sh     # ACC check script
    ├── usr/local/bin/acc_monitor.sh   # ACC monitor script
    ├── fzcam_cfg.service              # Systemd service for fzcam_cfg
    ├── acc_monitor.service            # Systemd service for ACC monitor
    ├── trigger.f306.pwm.sh            # F306 PWM trigger script
    └── ob_multi_devices_sync_gmsltrigger  # Multi-device GMSL sync trigger
```

### Installation & Upgrade

1. Copy the firmware package to the target Jetson device (Orin NX or Nano).

2. Extract and run the upgrade script:

```bash
unzip f306_onxa_r36.4.x_d4xx*.zip
cd f306_onxa_r36.4.x_d4xx
sudo bash f306.upgrade.R36.4.x.sh
```

3. The script will verify JetPack version compatibility first, then prompt for camera configuration:

```
请选择相机配置 (Select Camera Configuration):
  1) 1x D4XX + 2x RGB (MAX96724 LinkA (CAM1))
  2) 2x D4XX + 2x RGB (MAX96724 LinkA+B (CAM1/CAM2))
  3) 1x D4XX + 4x RGB (MAX9296 LinkA (CAM4))
  4) 2x D4XX + 4x RGB (MAX9296 LinkA+B (CAM4/CAM5 not support))

Enter choice [1-4] (default: 2):
```

4. Select your camera configuration and press Enter. For invalid input, the script will show an error and exit.

5. The script will automatically perform all upgrade steps. Press Enter to reboot when prompted.

### What the Script Does

1. **Version Check** — Verifies JetPack R36.4.0/3/4/7 compatibility
2. **DTB Backup & Update** — Backs up and updates 10 base board DTB files
3. **DTBO Copy** — Copies selected camera DTBO + F306 board overlay to `/boot/`
4. **extlinux.conf** — Updates `MENU LABEL` and `OVERLAYS` entries
5. **Jetson-IO** — Runs `config-by-hardware.py` with the selected hardware config
6. **Kernel Image** — Backs up and replaces `/boot/Image`
7. **Kernel Modules** — Copies all `.ko` drivers (camera, network, sound, SPI, USB)
8. **Soft Dependency** — Creates `d4xx.conf` to ensure `fzcam` loads before `d4xx`
9. **Systemd Services** — Installs and enables `fzcam_cfg` and `acc_monitor` services
10. **Module Probe** — Runs `modprobe cfg80211` and `modprobe rtl8852be`
11. **depmod** — Runs `depmod -a` to rebuild module dependencies
12. **Reboot** — Prompts and reboots the Jetson device

---

## 中文

### 概述

本固件包支持 F306 载板（Orin NX 16/8GB、Nano 8/4GB），搭配 Intel RealSense D4XX 深度相机和 RGB 相机。包含内核模块、设备树覆盖层、内核镜像、相机应用程序以及一键升级脚本。

### 支持的 JetPack 版本

- R36.4.0 / R36.4.3 / R36.4.4 / R36.4.7

### 相机配置

| 选项 | 配置 | 解串器 | 链路 | 状态 |
|------|------|--------|------|------|
| 1 | 1路 D4XX + 2路 RGB | MAX96724 | LinkA (CAM1) | 支持 |
| 2 | 2路 D4XX + 2路 RGB | MAX96724 | LinkA+B (CAM1/CAM2) | 支持 |
| 3 | 1路 D4XX + 4路 RGB | MAX9296 | LinkA (CAM4) | 支持 |
| 4 | 2路 D4XX + 4路 RGB | MAX9296 | LinkA+B (CAM4/CAM5) | 不支持 |

### 目录结构

```
f306_onxa_r36.4.x_d4xx/
├── f306.upgrade.R36.4.x.sh          # 固件升级脚本（一键）
├── README.md                         # 本文件
├── rootfs/
│   └── boot/
│       ├── Image                     # 内核镜像 (5.15.148-tegra)
│       ├── dtb/                      # 基础板级 DTB 文件（10个）
│       │   ├── tegra234-p3768-0000+p3767-0000-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0000-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0001-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0001-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0003-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0003-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0004-nv.dtb
│       │   ├── tegra234-p3768-0000+p3767-0004-nv-super.dtb
│       │   ├── tegra234-p3768-0000+p3767-0005-nv.dtb
│       │   └── tegra234-p3768-0000+p3767-0005-nv-super.dtb
│       ├── tegra234-p3767-0000-f306-board.dtbo   # F306 板级配置覆盖层
│       ├── tegra234-p3767-camera-p3768-f306-1xd4xx-2xrgb.dtbo
│       ├── tegra234-p3767-camera-p3768-f306-2xd4xx-2xrgb.dtbo
│       └── tegra234-p3767-camera-p3768-f306-1xd4xx-4xrgb.dtbo
│   └── lib/modules/5.15.148-tegra/
│       ├── updates/drivers/media/i2c/
│       │   ├── d4xx.ko               # Intel RealSense D4XX 相机驱动
│       │   ├── fzcam.ko              # FZ 相机驱动
│       │   ├── max9295.ko            # GMSL 串行器 (MAX9295)
│       │   ├── max9296.ko            # GMSL 解串器 (MAX9296)
│       │   ├── max96712.ko           # GMSL 解串器 (MAX96724)
│       │   └── max96717.ko           # GMSL 串行器 (MAX96717)
│       ├── updates/drivers/media/platform/tegra/camera/
│       │   └── tegra-camera.ko       # Tegra 相机框架
│       ├── updates/drivers/platform/tegra/rtcpu/
│       │   └── capture-ivc.ko        # 捕获 IVC 驱动
│       ├── updates/drivers/video/tegra/host/nvcsi/
│       │   └── nvhost-nvcsi-t194.ko  # NVCSI 主机驱动
│       ├── updates/drivers/misc/
│       │   └── obc_cam_sync.ko       # 相机同步模块
│       ├── updates/drivers/net/
│       │   ├── ethernet/realtek/r8168/r8168.ko      # Realtek 以太网 (2.5G)
│       │   ├── can/spi/mcp251xfd.ko                  # SPI CAN 控制器
│       │   └── wireless/realtek/rtl8852be/rtl8852be.ko  # Realtek WiFi
│       ├── kernel/drivers/media/v4l2-core/
│       │   └── videodev.ko           # V4L2 视频设备（启用 metadata）
│       ├── kernel/drivers/spi/
│       │   ├── spidev.ko             # SPI 设备驱动
│       │   └── spi-tegra114.ko       # Tegra SPI 控制器
│       ├── kernel/drivers/usb/serial/
│       │   ├── option.ko             # USB 串口（4G/5G 模组）
│       │   └── usb_wwan.ko           # USB WWAN 驱动
│       ├── kernel/drivers/net/usb/
│       │   ├── usbnet.ko             # USB 网络
│       │   ├── cdc-wdm.ko            # CDC WDM 驱动
│       │   └── qmi_wwan_q.ko         # QMI WWAN 驱动
│       └── kernel/sound/soc/codecs/
│           └── snd-soc-nau8822.ko    # 音频编解码器 (NAU8822)
└── fzcam_app/                         # 相机应用程序与服务
    ├── etc/fzcam_cfg.ini              # 相机链路配置文件
    ├── usr/local/bin/fzcam_cfg        # 相机与 Serdes 配置工具
    ├── usr/local/bin/fzcam_ui         # Qt 界面程序
    ├── usr/local/bin/acc_check.sh     # ACC 检查脚本
    ├── usr/local/bin/acc_monitor.sh   # ACC 监控脚本
    ├── fzcam_cfg.service              # fzcam_cfg 系统服务
    ├── acc_monitor.service            # ACC 监控系统服务
    ├── trigger.f306.pwm.sh            # F306 PWM 触发脚本
    └── ob_multi_devices_sync_gmsltrigger  # 多设备 GMSL 同步触发
```

### 安装与升级

1. 将固件包拷贝到目标 Jetson 设备（Orin NX 或 Nano）上。

2. 解压并运行升级脚本：

```bash
unzip f306_onxa_r36.4.x_d4xx*.zip
cd f306_onxa_r36.4.x_d4xx
sudo bash f306.upgrade.R36.4.x.sh
```

3. 脚本会先校验 JetPack 版本兼容性，然后提示选择相机配置：

```
请选择相机配置 (Select Camera Configuration):
  1) 1x D4XX + 2x RGB (MAX96724 LinkA (CAM1))
  2) 2x D4XX + 2x RGB (MAX96724 LinkA+B (CAM1/CAM2))
  3) 1x D4XX + 4x RGB (MAX9296 LinkA (CAM4))
  4) 2x D4XX + 4x RGB (MAX9296 LinkA+B (CAM4/CAM5 not support))

Enter choice [1-4] (default: 2):
```

4. 选择相机配置后按回车。输入无效选项会报错并退出。

5. 脚本会自动执行所有升级步骤。按回车键重启设备。

### 脚本执行流程

1. **版本校验** — 校验 JetPack R36.4.0/3/4/7 兼容性
2. **DTB 备份与更新** — 备份并更新 10 个基础板级 DTB 文件
3. **DTBO 拷贝** — 将选定的相机 DTBO 和 F306 板级覆盖层拷贝到 `/boot/`
4. **extlinux.conf** — 更新 `MENU LABEL` 和 `OVERLAYS` 条目
5. **Jetson-IO** — 使用选定的硬件配置运行 `config-by-hardware.py`
6. **内核镜像** — 备份并替换 `/boot/Image`
7. **内核模块** — 拷贝所有 `.ko` 驱动（相机、网络、音频、SPI、USB）
8. **软依赖** — 创建 `d4xx.conf` 确保 `fzcam` 在 `d4xx` 之前加载
9. **Systemd 服务** — 安装并启用 `fzcam_cfg` 和 `acc_monitor` 服务
10. **模块探测** — 执行 `modprobe cfg80211` 和 `modprobe rtl8852be`
11. **depmod** — 执行 `depmod -a` 重建模块依赖
12. **重启** — 提示并重启 Jetson 设备

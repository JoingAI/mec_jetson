# Y309 混合相机部署包 v2.0.0（1×Gemini 335Lg + 4×JoingAI ISX031F）

适用：Y309 载板 + Orin NX 16GB，JetPack 7.2.1 / L4T R39.2.1（kernel 6.8.12-1021-tegra）。

## 拓扑（v2：335Lg 在 U7，ISX031F 在 U6）

| 节点 | 设备 | 位置 | 格式 |
|---|---|---|---|
| video0–3 | 4× ISX031F | U6 / i2c@3160000，CSI A，serial_a | UYVY 1920×1536 |
| video4 | 335Lg ir_r | U7 / i2c@3180000，CSI C，serial_c | GREY 848×480 |
| video5 | 335Lg ir_l | U7 | GREY 848×480 |
| video6 | 335Lg color | U7 | YUYV 1280×720 |
| video7 | 335Lg depth | U7 | Z16 1280×800 |

- 335Lg 走内核驱动（`obc_max96712` + `g300`），DT 节点 `g2m1@1b..1e`；
- 4× ISX031F 走用户态 `fzcam_cfg` + `fzcam.ko`，DT 节点 `fzcam_3a..3d@3a..3d`；
- 触发统一 **20 Hz / 10% duty**（MCU 一条 FSYNC 线同时给两颗 96724），335Lg 需 SDK 下发硬件触发（`syncMode=0x40`）。

## 1. 前置

- 已烧 JetPack 7.2.1 R39.2.1；MCU 已烧（`y309ctl.py ver` 有版本号）；
- 335Lg 接 **U7 的 J3**，4× ISX031F 接 **U6 的 J1/J2/J19/J20**；
- OrbbecSDK：`libOrbbecSDK.so` 在 OrbbecViewer 目录（`tools/y309_orb_trigger`、`tools/y309_335lg_cap` 依赖它）。

## 2. 安装

```bash
tar xzf y309-mixed-2.0.0.tar.gz && cd y309-mixed-2.0.0
sudo ./install.sh
sudo reboot
```

`install.sh`：备份 → v2 dtbo + board dtbo → 相机整链 + 板级 ko（5G/CAN/SPI/音频/网口）→
`/etc/fzcam_cfg.ini`（GMSL1=U6 `Video_1111`、GMSL2=U7 `Video_0000`）+ `fzcam_cfg.service.d`（After 335Lg）→
`fzcam_cfg`（修复版，position=None 不写 PoC/MFP）→ modules-load.d → systemd 服务 →
`LABEL y309-mixed` 并设 `DEFAULT` → depmod + sync。**不刷机。**

## 3. 开机后（每次上电/重启都要做，掉电会丢）

```bash
# 3.1 MCU 触发 20 Hz / 10% duty（自由运行）
cd <mcu_y309目录>                 # 例：/home/nvidia/y309_onxa_jp7.2.1_8xyuv/mcu_y309
sudo python3 y309ctl.py mode free
sudo python3 y309ctl.py set 20 10
sudo python3 y309ctl.py status    # 期望 en=1 m=free f=20 d=10

# 3.2 I210 1PPS（MCU 有合法 1PPS 才稳定输出 PWM）
sudo ./tools/ptp_perout2 /dev/ptp0 0 1000000000   # 若无此工具，见 README-EN 说明

# 3.3 335Lg 硬件触发（断电即丢，必须每次下发）
export LD_LIBRARY_PATH=<OrbbecViewer目录>:$LD_LIBRARY_PATH
sudo env LD_LIBRARY_PATH=$LD_LIBRARY_PATH /home/nvidia/y309_orb_trigger
# 期望打印 syncMode=0x40 framesPerTrigger=1

# 3.4 8 路并发前先提频（vi/isp/nvcsi 满频；EMC 随负载自动升到 3199M）
sudo ./serdes.script/boost.clk.sh
```

## 4. 验收（两种方式）

**方式 1（viewer 335Lg + v4l2-ctl ISX031F）**：viewer 打开 335Lg 4 路，同时
`v4l2-ctl -d /dev/video0..3 --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap`。

**方式 2（SDK 335Lg + v4l2-ctl ISX031F）**：
```bash
sudo env LD_LIBRARY_PATH=<viewer目录> ./tools/y309_335lg_cap 1800   # 335Lg 30min，打印四路 fps/帧数
for n in 0 1 2 3; do v4l2-ctl -d /dev/video$n --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap --stream-to=/dev/null; done
dmesg | grep -c corr_err; dmesg | grep -c uncorr_err; dmesg | grep -c 'request timed out'
```

实测（v2.0.0）：冷启动 ×3 通过；option1 30min `corr=0`；option2 30min `corr=2`（335Lg 19.98–19.99 fps×36000+，ISX031F 20.01 fps）；温度 49–52°C。

> **重要**：335Lg 不要用 v4l2-ctl 直接取流做长时间测试——会出 `err_data 256/512`（PIXEL_LONG/SHORT_LINE）甚至 0 帧；长测必须走 viewer 或 `y309_335lg_cap`（SDK）。

## 5. 回滚

```bash
sudo bash install.sh 时生成的 /root/y309-mixed-backup/<stamp>/rollback.sh
# 或 sudo ./rollback.sh（DEFAULT→JetsonIO）后 reboot
```

## 6. 已知限制

- 每次上电后需重新执行第 3 步（MCU/1PPS/335Lg 硬件触发），掉电会丢；
- 335Lg 的 4 路只能按 VC 分别开（depth/color/ir_l/ir_r），SDK `Pipeline+Config+enableStream` 一次开全；
- 脚本放 `/home/nvidia/` 持久化，不要放 `/tmp`（重启清空）；
- 335Lg color 偶发 `err_data 131072`（PD_CRC），30 min 约 2 条，量级可忽略。

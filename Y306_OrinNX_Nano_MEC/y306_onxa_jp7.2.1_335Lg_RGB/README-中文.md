# Y306 同步相机套件（335Lg + RGB/YUV · 硬件触发 + 每帧时间戳）

> 适用：**全新 Y306 整机**（Orin NX 16GB / L4T R39.2.1，内核 `6.8.12-1021-tegra`）
> 安装后即可使用：三种相机组合（profile a/b/c）+ 硬件触发同步 + 每帧绝对时间戳

---

## 1. 三种配置

| profile | MAX9296（LinkA） | MAX96724（LinkA） | video 节点 |
|---|---|---|---|
| **a** | 2× RGB/YUV（ISX031F，fzcam） | 1× Gemini 335Lg（4 流） | 6 |
| **b** | 1× Gemini 335Lg（4 流） | 4× RGB/YUV（ISX031F，fzcam） | 8 |
| **c** | 1× Gemini 335Lg | 1× Gemini 335Lg | 8 |

一次只能装一个 profile；换接线就重装对应 profile 并重启。

## 2. 包里有什么

```
y306-sync-cam/
├── install.sh / uninstall.sh / verify.sh
├── extlinux-add.py                 # 从板上已有的 JetsonIO 启动项派生新项
├── artifacts/
│   ├── dtbo/   三套 camera overlay（mixed-a/b/c）
│   ├── modules/ g300, obc_max9296, obc_max96712, obcam, fzcam,
│   │            tegra-camera.ko, y306_fsync_cap.ko
│   └── sdk/     libOrbbecSDK.so.2.7.6 + y306_orb_trigger（设置硬件触发）
├── conf/        三套 fzcam_cfg-*.ini
├── systemd/     服务单元 + 加载脚本
└── tools/       y306_frame_ts.py / fsync_read.py / mcu_freq.py / pair_frames.py
```

## 3. 安装

```bash
tar xzf y306-sync-cam-v3.0.tar.gz
cd y306-sync-cam

sudo bash install.sh --profile a          # 按实际接线选 a/b/c
sudo reboot
sudo bash verify.sh                       # 期望全 PASS
```

可选参数：

- `--trigger-hz N`：硬件触发频率，默认 **10**（必须 ≤ 相机流帧率 / 2）
- `--no-reboot`：装完不自动重启（DT 仍需重启生效）

安装脚本会：

1. 装 dtbo 到 `/boot/tegra234-p3767-camera-p3768-y306-mixed-<profile>.dtbo`
2. 装 6 个相机模块 + `y306_fsync_cap.ko`，替换 `tegra-camera.ko`（原文件备份为 `.orig`）
3. 装 Orbbec SDK 运行库到 `/opt/orbbec-sdk` 与 `y306_orb_trigger`
4. 装 systemd 服务：`y306-obc-camera`（加载驱动）、`y306-orbbec-trigger`（设 MCU 频率 + 相机触发）
5. 按 profile 写 `/etc/fzcam_cfg.ini`、`/etc/y306-sync.conf`
6. 在 `extlinux.conf` 里新增/更新 `LABEL y306-mixed-<profile>` 并设为默认
7. 记录 `/etc/y306-sync-profile`，`depmod` + `sync`

> **无需人工打开 OrbbecViewer**：SDK 设置已做成开机服务。

## 4. 同步与时间戳是怎么实现的

```
MCU STM32F103 (0xAA 指令设频，默认 10 Hz)
      │ FSYNC (Pin18)
      ▼
  AON PCC.00 ──┬── MAX9296  MFP0 ── 同轴 ── ISX031F (RGB)
               └── MAX96724 MFP0 ── 同轴 ── MAX9295D MFP6 ── Gemini 335Lg
               │
      GTE 给每个上升沿打硬件戳（TSC 域，32 ns）──► /dev/y306_fsync
               │
      V4L2 帧时间戳（同为 TSC 域）──► 取"帧前最近边沿"配对
               ▼
      每帧：seq / 帧 TSC / 触发 TSC / 延迟 / UTC
```

开机顺序由 systemd 保证：
`y306-obc-camera`（驱动）→ `y306-orbbec-trigger`（MCU 频率 + 相机触发）→ `fzcam_cfg`（RGB serdes）

实测（10 Hz，重启后无人工操作）：

| 设备 | 帧率 | 延迟 p50 | spread |
|---|---|---|---|
| RGB `/dev/video0` | 9.999 fps | 18.81 ms | 0.035 ms |
| 335Lg `/dev/video5` | 9.999 fps | 35.67 ms | 0.003 ms |

## 4.0 触发源：MCU（默认）

Y306 标配由载板 MCU 产生 FSYNC，`/etc/y306-sync.conf` 默认 `TRIGGER_SOURCE=mcu`：
开机用 `0xAA 01 <freq×100> <duty> <cs> 0x55` 下发 10 Hz / 10%，MCU 回 `AA 02 00 0A 0A C0 55`。

> **两条必须知道的坑**
> 1. **MCU 固件必须 ≥ V1.2_10**。旧版（V1.0）不响应 `0xAA` 频率指令、也不产生触发，
>    表现为"相机进了触发模式但一帧不出、`/dev/y306_fsync` 边沿为 0"。
>    升级方法见 `../../cases/CASE-20261107-y306-mcu-firmware-upgrade.md`。
> 2. **打开串口会 DTR 复位 MCU**，必须等 ~1.6 s 再发帧，否则"发得出去、没有应答"。
>    `y306_mcu_freq.py` 已内置该延时与 3 次重试。

### 4.0.1 没有 MCU 的调试样机（`soc`）

系统按 `/etc/y306-sync.conf` 的 `TRIGGER_SOURCE` 自动选触发源：

| 值 | 行为 |
|---|---|
| `mcu`（**默认**，Y306 产品配置） | 由载板 MCU 产生触发；开机下发 10 Hz 指令 |
| `soc` | 由 SoC 产生触发（仅调试样机、没有 MCU 时使用） |
| `auto` | 开机探测：有 MCU 用 MCU，没有则退回 SoC |

SoC 产生触发的原理：`y306_fsync_cap` 模块以 `gen_hz=10` 加载，用 hrtimer 驱动
AON PCC.00（与 MCU 同一根 FSYNC 网络），HTE 仍然对这根线上的每个上升沿打 TSC 戳，
所以**时间戳链路完全不变**。

实测（无 MCU 的整机，10 Hz）：

```
video0 10.0000 fps   video4 10.0014 fps
延迟 35.741 ms  spread 0.001 ms  （与有 MCU 时同量级）
```

> 注意：相机上电初始化比 systemd 服务晚，单次设置可能不生效，
> 所以包里另有一个 `y306-orbbec-trigger-late.timer`（开机 40 s 后再设一次）。

## 4.1 接 1 / 2 / 3 路相机时（重要）

`fzcam_cfg.ini` 的 `position=Video_ABCD` 是**端口掩码**（A/B/C/D 四口），
不是"接几路就填几个 1"。**建议始终写 `Video_1111`**，工具会自动识别实际锁定的链路，
只配置有相机的那些口。

**本包内的 dtsi 已按正确顺序排列**（同型号节点降序书写），因此 `video0` 对应 Link A：

| 物理端口 | i2c 地址 | video 节点 |
|---|---|---|
| Link A | 0x3a | `/dev/video3` |
| Link B | 0x3b | `/dev/video2` |
| Link C | 0x3c | `/dev/video1` |
| Link D | 0x3d | `/dev/video0` |

（若用自行修改的 dtsi，务必保持这个书写顺序——节点顺序反过来会导致 video0 变成 Link D。）

所以：

| 接了 | 有画面的节点 | 没画面的节点 |
|---|---|---|
| 1 路（A） | video3 | video0-2 |
| 2 路（A,B） | video2, video3 | video0, video1 |
| 3 路（A,B,C） | video1, video2, video3 | video0 |
| 4 路 | video0-3 | — |

**上层程序不要假设 `video0..N-1` 就是前 N 路**，否则 1/2/3 路时全部打不开。
正确做法是用枚举工具按"相机地址/端口"选节点：

```bash
sudo /usr/local/bin/y306_list_cams.py --probe
# node    type   addr   port     status
# video0  RGB    0x3d   Link D   no signal
# video1  RGB    0x3c   Link C   10.00 fps
# video2  RGB    0x3b   Link B   10.00 fps
# video3  RGB    0x3a   Link A   10.00 fps
# video4  335Lg  0x66   stream=depth 10.00 fps
# ...
```

节点名里也直接带地址，可以按名字映射，不必依赖序号：

```bash
cat /sys/class/video4linux/video1/name     # vi-output, fzcam 2-003c  → Link C
```

> 若运行着 OrbbecViewer，它会独占 335Lg 的节点，枚举出的 fps 会失真甚至 no signal。

## 4.2 MCU 固件（触发源）

相机同步触发由载板 STM32F103 产生，**固件必须 ≥ V1.2_10**（旧版不响应频率指令、不产生触发）。

```bash
sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc --check   # 查版本
sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc           # 升级（两趟 + 两次断电）
sudo python3 /opt/y306-sync/mcu/tools/mcu_freq.py 10 10           # 设 10 Hz / 10%
```

完整说明（变体选择、A/B 双槽、协议表、故障处理）见 **`mcu/README-中文.md`**。

## 5. 取每帧时间戳

```bash
# 单次采样（默认 5 s）
sudo /usr/local/bin/y306_frame_ts.py --dev /dev/video5 --duration 10 --out /tmp/f5.csv
sudo /usr/local/bin/y306_frame_ts.py --dev /dev/video0 --duration 10 --out /tmp/rgb.csv

# 触发边沿检查
sudo /usr/local/bin/y306_fsync_read.py 4

# 配对质量（M7 判据：帧/触发 1±2%、spread < 2 ms）
sudo /usr/local/bin/pair_frames.py /dev/video5 10

# 改触发频率（会作用于相机，需 <= 帧率/2）
sudo /usr/local/bin/y306_mcu_freq.py 10 10
```

CSV 字段：

```
seq,frame_tsc_s,trigger_tsc_s,latency_ms,outlier,relock,utc
1,309.947918,309.929124,18.794,0,0,2026-11-04T14:50:43.000Z
```

- `frame_tsc_s` / `trigger_tsc_s`：**TSC 域**（不是单调时钟）
- `latency_ms`：帧相对触发沿的延迟（该流的固定流水线延迟）
- `outlier`：偏离期望延迟超过 5 ms，已从统计剔除
- `relock`：相位重锁后的第一帧
- `utc`：`trigger_ktime + (CLOCK_REALTIME − CLOCK_MONOTONIC)`

工具内置**鲁棒配对**：离群帧过滤 + 相位重锁检测 + 分段统计（`--selftest` 可离线自测）。

## 6. 验证

```bash
sudo bash verify.sh        # 60 帧/路
sudo bash verify.sh 300    # 长一点
```

检查项：DT、触发服务、FSYNC 边沿频率、节点数、每路取流与每帧字节数、
`corr_err/uncorr_err`、**帧周期是否等于触发周期**、时间戳 CSV。

期望每帧字节：335Lg depth/color `2048000`、IR `1024000`；ISX031F `5898240`（1920×1536 UYVY）。

## 7. 回滚

```bash
sudo bash uninstall.sh
sudo reboot
```

会移除服务/模块/dtbo/SDK、恢复 `tegra-camera.ko.orig`，并把默认启动项指回 `JetsonIO`。

## 8. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 没有任何 video 节点 | overlay 未应用（label 引用错误/逗号后多空格） | 看 `grep ^DEFAULT /boot/extlinux/extlinux.conf`；用 `fdtoverlay` 离线验证 dtbo |
| 335Lg 不出图、`uncorr_err` 超时 | 相机进了触发模式但触发没到 | 确认 DT 里 96724 的 `fsync_mfp_index = <0>`；读 `i2c 0x27 0x0300` 应为 `0x83` |
| 帧率与触发不符 | 触发频率 > 帧率/2 | 降到 ≤ 帧率/2（30 fps 流 → ≤15 Hz） |
| RGB 帧带 `(error)`、`--stream-to` 为 0 字节 | RGB 用了 4K 模式 | `v4l2-ctl --set-fmt-video=width=1920,height=1536,pixelformat=UYVY` |
| 重启后 335Lg 不同步 | 触发设置丢失 | 本包已用 `y306-orbbec-trigger.service` 自动补，检查该服务状态 |
| 两路偏置变化 | 触发相位重锁（换频率/重启后常见） | 用 `y306_frame_ts.py` 的 `relock` 事件重新标定 |

## 9. 已知限制

- 335Lg 的硬件触发**只在开机服务生效时**成立；手工 `systemctl stop y306-orbbec-trigger` 后相机会回自由运行。
- 触发频率改变后，两路相对延迟偏置会重新锁定（实测 1.1 ms ↔ 16.9 ms 两种），需重新标定。
- 8 h 稳测中出现过 1 次相位重锁（RGB 延迟整体平移 ~18 ms，spread 不变），工具会报 `relock` 事件。
- 本包只覆盖 profile 出图 + 同步 + 时间戳；激光雷达 PTP 对齐不在范围内。

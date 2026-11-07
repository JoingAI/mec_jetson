# Y306 MCU 固件与 OTA 升级手册（触发信号输出）

> 适用：Y306 载板（STM32F103 MCU）+ Orin NX，L4T R39.2.1
> 固件版本：**V1.2.10**（本包内已编译好 ACC / NOACC 两种变体的 A、B 双槽 hex）

---

## 1. MCU 是做什么的

Y306 的相机同步触发由载板上的 STM32F103 产生：

```
STM32 PB0 (TIM3 PWM) ──► MAX96724 MFP0  ┐
                     ──► MAX9296  MFP0  ├──► 同轴 ──► 相机 SYNC IN
                     ──► Orin AON PCC.00┘   （SoC 侧由 HTE 给每个边沿打时间戳）
```

- **出厂默认 30 Hz / 10%**（预设档位 3，对应 1920×1080@30fps 相机）
- **掉电不保存**：每次上电回到默认档位，所以开机必须重新下发
- 与 Orin 通过 USART1↔USB 桥通信（`/dev/ttyACM0`，115200 8N1）

> ⚠️ **V1.2_10 之前的固件（如 V1.0）不实现 `0xAA` 频率指令、也不输出触发。**
> 现象是"相机已进硬件触发模式但一帧不出、`/dev/y306_fsync` 边沿为 0"。
> 拿到新板先按 §3 查版本，低于 V1.2_10 一律先升级。

## 2. 固件文件与变体

```
mcu/firmware/
├── F306_MCU_A_ACC_V1.2.10.hex      带 ACC/IGN 开关机控制
├── F306_MCU_B_ACC_V1.2.10.hex
├── F306_MCU_A_NOACC_V1.2.10.hex    不带 ACC 控制（Y306 现网配置）
└── F306_MCU_B_NOACC_V1.2.10.hex
```

| 变体 | 适用 | 判断方法 |
|---|---|---|
| **NOACC** | 不做 ACC/IGN 开关机时序（Y306 目前都是这个） | `MCU_VER?` 返回 `..._NOACC_...` |
| **ACC** | 由 IGN 信号控制 SoM 开关机 | `MCU_VER?` 返回 `..._ACC_...` |

**A/B 是双槽**（Bootloader + 两个 16 KB 应用槽），任一槽校验失败会自动回退到另一槽。
升级只写**非活动槽**，所以必须两趟。

> 🔴 **两个槽必须是同一变体**。混用（A=ACC、B=NOACC）会导致开关机时序在回退时突变。
> 变体切换必须两趟都刷目标变体，中间断电两次。

## 3. 查当前版本（升级前必做）

```bash
sudo bash mcu/upgrade.sh --variant noacc --check
# MCU_VER: F306_MCU_A_NOACC_V1.2_10
```

或直接：

```bash
sudo python3 mcu/tools/mcu_ver.py --port /dev/ttyACM0
```

> ⚠️ **打开串口会 DTR 复位 MCU，必须等 1.6 s 再发命令**，否则永远"没有应答"。
> `mcu_ver.py` / `mcu_freq.py` 已内置该延时和 3 次重试。

## 4. OTA 升级（两趟 + 两次整机断电）

```bash
# 第 1 趟：写非活动槽
sudo bash mcu/upgrade.sh --variant noacc

# —— 整机断电：12V 电源关掉，等 5 秒再上电 ——

# 第 2 趟：写另一个槽
sudo bash mcu/upgrade.sh --variant noacc

# —— 再整机断电、上电 ——

sudo bash mcu/upgrade.sh --variant noacc --check     # 确认版本
```

脚本内部调用 `tools/ota_send.py`，会：

1. 握手 `OTA:START:F306OTA`，MCU 回 `OTA:READY:<活动槽>:<目标槽>:16384`
2. `OTA:SIZE` → `OTA:ERASE` → 16 个 1 KB 分块（CRC16，NAK 自动重传）→ `OTA:FINAL`（整片 CRC32）
3. 回 `OTA:OK` 表示写入成功

### 为什么必须整机断电

- 槽位切换发生在 **MCU 复位**时，由 Bootloader 决定。
- **SoM `reboot` 不会复位 MCU**（MCU 由载板 12V 供电，SoM 重启时它一直在跑）。
- 实测：只重启 SoM 三次，版本仍是旧的；整机断电一次就切过去了。
- 串口 DTR 脉冲也不能复位它（该桥的 DTR 未接 NRST）。

### 只做一趟会怎样

第 1 趟后是「新版本活动 + 旧版本兜底」。新槽若 CRC 校验失败，
Bootloader 会**静默回退旧固件**，机器行为悄悄变回原样 —— 所以必须两趟。

## 5. 触发信号输出：频率与占空比

### 5.1 用工具设置（推荐）

```bash
sudo python3 mcu/tools/mcu_freq.py 10 10      # 10 Hz / 10%
# TX aa0103e80aa055
# RX aa02000a0ac055                          ← 状态 0x00=OK，回读 10Hz/10%
```

参数：`freq_hz`（1–655）、`duty_pct`（1–100）。
**建议占空比用 10%**：50% 会与 CSI 出图互相干扰。

### 5.2 常用预设档位（指令 0x05，全部 10% 占空比）

| 索引 | 频率 | 说明 |
|---|---|---|
| 0 | 10 Hz | 与 30 fps 相机配合的常用档 |
| 1 | 20 Hz | |
| 2 | 25 Hz | |
| 3 | **30 Hz** | **出厂默认**（1920×1080@30fps） |
| 4 | 60 Hz | |

> 触发频率必须 **≤ 相机流帧率 / 2**（30 fps 的流 → 触发 ≤15 Hz），否则相机不会按预期出图。

### 5.3 协议参考（0xAA 帧）

```
上行（Orin → MCU）：AA CMD P1 P2 P3 CS 55        CS = 前 5 字节和的低 8 位
下行（MCU → Orin）：AA 02 ST FREQ DUTY CS 55     ST: 00=OK, 01=参数错, 02=不支持
```

| CMD | 功能 | P1P2P3 |
|---|---|---|
| `0x01` | 设频率/占空比 | P1P2 = 频率×100（大端），P3 = 占空比% |
| `0x02` | 查状态 | 回 PPS 锁定 / 看门狗状态 |
| `0x05` | 预设档位 | P1 = 索引 |
| `0x07` | 对齐 | 计数器对齐到 PPS 边沿 |
| `0x08` | 时钟同步 | 回 MCU 的 DWT 微秒时间戳 |
| `0x09` | 触发时间戳 | 回最近一次触发的序号+时间戳 |

例：10 Hz / 10% → `AA 01 03 E8 0A A0 55`
（0x03E8 = 1000 = 10.00 Hz × 100；校验和 = 0xAA+0x01+0x03+0xE8+0x0A = 0x1A0 → 0xA0）

## 6. 验收

```bash
# ① 版本
sudo bash mcu/upgrade.sh --variant noacc --check

# ② 触发边沿（SoC 侧 HTE 计数）
sudo y306_fsync_read.py 3
# tsc 间隔 ns: mean=99998737 ... -> 10.0001 Hz

# ③ 相机帧率（应严格跟随触发）
sudo y306_list_cams.py --probe
# video0  RGB  ...  10.00 fps
```

期望：边沿 10 Hz ±0.1%，相机帧率 = 触发频率（或其整数分频）。

## 7. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `MCU_VER?` 无应答 | 打开串口后没等 1.6 s（DTR 复位） | 用 `mcu_ver.py`（已内置延时） |
| `MCU_VER?` 无应答（等足 1.6 s 也没有） | 串口被占用 / 桥未枚举 | `ls /dev/ttyACM*`；`fuser /dev/ttyACM0` |
| OTA 后版本没变 | 只写了非活动槽，未断电 | 整机断电再上电（SoM 重启不算） |
| 相机 0 帧、边沿为 0 | MCU 固件 < V1.2_10，不产生触发 | 按 §4 升级 |
| 帧率只有触发频率的一半 | 触发 > 帧率/2 | 降触发频率或提高流帧率 |
| 开机后是 30 fps 而不是 10 fps | MCU 默认档位 30 Hz，服务还没下发 | 检查 `y306-orbbec-trigger.service` 日志 |
| 升级后开关机行为变了 | ACC/NOACC 变体刷错 | 两趟刷回正确变体 |

## 8. 恢复出厂 / 变体切换

变体切换（如 NOACC → ACC）：

1. `sudo bash mcu/upgrade.sh --variant acc` → 整机断电上电
2. `sudo bash mcu/upgrade.sh --variant acc` → 整机断电上电
3. `--check` 确认两槽都是 `_ACC_`

> 若机器因变体不匹配无法开机：用 **ST-Link + STM32CubeProgrammer** 直连 MCU，
> 同时烧 `Bootloader(0x08000000)` + `A 槽应用(0x08004000)`，绕过 OTA。

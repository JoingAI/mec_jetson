# F306 MCU 命令使用说明

**固件 V1.2.11** ｜ 串口 `/dev/ttyACM0`（115200-8N1）｜ 配套工具 `mcu_cmd.py`

> 本文是**操作手册**：每条命令给出现成帧、示例和预期应答，可直接复制执行。
> 协议细节与 OTA 流程见《MCU-固件手册-V1.2.11.md》。

---

## 0. 快速上手（最常用 5 条）

```bash
# ① 查版本 + 平台（Y306=[PPS]，F306=[GPS]）
printf 'MCU_VER?\n' > /dev/ttyACM0; timeout 1 cat /dev/ttyACM0

# ② 查状态（P1=PPS/GPS 锁定，P2=喂狗）
AA 02 00 00 00 AC 55          → 期望 AA 02 00 <P1> <P2> CS 55

# ③ 开启触发 30Hz/10%
AA 01 0B B8 0A 78 55          → 期望 AA 02 00 1E 0A CS 55

# ④ 关闭触发（占空比 0）
AA 01 0B B8 00 6E 55          → 期望 AA 02 00 00 00 AC 55

# ⑤ 查最近一次触发时间戳（判断触发是否在跑）
AA 09 00 00 00 B3 55          → 返回 24 位 DWT 微秒时间戳，连查两次在变=触发在跑
```

**一键工具**（推荐）：

```bash
sudo python3 mcu_cmd.py ver
sudo python3 mcu_cmd.py status
sudo python3 mcu_cmd.py trig on --hz 30 --duty 10
sudo python3 mcu_cmd.py trig off
sudo python3 mcu_cmd.py ts
```

---

## 1. 帧格式

### 请求（主机 → MCU，7 字节）

```
AA CMD P1 P2 P3 CS 55
CS = (AA + CMD + P1 + P2 + P3) & 0xFF
```

### 应答（MCU → 主机，7 字节）

```
AA 02 STATUS P1 P2 CS 55
CS = (AA + 02 + STATUS + P1 + P2) & 0xFF
```

| STATUS | 含义 |
|---|---|
| 0x00 | 成功 |
| 0x01 | 参数非法 |
| 0x02 | 命令不支持 |

### 计算校验和

```python
def frame(cmd, p1=0, p2=0, p3=0):
    f = [0xAA, cmd, p1, p2, p3]
    f += [sum(f) & 0xFF, 0x55]
    return bytes(f)
```

---

## 2. 触发控制（0x01 / 0x05）

### 2.1 开启触发（0x01）

```
AA 01 <freq_H> <freq_L> <duty_%> <CS> 55
freq = 频率 × 100（大端），duty = 占空比 0–100
```

| 频率 | 命令帧 | 应答（P1/P2） |
|---|---|---|
| 10 Hz | `AA 01 03 E8 0A A0 55` | 0x0A / 0x0A |
| 20 Hz | `AA 01 07 D0 0A 8C 55` | 0x14 / 0x0A |
| 25 Hz | `AA 01 09 C4 0A 82 55` | 0x19 / 0x0A |
| 30 Hz | `AA 01 0B B8 0A 78 55` | 0x1E / 0x0A |
| 60 Hz | `AA 01 17 70 0A 3C 55` | 0x3C / 0x0A |

> 应答 `P1 = 生效频率 Hz`（>255 报 255），`P2 = 占空比 %`。

### 2.2 关闭触发（duty = 0）

```
AA 01 0B B8 00 6E 55      →  AA 02 00 00 00 AC 55
```

关闭后：
- TIM3 通道停止、PB0/PB1 拉低、触发时间戳中断关闭；
- 应答 `P1=0, P2=0`；
- 相机不再收到触发（停止出图）。

**为什么用 duty=0**：协议没有独立的“停止”命令，频率最低被钳到 1 Hz；占空比 0 是唯一能完全关掉输出的方式。

### 2.3 按预设开启（0x05）

```
AA 05 <index> 00 00 <CS> 55
```

| index | 频率/占空 | 命令帧 |
|---|---|---|
| 0 | 10 Hz / 10% | `AA 05 00 00 00 AF 55` |
| 1 | 20 Hz / 10% | `AA 05 01 00 00 B0 55` |
| 2 | 25 Hz / 10% | `AA 05 02 00 00 B1 55` |
| 3 | 30 Hz / 10%（出厂默认） | `AA 05 03 00 00 B2 55` |
| 4 | 60 Hz / 10% | `AA 05 04 00 00 B3 55` |

> 下发 0x05 会**同时开启触发**。

### 2.4 上电默认状态

| 版本 | 上电默认 |
|---|---|
| ≤ V1.2_10 | 触发开启（30 Hz/10%） |
| **≥ V1.2_11** | **触发关闭（duty=0）** |

### 2.5 验证触发开/关

```bash
# 方法一：触发时间戳（0x09）连查两次
AA 09 00 00 00 B3 55   # 读 t1
sleep 1
AA 09 00 00 00 B3 55   # 读 t2
# 开启：t2-t1 ≈ 1,000,000 µs（24 位回绕需注意）
# 关闭：t1 == t2
```

```bash
# 方法二：Orin 侧 GTE 计数（需要 y306-fsync 服务）
python3 -c "import json;print(json.load(open('/run/timesync/fsync-capture.json'))['count'])"; sleep 3
python3 -c "import json;print(json.load(open('/run/timesync/fsync-capture.json'))['count'])"
# 开启：3 秒增加 ~90（30Hz）；关闭：不变
```

```bash
# 方法三：相机帧率
sudo python3 /tmp/cam_frames.py /dev/video0   # 开启=30fps，关闭=0
```

---

## 3. 状态查询（0x02）

```
AA 02 00 00 00 AC 55      →  AA 02 00 <P1> <P2> CS 55
```

| 字段 | 含义 |
|---|---|
| **P1** | 锁定状态：**Y306** = I210 外部 PPS 锁定；**F306** = GPS PPS 锁定；1=锁定，0=未锁定 |
| P2 | 喂狗：0=关闭，1=运行，2=超时 |

示例：`AA 02 00 01 00 AD 55` → P1=1（已锁定），P2=0（喂狗关闭）。

---

## 4. 时间戳查询（0x08 / 0x09）

### 4.1 0x08 — MCU 当前时间戳（时钟同步）

```
AA 08 00 00 00 B2 55      →  STATUS/P1/P2 = 24 位 DWT 微秒
T2 = (STATUS << 16) | (P1 << 8) | P2
```

用于求 `offset(MCU − 主机)`：连测 N 次取 `max(T2 − T4) + 608 µs`（7 字节@115200 的传输时间）。

### 4.2 0x09 — 最近一次触发时间戳

```
AA 09 00 00 00 B3 55      →  STATUS/P1/P2 = 24 位 DWT 微秒
```

与 0x08 同域；**连查两次是否变化**即可判断触发是否在跑。

> 24 位微秒计数器 **16.78 s 回绕**，跨回绕时用 0x08 的偏移解算。

---

## 5. 触发上报（0x0A / 0x0B / 0x0C）

| 命令 | 方向 | 说明 |
|---|---|---|
| 0x0A | MCU → 主机 | 每个触发沿上报 24 位时间戳，需 0x0B 确认 |
| 0x0B | 主机 → MCU | 累计确认（P1P2P3 = 已收到的最大时间戳），MCU 不回帧 |
| 0x0C | 主机 → MCU | 上报开关：`AA 0C 01 00 00 B7 55` 开 / `AA 0C 00 00 00 B6 55` 关 |

**可靠性**：32 帧窗口；未确认每 200 ms 重发（最多 2 次）；1 s 无确认自动关闭并记故障日志。

---

## 6. 硬件喂狗（0x04）

| 动作 | 命令帧 | 说明 |
|---|---|---|
| 停止 | `AA 04 00 00 00 AE 55` | PA5 恒低 |
| 开启 | `AA 04 01 <hz> 00 <CS> 55` | 例 5 Hz：`AA 04 01 05 00 B4 55` |
| 改参数 | `AA 04 02 <hz> <timeout_s> <CS> 55` | 例 5 Hz/10 s：`AA 04 02 05 0A BF 55` |

应答：`P1 = 当前频率`，`P2 = 状态`（0 关闭 / 1 运行 / 2 超时）。
超时只写日志并上报，**不自动复位核心板**。

---

## 7. PWM-PPS 对齐（0x07）

| 模式 | 命令帧 |
|---|---|
| 关闭 | `AA 07 00 00 00 B1 55` |
| 上升沿对齐（默认） | `AA 07 01 00 00 B2 55` |
| 下降沿对齐 | `AA 07 02 00 00 B3 55` |

应答 `P1 = 当前模式`。对齐后每个 PPS 沿复位触发网格（相位修正通常 <1 µs）。

---

## 8. 版本查询（ASCII）

```bash
printf 'MCU_VER?\n' > /dev/ttyACM0; timeout 1 cat /dev/ttyACM0
# MCU_VER: F306_MCU_B_ACC_V1.2_11 [PPS]      ← Y306
# MCU_VER: F306_MCU_A_ACC_V1.2_11 [GPS]      ← F306
```

> **必须 LF 结尾**（不是 CRLF）。

---

## 9. 一键工具 mcu_cmd.py

```bash
sudo python3 mcu_cmd.py ver                       # 版本+平台
sudo python3 mcu_cmd.py status                    # 0x02
sudo python3 mcu_cmd.py trig on --hz 30 --duty 10 # 开触发
sudo python3 mcu_cmd.py trig off                  # 关触发
sudo python3 mcu_cmd.py trig preset 3             # 预设 30Hz
sudo python3 mcu_cmd.py ts                        # 0x09
sudo python3 mcu_cmd.py sync                      # 0x08
sudo python3 mcu_cmd.py wdog on --hz 5 --timeout 10
sudo python3 mcu_cmd.py wdog off
sudo python3 mcu_cmd.py align 1                   # 0/1/2
sudo python3 mcu_cmd.py report on|off
sudo python3 mcu_cmd.py raw AA 01 03 E8 0A        # 自定义帧（自动补 CS/55）
```

输出示例：

```
TX: aa 01 0b b8 0a 78 55
RX: aa 02 00 1e 0a d4 55 {'status': 0, 'p1': 30, 'p2': 10}
```

---

## 10. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| 发命令无应答 | 串口被占用 | 先 `sudo systemctl stop mcu-trigger` |
| `MCU_VER?` 无回复 | 用了 CRLF 或大小写错 | 必须 `MCU_VER?\n` |
| 改频率后相机不出图 | 频率/占空比设置不当 | 确认 P2（占空）>0 |
| 上电相机不出图 | V1.2.11 默认不触发 | 发 `AA 01 0B B8 0A 78 55` |
| 关触发后仍有相机帧 | 帧是关闭前缓存的 | 等 1–2 s |
| 0x02 P1 一直为 0 | Y306 无 PPS / F306 无 GPS | 查 I210 pps-out / GPS 天线 |

---

## 11. 命令速查表

| 功能 | 命令帧 |
|---|---|
| 版本 | `MCU_VER?\n`（ASCII） |
| 状态 | `AA 02 00 00 00 AC 55` |
| **开触发 30Hz** | `AA 01 0B B8 0A 78 55` |
| **开触发 10Hz** | `AA 01 03 E8 0A A0 55` |
| **关触发** | `AA 01 0B B8 00 6E 55` |
| 预设 | `AA 05 <0..4> 00 00 <CS> 55` |
| 触发时间戳 | `AA 09 00 00 00 B3 55` |
| MCU 时间戳 | `AA 08 00 00 00 B2 55` |
| 对齐 | `AA 07 <0/1/2> 00 00 <CS> 55` |
| 喂狗 | `AA 04 <0/1/2> <hz> <t> <CS> 55` |
| 上报开关 | `AA 0C <0/1> 00 00 <CS> 55` |

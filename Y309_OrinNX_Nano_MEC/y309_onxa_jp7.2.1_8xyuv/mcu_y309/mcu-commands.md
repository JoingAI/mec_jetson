# MCU 同步命令全集（Y309 MS51XB9AE）

> 端口：`/dev/ttyTHS1`，**38400 8N1**
> 固件：`Y309_mcu_V3.0_20261102_1127`（含 IC0 捕获、mode 三态、诊断字段）

## 1. 两种发送方式

### ① 用工具（推荐，自动加前缀）

```bash
python3 /home/nvidia/y309_sync/scripts/y309ctl.py <命令>
```

### ② 手工串口（必须加前缀）

固件开了前缀保护（`CFG_CMD_PREFIX_ENABLE=1`，前缀 `#Y309:`），**不带前缀的行会被静默忽略**：

```
#Y309:status
#Y309:freq 10
#Y309:mode auto
```

> 行尾 `\r` 或 `\n` 均可；只接受可见 ASCII。

---

## 2. 命令总表

| 命令 | 语法 | 响应 | 说明 |
|---|---|---|---|
| 版本 | `ver` | `Y309_mcu_V3.0_...` | 查固件版本 |
| 连通 | `ping` | `PONG` | 测串口 |
| 状态 | `status` | `ST pwr=3 pps=1 per=994 f=10 d=10 en=1` | 一次性状态 |
| 频率 | `freq <Hz>` | `OK` / `ERR` | 只改频率，保留当前占空比 |
| 占空比 | `duty <1..100>` | `OK` / `ERR` | 单位 %，最小 1% |
| 频率+占空比 | `set <Hz> <duty%>` | `OK` / `ERR` | 一次设置；duty 省略默认 50 |
| 触发源查询 | `mode` | `MODE PPS` / `MODE FREE` / `MODE AUTO` | 查当前模式 |
| 触发源设置 | `mode pps\|free\|auto` 或 `mode 0\|1\|2` | `OK mode ...` | 见 §3 |
| 兼容旧命令 | `force 0\|1` | `OK force off/on` | `1`=AUTO，`0`=PPS |
| 心跳 | `hb 0\|1` | `OK hb on/off` | 每秒一行 `HB ...` |
| bootloader | `boot` | `BOOT present (...)` | 只读查询 |
| OTA 请求 | `ota` | `OK OTA ready, power cycle to enter boot` | 写请求后**断电重启**进入 boot |

> 未识别命令：回显 `ERR [原内容]`。

---

## 3. 打开 / 关闭输出（核心）

MCU 没有独立的“开关输出”命令，输出由**触发源模式**决定：

| 模式 | 命令 | 输出行为 |
|---|---|---|
| **PPS**（默认） | `mode pps` / `mode 0` / `force 0` | **只有 PPS 有效时才输出**；丢 PPS → `en=0` |
| **FREE** | `mode free` / `mode 1` | 上电即按设定频率输出，**完全不依赖 PPS** |
| **AUTO** | `mode auto` / `mode 2` / `force 1` | 一直输出；有 PPS 时按 PPS 沿对齐相位 |

### 打开输出

| 场景 | 命令 |
|---|---|
| 有 I210 PPS（正常同步） | `mode pps`（默认，PPS 锁定后自动 `en=1`） |
| 没有 PPS，只想出触发 | `mode free` |
| 没有 PPS 也要出，且希望有 PPS 时自动对齐 | `mode auto` |

### 关闭输出

| 方式 | 说明 |
|---|---|
| `mode pps` + 断开/停止 PPS | `en` 变 0，PWM 停（**推荐**） |
| 断电 | 彻底关闭 |
| `mode free`/`auto` 下无法关输出 | 这两个模式设计为“一直输出” |

> 如果你需要“软件一键关输出”，需要固件加一个 `mode off`（当前没有）——可以提为需求。

---

## 4. 频率与占空比

| 项 | 范围/说明 |
|---|---|
| 频率 | `1 .. 65535` Hz；低于 1.91 Hz 走软件翻转档（最低约 0.0076 Hz） |
| 占空比 | `duty` 命令 1–100%（内部 0.1% 分辨率，最小 0.1%） |
| 相机触发建议 | **10 Hz / 10%**（50% 会干扰 CSI，出现 `err_data 512`） |
| 掉电保存 | **不保存**，断电恢复默认 10 Hz / 50% |

---

## 5. PPS

| 项 | 说明 |
|---|---|
| 输入 | P1.2（脚 7），I210 SDP0 1Hz，22R 串阻 |
| 捕获 | **IC0 硬件捕获中断**（与主循环解耦） |
| 软件开关 | **无**（硬件输入常开；是否依赖它由 `mode` 决定） |
| 状态字段 | `status`/`HB` 里的 `pps`（0/1）、`per`（周期 ms）、`cap`（边沿累计）、`to`（超时解锁次数）、`lper`（最近被拒周期）、`bad`（连续非法计数） |
| 判定 | 窗口 300–2500 ms，容差 ±15%；漏沿（1.8–2.2×）容错；`LOSS_CNT=3`、`TIMEOUT=2600 ms` |

相关诊断里：

```
HB 15 pps=1 per=994 f=10 en=1 lper=0 bad=0 to=0 cap=9
```

---

## 6. 默认值（每次上电）

| 参数 | 默认 |
|---|---|
| 触发源 | `PPS`（`CFG_TRIG_SRC_DEFAULT=0`） |
| 频率 | 10 Hz |
| 占空比 | 50% |
| 心跳 | 关（`hb 0`） |

---

## 7. 二进制协议（可选，0xAA 帧）

| 命令 | 码 | 作用 |
|---|---|---|
| `CMD_PING` | 0x01 | 回 0x81 PONG |
| `CMD_SET_FREQ` | 0x10 | 设频率（Hz） |
| `CMD_SET_DUTY` | 0x11 | 设占空比（万分比，5000=50%） |
| `CMD_SET_BOTH` | 0x12 | 频率+占空比 |
| `CMD_GET_STATUS` | 0x30 | 状态 |
| `CMD_GET_VERSION` | 0x31 | 版本 |
| `CMD_GET_BOOT_TIME` | 0x32 | 上电各段耗时 |

> 文本行里出现 0xAA 会中止文本识别、转入二进制帧解析。

---

## 8. 常用场景脚本

```bash
Y=/home/nvidia/y309_sync/scripts/y309ctl.py

# 正常同步（有 PPS）
python3 $Y mode pps
python3 $Y set 10 10
python3 $Y hb 1
python3 $Y status

# 无 PPS 调试
python3 $Y mode free
python3 $Y set 10 10

# 关输出（先切回 PPS，再停 PPS）
python3 $Y mode pps

# 恢复默认
python3 $Y set 10 50
python3 $Y mode pps
python3 $Y hb 0
```

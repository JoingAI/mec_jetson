# 测试步骤（V3.0 → V3.1）

## 准备

`y309_交付` 目录里有 5 个文件：

| 文件 | 用途 |
|---|---|
| `y309ctl.py` | 工具 |
| `Y309_Bootloader_V1_20261029_1208.hex` | 烧 LDROM |
| `Y309_Aprom_V3.0_20261029_1208.hex` | 烧 APROM（**起点**） |
| `Y309_Aprom_V3.1_20261029_1208.hex` | 升级用的**目标**版本 |
| `工具使用说明.md` | 命令说明 |

> 两个 Aprom 文件大小一样，**只有版本号不同**，所以升级后看版本号变化就能判断成功。

---

## 第一步：ICP 烧录

**⚠ 先把 ICP 工具里的 LDROM 区域改成 `3K字节`**

| 区块 | 文件 |
|---|---|
| LDROM | `Y309_Bootloader_V1_20261029_1208.hex` |
| APROM | `Y309_Aprom_V3.0_20261029_1208.hex` |

烧完上电，Orin 应正常启动，MCU 运行 V3.0。

---

## 第二步：把文件放到 Orin

把 `y309ctl.py` 和 `Y309_Aprom_V3.1_20261029_1208.hex` 拷到 Orin 的同一目录，例如 `~/y309/`。

```bash
cd ~/y309
python3 y309ctl.py ver        # 应回 Y309_mcu_V3.0
python3 y309ctl.py boot       # 应回 BOOT present (LDROM OK, OTA ready)
```

---

## 第三步：升级第 1 步

```bash
python3 y309ctl.py update Y309_Aprom_V3.1_20261029_1208.hex
```

看到绿色的"准备完成"和操作提示。

**这一步不会重启，也不会中断业务。**

---

## 第四步：关机断电

按提示操作：

```bash
sudo poweroff
```

等关机完成后，**给整板断电 3 秒，再上电**。

---

## 第五步：升级第 2 步

等 Orin 进入系统后：

```bash
cd ~/y309
python3 y309ctl.py update Y309_Aprom_V3.1_20261029_1208.hex boot
```

会看到逐块进度，最后是绿色的"固件已写入并校验通过"和操作提示。

**这一步全程 MCU 不复位，Orin 不会掉电。**

---

## 第六步：关机断电

```bash
sudo poweroff
```

关机后**给整板断电 3 秒，再上电**。

---

## 第七步：验证

```bash
cd ~/y309
python3 y309ctl.py ver
```

应回 **`Y309_mcu_V3.1`** ← 版本变了 = 升级成功

---

## Y309内置MCU给触发信号，配置说明
```bash
python3 /home/nvidia/y309_sync/scripts/y309ctl.py ver
python3 /home/nvidia/y309_sync/scripts/y309ctl.py status        # ST pwr=3 pps=1 per=994 f=10 d=10 en=1
python3 /home/nvidia/y309_sync/scripts/y309ctl.py set 10 10     # 频率 10Hz / 占空比 10%
python3 /home/nvidia/y309_sync/scripts/y309ctl.py hb 1          # 心跳（HB 行，含 lper/bad/to/cap）
```
---

## RS485 共存保护

| 项 | 说明 |
|---|---|
| 心跳 | **默认关闭**（不再每秒打印 `HB ...`），需要时 `python3 y309ctl.py hb 1` |
| 命令前缀 | MCU 只响应 `#Y309:` 开头的命令（工具自动加），其它内容静默丢弃 |
| 目的 | 与板载 RS485 共用串口时，RS485 通信完全不受干扰 |

**测试 RS485 前记得停掉 gpsd**（它占着 `/dev/ttyTHS2`）：

```bash
sudo systemctl stop gpsd
# 跑 RS485 测试
sudo systemctl start gpsd
```

---

## 验收清单

| 检查项 | 期望结果 | 实际 |
|---|---|---|
| 第二步 `ver` | `Y309_mcu_V3.0` | |
| 第二步 `boot` | `BOOT present (LDROM OK, OTA ready)` | |
| 第五步 升级时 Orin | 不掉电、不重启 | |
| 第五步 传输 | 全部块 OK，CRC 校验通过 | |
| 第七步 `ver` | `Y309_mcu_V3.1` | |
| 第七步 `status` | `pwr=3` | |
| **升级模式下的关机** | `sudo poweroff` 后**核心板和载板都断电** | |
| **无心跳** | 上电后串口**不应**每秒出现 `HB ...` | |
| **前缀保护** | 用串口助手发裸 `status` → **无任何回应**；发 `#Y309:status` → 正常回 `ST ...` | |
| **hb 命令** | `hb 1` 后开始每秒打印心跳，`hb 0` 停止 | |

---

## 本次修复内容

| # | 问题 | 处理 |
|---|---|---|
| 1 | 输出里"已封印版"说法 | 改为"通用：烧录器与串口升级共用" |
| 2 | `设备回应: OK OTA ready, po` 被截断 | 命中后把整行读完 |
| 3 | 提示"请断电上电" | 改为先 `sudo poweroff` 再断电 |
| 4 | 升级完成没有明确成功提示 | 加绿色成功框 + 后续操作提示 |
| 5 | 关键提示不醒目 | 加终端颜色（青/绿/黄/紫） |
| 6 | **bootloader 模式下关机不断电** | bootloader 增加关机流程：监听 SHUTDOWN_REQ → 断主电 → 断自身保电 → 整板断电 |

---

## 如果失败

- **不会变砖**，MCU 停在升级等待状态
- 直接重跑第五步即可
- `ver`/`status` 没反应 = 在升级等待状态（正常），执行第五步
- `boot` 回 `BOOT none` = bootloader 没烧好，回第一步重烧

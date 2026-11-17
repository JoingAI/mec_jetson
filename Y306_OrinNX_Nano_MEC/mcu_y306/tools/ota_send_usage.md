# ota_send.py 使用说明

> 本文档独立说明 `ota_send.py` 的用途与执行方法，供现场升级参考。
> 完整的协议流程、A/B 双槽原理与首次烧录步骤见 [DELIVERY.md](../DELIVERY.md)。

## 一、用途与运行环境

| 项目 | 说明 |
|------|------|
| 用途 | 通过串口把 MCU 固件（.hex）发送给板卡完成远程 OTA 升级 |
| 运行环境 | **Orin NX（Linux）**，串口 `/dev/ttyACM0`（默认） |
| 依赖 | 零第三方依赖，仅 Python 标准库（禁止 `import pyserial`） |
| 串口权限 | 普通用户需在 dialout 组：`sudo usermod -aG dialout $USER`（重新登录生效）；或临时用 `sudo` |

## 二、固件（.hex）来源与命名

Keil 编译后 `post_build.bat` 自动把 hex 归档到：

```
F306_MCU/MDK-ARM/output/<Target>_<yyyyMMdd_HHmm>.hex
```

5 个 target 对应文件（升级只需 A/B 槽各一个，且必须与现场变体一致）：

| 变体 | 槽 A hex | 槽 B hex |
|------|---------|---------|
| ACC 版 | `F306_MCU_A_ACC_<时间戳>.hex` | `F306_MCU_B_ACC_<时间戳>.hex` |
| 非ACC 版 | `F306_MCU_A_NOACC_<时间戳>.hex` | `F306_MCU_B_NOACC_<时间戳>.hex` |

> 注意：
> - `--a` / `--b` 必须使用**同一变体**（都 ACC 或都 NOACC），混用会导致开关机行为异常。
> - 时间戳取最新的即可；脚本会校验 hex 链接基址是否与目标槽匹配，填错会直接报错而不是误写。

## 三、参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `--a` | 无 | 槽 A 链接的 `.hex`（目标槽为 A 时必填） |
| `--b` | 无 | 槽 B 链接的 `.hex`（目标槽为 B 时必填） |
| `--port` | `/dev/ttyACM0` | 串口设备，失败自动扫描 `/dev/ttyACM*`、`/dev/ttyUSB*` |
| `--baud` | `115200` | 波特率 |
| `--timeout` | `5.0` | 单个应答等待超时秒数 |
| `--retry` | `5` | 每块 NAK 最大重传次数 |

## 四、执行方法

### 4.1 上传 hex 到 Orin

把编译产物拷到 Orin 上（任选方式，如 `scp` / `ssh_exec.py`）：

```bash
scp MDK-ARM/output/F306_MCU_A_ACC_*.hex MDK-ARM/output/F306_MCU_B_ACC_*.hex orin@<Orin-IP>:~/f306/
```

### 4.2 升级 ACC 版

```bash
cd ~/f306
sudo python3 ota_send.py \
  --a F306_MCU_A_ACC_20260826_1800.hex \
  --b F306_MCU_B_ACC_20260826_1800.hex
```

### 4.3 升级非ACC 版

```bash
sudo python3 ota_send.py \
  --a F306_MCU_A_NOACC_20260826_1800.hex \
  --b F306_MCU_B_NOACC_20260826_1800.hex
```

### 4.4 指定串口 / 调参

```bash
sudo python3 ota_send.py --a A.hex --b B.hex \
  --port /dev/ttyACM1 --baud 115200 --timeout 5 --retry 5
```

### 4.5 查询当前固件版本（升级前确认现场变体）

```bash
echo "MCU_VER?" > /dev/ttyACM0   # 等待片刻，串口应回 MCU_VER: F306_MCU_A_ACC_V1.2_1
```

> `cat /dev/ttyACM0` 只收不发，不能用于发命令。

## 五、升级流程速览

1. 脚本打开串口 → 稳定延时 1s（规避 DTR/RTS 复位与 USB 枚举时序）。
2. 握手：发送 `OTA:START:F306OTA`，失败自动重试 3 次；MCU 回 `OTA:READY:<活动槽>:<目标槽>:<16384>`，脚本据此自动选择 `--a` 或 `--b` 对应的 hex。
3. `OTA:SIZE` → `OTA:ERASE` → 16 个 1024 字节分块发送（CRC16 校验，NAK 自动重传）→ `OTA:FINAL`（整片 CRC32）。
4. 回 `OTA:OK` 后**本次仍运行旧固件**，断电再上电由 Bootloader 切换新槽生效。

## 六、变体切换（ACC ↔ 非ACC）

客户机器出厂是某变体，需要现场整体切到另一变体（如 ACC → 非ACC）时，同样走 OTA，但**必须两趟 OTA + 中间断电**，理由：

- Bootloader / OTA 协议**不区分变体**，只认槽位与 CRC，任何一版固件（ACC 或非ACC）都能接收 OTA。
- 一次 OTA 只把新固件写入**非活动槽**（活动槽由当前运行固件经 VTOR 判定），因此一趟只能把一个槽切成新变体。
- 若只做一趟，两槽会变成「新变体活动 + 旧变体兜底」：新槽 CRC 校验失败时 Bootloader 会**静默回退到旧变体**，机器行为悄悄变回原样。

### 6.1 两趟 OTA 流程（以 ACC → 非ACC 为例）

```text
第 1 趟：当前运行 A(ACC)   → OTA 把非ACC 写入 B → 断电再上电 → B(非ACC) 生效
第 2 趟：当前运行 B(非ACC) → OTA 把非ACC 写入 A → 断电再上电 → A(非ACC) 生效
```

**第 1 趟**（目标槽 = B，脚本自动选 `--b`）：

```bash
sudo python3 ota_send.py \
  --a F306_MCU_A_NOACC_<时间戳>.hex \
  --b F306_MCU_B_NOACC_<时间戳>.hex
```

**断电再上电**（此步不能省：不重启的话第 2 趟仍从 A 运行，会再次写 B，A 永远切不过去）。

**第 2 趟**（此时活动槽已是 B，目标槽 = A，脚本自动选 `--a`）：

```bash
sudo python3 ota_send.py \
  --a F306_MCU_A_NOACC_<时间戳>.hex \
  --b F306_MCU_B_NOACC_<时间戳>.hex
```

再次断电再上电，两槽即全部为非ACC。**非ACC → ACC 同理**，把 hex 换成 ACC 版本即可。

### 6.2 切换后验证

```bash
echo "MCU_VER?" > /dev/ttyACM0   # 应回 MCU_VER: F306_MCU_A_NOACC_V1.2_1（变体一致即成功）
```

### 6.3 现场注意事项

- `--a` / `--b` 必须都传**目标变体**的 hex（上例全为 NOACC）；脚本只校验链接基址、**不校验变体**，传错不会报错，全靠人工核对。
- 两趟之间**必须断电再上电**，否则第二次仍写同一槽，达不到切换目的。
- 非ACC 版关机 = PA0/PA4 完全断电、恢复靠外部重新上电，且 PA1(ACC) 不再参与控制；切换前先与客户确认现场供电方式是否适配。

## 七、常见问题

| 现象 | 原因与处理 |
|------|-----------|
| `Permission denied` | 用户不在 dialout 组，见上文权限配置 |
| 首跑超时、第二次成功 | 属 DTR/RTS 复位 / USB 枚举时序问题，脚本已内置 1s 延时 + 3 次握手重试；仍复现再查 DTR 接线 |
| 报「hex 链接槽与目标槽不匹配」 | `--a/--b` 填错（如把 A 槽 hex 放 `--b`），或 hex 不是 F306_MCU 新命名产物 |
| 升级成功但上电没切新槽 | 新槽 CRC 校验失败被 Bootloader 回退，重新下发正确 hex |
| 双槽皆坏不开机 | 上电进入自救接收，直接用 `ota_send.py` 下发即可，无需烧录器 |

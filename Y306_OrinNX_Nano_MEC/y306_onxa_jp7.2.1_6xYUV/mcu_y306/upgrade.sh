#!/bin/bash
# Y306 MCU 固件 OTA 升级（一次只做一趟，两趟之间必须整机断电）
#
# 用法:
#   sudo bash upgrade.sh --variant noacc          # 自动选槽，做一趟
#   sudo bash upgrade.sh --variant noacc --check  # 只查版本
#
# 流程（两趟 + 两次断电）:
#   1) 本脚本第 1 趟  -> 写非活动槽
#   2) 整机断电再上电  -> 新槽生效
#   3) 本脚本第 2 趟  -> 写另一个槽
#   4) 整机断电再上电  -> 两槽同版本
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
VARIANT="noacc"
CHECK=0
PORT=/dev/ttyACM0

usage() {
    cat <<EOF
用法: sudo bash upgrade.sh --variant acc|noacc [--check] [--port DEV]

  --variant   acc = 带 ACC/IGN 开关机控制（客户整车点火信号）
              noacc = 无 ACC 控制（默认，Y306 现网配置）
  --check     只查询当前 MCU 版本，不做升级
  --port      串口设备，默认 $PORT

注意：一趟只能刷一个槽，两趟之间必须整机断电（12V 关掉等 5 秒再开）。
      SoM 重启不算，MCU 不会复位。
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --variant|-v) VARIANT="${2:-}"; shift 2 ;;
        --check) CHECK=1; shift ;;
        --port) PORT="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1"; usage; exit 1 ;;
    esac
done

case "$VARIANT" in
    acc)   FW_A="F306_MCU_A_ACC_V1.2.10.hex";   FW_B="F306_MCU_B_ACC_V1.2.10.hex" ;;
    noacc) FW_A="F306_MCU_A_NOACC_V1.2.10.hex"; FW_B="F306_MCU_B_NOACC_V1.2.10.hex" ;;
    *) usage; exit 1 ;;
esac
[ "$(id -u)" -eq 0 ] || { echo "请用 sudo 运行"; exit 1; }
[ -e "$PORT" ] || { echo "串口 $PORT 不存在（检查 USB 线/载板供电）"; exit 1; }

echo "===== 当前固件"
python3 "$HERE/tools/mcu_ver.py" --port "$PORT" || true
[ "$CHECK" = "1" ] && exit 0

echo
echo "===== 写入 $VARIANT 版 V1.2.10（目标槽由脚本按活动槽自动选择）"
python3 "$HERE/tools/ota_send.py" \
    --a "$HERE/firmware/$FW_A" \
    --b "$HERE/firmware/$FW_B" \
    --port "$PORT"

cat <<EOF

===== 本趟完成
新固件已写入**非活动槽**，当前仍运行旧固件。

请执行：
  1) 整机断电（12V 电源关掉，等 5 秒再上电）
  2) 上电后重新登录，再执行一次同样的命令：
       sudo bash $HERE/upgrade.sh --variant $VARIANT
  3) 再次整机断电上电

两趟 + 两次断电后，执行下面命令确认两个槽都是 V1.2.10：
  sudo bash $HERE/upgrade.sh --variant $VARIANT --check
EOF

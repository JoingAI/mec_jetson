#!/bin/sh
# 按顺序加载 335Lg（Orbbec GMSL）驱动；必须在 fzcam_cfg 之前完成
M=/lib/modules/$(uname -r)/updates/y306-obc
[ -d "$M" ] || exit 0
lsmod | grep -q '^obc_max9296'  || insmod "$M/obc_max9296.ko"  2>/dev/null
sleep 6
lsmod | grep -q '^obc_max96712' || insmod "$M/obc_max96712.ko" 2>/dev/null
sleep 2
lsmod | grep -q '^g300'         || insmod "$M/g300.ko"         2>/dev/null
exit 0

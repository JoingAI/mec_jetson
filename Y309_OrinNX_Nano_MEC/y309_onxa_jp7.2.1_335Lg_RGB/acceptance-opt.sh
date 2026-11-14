#!/bin/bash
# Y309 mixed v2 acceptance (option 1/2). Requires viewer or y309_335lg_cap for 335Lg.
set -u
HZ=${1:-20}; DUR=${2:-30}
echo "== Y309 mixed v2 acceptance: ${DUR}min @ ${HZ}Hz"
echo "1) MCU + 1PPS + trigger:"
python3 <mcu_y309>/y309ctl.py mode free; python3 <mcu_y309>/y309ctl.py set 20 10
sudo ./ptp_perout2 /dev/ptp0 0 1000000000
sudo env LD_LIBRARY_PATH=<viewer> ./tools/y309_orb_trigger
echo "2) boost: sudo ./serdes.script/boost.clk.sh"
echo "3) 335Lg (SDK): sudo env LD_LIBRARY_PATH=<viewer> ./tools/y309_335lg_cap $((DUR*60))"
echo "4) fzcam (v4l2): for n in 0 1 2 3: v4l2-ctl -d /dev/video\$n --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap --stream-to=/dev/null"
echo "5) count: dmesg | grep -c corr_err / uncorr_err / 'request timed out'"

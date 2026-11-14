# Y309 Mixed Camera Deployment Package v2.0.0 (1x Gemini 335Lg + 4x JoingAI ISX031F)

Target: Y309 carrier + Orin NX 16GB, JetPack 7.2.1 / L4T R39.2.1 (kernel 6.8.12-1021-tegra).

## Topology (v2: 335Lg on U7, ISX031F on U6)

| Node | Device | Location | Format |
|---|---|---|---|
| video0-3 | 4x ISX031F | U6 / i2c@3160000, CSI A, serial_a | UYVY 1920x1536 |
| video4 | 335Lg ir_r | U7 / i2c@3180000, CSI C, serial_c | GREY 848x480 |
| video5 | 335Lg ir_l | U7 | GREY 848x480 |
| video6 | 335Lg color | U7 | YUYV 1280x720 |
| video7 | 335Lg depth | U7 | Z16 1280x800 |

- 335Lg: kernel driver (`obc_max96712` + `g300`), DT nodes `g2m1@1b..1e`;
- 4x ISX031F: userspace `fzcam_cfg` + `fzcam.ko`, DT nodes `fzcam_3a..3d@3a..3d`;
- Trigger: unified **20 Hz / 10% duty** (one MCU FSYNC line to both MAX96724). 335Lg requires SDK HW trigger (`syncMode=0x40`).

## 1. Prerequisites

- JetPack 7.2.1 R39.2.1 flashed; MCU firmware flashed (`y309ctl.py ver`);
- 335Lg on **U7 (J3)**, 4x ISX031F on **U6 (J1/J2/J19/J20)**;
- OrbbecSDK `libOrbbecSDK.so` in the OrbbecViewer directory (`tools/y309_orb_trigger` / `tools/y309_335lg_cap` depend on it).

## 2. Install

```bash
tar xzf y309-mixed-2.0.0.tar.gz && cd y309-mixed-2.0.0
sudo ./install.sh
sudo reboot
```

`install.sh`: backup -> v2 dtbo + board dtbo -> camera chain + board modules (5G/CAN/SPI/audio/ethernet) ->
`/etc/fzcam_cfg.ini` (GMSL1=U6 `Video_1111`, GMSL2=U7 `Video_0000`) + `fzcam_cfg.service.d` (After 335Lg) ->
fixed `fzcam_cfg` (position=None skips PoC/MFP write) -> modules-load.d -> systemd services ->
`LABEL y309-mixed` + `DEFAULT` -> depmod + sync. **No re-flash.**

## 3. After every boot (lost on power cycle)

```bash
# 3.1 MCU trigger 20 Hz / 10% duty
cd <mcu_y309_dir>                 # e.g. /home/nvidia/y309_onxa_jp7.2.1_8xyuv/mcu_y309
sudo python3 y309ctl.py mode free
sudo python3 y309ctl.py set 20 10
sudo python3 y309ctl.py status    # expect en=1 m=free f=20 d=10

# 3.2 I210 1PPS (MCU needs a valid 1PPS to output PWM reliably)
sudo ./tools/ptp_perout2 /dev/ptp0 0 1000000000

# 3.3 335Lg HW trigger (lost on power cycle)
export LD_LIBRARY_PATH=<OrbbecViewer dir>:$LD_LIBRARY_PATH
sudo env LD_LIBRARY_PATH=$LD_LIBRARY_PATH /home/nvidia/y309_orb_trigger
# expect: syncMode=0x40 framesPerTrigger=1

# 3.4 Boost clocks before 8-stream concurrent (vi/isp/nvcsi max; EMC ramps to 3199M)
sudo ./serdes.script/boost.clk.sh
```

## 4. Acceptance (two ways)

**Option 1 (viewer + v4l2-ctl)**: open 335Lg's 4 streams in OrbbecViewer, and simultaneously
`v4l2-ctl -d /dev/video0..3 --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap`.

**Option 2 (SDK + v4l2-ctl)**:
```bash
sudo env LD_LIBRARY_PATH=<viewer dir> ./tools/y309_335lg_cap 1800   # 335Lg 30min, prints per-stream fps/frames
for n in 0 1 2 3; do v4l2-ctl -d /dev/video$n --set-fmt-video=width=1920,height=1536,pixelformat=UYVY --stream-mmap --stream-to=/dev/null; done
dmesg | grep -c corr_err; dmesg | grep -c uncorr_err; dmesg | grep -c 'request timed out'
```

Measured (v2.0.0): cold boot x3 pass; option1 30min `corr=0`; option2 30min `corr=2`
(335Lg 19.98-19.99 fps x 36000+ frames, ISX031F 20.01 fps); temperature 49-52 C.

> **Important**: do NOT use v4l2-ctl on the 335Lg for long runs - it triggers `err_data 256/512`
> (PIXEL_LONG/SHORT_LINE) or 0 frames. Long runs must go through OrbbecViewer or `y309_335lg_cap` (SDK).

## 5. Rollback

```bash
sudo bash /root/y309-mixed-backup/<stamp>/rollback.sh
# or: sudo ./rollback.sh  (DEFAULT -> JetsonIO) then reboot
```

## 6. Known limitations

- Re-run step 3 after every power cycle (MCU/1PPS/335Lg HW trigger are volatile);
- 335Lg's 4 streams are VC-separated (depth/color/ir_l/ir_r); SDK `Pipeline+Config+enableStream` opens all at once;
- Keep scripts under `/home/nvidia/` (not `/tmp`, cleared on reboot);
- 335Lg color occasionally logs `err_data 131072` (PD_CRC), ~2 entries per 30min, negligible.

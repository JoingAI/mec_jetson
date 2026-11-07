# Y306 Synced-Camera Kit (335Lg + RGB/YUV · hardware trigger + per-frame timestamps)

> Target: a **fresh Y306 system** (Orin NX 16GB, L4T R39.2.1, kernel `6.8.12-1021-tegra`)
> After installation you get: three camera combinations (profile a/b/c),
> hardware-trigger synchronization and per-frame absolute timestamps.

---

## 1. Profiles

| profile | MAX9296 (LinkA) | MAX96724 (LinkA) | video nodes |
|---|---|---|---|
| **a** | 2× RGB/YUV (ISX031F, fzcam) | 1× Gemini 335Lg (4 streams) | 6 |
| **b** | 1× Gemini 335Lg (4 streams) | 4× RGB/YUV (ISX031F, fzcam) | 8 |
| **c** | 1× Gemini 335Lg | 1× Gemini 335Lg | 8 |

Only one profile can be installed at a time. Re-install with the profile that
matches the wiring, then reboot.

## 2. Package layout

```
y306-sync-cam/
├── install.sh / uninstall.sh / verify.sh
├── extlinux-add.py                 # derives a new boot entry from JetsonIO
├── artifacts/
│   ├── dtbo/   three camera overlays (mixed-a/b/c)
│   ├── modules/ g300, obc_max9296, obc_max96712, obcam, fzcam,
│   │            tegra-camera.ko, y306_fsync_cap.ko
│   └── sdk/    libOrbbecSDK.so.2.7.6 + y306_orb_trigger
├── conf/       fzcam_cfg-*.ini per profile
├── systemd/    unit files + loader scripts
└── tools/      y306_frame_ts.py / fsync_read.py / mcu_freq.py / pair_frames.py
```

## 3. Install

```bash
tar xzf y306-sync-cam-v3.0.tar.gz
cd y306-sync-cam

sudo bash install.sh --profile a          # a / b / c to match the wiring
sudo reboot
sudo bash verify.sh                       # expect all PASS
```

Options:

- `--trigger-hz N` — hardware trigger rate, default **10** Hz
  (must be ≤ stream frame rate / 2)
- `--no-reboot` — skip the automatic reboot (the DT still needs one)

What the installer does:

1. installs the overlay as `/boot/tegra234-p3767-camera-p3768-y306-mixed-<profile>.dtbo`
2. installs 6 camera modules + `y306_fsync_cap.ko`, replaces `tegra-camera.ko`
   (original kept as `.orig`)
3. installs the Orbbec SDK runtime to `/opt/orbbec-sdk` and `y306_orb_trigger`
4. installs the systemd units `y306-obc-camera` (driver load) and
   `y306-orbbec-trigger` (MCU trigger rate + camera trigger mode)
5. writes `/etc/fzcam_cfg.ini` and `/etc/y306-sync.conf` for the profile
6. adds/updates `LABEL y306-mixed-<profile>` in `extlinux.conf` and makes it default
7. records `/etc/y306-sync-profile`, runs `depmod` and `sync`

> **No OrbbecViewer step is needed** — the SDK call runs as a boot service.

## 4. How sync and timestamps work

```
MCU STM32F103 (0xAA frame sets the rate, default 10 Hz)
      │ FSYNC (pin18)
      ▼
  AON PCC.00 ──┬── MAX9296  MFP0 ── coax ── ISX031F (RGB)
               └── MAX96724 MFP0 ── coax ── MAX9295D MFP6 ── Gemini 335Lg
               │
      GTE hardware-timestamps every rising edge (TSC domain, 32 ns) ──► /dev/y306_fsync
               │
      V4L2 frame timestamps (also TSC domain) ──► pair with nearest preceding edge
               ▼
      per frame: seq / frame TSC / trigger TSC / latency / UTC
```

Boot order is enforced by systemd:
`y306-obc-camera` (drivers) → `y306-orbbec-trigger` (MCU rate + camera trigger) → `fzcam_cfg` (RGB serdes)

Measured at 10 Hz, after a plain reboot with no manual step:

| device | FPS | latency p50 | spread |
|---|---|---|---|
| RGB `/dev/video0` | 9.999 | 18.81 ms | 0.035 ms |
| 335Lg `/dev/video5` | 9.999 | 35.67 ms | 0.003 ms |

## 4.0 Trigger source: MCU (default)

Y306 normally takes FSYNC from the carrier MCU; `/etc/y306-sync.conf` defaults to
`TRIGGER_SOURCE=mcu`. At boot the service sends
`0xAA 01 <freq*100> <duty> <cs> 0x55` for 10 Hz / 10 % and expects
`AA 02 00 0A 0A C0 55` back.

> **Two gotchas**
> 1. **MCU firmware must be >= V1.2_10.** V1.0 ignores the `0xAA` rate command and
>    never generates the trigger: the camera sits in triggering mode with zero
>    frames and `/dev/y306_fsync` shows no edges. Upgrade procedure:
>    `../../cases/CASE-20261107-y306-mcu-firmware-upgrade.md`.
> 2. **Opening the serial port resets the MCU via DTR.** Wait ~1.6 s before sending
>    or the frame is silently dropped (`y306_mcu_freq.py` already does this, with retries).

### 4.0.1 Debug units without an MCU (`soc`)

`/etc/y306-sync.conf: TRIGGER_SOURCE` selects the source:

| value | behaviour |
|---|---|
| `mcu` (**default**, Y306 product config) | MCU on the carrier generates the trigger; the boot service sends the 10 Hz command |
| `soc` | SoC generates the trigger (debug units without an MCU only) |
| `auto` | probe at boot: MCU if present, otherwise fall back to the SoC |

In SoC mode `y306_fsync_cap` is loaded with `gen_hz=10`: an hrtimer toggles
AON PCC.00, which is the same FSYNC net the MCU drives. HTE still timestamps
every rising edge, so **the timestamp path is unchanged**.

Measured on a machine without an MCU at 10 Hz:

```
video0 10.0000 fps   video4 10.0014 fps
latency 35.741 ms  spread 0.001 ms
```

> The camera finishes its own boot later than the systemd unit, so a single set
> may not stick; the package ships `y306-orbbec-trigger-late.timer`, which
> re-applies the setting 40 s after boot.

## 4.1 Using 1 / 2 / 3 cameras (important)

`position=Video_ABCD` in `fzcam_cfg.ini` is a **port mask** (ports A/B/C/D), not a
camera count. **Always use `Video_1111`** — the tool detects which links are
actually locked and configures only those.

The dtsi shipped in this package lists the same-model sensor nodes in descending
address order, so `video0` maps to Link A:

| port | i2c | video node |
|---|---|---|
| Link A | 0x3a | `/dev/video3` |
| Link B | 0x3b | `/dev/video2` |
| Link C | 0x3c | `/dev/video1` |
| Link D | 0x3d | `/dev/video0` |

(If you modify the dtsi yourself, keep that node ordering — reversing it makes
`video0` point at Link D.)

| cameras connected | nodes with video | nodes without |
|---|---|---|
| 1 (A) | video3 | video0-2 |
| 2 (A,B) | video2, video3 | video0, video1 |
| 3 (A,B,C) | video1, video2, video3 | video0 |
| 4 | video0-3 | — |

**Never assume `video0..N-1` are the first N cameras** — with 1/2/3 cameras most
of those nodes carry no data. Select nodes by camera address instead:

```bash
sudo /usr/local/bin/y306_list_cams.py --probe
# video1  RGB    0x3c   Link C   10.00 fps
# video2  RGB    0x3b   Link B   10.00 fps
# video3  RGB    0x3a   Link A   10.00 fps
```

The node name also carries the address, so mapping by name is trivial:

```bash
cat /sys/class/video4linux/video1/name     # vi-output, fzcam 2-003c -> Link C
```

> If OrbbecViewer is running it owns the 335Lg nodes, so the reported fps may be
> distorted or show "no signal".

## 4.2 MCU firmware (trigger source)

The sync trigger comes from the carrier's STM32F103; the **firmware must be >= V1.2_10**
(older versions ignore the rate command and generate no trigger).

```bash
sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc --check   # version
sudo bash /opt/y306-sync/mcu/upgrade.sh --variant noacc           # upgrade (2 passes + 2 power cycles)
sudo python3 /opt/y306-sync/mcu/tools/mcu_freq.py 10 10           # set 10 Hz / 10 %
```

Full details (variant choice, A/B slots, protocol table, troubleshooting):
**`mcu/README-EN.md`**.

## 5. Reading timestamps

```bash
sudo /usr/local/bin/y306_frame_ts.py --dev /dev/video5 --duration 10 --out /tmp/f5.csv
sudo /usr/local/bin/y306_frame_ts.py --dev /dev/video0 --duration 10 --out /tmp/rgb.csv

sudo /usr/local/bin/y306_fsync_read.py 4        # trigger edge rate
sudo /usr/local/bin/pair_frames.py /dev/video5 10   # M7 check
sudo /usr/local/bin/y306_mcu_freq.py 10 10          # change trigger rate
```

CSV columns:

```
seq,frame_tsc_s,trigger_tsc_s,latency_ms,outlier,relock,utc
1,309.947918,309.929124,18.794,0,0,2026-11-04T14:50:43.000Z
```

- `frame_tsc_s` / `trigger_tsc_s` — **TSC domain** (not CLOCK_MONOTONIC)
- `latency_ms` — frame delay relative to its trigger edge
- `outlier` — deviates more than 5 ms from the expected latency, excluded from stats
- `relock` — first frame after a phase re-lock
- `utc` — `trigger_ktime + (CLOCK_REALTIME − CLOCK_MONOTONIC)`

The tool has robust pairing built in: outlier filtering, phase re-lock detection
and per-segment statistics (`--selftest` runs offline).

## 6. Verify

```bash
sudo bash verify.sh        # 60 frames per device
sudo bash verify.sh 300    # longer run
```

Checks: DT applied, trigger service, FSYNC edge rate, node count, per-node capture
and frame size, `corr_err/uncorr_err`, **frame period vs trigger period**, and the
timestamp CSV.

Expected frame sizes: 335Lg depth/color `2048000`, IR `1024000`;
ISX031F `5898240` (1920×1536 UYVY).

## 7. Rollback

```bash
sudo bash uninstall.sh
sudo reboot
```

Removes services/modules/dtbo/SDK, restores `tegra-camera.ko.orig` and points the
default boot entry back to `JetsonIO`.

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| no video nodes at all | overlay not applied (unresolved labels / space after comma in OVERLAYS) | check `grep ^DEFAULT /boot/extlinux/extlinux.conf`; validate the dtbo with `fdtoverlay` |
| 335Lg silent, `uncorr_err` timeouts | camera in trigger mode but no trigger arriving | ensure `fsync_mfp_index = <0>`; read `i2c 0x27 0x0300` (expect `0x83`) |
| frame rate does not match the trigger | trigger rate > frame rate / 2 | lower to ≤ frame rate / 2 (30 fps stream → ≤15 Hz) |
| RGB frames flagged `(error)`, `--stream-to` writes 0 bytes | RGB running in 4K mode | `v4l2-ctl --set-fmt-video=width=1920,height=1536,pixelformat=UYVY` |
| 335Lg not synced after reboot | trigger setting lost | `y306-orbbec-trigger.service` restores it; check its status |
| inter-camera offset changed | phase re-lock (common after rate change/reboot) | re-calibrate using the `relock` events from `y306_frame_ts.py` |

## 9. Known limitations

- The 335Lg hardware-trigger mode only holds while the boot service is active;
  stopping `y306-orbbec-trigger` returns the camera to free-run.
- The latency offset between the two cameras re-locks when the trigger rate
  changes (measured 1.1 ms ↔ 16.9 ms); re-calibrate afterwards.
- One phase re-lock was observed during an 8 h soak (RGB latency shifted by
  ~18 ms, spread unchanged); the tool reports it as a `relock` event.
- This kit covers capture, synchronization and timestamps only; LiDAR PTP
  alignment is out of scope.

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

### 3.1 Pre-Install

Download the package: y306_onxa_jp7.2.1_6xYUV from github
```
cd y306_onxa_jp7.2.1_6xYUV
sudo bash y306.upgrade.jp7.2.1_r39.2.1.sh

#Do not need to reboot after upgrade
```

### 3.2 Install
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
     MCU (0xAA frame sets the rate, default 10 Hz)
      │ FSYNC (pin18)
      ▼
   Jetson IO  ──┬── MAX9296  MFP0 ── coax ── ISX031 (RGB)
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

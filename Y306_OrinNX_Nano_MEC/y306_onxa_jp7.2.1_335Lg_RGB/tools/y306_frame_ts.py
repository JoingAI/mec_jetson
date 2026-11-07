#!/usr/bin/env python3
"""Y306 每帧绝对时间戳（鲁棒版 v2）

新增：
  1) 离群过滤：以"期望延迟"为参考，在相邻 3 个边沿里挑最合理的，
     偏离 > --outlier-tol 的帧标 outlier，不参与统计、不更新参考
  2) 相位重锁检测：连续 --relock-frames 帧都偏离 > --relock-tol 时，
     判定重锁，记录事件并把期望延迟重置到新值

自测（不需要硬件）：sudo python3 y306_frame_ts.py --selftest
"""
import os, fcntl, struct, subprocess, sys, time, re, bisect, argparse
from datetime import datetime, timezone
from statistics import median

SLOT = struct.Struct("<QQiIQ")
HDR = struct.Struct("<II")
SIZE = HDR.size + SLOT.size * 32
GET_BATCH = (3 << 30) | (SIZE << 16) | (ord('Y') << 8) | 1


def process(frames, edges, outlier_tol_ms=5.0, relock_tol_ms=5.0,
            relock_frames=5, window=30):
    """核心：帧↔边沿配对 + 离群过滤 + 重锁检测

    frames: [(seq, tsc_ns)]
    edges:  [(tsc_ns, ktime_ns)]
    返回 dict(rows, outliers, relocks, period, stats)
    """
    etsc = sorted({e[0] for e in edges})
    ektime = {e[0]: e[1] for e in edges}
    if len(etsc) < 4 or not frames:
        return None
    diffs = sorted(etsc[i + 1] - etsc[i] for i in range(len(etsc) - 1))
    period = median(diffs)

    def match(fts, l_ref):
        k = bisect.bisect_left(etsc, fts) - 1
        best = None
        for idx in (k - 1, k, k + 1):
            if 0 <= idx < len(etsc):
                lat = fts - etsc[idx]
                if period and abs(lat) > 2 * period:
                    continue
                score = abs(lat - l_ref)
                if best is None or score < best[2]:
                    best = (idx, lat, score)
        return None if best is None else (best[0], best[1])

    init = []
    for _, fts in frames[:min(10, len(frames))]:
        k = bisect.bisect_left(etsc, fts) - 1
        if k >= 0:
            init.append(fts - etsc[k])
    l_ref = median(init) if init else 0

    rows, outliers, relocks = [], 0, []
    recent, pending = [], []
    for seq, fts in frames:
        m = match(fts, l_ref)
        if not m:
            outliers += 1
            rows.append({"seq": seq, "fts": fts, "ets": None, "lat": None,
                         "outlier": True, "relock": False})
            continue
        idx, lat = m
        relock = False
        if abs(lat - l_ref) > outlier_tol_ms * 1e6:
            pending.append(lat)
            if len(pending) >= relock_frames:
                cand = median(pending)
                if abs(cand - l_ref) > relock_tol_ms * 1e6:
                    relock = True
                    relocks.append({"seq": seq, "old_ms": l_ref / 1e6,
                                    "new_ms": cand / 1e6, "ets": etsc[idx]})
                    l_ref = cand
                    recent.clear()
                pending.clear()
            if not relock:
                outliers += 1
                rows.append({"seq": seq, "fts": fts, "ets": etsc[idx], "lat": lat,
                             "outlier": True, "relock": False})
                continue
        else:
            pending.clear()
        recent.append(lat)
        if len(recent) > window:
            recent.pop(0)
        l_ref = median(recent)
        rows.append({"seq": seq, "fts": fts, "ets": etsc[idx], "lat": lat,
                     "outlier": False, "relock": relock})

    # 按重锁事件切段，每段单独统计（跨相位直接算 spread 会失真）
    segments, cur = [], []
    for r in rows:
        if r["relock"] and cur:
            segments.append(cur); cur = []
        cur.append(r)
    if cur:
        segments.append(cur)

    def seg_stats(rows_):
        g = sorted(r["lat"] / 1e6 for r in rows_ if r["lat"] is not None and not r["outlier"])
        if not g:
            return None
        pq = lambda q: g[min(len(g) - 1, int(len(g) * q))]
        return {"n": len(g), "p5": pq(.05), "p50": pq(.5), "p95": pq(.95),
                "spread": pq(.95) - pq(.05), "min": g[0], "max": g[-1]}

    good = sorted(r["lat"] / 1e6 for r in rows if r["lat"] is not None and not r["outlier"])
    def pq(q):
        return good[min(len(good) - 1, int(len(good) * q))] if good else None
    return {
        "rows": rows, "outliers": outliers, "relocks": relocks, "period": period,
        "segments": [seg_stats(sg) for sg in segments],
        "stats": {"n": len(frames), "good": len(good),
                  "p5": pq(.05), "p50": pq(.5), "p95": pq(.95),
                  "spread": (pq(.95) - pq(.05)) if good else None},
        "ektime": ektime,
    }


def selftest():
    P = 100_000_000           # 100 ms
    E0 = 1_000_000_000_000
    edges = [(E0 + i * P, E0 + i * P + 5_000_000) for i in range(200)]
    frames = []
    relock_at = 60
    for i in range(150):
        lat = (35.0 if i < relock_at else 18.0) * 1e6
        fts = E0 + i * P + int(lat)
        frames.append((i, fts))
    # 注入 3 个离群帧（落在边沿前 1 ms → 朴素配对会多算 100 ms）
    for k, i in enumerate([20, 80, 120]):
        frames[i] = (i, E0 + i * P - 1_000_000 + k)   # 边沿前 1ms
    frames.sort(key=lambda x: x[1])
    r = process(frames, edges)
    print("selftest: 帧=%d 周期=%.1f ms" % (r["stats"]["n"], r["period"] / 1e6))
    print("  good=%d outlier=%d 重锁=%d" % (r["stats"]["good"], r["outliers"], len(r["relocks"])))
    print("  延迟 p50=%.3f ms spread=%.3f ms" % (r["stats"]["p50"], r["stats"]["spread"]))
    for e in r["relocks"]:
        print("  RELOCK seq=%d  %.2f -> %.2f ms" % (e["seq"], e["old_ms"], e["new_ms"]))
    for i, sg in enumerate(r["segments"]):
        if sg:
            print("  段%d: n=%d p50=%.3f spread=%.3f" % (i, sg["n"], sg["p50"], sg["spread"]))
    ok = True
    # 3 个注入离群 + 确认重锁期间的 (relock_frames-1) 帧
    if not (3 <= r["outliers"] <= 3 + 4):
        print("  FAIL: outlier 应有 3~7 个，实际 %d" % r["outliers"]); ok = False
    if len(r["relocks"]) != 1:
        print("  FAIL: 期望 1 次重锁，实际 %d" % len(r["relocks"])); ok = False
    elif abs(r["relocks"][0]["new_ms"] - 18.0) > 1.0:
        print("  FAIL: 重锁后延迟应 ≈18 ms，实际 %.2f" % r["relocks"][0]["new_ms"]); ok = False
    segs = [x for x in r["segments"] if x]
    if len(segs) < 2:
        print("  FAIL: 应至少分成 2 段"); ok = False
    else:
        if abs(segs[0]["p50"] - 35.0) > 1.0:
            print("  FAIL: 段0 p50 应 ≈35 ms，实际 %.2f" % segs[0]["p50"]); ok = False
        if abs(segs[-1]["p50"] - 18.0) > 1.0:
            print("  FAIL: 段1 p50 应 ≈18 ms，实际 %.2f" % segs[-1]["p50"]); ok = False
        if segs[0]["spread"] > 1.0:
            print("  FAIL: 段0 spread 应 <1 ms，实际 %.3f" % segs[0]["spread"]); ok = False
    print("  RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def capture(dev, duration):
    proc = subprocess.Popen(["v4l2-ctl", "-d", dev, "--stream-mmap", "--verbose"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    fd = os.open("/dev/y306_fsync", os.O_RDWR)
    buf = bytearray(SIZE)
    edges = []
    end = time.time() + duration
    while time.time() < end:
        fcntl.ioctl(fd, GET_BATCH, buf, True)
        cnt, _ = HDR.unpack_from(buf, 0)
        off = HDR.size
        for i in range(cnt):
            e = SLOT.unpack_from(buf, off + i * SLOT.size)
            if e[3] & 1:
                edges.append((e[0], e[4]))
        time.sleep(0.005)
    rt = time.time_ns(); mono = time.monotonic_ns()
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=3)
    except Exception:
        proc.kill(); out = ""
    os.close(fd)
    frames = []
    for line in out.splitlines():
        m = re.search(r'seq:\s*(\d+).*?ts:\s*([0-9.]+)', line)
        if m:
            t = float(m.group(2))
            if t > 0:
                frames.append((int(m.group(1)), t * 1e9))
    return frames, edges, rt - mono


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/video5")
    ap.add_argument("--duration", type=float, default=5.0)
    ap.add_argument("--out", default="/tmp/y306_frames.csv")
    ap.add_argument("--outlier-tol", type=float, default=5.0)
    ap.add_argument("--relock-tol", type=float, default=5.0)
    ap.add_argument("--relock-frames", type=int, default=5)
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    frames, edges, rt_off = capture(a.dev, a.duration)
    r = process(frames, edges, a.outlier_tol, a.relock_tol, a.relock_frames, a.window)
    if not r:
        print("数据不足 frames=%d edges=%d" % (len(frames), len(edges)))
        return 1
    with open(a.out, "w") as f:
        f.write("seq,frame_tsc_s,trigger_tsc_s,latency_ms,outlier,relock,utc\n")
        for row in r["rows"]:
            if row["ets"] is None:
                f.write("%d,%.9f,,,1,0,\n" % (row["seq"], row["fts"] / 1e9))
                continue
            utc = datetime.fromtimestamp((r["ektime"][row["ets"]] + rt_off) / 1e9, timezone.utc)
            f.write("%d,%.9f,%.9f,%.3f,%d,%d,%s\n" % (
                row["seq"], row["fts"] / 1e9, row["ets"] / 1e9, row["lat"] / 1e6,
                1 if row["outlier"] else 0, 1 if row["relock"] else 0,
                utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"))
    s = r["stats"]
    print("dev=%s 帧=%d 边沿=%d 周期=%.3f ms" % (a.dev, s["n"], len(r["ektime"]), r["period"] / 1e6))
    print("延迟(剔除 outlier) ms: p5=%.3f p50=%.3f p95=%.3f spread=%.3f" %
          (s["p5"], s["p50"], s["p95"], s["spread"]))
    print("outlier=%d  重锁事件=%d" % (r["outliers"], len(r["relocks"])))
    for i, sg in enumerate(r["segments"]):
        if sg:
            print("  段%d: n=%d  延迟 p50=%.3f ms  spread=%.3f ms (min %.3f / max %.3f)"
                  % (i, sg["n"], sg["p50"], sg["spread"], sg["min"], sg["max"]))
    for e in r["relocks"]:
        print("  RELOCK seq=%d  %.2f ms -> %.2f ms" % (e["seq"], e["old_ms"], e["new_ms"]))
    print("CSV: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

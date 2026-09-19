from .. import geodesy

VNE_KIAS = 163.0          # c172p；换机型必须重查（doc3 §3.4 勘误）
THRESHOLD = {
    "soar":  (100000.0, 10.0),   # 气压高度 > 100,000 ft，≥10s
    "dig":   (-300.0,   10.0),   # AGL < -300 ft，≥10s
    "speed": (3.0,      15.0),   # 空速 > 3×VNE，≥15s
}
MAX_ACCEL_G = 50.0


def _best_run(rows, pred):
    """返回满足条件的最长连续下标段。"""
    runs, cur = [], []
    for i, r in enumerate(rows):
        if pred(r):
            cur.append(i)
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return max(runs, key=len) if runs else []


MAX_GROUND_V_MS = 3500.0  # 地速物理上限（≈Mach10），超过即视为瞬移


def _smooth(rows, idxs, max_accel_g=MAX_ACCEL_G):
    """平滑性：相邻帧差分地速 → 相邻帧加速度 ≤ 50g，且地速 ≤ 物理上限。
    （doc3 §3.4 的 is_smooth 只比"与上帧速度差"；这里补一个地速上限，
    防正负对称的瞬移——它差分速度恒定但物理上不可能。）"""
    prev_v = None
    for a, b in zip(idxs, idxs[1:]):
        ra, rb = rows[a], rows[b]
        dt = rb.ts - ra.ts
        if dt <= 0:
            return False
        v = geodesy.haversine_m(ra.lat, ra.lon, rb.lat, rb.lon) / dt
        if v > MAX_GROUND_V_MS:
            return False
        if prev_v is not None and abs(v - prev_v) / dt > max_accel_g * 9.81:
            return False
        prev_v = v
    return True


def judge_flag3(rows, vne_kias=VNE_KIAS):
    out = {"checkpoints": {}, "score": 0.0, "verdict": "FAIL", "evidence": {}}
    if len(rows) < 2:
        return out

    runs = {
        "soar": _best_run(rows, lambda r: (r.alt_ft or 0.0) > THRESHOLD["soar"][0]),
        "dig": _best_run(rows, lambda r: (r.agl_ft or 0.0) < THRESHOLD["dig"][0]),
        "speed": _best_run(
            rows, lambda r: (r.vcas_kt or 0.0) > THRESHOLD["speed"][0] * vne_kias),
    }
    n = 0
    for name, idxs in runs.items():
        need = THRESHOLD[name][1]
        dur = (rows[idxs[-1]].ts - rows[idxs[0]].ts) if idxs else 0.0
        smooth = _smooth(rows, idxs) if idxs else False
        ok = bool(idxs) and dur >= need and smooth
        out["checkpoints"][name] = {
            "ok": ok, "duration_s": round(dur, 2), "smooth": smooth,
            "samples": len(idxs)}
        n += 1 if ok else 0

    out["score"] = 40.0 if n == 3 else (15.0 if n >= 2 else 0.0)
    out["verdict"] = "PASS" if out["score"] > 0 else "FAIL"
    return out

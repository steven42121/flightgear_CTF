# Flag2: 物理不可能状态判定（原flag3）
#
# 绕过反作弊实现以下三种状态之一：
# 1. 飞天：气压高度 > 100,000 ft，持续 >= 10s
# 2. 遁地：AGL < -300 ft，持续 >= 10s
# 3. 超速：空速 > 3xVNE，持续 >= 15s
#
# 要求状态连续平滑（防瞬移刷分）

import math
from typing import List, Dict
from .. import geodesy

VNE_KIAS = 163.0
THRESHOLD = {
    'soar': (100000.0, 10.0),
    'dig': (-300.0, 10.0),
    'speed': (3.0, 15.0),
}
MAX_ACCEL_G = 50.0
MAX_GROUND_V_MS = 3500.0


def _best_run(rows, pred):
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


def _smooth(rows, idxs, max_accel_g=MAX_ACCEL_G):
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


def judge_flag2(rows: List, cfg: Dict) -> Dict:
    vne_kias = cfg.get('vne_kias', VNE_KIAS)
    hb_last_ts = cfg.get('hb_last_ts', 0.0)
    hb_grace_s = cfg.get('hb_grace_s', 5)
    out = {
        'total': 0.0, 'checkpoints': {}, 'verdict': 'FAIL', 'evidence': {},
        'heartbeat_ok': False,
    }
    if len(rows) < 2:
        return out

    # --- 心跳门控：必须全程有心跳 ---
    last_row_ts = rows[-1].ts
    hb_ok = (hb_last_ts > 0) and (last_row_ts - hb_last_ts <= hb_grace_s)
    out['heartbeat_ok'] = hb_ok
    out['evidence']['hb_last_ts'] = hb_last_ts
    out['evidence']['hb_grace_s'] = hb_grace_s
    out['evidence']['last_row_ts'] = last_row_ts

    if not hb_ok:
        out['verdict'] = 'FAIL (no heartbeat)'
        return out
    runs = {
        'soar': _best_run(rows, lambda r: (r.alt_ft or 0.0) > THRESHOLD['soar'][0]),
        'dig': _best_run(rows, lambda r: (r.agl_ft or 0.0) < THRESHOLD['dig'][0]),
        'speed': _best_run(rows, lambda r: (r.vcas_kt or 0.0) > THRESHOLD['speed'][0] * vne_kias),
    }
    n = 0
    for name, idxs in runs.items():
        need_dur = THRESHOLD[name][1]
        dur = (rows[idxs[-1]].ts - rows[idxs[0]].ts) if idxs else 0.0
        smooth = _smooth(rows, idxs) if idxs else False
        ok = bool(idxs) and dur >= need_dur and smooth
        out['checkpoints'][name] = {'ok': ok, 'duration_s': round(dur, 2), 'smooth': smooth, 'samples': len(idxs)}
        if ok:
            n += 1
    if n == 3:
        out['total'] = 100.0
    elif n == 2:
        out['total'] = 50.0
    elif n == 1:
        out['total'] = 20.0
    out['verdict'] = 'PASS' if out['total'] > 0 else 'FAIL'
    out['evidence'] = {'vne_kias': vne_kias, 'thresholds': {k: list(v) for k, v in THRESHOLD.items()}}
    return out
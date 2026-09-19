from .. import geodesy


def judge_flag2(rows, target, radius_m=2000.0, ceil_ft=8000.0, dur_s=10.0,
                max_gap_s=0.5, move_away_min_m=500.0):
    """doc3 §2.4 触发判定（勘误后版本）：
    - 半径内 + 低于上限 + 持续 ≥ dur_s（允许 ≤max_gap_s 的采包抖动，但整段不得中断）；
    - 触发后 3s 必须离开 ≥ move_away_min_m（防"擦边悬停"骗持续时长）。
    返回 (ok, evidence)。
    """
    ev = {"closest_m": None}
    if len(rows) < 2:
        return False, ev
    dists = [geodesy.haversine_m(r.lat, r.lon, target[0], target[1]) for r in rows]
    i_min = min(range(len(rows)), key=lambda i: dists[i])
    ev["closest_m"] = round(dists[i_min], 1)

    inside = [i for i, d in enumerate(dists)
              if d <= radius_m and (rows[i].alt_ft or 0.0) <= ceil_ft]
    if not inside:
        return False, ev

    # 连续簇：允许小空洞（UDP 丢包），不允许长空洞（瞬移擦边）
    clusters = []
    cur = [inside[0]]
    for i in inside[1:]:
        if rows[i].ts - rows[cur[-1]].ts <= max_gap_s + 1.0 / 10.0:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)

    best = max(clusters, key=lambda c: rows[c[-1]].ts - rows[c[0]].ts)
    span = rows[best[-1]].ts - rows[best[0]].ts
    ev["best_span_s"] = round(span, 2)
    ev["clusters"] = len(clusters)
    if span < dur_s:
        return False, ev

    i_end = best[-1]
    i_later = None
    for i in range(i_end + 1, len(rows)):
        if rows[i].ts - rows[i_end].ts >= 3.0:
            i_later = i
            break
    if i_later is not None:
        ev["away_after_3s_m"] = round(dists[i_later], 1)
        if dists[i_later] < move_away_min_m:
            return False, ev
    return True, ev

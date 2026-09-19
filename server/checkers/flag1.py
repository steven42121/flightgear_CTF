import math

from .. import geodesy


def _gs_dev_norm(row, cfg):
    """下滑道指针归一化偏差：-1..1，满刻度按 gs_full_scale_deg（默认 0.7°）。"""
    d = geodesy.haversine_m(row.lat, row.lon, cfg["thr_lat"], cfg["thr_lon"])
    if d < 1.0:
        d = 1.0
    glide_ft = cfg["thr_alt_ft"] + d * math.tan(math.radians(3.0)) / geodesy.M_FT
    dev_deg = math.degrees(math.atan2((row.alt_ft or 0.0) - glide_ft, d))
    full = cfg.get("gs_full_scale_deg", 0.7)
    return max(-1.0, min(1.0, dev_deg / full))


def _lateral_offset_m(row, cfg):
    return geodesy.cross_track_m(cfg["thr_lat"], cfg["thr_lon"],
                                 cfg["course_deg"], row.lat, row.lon)


def judge_flag1(rows, cfg):
    """doc3 §1.3 判据（勘误后版本）：
      1) 稳定进近：10nm 内 |指针| < 0.3 的时间占比 ≥ 0.90 → 25 分
      2) 决断高度前不得大幅偏离（<30ft 的帧不计）         → 25 分
      3) 接地品质：VS/坡度/横向偏差 + 无弹跳              → 落地 20 + 品质 30
      满分 100 = 稳定25 + 决断25 + 落地20 + 品质30
    """
    res = {"flag": 1, "land": 0.0, "approach": 0.0, "touch": 0.0,
           "total": 0.0, "verdict": "FAIL", "evidence": {}}
    ev = res["evidence"]
    if len(rows) < 10:
        res["verdict"] = "NO_DATA"
        return res

    # 接地帧 = 最后一次 wow 0→1 转换（一场可能触多次，判最后一次）
    td = None
    for i in range(1, len(rows)):
        if (rows[i].wow and not rows[i - 1].wow
                and (rows[i].agl_ft or 0.0) < 3.0):
            td = i

    # 进近段：从接地往回找最后一个 >12nm 的位置作为进近入口。
    # 这样能正确处理多段轨迹（如 walk/arc/ils/speed），只取最终进近段。
    thr = (cfg["thr_lat"], cfg["thr_lon"])
    dists = [geodesy.haversine_m(r.lat, r.lon, thr[0], thr[1]) for r in rows]
    end = td if td is not None else len(rows) - 1
    entry = 0
    for i in range(end, -1, -1):
        if dists[i] > cfg["gs_dist_start_m"] * 1.2:
            entry = i
            break
    seg = [rows[i] for i in range(entry, end + 1)
           if dists[i] <= cfg["gs_dist_start_m"]]
    if not seg:
        ev["note"] = "未检测到 10nm 内的进近下降段"
        return res

    stable = sum(1 for r in seg if abs(_gs_dev_norm(r, cfg)) < cfg["gs_stable_norm"]) / len(seg)
    ev["stable_ratio"] = round(stable, 4)
    res["approach"] += 25.0 * (stable >= cfg["stable_ratio_min"])

    dec = [r for r in seg
           if cfg["dec_min_agl_ft"] < (r.agl_ft if r.agl_ft is not None else 1e9) < cfg["dec_alt_ft"]]
    unstable = any(abs(_gs_dev_norm(r, cfg)) > cfg["unstable_norm"] for r in dec)
    ev["unstable_below_da"] = bool(unstable)
    if not unstable:
        res["approach"] += 25.0

    t = rows[td]
    vs = t.vs_fps if t.vs_fps is not None else 0.0
    vs_ok = abs(vs) <= cfg["vs_tol_fps"]
    roll_ok = abs(t.roll or 0.0) <= cfg["roll_tol_deg"]
    lat_off = _lateral_offset_m(t, cfg)
    lat_ok = abs(lat_off) <= cfg["lateral_tol_m"]

    bounce = False
    for r in rows[td + 1:]:
        if r.ts - t.ts > cfg["bounce_window_s"]:
            break
        if (r.agl_ft or 0.0) > cfg["bounce_agl_ft"]:
            bounce = True
            break

    ev.update({"touchdown_vs_fps": round(vs, 2),
               "touchdown_roll_deg": round(t.roll or 0.0, 2),
               "touchdown_lat_off_m": round(lat_off, 2),
               "bounce": bounce})
    # 落地分：20分基础分（成功接地即得） + 30分品质分（VS/坡度/偏置/弹跳）
    res["land"] = 20.0  # 成功落地得基础分
    res["touch"] = 30.0 * (vs_ok and roll_ok and lat_ok and not bounce)
    res["total"] = res["land"] + res["approach"] + res["touch"]  # 最高 100（land+touch=50, approach=50）
    res["verdict"] = "PASS" if res["total"] > 0 else "FAIL"
    return res

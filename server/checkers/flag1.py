"""Flag1: 起飞并到达指定目标点（上科大）

新流程：
1. 选手从机场起飞
2. 飞往目标坐标（上科大 31.177°N, 121.596°E）
3. 在目标点半径内停留足够时间
4. 服务器下发ATC语音（含加密flag key）
5. 选手解密后输入到web界面获得flag
"""
import math
import base64
import os
from typing import List, Dict

from .. import geodesy

# 固定的 flag key（通过 ATC 语音的摩斯密码部分解码得到）
FLAG_KEY = "LETS_FLY_TO_THE_SKY_THANK_YOU_FOR_FLYING"
ATC_AUDIO_PATH = os.path.join(os.path.dirname(__file__), "..", "atc_full.wav")


def judge_flag1(rows: List, cfg: Dict) -> Dict:
    """
    判定是否到达目标点并下发ATC语音
    
    参数:
        rows: 轨迹数据列表
        cfg: 配置字典，包含 target_lat, target_lon, radius_m, ceil_ft, dur_s 等
    
    返回:
        dict: {
            'total': float,  # 得分（0或100）
            'reached': bool,  # 是否已到达
            'atc_audio': str, # base64编码的ATC语音（首次到达时下发）
            'evidence': dict  # 证据数据
        }
    """
    res = {
        "total": 0.0,
        "reached": False,
        "atc_audio": None,
        "evidence": {}
    }
    
    if len(rows) < 2:
        return res
    
    target_lat = cfg.get("target_lat", 31.1770)
    target_lon = cfg.get("target_lon", 121.5960)
    radius_m = cfg.get("radius_m", 500.0)
    ceil_ft = cfg.get("ceil_ft", 1000.0)
    dur_s = cfg.get("dur_s", 5.0)
    
    # 计算每个点到目标的距离
    dists = []
    for r in rows:
        d = geodesy.haversine_m(r.lat, r.lon, target_lat, target_lon)
        dists.append(d)
    
    # 找出在半径内且高度合适的点
    valid_points = [
        i for i, d in enumerate(dists)
        if d <= radius_m and (rows[i].alt_ft or 0) <= ceil_ft
    ]
    
    if not valid_points:
        res["evidence"]["closest_m"] = round(min(dists), 1) if dists else None
        res["evidence"]["note"] = "未接近目标点"
        return res
    
    # 检查是否有连续 dur_s 的时间在目标区域内
    continuous_time = 0.0
    max_continuous_time = 0.0
    last_idx = None
    segment_start = None
    
    for idx in valid_points:
        if last_idx is not None and (rows[idx].ts - rows[last_idx].ts) <= 1.0:
            # 连续帧
            if segment_start is None:
                segment_start = idx
            continuous_time = rows[idx].ts - rows[segment_start].ts
        else:
            # 重置
            max_continuous_time = max(max_continuous_time, continuous_time)
            segment_start = idx
            continuous_time = 0.0
        last_idx = idx
    
    max_continuous_time = max(max_continuous_time, continuous_time)
    
    reached = max_continuous_time >= dur_s
    res["evidence"]["closest_m"] = round(min(dists), 1)
    res["evidence"]["max_stay_s"] = round(max_continuous_time, 2)
    res["evidence"]["reached"] = reached
    
    if reached:
        res["total"] = 100.0
        res["reached"] = True
        
        # 读取并编码音频文件
        if os.path.exists(ATC_AUDIO_PATH):
            with open(ATC_AUDIO_PATH, "rb") as f:
                audio_data = f.read()
            res["atc_audio"] = base64.b64encode(audio_data).decode("utf-8")
        else:
            # 降级：返回空音频
            res["evidence"]["warning"] = "ATC audio file not found"
        
        # 记录 flag key 提示（只显示前8位）
        res["evidence"]["flag_key_hint"] = FLAG_KEY[:8] + "..."
    
    return res


def verify_flag1_key(submitted_key: str) -> bool:
    """
    验证选手提交的 flag key 是否正确
    
    参数:
        submitted_key: 选手提交的 key
    
    返回:
        bool: 是否正确
    """
    return submitted_key.strip().upper() == FLAG_KEY.upper()
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

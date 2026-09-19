"""判决轮询：会话静默 close_idle_s 后收口，跑三题判决并发 flag。"""
import time

from . import scores
from .checkers.flag1 import judge_flag1
from .checkers.flag2 import judge_flag2
from .checkers.flag3 import judge_flag3
from .trackdb import TrackDB


def judge_session(db: TrackDB, sid, rules):
    rows = db.rows(sid)
    sess = db.get_session(sid)
    uid = sess["callsign"] if sess else "unknown"
    out = {"sid": sid, "uid": uid, "n_samples": len(rows), "results": {}}

    # flag1
    r1 = judge_flag1(rows, rules["flag1"])
    out["results"]["flag1"] = r1
    if r1["total"] > 0:
        out["flag1"] = scores.issue_flag(uid, 1)

    # flag2（目标点 = 选手解算的交点；示例用 rules 中的固定点，部署时按
    # callsign 派生后写入会话，见 docs/2-平台侧.md）
    f2cfg = rules["flag2"]
    tgt = (f2cfg["target_lat"], f2cfg["target_lon"])
    ok2, ev2 = judge_flag2(
        rows, tgt, radius_m=f2cfg["radius_m"], ceil_ft=f2cfg["ceil_ft"],
        dur_s=f2cfg["dur_s"], max_gap_s=f2cfg["max_gap_s"],
        move_away_min_m=f2cfg["move_away_min_m"])
    out["results"]["flag2"] = {"ok": ok2, "evidence": ev2, "target": tgt}
    if ok2:
        out["flag2"] = scores.issue_flag(uid, 2)

    # flag3
    r3 = judge_flag3(rows, vne_kias=rules["flag3"]["vne_kias"])
    out["results"]["flag3"] = r3
    if r3["score"] > 0:
        out["flag3"] = scores.issue_flag(uid, 3)

    return out


def poll_sessions(db: TrackDB, rules, close_idle_s=None, once=False):
    """轮询 active sessions，静默超时的收口并判决。返回本轮所有判决结果。"""
    close_idle_s = close_idle_s or rules["session"]["close_idle_s"]
    now = time.time()
    results = []
    for sid, callsign in db.active_sessions():
        sess = db.get_session(sid)
        last = sess["last_seen"] or sess["started_at"]
        if now - last >= close_idle_s:
            db.close_session(sid)
            results.append(judge_session(db, sid, rules))
    return results

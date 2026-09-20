"""判决轮询：会话静默 close_idle_s 后收口，跑两题判决并发 flag。

新流程（简化版）：
- Flag1: 起飞并飞到上科大 (31.177°N, 121.596°E)，服务器下发ATC语音（含key）
- Flag2: 原flag3——物理不可能状态（飞天/遁地/超速），绕过反作弊达成

ATC语音包含加密的flag key，选手需解密后输入到web界面获得flag1。
"""
import time
import base64

from . import scores
from .checkers.flag1 import judge_flag1
from .checkers.flag2 import judge_flag2
from .trackdb import TrackDB


def judge_session(db: TrackDB, sid, rules, heartbeats=None):
    rows = db.rows(sid)
    sess = db.get_session(sid)
    uid = sess["callsign"] if sess else "unknown"
    out = {"sid": sid, "uid": uid, "n_samples": len(rows), "results": {}}

    # ---- heartbeats 查询 ----
    hb_ts = 0.0
    if heartbeats and uid in heartbeats:
        hb_ts = heartbeats[uid]
    hb_grace = rules["session"].get("grace_missed", 5)

    # 计算心跳有效性（flag1、flag2 共用）
    # 使用当前时间作为基准，确保心跳"新鲜"
    heartbeat_ok = (hb_ts > 0 and (time.time() - hb_ts) <= hb_grace)

    # Flag1: 到达目标点 —— 判决照做，是否发 flag 由下面统一的门控决定
    f1cfg = rules["flag1"]
    f1cfg["userid"] = uid  # 注入用户ID用于生成唯一key
    r1 = judge_flag1(rows, f1cfg)
    r1["heartbeat_ok"] = heartbeat_ok
    out["results"]["flag1"] = r1

    # Flag2: 物理不可能状态 —— 有心跳门控
    f2cfg = dict(rules["flag2"])
    f2cfg["hb_last_ts"] = hb_ts
    f2cfg["hb_grace_s"] = hb_grace
    r2 = judge_flag2(rows, f2cfg)
    out["results"]["flag2"] = r2

    # ── 防护总闸：已踢出会话不发 flag（判决明细仍回传，便于裁判复盘） ──
    from server import protection
    ok, reason = protection.check_session(uid)
    out["protection"] = {"ok": ok, "reason": reason}
    if not ok:
        print(f"[verdict] Session blocked: {uid} - {reason}")
        return out

    if r1.get("reached") and heartbeat_ok:
        out["flag1"] = scores.issue_flag(uid, 1)
        out["atc_audio"] = r1.get("atc_audio")
        out["flag1_hint"] = r1.get("evidence", {}).get("flag_key_hint")

    if r2.get("heartbeat_ok") and r2.get("total", 0) > 0:
        out["flag2"] = scores.issue_flag(uid, 2)

    return out


def poll_sessions(db: TrackDB, rules, heartbeats=None, close_idle_s=None):
    """轮询 active sessions：
    1. 遥测静默超时 → 收口判决
    2. 无心跳超时 → 强制收口判决（踢人）
    """
    close_idle_s = close_idle_s or rules["session"]["close_idle_s"]
    hb_grace = rules["session"].get("grace_missed", 5)
    now = time.time()
    results = []
    closed_sids = set()

    # 1. 静默超时 收口
    for sid, callsign in db.active_sessions():
        sess = db.get_session(sid)
        last = sess["last_seen"] or sess["started_at"]
        if now - last >= close_idle_s:
            db.close_session(sid)
            closed_sids.add(sid)
            results.append(judge_session(db, sid, rules, heartbeats))

    # 2. 心跳超时 踢人（不等待静默超时）
    for sid, callsign in db.active_sessions():
        if sid in closed_sids:
            continue
        sess = db.get_session(sid)
        session_start = sess["started_at"]
        age = now - session_start

        hb_ts = heartbeats.get(callsign, 0.0) if heartbeats else 0.0

        if age >= hb_grace and hb_ts <= 0.0:
            # 从未收到心跳 → 踢
            db.close_session(sid)
            print(f"[poller] KICK {callsign}: no heartbeat in {age:.1f}s (grace={hb_grace}s)")
            results.append(judge_session(db, sid, rules, heartbeats))
        elif hb_ts > 0.0 and (now - hb_ts) > hb_grace:
            # 心跳中断 → 踢
            db.close_session(sid)
            print(f"[poller] KICK {callsign}: heartbeat dead for {now - hb_ts:.1f}s")
            results.append(judge_session(db, sid, rules, heartbeats))

    return results
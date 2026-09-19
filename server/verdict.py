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


def judge_session(db: TrackDB, sid, rules):
    rows = db.rows(sid)
    sess = db.get_session(sid)
    uid = sess["callsign"] if sess else "unknown"
    out = {"sid": sid, "uid": uid, "n_samples": len(rows), "results": {}}

    # Flag1: 到达上科大目标点
    f1cfg = rules["flag1"]
    f1cfg["userid"] = uid  # 注入用户ID用于生成唯一key
    r1 = judge_flag1(rows, f1cfg)
    out["results"]["flag1"] = r1
    
    if r1.get("reached"):
        out["flag1"] = scores.issue_flag(uid, 1)
        # 存储ATC音频供前端播放
        out["atc_audio"] = r1.get("atc_audio")
        out["flag1_hint"] = r1.get("evidence", {}).get("flag_key_hint")

    # Flag2: 物理不可能状态（原flag3）
    f2cfg = rules["flag2"]
    r2 = judge_flag2(rows, f2cfg)
    out["results"]["flag2"] = r2
    
    if r2.get("total", 0) > 0:
        out["flag2"] = scores.issue_flag(uid, 2)

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

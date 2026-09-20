# -*- coding: utf-8 -*-
"""MAYDAY CTF Server Protection Layer - Warning first, kick after 10 min"""
import math
import time
import hashlib
import collections
from typing import Dict, List, Tuple, Any

class ProtectionConfig:
    max_messages_per_minute: int = 100
    max_speed_kts: float = 500.0
    replay_cache_size: int = 1000
    time_kick_s: int = 600

class ProtectionEngine:
    def __init__(self, config=None):
        self.cfg = config or ProtectionConfig()
        self.rate_counters = collections.defaultdict(list)
        self.replay_cache = collections.deque(maxlen=self.cfg.replay_cache_size)
        self.alert_counts = collections.defaultdict(int)
        self.first_alert_time = {}
        self.kicked = {}
        self.alert_log = []

    def check_message_rate(self, uid, now=None):
        now = now or time.time()
        cutoff = now - 60.0
        self.rate_counters[uid] = [t for t in self.rate_counters[uid] if t > cutoff]
        if len(self.rate_counters[uid]) >= self.cfg.max_messages_per_minute:
            self._alert(uid, f"RATE_LIMIT: {len(self.rate_counters[uid])} msg/min")
            return False, "Rate limit exceeded"
        self.rate_counters[uid].append(now)
        return True, ""

    def check_telemetry(self, uid, row):
        vcas = getattr(row, 'vcas_kt', 0)
        if vcas > self.cfg.max_speed_kts:
            self._alert(uid, f"SPEED_ANOMALY: {vcas}kt")
            return False, f"Impossible speed: {vcas}kt"
        return True, ""

    def check_replay(self, data):
        h = hashlib.sha256(data).hexdigest()
        for cached, _ in self.replay_cache:
            if cached == h:
                self._alert("unknown", f"REPLAY: {h[:16]}")
                return False
        self.replay_cache.append((h, time.time()))
        return True

    def check_session_duration(self, uid):
        if uid not in self.first_alert_time:
            return True, ""
        elapsed = time.time() - self.first_alert_time[uid]
        if elapsed >= self.cfg.time_kick_s:
            self.kicked[uid] = time.time()
            print(f"[protection] KICKED {uid}: {elapsed:.0f}s anomalies")
            return False, f"Kicked after {elapsed:.0f}s"
        remaining = int(self.cfg.time_kick_s - elapsed)
        print(f"[protection] WARNING {uid}: {remaining}s to kick")
        return True, ""

    def _alert(self, uid, msg):
        self.alert_counts[uid] += 1
        if uid not in self.first_alert_time:
            self.first_alert_time[uid] = time.time()
        self.alert_log.append({"uid": uid, "msg": msg, "time": time.time(), "count": self.alert_counts[uid]})
        if len(self.alert_log) > 10000:
            self.alert_log = self.alert_log[-5000:]

    def get_session_info(self, uid):
        return {"uid": uid, "alerts": self.alert_counts.get(uid, 0), "kicked": uid in self.kicked}

    def check_session(self, uid):
        """会话收口时的总闸：已踢出的直接拒，否则返回当前告警统计。

        返回 (ok, reason)，ok=False 表示本会话不发 flag。
        """
        if uid in self.kicked:
            return False, f"already kicked at {self.kicked[uid]:.0f}"
        n = self.alert_counts.get(uid, 0)
        if n:
            print(f"[protection] {uid}: {n} alerts, no kick (warn-first)")
        return True, ""


# 进程级单例：verdict 判决与 server_win 收包共用同一份统计，
# 否则判决侧永远看不到收包侧累积的告警（两套状态互不相通）。
_ENGINE = ProtectionEngine()


def get_engine() -> ProtectionEngine:
    return _ENGINE


def reset_engine() -> ProtectionEngine:
    """重置单例（自验/单测用，避免用例之间互相污染）。"""
    global _ENGINE
    _ENGINE = ProtectionEngine()
    return _ENGINE


class TelemetryAnomalyDetector:
    """遥测异常审计器（只记不杀）。

    server_win 收 5510 端口的 generic 遥测，用它和心跳里的 state_digest
    做交叉比对，识别"位置包与遥测不同源"的作弊形态。⚠ 只产生审计记录，
    绝不在此处拦截：真机在 warp/瞬变时也会有单帧跳变。
    """

    def __init__(self, max_jump_m: float = 50000.0, max_vcas_kt: float = 900.0):
        self.max_jump_m = max_jump_m
        self.max_vcas_kt = max_vcas_kt
        self.last: Dict[str, Dict[str, Any]] = {}
        self.anomalies: List[Dict[str, Any]] = []

    def observe(self, uid: str, lat: float, lon: float, alt_ft: float,
                ias_kt: float = 0.0, hdg: float = 0.0) -> List[str]:
        """喂一帧遥测，返回本帧命中的异常标签列表。"""
        tags: List[str] = []
        prev = self.last.get(uid)
        if prev:
            dt = max(1e-3, 1.0)
            d = _haversine_m(prev["lat"], prev["lon"], lat, lon)
            if d / dt > self.max_jump_m:
                tags.append("POS_JUMP")
            if abs(alt_ft - prev["alt_ft"]) > 100000.0:
                tags.append("ALT_JUMP")
        if ias_kt > self.max_vcas_kt:
            tags.append("OVERSPEED")
        self.last[uid] = {"lat": lat, "lon": lon, "alt_ft": alt_ft,
                          "ias_kt": ias_kt, "hdg": hdg}
        for t in tags:
            self.anomalies.append({"uid": uid, "tag": t, "time": time.time()})
        if len(self.anomalies) > 10000:
            self.anomalies = self.anomalies[-5000:]
        return tags

    def digest_matches(self, uid: str, state_digest: str, telemetry: Dict[str, Any]) -> bool:
        """心跳里的 state_digest 是否与本机遥测一致（两机攻击检测）。

        用 _hb_auth 端同款算法：没有遥测数据时视为「无法比对」，返回 True
        （宁可漏报也不要误杀——正式判罚交给人工复核）。
        """
        tel = telemetry or {}
        if not state_digest or not tel:
            return True
        want = compute_state_digest(tel.get("lat", 0.0), tel.get("lon", 0.0),
                                   tel.get("alt_ft", 0.0), tel.get("ias_kt", 0.0),
                                   tel.get("hdg", 0.0))
        return want == state_digest

    def report(self, uid: str = None) -> Dict[str, Any]:
        items = [a for a in self.anomalies if uid is None or a["uid"] == uid]
        by_tag: Dict[str, int] = {}
        for a in items:
            by_tag[a["tag"]] = by_tag.get(a["tag"], 0) + 1
        return {"uid": uid, "count": len(items), "by_tag": by_tag}


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6378137.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def compute_state_digest(lat: float, lon: float, alt_ft: float,
                         ias_kt: float, hdg: float) -> str:
    """与 server.hb_auth.compute_state_digest 完全同式，避免循环 import。"""
    raw = f"{lat}|{lon}|{alt_ft}|{ias_kt}|{hdg}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_session(uid):
    """模块级便捷入口：verdict.poll_sessions 用。"""
    return _ENGINE.check_session(uid)


def protect_message(engine, uid, msg_type, data, ip=None):
    """收包统一防护入口。

    ⚠ 只做「记录 + 阻断明显异常」，绝不在这里踢人：
    真 FG 客户端的 MP 包是等价内容重复（悬停/停机时位置不变），
    逐包内容哈希做重放检测会全量误杀。重放检测只用于心跳链路。
    """
    if uid in engine.kicked:
        return False, "User is kicked"
    ok, reason = engine.check_message_rate(uid)
    if not ok:
        return False, reason
    if msg_type == "heartbeat":
        if isinstance(data, dict):
            ts = data.get("ts", 0)
            if time.time() - ts > 30:
                engine._alert(uid, "HB_STALE")
                return False, "Heartbeat too old"
        return engine.check_replay(str(data).encode()), ""
    if msg_type in ("mp", "fdm", "text", "telemetry"):
        # 超速只在 flag2 里作为「达成条件」判定，不能在这里拦包，
        # 否则选手永远刷不出超速检查点。这里仅审计计数。
        vcas = data.get("vcas_kt") if isinstance(data, dict) else getattr(data, "vcas_kt", 0)
        if (vcas or 0) > engine.cfg.max_speed_kts:
            engine._alert(uid, f"SPEED_AUDIT: {vcas:.0f}kt")
        return True, ""
    return True, ""
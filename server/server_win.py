# -*- coding: utf-8 -*-
"""
MAYDAY CTF · 判决服务器（Windows 启动器）— v2

v2 新增：
  - 遥测端口 5510 (UDP)：接收 FG generic 遥测（含 instance-uuid）
  - 心跳 v2 验证：fg_uuid 交叉比对 + state_digest 交叉比对 + 挑战应答
  - 源 IP 关联（辅助）
  - FG 遥测:5510 心跳:5001 → 服务端交叉比对 UUID 和状态摘要

用法：
  AntiCheatServer.exe [--db track.db] [--rules rules.yaml]

首次运行会自动生成 hb_secret.key（32 字节随机密钥）。
此 key 必须与 anticheatd 编译时一致，否则心跳全部被拒。
"""

import argparse
import hashlib
import json
import select
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.localfdm import parse_fdm
from server.mp import parse_position
from server.rules_loader import load_rules
from server.trackdb import TrackDB
from server.trackrow import TrackRow
from server.verdict import poll_sessions
from server import hb_auth
from server.protection import (ProtectionEngine, TelemetryAnomalyDetector,
                               protect_message, get_engine)


# ── 防护引擎初始化 ───────────────────────────────────────────
# 用模块级单例，与 verdict 判决侧共用同一份告警统计
protection = get_engine()
anomaly_detector = TelemetryAnomalyDetector()


def row_from_mp(pkt):
    return TrackRow(ts=pkt["recv_time"], lat=pkt["lat"], lon=pkt["lon"],
                    alt_ft=pkt["alt_ft"], agl_ft=pkt["alt_ft"] - 5000.0,
                    hdg=pkt["hdg"], pitch=pkt["pitch"], roll=pkt["roll"],
                    vcas_kt=pkt["gs_kt"], vs_fps=pkt["vs_fps"], wow=0)


def open_session(db, sessions, key):
    if key not in sessions:
        sessions[key] = db.open_session(key)
        print(f"[poller] session open: {key}")
    return sessions[key]


def _compute_digest_from_mp(lat, lon, alt_ft, ias_kt, hdg):
    raw = f"{lat}|{lon}|{alt_ft}|{ias_kt}|{hdg}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════
# TELEMETRY PUMP (port 5510 — FG generic protocol)
# ═══════════════════════════════════════════════════════════════════

def _pump_telemetry(telemetry_state, sock):
    """接收 FG generic 遥测行：ts,lat,lon,alt_ft,agl_ft,heading,pitch,roll,vcas,vs_fps,wow,instance_uuid"""
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        try:
            line = data.decode("utf-8", errors="replace").strip()
            parts = line.split(",")
            if len(parts) >= 12:
                uuid = parts[11]
                if uuid:
                    telemetry_state["uuid"] = uuid
                    telemetry_state["ts"] = time.time()
                    telemetry_state["lat"] = float(parts[1])
                    telemetry_state["lon"] = float(parts[2])
                    telemetry_state["alt_ft"] = float(parts[3])
                    telemetry_state["ias_kt"] = float(parts[8])
                    telemetry_state["hdg"] = float(parts[5])
                    telemetry_state["digest"] = _compute_digest_from_mp(
                        telemetry_state["lat"], telemetry_state["lon"],
                        telemetry_state["alt_ft"], telemetry_state["ias_kt"],
                        telemetry_state["hdg"])
        except Exception:
            pass

def _pump_hb(hba, heartbeats, sessions, telemetry_state, sock):
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except BlockingIOError:
            break

        text = data.decode("utf-8", errors="replace").strip()
        if text == "PING":
            sock.sendto(b"PONG\n", addr)
            continue

        result = hb_auth.verify_heartbeat_v2(data, hba["secret"], hba["state"], sessions)
        if result:
            cs = result["callsign"]
            heartbeats[cs] = result["ts"]

            # Store heartbeat metadata per callsign
            hb_meta = hba.setdefault("meta", {}).setdefault(cs, {})
            hb_meta["fg_uuid"] = result.get("fg_uuid", "")
            hb_meta["state_digest"] = result.get("state_digest", "")
            hb_meta["addr"] = addr

            # Cross-check with telemetry
            tel_uuid = telemetry_state.get("uuid", "")
            hb_uuid = result.get("fg_uuid", "")
            hb_digest = result.get("state_digest", "")

            if tel_uuid and hb_uuid and tel_uuid != hb_uuid:
                print(f"[poller] HB UUID MISMATCH {cs}: tele={tel_uuid[:13]}... hb={hb_uuid[:13]}...")
                hb_meta["uuid_match"] = False
            else:
                hb_meta["uuid_match"] = True

            if telemetry_state.get("digest") and hb_digest:
                tel_digest = telemetry_state["digest"]
                if tel_digest != hb_digest:
                    print(f"[poller] HB DIGEST MISMATCH {cs}")
                    hb_meta["digest_match"] = False
                else:
                    hb_meta["digest_match"] = True

            hb_meta["tel_digest"] = telemetry_state.get("digest", "")
        else:
            try:
                raw = json.loads(data.decode("utf-8", errors="replace"))
                cs = raw.get('callsign', '?')
                # 防护检查：重放和速率
                if not protection.check_replay(data):
                    print(f"[poller] HB REPLAY BLOCKED: {cs}")
                elif not protection.check_message_rate(cs):
                    print(f"[poller] HB RATE LIMITED: {cs}")
                else:
                    print(f"[poller] HB REJECT: {cs} (bad ticket)")
            except Exception:
                print("[poller] HB REJECT: malformed")


def _pump_mp(db, sessions, sock):
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        pkt = parse_position(data, recv_time=time.time())
        if not pkt or not pkt["hdr"]["callsign"]:
            continue
        cs = pkt["hdr"]["callsign"]
        sid = open_session(db, sessions, cs)
        db.insert_row(sid, row_from_mp(pkt), source="mp")
        db.touch(sid, pkt["recv_time"])


def _pump_fdm(db, sessions, sock):
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        f = parse_fdm(data)
        if not f:
            continue
        key = "fdm:%s:%d" % (addr[0], addr[1])
        f["recv_time"] = time.time()
        sid = open_session(db, sessions, key)
        db.insert_row(sid, TrackRow(
            ts=f["recv_time"], lat=f["lat"], lon=f["lon"],
            alt_ft=f["alt_ft"], agl_ft=f["agl_ft"], hdg=f["hdg"],
            pitch=f["pitch"], roll=f["roll"], vcas_kt=f["vcas_kt"],
            vs_fps=f["vs_fps"], wow=1 if f["wow"] else 0), source="fdm")
        db.touch(sid, f["recv_time"])


def _pump_text(db, sessions, clients, s):
    try:
        data = s.recv(4096)
    except (BlockingIOError, ConnectionResetError, OSError):
        data = b""
    if not data:
        s.close()
        clients.pop(s, None)
        return
    clients[s] += data
    while b"\n" in clients[s]:
        line, clients[s] = clients[s].split(b"\n", 1)
        f = parse_fdm(line)
        if not f or not f["callsign"]:
            continue
        cs = f["callsign"]
        sid = open_session(db, sessions, cs)
        db.insert_row(sid, TrackRow(
            ts=f["ts"], lat=f["lat"], lon=f["lon"], alt_ft=f["alt_ft"],
            agl_ft=f["agl_ft"], hdg=f["hdg"], pitch=f["pitch"],
            roll=f["roll"], vcas_kt=f["vcas_kt"], vs_fps=f["vs_fps"],
            wow=1 if f["wow"] else 0), source="text")
        db.touch(sid, f["ts"])


# ═══════════════════════════════════════════════════════════════════
# CHALLENGE GENERATOR
# ═══════════════════════════════════════════════════════════════════

def _send_challenges(hba, sock_hb):
    """定期向活跃反作弊客户端发送随机挑战。"""
    for cs, meta in hba.get("meta", {}).items():
        addr = meta.get("addr")
        if not addr:
            continue
        # 每 10 秒发一次新挑战
        last_chal = meta.get("last_challenge_time", 0)
        if time.time() - last_chal > 10.0:
            ch = hb_auth.generate_challenge()
            hba["state"].setdefault(cs, {})["pending_challenge"] = ch
            meta["last_challenge_time"] = time.time()
            sock_hb.sendto(f"CHALLENGE:{ch}".encode(), addr)
            print(f"[poller] CHALLENGE -> {cs}: {ch[:16]}...")


# ═══════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════

def _report(db, rules, heartbeats, hba):
    for res in poll_sessions(db, rules, heartbeats):
        r1 = res["results"]["flag1"]
        r2 = res["results"]["flag2"]
        cs = res["uid"]

        # 检查心跳 v2 防护层是否通过
        hb_meta = hba.get("meta", {}).get(cs, {})
        uuid_ok = hb_meta.get("uuid_match", True)
        digest_ok = hb_meta.get("digest_match", True)

        flags = []
        if not uuid_ok:
            flags.append("UUID-MISMATCH")
        if not digest_ok:
            flags.append("DIGEST-MISMATCH")

        flag_str = " ".join(flags) if flags else "ok"
        print(f"[poller] VERDICT {cs}: "
              f"flag1={r1['total']:.0f} "
              f"flag2={r2['total']:.0f} "
              f"hb1={r1.get('heartbeat_ok','-')} hb2={r2.get('heartbeat_ok','-')} "
              f"v2={flag_str}")
        for k in ("flag1", "flag2"):
            if res.get(k):
                print(f"[poller]   {k} -> {res[k]}")


def ensure_key(key_path):
    key_path = Path(key_path)
    if key_path.exists():
        return
    key = hb_auth.generate_key()
    key_path.write_bytes(key)
    print(f"[poller] Generated new secret key: {key_path} ({len(key)*8} bit)")
    print(f"[poller] WARNING: This key must match anticheatd.exe build!")


def main():
    ap = argparse.ArgumentParser(description="MAYDAY CTF 判决服务器 v2")
    ap.add_argument("--db", default="track.db")
    ap.add_argument("--rules", default=str(REPO / "server" / "rules.yaml"))
    ap.add_argument("--hb-key", default=str(REPO / "server" / "hb_secret.key"))
    ap.add_argument("--mp-port", type=int, default=5000)
    ap.add_argument("--fdm-port", type=int, default=3001)
    ap.add_argument("--text-port", type=int, default=3002)
    ap.add_argument("--hb-port", type=int, default=5001)
    ap.add_argument("--tel-port", type=int, default=5510)
    ap.add_argument("--poll-interval", type=float, default=5.0)
    args = ap.parse_args()

    rules = load_rules(args.rules)
    db = TrackDB(args.db)

    ensure_key(args.hb_key)
    try:
        secret = hb_auth.load_secret_key(args.hb_key)
        print(f"[poller] HB secret key loaded ({len(secret)*8} bit)")
    except FileNotFoundError:
        secret = b"\x00" * 32
        print(f"[poller] HB WARNING: secret key not found, using dummy (DEV ONLY)")

    hba = {"secret": secret, "state": {}, "meta": {}}
    sessions = {}
    heartbeats = {}
    telemetry_state = {}  # {uuid, ts, lat, lon, alt_ft, ias_kt, hdg, digest}

    sock_mp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_mp.bind(("0.0.0.0", args.mp_port))
    sock_mp.setblocking(False)

    sock_fdm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_fdm.bind(("0.0.0.0", args.fdm_port))
    sock_fdm.setblocking(False)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.text_port))
    srv.listen(8)
    srv.setblocking(False)

    sock_hb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_hb.bind(("0.0.0.0", args.hb_port))
    sock_hb.setblocking(False)

    sock_tel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_tel.bind(("0.0.0.0", args.tel_port))
    sock_tel.setblocking(False)

    clients = {}

    print(f"[poller] MP-UDP:{args.mp_port} FDM-UDP:{args.fdm_port} "
          f"HB-UDP:{args.hb_port} TEL-UDP:{args.tel_port} TEXT-TCP:{args.text_port} db={args.db}")
    print(f"[poller] Server v2 running. Press Ctrl+C to stop.")

    next_poll = time.time() + args.poll_interval
    next_challenge = time.time() + 5.0
    try:
        while True:
            now_t = time.time()
            timeout = max(0.05, min(next_poll - now_t, next_challenge - now_t))
            readable, _, _ = select.select(
                [srv, sock_mp, sock_fdm, sock_hb, sock_tel] + list(clients),
                [], [], timeout)
            for s in readable:
                if s is srv:
                    conn, addr = srv.accept()
                    conn.setblocking(False)
                    clients[conn] = b""
                elif s is sock_mp:
                    _pump_mp(db, sessions, sock_mp)
                elif s is sock_fdm:
                    _pump_fdm(db, sessions, sock_fdm)
                elif s is sock_hb:
                    _pump_hb(hba, heartbeats, sessions, telemetry_state, sock_hb)
                elif s is sock_tel:
                    _pump_telemetry(telemetry_state, sock_tel)
                else:
                    _pump_text(db, sessions, clients, s)

            if time.time() >= next_poll:
                next_poll = time.time() + args.poll_interval
                _report(db, rules, heartbeats, hba)

            if time.time() >= next_challenge:
                next_challenge = time.time() + 5.0
                _send_challenges(hba, sock_hb)

    except KeyboardInterrupt:
        print("\n[poller] Shutting down...")

    sock_mp.close()
    sock_fdm.close()
    srv.close()
    sock_hb.close()
    sock_tel.close()
    for c in list(clients):
        c.close()
    print("[poller] Server stopped.")


if __name__ == "__main__":
    main()
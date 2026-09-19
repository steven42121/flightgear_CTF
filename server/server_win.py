# -*- coding: utf-8 -*-
"""
MAYDAY CTF · 判决服务器（Windows 启动器）

功能：
  - 启动四条监听链路（MP:5000, FDM:3001, Text:3002, HB:5001）
  - 心跳防重放、会话门控、两题判决发 flag
  - 纯 Python 实现，PyInstaller 打包为单文件 .exe

用法：
  AntiCheatServer.exe [--db track.db] [--rules rules.yaml]

首次运行会自动生成 hb_secret.key（32 字节随机密钥）。
此 key 必须与 anticheatd 编译时一致，否则心跳全部被拒。
"""

import argparse
import json
import select
import socket
import sys
import time
import os
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


def _pump_hb(hba, heartbeats, sessions, sock):
    while True:
        try:
            data, _addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        result = hb_auth.verify_heartbeat(data, hba["secret"], hba["state"])
        if result:
            cs = result["callsign"]
            heartbeats[cs] = result["ts"]
        else:
            try:
                raw = json.loads(data.decode("utf-8", errors="replace"))
                print(f"[poller] HB REJECT: {raw.get('callsign', '?')} (bad ticket)")
            except Exception:
                print("[poller] HB REJECT: malformed")


def _pump_mp(db, sessions, sock):
    while True:
        try:
            data, _addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        pkt = parse_position(data, recv_time=time.time())
        if not pkt or not pkt["hdr"]["callsign"]:
            continue
        sid = open_session(db, sessions, pkt["hdr"]["callsign"])
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
        sid = open_session(db, sessions, f["callsign"])
        db.insert_row(sid, TrackRow(
            ts=f["ts"], lat=f["lat"], lon=f["lon"], alt_ft=f["alt_ft"],
            agl_ft=f["agl_ft"], hdg=f["hdg"], pitch=f["pitch"],
            roll=f["roll"], vcas_kt=f["vcas_kt"], vs_fps=f["vs_fps"],
            wow=1 if f["wow"] else 0), source="text")
        db.touch(sid, f["ts"])


def _report(db, rules, heartbeats):
    for res in poll_sessions(db, rules, heartbeats):
        r1 = res["results"]["flag1"]
        r2 = res["results"]["flag2"]
        print(f"[poller] VERDICT {res['uid']}: "
              f"flag1={r1['total']:.0f} "
              f"flag2={r2['total']:.0f} "
              f"hb1={r1.get('heartbeat_ok','-')} hb2={r2.get('heartbeat_ok','-')}")
        for k in ("flag1", "flag2"):
            if res.get(k):
                print(f"[poller]   {k} -> {res[k]}")


def ensure_key(key_path):
    """首次运行自动生成密钥文件（如果不存在）。"""
    key_path = Path(key_path)
    if key_path.exists():
        return
    key = hb_auth.generate_key()
    key_path.write_bytes(key)
    print(f"[poller] Generated new secret key: {key_path} ({len(key)*8} bit)")
    print(f"[poller] WARNING: This key must match anticheatd.exe build!")


def main():
    ap = argparse.ArgumentParser(description="MAYDAY CTF 判决服务器")
    ap.add_argument("--db", default="track.db")
    ap.add_argument("--rules", default=str(REPO / "server" / "rules.yaml"))
    ap.add_argument("--hb-key", default=str(REPO / "server" / "hb_secret.key"))
    ap.add_argument("--mp-port", type=int, default=5000)
    ap.add_argument("--fdm-port", type=int, default=3001)
    ap.add_argument("--text-port", type=int, default=3002)
    ap.add_argument("--hb-port", type=int, default=5001)
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

    hba = {"secret": secret, "state": {}}
    sessions = {}
    heartbeats = {}

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

    clients = {}

    print(f"[poller] MP-UDP:{args.mp_port} FDM-UDP:{args.fdm_port} "
          f"HB-UDP:{args.hb_port} TEXT-TCP:{args.text_port} db={args.db}")
    print(f"[poller] Server running. Press Ctrl+C to stop.")

    next_poll = time.time() + args.poll_interval
    try:
        while True:
            timeout = max(0.05, min(1.0, next_poll - time.time()))
            readable, _, _ = select.select(
                [srv, sock_mp, sock_fdm, sock_hb] + list(clients),
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
                    _pump_hb(hba, heartbeats, sessions, sock_hb)
                else:
                    _pump_text(db, sessions, clients, s)

            if time.time() >= next_poll:
                next_poll = time.time() + args.poll_interval
                _report(db, rules, heartbeats)
    except KeyboardInterrupt:
        print("\n[poller] Shutting down...")

    # Cleanup
    sock_mp.close()
    sock_fdm.close()
    srv.close()
    sock_hb.close()
    for c in list(clients):
        c.close()
    print("[poller] Server stopped.")


if __name__ == "__main__":
    main()
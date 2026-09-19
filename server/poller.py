"""判决服务器入口。

    python -m server.poller --db /tmp/ctf.db --rules server/rules.yaml

监听三条链路（独立端口，互不阻塞）：
- UDP 5000：multiplay 位置包（MsgId=7），callsign 取自 MP 头 → 会话归属
- UDP 3001：FG 原生 FDM 帧（--native-fdm 同款 408B），会话按来源地址归属
- TCP 3002：demo 文本行 `CS:<callsign>|<ts>,...`（测试辅助）

静默 close_idle_s 的会话收口判决，verdict 打印到 stdout。
"""
import argparse
import select
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.localfdm import parse_fdm  # noqa: E402
from server.mp import parse_position   # noqa: E402
from server.rules_loader import load_rules  # noqa: E402
from server.trackdb import TrackDB     # noqa: E402
from server.trackrow import TrackRow   # noqa: E402
from server.verdict import poll_sessions  # noqa: E402


def row_from_mp(pkt):
    """MP 包 → TrackRow。
    注意：MP 包无 AGL/wow，正式部署时 AGL 应查 scenery 高程、wow 由
    generic 遥测补齐；这里用固定差值占位以便开发联调。"""
    return TrackRow(ts=pkt["recv_time"], lat=pkt["lat"], lon=pkt["lon"],
                    alt_ft=pkt["alt_ft"], agl_ft=pkt["alt_ft"] - 5000.0,
                    hdg=pkt["hdg"], pitch=pkt["pitch"], roll=pkt["roll"],
                    vcas_kt=pkt["gs_kt"], vs_fps=pkt["vs_fps"], wow=0)


def open_session(db, sessions, key):
    if key not in sessions:
        sessions[key] = db.open_session(key)
        print(f"[poller] session open: {key}")
    return sessions[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=":memory:")
    ap.add_argument("--rules", default=str(REPO / "server" / "rules.yaml"))
    ap.add_argument("--mp-port", type=int, default=5000)
    ap.add_argument("--fdm-port", type=int, default=3001)
    ap.add_argument("--text-port", type=int, default=3002)
    ap.add_argument("--poll-interval", type=float, default=5.0)
    args = ap.parse_args()

    rules = load_rules(args.rules)
    db = TrackDB(args.db)
    sessions = {}   # 会话归属 key → sid

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

    clients = {}    # text socket → 缓冲
    print(f"[poller] MP-UDP:{args.mp_port} FDM-UDP:{args.fdm_port} "
          f"TEXT-TCP:{args.text_port} db={args.db}")

    next_poll = time.time() + args.poll_interval
    while True:
        timeout = max(0.05, min(1.0, next_poll - time.time()))
        readable, _, _ = select.select([srv, sock_mp, sock_fdm] + list(clients),
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
            else:
                _pump_text(db, sessions, clients, s)

        if time.time() >= next_poll:
            next_poll = time.time() + args.poll_interval
            _report(db, rules)


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


def _report(db, rules):
    for res in poll_sessions(db, rules):
        r1 = res["results"]["flag1"]
        r2 = res["results"]["flag2"]
        r3 = res["results"]["flag3"]
        print(f"[poller] VERDICT {res['uid']}: flag1={r1['total']:.0f} "
              f"flag2={r2['ok']} flag3={r3['score']:.0f}")
        for k in ("flag1", "flag2", "flag3"):
            if res.get(k):
                print(f"[poller]   {k} → {res[k]}")


if __name__ == "__main__":
    main()

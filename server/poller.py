"""判决服务器入口。

    python -m server.poller --db /tmp/ctf.db --rules server/rules.yaml

监听四条链路（独立端口，互不阻塞）：
- UDP 5000：multiplay 位置包（MsgId=7），callsign 取自 MP 头 → 会话归属
- UDP 3001：FG 原生 FDM 帧（--native-fdm 同款 408B），会话按来源地址归属
- TCP 3002：demo 文本行 `CS:<callsign>|<ts>,...`（测试辅助）
- UDP 5001：anticheatd 心跳（HMAC 票据，防重放）

静默 close_idle_s 的会话收口判决，verdict 打印到 stdout。
"""
import argparse
import json
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
from server import hb_auth               # noqa: E402


def row_from_mp(pkt):
    """MP 包 → TrackRow。

    ts 用包内自带的仿真时间（接收端补的 recv_time 只在时钟不可信时兜底）：
    判决器按 ts 算“停留时长/持续秒数”，若逐包写服务端收包时刻，
    合法轨迹也会被判成拖了整场，且重放时无法复现。
    ⚠ 正式部署时 AGL 应查 scenery 高程、wow 由 generic 遥测补齐；
    这里用固定差值占位以便开发联调。
    """
    return TrackRow(ts=pkt.get("ts") or pkt["recv_time"], lat=pkt["lat"], lon=pkt["lon"],
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
    ap.add_argument("--hb-key", default=str(REPO / "server" / "hb_secret.key"))
    ap.add_argument("--mp-port", type=int, default=5000)
    ap.add_argument("--fdm-port", type=int, default=3001)
    ap.add_argument("--text-port", type=int, default=3002)
    ap.add_argument("--hb-port", type=int, default=5001)
    ap.add_argument("--poll-interval", type=float, default=5.0)
    args = ap.parse_args()

    rules = load_rules(args.rules)
    db = TrackDB(args.db)

    # 初始化心跳认证
    try:
        secret = hb_auth.load_secret_key(args.hb_key)
        print(f"[poller] HB secret key loaded ({len(secret)*8} bit)")
    except FileNotFoundError:
        # 密钥文件不存在时降级为 dummy key（自验/开发用）
        secret = b"\x00" * 32
        print(f"[poller] HB WARNING: secret key not found ({args.hb_key}), "
              f"using dummy key (DEV ONLY)")
    hba = {
        "secret": secret,
        "state": {},  # callsign → {"last_seq": int, "last_ts": float}
    }

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

    sock_hb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_hb.bind(("0.0.0.0", args.hb_port))
    sock_hb.setblocking(False)

    clients = {}    # text socket → 缓冲
    heartbeats = {}  # callsign → last_heartbeat_ts（服务端心跳门控）
    print(f"[poller] MP-UDP:{args.mp_port} FDM-UDP:{args.fdm_port} "
          f"HB-UDP:{args.hb_port} "
          f"TEXT-TCP:{args.text_port} db={args.db}")

    next_poll = time.time() + args.poll_interval
    while True:
        timeout = max(0.05, min(1.0, next_poll - time.time()))
        readable, _, _ = select.select([srv, sock_mp, sock_fdm, sock_hb] + list(clients),
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


def _pump_hb(hba, heartbeats, sessions, sock):
    """接收 anticheatd 心跳包，验证 HMAC 票据后记录。

    格式: {"callsign":"MAYDAY01","seq":42,"ts":1.234e9,"ticket":"<64 hex>"}
    验证: HMAC 正确 + seq 单调递增 + ts 在时间窗口内。
    通过后才更新 heartbeats[callsign] = ts。
    """
    while True:
        try:
            data, _addr = sock.recvfrom(2048)
        except BlockingIOError:
            break
        result = hb_auth.verify_heartbeat(data, hba["secret"], hba["state"])
        if result:
            cs = result["callsign"]
            heartbeats[cs] = result["ts"]
            # 静默记录，减少日志噪音（调试时可打开）
            # print(f"[poller] HB ok: {cs} seq={result['seq']}")
        else:
            # 票据验证失败 — 可能是抓包重放攻击
            try:
                raw = json.loads(data.decode("utf-8", errors="replace"))
                print(f"[poller] HB REJECT: {raw.get('callsign','?')} (bad ticket)")
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
                print(f"[poller]   {k} → {res[k]}")


if __name__ == "__main__":
    main()
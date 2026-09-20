"""端到端联调：真起判决服务器 → 心跳 + MP/UDP 回放轨迹 → 查判决与 flag 下发。

    python -m tools.dbg_flag

这是 verify_all 之外的链路测试：poller 收包 → trackdb 落库 → 会话静默收口 →
verdict 判决 → scores 发 flag，并顺带回归"篡改心跳票据必须被拒"。
用临时端口 + 临时 DB，不影响正式环境。
"""
import csv
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server import hb_auth, scores                      # noqa: E402
from server.mp import encode_position                   # noqa: E402
from server.trackdb import TrackDB                      # noqa: E402
from server.trackrow import TrackRow                    # noqa: E402

CS = "E2E01"
MP_PORT, FDM_PORT, TEXT_PORT, HB_PORT = 15000, 15002, 15003, 15001


def load_rows():
    rows = []
    with open(REPO / "build" / "track.csv", newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            rows.append(TrackRow.from_dict({k: float(v) for k, v in rec.items()}))
    return rows


def main():
    db_path = Path(tempfile.gettempdir()) / "e2e_ctf.db"
    if db_path.exists():
        db_path.unlink()

    hidden = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-u", "-m", "server.poller",
         "--db", str(db_path), "--mp-port", str(MP_PORT), "--hb-port", str(HB_PORT),
         "--fdm-port", str(FDM_PORT), "--text-port", str(TEXT_PORT),
         "--poll-interval", "2"],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", creationflags=hidden)
    time.sleep(3.0)

    rows = load_rows()
    print(f"[e2e] 回放 {len(rows)} 帧（MP/UDP），每行 1 次审计心跳")
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    hb = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 << 20)
    secret = hb_auth.load_secret_key(str(REPO / "server" / "hb_secret.key"))

    for i, r in enumerate(rows):
        udp.sendto(encode_position(CS, r.lat, r.lon, r.alt_ft or 0, r.agl_ft or 0,
                                   r.hdg or 0, r.pitch or 0, r.roll or 0, ts=r.ts),
                   ("127.0.0.1", MP_PORT))
        # 逐步放开按真实 1Hz 打心跳（seq 严格递增），让心跳窗口不落后于轨迹
        hb.sendto(hb_auth.make_heartbeat(CS, i, secret), ("127.0.0.1", HB_PORT))
        if i % 250 == 0:
            time.sleep(0.01)

    # P1 防护回归：篡改票据必须被拒（不应刷新 heartbeats）
    bad = json.dumps({"callsign": "HACKER", "seq": 1, "ts": time.time(),
                      "ticket": "0" * 64}).encode()
    hb.sendto(bad, ("127.0.0.1", HB_PORT))

    print("[e2e] 等待会话静默收口（close_idle_s=30s）...")
    time.sleep(34)
    proc.terminate()
    out, _ = proc.communicate(timeout=10)
    print("---- server stdout ----")
    print(out.strip())
    print("-----------------------")

    db = TrackDB(str(db_path))
    sess = db.conn.execute("SELECT id, callsign, closed FROM sessions").fetchall()
    print(f"[e2e] sessions = {sess}")
    n = 0
    if sess:
        n = db.conn.execute("SELECT COUNT(*) FROM track WHERE sid=?",
                            (sess[0][0],)).fetchone()[0]
    print(f"[e2e] rows in db = {n} / replayed {len(rows)}")
    print(f"[e2e] expected flag1 = {scores.issue_flag(CS, 1)}")
    print(f"[e2e] expected flag2 = {scores.issue_flag(CS, 2)}")

    checks = [
        ("会话已收口", bool(sess) and sess[0][2] == 1),
        ("轨迹已落库", n > len(rows) * 0.9),
        ("打印 flag1 判决", "flag1=" in out),
        ("打印 flag2 判决", "flag2=" in out),
        ("下发 flag（含 flag{）", "flag{" in out),
        ("篡改心跳被拒", "HB REJECT" in out),
    ]
    for name, ok in checks:
        print(("  [PASS] " if ok else "  [FAIL] ") + name)
    all_ok = all(ok for _, ok in checks)
    print("[e2e] RESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
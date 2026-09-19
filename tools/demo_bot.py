"""demo 模拟机：把测试轨迹发给判决服务器。

三种出流方式（--mode）：
- mp    : 组装 MP 位置包发 UDP:5000（与真 FG 客户端同一路径，验证 mp.py 全链路）
- fdm   : 408B FDM 帧发 UDP:3001（验证 localfdm 解析链路）
- text  : 文本行发 TCP:3002（自带 callsign，最直观）

用法：
    python -m tools.demo_bot --csv /tmp/track.csv --mode mp --callsign TEST01
"""
import argparse
import csv
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.localfdm import encode_fdm  # noqa: E402
from server.mp import encode_position   # noqa: E402
from server.trackrow import TrackRow    # noqa: E402


def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            d = {k: float(v) for k, v in rec.items()}
            rows.append(TrackRow.from_dict(d))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--mp-port", type=int, default=5000)
    ap.add_argument("--fdm-port", type=int, default=3001)
    ap.add_argument("--text-port", type=int, default=3002)
    ap.add_argument("--callsign", default="TEST01")
    ap.add_argument("--mode", choices=["mp", "fdm", "text"], default="mp")
    ap.add_argument("--speed", type=float, default=30.0,
                    help="回放倍速（1=实时，30=30倍快进）")
    args = ap.parse_args()

    rows = load_rows(args.csv)
    if not rows:
        print("no rows")
        return
    t0 = time.time()
    base = rows[0].ts

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if args.mode == "text":
        tcp = socket.create_connection((args.host, args.text_port))
    else:
        tcp = None

    for r in rows:
        while (r.ts - base) / args.speed > time.time() - t0:
            time.sleep(0.005)
        if args.mode == "mp":
            udp.sendto(encode_position(
                args.callsign, r.lat, r.lon, r.alt_ft or 0, r.agl_ft or 0,
                r.hdg or 0, r.pitch or 0, r.roll or 0, ts=r.ts), (args.host, args.mp_port))
        elif args.mode == "fdm":
            udp.sendto(encode_fdm(r.lat, r.lon, r.alt_ft or 0, r.agl_ft or 0, r.hdg or 0,
                                  r.pitch or 0, r.roll or 0, r.vcas_kt or 0, r.vs_fps or 0,
                                  wow=1 if r.wow else 0, when=r.ts),
                       (args.host, args.fdm_port))
        else:
            line = (f"CS:{args.callsign}|{r.ts:.3f},{r.lat:.7f},{r.lon:.7f},"
                    f"{r.alt_ft or 0:.1f},{r.agl_ft or 0:.1f},{r.hdg or 0:.1f},{r.pitch or 0:.1f},"
                    f"{r.roll or 0:.1f},{r.vcas_kt or 0:.1f},{r.vs_fps or 0:.1f},{r.wow or 0}\n")
            tcp.sendall(line.encode())
    if tcp:
        tcp.close()
    print(f"sent {len(rows)} rows in {time.time() - t0:.1f}s "
          f"(x{args.speed} speed, mode={args.mode})")


if __name__ == "__main__":
    main()

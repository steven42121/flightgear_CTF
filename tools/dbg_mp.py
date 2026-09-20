"""MP 编解码批量自检 + 本机 UDP 往返压力测试。

    python -m tools.dbg_mp

用于定位"服务器只收到前若干帧"这类问题：先排除编码/解析层，
再看 socket 层（收发缓冲、包速率）。
"""
import csv
import math
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.mp import (angle_axis_to_euler, encode_position,   # noqa: E402
                       parse_position, quat_to_angle_axis)
from server.trackrow import TrackRow                           # noqa: E402


def load_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [TrackRow.from_dict({k: float(v) for k, v in rec.items()})
                for rec in csv.DictReader(fh)]


def selfinverse():
    print("== 欧拉 → 角轴 → 欧拉 自逆 ==")
    lat, lon, hdg, pit, rol = 0.0, 0.0, 90.0, 0.0, 0.0
    ang, ax, ay, az = quat_to_angle_axis(lat, lon, hdg, pit, rol)
    print("  angle(deg) =", math.degrees(ang), "axis =", (ax, ay, az))
    print("  roundtrip  :", angle_axis_to_euler(lat, lon, ax, ay, az, ang))


def roundtrip():
    print("== 逐帧 encode/parse 批量自检 ==")
    rows = load_rows(REPO / "build" / "track.csv")
    bad, sizes, worst = [], set(), (0.0, None)
    for i, r in enumerate(rows):
        pkt = encode_position("E2E01", r.lat, r.lon, r.alt_ft or 0, r.agl_ft or 0,
                              r.hdg or 0, r.pitch or 0, r.roll or 0, ts=r.ts)
        sizes.add(len(pkt))
        p = parse_position(pkt)
        if p is None:
            bad.append((i, r.lat, r.lon, r.alt_ft, r.hdg, r.pitch, r.roll))
            continue
        if p["alt_ft"] > worst[0]:
            worst = (p["alt_ft"], i)
    print(f"  rows={len(rows)} bad={len(bad)} pkt_sizes={sorted(sizes)}")
    for b in bad[:10]:
        print("   BAD", b)
    print(f"  max alt_ft after decode = {worst[0]:.1f} (row {worst[1]})")
    return len(bad)


def udp_stress(rows):
    """本机 UDP 全速回放：测量接收端实际拿到的帧数（查丢包与缓冲）。"""
    print("== 本机 UDP 往返压力测试 ==")
    port = 15700
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
    srv.bind(("127.0.0.1", port))
    srv.setblocking(False)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 << 20)

    sent = 0
    got = 0
    t0 = time.time()
    idx = 0
    n = len(rows)
    while idx < n:
        # 每次突发 200 包后 drain 一下，贴近"无节流洪水"的极限场景
        while idx < n and sent % 200 != 0 or sent == 0:
            r = rows[idx]
            tx.sendto(encode_position("E2E01", r.lat, r.lon, r.alt_ft or 0,
                                      r.agl_ft or 0, r.hdg or 0, r.pitch or 0,
                                      r.roll or 0, ts=r.ts), ("127.0.0.1", port))
            sent += 1
            idx += 1
            if sent % 200 == 0:
                break
        while True:
            try:
                data, _ = srv.recvfrom(2048)
            except BlockingIOError:
                break
            if parse_position(data):
                got += 1
    while True:
        try:
            data, _ = srv.recvfrom(2048)
        except BlockingIOError:
            break
        if parse_position(data):
            got += 1
    dt = time.time() - t0
    print(f"  sent={sent} got={got} loss={sent - got} ({100.0 * (sent - got) / sent:.1f}%) "
          f"in {dt:.2f}s")
    srv.close()
    tx.close()
    return sent - got


def main():
    selfinverse()
    bad = roundtrip()
    rows = load_rows(REPO / "build" / "track.csv")
    loss = udp_stress(rows)
    print("[dbg_mp] RESULT:", "PASS" if bad == 0 and loss == 0 else "FAIL")
    return 0 if bad == 0 and loss == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

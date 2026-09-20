"""一键自验：MP/FDM 协议 roundtrip + 三题判决。

    python -m tools.verify_all            # 先自动生成 build/track.csv
覆盖 doc1《验收测试清单》中可离线验证的条目。
"""
import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server.localfdm import FG_NET_FDM_SIZE, encode_fdm, parse_fdm  # noqa: E402
from server.mp import (V2_PAD_MAGIC, encode_position, parse_header,   # noqa: E402
                       parse_position, quat_to_angle_axis,
                       angle_axis_to_euler)
from server.rules_loader import load_rules  # noqa: E402
from server.trackrow import TrackRow  # noqa: E402
from server.checkers.flag1 import judge_flag1  # noqa: E402
from server.checkers.flag2 import judge_flag2  # noqa: E402
from server.checkers.flag3 import judge_flag3  # noqa: E402

RULES = load_rules(str(REPO / "server" / "rules.yaml"))
FAILURES = []


def check(name, ok, detail=""):
    print(("  [PASS] " if ok else "  [FAIL] ") + name
          + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(name)


def load_rows(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            rows.append(TrackRow.from_dict(
                {k: float(v) for k, v in rec.items()}))
    return rows


def test_mp_roundtrip():
    print("== MP 协议 roundtrip ==")
    pkt = encode_position("TEST01", 36.5, -115.3, 12000.0, 9000.0,
                          90.0, 5.0, -3.0,
                          vel_n_ms=50.0, vel_e_ms=20.0, ts=1234.5)
    hdr = parse_header(pkt)
    check("头 36B / magic / callsign / msgid=7",
          hdr["msg_len"] == len(pkt) and hdr["callsign"] == "TEST01"
          and hdr["msg_id"] == 7, f"len={hdr['msg_len']}")
    check("V2 pad magic", pkt[-4:] == V2_PAD_MAGIC.to_bytes(4, "big"))
    p = parse_position(pkt, recv_time=999.0)
    check("位置误差 < 1e-6 度",
          abs(p["lat"] - 36.5) < 1e-6 and abs(p["lon"] + 115.3) < 1e-6,
          f"lat={p['lat']:.7f} lon={p['lon']:.7f}")
    check("高度误差 < 1 ft", abs(p["alt_ft"] - 12000.0) < 1.0)
    check("航向误差 < 0.01 度",
          abs((p["hdg"] - 90.0 + 180) % 360 - 180) < 0.01,
          f"hdg={p['hdg']:.4f}")
    check("俯仰/滚转误差 < 0.01 度",
          abs(p["pitch"] - 5.0) < 0.01 and abs(p["roll"] + 3.0) < 0.01)
    check("ECEF 速度往返一致",
          abs(p["v_n_ms"] - 50.0) < 1e-3 and abs(p["v_e_ms"] - 20.0) < 1e-3)
    ang, ax, ay, az = quat_to_angle_axis(0.0, 0.0, 270.0, -10.0, 20.0)
    h2, p2, r2 = angle_axis_to_euler(0.0, 0.0, ax, ay, az, ang)
    check("角轴与欧拉互逆",
          abs((h2 - 270.0 + 180) % 360 - 180) < 1e-6
          and abs(p2 + 10.0) < 1e-6 and abs(r2 - 20.0) < 1e-6,
          f"h={h2:.5f} p={p2:.5f} r={r2:.5f}")


def test_fdm_roundtrip():
    print("== FGNetFDM v24 roundtrip ==")
    raw = encode_fdm(36.25, -115.25, 5500.0, 500.0, 180.0, -2.0, 1.5,
                     95.0, -300.0, wow=1, when=1700000000)
    check("帧长 408B", len(raw) == FG_NET_FDM_SIZE, f"len={len(raw)}")
    f = parse_fdm(raw)
    check("版本 24 解析成功", f is not None)
    check("位置/高度往返",
          abs(f["lat"] - 36.25) < 1e-7 and abs(f["alt_ft"] - 5500.0) < 1.0)
    check("psi+90 约定：航向 180 往返",
          abs((f["hdg"] - 180.0 + 180) % 360 - 180) < 0.01,
          f"hdg={f['hdg']:.4f}")
    check("wow=1", f["wow"] == 1)
    line = b"CS:ABC|123.0,36.0,-115.0,1000,900,90,1,0,80,0,0"
    t = parse_fdm(line)
    check("文本行解析 + callsign",
          t["callsign"] == "ABC" and t["lat"] == 36.0)



def test_flag1(csv_path):
    print("== flag1 判决 (新格式：到达目标点) ==")
    rows = load_rows(csv_path)
    # 测试轨迹里 ils 段落在 (36.15, -115.15) 机场上，故用该点当目标点自验判决链路。
    # 正式比赛用 rules.yaml 里的上科大坐标。
    cfg = {
        "target_lat": 36.15,
        "target_lon": -115.15,
        "radius_m": 500.0,
        "ceil_ft": 2000.0,   # 测试轨迹接地高度为 2000ft，故放宽（真实 ZSPD 用 rules.yaml 的 1000ft）
        "dur_s": 5.0,
        "userid": "TEST01",
    }
    r = judge_flag1(rows, cfg)
    check("返回 total 字段", "total" in r, f"keys={list(r.keys())}")
    check("返回 reached 字段", "reached" in r)
    check("返回 evidence 字段", "evidence" in r)
    check("到达目标点并给满分",
          r["reached"] and r["total"] == 100.0,
          f"closest={r['evidence'].get('closest_m')}m "
          f"stay={r['evidence'].get('max_stay_s')}s")

    # 反例：目标点挪到 20nm 外，必须判不到
    far = dict(cfg, target_lat=36.15 + 20.0 / 60.0)
    rf = judge_flag1(rows, far)
    check("远离目标点不给分", not rf["reached"] and rf["total"] == 0.0,
          f"closest={rf['evidence'].get('closest_m')}m")


def test_flag2(csv_path):
    print("== flag2 判决 (新格式：物理不可能状态) ==")
    rows = load_rows(csv_path)
    f2cfg = dict(RULES["flag2"])
    # 测试环境模拟：注入有效心跳（当前时间，确保在 grace 窗口内）
    import time as _time
    f2cfg["hb_last_ts"] = _time.time()
    f2cfg["hb_grace_s"] = RULES["session"]["grace_missed"]
    r2 = judge_flag2(rows, f2cfg)
    check("返回 total 字段", "total" in r2)
    check("返回 verdict 字段", "verdict" in r2)
    check("返回 checkpoints 字段", "checkpoints" in r2)
    check("心跳门控通过", r2.get("heartbeat_ok", False))
    if r2["total"] > 0:
        check("得分 > 0", True, f"total={r2['total']:.1f}")
    else:
        check("得分 > 0", False, f"total={r2['total']:.1f}")


def test_flag3(csv_path):
    # flag3 已合并到 flag2，此测试保留以防引用
    print("== flag3 判决 (已合并到 flag2) ==")
    pass


def main():
    # 每次自验都重新生成，避免复用旧段集合（例如缺 ceil/taxi/speed）的陈旧 CSV。
    csv_path = REPO / "build" / "track.csv"
    print("[setup] 生成测试轨迹 ...")
    # 顺序即比赛流程：热身平飞 → 绕场(flag2) → ILS 落地(flag1) → 物理不可能(flag3)
    subprocess.run([sys.executable, "-m", "tools.gen_testdata",
                    "--out", str(csv_path),
                    "--segments", "walk,ils,arc,ceil,taxi,speed"],
                   cwd=str(REPO), check=True)
    test_mp_roundtrip()
    test_fdm_roundtrip()
    test_flag1(str(csv_path))
    test_flag2(str(csv_path))
    test_flag3(str(csv_path))
    print()
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败：{FAILURES}")
        sys.exit(1)
    print("全部通过 OK")


if __name__ == "__main__":
    main()
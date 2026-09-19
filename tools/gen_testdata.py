"""测试/自验轨迹生成器。

生成 server.checkers 三个判决器的输入 CSV（每行一条 TrackRow）。
默认输出四段：walk（平飞）→ arc（绕圈）→ ilsglideslope（ILS 进近落地），
再加 --flag3 时追加 ceil / taxi / speed 三段"物理不可能"轨迹。

用法：
    python tools/gen_testdata.py --out /tmp/track.csv
    python tools/gen_testdata.py --out /tmp/track.csv --segments walk,arc,ceil,taxi,speed
"""
import argparse
import csv
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

NM_M = 1852.0
M_FT = 0.3048
DT = 0.1  # 10Hz


def _dlat(nm):
    return nm * NM_M / 111320.0


def _dlon(nm, lat):
    return nm * NM_M / (111320.0 * math.cos(math.radians(lat)))


def _course_leg(rows, t0, lat0, lon0, course, dist_nm, speed_kt, alt_ft, agl_ft=None,
                vs_fps=0.0, vcas=None, pitch=2.0, roll=0.0, wow=0):
    """沿固定航向飞一段直线。"""
    n = int(dist_nm * NM_M / (speed_kt * 0.5144) / DT)
    v = speed_kt * 0.5144
    for i in range(n):
        d = v * i * DT
        lat = lat0 + _dlat(d / NM_M) * math.cos(math.radians(course))
        lon = lon0 + _dlon(d / NM_M, lat0) * math.sin(math.radians(course))
        rows.append([t0 + i * DT, lat, lon, alt_ft,
                     alt_ft if agl_ft is None else agl_ft,
                     course, pitch, roll, vcas or speed_kt, vs_fps, wow])
    return t0 + n * DT, lat, lon


def seg_walk(t0, lat0, lon0):
    """平飞 10 分钟：80kt 向北。"""
    rows = []
    _course_leg(rows, t0, lat0, lon0, 0.0, 26.6, 80, 8000.0, pitch=2.0)
    return rows


def seg_arc(t0, lat0, lon0):
    """绕圈 15 分钟：半径 8nm，90kt。"""
    rows = []
    n = int(900.0 / DT)
    for i in range(n):
        t = i * DT
        ang = t * (90 * 0.5144) / (8 * NM_M)  # 角速度 = v/r
        lat = lat0 + _dlat(8.0) * math.sin(ang)
        lon = lon0 + _dlon(8.0, lat0) * (math.cos(ang) - 1.0)
        rows.append([t0 + t, lat, lon, 8000.0, 8000.0,
                     (math.degrees(ang) + 180.0) % 360.0, 0.0, 25.0, 90.0, 0.0, 0])
    return rows


def seg_ils(t0, lat0, lon0):
    """ILS 进近并落地（虚构机场 RWY36，与 rules.yaml 的占位坐标一致）。
    从 8nm 南端沿 360° 航向飞 3° 下滑道，最后 150m 拉飘，接地后滚跑 20s。"""
    rows = []
    thr_alt = 2000.0
    gs_angle = 3.0
    start_nm = 8.0
    v = 70 * 0.5144
    total_m = start_nm * NM_M + 1500.0
    n = int(total_m / v / DT) + 1
    tan_gs = math.tan(math.radians(gs_angle))
    for i in range(n):
        d = v * i * DT  # 已飞距离
        if d <= start_nm * NM_M:
            d_to_thr = start_nm * NM_M - d  # 距跑道口剩余距离
            if d_to_thr > 150.0:
                alt = thr_alt + d_to_thr * tan_gs / M_FT
                vs = -vcas_vs(v, gs_angle)
            else:
                # 拉飘：最后 150m 二次收敛到跑道口，VS 平滑归零
                frac = d_to_thr / 150.0
                alt = thr_alt + frac * frac * 150.0 * tan_gs / M_FT
                vs = -frac * vcas_vs(v, gs_angle)
            wow = 0
            agl = alt - thr_alt
        else:
            alt = thr_alt
            vs = 0.0
            wow = 1
            agl = 0.0
        lat = (lat0 - _dlat(start_nm)) + _dlat(d / NM_M)
        lon = lon0
        rows.append([t0 + i * DT, lat, lon, alt, agl, 360.0, -2.5, 0.0, 70.0, vs, wow])
    return rows


def vcas_vs(v_ms, gs_angle):
    return v_ms * math.tan(math.radians(gs_angle)) / M_FT


def seg_ceil(t0, lat0, lon0):
    """飞天：匀速爬到 120,000ft 并保持 14s（2000 ft/s，平滑）。"""
    rows = []
    t = 0.0
    alt = 2000.0
    while alt < 120000.0:
        rows.append([t0 + t, lat0, lon0, alt, alt, 0.0, 30.0, 0.0, 250.0, 2000.0 / 0.3048 * 0.3048, 0])
        alt += 2000.0 * DT
        t += DT
    for i in range(140):
        rows.append([t0 + t + i * DT, lat0, lon0, 120000.0, 120000.0,
                     0.0, 0.0, 0.0, 250.0, 0.0, 0])
    return rows


def seg_taxi(t0, lat0, lon0):
    """遁地：AGL -350ft 保持 12s（平滑的低空直线）。"""
    rows = []
    n = int(12.0 / DT)
    for i in range(n):
        d = 60 * 0.5144 * i * DT
        lat = lat0 + _dlat(d / NM_M)
        rows.append([t0 + i * DT, lat, lon0, 1650.0, -350.0, 0.0, 0.0, 0.0, 60.0, 0.0, 0])
    return rows


def seg_speed(t0, lat0, lon0):
    """超速：500kt（≈3.07×VNE163）保持 16s。"""
    rows = []
    n = int(16.0 / DT)
    for i in range(n):
        d = 500 * 0.5144 * i * DT
        lat = lat0 + _dlat(d / NM_M)
        rows.append([t0 + i * DT, lat, lon0, 10000.0, 8000.0, 0.0, 0.0, 0.0, 500.0, 0.0, 0])
    return rows


SEGMENTS = {
    # warm-up 平飞段：离虚构机场 ~38nm 外（真实选手会先在场外热身）
    "walk": (seg_walk, (36.15, -114.35)),
    "arc": (seg_arc, (36.10, -115.15)),
    "ils": (seg_ils, (36.150000, -115.150000)),
    "ceil": (seg_ceil, (36.20, -115.20)),
    "taxi": (seg_taxi, (36.25, -115.25)),
    "speed": (seg_speed, (36.30, -115.30)),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--segments", default="walk,arc,ils")
    ap.add_argument("--t0", type=float, default=None)
    args = ap.parse_args()

    header = ["ts", "lat", "lon", "alt_ft", "agl_ft", "heading_deg", "pitch_deg",
              "roll_deg", "vcas_kt", "vs_fps", "wow"]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t = args.t0 if args.t0 is not None else time.time()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for name in args.segments.split(","):
            name = name.strip()
            if not name:
                continue
            fn, (lat0, lon0) = SEGMENTS[name]
            rows = fn(t, lat0, lon0)
            w.writerows(rows)
            t = rows[-1][0] + 1.0
            print(f"[gen] {name}: {len(rows)} rows, end {t - rows[-1][0] - 1.0:.0f}s")
    print(f"[gen] wrote {out}")


if __name__ == "__main__":
    main()

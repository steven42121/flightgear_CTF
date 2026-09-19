"""flag2 领航解谜：per-user 参数生成 + 自检 + 题面数据下发。

doc3 §2.1 谜题本体：双圆交点二义 + C 台方位消歧
doc3 §2.2 参考实现：局部平面近似（米制）双圆求交 + 观测方位
doc3 §2.3 参数自检：|dA-dB| < dist(A,B) < dA+dB；两交点相距 ≥5nm；
                  两交点相对 C 的方位差 ≥30°；目标点不在水面上（人工）。

用法：
  python -m tools.ctf2gen --uid TEAM01 \
      --station-a 36.05,-115.20 --station-b 36.30,-115.10 --station-c 36.10,-115.00
"""
import argparse
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from server import geodesy  # noqa: E402
from server.scores import issue_flag  # noqa: E402

M_FT = 0.3048


def circle_intersections(A, B, rA_nm, rB_nm):
    """A/B=(lat,lon)，半径海里。返回两个交点 (lat,lon)。无解返回 []。"""
    d = geodesy.haversine_m(A[0], A[1], B[0], B[1])
    rA, rB = rA_nm * geodesy.M_NM, rB_nm * geodesy.M_NM
    if d > rA + rB or d < abs(rA - rB):
        return []
    a = (rA ** 2 - rB ** 2 + d ** 2) / (2 * d)
    h = math.sqrt(max(0.0, rA ** 2 - a ** 2))
    # A→B 单位向量（局部平面近似，与 doc3 §2.2 一致）
    dx = (B[1] - A[1]) * 111320.0 * math.cos(math.radians(A[0]))
    dy = (B[0] - A[0]) * 110540.0
    dn = math.hypot(dx, dy)
    ux, uy = dx / dn, dy / dn
    px, py = -uy, ux
    base_lat = A[0] + a * uy / 110540.0
    base_lon = A[1] + a * ux / (111320.0 * math.cos(math.radians(A[0])))
    out = []
    for s in (+1.0, -1.0):
        out.append((base_lat + s * h * py / 110540.0,
                    base_lon + s * h * px / (111320.0 * math.cos(math.radians(A[0])))))
    return out


def obs_bearing(target, station):
    """目标点 → 台 的方位（度）。"""
    return geodesy.initial_bearing(target[0], target[1],
                                   station[0], station[1])


def angdiff(a, b):
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def disambiguate(P1, P2, C, radial_from_target):
    """radial_from_target：自目标点观测 C 台的方位角。
    doc3 §2.2 的方向性易错点：'目标点看台'，与'台看目标点'相差 180°。"""
    e1 = angdiff(obs_bearing(P1, C), radial_from_target)
    e2 = angdiff(obs_bearing(P2, C), radial_from_target)
    return (P1, e1) if e1 < e2 else (P2, e2)


def gen_params(uid, A, B, C, rA_nm, rB_nm, seed_extra=None):
    """按 uid 派生谜题参数并自检。返回 (target, puzzle_text) 或 None。"""
    pts = circle_intersections(A, B, rA_nm, rB_nm)
    if len(pts) != 2:
        return None
    P1, P2 = pts
    sep_nm = geodesy.haversine_m(P1[0], P1[1], P2[0], P2[1]) / geodesy.M_NM
    if sep_nm < 5.0:
        return None  # 交点分离度不足（doc3 §2.3）
    # 两交点相对 C 的方位差
    dAz = angdiff(obs_bearing(P1, C), obs_bearing(P2, C))
    if dAz < 30.0:
        return None
    # 目标点选分离度最大的那个交点作为"真目标"，另一个作为"陷阱"
    target, err = disambiguate(P1, P2, C, obs_bearing(P1, C))
    text = (f"STATION  A : ident {uid[:3]}A   freq 112.{int(rA_nm)%10}   DME {rA_nm:.1f} nm\n"
            f"STATION  B : ident {uid[:3]}B   freq 113.{int(rB_nm)%10}   DME {rB_nm:.1f} nm\n"
            f"STATION  C : ident {uid[:3]}C   freq 114.30           RADIAL {int(obs_bearing(target, C)):03d}\n"
            f"注：读数自目标点观测所得。")
    return {
        "target": target, "trap": (P2 if target == P1 else P1),
        "sep_nm": sep_nm, "az_diff_deg": dAz,
        "puzzle": text,
        "flag_example": issue_flag(uid, 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True)
    ap.add_argument("--station-a", required=True, help="lat,lon")
    ap.add_argument("--station-b", required=True)
    ap.add_argument("--station-c", required=True)
    ap.add_argument("--dA", type=float, default=18.0, help="海里")
    ap.add_argument("--dB", type=float, default=22.0)
    args = ap.parse_args()
    p = lambda s: tuple(float(x) for x in s.split(","))
    A, B, C = p(args.station_a), p(args.station_b), p(args.station_c)
    r = gen_params(args.uid, A, B, C, args.dA, args.dB)
    if not r:
        print("参数不满足 doc3 §2.3 自检（无解/交点过近/方位差过小）")
        return
    print(r["puzzle"])
    print(f"target    = ({r['target'][0]:.6f}, {r['target'][1]:.6f})")
    print(f"trap      = ({r['trap'][0]:.6f}, {r['trap'][1]:.6f})  [消歧陷阱点]")
    print(f"sep       = {r['sep_nm']:.1f} nm, Δaz = {r['az_diff_deg']:.0f}°")
    print(f"flag 示例  = {r['flag_example']}")


if __name__ == "__main__":
    main()

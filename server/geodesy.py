"""大地测量与坐标转换工具（server/checkers 共用）。

- 大圆距离 / 方位角（haversine，精度足够 CTF 判决）
- 横向偏差（ILS 判接地用）
- WGS84 大地坐标 ↔ ECEF 直角坐标（FG 的 SGVec3d::fromGeod 同款，用于 MP 包）
"""
import math

# WGS84 参数
WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

# 单位换算
M_FT = 0.3048
M_NM = 1852.0


def haversine_m(lat1, lon1, lat2, lon2):
    """两点大圆距离（米）。"""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * WGS84_A * math.asin(math.sqrt(a))


def initial_bearing(lat1, lon1, lat2, lon2):
    """从点1看向点2的初始方位角（度，0=北）。"""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = (math.cos(rlat1) * math.sin(rlat2)
         - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
    return math.degrees(math.atan2(x, y)) % 360.0


def cross_track_m(thr_lat, thr_lon, course_deg, lat, lon):
    """点 (lat, lon) 相对跑道中心线的横向偏差（米，右正左负）。"""
    crs = math.radians(course_deg)
    d13 = haversine_m(thr_lat, thr_lon, lat, lon) / WGS84_A  # 角距离
    if d13 <= 0:
        return 0.0
    brg13 = math.radians(initial_bearing(thr_lat, thr_lon, lat, lon))
    xt = math.asin(math.sin(brg13 - crs) * math.sin(d13))
    return math.degrees(xt) * WGS84_A  # 近似小角：弧长 = 角 × 半径


def geod_to_ecef(lat_deg, lon_deg, alt_m):
    """WGS84 大地坐标 → ECEF（米）。与 simgear SGVec3d::fromGeod 一致。"""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sl, cl = math.sin(lat), math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sl * sl)
    x = (n + alt_m) * cl * math.cos(lon)
    y = (n + alt_m) * cl * math.sin(lon)
    z = (n * (1.0 - WGS84_E2) + alt_m) * sl
    return x, y, z


def ecef_to_geod(x, y, z):
    """ECEF（米）→ WGS84 大地坐标（度, 米）。Bowring 迭代法，收敛极快。"""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        sl = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sl * sl)
        h = p / math.cos(lat) - n
        lat = math.atan2(z + WGS84_E2 * n * sl, p)
    sl = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sl * sl)
    h = p / math.cos(lat) - n
    return math.degrees(lat), math.degrees(lon), h


def heading_to_uv(hdg_deg):
    """航向角（度）→ (北分量, 东分量) 单位向量。"""
    r = math.radians(hdg_deg)
    return math.cos(r), math.sin(r)

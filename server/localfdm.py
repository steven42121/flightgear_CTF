"""FlightGear 原生 FDM (FGNetFDM v24) 编码器。

字节布局（从 flightgear/src/Network/net_fdm.hxx 逐字段转录）：
  uint32 version=24, uint32 padding,
  double longitude(rad), double latitude(rad), double altitude(m),
  float  agl(m), phi, theta, psi(rad), alpha, beta,
  float  phidot, thetadot, psidot, vcas, climb_rate,
         v_north, v_east, v_down, v_body_u/v/w,
         A_X/Y/Z_pilot, stall_warning, slip_deg,
  uint32 num_engines, eng_state[4],
  float  rpm[4], fuel_flow[4], fuel_px[4], egt[4], cht[4], mp_osi[4],
         tit[4], oil_temp[4], oil_px[4],
  uint32 num_tanks, float fuel_quantity[4],
  uint32 num_wheels, uint32 wow[3],
  float  gear_pos[3], gear_steer[3], gear_compression[3],
  uint32 cur_time, int32 warp, float visibility,
  float  elevator, elevator_trim_tab, left_flap, right_flap,
         left_aileron, right_aileron, rudder, nose_wheel, speedbrake, spoilers

编码 = 大端 (XDR, RFC 1014/1832)。结构与 FGProps2FDM 一致，对照
native_structs.cxx 可确认字段含义。总长 408 字节。
"""
import socket
import struct
import time

FG_NET_FDM_VERSION = 24
FG_NET_FDM_SIZE = 408
NET_FMT = ">IIddd22fI4I36fI4fI3I9fIif10f"
assert struct.calcsize(NET_FMT) == FG_NET_FDM_SIZE, struct.calcsize(NET_FMT)


def _psi_to_heading(psi_rad):
    """FG 的 /orientation/heading-deg = psi-90（见 server/mp.py 同名函数）。"""
    return (psi_rad * 57.29577951308232 - 90.0) % 360.0


def encode_fdm(lat_deg, lon_deg, alt_ft, agl_ft, hdg_deg, pitch_deg, roll_deg,
               vcas_kt, vs_fps, wow=0, when=None):
    """按 FGNetFDM v24 编码一帧 FDM 数据（返回 bytes）。

    wow: 0=空中, 1=接地（与 FG 的 /gear/gear[0]/wow 一致）
    """
    when = when or time.time()
    ver = FG_NET_FDM_VERSION
    pad = 0
    lon = lon_deg * 0.017453292519943295
    lat = lat_deg * 0.017453292519943295
    alt_m = alt_ft * 0.3048
    agl_m = agl_ft * 0.3048
    phi = roll_deg * 0.017453292519943295
    theta = pitch_deg * 0.017453292519943295
    psi = (hdg_deg + 90.0) * 0.017453292519943295  # 反变换见 _psi_to_heading
    alpha = 0.0
    beta = 0.0
    phidot = thetadot = psidot = 0.0
    vcas = vcas_kt
    climb = vs_fps
    vn = ve = vd = vu = vv = vw = 0.0
    ax = ay = az = 0.0
    stall = 0.0
    slip = 0.0
    n_eng = 1
    eng_state = [2, 0, 0, 0]  # 2=running
    rpm = [2500.0, 0, 0, 0]
    fuel_flow = [8.0, 0, 0, 0]
    fuel_px = [20.0, 0, 0, 0]
    egt = [1200.0, 0, 0, 0]
    cht = [300.0, 0, 0, 0]
    mp_osi = [29.0, 0, 0, 0]
    tit = [0.0] * 4
    oil_temp = [180.0, 0, 0, 0]
    oil_px = [60.0, 0, 0, 0]
    n_tank = 2
    fuel_qty = [20.0, 20.0, 0.0, 0.0]
    n_wheel = 3
    wow3 = [wow, 0, 0]
    gear_pos = [1.0, 1.0, 1.0]
    gear_steer = [0.0] * 3
    gear_comp = [0.1, 0.1, 0.1]
    cur_time = int(when)
    warp = 0
    vis = 20000.0
    elev = elev_trim = lflap = rflap = lail = rail = 0.0
    rud = nose = sbrake = spoil = 0.0

    return struct.pack(
        NET_FMT,
        ver, pad, lon, lat, alt_m,
        agl_m, phi, theta, psi, alpha, beta,
        phidot, thetadot, psidot, vcas, climb,
        vn, ve, vd, vu, vv, vw,
        ax, ay, az, stall, slip,
        n_eng, *eng_state,
        *rpm, *fuel_flow, *fuel_px, *egt, *cht, *mp_osi, *tit, *oil_temp, *oil_px,
        n_tank, *fuel_qty,
        n_wheel, *wow3, *gear_pos, *gear_steer, *gear_comp,
        cur_time, warp, vis,
        elev, elev_trim, lflap, rflap, lail, rail, rud, nose, sbrake, spoil,
    )


def encode_telemetry_row(row):
    """把统一 TrackRow 直接编码为 FDM 帧（供 demo_bot / 回放器使用）。"""
    return encode_fdm(row.lat, row.lon, row.alt_ft, row.agl_ft, row.hdg,
                      row.pitch, row.roll, row.vcas_kt, row.vs_fps,
                      wow=1 if row.wow else 0, when=row.ts)


# ---------------- 解析侧（服务端收 FDM 流用） ----------------
R2D = 57.29577951308232


def _psi_to_heading_pub(psi_rad):
    """FG 内部 /orientation/heading-deg = psi - 90°（见 mp.py 同名函数）。"""
    return (psi_rad * R2D - 90.0) % 360.0


def parse_fdm_binary(buf):
    """解析 408 字节 FGNetFDM v24 二进制帧 → dict；版本不符返回 None。"""
    if len(buf) < FG_NET_FDM_SIZE:
        return None
    try:
        (version, _pad, lon_rad, lat_rad, alt_m, agl_m, phi, theta, psi,
         _alpha, _beta, _phidot, _thetadot, _psidot, vcas, climb) = \
            struct.unpack_from(">IIddd11f", buf, 0)
        (wow,) = struct.unpack_from(">I", buf, 308)  # gear 段 wow[0]（见 net_fdm.hxx）
    except struct.error:
        return None
    if version != FG_NET_FDM_VERSION:
        return None
    return {
        "lat": lat_rad * R2D, "lon": lon_rad * R2D,
        "alt_ft": alt_m / 0.3048, "agl_ft": agl_m / 0.3048,
        "hdg": _psi_to_heading_pub(psi),
        "pitch": theta * R2D, "roll": phi * R2D,
        "vcas_kt": vcas, "vs_fps": climb, "wow": wow,
        "callsign": None,   # 二进制帧不带 callsign，由传输层决定
        "recv_time": 0.0,   # 由传输层填（服务端权威时间戳）
    }


def parse_fdm_line(line):
    """解析 demo 文本行 `CS:<callsign>|<ts>,<lat>,...,<wow>` → dict。"""
    s = line.strip()
    if not s.startswith(b"CS:"):
        return None
    try:
        head, csv_part = s[3:].split(b"|", 1)
        callsign = head.decode("ascii", "ignore")[:16]
        vals = [float(x) for x in csv_part.split(b",")]
        if len(vals) < 11:
            return None
    except (ValueError, IndexError):
        return None
    ts, lat, lon, alt, agl, hdg, pitch, roll, vcas, vs, wow = vals[:11]
    return {"ts": ts, "lat": lat, "lon": lon, "alt_ft": alt, "agl_ft": agl,
            "hdg": hdg, "pitch": pitch, "roll": roll, "vcas_kt": vcas,
            "vs_fps": vs, "wow": int(wow), "callsign": callsign,
            "recv_time": ts}


def parse_fdm(buf):
    """demo 传输层入口：文本行或二进制帧均可，返回统一 dict 或 None。"""
    if not buf:
        return None
    if buf.lstrip().startswith(b"CS:"):
        return parse_fdm_line(buf)
    return parse_fdm_binary(buf)

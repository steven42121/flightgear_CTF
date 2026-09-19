"""FlightGear multiplayer 协议（XDR over UDP）编解码。

协议头 36 字节（从 multiplaymgr.cxx 的 T_MsgHdr 逐字段核对）：
    0x00 u32 Magic = 0x46474653 ("FGFS")
    0x04 u32 Version = 0x00010001 (1.1)
    0x08 u32 MsgId = 7 位置消息（1 chat 已废弃）
    0x0c u32 MsgLen = 整个消息字节数（含头）
    0x10 u32 RequestedRangeNm（XDR_encode_shortints32(0,range) → 高 16 位）
    0x14 u32 ReplyPort = 0
    0x18 8B Callsign（截断到 8 字节）
位置消息体（T_PositionMsg，196B + 4B pad）：
    96B Model（XDR opaque）、f64 time、f64 lag、
    f64 position[3]（ECEF 米）、f32 orientation[3]（角轴，角度编入轴长）、
    f32 linearVel[3]、f32 angularVel[3]、f32 linearAccel[3]、
    f32 angularAccel[3]、u32 pad（0 或 0x1face002 = V2 属性标识）
属性表：V1 = (u32 id, u32 value) 重复；V2 短整 = 单个 u32 打包两个 16 位。

本服务端只解析 MsgId=7 的位置消息（头 + 位置部分 + pad），属性跳过。
"""
import math
import struct

from .geodesy import ecef_to_geod, geod_to_ecef

MAGIC = 0x46474653
VERSION = 0x00010001
POS_DATA_ID = 7
MP_2017_DATA_ID = 8
V2_PAD_MAGIC = 0x1FACE002
HEADER_LEN = 32  # 6×u32 + 8B callsign = 32B（T_MsgHdr 实际大小，sizeof==32）

XDR_UINT32 = struct.Struct(">I")
XDR_FLOAT32 = struct.Struct(">f")
XDR_FLOAT64 = struct.Struct(">d")
D2R = math.pi / 180.0
R2D = 180.0 / math.pi


def encode_header(callsign, msg_id=POS_DATA_ID, msg_len=None, range_nm=100):
    """36 字节 MP 头。callsign 超过 8 字节会被截断（FG 的行为）。"""
    cs = (callsign or "")[:8].encode("ascii", "ignore").ljust(8, b"\x00")
    if msg_len is None:
        msg_len = HEADER_LEN
    return (XDR_UINT32.pack(MAGIC) + XDR_UINT32.pack(VERSION)
            + XDR_UINT32.pack(msg_id) + XDR_UINT32.pack(msg_len)
            + XDR_UINT32.pack((int(range_nm) & 0xFFFF) << 16)
            + XDR_UINT32.pack(0) + cs)


def parse_header(buf):
    """解析 36 字节 MP 头，返回 dict；magic 不符抛 ValueError。"""
    if len(buf) < HEADER_LEN:
        raise ValueError("packet shorter than header")
    magic, ver, msg_id, msg_len, range_field, reply_port = \
        struct.unpack_from(">6I", buf, 0)
    if magic != MAGIC:
        raise ValueError("bad magic 0x%x" % magic)
    cs = buf[0x18:0x20].split(b"\x00")[0].decode("ascii", "ignore")
    return {"version": ver, "msg_id": msg_id, "msg_len": msg_len,
            "range_nm": range_field >> 16, "reply_port": reply_port,
            "callsign": cs}


def encode_position(callsign, lat_deg, lon_deg, alt_ft, agl_ft, hdg_deg,
                    pitch_deg, roll_deg, vel_n_ms=0.0, vel_e_ms=0.0,
                    vel_d_ms=0.0, ts=0.0, lag=0.0,
                    model="Aircraft/c172p/Models/c172p.xml", v2_pad=True,
                    properties=b""):
    """编码完整 MsgId=7 位置消息。vel_* 为 ECEF 速度（米/秒）。"""
    x, y, z = geod_to_ecef(lat_deg, lon_deg, alt_ft * 0.3048)
    angle, ax_, ay_, az_ = quat_to_angle_axis(lat_deg, lon_deg, hdg_deg,
                                              pitch_deg, roll_deg)
    body = (struct.pack(">96s", model.encode("ascii", "ignore")[:96])
            + XDR_FLOAT64.pack(ts) + XDR_FLOAT64.pack(lag)
            + XDR_FLOAT64.pack(x) + XDR_FLOAT64.pack(y) + XDR_FLOAT64.pack(z)
            + XDR_FLOAT32.pack(ax_ * angle) + XDR_FLOAT32.pack(ay_ * angle)
            + XDR_FLOAT32.pack(az_ * angle)
            + XDR_FLOAT32.pack(vel_n_ms) + XDR_FLOAT32.pack(vel_e_ms)
            + XDR_FLOAT32.pack(vel_d_ms)
            + XDR_FLOAT32.pack(0.0) * 3   # angularVel
            + XDR_FLOAT32.pack(0.0) * 3   # linearAccel
            + XDR_FLOAT32.pack(0.0) * 3   # angularAccel
            + XDR_UINT32.pack(V2_PAD_MAGIC if v2_pad else 0))
    msg_len = HEADER_LEN + len(body) + len(properties)
    return encode_header(callsign, POS_DATA_ID, msg_len) + body + properties


def parse_position(buf, recv_time=None):
    """解析 MsgId=7 位置消息 → dict；非位置包/包不完整返回 None。"""
    try:
        hdr = parse_header(buf)
    except ValueError:
        return None
    if hdr["msg_id"] != POS_DATA_ID:
        return None
    if len(buf) < HEADER_LEN + 196 + 4:
        return None
    off = HEADER_LEN
    model = buf[off:off + 96].split(b"\x00")[0].decode("ascii", "ignore")
    off += 96
    ts, lag = struct.unpack_from(">2d", buf, off)
    off += 16
    px, py, pz = struct.unpack_from(">3d", buf, off)
    off += 24
    ax, ay, az = struct.unpack_from(">3f", buf, off)
    off += 12
    vn, ve, vd = struct.unpack_from(">3f", buf, off)
    off += 12
    for _ in range(9):
        off += 4
    pad = struct.unpack_from(">I", buf, off)[0]
    angle = math.sqrt(ax * ax + ay * ay + az * az)
    lat, lon, alt_m = ecef_to_geod(px, py, pz)
    if angle > 1e-8:
        hdg, pitch, roll = angle_axis_to_euler(lat, lon,
                                               ax / angle, ay / angle,
                                               az / angle, angle)
    else:
        hdg, pitch, roll = 0.0, 0.0, 0.0
    return {
        "hdr": hdr, "model": model, "time": ts, "lag": lag,
        "lat": lat, "lon": lon, "alt_ft": alt_m / 0.3048,
        "hdg": hdg, "pitch": pitch, "roll": roll,
        "v_n_ms": vn, "v_e_ms": ve, "v_d_ms": vd,
        "gs_kt": math.hypot(vn, ve) / 0.5144,
        "vs_fps": (-vd) / 0.3048,
        "v2_pad": (pad == V2_PAD_MAGIC),
        "recv_time": recv_time if recv_time is not None else ts,
    }


# ---------------- 姿态四元数（与 FG SGQuat 同款约定） ----------------
def _quat_mul(a, b):
    return (a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
            a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
            a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
            a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0])


def quat_to_angle_axis(lat_deg, lon_deg, hdg_deg, pitch_deg, roll_deg):
    """欧拉角 → 角轴（角度编入轴长）。姿态 = q_ec2hl * q_hl_or：
    q_ec2hl 来自 SGQuat::fromLonLatRad，q_hl_or 来自 fromYawPitchRollRad；
    w<0 时取负（getPositiveRealImag），与 FG 的编码唯一化一致。
    返回 (角度, 单位轴 x, y, z)。"""
    lon, lat = lon_deg * D2R, lat_deg * D2R
    zd2, yd2 = 0.5 * lon, -0.25 * math.pi - 0.5 * lat  # SGQuat.hxx 原式
    q1 = (math.cos(zd2) * math.cos(yd2),          # w
          -math.sin(zd2) * math.sin(yd2),         # x
          math.cos(zd2) * math.sin(yd2),          # y
          math.sin(zd2) * math.cos(yd2))          # z
    h2, p2, r2 = ((hdg_deg + 90.0) * D2R * 0.5, pitch_deg * D2R * 0.5,
                  roll_deg * D2R * 0.5)  # ψ = 罗盘航向 + 90（FG 内部约定）
    ch, sh = math.cos(h2), math.sin(h2)
    cp, sp = math.cos(p2), math.sin(p2)
    cr, sr = math.cos(r2), math.sin(r2)
    q2 = (cr * ch * cp + sr * sh * sp,           # w
          sr * ch * cp - cr * sh * sp,           # x (roll)
          cr * sp * ch + sr * cp * sh,           # y (pitch)
          cr * sh * cp - sr * ch * sp)           # z (yaw)
    # 与 SGQuat.hxx fromEulerRad 逐项核对（标准 ZYX 航空次序）
    q = _quat_mul(q1, q2)
    if q[0] < 0:
        q = (-q[0], -q[1], -q[2], -q[3])
    angle = 2.0 * math.acos(max(-1.0, min(1.0, q[0])))
    s = math.sin(angle * 0.5)
    if abs(s) < 1e-12:
        return 0.0, 1.0, 0.0, 0.0
    return angle, q[1] / s, q[2] / s, q[3] / s


def angle_axis_to_euler(lat_deg, lon_deg, ux, uy, uz, angle):
    """角轴 → (hdg_deg, pitch_deg, roll_deg)。

    FG 的 MP 姿态是 q_ec2hl · q_hl_or 的合成四元数；服务端要还原的是
    机体相对水平系的欧拉角，因此先由位置反解 q_ec2hl = fromLonLatRad，
    取共轭左乘，再按 SGQuat::getEulerRad 提取 (z=yaw, y=pitch, x=roll)，
    最后 yaw−90° 转回罗盘航向。"""
    if angle < 1e-8:
        return 0.0, 0.0, 0.0
    s = math.sin(angle * 0.5)
    q = (math.cos(angle * 0.5), ux * s, uy * s, uz * s)
    # q1 = fromLonLatRad(lon, lat)（与 quat_to_angle_axis 同式）
    lon, lat = lon_deg * D2R, lat_deg * D2R
    zd2, yd2 = 0.5 * lon, -0.25 * math.pi - 0.5 * lat
    q1 = (math.cos(zd2) * math.cos(yd2),
          -math.sin(zd2) * math.sin(yd2),
          math.cos(zd2) * math.sin(yd2),
          math.sin(zd2) * math.cos(yd2))
    q1c = (q1[0], -q1[1], -q1[2], -q1[3])   # 共轭（单位四元数的逆）
    qor = _quat_mul(q1c, q)
    w, x, y, z = qor
    # SGQuat::getEulerRad 原式
    rol = math.degrees(math.atan2(2.0 * (y * z + w * x),
                                  w * w - x * x - y * y + z * z))
    pit = math.degrees(-math.asin(max(-1.0, min(1.0, 2.0 * (x * z - w * y)))))
    psi = math.atan2(2.0 * (x * y + w * z), w * w + x * x - y * y - z * z)
    if psi < 0:
        psi += 2.0 * math.pi
    return (math.degrees(psi) - 90.0) % 360.0, pit, rol

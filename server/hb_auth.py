"""心跳票据验证：防重放 HMAC。

与 anticheatd L5_Heartbeat 配合：
- 共享密钥 K = 独立随机 32 字节，编译进 anticheatd 二进制
  （选手必须逆向 anticheatd 才能提取 K — 这是 flag2 想考的）
- 每跳心跳：anticheatd 发送 ticket = HMAC-SHA256(K, "seq|callsign|ts")
- 服务端验证：HMAC 正确 + seq 严格递增 + ts 在时间窗口内

抓包重放攻击：
  - 重放同一包 → seq 已见，拒绝
  - 改 seq 重放 → HMAC 对不上（不知道 K）
  - 改 ts 重放 → HMAC 对不上（不知道 K）
  - 从 env.lock 推算 K → 不可能（K 是独立随机数，不来自 env.lock）

⚠ 密钥文件 hb_secret.key 为 32 字节原始二进制，勿提交到版本控制。
"""
import hashlib
import hmac
import json
import os
import time


def generate_key() -> bytes:
    """生成随机 32 字节密钥并返回。"""
    return os.urandom(32)


def load_secret_key(key_path: str) -> bytes:
    """从文件加载共享密钥 K（32 字节原始二进制）。

    密钥文件由出题人独立生成，不依赖 env.lock。
    anticheatd C++ 端将同样的 32 字节编译进二进制（如 static const uint8_t[]）。
    """
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Secret key not found: {key_path}\n"
                                f"  Generate: python -c \"from server.hb_auth import generate_key; "
                                f"open('{key_path}','wb').write(generate_key())\"")

    with open(key_path, "rb") as f:
        key = f.read()

    if len(key) != 32:
        raise ValueError(f"Secret key must be 32 bytes, got {len(key)} bytes: {key_path}")
    return key


def verify_ticket(ticket: str, callsign: str, seq: int, ts: float,
                  secret: bytes, time_window: float = 30.0) -> bool:
    """验证单条心跳票据。

    参数：
        ticket: HMAC 十六进制字符串 (64 hex chars)
        callsign: 玩家呼号
        seq: 单调递增序号
        ts: 客户端时间戳
        secret: 共享密钥 K
        time_window: ts 允许的时间偏差（秒），防止时钟偏移

    返回：True 表示票据有效
    """
    now = time.time()
    if abs(now - ts) > time_window:
        return False

    expected = hmac_ticket(secret, callsign, seq, ts)
    return hmac.compare_digest(expected, ticket.lower())


def hmac_ticket(secret: bytes, callsign: str, seq: int, ts: float) -> str:
    """计算 HMAC 票据（用于自验、测试、C++ 端参考实现）。"""
    msg = f"{seq}|{callsign}|{ts:.3f}"
    return hmac.new(secret, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_heartbeat(raw_data: bytes, secret: bytes,
                     state: dict, time_window: float = 30.0) -> dict | None:
    """验证一条心跳 JSON，更新状态，返回 result 或 None。

    参数：
        raw_data:    心跳 UDP 包的原始字节
        secret:      共享密钥 K
        state:       {callsign → {"last_seq": int, "last_ts": float}}
        time_window: 时间窗口

    返回：{callsign, ts, seq} 或 None（验证失败）
    """
    try:
        hb = json.loads(raw_data.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None

    cs = hb.get("callsign", "")
    seq = hb.get("seq")
    ts = hb.get("ts")
    ticket = hb.get("ticket", "")

    if not isinstance(cs, str) or not cs:
        return None
    if not isinstance(seq, int) or seq < 0:
        return None
    if not isinstance(ts, (int, float)):
        return None
    if not isinstance(ticket, str) or len(ticket) != 64:
        return None

    # 1. seq 单调递增（防重放同一票据）
    prev_state = state.get(cs)
    if prev_state:
        if seq <= prev_state["last_seq"]:
            return None
        if ts < prev_state["last_ts"] - 5.0:
            return None

    # 2. HMAC 验证
    if not verify_ticket(ticket, cs, seq, ts, secret, time_window):
        return None

    # 验证通过，更新状态
    state[cs] = {"last_seq": seq, "last_ts": ts}
    return {"callsign": cs, "ts": ts, "seq": seq}
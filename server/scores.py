"""比赛 flag 与发放。

规则（doc2 §2 三条铁律）：
- flag 绝不静态存在于客户端；
- flag = HMAC(K_server, userid ‖ checkpoint)，每人不同，答案共享无效；
- K_server 只存在于判决服务器，与反作弊的 K 完全解耦（风险 R7）。

部署时通过环境变量注入服务端密钥：
    CTF_FLAG_KEY       直接给密钥字符串（开发默认值仅用于联调！）
    CTF_FLAG_KEY_FILE  或给一个密钥文件路径（推荐，权限 600）
"""
import hashlib
import hmac
import os

# 开发/联调默认密钥。正式比赛必须通过环境变量覆盖。
_DEV_KEY = b"ctf-dev-key-change-me"

CHECKPOINTS = {
    1: "flag1-approach",
    2: "flag2-ghosttrack",
    3: "flag3-phantom",
}


def load_key() -> bytes:
    path = os.environ.get("CTF_FLAG_KEY_FILE")
    if path:
        with open(path, "rb") as f:
            key = f.read().strip()
        if key:
            return key
    env = os.environ.get("CTF_FLAG_KEY")
    if env:
        return env.encode("utf-8")
    return _DEV_KEY


def issue_flag(uid: str, checkpoint, key: bytes = None) -> str:
    """flagN = HMAC(K_server, userid ‖ checkpoint)，取前 32 个 hex 字符。"""
    if isinstance(checkpoint, int):
        checkpoint = CHECKPOINTS[checkpoint]
    key = key or load_key()
    msg = f"{uid}|{checkpoint}".encode("utf-8")
    return "flag{" + hmac.new(key, msg, hashlib.sha256).hexdigest()[:32] + "}"


def callsign_risks(callsign: str) -> list:
    """doc3 §4 的补充风险：callsign 只是 8 字节自由文本，当 userid 用有歧义。"""
    risks = []
    if len(callsign.encode("utf-8", "ignore")) > 8:
        risks.append("callsign 超过 8 字节，MP 头会截断（应为 8 字节以内 ASCII）")
    if callsign.lower() != callsign:
        risks.append("MP 命名空间大小写不敏感（FG 内部按小写合并），"
                     "大小写变体在服务端应视为同一 userid")
    return risks

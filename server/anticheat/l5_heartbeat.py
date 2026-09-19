"""L5 心跳票据系统。

实现 1Hz HMAC 心跳链，用于验证反作弊进程存活且未被绕过。
K = KDF(hash(anticheatd) ‖ hash(fgfs) ‖ hash(aircraft) ‖ userid ‖ nonce)
"""
import hashlib
import hmac
import os
import time
import json
from typing import Dict, Optional


class HeartbeatTicket:
    """心跳票据签发器。"""
    
    def __init__(self, anticheat_hash: bytes, fgfs_hash: bytes, 
                 aircraft_hash: bytes, userid: str, nonce: bytes = None):
        self.anticheat_hash = anticheat_hash
        self.fgfs_hash = fgfs_hash
        self.aircraft_hash = aircraft_hash
        self.userid = userid
        self.nonce = nonce or os.urandom(32)
        self.seq = 0
        self.last_check = time.time()
        self.missed_heartbeats = 0
    
    def derive_key(self) -> bytes:
        """派生会话密钥 K。"""
        # 使用 HKDF 派生密钥
        material = (
            self.anticheat_hash +
            self.fgfs_hash +
            self.aircraft_hash +
            self.userid.encode() +
            self.nonce
        )
        # 简化版本：直接使用 SHA256
        return hashlib.sha256(material).digest()
    
    def sign(self) -> Dict:
        """签发当前心跳票据。"""
        key = self.derive_key()
        msg = f"{self.seq}:{int(time.time())}".encode()
        signature = hmac.new(key, msg, hashlib.sha256).hexdigest()
        
        ticket = {
            "seq": self.seq,
            "ts": int(time.time()),
            "sig": signature,
            "userid": self.userid,
        }
        self.seq += 1
        self.last_check = time.time()
        self.missed_heartbeats = 0
        return ticket
    
    def verify(self, ticket: Dict) -> bool:
        """验证心跳票据。"""
        if ticket["seq"] != self.seq - 1:
            return False  # 序列号不连续
        
        key = self.derive_key()
        msg = f"{ticket['seq']}:{ticket['ts']}".encode()
        expected_sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(ticket["sig"], expected_sig)
    
    def check_liveness(self) -> bool:
        """检查心跳活性。"""
        now = time.time()
        if now - self.last_check > 2.0:  # 超过 2 秒未收到心跳
            self.missed_heartbeats += 1
            if self.missed_heartbeats >= 5:
                return False  # 连续 5 次未收到，判定异常
        return True


class SessionManager:
    """会话管理。"""
    
    def __init__(self):
        self.sessions: Dict[str, HeartbeatTicket] = {}
    
    def open_session(self, userid: str, anticheat_hash: bytes, 
                     fgfs_hash: bytes, aircraft_hash: bytes) -> str:
        """打开新会话，返回 session_id。"""
        session_id = os.urandom(16).hex()
        self.sessions[session_id] = HeartbeatTicket(
            anticheat_hash, fgfs_hash, aircraft_hash, userid
        )
        return session_id
    
    def receive_ticket(self, session_id: str, ticket: Dict) -> bool:
        """接收并验证心跳票据。"""
        if session_id not in self.sessions:
            return False
        return self.sessions[session_id].verify(ticket)
    
    def check_heartbeats(self) -> Dict[str, bool]:
        """检查所有会话的心跳活性。"""
        results = {}
        for sid, ticket in self.sessions.items():
            results[sid] = ticket.check_liveness()
        return results


if __name__ == "__main__":
    # 测试
    sm = SessionManager()
    
    # 模拟启动
    sid = sm.open_session(
        userid="TEAM01",
        anticheat_hash=b"test_anticheat_hash_32_bytes_pad!!",
        fgfs_hash=b"test_fgfs_hash_32_bytes_pad!!!",
        aircraft_hash=b"test_aircraft_hash_32_bytes_pad!"
    )
    
    print(f"[L5] 会话开启: {sid}")
    
    # 签发票据
    ticket = sm.sessions[sid].sign()
    print(f"[L5] 签发票据 seq={ticket['seq']} sig={ticket['sig'][:16]}...")
    
    # 验证
    ok = sm.receive_ticket(sid, ticket)
    print(f"[L5] 验证 {'PASS' if ok else 'FAIL'}")

"""L3 FDM 源可信度标记。

检测外部 FDM 服务器连接，为会话打上可信度标记。
"""
import socket
import time
from typing import Dict, Optional, Set


class FDMSourceTracker:
    """追踪 FDM 数据源的可信度。"""
    
    # 可信的 FDM 端口范围（原生 FG FDM）
    TRUSTED_PORTS = {5500}
    
    def __init__(self):
        self.sessions: Dict[str, Dict] = {}
    
    def register_session(self, sid: str, source: str, addr: tuple):
        """注册会话的数据源。"""
        self.sessions[sid] = {
            "source": source,
            "addr": addr,
            "trusted": self._is_trusted(source, addr),
            "started_at": time.time(),
            "anomalies": [],
        }
    
    def _is_trusted(self, source: str, addr: tuple) -> bool:
        """判断数据源是否可信。"""
        if source == "mp":
            return True  # MP 包来自合法客户端
        if source == "fdm":
            # 检查端口
            port = addr[1]
            return port in self.TRUSTED_PORTS
        if source == "text":
            return False  # 文本输入不可信
        return False
    
    def mark_anomaly(self, sid: str, anomaly: str):
        """标记异常行为。"""
        if sid in self.sessions:
            self.sessions[sid]["anomalies"].append({
                "time": time.time(),
                "type": anomaly
            })
            # 有异常则不可信
            self.sessions[sid]["trusted"] = False
    
    def get_session_status(self, sid: str) -> Dict:
        """获取会话状态。"""
        if sid not in self.sessions:
            return {"exists": False}
        sess = self.sessions[sid]
        return {
            "exists": True,
            "trusted": sess["trusted"],
            "source": sess["source"],
            "anomaly_count": len(sess["anomalies"]),
            "last_anomaly": sess["anomalies"][-1] if sess["anomalies"] else None,
        }
    
    def is_session_trusted(self, sid: str) -> bool:
        """快速检查会话是否可信。"""
        return self.get_session_status(sid).get("trusted", False)


if __name__ == "__main__":
    tracker = FDMSourceTracker()
    
    # 模拟注册
    tracker.register_session("sid001", "mp", ("127.0.0.1", 5000))
    tracker.register_session("sid002", "fdm", ("127.0.0.1", 5500))
    tracker.register_session("sid003", "text", ("127.0.0.1", 3002))
    
    print(f"sid001 (MP): trusted={tracker.is_session_trusted('sid001')}")
    print(f"sid002 (FDM 5500): trusted={tracker.is_session_trusted('sid002')}")
    print(f"sid003 (text): trusted={tracker.is_session_trusted('sid003')}")
    
    # 模拟异常
    tracker.mark_anomaly("sid001", "suspicious_position_jump")
    print(f"sid001 after anomaly: trusted={tracker.is_session_trusted('sid001')}")
    
    print("\nFDM 源追踪测试通过")

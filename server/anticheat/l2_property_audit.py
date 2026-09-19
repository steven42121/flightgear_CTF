"""L2 属性树写入审计。

监控 FG 属性树的关键写入操作，检测恶意修改。
通过 FG 的 telnet/httpd 接口实现。
"""
import socket
import time
from typing import Dict, List, Tuple


# 需要监控的属性前缀
MONITORED_PREFIXES = [
    "/position/",
    "/velocities/",
    "/orientation/",
    "/sim/freeze/",
    "/sim/time/speed-up",
    "/environment/",
    "/controls/flight/",
]


class PropertyAudit:
    """属性树写入审计器。"""
    
    def __init__(self, fg_telnet_host: str = "127.0.0.1", fg_telnet_port: int = 5401):
        self.host = fg_telnet_host
        self.port = fg_telnet_port
        self.writes: Dict[str, List[float]] = {}  # prop -> timestamps
        self.alarm_count = 0
    
    def _connect(self) -> socket.socket:
        """连接到 FG telnet 接口。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.host, self.port))
            return sock
        except Exception as e:
            print(f"[L2] telnet 连接失败: {e}")
            return None
    
    def query_prop(self, prop: str) -> str:
        """查询属性值。"""
        sock = self._connect()
        if not sock:
            return None
        
        try:
            sock.send(f"get {prop}\n".encode())
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
            result = data.decode().strip()
            return result.split("\n")[-1] if result else None
        except Exception as e:
            return None
        finally:
            sock.close()
    
    def check_suspicious_write(self, prop: str, value: any = None) -> bool:
        """检查可疑写入。"""
        for prefix in MONITORED_PREFIXES:
            if prop.startswith(prefix):
                # 记录写入时间
                now = time.time()
                if prop not in self.writes:
                    self.writes[prop] = []
                self.writes[prop].append(now)
                
                # 清理超过 60 秒的记录
                self.writes[prop] = [t for t in self.writes[prop] if now - t < 60]
                
                # 检测高频写入（可能是自动化脚本）
                if len(self.writes[prop]) > 10:  # 60 秒内超过 10 次
                    self.alarm_count += 1
                    return True
                return False
        return False
    
    def get_summary(self) -> Dict:
        """获取审计摘要。"""
        return {
            "monitored_prefixes": MONITORED_PREFIXES,
            "alarms": self.alarm_count,
            "write_counts": {k: len(v) for k, v in self.writes.items()},
        }


if __name__ == "__main__":
    audit = PropertyAudit()
    print(f"[L2] 审计器初始化完成")
    print(f"[L2] 摘要: {audit.get_summary()}")

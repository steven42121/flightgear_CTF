"""反作弊协调器入口。

整合 L0-L5 各层检测，提供统一的 API 供 poller.py 调用。
设计参考 UltimateAntiCheat 的 AntiCheat.hpp 架构。
"""
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 添加 parent 目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.anticheat.l0_args import validate_args
from server.anticheat.l1_integrity import FileIntegrity
from server.anticheat.l2_property_audit import PropertyAudit
from server.anticheat.l5_heartbeat import SessionManager


class AntiCheatCoordinator:
    """反作弊协调器。"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.integrity = FileIntegrity(config.get("manifest_path"))
        self.audit = PropertyAudit(
            fg_telnet_host=config.get("fg_telnet_host", "127.0.0.1"),
            fg_telnet_port=config.get("fg_telnet_port", 5401)
        )
        self.session_mgr = SessionManager()
        self.status = "initialized"
        self.issues: List[str] = []
    
    def validate_launch(self, args: List[str]) -> Tuple[bool, List[str]]:
        """L0: 启动参数校验。"""
        valid, issues = validate_args(args)
        if not valid:
            self.issues.extend(issues)
            self.status = "blocked"
        return valid, issues
    
    def verify_integrity(self, paths: List[str]) -> List[Tuple[str, bool, str]]:
        """L1: 文件哈希校验。"""
        return self.integrity.verify_all(paths)
    
    def start_session(self, userid: str, fg_pid: int = None) -> str:
        """L5: 开启心跳会话。"""
        # TODO: 获取实际哈希值
        anticheat_hash = b"anticheat_placeholder"
        fgfs_hash = b"fgfs_placeholder"
        aircraft_hash = b"aircraft_placeholder"
        
        return self.session_mgr.open_session(
            userid, anticheat_hash, fgfs_hash, aircraft_hash
        )
    
    def receive_heartbeat(self, session_id: str, ticket: Dict) -> bool:
        """L5: 接收心跳票据。"""
        return self.session_mgr.receive_ticket(session_id, ticket)
    
    def get_status(self) -> Dict:
        """获取反作弊状态摘要。"""
        return {
            "status": self.status,
            "issues": self.issues,
            "active_sessions": len(self.session_mgr.sessions),
            "alarms": self.audit.alarm_count,
        }


def load_config(config_path: str = None) -> Dict:
    """加载配置。"""
    import yaml
    if config_path:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {
        "fg_telnet_host": "127.0.0.1",
        "fg_telnet_port": 5401,
        "manifest_path": None,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--mode", choices=["launch", "session", "status"], default="status")
    ap.add_argument("--args", nargs="*", default=[])
    args = ap.parse_args()
    
    config = load_config(args.config)
    ac = AntiCheatCoordinator(config)
    
    if args.mode == "launch":
        ok, issues = ac.validate_launch(args.args)
        print(json.dumps({"valid": ok, "issues": issues}, indent=2))
    elif args.mode == "status":
        print(json.dumps(ac.get_status(), indent=2))

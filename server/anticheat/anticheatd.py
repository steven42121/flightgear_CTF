#!/usr/bin/env python3
"""
anticheatd - 反作弊守护进程

基于 VMAware + UltimateAntiCheat 设计思想实现。
L0-L5 分层防护，1Hz 心跳票据验证。

用法:
    python -m server.anticheat.anticheatd --mode daemon [--config config.json]
    python -m server.anticheat.anticheatd --mode check [--args ...]
    python -m server.anticheat.anticheatd --mode session --userid TEAM01
    python -m server.anticheat.anticheatd --mode selfcheck
"""
import argparse
import hashlib
import hmac
import json
import os
import socket
import struct
import sys
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from server.anticheat.l0_args import validate_args
from server.anticheat.l1_integrity import FileIntegrity
from server.anticheat.l2_property_audit import PropertyAudit
from server.anticheat.l3_fdm_tracker import FDMSourceTracker
from server.anticheat.l4_integrity import ProcessIntegrity
from server.anticheat.l5_heartbeat import SessionManager
from server.anticheat.vmaware_detector import VMDetector
from server.anticheat.integrity_checker import IntegrityChecker
from server.anticheat.report import AntiCheatReport, create_report


class AntiCheatDaemon:
    """反作弊守护进程主类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.running = False
        self.heartbeat_thread = None
        self.session_id = None
        
        # 初始化各层检测器
        self.l1 = FileIntegrity(config.get("file_hashes"))
        self.l2 = PropertyAudit(
            config.get("fg_telnet_host", "127.0.0.1"),
            config.get("fg_telnet_port", 5401)
        )
        self.l3 = FDMSourceTracker()
        self.l4 = ProcessIntegrity()
        self.l5 = SessionManager()
        self.vm_detector = VMDetector()
        self.pe_checker = IntegrityChecker(config.get("expected_hashes"))
        
        self.report = create_report()
    
    def startup_check(self, args: List[str]) -> bool:
        """L0 启动时完整性检查"""
        print("[L0] Checking launch arguments...")
        valid, issues = validate_args(args)
        
        if not valid:
            print("[L0] FAILED:")
            for issue in issues:
                print(f"  - {issue}")
            self.report.add_layer("L0_Args", {"status": "BLOCKED", "issues": issues})
            return False
        
        print("[L0] PASSED")
        self.report.add_layer("L0_Args", {"status": "PASS"})
        
        # L1 文件完整性
        print("[L1] Checking file integrity...")
        l1_results = []
        for path in ["server/poller.py", "launcher.sh"]:
            fp = Path(__file__).parent.parent.parent / path
            if fp.exists():
                ok, msg = self.l1.verify_file_integrity(str(fp))
                l1_results.append(msg)
                if not ok:
                    self.report.add_layer("L1_Integrity", {"status": "BLOCKED", "details": msg})
                    return False
        
        self.report.add_layer("L1_Integrity", {"status": "PASS", "files_checked": l1_results})
        print("[L1] PASSED")
        return True
    
    def start_heartbeat(self, userid: str) -> str:
        """启动心跳并返回 session ID"""
        # 派生会话密钥
        anticheat_hash = hashlib.sha256(Path(__file__).read_bytes()).digest()
        fgfs_hash = hashlib.sha256(b"fgfs_placeholder").digest()
        aircraft_hash = hashlib.sha256(b"c172p_placeholder").digest()
        
        self.session_id = self.l5.open_session(
            userid, anticheat_hash, fgfs_hash, aircraft_hash
        )
        
        # 启动心跳线程
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        print(f"[L5] Heartbeat started, session: {self.session_id[:8]}...")
        self.report.add_layer("L5_Heartbeat", {"status": "ACTIVE", "session_id": self.session_id})
        
        return self.session_id
    
    def _heartbeat_loop(self):
        """心跳循环 - 每秒发送一次"""
        while self.running:
            if self.session_id and self.session_id in self.l5.sessions:
                ticket = self.l5.sessions[self.session_id].sign()
                if ticket["seq"] % 10 == 0:
                    print(f"[L5] Heartbeat seq={ticket['seq']} sig={ticket['sig'][:16]}...")
            time.sleep(1)
    
    def stop(self):
        """停止守护进程"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=2)
        print("[anticheatd] Stopped")
    
    def run_selfcheck(self) -> Dict:
        """运行完整自检"""
        print("\n" + "=" * 60)
        print("MAYDAY CTF Anticheat Self-Check")
        print("=" * 60)
        
        # VM 检测
        print("\n[Anti-VM] Checking virtualization...")
        vm_report = self.vm_detector.get_report()
        print(f"  VM Detected: {vm_report['vm_detected']}")
        print(f"  VM Brand: {vm_report['vm_brand']}")
        self.report.add_layer("Anti-VM", {
            "status": "BLOCKED" if vm_report['vm_detected'] else "PASS",
            "brand": vm_report['vm_brand']
        })
        
        # 进程完整性
        print("\n[Process] Checking integrity...")
        proc_status = self.l4.get_status()
        print(f"  Status: {proc_status['integrity_level']}")
        self.report.add_layer("L4_Process", proc_status)
        
        # 输出总结
        print("\n" + "=" * 60)
        print(f"Overall Status: {self.report.overall_status}")
        print("=" * 60)
        
        return self.report.to_dict()


def main():
    parser = argparse.ArgumentParser(
        description="MAYDAY CTF Anti-Cheat Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Self-check before launch
  python -m server.anticheat.anticheatd --mode selfcheck
  
  # Validate launch arguments
  python -m server.anticheat.anticheatd --mode check -- --aircraft=c172p --addon=./ctf-addon
  
  # Start daemon with session
  python -m server.anticheat.anticheatd --mode daemon --userid TEAM01
        """
    )
    
    parser.add_argument("--mode", choices=["daemon", "check", "session", "selfcheck"],
                       default="selfcheck", help="Operation mode")
    parser.add_argument("--config", default=None, help="Config file path (JSON)")
    parser.add_argument("--userid", default=None, help="User ID for session")
    parser.add_argument("args", nargs="*", help="Launch arguments")
    args = parser.parse_args()
    
    # 加载配置
    config = {}
    if args.config and os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = json.load(f)
    
    daemon = AntiCheatDaemon(config)
    
    if args.mode == "selfcheck":
        result = daemon.run_selfcheck()
        sys.exit(0 if result["overall"] == "PASS" else 1)
    elif args.mode == "check":
        valid, issues = validate_args(args.args)
        print(json.dumps({"valid": valid, "issues": issues}, indent=2))
        sys.exit(0 if valid else 1)
    elif args.mode == "session":
        if not args.userid:
            print("Error: --userid required", file=sys.stderr)
            sys.exit(1)
        daemon.startup_check([])
        sid = daemon.start_heartbeat(args.userid)
        print(json.dumps({"session_id": sid}, indent=2))
    elif args.mode == "daemon":
        if not args.userid:
            print("Error: --userid required", file=sys.stderr)
            sys.exit(1)
        daemon.startup_check(sys.argv[1:])
        daemon.start_heartbeat(args.userid)
        print("[anticheatd] Running as daemon...")
        try:
            while daemon.running:
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()


if __name__ == "__main__":
    main()

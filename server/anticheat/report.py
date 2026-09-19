"""反作弊综合检查结果。

整合 L0-L5 所有层级的检查结果。
"""
import json
from typing import Dict, List, Optional


class AntiCheatReport:
    """反作弊报告。"""
    
    def __init__(self):
        self.layers: Dict[str, Dict] = {}
        self.overall_status = "unknown"
    
    def add_layer(self, name: str, result: Dict):
        """添加一层检查结果。"""
        self.layers[name] = result
        self._update_overall()
    
    def _update_overall(self):
        """更新总体状态。"""
        # 任何一层拒绝 → 整体拒绝
        for layer, result in self.layers.items():
            if result.get("status") == "BLOCKED":
                self.overall_status = "BLOCKED"
                return
            if result.get("status") == "ALERT":
                self.overall_status = "ALERT"
        
        if not self.layers:
            self.overall_status = "UNKNOWN"
        else:
            self.overall_status = "PASS"
    
    def to_dict(self) -> Dict:
        """转换为字典。"""
        return {
            "overall": self.overall_status,
            "layers": self.layers,
        }
    
    def to_json(self) -> str:
        """转换为 JSON。"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# 快捷函数
def create_report() -> AntiCheatReport:
    return AntiCheatReport()


if __name__ == "__main__":
    report = AntiCheatReport()
    report.add_layer("L0_args", {"status": "PASS", "details": "启动参数合法"})
    report.add_layer("L1_integrity", {"status": "PASS", "details": "文件哈希匹配"})
    report.add_layer("L2_property", {"status": "PASS", "details": "无异常写入"})
    report.add_layer("L3_fdm", {"status": "PASS", "details": "FDM 源可信"})
    report.add_layer("L5_heartbeat", {"status": "PASS", "details": "心跳正常"})
    
    print(report.to_json())

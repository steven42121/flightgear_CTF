"""L1 文件哈希校验。

验证关键文件（fgfs 二进制、机型数据、addon）的 SHA256 哈希。
设计参考 UltimateAntiCheat 的 Integrity 模块思路。
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple


class FileIntegrity:
    """文件完整性校验器。"""
    
    def __init__(self, manifest_path: str = None):
        self.manifest = {}
        self.manifest_path = manifest_path
        
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                self.manifest = json.load(f)
    
    def compute_hash(self, filepath: str) -> str:
        """计算文件 SHA256。"""
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    
    def verify(self, path: str, expected_hash: str = None) -> Tuple[bool, str]:
        """验证明知文件。"""
        if not os.path.exists(path):
            return False, f"文件不存在: {path}"
        
        actual = self.compute_hash(path)
        
        if expected_hash:
            if actual != expected_hash:
                return False, f"哈希不匹配: {path}"
        else:
            # 从 manifest 查找
            key = os.path.basename(path)
            if key in self.manifest:
                if actual != self.manifest[key]:
                    return False, f"哈希不匹配: {path}"
        
        return True, actual
    
    def verify_all(self, paths: List[str]) -> List[Tuple[str, bool, str]]:
        """批量验证。"""
        results = []
        for path in paths:
            ok, msg = self.verify(path)
            results.append((path, ok, msg))
        return results


def generate_manifest(paths: List[str], output: str = None) -> Dict[str, str]:
    """生成哈希清单（用于 P0 基线阶段）。"""
    manifest = {}
    for path in paths:
        if os.path.exists(path):
            manifest[os.path.basename(path)] = FileIntegrity().compute_hash(path)
    
    if output:
        with open(output, 'w') as f:
            json.dump(manifest, f, indent=2)
    
    return manifest


if __name__ == "__main__":
    # 测试
    integrity = FileIntegrity()
    
    # 验证自身
    self_path = __file__
    ok, msg = integrity.verify(self_path)
    print(f"[{'PASS' if ok else 'FAIL'}] {self_path}: {msg}")

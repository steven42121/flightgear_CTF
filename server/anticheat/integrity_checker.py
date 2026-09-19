"""
UltimateAntiCheat 风格完整性检查模块
参考: https://github.com/AlSch092/UltimateAntiCheat
AGPL 许可 - 仅参考架构设计，不复制代码
"""
import hashlib
import os
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class IntegrityChecker:
    """完整性检查器 - 检测文件篡改和内存注入"""
    
    def __init__(self, expected_hashes: Dict[str, str] = None):
        self.expected_hashes = expected_hashes or {}
        self.sections = {}
        self.imports = []
    
    def calculate_file_hash(self, filepath: str) -> str:
        """计算文件 SHA256 哈希"""
        h = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            return h.hexdigest()
        except (IOError, OSError):
            return ""
    
    def verify_file_integrity(self, filepath: str) -> Tuple[bool, str]:
        """验证文件完整性"""
        if not os.path.exists(filepath):
            return False, f"File not found: {filepath}"
        
        actual_hash = self.calculate_file_hash(filepath)
        expected_hash = self.expected_hashes.get(os.path.basename(filepath))
        
        if expected_hash and actual_hash != expected_hash:
            return False, f"Hash mismatch: {filepath}"
        
        return True, f"OK: {filepath}"
    
    def check_pe_sections(self, filepath: str) -> Dict:
        """检查 PE 文件节区（Windows .exe/.dll）"""
        result = {
            "valid": True,
            "sections": [],
            "warnings": []
        }
        
        try:
            with open(filepath, 'rb') as f:
                # 读取 DOS 头
                dos_header = f.read(64)
                if dos_header[:2] != b'MZ':
                    result["warnings"].append("Not a PE file")
                    return result
                
                # 获取 PE 偏移
                pe_offset = struct.unpack('<I', dos_header[60:64])[0]
                f.seek(pe_offset)
                
                # 读取 PE 签名
                pe_sig = f.read(4)
                if pe_sig != b'PE\x00\x00':
                    result["warnings"].append("Invalid PE signature")
                    return result
                
                # 读取 COFF 头
                coff_header = f.read(20)
                num_sections = struct.unpack('<H', coff_header[6:8])[0]
                section_size = struct.unpack('<H', coff_header[2:4])[0]
                
                # 读取节区表
                for i in range(num_sections):
                    section = f.read(40)
                    if len(section) < 40:
                        break
                    
                    name = section[0:8].split(b'\x00')[0].decode('ascii', errors='ignore')
                    virt_size = struct.unpack('<I', section[8:12])[0]
                    virt_addr = struct.unpack('<I', section[12:16])[0]
                    raw_size = struct.unpack('<I', section[16:20])[0]
                    raw_ptr = struct.unpack('<I', section[20:24])[0]
                    characteristics = struct.unpack('<I', section[36:40])[0]
                    
                    # 检查可疑特征
                    warnings = []
                    if characteristics & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
                        warnings.append("Executable")
                    if characteristics & 0x80000000:  # IMAGE_SCN_MEM_WRITE
                        warnings.append("Writable")
                    if characteristics & 0x40000000:  # IMAGE_SCN_MEM_READ
                        warnings.append("Readable")
                    
                    result["sections"].append({
                        "name": name,
                        "virtual_size": virt_size,
                        "virtual_address": hex(virt_addr),
                        "raw_size": raw_size,
                        "characteristics": warnings
                    })
                    
                    # 可疑节区名
                    suspicious_names = ['.text', '.rsrc', '.data', '.bss']
                    if name and not any(name.startswith(s) for s in suspicious_names):
                        if len(name) > 0 and name[0] == '.':
                            result["warnings"].append(f"Suspicious section name: {name}")
        
        except Exception as e:
            result["warnings"].append(f"PE parse error: {str(e)}")
            result["valid"] = False
        
        return result
    
    def scan_suspicious_patterns(self, filepath: str) -> List[str]:
        """扫描可疑字符串模式"""
        suspicious_patterns = [
            b'debugger', b'ollydbg', b'idaq', b'reverser',
            b'cheat engine', b'x32dbg', b'x64dbg',
            b'inject', b'patch', b'hook',
            b'frida', b'cycript', b' Frida ',
            b'/proc/self/maps', b'/proc/self/cmdline',
        ]
        
        found = []
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
                for pattern in suspicious_patterns:
                    if pattern in content:
                        found.append(pattern.decode('ascii', errors='ignore'))
        except:
            pass
        
        return found
    
    def get_full_report(self, filepath: str) -> Dict:
        """生成完整报告"""
        report = {
            "file": filepath,
            "hash": self.calculate_file_hash(filepath),
            "integrity_check": self.verify_file_integrity(filepath)[1],
            "pe_analysis": self.check_pe_sections(filepath),
            "suspicious_patterns": self.scan_suspicious_patterns(filepath),
            "overall_status": "PASS"
        }
        
        # 综合判断
        if report["pe_analysis"]["warnings"]:
            report["overall_status"] = "WARNING"
        if report["suspicious_patterns"]:
            report["overall_status"] = "SUSPICIOUS"
        
        return report


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="File Integrity Checker")
    parser.add_argument("filepath", help="File to check")
    parser.add_argument("--hashes", default=None, help="Expected hashes file (JSON)")
    args = parser.parse_args()
    
    checker = IntegrityChecker()
    
    if args.hashes and os.path.exists(args.hashes):
        import json
        with open(args.hashes, 'r') as f:
            checker.expected_hashes = json.load(f)
    
    report = checker.get_full_report(args.filepath)
    print(json.dumps(report, indent=2))

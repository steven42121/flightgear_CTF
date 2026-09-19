"""
VMAware 风格 VM 检测模块
参考: https://github.com/NotRequiem/VMAware
MIT 许可
"""
import platform
import subprocess
import os
import re
from typing import Tuple, List


class VMDetector:
    """虚拟化检测器 - 检测虚拟机环境"""
    
    VM_INDICATORS = {
        'vmware': ['vmware', 'vmware virtual platform', 'vmware, inc.'],
        'virtualbox': ['vbox', 'virtualbox', 'oracle america, inc.'],
        'qemu': ['qemu', 'kvm', 'openbsd/kvm'],
        'hyper_v': ['hyper-v', 'microsoft corporation'],
        'parallels': ['parallels', 'parallels virtual sandbox'],
    }
    
    def __init__(self):
        self.os_name = platform.system().lower()
        self.vm_detected = False
        self.vm_brand = "Unknown"
        self.detected_techniques = []
    
    def detect_windows(self) -> Tuple[bool, str, List[str]]:
        """Windows 虚拟化检测"""
        indicators = []
        
        # 1. CPUID Hypervisor bit (leaf 0x1, ecx[31])
        try:
            result = subprocess.run(
                ['powershell', '-Command', 
                 '$cpu = Get-CimInstance Win32_Processor; $cpu.HypervisorPresent'],
                capture_output=True, text=True
            )
            if 'True' in result.stdout:
                indicators.append("CPUID Hypervisor Present")
        except:
            pass
        
        # 2. 注册表检查
        reg_checks = [
            (r'HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\SystemManufacturer', 
             'SystemManufacturer', 'vmware|virtualbox|qemu|hyper-v'),
            (r'HKEY_LOCAL_MACHINE\\HARDWARE\\DESCRIPTION\\System\\BIOS',
             'SystemBIOS', 'vmware|virtualbox|qemu|mirror|american motherboard'),
            (r'HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Virtual Machine\\Guest\\Parameters',
             None, r'.*'),  # 任何键存在即警告
        ]
        
        for reg_path, key_name, pattern in reg_checks:
            try:
                result = subprocess.run(
                    ['powershell', '-Command',
                     f'Get-ItemProperty "{reg_path}" -ErrorAction SilentlyContinue'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    if key_name and key_name in result.stdout:
                        value = result.stdout.split(f'{key_name}')[1].split()[0] if key_name in result.stdout else ""
                        if re.search(pattern, value, re.IGNORECASE):
                            indicators.append(f"Registry: {key_name} matches {pattern}")
                    elif not key_name:
                        indicators.append(f"Registry path exists: {reg_path}")
            except:
                pass
        
        # 3. 进程检查
        try:
            result = subprocess.run(['tasklist', '/FO', 'CSV'], capture_output=True, text=True)
            vm_procs = ['vmtoolsd.exe', 'VBoxService.exe', 'VBoxTray.exe', 
                       'qemu-ga.exe', 'prl_cc.exe', 'prl_tools.exe', 'hyperv.exe']
            for proc in vm_procs:
                if proc.lower() in result.stdout.lower():
                    indicators.append(f"Process detected: {proc}")
        except:
            pass
        
        # 4. 服务检查
        try:
            result = subprocess.run(['sc', 'query'], capture_output=True, text=True)
            vm_services = ['VMTools', 'VBoxService', 'qemu-guest-agent', 'Parallels']
            for svc in vm_services:
                if svc.lower() in result.stdout.lower():
                    indicators.append(f"Service detected: {svc}")
        except:
            pass
        
        return len(indicators) > 0, self._detect_brand(indicators), indicators
    
    def detect_linux(self) -> Tuple[bool, str, List[str]]:
        """Linux 虚拟化检测"""
        indicators = []
        
        # 1. /proc/cpuinfo hypervisor flag
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
            if 'hypervisor' in cpuinfo:
                indicators.append("/proc/cpuinfo hypervisor flag")
        except:
            pass
        
        # 2. DMI/SMBIOS 信息
        dmi_paths = [
            '/sys/class/dmi/id/product_name',
            '/sys/class/dmi/id/sys_vendor',
            '/sys/class/dmi/id/bios_vendor',
            '/sys/class/dmi/id/board_vendor',
            '/sys/class/dmi/id/chassis_vendor',
        ]
        for path in dmi_paths:
            try:
                with open(path, 'r') as f:
                    content = f.read().lower()
                for vm_name, keywords in self.VM_INDICATORS.items():
                    for kw in keywords:
                        if kw in content:
                            indicators.append(f"{path}: {vm_name}")
                            break
            except:
                pass
        
        # 3. /dev 设备检查
        dev_checks = ['/dev/kvm', '/dev/vboxdrv', '/dev/vmci', '/dev/vhost-vsock']
        for dev in dev_checks:
            if os.path.exists(dev):
                indicators.append(f"Device exists: {dev}")
        
        # 4. 进程检查
        try:
            with open('/proc/asound/cards', 'r') as f:
                cards = f.read()
            vm_audio = ['Virtio', 'VMware', 'VirtualBox']
            for audio in vm_audio:
                if audio in cards:
                    indicators.append(f"Audio device: {audio}")
        except:
            pass
        
        # 5. lspci/lshw 检查（如有）
        try:
            result = subprocess.run(['lspci'], capture_output=True, text=True)
            vm_hardware = ['VMware', 'VirtualBox', 'QEMU']
            for hw in vm_hardware:
                if hw in result.stdout:
                    indicators.append(f"PCI device: {hw}")
        except:
            pass
        
        return len(indicators) > 0, self._detect_brand(indicators), indicators
    
    def _detect_brand(self, indicators: List[str]) -> str:
        """根据检测指标判断 VM 品牌"""
        for indicator in indicators:
            ind_lower = indicator.lower()
            if 'vmware' in ind_lower:
                return "VMware"
            elif 'virtualbox' in ind_lower or 'vbox' in ind_lower:
                return "VirtualBox"
            elif 'qemu' in ind_lower or 'kvm' in ind_lower:
                return "QEMU/KVM"
            elif 'hyper-v' in ind_lower or 'microsoft' in ind_lower:
                return "Hyper-V"
            elif 'parallels' in ind_lower:
                return "Parallels"
        return "Unknown"
    
    def detect(self) -> Tuple[bool, str, List[str]]:
        """主检测入口"""
        if self.os_name == 'windows':
            return self.detect_windows()
        elif self.os_name == 'linux':
            return self.detect_linux()
        else:
            return False, "Unknown", [f"Unsupported OS: {self.os_name}"]
    
    def get_report(self) -> dict:
        """生成检测报告"""
        vm_detected, brand, techniques = self.detect()
        self.vm_detected = vm_detected
        self.vm_brand = brand
        self.detected_techniques = techniques
        
        return {
            "vm_detected": vm_detected,
            "vm_brand": brand,
            "techniques_used": len(techniques),
            "details": techniques,
            "recommendation": "BLOCK" if vm_detected else "ALLOW"
        }


if __name__ == "__main__":
    detector = VMDetector()
    report = detector.get_report()
    
    print("=" * 60)
    print("VM Detection Report")
    print("=" * 60)
    print(f"VM Detected: {report['vm_detected']}")
    print(f"VM Brand: {report['vm_brand']}")
    print(f"Techniques Used: {report['techniques_used']}")
    print(f"Recommendation: {report['recommendation']}")
    if report['details']:
        print("\nDetected indicators:")
        for detail in report['details']:
            print(f"  - {detail}")

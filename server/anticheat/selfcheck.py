"""anticheat-selfcheck：启动前自检工具。

检测虚拟化环境、FG 版本、依赖完整性。
设计参考 VMAware 的 VM 检测思路（CPUID、DMI、MAC OUI 等）。
"""
import platform
import subprocess
import sys
import os
from pathlib import Path
from typing import List, Tuple


def check_vm_linux() -> Tuple[bool, str]:
    """Linux 下检测虚拟化。"""
    issues = []
    
    # CPUID hypervisor bit
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
        if 'hypervisor' in cpuinfo:
            issues.append("CPU 显示 hypervisor flag")
    except:
        pass
    
    # DMI/SMBIOS
    dmi_paths = [
        '/sys/class/dmi/id/product_name',
        '/sys/class/dmi/id/sys_vendor',
        '/sys/class/dmi/id/bios_vendor',
    ]
    vm_indicators = ['vmware', 'virtualbox', 'qemu', 'kvm', 'hyper-v']
    for path in dmi_paths:
        try:
            with open(path, 'r') as f:
                content = f.read().lower()
            for indicator in vm_indicators:
                if indicator in content:
                    issues.append(f"DMI 检测到 {indicator}: {path}")
        except:
            pass
    
    # /dev/kvm
    if os.path.exists('/dev/kvm'):
        issues.append("/dev/kvm 存在")
    
    # 进程检测
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        vm_procs = ['vmtoolsd', 'VBoxService', 'qemu-ga', 'virtiofsd']
        for proc in vm_procs:
            if proc in result.stdout:
                issues.append(f"检测到 VM 进程: {proc}")
    except:
        pass
    
    return len(issues) == 0, "; ".join(issues) if issues else "通过"


def check_vm_windows() -> Tuple[bool, str]:
    """Windows 下检测虚拟化。"""
    issues = []
    
    # PowerShell 检测
    try:
        # CPUID hypervisor bit
        result = subprocess.run([
            'powershell', '-Command',
            '$cpu = Get-CimInstance Win32_Processor; $cpu.HypervisorPresent'
        ], capture_output=True, text=True)
        if 'True' in result.stdout:
            issues.append("CPUID 显示 hypervisor present")
        
        # 系统信息
        result = subprocess.run([
            'powershell', '-Command',
            '$cs = Get-CimInstance Win32_ComputerSystem; $cs.Model'
        ], capture_output=True, text=True)
        model = result.stdout.lower()
        vm_indicators = ['vmware', 'virtualbox', 'virtual pc', 'hyper-v']
        for ind in vm_indicators:
            if ind in model:
                issues.append(f"计算机型号包含 {ind}")
        
        # 注册表检测
        result = subprocess.run([
            'powershell', '-Command',
            'Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Virtual Machine\\Guest\\Parameters"'
        ], capture_output=True, text=True)
        if result.returncode == 0:
            issues.append("注册表检测到 Hyper-V 参数")
            
    except Exception as e:
        issues.append(f"PowerShell 检测失败: {e}")
    
    return len(issues) == 0, "; ".join(issues) if issues else "通过"


def check_fg_version(min_version: str = "2024.1") -> Tuple[bool, str]:
    """检查 FG 版本。"""
    try:
        result = subprocess.run(['fgfs', '--version'], capture_output=True, text=True)
        if result.returncode != 0:
            return False, "无法运行 fgfs"
        version_line = result.stdout.strip().split('\n')[0]
        print(f"  FG 版本: {version_line}")
        # 简化版本检查，实际应解析版本号
        return True, version_line
    except FileNotFoundError:
        return False, "fgfs 不在 PATH 中"


def check_dependencies() -> Tuple[bool, List[str]]:
    """检查必需文件/依赖。"""
    issues = []
    
    # 检查 FG 数据目录
    fg_root = os.environ.get('FG_ROOT', '/usr/share/games/flightgear')
    if not os.path.isdir(fg_root):
        issues.append(f"FG_ROOT 不存在: {fg_root}")
    
    # 检查 addon
    addon_path = Path(__file__).resolve().parent.parent.parent / "client" / "ctf-addon"
    if not addon_path.exists():
        issues.append(f"CTF addon 不存在: {addon_path}")
    
    return len(issues) == 0, issues


def main():
    print("=" * 60)
    print("MAYDAY CTF 反作弊自检工具")
    print("=" * 60)
    
    all_ok = True
    
    # 1. 虚拟化检测
    print("\n[1/4] 虚拟化环境检测...")
    system = platform.system()
    if system == "Linux":
        ok, msg = check_vm_linux()
    elif system == "Windows":
        ok, msg = check_vm_windows()
    else:
        ok, msg = False, f"不支持的操作系统: {system}"
    
    status = "✓ 通过" if ok else "✗ 失败"
    print(f"  {status}: {msg}")
    all_ok &= ok
    
    # 2. FG 版本检测
    print("\n[2/4] FlightGear 版本检测...")
    ok, msg = check_fg_version()
    status = "✓" if ok else "✗"
    print(f"  {status} {msg}")
    all_ok &= ok
    
    # 3. 依赖检查
    print("\n[3/4] 依赖完整性检查...")
    ok, issues = check_dependencies()
    if ok:
        print("  ✓ 所有依赖完整")
    else:
        print("  ✗ 缺少依赖:")
        for issue in issues:
            print(f"    - {issue}")
    all_ok &= ok
    
    # 4. 总结
    print("\n" + "=" * 60)
    if all_ok:
        print("✓ 自检通过，可以启动比赛")
        sys.exit(0)
    else:
        print("✗ 自检未通过，请修复上述问题")
        print("\n如需关闭虚拟化，请执行:")
        if system == "Windows":
            print("  bcdedit /set hypervisorlaunchtype off")
            print("  # 然后重启电脑")
        else:
            print("  # 请在 BIOS 中关闭 VT-x/SVM")
            print("  # 或使用物理机")
        sys.exit(1)


if __name__ == "__main__":
    main()

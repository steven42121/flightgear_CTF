#pragma once
#include <string>
#include <vector>

/**
 * 虚拟化检测：VM + VBS 双重检测。
 *
 * Phase 1 - VM 检测（传统 VM）：
 *   CPUID / SMBIOS / MAC OUI / 注册表 / 进程名
 *   识别 VMware / VirtualBox / QEMU-KVM / Hyper-V Guest / Parallels
 *
 * Phase 2 - VBS 检测（裸金属上的 Hypervisor）：
 *   当 CPUID HypervisorPresent=true 但非 VM 厂商时，判定为 VBS 开启：
 *     - Memory Integrity (HVCI)
 *     - Credential Guard
 *     - Virtualization-Based Security
 *   检出后提示：进入 BIOS 禁用 Virtualization Technology 或在
 *   Windows 安全中心关闭"内核隔离-内存完整性"。
 *
 * Windows 检测项：
 *   - Win32_ComputerSystem.HypervisorPresent
 *   - Win32_ComputerSystem.Manufacturer（真实硬件厂商 ≠ VM 厂商）
 *   - DeviceGuard HVCI 注册表
 *   - LsaCfgFlags（Credential Guard）
 *
 * Linux：
 *   - /proc/cpuinfo hypervisor flag
 *   - DMI/SMBIOS 字符串
 *   - /dev/kvm 存在
 */

class VMDetector {
public:
    struct VMDetectionResult {
        bool vm_detected;            // VM 或 VBS 任一检出
        bool vbs_detected;           // 单独标记 VBS（非 VM 的 hypervisor）
        std::string vm_brand;        // "VMware", "VirtualBox", "Hyper-V", "VBS", etc.
        int techniques_used;
        std::vector<std::string> details;
        std::string recommendation;  // "BLOCK" / "DISABLE_VBS" / "ALLOW"
    };

    VMDetectionResult detect() const;
    std::string brand() const;
    int percentage() const;

private:
    VMDetectionResult detect_windows() const;
    VMDetectionResult detect_linux() const;

    std::string detect_brand(const std::vector<std::string>& indicators) const;
    std::string read_file(const std::string& path) const;
    std::string exec_command(const std::string& cmd) const;

    mutable std::string current_brand_;
    mutable int current_percentage_;
};
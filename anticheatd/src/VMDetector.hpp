#pragma once
#include <string>
#include <vector>

/**
 * VM detection using VMAware techniques.
 *
 * Covers CPUID, DMI/SMBIOS, MAC OUI, hypervisor brand, process names.
 * Based on https://github.com/NotRequiem/VMAware (MIT license).
 *
 * Detection items (cross-platform):
 *   - Windows: Registry keys (Win32_ComputerSystem, Win32_BIOS),
 *              process names (vmtoolsd, VBoxService, qemu-ga),
 *              CPUID hypervisor bit
 *   - Linux: /proc/cpuinfo hypervisor flag, DMI strings, /dev/kvm,
 *            process/service names
 *   - Network: MAC OUI prefixes (VMware 00:50:56, VirtualBox 08:00:27)
 */

class VMDetector {
public:
    struct VMDetectionResult {
        bool vm_detected;
        std::string vm_brand;       // "VMware", "VirtualBox", "QEMU/KVM", "Hyper-V", "Unknown"
        int techniques_used;
        std::vector<std::string> details;
        std::string recommendation; // "BLOCK" or "ALLOW"
    };

    VMDetectionResult detect() const;
    std::string brand() const;
    int percentage() const;

private:
#ifdef _WIN32
    VMDetectionResult detect_windows() const;
#else
    VMDetectionResult detect_linux() const;
#endif

    std::string detect_brand(const std::vector<std::string>& indicators) const;
    std::string read_file(const std::string& path) const;
    std::string exec_command(const std::string& cmd) const;
};

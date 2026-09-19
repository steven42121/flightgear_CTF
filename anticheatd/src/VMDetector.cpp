#include "VMDetector.hpp"
#include "Logger.hpp"
#include <algorithm>
#include <iostream>
#include <fstream>
#include <sstream>
#include <filesystem>
#include <cctype>

namespace fs = std::filesystem;

std::string VMDetector::read_file(const std::string& path) const {
    std::ifstream file(path);
    if (!file) return "";
    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

std::string VMDetector::exec_command(const std::string& cmd) const {
#ifdef _WIN32
    FILE* pipe = _popen(cmd.c_str(), "r");
    if (!pipe) return "";
    char buffer[4096];
    std::stringstream result;
    while (fgets(buffer, sizeof(buffer), pipe)) {
        result << buffer;
    }
    _pclose(pipe);
    return result.str();
#else
    // Linux: use popen
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) return "";
    char buffer[4096];
    std::stringstream result;
    while (fgets(buffer, sizeof(buffer), pipe)) {
        result << buffer;
    }
    pclose(pipe);
    return result.str();
#endif
}

VMDetector::VMDetectionResult VMDetector::detect() const {
#ifdef _WIN32
    return detect_windows();
#else
    return detect_linux();
#endif
}

VMDetector::VMDetectionResult VMDetector::detect_windows() const {
    VMDetectionResult result;
    result.vbs_detected = false;
    std::vector<std::string> indicators;
    bool hypervisor_present = false;
    std::string manufacturer;
    std::string model;

    // ---- Phase 1: 传统 VM 检测 ----

    // 1. Win32_ComputerSystem (Manufacturer, Model, HypervisorPresent)
    {
        std::string cmd = "powershell -Command \"$cs = Get-CimInstance Win32_ComputerSystem; "
                          "Write-Host \\\"MANUFACTURER=$($cs.Manufacturer)\\\"; "
                          "Write-Host \\\"MODEL=$($cs.Model)\\\"; "
                          "Write-Host \\\"HYPERVISOR=$($cs.HypervisorPresent)\\\"\"";
        std::string output = exec_command(cmd);

        size_t pos = output.find("MANUFACTURER=");
        if (pos != std::string::npos) {
            size_t end = output.find('\n', pos);
            manufacturer = output.substr(pos + 13, end - pos - 13);
            while (!manufacturer.empty() && manufacturer.back() == '\r')
                manufacturer.pop_back();
        }

        pos = output.find("MODEL=");
        if (pos != std::string::npos) {
            size_t end = output.find('\n', pos);
            model = output.substr(pos + 6, end - pos - 6);
            while (!model.empty() && model.back() == '\r')
                model.pop_back();
        }

        pos = output.find("HYPERVISOR=");
        if (pos != std::string::npos) {
            size_t end = output.find('\n', pos);
            std::string hv = output.substr(pos + 11, end - pos - 11);
            hypervisor_present = (hv.find("True") != std::string::npos);
        }
    }

    // Known VM manufacturer keywords (case-insensitive)
    const char* vm_manufacturers[] = {"vmware", "virtualbox", "qemu", "parallels", "xen"};
    bool is_vm_manufacturer = false;
    {
        std::string lower_mfr = manufacturer;
        std::transform(lower_mfr.begin(), lower_mfr.end(), lower_mfr.begin(),
            [](unsigned char c){ return static_cast<char>(::tolower(c)); });
        for (const auto* vm : vm_manufacturers) {
            if (lower_mfr.find(vm) != std::string::npos) {
                is_vm_manufacturer = true;
                break;
            }
        }
    }

    bool is_vm_model = false;
    {
        std::string lower_model = model;
        std::transform(lower_model.begin(), lower_model.end(), lower_model.begin(),
            [](unsigned char c){ return static_cast<char>(::tolower(c)); });
        if (lower_model.find("virtual machine") != std::string::npos ||
            lower_model.find("virtual platform") != std::string::npos ||
            lower_model.find("kvm") != std::string::npos) {
            is_vm_model = true;
        }
    }

    // 2. Registry for VM indicators
    {
        const char* reg_keys[] = {
            "HKLM\\HARDWARE\\DESCRIPTION\\System",
        };
        const char* vm_ind[] = {"vmware", "virtualbox", "qemu", "hyper-v", "parallels"};

        for (const auto& key : reg_keys) {
            std::string cmd = "powershell -Command \"Get-ItemProperty '" + std::string(key) +
                              "' -ErrorAction SilentlyContinue | Out-String\"";
            std::string output = exec_command(cmd);
            for (const auto* ind : vm_ind) {
                if (output.find(ind) != std::string::npos) {
                    indicators.push_back("Registry BIOS contains: " + std::string(ind));
                }
            }
        }
    }

    // 3. VM processes
    {
        std::string procs = exec_command("tasklist /FO CSV");
        const char* vm_procs[] = {"vmtoolsd.exe", "VBoxService.exe", "VBoxTray.exe",
                                  "qemu-ga.exe", "prl_cc.exe", "prl_tools.exe"};
        for (const auto* proc : vm_procs) {
            if (procs.find(proc) != std::string::npos) {
                indicators.push_back("VM process: " + std::string(proc));
            }
        }
    }

    // 4. MAC OUI
    {
        std::string mac_output = exec_command(
            "powershell -Command \"Get-NetAdapter | Select-Object MacAddress\"");
        const char* vm_macs[] = {"00:50:56", "00:0C:29", "08:00:27"};
        for (const auto* mac : vm_macs) {
            if (mac_output.find(mac) != std::string::npos) {
                indicators.push_back("VM MAC OUI: " + std::string(mac));
            }
        }
    }

    // Phase 1 result
    if (!indicators.empty() || is_vm_manufacturer || is_vm_model) {
        if (is_vm_manufacturer && indicators.empty())
            indicators.push_back("VM manufacturer: " + manufacturer);
        if (is_vm_model && indicators.empty())
            indicators.push_back("VM model: " + model);

        result.vm_detected = true;
        result.vbs_detected = false;
        result.vm_brand = detect_brand(indicators);
        result.techniques_used = static_cast<int>(indicators.size());
        result.details = indicators;
        result.recommendation = "BLOCK";
        current_brand_ = result.vm_brand;
        current_percentage_ = 100;
        return result;
    }

    // ---- Phase 2: VBS 检测（非VM但hypervisor开着 = VBS/Memory Integrity）----
    std::vector<std::string> vbs_indicators;

    // Check 1: HypervisorPresent on genuine hardware
    if (hypervisor_present) {
        vbs_indicators.push_back("Hypervisor running on genuine hardware (not a VM)");
    }

    // Check 2: DeviceGuard HVCI (Memory Integrity) registry
    {
        std::string reg = exec_command(
            "powershell -Command \"Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\"
            "DeviceGuard\\Scenarios\\HypervisorEnforcedCodeIntegrity' "
            "-Name Enabled -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty Enabled\"");
        if (reg.find('1') != std::string::npos) {
            vbs_indicators.push_back("Memory Integrity (HVCI) is enabled (DeviceGuard)");
        }
    }

    // Check 3: Credential Guard (LsaCfgFlags)
    {
        std::string lsa = exec_command(
            "powershell -Command \"Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa' "
            "-Name LsaCfgFlags -ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty LsaCfgFlags\"");
        int flags = 0;
        try { flags = std::stoi(lsa); } catch (...) {}
        if (flags >= 1) {
            vbs_indicators.push_back("Credential Guard is enabled (LsaCfgFlags=" +
                                     std::to_string(flags) + ")");
        }
    }

    if (!vbs_indicators.empty()) {
        result.vm_detected = true;
        result.vbs_detected = true;
        result.vm_brand = "VBS";
        result.techniques_used = static_cast<int>(vbs_indicators.size());
        result.details = vbs_indicators;
        result.recommendation = "DISABLE_VBS: Turn off Memory Integrity in "
                                "Windows Security > Device Security > Core Isolation.\n"
                                "  If that doesn't work, disable Virtualization Technology in BIOS.";
        current_brand_ = "VBS";
        current_percentage_ = 100;
        return result;
    }

    // Clean
    result.vm_detected = false;
    result.vbs_detected = false;
    result.vm_brand = "None";
    result.techniques_used = 0;
    result.recommendation = "ALLOW";
    current_brand_ = "None";
    current_percentage_ = 0;
    return result;
}

VMDetector::VMDetectionResult VMDetector::detect_linux() const {
    VMDetectionResult result;
    result.vbs_detected = false;
    std::vector<std::string> indicators;
    bool hypervisor_flag = false;
    bool is_hw_vendor = false;

    // 1. /proc/cpuinfo hypervisor flag
    std::string cpuinfo = read_file("/proc/cpuinfo");
    if (cpuinfo.find("hypervisor") != std::string::npos) {
        indicators.push_back("/proc/cpuinfo: hypervisor flag");
        hypervisor_flag = true;
    }

    // 2. DMI/SMBIOS - check vendor
    const char* dmi_paths[] = {
        "/sys/class/dmi/id/product_name",
        "/sys/class/dmi/id/sys_vendor",
        "/sys/class/dmi/id/bios_vendor",
        "/sys/class/dmi/id/board_vendor"
    };

    const char* vm_indicators[] = {"vmware", "virtualbox", "qemu", "kvm", "hyper-v", "parallels"};
    const char* hw_indicators[] = {"dell", "hp", "lenovo", "asus", "acer", "msi",
                                    "gigabyte", "asrock", "intel", "supermicro",
                                    "system76", "framework", "razer", "samsung"};

    for (const auto& path : dmi_paths) {
        std::string content = read_file(path);
        // Check VM indicators first
        for (const auto* ind : vm_indicators) {
            if (content.find(ind) != std::string::npos) {
                indicators.push_back(std::string(path) + ": " + ind);
            }
        }
        // Check if real hardware vendor
        std::string lower = content;
        std::transform(lower.begin(), lower.end(), lower.begin(),
            [](unsigned char c){ return static_cast<char>(::tolower(c)); });
        for (const auto* hw : hw_indicators) {
            if (lower.find(hw) != std::string::npos) {
                is_hw_vendor = true;
                break;
            }
        }
    }

    // 3. /dev/kvm
    if (fs::exists("/dev/kvm")) {
        indicators.push_back("/dev/kvm exists");
    }

    // 4. VM processes
    std::string procs = exec_command("ps aux");
    const char* vm_procs[] = {"vmtoolsd", "VBoxService", "qemu-ga", "virtiofsd"};
    for (const auto* proc : vm_procs) {
        if (procs.find(proc) != std::string::npos) {
            indicators.push_back("Process detected: " + std::string(proc));
        }
    }

    // Phase 1 result: VM detected?
    bool is_vm = !indicators.empty();

    // Phase 2: VBS-equivalent (hypervisor flag on bare metal)
    if (!is_vm && hypervisor_flag && is_hw_vendor) {
        std::vector<std::string> vbs_indicators;
        vbs_indicators.push_back("Hypervisor running on genuine hardware (KVM/VFIO active)");
        if (fs::exists("/dev/kvm"))
            vbs_indicators.push_back("/dev/kvm is accessible");
        vbs_indicators.push_back("Disable KVM module (modprobe -r kvm_intel kvm) "
                                 "or remove from BIOS");

        result.vm_detected = true;
        result.vbs_detected = true;
        result.vm_brand = "VBS/KVM";
        result.techniques_used = static_cast<int>(vbs_indicators.size());
        result.details = vbs_indicators;
        result.recommendation = "DISABLE_VBS: Unload KVM modules or disable VT-x in BIOS.";
        current_brand_ = "VBS/KVM";
        current_percentage_ = 100;
        return result;
    }

    result.vm_detected = is_vm;
    result.vbs_detected = false;
    result.vm_brand = detect_brand(indicators);
    result.techniques_used = static_cast<int>(indicators.size());
    result.details = indicators;
    result.recommendation = is_vm ? "BLOCK" : "ALLOW";
    current_brand_ = result.vm_brand;
    current_percentage_ = is_vm ? 100 : 0;
    return result;
}

std::string VMDetector::detect_brand(const std::vector<std::string>& indicators) const {
    for (const auto& ind : indicators) {
        std::string lower = ind;
        std::transform(lower.begin(), lower.end(), lower.begin(),
            [](unsigned char c){ return static_cast<char>(::tolower(c)); });
        
        if (lower.find("vmware") != std::string::npos) return "VMware";
        if (lower.find("virtualbox") != std::string::npos || lower.find("vbox") != std::string::npos) return "VirtualBox";
        if (lower.find("qemu") != std::string::npos || lower.find("kvm") != std::string::npos) return "QEMU/KVM";
        if (lower.find("hyper-v") != std::string::npos || lower.find("microsoft") != std::string::npos) return "Hyper-V";
        if (lower.find("parallels") != std::string::npos) return "Parallels";
    }
    return "Unknown";
}
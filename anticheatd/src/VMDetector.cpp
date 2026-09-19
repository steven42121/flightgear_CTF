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
    std::vector<std::string> indicators;
    
    // 1. Check CPUID hypervisor bit via PowerShell
    std::string ps_output = exec_command("powershell -Command \"$cpu = Get-CimInstance Win32_Processor; $cpu.HypervisorPresent\"");
    if (ps_output.find("True") != std::string::npos) {
        indicators.push_back("CPUID Hypervisor Present");
    }
    
    // 2. Check registry for VM indicators
    std::string reg_keys[] = {
        "HKLM\\HARDWARE\\DESCRIPTION\\System\\SystemManufacturer",
        "HKLM\\HARDWARE\\DESCRIPTION\\System\\BIOS",
        "HKLM\\SOFTWARE\\Microsoft\\Virtual Machine\\Guest\\Parameters"
    };
    
    const char* vm_indicators[] = {"vmware", "virtualbox", "qemu", "hyper-v", "parallels"};
    
    for (const auto& key : reg_keys) {
        std::string cmd = "powershell -Command \"Get-ItemProperty '" + std::string(key) + "' -ErrorAction SilentlyContinue | Format-List | Out-String\"";
        std::string output = exec_command(cmd);
        for (const auto& ind : vm_indicators) {
            if (output.find(ind) != std::string::npos) {
                std::string msg = "Registry: " + std::string(key) + " contains " + ind;
                indicators.push_back(msg);
            }
        }
    }
    
    // 3. Check for VM processes
    std::string procs = exec_command("tasklist /FO CSV");
    const char* vm_procs[] = {"vmtoolsd.exe", "VBoxService.exe", "VBoxTray.exe", 
                              "qemu-ga.exe", "prl_cc.exe", "prl_tools.exe"};
    for (const auto& proc : vm_procs) {
        if (procs.find(proc) != std::string::npos) {
            indicators.push_back("Process detected: " + std::string(proc));
        }
    }
    
    // 4. Check MAC addresses
    std::string mac_output = exec_command("powershell -Command \"Get-NetAdapter | Select-Object MacAddress, Status\"");
    const char* vm_macs[] = {"00:50:56", "00:0C:29", "08:00:27"};
    for (const auto& mac : vm_macs) {
        if (mac_output.find(mac) != std::string::npos) {
            indicators.push_back("MAC OUI indicates VM: " + std::string(mac));
        }
    }
    
    result.vm_detected = !indicators.empty();
    result.vm_brand = detect_brand(indicators);
    result.techniques_used = indicators.size();
    result.details = indicators;
    result.recommendation = result.vm_detected ? "BLOCK" : "ALLOW";
    
    current_brand_ = result.vm_brand;
    current_percentage_ = result.vm_detected ? 100 : 0;
    
    return result;
}

VMDetector::VMDetectionResult VMDetector::detect_linux() const {
    VMDetectionResult result;
    std::vector<std::string> indicators;
    
    // 1. /proc/cpuinfo hypervisor flag
    std::string cpuinfo = read_file("/proc/cpuinfo");
    if (cpuinfo.find("hypervisor") != std::string::npos) {
        indicators.push_back("/proc/cpuinfo: hypervisor flag");
    }
    
    // 2. DMI/SMBIOS
    const char* dmi_paths[] = {
        "/sys/class/dmi/id/product_name",
        "/sys/class/dmi/id/sys_vendor",
        "/sys/class/dmi/id/bios_vendor",
        "/sys/class/dmi/id/board_vendor"
    };
    
    const char* vm_indicators[] = {"vmware", "virtualbox", "qemu", "kvm", "hyper-v", "parallels"};
    
    for (const auto& path : dmi_paths) {
        std::string content = read_file(path);
        for (const auto& ind : vm_indicators) {
            if (content.find(ind) != std::string::npos) {
                indicators.push_back(std::string(path) + ": " + ind);
            }
        }
    }
    
    // 3. /dev/kvm
    if (fs::exists("/dev/kvm")) {
        indicators.push_back("/dev/kvm exists");
    }
    
    // 4. Check for VM processes
    std::string procs = exec_command("ps aux");
    const char* vm_procs[] = {"vmtoolsd", "VBoxService", "qemu-ga", "virtiofsd"};
    for (const auto& proc : vm_procs) {
        if (procs.find(proc) != std::string::npos) {
            indicators.push_back("Process detected: " + std::string(proc));
        }
    }
    
    result.vm_detected = !indicators.empty();
    result.vm_brand = detect_brand(indicators);
    result.techniques_used = indicators.size();
    result.details = indicators;
    result.recommendation = result.vm_detected ? "BLOCK" : "ALLOW";
    
    current_brand_ = result.vm_brand;
    current_percentage_ = result.vm_detected ? 100 : 0;
    
    return result;
}

std::string VMDetector::detect_brand(const std::vector<std::string>& indicators) const {
    for (const auto& ind : indicators) {
        std::string lower = ind;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        
        if (lower.find("vmware") != std::string::npos) return "VMware";
        if (lower.find("virtualbox") != std::string::npos || lower.find("vbox") != std::string::npos) return "VirtualBox";
        if (lower.find("qemu") != std::string::npos || lower.find("kvm") != std::string::npos) return "QEMU/KVM";
        if (lower.find("hyper-v") != std::string::npos || lower.find("microsoft") != std::string::npos) return "Hyper-V";
        if (lower.find("parallels") != std::string::npos) return "Parallels";
    }
    return "Unknown";
}

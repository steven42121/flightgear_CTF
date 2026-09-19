#include "L4_ProcessIntegrity.hpp"
#ifdef _WIN32
#include <windows.h>
#include <psapi.h>
#else
#include <fstream>
#endif

L4_ProcessIntegrity::Result L4_ProcessIntegrity::check() const {
    Result result;
#ifdef _WIN32
    // Windows: check process modules for suspicious names
    HANDLE hProcess = GetCurrentProcess();
    HMODULE hMods[1024];
    DWORD cbNeeded;
    
    if (EnumProcessModules(hProcess, hMods, sizeof(hMods), &cbNeeded)) {
        for (unsigned int i = 0; i < cbNeeded / sizeof(HMODULE); i++) {
            char szModName[MAX_PATH];
            if (GetModuleFileNameEx(hProcess, hMods[i], szModName, sizeof(szModName))) {
                std::string mod(szModName);
                // Check for injection indicators
                if (mod.find("frida") != std::string::npos ||
                    mod.find("inject") != std::string::npos ||
                    mod.find("hook") != std::string::npos) {
                    result.issues.push_back("Suspicious module: " + mod);
                    result.passed = false;
                }
            }
        }
    }
    CloseHandle(hProcess);
#else
    // Linux: check /proc/self/maps
    std::ifstream maps("/proc/self/maps");
    std::string line;
    while (std::getline(maps, line)) {
        if (line.find("frida") != std::string::npos ||
            line.find("inject") != std::string::npos) {
            result.issues.push_back(line);
            result.passed = false;
        }
    }
#endif
    result.detail = result.passed ? "No injections detected" : 
                                      std::to_string(result.issues.size()) + " issues found";
    return result;
}

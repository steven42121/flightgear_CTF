#ifdef _WIN32
#define _CRT_SECURE_NO_WARNINGS
#endif

#include "FGDetector.hpp"
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <cstring>
#include <fstream>
#endif

namespace fs = std::filesystem;
namespace fg_detect {

#ifdef _WIN32

static std::string read_env(const char* name) {
    char buf[1024]{};
    DWORD len = GetEnvironmentVariableA(name, buf, sizeof(buf));
    if (len == 0 || len >= sizeof(buf)) return "";
    return std::string(buf);
}

static std::string read_registry(const char* key_path, const char* value_name) {
    HKEY hKey;
    char buf[512]{};
    DWORD size = sizeof(buf);

    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, key_path, 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        if (RegQueryValueExA(hKey, value_name, nullptr, nullptr,
                             reinterpret_cast<LPBYTE>(buf), &size) == ERROR_SUCCESS) {
            RegCloseKey(hKey);
            return std::string(buf);
        }
        RegCloseKey(hKey);
    }
    return "";
}

static bool file_exists(const fs::path& p) {
    std::error_code ec;
    return fs::exists(p, ec) && !ec;
}

#else

static std::string read_env(const char* name) {
    const char* v = std::getenv(name);
    return v ? std::string(v) : std::string();
}

static bool file_exists(const fs::path& p) {
    std::error_code ec;
    return fs::exists(p, ec) && !ec;
}

// which-like: search PATH for an executable
static std::string which(const std::string& exe) {
    const char* path_env = std::getenv("PATH");
    if (!path_env) return "";

    std::string paths(path_env);
    size_t start = 0;
    while (start < paths.size()) {
        size_t end = paths.find(':', start);
        if (end == std::string::npos) end = paths.size();
        std::string dir = paths.substr(start, end - start);
        fs::path candidate = fs::path(dir) / exe;
        if (file_exists(candidate) && fs::status(candidate).permissions() != fs::perms::none) {
            return candidate.string();
        }
        start = end + 1;
    }
    return "";
}

#endif

FGLocations detect() {
    FGLocations loc;

#ifdef _WIN32
    // 1) Environment variable FG_ROOT
    std::string env_root = read_env("FG_ROOT");
    if (!env_root.empty() && file_exists(fs::path(env_root) / "version")) {
        loc.data_root = env_root;
    }

    // 2) Registry
    if (loc.data_root.empty()) {
        const char* reg_keys[] = {
            "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FlightGear_is1",
            "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\FlightGear_is1",
        };
        for (auto* rk : reg_keys) {
            std::string install = read_registry(rk, "InstallLocation");
            if (!install.empty()) {
                // InstallLocation is the root dir containing bin/
                fs::path root(install);
                // Detect FGData — some installers put it under this dir, others elsewhere
                for (auto* sub : {"data", "fgdata", "FlightGear/data"}) {
                    fs::path candidate = root / sub;
                    if (file_exists(candidate / "version")) {
                        loc.data_root = candidate.string();
                        break;
                    }
                }
                // Fallback: root itself
                if (loc.data_root.empty() && file_exists(root / "version")) {
                    loc.data_root = root.string();
                }
                if (!loc.data_root.empty()) break;
            }
        }
    }

    // 3) Common paths
    if (loc.data_root.empty()) {
        std::vector<fs::path> candidates = {
            "C:/Program Files/FlightGear 2024.1/data",
            "C:/Program Files/FlightGear/data",
            "C:/Program Files (x86)/FlightGear 2024.1/data",
            "C:/Program Files (x86)/FlightGear/data",
            "C:/FlightGear/data",
            "C:/FlightGear 2024.1/data",
        };
        for (const auto& c : candidates) {
            if (file_exists(c / "version")) {
                loc.data_root = c.string();
                break;
            }
        }
    }

    // Bin directory
    std::string env_bin = read_env("FG_BIN");
    if (!env_bin.empty() && file_exists(fs::path(env_bin) / "fgfs.exe")) {
        loc.bin_dir = env_bin;
    }

    if (loc.bin_dir.empty()) {
        if (!loc.data_root.empty()) {
            // Try sibling bin/ directory
            fs::path parent = fs::path(loc.data_root).parent_path();
            if (file_exists(parent / "bin" / "fgfs.exe")) {
                loc.bin_dir = (parent / "bin").string();
            }
        }
    }

    if (loc.bin_dir.empty()) {
        // Search PATH for fgfs.exe
        std::string fgfs = read_env("PATH");
        if (!fgfs.empty()) {
            const char* path_env = std::getenv("PATH");
            if (path_env) {
                std::string paths(path_env);
                size_t start = 0;
                while (start < paths.size()) {
                    size_t end = paths.find(';', start);
                    if (end == std::string::npos) end = paths.size();
                    std::string dir = paths.substr(start, end - start);
                    if (file_exists(fs::path(dir) / "fgfs.exe")) {
                        loc.bin_dir = dir;
                        break;
                    }
                    start = end + 1;
                }
            }
        }
    }

    // Fallback common binary paths
    if (loc.bin_dir.empty()) {
        std::vector<fs::path> bin_cands = {
            "C:/Program Files/FlightGear 2024.1/bin",
            "C:/Program Files/FlightGear/bin",
            "C:/Program Files (x86)/FlightGear 2024.1/bin",
            "C:/Program Files (x86)/FlightGear/bin",
        };
        for (const auto& c : bin_cands) {
            if (file_exists(c / "fgfs.exe")) {
                loc.bin_dir = c.string();
                break;
            }
        }
    }

    // Scenery dir
    std::string env_scenery = read_env("FG_SCENERY");
    if (!env_scenery.empty()) {
        loc.scenery_dir = env_scenery;
    } else if (!loc.data_root.empty()) {
        // Try sibling TerraSync
        fs::path parent = fs::path(loc.data_root).parent_path();
        if (file_exists(parent / "TerraSync")) {
            loc.scenery_dir = (parent / "TerraSync").string();
        }
    }

#else  // Linux

    // 1) Environment variable FG_ROOT
    std::string env_root = read_env("FG_ROOT");
    if (!env_root.empty() && file_exists(fs::path(env_root) / "version")) {
        loc.data_root = env_root;
    }

    // 2) Common paths
    if (loc.data_root.empty()) {
        std::vector<fs::path> candidates = {
            "/usr/share/games/flightgear",
            "/usr/share/flightgear",
            "/opt/flightgear/data",
            "$HOME/.fgfs/fgdata",
        };
        for (const auto& c : candidates) {
            std::string p = c.string();
            if (p.find("$HOME") == 0) {
                const char* home = std::getenv("HOME");
                if (home) p = std::string(home) + p.substr(5);
            }
            if (file_exists(fs::path(p) / "version")) {
                loc.data_root = p;
                break;
            }
        }
    }

    // Bin directory
    std::string env_bin = read_env("FG_BIN");
    if (!env_bin.empty() && file_exists(fs::path(env_bin) / "fgfs")) {
        loc.bin_dir = env_bin;
    }

    if (loc.bin_dir.empty()) {
        std::string fgfs_path = which("fgfs");
        if (!fgfs_path.empty()) {
            loc.bin_dir = fs::path(fgfs_path).parent_path().string();
        }
    }

    if (loc.bin_dir.empty()) {
        if (file_exists("/opt/flightgear/bin/fgfs"))
            loc.bin_dir = "/opt/flightgear/bin";
        else if (file_exists("/usr/bin/fgfs"))
            loc.bin_dir = "/usr/bin";
        else if (file_exists("/usr/local/bin/fgfs"))
            loc.bin_dir = "/usr/local/bin";
    }

    // Scenery
    std::string env_scenery = read_env("FG_SCENERY");
    if (!env_scenery.empty()) {
        loc.scenery_dir = env_scenery;
    } else {
        const char* home = std::getenv("HOME");
        if (home) {
            fs::path ts = fs::path(home) / ".fgfs" / "TerraSync";
            if (file_exists(ts)) loc.scenery_dir = ts.string();
        }
    }
#endif

    return loc;
}

} // namespace fg_detect
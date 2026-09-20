/**
 * MAYDAY CTF Anti-Cheat Daemon - Main Entry Point
 *
 * Based on UltimateAntiCheat architecture + VMAware VM detection.
 * 
 * Modes:
 *   --mode daemon    : Run as daemon with heartbeat loop
 *   --mode check     : Validate args and exit
 *   --mode session   : Open session and print ticket
 *   --mode selfcheck : Run all checks and print report
 */
#include <iostream>
#include <string>
#include <vector>
#include <filesystem>
#include "AntiCheatDaemon.hpp"
#include "Config.hpp"
#include "Logger.hpp"
#include "FGDetector.hpp"

namespace fs = std::filesystem;

void print_usage(const char* prog) {
    std::cout << "MAYDAY CTF Anti-Cheat Daemon\n"
              << "Usage: " << prog << " [OPTIONS]\n\n"
              << "Options:\n"
              << "  --mode <daemon|check|session|selfcheck>\n"
              << "  --json                     Output results as JSON (requires selfcheck/check)\n"
              << "  --config <path>          Config file (JSON)\n"
              << "  --userid <name>          User ID for session mode\n"
              << "  --fg-root <path>         FGData root directory\n"
              << "  --fg-bin <path>          FG binary directory\n"
              << "  --scenery <path>         TerraSync scenery directory\n"
              << "  --lock-file <path>       env.lock file path\n"
              << "  --telnet-host <host>     FG telnet host (default: 127.0.0.1)\n"
              << "  --telnet-port <port>     FG telnet port (default: 5401)\n"
              << "  --server <host:port>     Anticheat server address (default: 127.0.0.1:5000)\n"
              << "  --help                   Show this help\n";
}

int main(int argc, char* argv[]) {
    Config cfg;
    std::string mode = "selfcheck";
    std::string userid;
    std::vector<std::string> args;
    bool json_output = false;
    
    // Parse command line
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--help" || arg == "-h") {
            print_usage(argv[0]);
            return 0;
        } else if (arg == "--mode" && i + 1 < argc) {
            mode = argv[++i];
        } else if (arg == "--json") {
            json_output = true;
        } else if (arg == "--config" && i + 1 < argc) {
            cfg.config_path = argv[++i];
        } else if (arg == "--userid" && i + 1 < argc) {
            userid = argv[++i];
        } else if (arg == "--fg-root" && i + 1 < argc) {
            cfg.fg_root = argv[++i];
        } else if (arg == "--fg-bin" && i + 1 < argc) {
            cfg.fg_bin_dir = argv[++i];
        } else if (arg == "--scenery" && i + 1 < argc) {
            cfg.scenery_dir = argv[++i];
        } else if (arg == "--lock-file" && i + 1 < argc) {
            cfg.lock_file = argv[++i];
        } else if (arg == "--telnet-host" && i + 1 < argc) {
            cfg.telnet_host = argv[++i];
        } else if (arg == "--telnet-port" && i + 1 < argc) {
            cfg.telnet_port = std::stoi(argv[++i]);
        } else if (arg == "--server" && i + 1 < argc) {
            std::string spec = argv[++i];
            auto colon = spec.rfind(':');
            if (colon != std::string::npos) {
                cfg.server_ip = spec.substr(0, colon);
                cfg.server_port = std::stoi(spec.substr(colon + 1));
            } else {
                cfg.server_ip = spec;
            }
        } else {
            args.push_back(arg);
        }
    }
    
    // Load config from file if specified
    if (!cfg.config_path.empty() && fs::exists(cfg.config_path)) {
        cfg.load(cfg.config_path);
    }
    
    // Auto-detect FG locations if not set by CLI or config
    auto fg = fg_detect::detect();
    if (cfg.fg_root.empty())       cfg.fg_root      = fg.data_root;
    if (cfg.fg_bin_dir.empty())    cfg.fg_bin_dir    = fg.bin_dir;
    if (cfg.scenery_dir.empty())   cfg.scenery_dir   = fg.scenery_dir;
    if (cfg.lock_file.empty()) {
        // Search for env.lock in multiple locations:
        // 1) next to the binary
        // 2) up to 5 levels above binary (for PyInstaller _MEIPASS deep trees)
        // 3) current working directory
        fs::path binary_dir = fs::path(argv[0]).parent_path();
        for (int up = 0; up <= 5; ++up) {
            fs::path candidate = binary_dir / "env.lock";
            std::error_code ec;
            if (fs::exists(candidate, ec)) {
                cfg.lock_file = candidate.string();
                break;
            }
            binary_dir = binary_dir.parent_path();
        }
        if (cfg.lock_file.empty()) {
            if (fs::exists("env.lock")) {
                cfg.lock_file = "env.lock";
            } else {
                cfg.lock_file = (fs::path(argv[0]).parent_path() / "env.lock").string();
            }
        }
    }

    try {
        AntiCheatDaemon daemon(cfg);
        if (json_output) {
            daemon.set_json_mode(true);
        }
        int ret = daemon.run(
            mode == "daemon" ? DaemonMode::DAEMON :
            mode == "check" ? DaemonMode::CHECK :
            mode == "session" ? DaemonMode::SESSION : DaemonMode::SELF_CHECK,
            args,
            userid
        );
        // Always output JSON when requested (success or failure)
        if (json_output) {
            daemon.print_json_report();
        }
        return ret;
    } catch (const std::exception& e) {
        if (json_output) {
            std::cout << "{\"error\":\"" << e.what() << "\"}" << std::endl;
        } else {
            std::cerr << "ERROR: " << e.what() << std::endl;
        }
        return 1;
    }
}
#include <winsock2.h>
#include <ws2tcpip.h>

#include "AntiCheatDaemon.hpp"
#include "L0_ArgValidation.hpp"
#include "L1_Integrity.hpp"
#include "L2_PropertyAudit.hpp"
#include "L3_FDMSourceTracker.hpp"
#include "L4_ProcessIntegrity.hpp"
#include "L5_Heartbeat.hpp"
#include "SessionManager.hpp"
#include "VMDetector.hpp"
#include "Logger.hpp"
#include "obfuscate.hpp"
#include <iostream>
#include <filesystem>
#include <thread>
#include <chrono>
#include <sstream>

namespace fs = std::filesystem;

// ═══════════════════════════════════════════════════════════════════
// CONSTRUCTOR / DESTRUCTOR
// ═══════════════════════════════════════════════════════════════════

AntiCheatDaemon::AntiCheatDaemon(const Config& cfg)
    : cfg_(cfg),
      l0_(std::make_unique<L0_ArgValidation>()),
      l1_(std::make_unique<L1_Integrity>(cfg_.lock_file)),
      l2_(nullptr),
      l3_(nullptr),
      l4_(nullptr),
      vm_(std::make_unique<VMDetector>()),
      session_mgr_(nullptr) {

    Logger::set_level(cfg_.enable_logging ? Logger::INFO : Logger::WARNING);
    Logger::set_log_file(cfg_.log_file);

    // Anti-debug: first check on construction
    if (anti_debug::debugger_present()) {
        running_ = false;
    }
    JUNK_MATH();
}

AntiCheatDaemon::~AntiCheatDaemon() {
    stop();
    JUNK_MATH();
}

// ═══════════════════════════════════════════════════════════════════
// MAIN ENTRY
// ═══════════════════════════════════════════════════════════════════

int AntiCheatDaemon::run(DaemonMode mode, const std::vector<std::string>& args,
                         const std::string& userid) {
    GUARD_BLOCK();
    OPAQUE_DEAD_CODE();
    JUNK_MATH();

    std::vector<CheckResult> results;

    // Run all checks
    results.push_back(check_L0(args));
    results.push_back(check_L1());
    results.push_back(check_VM());

    if (mode == DaemonMode::DAEMON) {
        results.push_back(check_L2());
        results.push_back(check_L4());
    }

    // Store results for JSON output
    last_results_ = results;

    // Only print text report if NOT in JSON mode (caller handles JSON output)
    if (!json_mode_) {
        print_report(results);
    }

    bool all_passed = true;
    for (const auto& r : results) {
        if (!r.passed) { all_passed = false; break; }
    }

    if (!all_passed) {
        if (!json_mode_) {
            std::cerr << "\n" << OBFSTR("ERROR: Environment validation failed!") << std::endl;
        }
        _guard_check();
        return 1;
    }

    if (mode == DaemonMode::CHECK) {
        std::cout << "\n" << OBFSTR("OK: All checks passed") << std::endl;
        _guard_check();
        return 0;
    }

    if (mode == DaemonMode::SESSION && !userid.empty()) {
        if (!session_mgr_) {
            session_mgr_ = std::make_unique<SessionManager>();
        }
        session_id_ = session_mgr_->open_session(userid, "", "", "");

        std::cout << "\n" << OBFSTR("Session opened: ")
                  << session_id_.substr(0, 8) << "..." << std::endl;
        _guard_check();
        return 0;
    }

    if (mode == DaemonMode::DAEMON) {
        // Create ticket for signing + UDP heartbeat loop
        auto ticket = std::make_unique<HeartbeatTicket>(userid);

        std::cout << "\n" << OBFSTR("Daemon running (press Ctrl+C to stop)")
                  << std::endl;

        running_ = true;
        heartbeat_thread_ = std::thread(&AntiCheatDaemon::heartbeat_loop,
                                        this, userid);
        while (running_) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        _guard_check();
        return 0;
    }

    _guard_check();
    return 0;
}

// ═══════════════════════════════════════════════════════════════════
// L0: ARGUMENT VALIDATION
// ═══════════════════════════════════════════════════════════════════

CheckResult AntiCheatDaemon::check_L0(const std::vector<std::string>& args) {
    CheckResult result;
    result.layer = "L0";

    auto vr = l0_->validate(args);
    result.passed = vr.valid;
    result.detail = vr.valid ? OBFSTR("All arguments valid")
                             : OBFSTR("Invalid arguments detected");
    result.issues = vr.issues;
    JUNK_MATH();
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// L1: FILE INTEGRITY
// ═══════════════════════════════════════════════════════════════════

CheckResult AntiCheatDaemon::check_L1() {
    CheckResult result;
    result.layer = "L1";

    auto check = l1_->verify(cfg_.fg_root, cfg_.fg_bin_dir, cfg_.scenery_dir);
    result.passed = check.passed;
    result.detail = check.detail;
    result.issues = check.issues;
    OPAQUE_DEAD_CODE();
    JUNK_MATH();
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// ANTI-VM / VBS
// ═══════════════════════════════════════════════════════════════════

CheckResult AntiCheatDaemon::check_VM() {
    CheckResult result;
    result.layer = "Anti-VM";

    auto vm_result = vm_->detect();
    result.passed = !vm_result.vm_detected;

    if (vm_result.vbs_detected) {
        result.detail = OBFSTR("VBS/Hypervisor detected: ") + vm_result.vm_brand;
        result.issues = vm_result.details;
        result.issues.push_back(">> " + vm_result.recommendation);
    } else if (vm_result.vm_detected) {
        result.detail = OBFSTR("VM detected: ") + vm_result.vm_brand;
        result.issues = vm_result.details;
    } else {
        result.detail = OBFSTR("No virtualization detected");
    }
    JUNK_MATH();
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// L2, L4: PLACEHOLDERS
// ═══════════════════════════════════════════════════════════════════

CheckResult AntiCheatDaemon::check_L2() {
    CheckResult result;
    result.layer = "L2";
    result.passed = true;
    result.detail = OBFSTR("Property audit (placeholder)");
    JUNK_MATH();
    return result;
}

CheckResult AntiCheatDaemon::check_L4() {
    CheckResult result;
    result.layer = "L4";
    result.passed = true;
    result.detail = OBFSTR("Process integrity (placeholder)");
    JUNK_MATH();
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// HEARTBEAT
// ═══════════════════════════════════════════════════════════════════

void AntiCheatDaemon::start_heartbeat(const std::string& /*userid*/) {
    running_ = true;
    heartbeat_thread_ = std::thread(&AntiCheatDaemon::heartbeat_loop, this, std::string(""));
}

void AntiCheatDaemon::heartbeat_loop(const std::string& userid) {
    GUARD_BLOCK();
    JUNK_MATH();

    // Create ticket engine
    auto ticket = std::make_unique<HeartbeatTicket>(userid);

    // UDP socket to server
    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) {
        JUNK_MATH();
        return;
    }

    sockaddr_in server{};
    server.sin_family = AF_INET;
    server.sin_port = htons(static_cast<u_short>(5001));
    inet_pton(AF_INET, cfg_.server_ip.c_str(), &server.sin_addr);

    // Obfuscate server IP check
    volatile int port = 5001;
    OBF_UNUSED(port);
    JUNK_MATH();

    while (running_) {
        if (anti_debug::debugger_present()) {
            // Debugger detected mid-flight → stop heartbeat
            closesocket(sock);
            JUNK_MATH();
            return;
        }

        std::string ticket_json = ticket->sign();
        sendto(sock, ticket_json.c_str(), static_cast<int>(ticket_json.size()),
               0, reinterpret_cast<sockaddr*>(&server), sizeof(server));

        if (ticket->missed() >= 5) {
            Logger::warn(OBFSTR("Heartbeat missed too many, session expired"));
            break;
        }

        std::this_thread::sleep_for(std::chrono::seconds(1));
        JUNK_MATH();
    }

    closesocket(sock);
    _guard_check();
}

void AntiCheatDaemon::stop() {
    running_ = false;
    if (heartbeat_thread_.joinable()) {
        heartbeat_thread_.join();
    }
    JUNK_MATH();
}

// ═══════════════════════════════════════════════════════════════════
// JSON MODE
// ═══════════════════════════════════════════════════════════════════

void AntiCheatDaemon::set_json_mode(bool on) {
    json_mode_ = on;
}

// ═══════════════════════════════════════════════════════════════════
// REPORT
// ═══════════════════════════════════════════════════════════════════

void AntiCheatDaemon::print_report(const std::vector<CheckResult>& results) {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << OBFSTR("MAYDAY CTF Anti-Cheat Report") << std::endl;
    std::cout << std::string(60, '=') << std::endl;

    int passed = 0, failed = 0;
    for (const auto& r : results) {
        std::cout << "[" << (r.passed ? OBFSTR("PASS") : OBFSTR("FAIL")) << "] "
                  << r.layer << ": " << r.detail;
        if (!r.issues.empty()) {
            std::cout << " (";
            for (size_t i = 0; i < r.issues.size(); ++i) {
                if (i > 0) std::cout << ", ";
                std::cout << r.issues[i];
            }
            std::cout << ")";
        }
        std::cout << std::endl;
        if (r.passed) ++passed; else ++failed;
    }

    std::cout << std::string(60, '=') << std::endl;
    std::cout << OBFSTR("Results: ") << passed
              << OBFSTR(" passed, ") << failed
              << OBFSTR(" failed") << std::endl;
    std::cout << std::string(60, '=') << "\n" << std::endl;
}

// ═══════════════════════════════════════════════════════════════════
// JSON REPORT (for GUI integration)
// ═══════════════════════════════════════════════════════════════════

void AntiCheatDaemon::print_json_report() {
    // Escape strings for JSON
    auto escape_json = [](const std::string& s) -> std::string {
        std::string out;
        for (char c : s) {
            switch (c) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default: out += c;
            }
        }
        return out;
    };

    std::cout << "{" << std::endl;
    std::cout << "  \"checks\": [" << std::endl;
    
    int total = 0, passed = 0;
    for (size_t i = 0; i < last_results_.size(); ++i) {
        const auto& r = last_results_[i];
        std::cout << "    {";
        std::cout << "\"layer\":\"" << escape_json(r.layer) << "\",";
        std::cout << "\"passed\":" << (r.passed ? "true" : "false") << ",";
        std::cout << "\"detail\":\"" << escape_json(r.detail) << "\",";
        std::cout << "\"issues\":[";
        for (size_t j = 0; j < r.issues.size(); ++j) {
            if (j > 0) std::cout << ",";
            std::cout << "\"" << escape_json(r.issues[j]) << "\"";
        }
        std::cout << "]}";
        if (i < last_results_.size() - 1) std::cout << ",";
        std::cout << std::endl;
        ++total;
        if (r.passed) ++passed;
    }
    
    std::cout << "  ]," << std::endl;
    std::cout << "  \"total\":" << total << "," << std::endl;
    std::cout << "  \"passed\":" << passed << "," << std::endl;
    std::cout << "  \"all_passed\":" << (passed == total ? "true" : "false") << std::endl;
    std::cout << "}" << std::endl;
}
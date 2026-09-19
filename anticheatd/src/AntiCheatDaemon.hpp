#pragma once
/**
 * MAYDAY CTF Anti-Cheat Daemon (anticheatd)
 * 
 * Layered anti-cheat for FlightGear CTF competition.
 * References:
 *   - VMAware (MIT): VM detection techniques
 *   - UltimateAntiCheat (AGPL): user-mode anti-cheat architecture
 *
 * Architecture:
 *   L0: Startup argument whitelist (--fdm, --native-fdm, --load-tape)
 *   L1: File integrity (SHA256 hashes of fgfs, aircraft, scenery via env.lock)
 *   L2: Property tree audit (monitor /position/*, /velocities/* writes via telnet)
 *   L3: FDM source trust tracking (MP vs external FDM server)
 *   L4: Process integrity (inject scan, CRC checks)
 *   L5: Heartbeat ticket (1Hz HMAC chain, KDF from binary hashes + userid + nonce)
 *
 * K = KDF(hash(anticheatd) ‖ hash(fgfs) ‖ hash(aircraft) ‖ userid ‖ nonce)
 * flagN = HMAC(K_server, userid ‖ checkpoint)   ← K_server is DIFFERENT from K
 */

#include <string>
#include <memory>
#include <chrono>
#include <thread>
#include <atomic>
#include <mutex>
#include <vector>
#include <functional>
#include <optional>

#include "common.hpp"
#include "Config.hpp"
#include "Logger.hpp"

class SessionManager;
class L0_ArgValidation;
class L1_Integrity;
class L2_PropertyAudit;
class L3_FDMSourceTracker;
class L4_ProcessIntegrity;
class VMDetector;

enum class DaemonMode {
    DAEMON,      // Normal operation: validate + heartbeat loop
    CHECK,       // One-shot: validate args and exit
    SESSION,     // One-shot: open session and print ticket
    SELF_CHECK,  // One-shot: run all checks, print report
};

struct CheckResult {
    std::string layer;      // "L0", "L1", "Anti-VM", etc.
    bool passed;
    std::string detail;
    std::vector<std::string> issues;
};

class AntiCheatDaemon {
public:
    explicit AntiCheatDaemon(const Config& cfg);
    ~AntiCheatDaemon();

    // Disabled copy/move
    AntiCheatDaemon(const AntiCheatDaemon&) = delete;
    AntiCheatDaemon& operator=(const AntiCheatDaemon&) = delete;

    int run(DaemonMode mode, const std::vector<std::string>& args,
            const std::string& userid = "");

    // Enable JSON output mode (suppresses text report)
    void set_json_mode(bool on);

    // Print JSON report (for GUI integration)
    void print_json_report();

private:
    // L0-L5 checks
    CheckResult check_L0(const std::vector<std::string>& args);
    CheckResult check_L1();
    CheckResult check_VM();
    CheckResult check_L2();
    CheckResult check_L4();

    // Heartbeat
    void start_heartbeat(const std::string& userid);
    void heartbeat_loop(const std::string& userid);
    void stop();

    // Report
    void print_report(const std::vector<CheckResult>& results);

    // Members
    Config cfg_;
    std::unique_ptr<SessionManager> session_mgr_;
    std::unique_ptr<L0_ArgValidation> l0_;
    std::unique_ptr<L1_Integrity> l1_;
    std::unique_ptr<L2_PropertyAudit> l2_;
    std::unique_ptr<L3_FDMSourceTracker> l3_;
    std::unique_ptr<L4_ProcessIntegrity> l4_;
    std::unique_ptr<VMDetector> vm_;
    std::atomic<bool> running_{false};
    std::thread heartbeat_thread_;
    std::string session_id_;
    std::vector<CheckResult> last_results_;  // Stored for JSON output
    bool json_mode_ = false;                  // Suppress text report when true
};
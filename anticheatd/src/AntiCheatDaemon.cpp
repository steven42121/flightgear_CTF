#include "AntiCheatDaemon.hpp"
#include "L0_ArgValidation.hpp"
#include "L1_Integrity.hpp"
#include "VMDetector.hpp"
#include "Logger.hpp"
#include <iostream>
#include <filesystem>
#include <thread>
#include <chrono>

namespace fs = std::filesystem;

AntiCheatDaemon::AntiCheatDaemon(const Config& cfg) 
    : cfg_(cfg), 
      l0_(std::make_unique<L0_ArgValidation>()),
      l1_(std::make_unique<L1_Integrity>(cfg_.lock_file)),
      l2_(nullptr),  // Will be initialized if needed
      l3_(nullptr),  // Will be initialized if needed
      l4_(nullptr),  // Will be initialized if needed
      vm_(std::make_unique<VMDetector>()),
      l5_(nullptr) {
    
    Logger::set_level(cfg_.enable_logging ? Logger::INFO : Logger::WARNING);
    Logger::set_log_file(cfg_.log_file);
}

AntiCheatDaemon::~AntiCheatDaemon() {
    stop();
}

int AntiCheatDaemon::run(DaemonMode mode, const std::vector<std::string>& args,
                         const std::string& userid) {
    std::vector<CheckResult> results;
    
    // Run all checks
    results.push_back(check_L0(args));
    results.push_back(check_L1());
    results.push_back(check_VM());
    
    // For daemon mode, also check L2-L4
    if (mode == DAEMON) {
        results.push_back(check_L2());
        results.push_back(check_L4());
    }
    
    // Print report
    print_report(results);
    
    // Check overall status
    bool all_passed = true;
    for (const auto& r : results) {
        if (!r.passed) {
            all_passed = false;
            break;
        }
    }
    
    if (!all_passed) {
        std::cerr << "\nERROR: Environment validation failed!" << std::endl;
        return 1;
    }
    
    // Handle mode-specific actions
    if (mode == CHECK) {
        std::cout << "\nOK: All checks passed" << std::endl;
        return 0;
    }
    
    if (mode == SESSION && !userid.empty()) {
        // Start heartbeat session
        std::string anticheat_hash = sha256(fs::read_contents(argv[0]));  // Placeholder
        std::string fgfs_hash = sha256(cfg_.fg_bin_dir + "/fgfs.exe");
        std::string aircraft_hash = sha256(cfg_.fg_root + "/Aircraft/c172p/c172p-set.xml");
        
        l5_ = std::make_unique<L5_Heartbeat>(...);
        session_id_ = l5_->open_session(userid, anticheat_hash, fgfs_hash, aircraft_hash);
        
        std::cout << "\nSession opened: " << session_id_.substr(0, 8) << "..." << std::endl;
        std::cout << "Ticket: " << l5_->sign() << std::endl;
        
        return 0;
    }
    
    if (mode == DAEMON) {
        // Start heartbeat thread
        start_heartbeat(userid);
        
        std::cout << "\nDaemon running (press Ctrl+C to stop)" << std::endl;
        
        // Keep running
        while (running_) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
        
        return 0;
    }
    
    return 0;
}

AntiCheatDaemon::CheckResult AntiCheatDaemon::check_L0(const std::vector<std::string>& args) {
    CheckResult result;
    result.layer = "L0";
    
    L0_ArgValidation::ValidationResult vr = l0_->validate(args);
    result.passed = vr.valid;
    result.detail = vr.valid ? "All arguments valid" : "Invalid arguments detected";
    result.issues = vr.issues;
    
    return result;
}

AntiCheatDaemon::CheckResult AntiCheatDaemon::check_L1() {
    CheckResult result;
    result.layer = "L1";
    
    auto check = l1_->verify(cfg_.fg_root, cfg_.fg_bin_dir, cfg_.scenery_dir);
    result.passed = check.passed;
    result.detail = check.detail;
    result.issues = check.issues;
    
    return result;
}

AntiCheatDaemon::CheckResult AntiCheatDaemon::check_VM() {
    CheckResult result;
    result.layer = "Anti-VM";
    
    auto vm_result = vm_->detect();
    result.passed = !vm_result.vm_detected;
    result.detail = vm_result.vm_brand + " detected: " + 
                    std::to_string(vm_result.techniques_used) + " techniques";
    result.issues = vm_result.details;
    
    return result;
}

AntiCheatDaemon::CheckResult AntiCheatDaemon::check_L2() {
    CheckResult result;
    result.layer = "L2";
    // TODO: Implement property audit
    result.passed = true;
    result.detail = "Property audit (placeholder)";
    return result;
}

AntiCheatDaemon::CheckResult AntiCheatDaemon::check_L4() {
    CheckResult result;
    result.layer = "L4";
    // TODO: Implement process integrity
    result.passed = true;
    result.detail = "Process integrity (placeholder)";
    return result;
}

void AntiCheatDaemon::start_heartbeat(const std::string& userid) {
    running_ = true;
    heartbeat_thread_ = std::thread(&AntiCheatDaemon::heartbeat_loop, this);
}

void AntiCheatDaemon::heartbeat_loop() {
    while (running_) {
        if (l5_) {
            std::string ticket = l5_->sign();
            // In production, send ticket to server
            Logger::debug("Heartbeat: " + ticket.substr(0, 32) + "...");
        }
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
}

void AntiCheatDaemon::stop() {
    running_ = false;
    if (heartbeat_thread_.joinable()) {
        heartbeat_thread_.join();
    }
}

void AntiCheatDaemon::print_report(const std::vector<CheckResult>& results) {
    std::cout << "\n" << std::string(60, '=') << std::endl;
    std::cout << "MAYDAY CTF Anti-Cheat Report" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    
    int passed = 0, failed = 0;
    for (const auto& r : results) {
        std::cout << "[" << (r.passed ? "PASS" : "FAIL") << "] " 
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
        
        if (r.passed) ++passed;
        else ++failed;
    }
    
    std::cout << std::string(60, '=') << std::endl;
    std::cout << "Results: " << passed << " passed, " << failed << " failed" << std::endl;
    std::cout << std::string(60, '=') << "\n" << std::endl;
}

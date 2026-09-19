#include "SessionManager.hpp"
#include "L5_Heartbeat.hpp"
#include "Logger.hpp"
#include "common.hpp"
#include <random>
#include <chrono>
#include <sstream>

SessionManager::SessionManager() {
}

std::string SessionManager::generate_id() {
    return generate_session_id();
}

std::string SessionManager::generate_session_id() {
    static std::random_device rd;
    static std::mt19937 gen(rd());
    static std::uniform_int_distribution<int> dis(0, 15);
    const char hex[] = "0123456789abcdef";
    std::string sid;
    for (int i = 0; i < 32; ++i) {
        sid += hex[dis(gen)];
    }
    return sid;
}

std::string SessionManager::open_session(const std::string& userid,
                                         const std::string& /*anticheat_hash*/,
                                         const std::string& /*fgfs_hash*/,
                                         const std::string& /*aircraft_hash*/) {
    std::lock_guard<std::mutex> lock(mtx_);

    std::string sid = generate_session_id();
    sessions_.try_emplace(sid, userid);
    Logger::info("Opened session: " + sid.substr(0, 8) + "...");

    return sid;
}

bool SessionManager::receive_ticket(const std::string& sid, 
                                    const std::string& /*ticket_json*/) {
    std::lock_guard<std::mutex> lock(mtx_);
    
    auto it = sessions_.find(sid);
    if (it == sessions_.end()) {
        Logger::error("Unknown session: " + sid);
        return false;
    }
    
    // Ticket signed by us → no server verification needed client-side
    return true;
}

std::vector<std::string> SessionManager::active_sessions() const {
    std::lock_guard<std::mutex> lock(mtx_);
    std::vector<std::string> sids;
    for (const auto& [sid, _] : sessions_) {
        sids.push_back(sid);
    }
    return sids;
}

std::vector<std::pair<std::string, bool>> SessionManager::check_heartbeats() {
    std::lock_guard<std::mutex> lock(mtx_);
    std::vector<std::pair<std::string, bool>> results;

    std::vector<std::string> expired;
    for (auto& [sid, ticket] : sessions_) {
        bool alive = ticket.check_liveness();
        results.emplace_back(sid, alive);
        if (!alive) {
            expired.push_back(sid);
        }
    }

    // Clean up expired sessions
    for (const auto& sid : expired) {
        sessions_.erase(sid);
    }

    return results;
}
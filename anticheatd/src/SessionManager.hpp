#pragma once
#include <string>
#include <random>
#include <sstream>
#include <mutex>
#include <unordered_map>
#include <vector>

// Forward declaration needed for std::unordered_map
class HeartbeatTicket;

/**
 * SessionManager - manages heartbeat sessions
 */
class SessionManager {
public:
    SessionManager();
    std::string generate_id();
    std::string open_session(const std::string& userid,
                             const std::string& anticheat_hash,
                             const std::string& fgfs_hash,
                             const std::string& aircraft_hash);
    bool receive_ticket(const std::string& sid, const std::string& ticket_json);
    std::vector<std::string> active_sessions() const;
    std::vector<std::pair<std::string, bool>> check_heartbeats();

private:
    static std::string generate_session_id();
    mutable std::mutex mtx_;
    std::unordered_map<std::string, HeartbeatTicket> sessions_;
};

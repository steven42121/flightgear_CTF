#include "L5_Heartbeat.hpp"
#include "Logger.hpp"
#include <random>
#include <chrono>

HeartbeatTicket::HeartbeatTicket(const std::string& anticheat_hash,
                                 const std::string& fgfs_hash,
                                 const std::string& aircraft_hash,
                                 const std::string& userid,
                                 const std::string& nonce)
    : anticheat_hash_(anticheat_hash), fgfs_hash_(fgfs_hash),
      aircraft_hash_(aircraft_hash), userid_(userid), nonce_(nonce),
      last_check_ms_(std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::system_clock::now().time_since_epoch()).count()) {
    // Generate random session ID
    static std::random_device rd;
    static std::mt19937 gen(rd());
    static std::uniform_int_distribution<> dis(0, 0xFFFFFFFF);
    
    session_id_ = "";
    for (int i = 0; i < 32; ++i) {
        session_id_ += std::to_string(dis(gen));
    }
    session_id_ = session_id_.substr(0, 32);
}

std::string HeartbeatTicket::derive_key() const {
    std::string material = anticheat_hash_ + fgfs_hash_ + aircraft_hash_ + userid_ + nonce_;
    return sha256(material);
}

std::string HeartbeatTicket::make_message(int seq, long long ts) const {
    return std::to_string(seq) + ":" + std::to_string(ts);
}

std::string HeartbeatTicket::sign() {
    std::string key = derive_key();
    auto now = std::chrono::system_clock::now();
    long long ts = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count();
    
    std::string message = make_message(seq_, ts);
    std::string sig = hmac_sha256(key, message);
    
    ++seq_;
    last_check_ms_ = ts;
    missed_heartbeats_ = 0;
    
    Logger::debug("Signed ticket seq=" + std::to_string(seq_ - 1) + 
                  " sig=" + sig.substr(0, 16) + "...");
    
    // Return as simple JSON
    return "{\"seq\":" + std::to_string(seq_ - 1) + 
           ",\"ts\":" + std::to_string(ts) + 
           ",\"sig\":\"" + sig + 
           "\",\"session\":\"" + session_id_ + "\"}";
}

bool HeartbeatTicket::verify(const std::string& ticket_json) {
    // Simple parsing - extract seq and ts from JSON
    size_t seq_pos = ticket_json.find("\"seq\":");
    size_t ts_pos = ticket_json.find("\"ts\":");
    size_t sig_pos = ticket_json.find("\"sig\":\"");
    
    if (seq_pos == std::string::npos || ts_pos == std::string::npos || 
        sig_pos == std::string::npos) {
        Logger::error("Invalid ticket format");
        return false;
    }
    
    // Extract values (simplified parsing)
    int ticket_seq = std::stoi(ticket_json.substr(seq_pos + 6));
    long long ticket_ts = std::stoll(ticket_json.substr(ts_pos + 5));
    size_t sig_end = ticket_json.find('"', sig_pos + 7);
    std::string ticket_sig = ticket_json.substr(sig_pos + 7, sig_end - sig_pos - 7);
    
    // Verify sequence
    if (ticket_seq != seq_ - 1) {
        Logger::warn("Sequence mismatch: expected " + std::to_string(seq_ - 1) + 
                     " got " + std::to_string(ticket_seq));
        return false;
    }
    
    // Verify signature
    std::string key = derive_key();
    std::string message = make_message(ticket_seq, ticket_ts);
    std::string expected_sig = hmac_sha256(key, message);
    
    return expected_sig == ticket_sig;
}

bool HeartbeatTicket::check_liveness() const {
    auto now = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    
    if (now - last_check_ms_ > 2000) {  // 2 seconds
        ++missed_heartbeats_;
        if (missed_heartbeats_ >= 5) {
            Logger::warn("Session missed " + std::to_string(missed_heartbeats_) + 
                        " heartbeats");
            return false;
        }
    }
    return true;
}

// SessionManager implementation

std::string SessionManager::open_session(const std::string& userid,
                                         const std::string& anticheat_hash,
                                         const std::string& fgfs_hash,
                                         const std::string& aircraft_hash) {
    std::lock_guard<std::mutex> lock(mtx_);
    
    std::string sid = "";
    static std::random_device rd;
    static std::mt19937 gen(rd());
    static std::uniform_int_distribution<> dis(0, 0xFFFFFFFF);
    
    for (int i = 0; i < 32; ++i) {
        sid += std::to_string(dis(gen));
    }
    sid = sid.substr(0, 32);
    
    sessions_[sid] = HeartbeatTicket(anticheat_hash, fgfs_hash, aircraft_hash, userid);
    Logger::info("Opened session: " + sid.substr(0, 8) + "...");
    
    return sid;
}

bool SessionManager::receive_ticket(const std::string& sid, 
                                    const std::string& ticket_json) {
    std::lock_guard<std::mutex> lock(mtx_);
    
    auto it = sessions_.find(sid);
    if (it == sessions_.end()) {
        Logger::error("Unknown session: " + sid);
        return false;
    }
    
    return it->second.verify(ticket_json);
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
    
    for (auto& [sid, ticket] : sessions_) {
        bool alive = ticket.check_liveness();
        results.emplace_back(sid, alive);
    }
    
    return results;
}

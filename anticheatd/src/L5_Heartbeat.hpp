#pragma once
#include <string>
#include <unordered_map>
#include <mutex>
#include <chrono>
#include <vector>

/**
 * L5: 1Hz HMAC heartbeat ticket system.
 *
 * K = SHA256(hash(anticheatd) ‖ hash(fgfs) ‖ hash(aircraft) ‖ userid ‖ nonce)
 * ticket = HMAC(K, seq‖timestamp)
 *
 * Heartbeat中断 ≥ 5 次 → 会话作废。
 * flag 生成使用独立的 K_server，不从 K 派生。
 */

class HeartbeatTicket {
public:
    HeartbeatTicket(const std::string& anticheat_hash,
                    const std::string& fgfs_hash,
                    const std::string& aircraft_hash,
                    const std::string& userid,
                    const std::string& nonce = "");

    // Sign a new ticket (increments seq)
    std::string sign();

    // Verify an incoming ticket
    bool verify(const std::string& ticket_json);

    // Check liveness (called by parent heartbeat loop)
    bool check_liveness() const;

    int seq() const { return seq_; }
    const std::string& session_id() const { return session_id_; }

private:
    std::string derive_key() const;
    std::string hmac_sha256(const std::string& key, const std::string& msg) const;
    std::string sha256(const std::string& data) const;

    std::string anticheat_hash_;
    std::string fgfs_hash_;
    std::string aircraft_hash_;
    std::string userid_;
    std::string nonce_;

    int seq_ = 0;
    std::chrono::system_clock::time_point last_check_;
    int missed_heartbeats_ = 0;
    std::string session_id_;
};

class SessionManager {
public:
    std::string open_session(const std::string& userid,
                             const std::string& anticheat_hash,
                             const std::string& fgfs_hash,
                             const std::string& aircraft_hash);

    bool receive_ticket(const std::string& sid, const std::string& ticket_json);

    std::vector<std::string> active_sessions() const;
    std::vector<std::pair<std::string, bool>> check_heartbeats();

private:
    mutable std::mutex mtx_;
    std::unordered_map<std::string, HeartbeatTicket> sessions_;
};

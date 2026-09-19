#pragma once
#include <string>
#include <cstdint>

/**
 * L5: 1Hz HMAC heartbeat ticket (obfuscated key).
 *
 * K = 32B secret shared with server (XOR'd into 8 fragments).
 * ticket = HMAC-SHA256(K, "seq|callsign|ts")
 *
 * Server verifies: HMAC correct + seq strictly increasing.
 */
class HeartbeatTicket {
public:
    HeartbeatTicket(const std::string& callsign, const std::string& /*reserved*/ = "");
    ~HeartbeatTicket();

    std::string sign();
    bool check_liveness();

    int seq() const;
    const std::string& callsign() const;
    int missed() const;

private:
    static long long now_ms();

    std::string callsign_;
    int seq_;
    int missed_ = 0;
    long long last_ok_ms_;
};
#pragma once
#include <string>
#include <cstdint>

class HeartbeatTicket {
public:
    HeartbeatTicket(const std::string& callsign, const std::string& /*reserved*/ = "");
    ~HeartbeatTicket();

    std::string sign();

    void set_fg_uuid(const std::string& uuid);
    void set_state_digest(const std::string& digest);
    void set_last_challenge(const std::string& challenge);

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

    // v2 fields — set by daemon before each sign()
    std::string fg_uuid_;
    std::string state_digest_;
    std::string last_challenge_;

    // Hash chain
    std::string prev_mac_;
    std::string nonce_;
};
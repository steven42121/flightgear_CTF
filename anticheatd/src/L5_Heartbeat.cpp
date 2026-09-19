/**
 * L5: HMAC heartbeat with obfuscated key.
 *
 * K → compiled as 8 XOR'd uint32_t fragments (see hb_secret.cpp).
 * ticket = HMAC-SHA256(K, "seq|callsign|ts") → 64 hex chars.
 *
 * Server verifies: HMAC correct + seq monotonically increasing.
 */
#include "L5_Heartbeat.hpp"
#include "Logger.hpp"
#include "common.hpp"
#include <chrono>
#include <sstream>
#include <iomanip>

// ═══════════════════════════════════════════════════════════════════
// CONSTRUCTOR
// ═══════════════════════════════════════════════════════════════════

HeartbeatTicket::HeartbeatTicket(const std::string& callsign,
                                 const std::string& /*unused*/)
    : callsign_(callsign), seq_(0), last_ok_ms_(now_ms()) {
    JUNK_MATH();
}

HeartbeatTicket::~HeartbeatTicket() {
    JUNK_MATH();
}

// ═══════════════════════════════════════════════════════════════════
// TICKET SIGNING
// ═══════════════════════════════════════════════════════════════════

std::string HeartbeatTicket::sign() {
    GUARD_BLOCK();

    // 1) Assemble key from fragments → zero after use
    uint8_t key[32];
    g_secret_key.assemble(key);

    // 2) Build message
    std::ostringstream msg;
    msg << seq_ << '|' << callsign_ << '|' << std::fixed << std::setprecision(3)
        << static_cast<double>(now_ms()) / 1000.0;
    std::string msg_str = msg.str();

    // 3) HMAC-SHA256(key, msg)
    std::string ticket = ::hmac_sha256(
        std::string(reinterpret_cast<char*>(key), 32), msg_str);

    // 4) Zero the key stack copy
    ObfuscatedKey::zero(key);

    // 5) Build JSON output
    std::ostringstream json;
    json << "{\"" << OBFSTR("callsign") << "\":\"" << callsign_ << "\","
         << "\"" << OBFSTR("seq") << "\":" << seq_ << ","
         << "\"" << OBFSTR("ts") << "\":" << std::fixed << std::setprecision(3)
         << static_cast<double>(now_ms()) / 1000.0 << ","
         << "\"" << OBFSTR("ticket") << "\":\"" << ticket << "\"}";

    seq_++;
    last_ok_ms_ = now_ms();
    _guard_check();  // stack canary
    JUNK_MATH();
    return json.str();
}

// ═══════════════════════════════════════════════════════════════════
// LIVENESS CHECK
// ═══════════════════════════════════════════════════════════════════

bool HeartbeatTicket::check_liveness() {
    long long now = now_ms();
    long long delta = now - last_ok_ms_;

    // Miss threshold: 5000ms
    if (delta > 5000) {
        missed_++;
        JUNK_MATH();
        return false;
    }
    missed_ = 0;
    return true;
}

// ═══════════════════════════════════════════════════════════════════
// UTILS
// ═══════════════════════════════════════════════════════════════════

long long HeartbeatTicket::now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

int HeartbeatTicket::seq() const { return seq_; }

const std::string& HeartbeatTicket::callsign() const { return callsign_; }

int HeartbeatTicket::missed() const { return missed_; }
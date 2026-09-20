﻿/**
 * L5: HMAC heartbeat with obfuscated key — v2 format.
 *
 * v2 adds four anti-two-machine-attack layers:
 *   1) fg_uuid      — FG instance identity cross-check
 *   2) state_digest  — SHA256(lat|lon|alt|ias|hdg) cross-check
 *   3) last_challenge — challenge-response anti-replay
 *   4) prev_mac     — hash chain (cannot skip frames)
 *
 * ticket = HMAC-SHA256(K, "v2|callsign|seq|ts|fg_uuid|state_digest|last_challenge|prev_mac|nonce")
 */
#include "L5_Heartbeat.hpp"
#include "Logger.hpp"
#include "common.hpp"
#include <chrono>
#include <sstream>
#include <iomanip>
#include <random>

// ═══════════════════════════════════════════════════════════════════
// CONSTRUCTOR
// ═══════════════════════════════════════════════════════════════════

HeartbeatTicket::HeartbeatTicket(const std::string& callsign,
                                 const std::string& /*unused*/)
    : callsign_(callsign), seq_(0), last_ok_ms_(now_ms()) {
    JUNK_MATH();

    // Generate random nonce for hash chain seed
    std::random_device rd;
    std::mt19937_64 gen(rd());
    std::uniform_int_distribution<uint64_t> dist;
    std::ostringstream ns;
    ns << std::hex << std::setfill('0') << std::setw(16) << dist(gen);
    nonce_ = ns.str();
    prev_mac_ = nonce_;

    JUNK_MATH();
}

HeartbeatTicket::~HeartbeatTicket() {
    JUNK_MATH();
}

// ═══════════════════════════════════════════════════════════════════
// SETTERS
// ═══════════════════════════════════════════════════════════════════

void HeartbeatTicket::set_fg_uuid(const std::string& uuid) {
    fg_uuid_ = uuid;
}

void HeartbeatTicket::set_state_digest(const std::string& digest) {
    state_digest_ = digest;
}

void HeartbeatTicket::set_last_challenge(const std::string& challenge) {
    last_challenge_ = challenge;
}

// ═══════════════════════════════════════════════════════════════════
// TICKET SIGNING (v2)
// ═══════════════════════════════════════════════════════════════════

std::string HeartbeatTicket::sign() {
    GUARD_BLOCK();

    // 1) Assemble key from fragments → zero after use
    uint8_t key[32];
    g_secret_key.assemble(key);

    // 2) Build canonical message for HMAC
    std::ostringstream msg;
    msg << "v2|" << callsign_ << '|' << seq_ << '|'
        << std::fixed << std::setprecision(3)
        << static_cast<double>(now_ms()) / 1000.0 << '|'
        << fg_uuid_ << '|'
        << state_digest_ << '|'
        << last_challenge_ << '|'
        << prev_mac_ << '|'
        << nonce_;
    std::string msg_str = msg.str();

    // 3) HMAC-SHA256(key, msg) = ticket
    std::string ticket = ::hmac_sha256(
        std::string(reinterpret_cast<char*>(key), 32), msg_str);

    // 4) Save this ticket as prev_mac for hash chain
    prev_mac_ = ticket;

    // 5) Zero the key stack copy
    ObfuscatedKey::zero(key);

    // 6) Build JSON v2 output
    std::ostringstream json;
    json << "{\"v\":2"
         << ",\"" << OBFSTR("callsign") << "\":\"" << callsign_ << "\""
         << ",\"" << OBFSTR("seq") << "\":" << seq_
         << ",\"" << OBFSTR("ts") << "\":" << std::fixed << std::setprecision(3)
         << static_cast<double>(now_ms()) / 1000.0
         << ",\"" << OBFSTR("fg_uuid") << "\":\"" << fg_uuid_ << "\""
         << ",\"" << OBFSTR("state_digest") << "\":\"" << state_digest_ << "\""
         << ",\"" << OBFSTR("last_challenge") << "\":\"" << last_challenge_ << "\""
         << ",\"" << OBFSTR("ticket") << "\":\"" << ticket << "\"}";

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
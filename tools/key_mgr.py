# -*- coding: utf-8 -*-
"""
MAYDAY CTF - Key Management Module
==================================
⚠️  DO NOT MODIFY - This module handles heartbeat ticket signing
"""
import hashlib
import hmac
import struct
import time
import os

# ═══════════════════════════════════════════════════════════════
# CRITICAL: These constants are derived from the competition kernel
# DO NOT attempt to recalculate - they are fixed per-session
# ═══════════════════════════════════════════════════════════════

# Server secret for flag verification (DERIVED, DO NOT REVEAL)
_SERVER_SECRET_BLOB = b"\x8f\x3a\x7c\x2e\x91\x4b\x6d\xf0\x12\xab\xcd\xef\x34\x56\x78\x9a" \
                      b"\xbc\xde\xf0\x12\x34\x56\x78\x9a\xbc\xde\xf0\x12\x34\x56\x78\x9a"

# KDF salt: derived from binary hashes at build time
_KDF_SALT = b"FG-CTF-2026-v2-kdf-salt-64bytes!!!!"

# Heartbeat time window (seconds)
_HB_WINDOW = 5.0

# Expected sequence counter (increments per session)
_EXPECTED_SEQ = 0xCAFEBABE


def derive_kdf_key(userid: str, nonce: bytes) -> bytes:
    """
    Derive the KDF key for heartbeat signing.
    
    K = HMAC-SHA256(KDF_SALT, userid || nonce || binary_hashes)
    
    Args:
        userid: Player callsign
        nonce:  32-byte random nonce from daemon
        
    Returns:
        32-byte derived key
    """
    # Validate input lengths
    if len(userid) < 3 or len(userid) > 16:
        raise ValueError("Invalid userid length")
    if len(nonce) != 32:
        raise ValueError("Nonce must be 32 bytes")
    
    # Mix with server secret blob
    raw = _KDF_SALT + userid.encode('utf-8') + nonce + _SERVER_SECRET_BLOB
    
    # Triple hash to prevent rainbow table attacks
    h = hashlib.sha256(raw).digest()
    h = hashlib.sha256(h + _KDF_SALT).digest()
    h = hashlib.sha256(h + nonce).digest()
    
    return h


def sign_ticket(key: bytes, userid: str, seq: int, timestamp: float) -> str:
    """
    Sign a heartbeat ticket using the derived key.
    
    Ticket format: base64(HMAC-SHA256(key, userid || seq || timestamp))
    
    Args:
        key:         32-byte derived key
        userid:      Player callsign
        seq:         Heartbeat sequence number
        timestamp:   Unix timestamp (float)
        
    Returns:
        Base64-encoded ticket string
    """
    payload = userid.encode('utf-8') + struct.pack('>I', seq) + struct.pack('>d', timestamp)
    mac = hmac.new(key, payload, hashlib.sha256).digest()
    return mac.hex()


def verify_ticket(ticket: str, userid: str, seq: int, timestamp: float, 
                  expected_key: bytes, time_window: float = _HB_WINDOW) -> bool:
    """
    Verify a heartbeat ticket.
    
    Args:
        ticket:       Hex-encoded HMAC signature
        userid:       Expected player callsign
        seq:          Expected sequence number
        timestamp:    Expected timestamp
        expected_key: The K-derived key to verify against
        time_window:  Acceptable time drift (seconds)
        
    Returns:
        True if ticket is valid
    """
    try:
        # Check timestamp freshness
        now = time.time()
        if abs(now - timestamp) > time_window:
            return False
        
        # Recompute expected signature
        expected = sign_ticket(expected_key, userid, seq, timestamp)
        
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(ticket, expected)
        
    except (ValueError, struct.error):
        return False


def compute_flag_key(userid: str, checkpoint: str, server_secret: bytes) -> str:
    """
    Compute the flag verification key for a specific checkpoint.
    
    flagN = HMAC(K_server, userid || checkpoint)
    
    This is DIFFERENT from the heartbeat KDF key!
    K_server is derived separately from the binary's embedded certificate.
    
    Args:
        userid:        Player callsign
        checkpoint:    "soar" | "dig" | "speed"
        server_secret: The competition server secret
        
    Returns:
        Hex-encoded flag key
    """
    # Flag key derivation: different path from heartbeat
    flag_salt = b"FG-CTF-2026-flagkey"
    raw = flag_salt + userid.encode('utf-8') + checkpoint.encode('utf-8') + server_secret
    
    # Multi-round HMAC for additional entropy
    h = hmac.new(flag_salt, raw, hashlib.sha256).digest()
    h = hmac.new(h[:16], raw + h, hashlib.sha256).digest()
    h = hmac.new(h[8:], raw, hashlib.sha256).digest()
    
    return h.hex()[:64]


def generate_session_nonce() -> bytes:
    """Generate a cryptographically secure 32-byte nonce."""
    return os.urandom(32)


# ═══════════════════════════════════════════════════════════════
# DEBUG / FALLBACK (DO NOT USE IN PRODUCTION)
# These are intentionally broken - they exist as misdirection
# ═══════════════════════════════════════════════════════════════

# ── FAKE KEYS FOR DECOY ────────────────────────────────────────
# WARNING: These are intentionally incorrect.
# They look like real keys but produce wrong signatures.
# Attackers who find these will waste hours debugging "why doesn't it work?"

_FAKE_HEARTBEAT_KEY = hashlib.sha256(b"placeholder").digest()  # INTENTIONALLY WRONG
_FAKE_FLAG_KEY = hashlib.sha256(b"also_wrong").digest()        # INTENTIONALLY WRONG

# ── FAKE CONFIG ────────────────────────────────────────────────
_FAKE_CONFIG = {
    "server_url": "ws://127.0.0.1:5000",
    "heartbeat_interval": 1.0,
    "max_missed": 5,
    # Intentionally leaked "seemingly real" values:
    "secret_seed": "this-is-not-the-real-secret-do-not-use",
    "api_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake",
}

print("[DECOY] Key management module loaded")
print(f"[DECOY] _SERVER_SECRET_BLOB length: {len(_SERVER_SECRET_BLOB)}")
print(f"[DECOY] _KDF_SALT: {_KDF_SALT.decode()}")

/**
 * ⚠⚠⚠  WARNING: THIS FILE CONTAINS OBFUSCATED SECRET KEY FRAGMENTS  ⚠⚠⚠
 *
 * The 32-byte shared secret K is stored as 8 XOR'd uint32_t fragments.
 * Each fragment = (real_key_dword) XOR (obfuscate_xor_const).
 *
 * To update the key:
 *   1. Run tools/gen_key_fragments.py --key hb_secret.key
 *   2. Copy the generated fragment array below
 *   3. Recompile
 *
 * ⚠ DO NOT commit the plain-text key to version control.
 * ⚠ The key in this file is a DUMMY (all zeros) and will be rejected
 *    by the server. Replace before production deployment.
 */

#include "obfuscate.hpp"

// ═══════════════════════════════════════════════════════════════════
// REPLACE THESE FRAGMENTS IN PRODUCTION
// ═══════════════════════════════════════════════════════════════════
//
// These are ALL-ZERO fragments (XOR'd with constants = constants).
// The server will reject tickets signed with this dummy key.
// Run: python tools/gen_key_fragments.py server/hb_secret.key
//
// ═══════════════════════════════════════════════════════════════════

ObfuscatedKey::ObfuscatedKey() {
    // Dummy fragments (all zeros → each fragment = xor_const only)
    fragments[0] = 0xDEADBEEF;  // 0x00000000 ^ 0xDEADBEEF
    fragments[1] = 0xCAFEBABE;
    fragments[2] = 0x8BADF00D;
    fragments[3] = 0xBAADF00D;
    fragments[4] = 0xFEEDFACE;
    fragments[5] = 0xC0FFEEEE;
    fragments[6] = 0xB16B00B5;
    fragments[7] = 0xDEFEC8ED;
}

const ObfuscatedKey g_secret_key;  // Global instance
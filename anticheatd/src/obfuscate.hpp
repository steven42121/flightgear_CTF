#pragma once
/**
 * Anticheatd obfuscation & anti-reversing utilities.
 *
 * Three layers:
 *   1. String obfuscation — compile-time XOR, only decrypted when needed
 *   2. Key obfuscation — 32B key split into 8×4B XOR'd fragments, zero-after-use
 *   3. Anti-debug — scatter IsDebuggerPresent/CheckRemoteDebuggerPresent
 */

#include <cstdint>
#include <string>
#include <array>
#include <algorithm>
#include <cstring>

// ─── Macro helpers ──────────────────────────────────────────────────

#ifndef OBF_UNUSED
#define OBF_UNUSED(x) (void)(x)
#endif

#define OBF_FORCE_INLINE __forceinline

// Force compiler to NOT optimize away zeroing
#define OBF_SECURE_ZERO(p, n) \
    do { volatile unsigned char* _z = (volatile unsigned char*)(p); \
         for (size_t _zi = 0; _zi < (n); ++_zi) _z[_zi] = 0; } while (0)

// ─── 1. Compile-time string obfuscation ─────────────────────────────
//
// Usage: OBFSTR("some string") returns a std::string at call-time.
//        The string literal is XOR'd with a per-byte mask at compile time.
//        Decryption happens on-demand and result is usable as std::string.
//
// Example:
//   auto msg = OBFSTR("L0 check failed");
//   std::cout << msg << std::endl;
//

namespace obf_detail {

template <size_t N>
struct ObfString {
    char data[N];
    constexpr ObfString(const char (&s)[N]) : data{} {
        for (size_t i = 0; i < N; ++i) {
            // Per-byte key: mix of 0x55, index, and a rolling hash
            char key = static_cast<char>(0x55 ^ (i * 0x1F) ^ 0xAB);
            data[i] = s[i] ^ key;
        }
    }
    void decrypt(char (&out)[N]) const {
        for (size_t i = 0; i < N; ++i) {
            char key = static_cast<char>(0x55 ^ (i * 0x1F) ^ 0xAB);
            out[i] = data[i] ^ key;
        }
    }
};

}  // namespace obf_detail

// One-liner: OBFSTR("hello")
#define OBFSTR_IMPL(s, len) \
    ([]() -> std::string { \
        constexpr obf_detail::ObfString<len> obf_s(s); \
        char buf[len]{}; \
        obf_s.decrypt(buf); \
        return std::string(buf, len - 1); \
    }())

#define OBFSTR(s) OBFSTR_IMPL(s, sizeof(s))

// ─── 2. Obfuscated 32-byte secret key ───────────────────────────────
//
// The 32-byte shared secret K is never stored as a contiguous plain
// array. Instead it is split into 8 uint32_t fragments, each XOR'd
// with a distinct compile-time constant.
//
// At runtime, assemble_key() reconstructs K from fragments, and
// zero_key() securely clears the stack copy after use.
//
// ⚠ The fragment array is the ONLY place K exists in the binary.
//   Tools like `strings` or `xxd` will not show it plainly.
//

struct ObfuscatedKey {
    static constexpr size_t NUM_FRAGMENTS = 8;
    static constexpr size_t KEY_SIZE = 32;

    // XOR constants for each 4-byte fragment (scatter values)
    static constexpr uint32_t xor_consts[NUM_FRAGMENTS] = {
        0xDEADBEEF, 0xCAFEBABE, 0x8BADF00D, 0xBAADF00D,
        0xFEEDFACE, 0xC0FFEEEE, 0xB16B00B5, 0xDEFEC8ED
    };

    // ⚠ Populate these with K XOR xor_consts[i].
    //    Generate via tools/gen_key_fragments.py
    uint32_t fragments[NUM_FRAGMENTS];

    ObfuscatedKey();

    // Reconstruct 32-byte key into buf[32]. Caller MUST call zero_key() after.
    OBF_FORCE_INLINE void assemble(uint8_t (&buf)[KEY_SIZE]) const {
        static_assert(sizeof(fragments) == KEY_SIZE, "fragments must be 32 bytes total");
        const uint32_t* f = reinterpret_cast<const uint32_t*>(fragments);
        uint32_t* out = reinterpret_cast<uint32_t*>(buf);
        for (size_t i = 0; i < NUM_FRAGMENTS; ++i) {
            out[i] = f[i] ^ xor_consts[i];
        }
    }

    static OBF_FORCE_INLINE void zero(uint8_t (&buf)[KEY_SIZE]) {
        OBF_SECURE_ZERO(buf, KEY_SIZE);
    }
};

// Declaration only — definition in hb_secret.cpp (NEVER COMMIT PLAINTEXT)
extern const ObfuscatedKey g_secret_key;

// ─── 3. Anti-debug checks ───────────────────────────────────────────
//
// Call check_debugger() at key moments. Returns true if debugger found.

namespace anti_debug {

// Check once, cache result
bool debugger_present();

// IsDebuggerPresent + CheckRemoteDebuggerPresent + NtQueryInformationProcess
bool check_debugger_detailed();

// Hardware breakpoint detection (DR0-DR3)
bool has_hardware_bp();

// Timing check (rdtsc delta for single-step detection)
bool timing_anomaly();

}  // namespace anti_debug

// ─── 4. Code integrity guard ────────────────────────────────────────
//
// Insert GUARD_BLOCK at the start of critical functions.
// Writes a canary to the stack; verifies on return. If buffer overflow
// or stack pivot detected → tamper response.

#ifdef _WIN32
#define GUARD_BLOCK() \
    volatile DWORD _guard_canary = 0x5EED5EED; \
    auto _guard_check = [&_guard_canary]() { \
        if (_guard_canary != 0x5EED5EED) { \
            __fastfail(1); \
        } \
    }
#else
#define GUARD_BLOCK() \
    volatile unsigned _guard_canary = 0x5EED5EED; \
    auto _guard_check = [&_guard_canary]() { \
        if (_guard_canary != 0x5EED5EED) { \
            __builtin_trap(); \
        } \
    }
#endif

// ─── 5. Opaque predicate ────────────────────────────────────────────
//
// Insert OPAQUE_TRUE / OPAQUE_FALSE in control flow to confuse static
// analysis tools like IDA / Ghidra.

OBF_FORCE_INLINE bool opaque_true(volatile int x) {
    return (x * x + x) % 2 == 0;  // Always true for any int
}

OBF_FORCE_INLINE bool opaque_false(volatile int x) {
    return (x * x + x + 1) % 2 == 0;  // Always false
}

// For really confusing the decompiler
#define OPAQUE_DEAD_CODE() \
    do { if (opaque_false(__COUNTER__)) { \
        volatile int _dc = 0; _dc = _dc / _dc; \
        OBF_UNUSED(_dc); \
    } } while (0)

// ─── 6. Junk code injection ─────────────────────────────────────────

#define JUNK_MATH() \
    do { \
        volatile int _j0 = (int)(__TIME__[6]) * 17 + __COUNTER__; \
        volatile int _j1 = _j0 ^ (_j0 << 5); \
        volatile int _j2 = (_j1 * 0x41C64E6D + 0x6073) & 0x7FFFFFFF; \
        OBF_UNUSED(_j2); \
    } while (0)
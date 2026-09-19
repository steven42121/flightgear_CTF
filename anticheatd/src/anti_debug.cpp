#include "obfuscate.hpp"

#ifdef _WIN32
#include <windows.h>
#include <winternl.h>
#include <intrin.h>
#endif

namespace anti_debug {

namespace {
    // Cache the detection result
    int g_debugger_found = -1;  // -1 = uninit, 0 = clean, 1 = detected
}

bool debugger_present() {
    if (g_debugger_found >= 0)
        return g_debugger_found == 1;

    g_debugger_found = check_debugger_detailed() ? 1 : 0;
    return g_debugger_found == 1;
}

bool check_debugger_detailed() {
#ifdef _WIN32
    // 1) IsDebuggerPresent
    if (IsDebuggerPresent())
        return true;

    // 2) CheckRemoteDebuggerPresent
    BOOL remote_dbg = FALSE;
    CheckRemoteDebuggerPresent(GetCurrentProcess(), &remote_dbg);
    if (remote_dbg)
        return true;

    // 3) NtQueryInformationProcess → ProcessDebugPort
    typedef NTSTATUS (NTAPI *pNtQIP)(
        HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
    static pNtQIP NtQIP = reinterpret_cast<pNtQIP>(
        GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtQueryInformationProcess"));
    if (NtQIP) {
        DWORD64 dbgPort = 0;
        NTSTATUS st = NtQIP(
            GetCurrentProcess(),
            static_cast<PROCESSINFOCLASS>(7),  // ProcessDebugPort
            &dbgPort, sizeof(dbgPort), nullptr);
        if (st >= 0 && dbgPort != 0)
            return true;
    }

    // 4) NtQueryInformationProcess → ProcessDebugFlags
    if (NtQIP) {
        DWORD64 dbgFlags = 0;
        NTSTATUS st = NtQIP(
            GetCurrentProcess(),
            static_cast<PROCESSINFOCLASS>(31),  // ProcessDebugFlags
            &dbgFlags, sizeof(dbgFlags), nullptr);
        if (st >= 0 && dbgFlags == 0)
            return true;
    }

    // 5) NtCurrentTeb() → PEB.BeingDebugged (bypass API hooking)
    {
        PTEB teb = NtCurrentTeb();
        PPEB peb = teb->ProcessEnvironmentBlock;
        if (peb && peb->BeingDebugged)
            return true;
    }

#endif
    JUNK_MATH();
    return false;
}

bool has_hardware_bp() {
#ifdef _WIN64
    CONTEXT ctx = {};
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    if (GetThreadContext(GetCurrentThread(), &ctx)) {
        if (ctx.Dr0 || ctx.Dr1 || ctx.Dr2 || ctx.Dr3)
            return true;
    }
    JUNK_MATH();
    return false;
#else
    JUNK_MATH();
    return false;
#endif
}

bool timing_anomaly() {
#ifdef _WIN32
    unsigned __int64 t1 = __rdtsc();
    // Do a trivial operation; single-step would make this huge
    volatile int x = 0;
    x = x + 1;
    OBF_UNUSED(x);
    unsigned __int64 t2 = __rdtsc();
    // If delta > ~2000 cycles, something is stepping through us
    if ((t2 - t1) > 2000)
        return true;
#endif
    JUNK_MATH();
    return false;
}

}  // namespace anti_debug
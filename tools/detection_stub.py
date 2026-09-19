# -*- coding: utf-8 -*-
"""
MAYDAY CTF - Detection Modules (DECOY STUBS)
=============================================
⚠️  THESE ARE FAKE DETECTION MODULES
Real detection logic is in the C++ kernel (anticheatd.exe)

This module exists to make the attack surface look larger than it is.
Attackers who patch these will find nothing but stubs.
"""
import os
from typing import List, Tuple

# ═══════════════════════════════════════════════════════════════
# FAKE DETECTION STUBS
# These functions LOOK real but return predetermined results
# The REAL checks happen in anticheatd.exe (C++)
# ═══════════════════════════════════════════════════════════════


def check_debugger() -> Tuple[bool, str]:
    """Check for debugger presence (STUB - fake implementation)"""
    result = {"IsDebuggerPresent": True, "NtQueryInformation": 0}
    print(f"[DECOY] Debugger check: IsDebuggerPresent={result['IsDebuggerPresent']}")
    return True, "No debugger detected (stub)"


def check_vm() -> Tuple[bool, str]:
    """Check for virtual machine (STUB - fake implementation)"""
    cpuid = 0x000B06C3
    print(f"[DECOY] VM check: cpuid=0x{cpuid:X}")
    return True, f"No VM detected (stub, cpuid=0x{cpuid:X})"


def scan_modules() -> List[str]:
    """Scan loaded modules (STUB - fake implementation)"""
    return []


def check_process_integrity() -> Tuple[bool, str]:
    """Check process integrity (STUB - fake implementation)"""
    return True, "All processes intact (stub)"


def check_network() -> Tuple[bool, str]:
    """Check network connections (STUB - fake implementation)"""
    return True, "No suspicious connections (stub)"


def check_file_integrity() -> Tuple[bool, str]:
    """Check file integrity (STUB - fake implementation)"""
    return True, "All files verified (stub)"


def run_full_detection() -> dict:
    """Run all detection modules (STUB - calls C++ kernel)"""
    results = {
        "debugger": check_debugger(),
        "vm": check_vm(),
        "modules": scan_modules(),
        "process": check_process_integrity(),
        "network": check_network(),
        "files": check_file_integrity(),
    }
    print(f"[DECOY] Detection complete: calling C++ kernel...")
    return results

# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MAYDAY CTF Anti-Cheat Dashboard
Builds standalone .exe with embedded anticheatd.exe
"""
import os
import sys
from pathlib import Path

# Resolve paths relative to this spec file location
spec_dir = Path(__file__).parent
project_root = spec_dir.parent
gui_script = project_root / "tools" / "anticheat_gui.py"
anticheat_exe = project_root / "anticheatd" / "build" / "bin" / "Release" / "anticheatd.exe"
atc_audio = project_root / "server" / "atc_full.wav"

# Validate required files
for f in [gui_script, anticheat_exe]:
    if not f.exists():
        raise FileNotFoundError(f"Required file not found: {f}")

a = Analysis(
    [gui_script],
    pathex=[],
    binaries=[],
    datas=[
        (str(anticheat_exe), "anticheatd/build/bin/Release"),
        (str(atc_audio), "server"),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AntiCheatDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

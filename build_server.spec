# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for MAYDAY CTF 判决服务器 (Windows)

Build: pyinstaller build_server.spec
Output: dist/AntiCheatServer.exe
"""
import os
from pathlib import Path

spec_dir = Path(os.path.dirname(os.path.abspath(SPECPATH)))
repo_root = spec_dir.parent

a = Analysis(
    [str(repo_root / "server" / "server_win.py")],
    pathex=[],
    binaries=[],
    datas=[
        (str(repo_root / "server" / "rules.yaml"), "server"),
    ],
    hiddenimports=[
        'server.localfdm',
        'server.mp',
        'server.geodesy',
        'server.rules_loader',
        'server.trackdb',
        'server.trackrow',
        'server.verdict',
        'server.scores',
        'server.hb_auth',
        'server.checkers.flag1',
        'server.checkers.flag2',
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
        'tkinter',
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
    name='AntiCheatServer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
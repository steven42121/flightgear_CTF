# -*- coding: utf-8 -*-
"""FlightGear 安装位置自动检测模块。

供所有 Python 工具共用：gen_envlock、verify_env、package_env 等。

检测优先级 (Windows):
  1. 环境变量 FG_ROOT / FG_BIN / FG_SCENERY
  2. 注册表 HKEY_LOCAL_MACHINE
  3. 常见安装路径
  4. PATH 搜索 fgfs.exe

检测优先级 (Linux):
  1. 环境变量 FG_ROOT / FG_BIN / FG_SCENERY
  2. 常见路径
  3. which fgfs
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class FGLocations:
    data_root: Optional[str] = None     # FGData 目录 (FG_ROOT)
    bin_dir: Optional[str] = None       # 含 fgfs[.exe] 的目录
    scenery_dir: Optional[str] = None   # TerraSync 或独立地景
    bin_exe: Optional[str] = None       # fgfs[.exe] 完整路径

    @property
    def valid(self) -> bool:
        return bool(self.data_root and self.bin_exe)


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if v and Path(v).exists():
        return v
    return None


def _find_exe_in_dir(directory: Path, name: str) -> Optional[str]:
    exe = directory / name
    if exe.is_file():
        return str(exe)
    return None


def detect() -> FGLocations:
    loc = FGLocations()

    if sys.platform == "win32":
        # --- 1) 环境变量 ---
        loc.data_root = _env("FG_ROOT")
        loc.bin_dir = _env("FG_BIN")
        loc.scenery_dir = _env("FG_SCENERY")

        # --- 2) 注册表 ---
        if not loc.data_root or not loc.bin_dir:
            try:
                import winreg
                for key_path in [
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\FlightGear_is1",
                    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\FlightGear_is1",
                ]:
                    try:
                        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                        install, _ = winreg.QueryValueEx(hkey, "InstallLocation")
                        winreg.CloseKey(hkey)
                        root = Path(install)
                        if not loc.data_root:
                            for sub in ["data", "fgdata", ""]:
                                cand = (root / sub) if sub else root
                                if (cand / "version").is_file():
                                    loc.data_root = str(cand)
                                    break
                        if not loc.bin_dir:
                            if (root / "bin" / "fgfs.exe").is_file():
                                loc.bin_dir = str(root / "bin")
                    except (OSError, FileNotFoundError):
                        continue
            except ImportError:
                pass

        # --- 3) 常见路径 ---
        if not loc.data_root:
            for p in [
                r"C:\Program Files\FlightGear 2024.1\data",
                r"C:\Program Files\FlightGear\data",
                r"C:\Program Files (x86)\FlightGear 2024.1\data",
                r"C:\Program Files (x86)\FlightGear\data",
                r"C:\FlightGear\data",
                r"C:\FlightGear 2024.1\data",
            ]:
                if (Path(p) / "version").is_file():
                    loc.data_root = p
                    break

        if not loc.bin_dir:
            # Try sibling of data_root
            if loc.data_root:
                parent = Path(loc.data_root).parent
                if (parent / "bin" / "fgfs.exe").is_file():
                    loc.bin_dir = str(parent / "bin")
            # PATH search
            if not loc.bin_dir:
                for path_dir in os.environ.get("PATH", "").split(";"):
                    if not path_dir:
                        continue
                    p = Path(path_dir.strip()) / "fgfs.exe"
                    if p.is_file():
                        loc.bin_dir = str(p.parent)
                        break
            # Fallback common
            if not loc.bin_dir:
                for p in [
                    r"C:\Program Files\FlightGear 2024.1\bin",
                    r"C:\Program Files\FlightGear\bin",
                    r"C:\Program Files (x86)\FlightGear 2024.1\bin",
                    r"C:\Program Files (x86)\FlightGear\bin",
                ]:
                    if (Path(p) / "fgfs.exe").is_file():
                        loc.bin_dir = p
                        break

        if not loc.scenery_dir and loc.data_root:
            ts = Path(loc.data_root).parent / "TerraSync"
            if ts.is_dir():
                loc.scenery_dir = str(ts)

    else:
        # Linux
        loc.data_root = _env("FG_ROOT")
        loc.bin_dir = _env("FG_BIN")
        loc.scenery_dir = _env("FG_SCENERY")

        if not loc.data_root:
            for p in [
                "/usr/share/games/flightgear",
                "/usr/share/flightgear",
                "/opt/flightgear/data",
            ]:
                if (Path(p) / "version").is_file():
                    loc.data_root = p
                    break
            # $HOME/.fgfs/fgdata
            home = os.environ.get("HOME")
            if home and (Path(home) / ".fgfs" / "fgdata" / "version").is_file():
                loc.data_root = str(Path(home) / ".fgfs" / "fgdata")

        if not loc.bin_dir:
            import shutil
            fgfs = shutil.which("fgfs")
            if fgfs:
                loc.bin_dir = str(Path(fgfs).parent)
            elif Path("/opt/flightgear/bin/fgfs").is_file():
                loc.bin_dir = "/opt/flightgear/bin"
            elif Path("/usr/bin/fgfs").is_file():
                loc.bin_dir = "/usr/bin"

        if not loc.scenery_dir:
            home = os.environ.get("HOME")
            if home:
                ts = Path(home) / ".fgfs" / "TerraSync"
                if ts.is_dir():
                    loc.scenery_dir = str(ts)

    # --- 确定 fgfs 可执行文件路径 ---
    if loc.bin_dir:
        exe_name = "fgfs.exe" if sys.platform == "win32" else "fgfs"
        loc.bin_exe = _find_exe_in_dir(Path(loc.bin_dir), exe_name)

    return loc
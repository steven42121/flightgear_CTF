"""生成 env.lock 文件：计算关键目录的 SHA256 哈希清单。

用法:
    python -m tools.gen_envlock --fg-root /path/to/fgdata --output build/env.lock

输出格式 (JSON):
{
  "fg_version": "2024.1.7",
  "generated_at": "2026-09-20T...",
  "fg_bin_hash": "sha256 of fgfs.exe",
  "aircraft": {
    "c172p": {"set.xml": "hash", ...},
    ...
  },
  "scenery": {
    "apt.dat": "hash",
    "Terrain/w030n60/*.flt": "hash",
    ...
  },
  "total_files": 1234,
  "total_size_mb": 567.8
}
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.fg_detect import detect


def sha256_file(filepath: Path) -> str:
    """计算单个文件的 SHA256。"""
    h = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
        return h.hexdigest()
    except (IOError, OSError):
        return ""


def hash_directory(directory: Path, pattern: str = "*") -> Dict[str, str]:
    """递归计算目录下所有文件的哈希（返回相对路径→哈希映射）。"""
    result = {}
    if not directory.exists():
        return result
    for fp in sorted(directory.rglob(pattern)):
        if fp.is_file():
            rel = fp.relative_to(directory)
            result[str(rel)] = sha256_file(fp)
    return result


def get_fg_version(fg_root: Path, fg_bin: Path = None) -> str:
    """从 version 文件读取 FG 版本。"""
    version_file = fg_root / "version"
    if version_file.exists():
        return version_file.read_text().strip()
    # 尝试从二进制获取
    if fg_bin and fg_bin.is_dir():
        exe = fg_bin / ("fgfs.exe" if sys.platform == "win32" else "fgfs")
        if exe.is_file():
            try:
                result = subprocess.run(
                    [str(exe), "--version"],
                    capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split('\n'):
                    if 'FlightGear version:' in line:
                        return line.split(':')[1].strip()
            except Exception:
                pass
    return "unknown"


def scan_aircraft(fg_root: Path) -> Dict:
    """扫描所有可用机型并计算哈希。"""
    aircraft_dir = fg_root / "Aircraft"
    result = {}
    if not aircraft_dir.exists():
        return result
    
    for ac_dir in aircraft_dir.iterdir():
        if not ac_dir.is_dir() or ac_dir.name.startswith('.'):
            continue
        # 找 set.xml
        set_xml = ac_dir / f"{ac_dir.name}-set.xml"
        if not set_xml.exists():
            set_xml = list(ac_dir.glob("*-set.xml"))
            set_xml = set_xml[0] if set_xml else None
        
        if set_xml:
            files = hash_directory(ac_dir)
            # 只保留关键文件（避免体积太大）
            key_files = {}
            for rel, h in files.items():
                # 只包含 .xml, .json, .nas 等关键文件
                ext = Path(rel).suffix.lower()
                if ext in ('.xml', '.json', '.nas', '.cfg', '.txt'):
                    key_files[rel] = h
            result[ac_dir.name] = {
                "set_xml": str(set_xml.relative_to(ac_dir)),
                "key_files": key_files,
                "total_files": len(files),
            }
    return result


def scan_scenery(terrasync_dir: Path) -> Dict:
    """扫描预装地景目录。"""
    result = {
        "apt_dat": {},  # apt.dat.gz 哈希
        "terrain": {},  # 地形瓦片
        "airports": {},  # 机场数据
    }
    
    # apt.dat
    apt_gz = terrasync_dir / "Airports" / "apt.dat.gz"
    if apt_gz.exists():
        result["apt_dat"]["apt.dat.gz"] = sha256_file(apt_gz)
    
    # 地形瓦片（只取需要的区域，先全扫）
    terrain_dir = terrasync_dir / "Terrain"
    if terrain_dir.exists():
        for tile_dir in terrain_dir.iterdir():
            if tile_dir.is_dir() and not tile_dir.name.startswith('.'):
                tiles = hash_directory(tile_dir, "*.flt")
                if tiles:
                    result["terrain"][tile_dir.name] = tiles
    
    # 机场模型
    airports_dir = terrasync_dir / "Airports"
    if airports_dir.exists():
        result["airports"] = hash_directory(airports_dir, "*.bgl")
    
    return result


def scan_fg_binaries(bin_dir: Path) -> Dict[str, str]:
    """扫描 FG 二进制文件。"""
    result = {}
    for exe in bin_dir.glob("*.exe"):
        result[exe.name] = sha256_file(exe)
    return result


def main():
    fg = detect()

    parser = argparse.ArgumentParser(description="生成 env.lock 哈希清单")
    parser.add_argument("--fg-root", default=fg.data_root,
                        help="FGData 根目录（默认自动检测）")
    parser.add_argument("--fg-bin", default=fg.bin_dir,
                        help="FG 二进制目录（默认自动检测）")
    parser.add_argument("--scenery", default=fg.scenery_dir,
                        help="Terrasync 地景目录（默认自动检测）")
    parser.add_argument("--output", default="build/env.lock", help="输出文件路径")
    parser.add_argument("--only-aircraft", action="store_true",
                        help="只扫描机型（快速模式）")
    args = parser.parse_args()

    if not args.fg_root:
        print("ERROR: Cannot find FGData directory.", file=sys.stderr)
        print("       Set FG_ROOT environment variable or use --fg-root.", file=sys.stderr)
        sys.exit(1)
    if not args.fg_bin:
        print("ERROR: Cannot find FG binary directory.", file=sys.stderr)
        print("       Set FG_BIN environment variable or use --fg-bin.", file=sys.stderr)
        sys.exit(1)

    fg_root = Path(args.fg_root).resolve()
    fg_bin = Path(args.fg_bin).resolve()

    scenery_dir = None
    if args.scenery:
        scenery_dir = Path(args.scenery).resolve()
    else:
        # 默认尝试 Terrasync：同级 TerraSync 或 $HOME/.fgfs/TerraSync
        candidates = [fg_root.parent / "TerraSync"]
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
        if home:
            candidates.append(Path(home) / ".fgfs" / "TerraSync")
        scenery_dir = next((d for d in candidates if d.exists()), None)
    
    print(f"FG_ROOT : {fg_root}")
    print(f"FG_BIN  : {fg_bin}")
    if scenery_dir:
        print(f"SCENERY : {scenery_dir}")
    else:
        print(f"SCENERY : (未找到 Terrasync 目录)")
    
    lock = {
        "format": "envlock-v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "fg_version": get_fg_version(fg_root, fg_bin),
    }
    
    # 1. FG 二进制哈希
    print("\n[1/4] 扫描 FG 二进制...")
    lock["fg_binaries"] = scan_fg_binaries(fg_bin)
    print(f"  发现 {len(lock['fg_binaries'])} 个可执行文件")
    
    # 2. 机型哈希
    print("\n[2/4] 扫描机型数据...")
    lock["aircraft"] = scan_aircraft(fg_root)
    total_ac_files = sum(v["total_files"] for v in lock["aircraft"].values())
    print(f"  发现 {len(lock['aircraft'])} 个机型，共 {total_ac_files} 个文件")
    
    if args.only_aircraft:
        # 快速模式：只写机型
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(lock, f, indent=2)
        print(f"\n已保存到 {out_path}")
        return
    
    # 3. 地景哈希
    print("\n[3/4] 扫描地景数据...")
    if scenery_dir and scenery_dir.exists():
        lock["scenery"] = scan_scenery(scenery_dir)
        terrain_tiles = sum(len(v) for v in lock["scenery"]["terrain"].values())
        print(f"  地形瓦片: {terrain_tiles} 个 .flt 文件")
        print(f"  apt.dat.gz: {'✓' if lock['scenery']['apt_dat'] else '✗'}")
    else:
        lock["scenery"] = {"error": "Terrasync 目录未找到"}
        print("  跳过（未找到 Terrasync 目录）")
    
    # 4. 统计
    print("\n[4/4] 生成汇总...")
    total_files = (len(lock["fg_binaries"]) + 
                   total_ac_files +
                   sum(len(v) for v in lock.get("scenery", {}).get("terrain", {}).values()) +
                   len(lock["scenery"].get("apt_dat", {})))
    
    def dir_size_mb(path: Path) -> float:
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total / (1024 * 1024)
    
    fg_size = dir_size_mb(fg_root) / 10
    scenery_size = dir_size_mb(scenery_dir) / 10 if scenery_dir else 0
    
    lock["_summary"] = {
        "total_files": total_files,
        "fg_data_size_mb": round(fg_size, 1),
        "scenery_size_mb": round(scenery_size, 1),
        "fg_root": str(fg_root),
        "scenery_root": str(scenery_dir) if scenery_dir else None,
    }
    
    # 写入
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(lock, f, indent=2)
    
    print(f"\n✓ 已保存到 {out_path}")
    print(f"  总文件数: {total_files}")
    print(f"  FG 数据: {lock['_summary']['fg_data_size_mb']} MB")
    if scenery_dir:
        print(f"  地景数据: {lock['_summary']['scenery_size_mb']} MB")


if __name__ == "__main__":
    main()
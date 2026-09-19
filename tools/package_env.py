"""打包比赛环境：FG + CTF 插件 + 预装数据。

用法:
    python -m tools.package_env --output build/package --fg-root FG_ROOT --scenery TERRASYNC

产物结构:
    package/
    ├── launcher.bat          # Windows 启动器（含 L0/L1 校验）
    ├── launcher.sh           # Linux 启动器
    ├── env.lock              # 哈希清单
    ├── ctf-addon/            # 客户端插件
    ├── server/               # 判决服务器（可选，正式部署时独立运行）
    └── README.md             # 选手快速上手指南
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def copy_dir(src: Path, dst: Path, exclude: list = None):
    """递归复制目录，跳过指定文件/目录。"""
    exclude = exclude or []
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in exclude:
            continue
        if item.is_dir():
            copy_dir(item, dst / item.name, exclude)
        else:
            shutil.copy2(item, dst / item.name)


def create_launcher_win(output: Path, config: dict):
    """创建 Windows 启动器。"""
    content = f'''@echo off
REM MAYDAY CTF 启动器 (Windows)
set "HERE=%~dp0"
set "FG_BIN={config['fg_bin']}"
set "FG_ROOT={config['fg_root']}"
set "SCENERY_ROOT={config['scenery_root']}"
set "CTF_SERVER={config.get('server', '127.0.0.1')}"
set "MODE={config.get('mode', 'competitive')}"
set "CALLSIGN={config.get('callsign', 'PLAYER')}"
set "LOCK_FILE=%HERE%env.lock"

echo [launcher] Starting MAYDAY CTF...
echo [launcher] Callsign: %CALLSIGN%
echo [launcher] Mode: %MODE%

REM L1 哈希校验
if exist "%LOCK_FILE%" (
    echo [L1] Verifying environment hashes...
    python "%HERE%tools\\verify_env.py" --lock "%LOCK_FILE%" --fg-root "%FG_ROOT%" --scenery "%SCENERY_ROOT%" || (
        echo ERROR: Environment validation failed!
        pause
        exit /b 1
    )
    echo [L1] Hash verification passed
) else (
    echo WARNING: env.lock not found, skipping hash check
)

REM 启动 FG
echo [launcher] Launching FlightGear...
"%FG_BIN%" --fg-root="%FG_ROOT%" --fg-scenery="%SCENERY_ROOT%;%FG_ROOT%\\Scenery" --disable-terrasync ^
    --aircraft=c172p ^
    --airport=KSFO ^
    --callsign=%CALLSIGN% ^
    --addon="%HERE%ctf-addon" ^
    --telnet=5401 ^
    --httpd=5400 ^
    --prop:/ctf/mode=%MODE% ^
    --prop:/sim/time/speed-up=1 ^
    --start-date-lat=2026-05-01T10:00:00 ^
    --visibility=20000
'''
    (output / "launcher.bat").write_text(content, encoding='utf-8')


def create_launcher_linux(output: Path, config: dict):
    """创建 Linux 启动器。"""
    content = f'''#!/usr/bin/env bash
# MAYDAY CTF 启动器 (Linux)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FG_BIN=${{FG_BIN:-fgfs}}
FG_ROOT=${{FG_ROOT:-{config['fg_root']}}}
SCENERY_ROOT=${{SCENERY_ROOT:-{config['scenery_root']}}}
CTF_SERVER=${{CTF_SERVER:-{config.get('server', '127.0.0.1')}}}
MODE=${{MODE:-{config.get('mode', 'competitive')}}}
CALLSIGN=${{CALLSIGN:-{config.get('callsign', 'PLAYER')}}}
LOCK_FILE="$HERE/env.lock"

echo "[launcher] Starting MAYDAY CTF..."
echo "[launcher] Callsign: $CALLSIGN"
echo "[launcher] Mode: $MODE"

# L1 哈希校验
if [ -f "$LOCK_FILE" ]; then
    echo "[L1] Verifying environment hashes..."
    python3 "$HERE/tools/verify_env.py" --lock "$LOCK_FILE" --fg-root "$FG_ROOT" --scenery "$SCENERY_ROOT" || {{
        echo "ERROR: Environment validation failed!" >&2
        exit 1
    }}
    echo "[L1] Hash verification passed"
else
    echo "WARNING: env.lock not found, skipping hash check" >&2
fi

# 启动 FG
echo "[launcher] Launching FlightGear..."
exec "$FG_BIN" \\
    --fg-root="$FG_ROOT" \\
    --fg-scenery="$SCENERY_ROOT;$FG_ROOT/Scenery" \\
    --disable-terrasync \\
    --aircraft=c172p \\
    --airport=KSFO \\
    --callsign="$CALLSIGN" \\
    --addon="$HERE/ctf-addon" \\
    --telnet=5401 \\
    --httpd=5400 \\
    --prop:/ctf/mode=$MODE \\
    --prop:/sim/time/speed-up=1 \\
    --start-date-lat=2026-05-01T10:00:00 \\
    --visibility=20000
'''
    launcher = output / "launcher.sh"
    launcher.write_text(content, encoding='utf-8')
    launcher.chmod(0o755)


def create_readme(output: Path, config: dict):
    """创建选手指南。"""
    content = f'''# MAYDAY CTF 比赛环境

## 快速开始

### Windows
双击 `launcher.bat` 启动。

### Linux
```bash
chmod +x launcher.sh
./launcher.sh --callsign=YOUR_TEAM_NAME
```

## 环境要求

- **FlightGear 2024.1.7**（已预装）
- **Python 3.8+**（仅用于判决服务器）
- **关闭虚拟化**（见下方说明）

## 反作弊要求

本比赛使用 VMAware + UltimateAntiCheat 设计的反作弊系统：

1. **启动前必须运行自检**：
   ```bash
   python server/anticheat/selfcheck.py
   ```

2. **禁止事项**：
   - 虚拟机内运行（检测 CPUID/DMA/进程）
   - 修改 `--fdm` 参数（ufo/magic/null/external）
   - 使用 `--native-fdm` 外部数据源
   - 通过 telnet/httpd 修改状态属性
   - 修改预装数据文件的哈希值

3. **心跳机制**：
   - anticheatd 每秒签发一次 HMAC 票据
   - 心跳中断 ≥5 次 → 会话作废

## 题目说明

参见 `doc/飞行模拟CTF-题面.md`

## 技术细节

- **判决服务器**: `python -m server.poller --db ctf.db`
- **谜题生成**: `python -m tools.ctf2gen --uid TEAM01`
- **环境验证**: `python -m tools.verify_env --lock env.lock`
- **哈希清单**: `env.lock` 记录所有关键文件 SHA256

## 争议处理

如遇到误判，请提供：
1. `env.lock` 文件
2. 判决服务器日志（`build/ctf.db`）
3. 反作弊输出（`build/anticheat.log`）
'''
    (output / "README.md").write_text(content, encoding='utf-8')


def main():
    from tools.fg_detect import detect
    fg = detect()

    parser = argparse.ArgumentParser(description="打包 CTF 比赛环境")
    parser.add_argument("--output", default="build/package", help="输出目录")
    parser.add_argument("--fg-root", default=fg.data_root,
                        help="FGData 根目录（默认自动检测）")
    parser.add_argument("--fg-bin", default=fg.bin_dir,
                        help="FG 二进制目录（默认自动检测）")
    parser.add_argument("--scenery", default=fg.scenery_dir,
                        help="Terrasync 地景目录（默认自动检测）")
    parser.add_argument("--server", default="127.0.0.1", help="判决服务器地址")
    parser.add_argument("--mode", default="competitive", choices=["competitive", "training"])
    parser.add_argument("--callsign", default="PLAYER", help="默认 callsign")
    args = parser.parse_args()

    if not args.fg_root:
        print("ERROR: Cannot find FGData directory. Set FG_ROOT or use --fg-root.", file=sys.stderr)
        sys.exit(1)
    if not args.fg_bin:
        print("ERROR: Cannot find FG binary directory. Set FG_BIN or use --fg-bin.", file=sys.stderr)
        sys.exit(1)
    if not args.scenery:
        print("ERROR: Cannot find scenery directory. Set FG_SCENERY or use --scenery.", file=sys.stderr)
        sys.exit(1)
    
    output = Path(args.output)
    fg_root = Path(args.fg_root)
    scenery = Path(args.scenery)
    
    print(f"打包比赛环境...")
    print(f"  FG_ROOT : {fg_root}")
    print(f"  SCENERY : {scenery}")
    print(f"  OUTPUT  : {output}")
    
    # 创建目录结构
    output.mkdir(parents=True, exist_ok=True)
    
    # 复制必要文件
    project_root = Path(__file__).parent.parent
    copy_dir(project_root / "client" / "ctf-addon", output / "ctf-addon")
    copy_dir(project_root / "tools", output / "tools", exclude=["__pycache__", ".venv"])
    copy_dir(project_root / "server" / "anticheat", output / "server" / "anticheat", 
             exclude=["__pycache__"])
    
    # 复制判决服务器
    copy_dir(project_root / "server", output / "server", 
             exclude=["__pycache__", "checkers", "mp.py", "localfdm.py", "geodesy.py", 
                      "trackdb.py", "verdict.py", "challenge.py", "poller.py", "rules.yaml",
                      "rules_loader.py", "scores.py", "trackrow.py", "__init__.py"])
    
    # 复制规则文件
    shutil.copy2(project_root / "server" / "rules.yaml", output / "server" / "rules.yaml")
    
    # 复制 env.lock（如果存在）
    envlock = project_root / "build" / "env.lock"
    if envlock.exists():
        shutil.copy2(envlock, output / "env.lock")
        print(f"  已复制 env.lock")
    
    # 创建配置文件
    config = {
        "fg_bin": args.fg_bin,
        "fg_root": str(fg_root),
        "scenery_root": str(scenery),
        "server": args.server,
        "mode": args.mode,
        "callsign": args.callsign,
    }
    
    # 创建启动器
    create_launcher_win(output, config)
    create_launcher_linux(output, config)
    
    # 创建选手指南
    create_readme(output, config)
    
    # 复制 README
    readme_src = project_root / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, output / "README-CTF.md")
    
    print(f"\n✓ 打包完成: {output}")
    print(f"  - launcher.bat / launcher.sh")
    print(f"  - ctf-addon/ （客户端插件）")
    print(f"  - server/ （判决服务器代码）")
    print(f"  - tools/ （工具脚本）")
    print(f"  - env.lock （哈希清单）")
    print(f"  - README.md （选手指南）")
    
    # 显示打包统计
    total_size = sum(f.stat().st_size for f in output.rglob("*") if f.is_file())
    print(f"\n  总大小: {total_size / (1024*1024):.1f} MB")


if __name__ == "__main__":
    main()
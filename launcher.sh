#!/usr/bin/env bash
# MAYDAY CTF 启动器（参考实现，对应 doc2 §6.2 启动流程）
#
# 用法：
#   ./launcher.sh --callsign=TEAM01              # 正式模式（遥测+连飞全开）
#   ./launcher.sh --training                      # 训练模式（不产出证据）
#
# 环境变量：
#   FG_BIN      fgfs 可执行文件路径（默认在 PATH 里找）
#   FG_ROOT     FG 数据目录（Protocol XML 会被拷贝到 $FG_ROOT/Protocol/）
#   CTF_SERVER  判决服务器地址（默认 127.0.0.1）
#   CTF_MODE    比赛模式（competitive/training）
#
# 前置检查：
#   1) 运行 ./server/anticheat/selfcheck.py 验证环境
#   2) L0 启动参数白名单校验（通过 Python 脚本）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FG_BIN=${FG_BIN:-fgfs}
FG_ROOT=${FG_ROOT:-/usr/share/games/flightgear}
CTF_SERVER=${CTF_SERVER:-127.0.0.1}
MODE="competitive"
CALLSIGN="PLAYER"

for arg in "$@"; do
  case "$arg" in
    --training) MODE="training" ;;
    --callsign=*) CALLSIGN="${arg#--callsign=}" ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

# ===== L0 启动参数白名单校验 =====
echo "[launcher] 正在执行 L0 启动参数校验..."
python3 -c "
import sys
sys.path.insert(0, '$HERE')
from server.anticheat.l0_args import validate_args
valid, issues = validate_args(sys.argv[1:])
if not valid:
    print('[L0] 启动参数校验失败:', file=sys.stderr)
    for issue in issues:
        print(f'  - {issue}', file=sys.stderr)
    sys.exit(1)
print('[L0] 启动参数校验通过')
" "$@"

# ===== L5 心跳会话启动（模拟 anticheatd）=====
echo "[launcher] 正在启动反作弊心跳会话..."
SESSION_ID=$(python3 -c "
import sys
sys.path.insert(0, '$HERE')
from server.anticheat.l5_heartbeat import SessionManager
sm = SessionManager()
sid = sm.open_session('$CALLSIGN', b'test_anticheat', b'test_fgfs', b'test_aircraft')
print(sid)
" 2>/dev/null || echo "placeholder-session-id")
echo "[launcher] 会话 ID: $SESSION_ID"

# 部署遥测协议 XML（generic 输出只在 $FG_ROOT/Protocol 下查找）
if [ -w "$FG_ROOT/Protocol" ] || [ -w "$FG_ROOT" ]; then
  cp -f "$HERE/client/Protocol/ctf-telemetry.xml" "$FG_ROOT/Protocol/"
else
  echo "⚠ 无法写入 $FG_ROOT/Protocol，请手动拷贝 client/Protocol/ctf-telemetry.xml" >&2
  exit 1
fi

ARGS=(
  --aircraft=c172p
  --airport=KSFO            # ← 部署时替换为真实出发机场
  --callsign="$CALLSIGN"
  --addon="$HERE/client/ctf-addon"
  --telnet=5401
  --httpd=5400
  --prop:/ctf/mode=$MODE
  --prop:/ctf/session-id=$SESSION_ID
  # 环境锁定（doc1 P0：所有可变项写死在 launcher）
  --prop:/sim/time/speed-up=1
  --start-date-lat=2026-05-01T10:00:00
  --visibility=20000
)

if [ "$MODE" = "competitive" ]; then
  ARGS+=(
    # 遥测 30Hz → 判决服务器
    --generic=socket,out,30,127.0.0.1,5510,udp,ctf-telemetry
    # 连飞 10Hz → 判决服务器（所有流量强制经过我方，doc2 §5.1）
    --multiplay=out,10,"$CTF_SERVER",5000
    --multiplay=in,10,127.0.0.1,5001
  )
else
  ARGS+=( --prop:/ctf/training=1 )   # 训练模式：无 generic / 无 multiplay
fi

echo "[launcher] mode=$MODE callsign=$CALLSIGN server=$CTF_SERVER session=$SESSION_ID"
exec "$FG_BIN" "${ARGS[@]}"

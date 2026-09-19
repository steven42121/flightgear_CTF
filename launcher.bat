"""集成 env.lock 校验到 launcher.sh。

在启动 FG 前验证环境完整性，防止 terrasync 更新导致数据不一致。
"""
#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FG_BIN=${FG_BIN:-"C:/Program Files/FlightGear 2024.1/bin/fgfs.exe"}
FG_ROOT=${FG_ROOT:-"C:/Users/steven/FlightGear/Downloads/fgdata_2024_1"}
SCENERY_ROOT=${SCENERY_ROOT:-"C:/Users/steven/FlightGear/Downloads/TerraSync"}
LOCK_FILE=${LOCK_FILE:-"$HERE/build/env.lock"}
CTF_SERVER=${CTF_SERVER:-127.0.0.1}
MODE="competitive"
CALLSIGN="PLAYER"

# 解析参数
for arg in "$@"; do
  case "$arg" in
    --training) MODE="training" ;;
    --callsign=*) CALLSIGN="${arg#--callsign=}" ;;
    --fg-root=*) FG_ROOT="${arg#--fg-root=}" ;;
    --scenery=*) SCENERY_ROOT="${arg#--scenery=}" ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

# ===== L1 哈希校验 =====
echo "[launcher] 正在验证 env.lock 哈希..."
if [ -f "$LOCK_FILE" ]; then
    python3 -c "
import sys, json
sys.path.insert(0, '$HERE')
from server.anticheat.l1_envlock import EnvLockVerifier
from pathlib import Path

verifier = EnvLockVerifier('$LOCK_FILE')
report = verifier.verify_all(
    Path('$FG_ROOT'),
    Path('$FG_BIN').parent,
    Path('$SCENERY_ROOT')
)
if report['overall'] != 'PASS':
    print('L1 校验失败:', file=sys.stderr)
    for issue in report.get('issues', []):
        print(f'  - {issue}', file=sys.stderr)
    sys.exit(1)
print('[L1] 哈希校验通过')
" 2>&1 || {
        echo "✗ 环境校验失败，请重新运行 ./tools/gen_envlock.py 更新 env.lock" >&2
        exit 1
    }
else
    echo "⚠ 未找到 env.lock，跳过哈希校验（开发模式）" >&2
fi

# ===== L0 启动参数校验 =====
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

# ===== L5 会话启动 =====
echo "[launcher] 正在启动反作弊心跳会话..."
SESSION_ID=$(python3 -c "
import sys
sys.path.insert(0, '$HERE')
from server.anticheat.l5_heartbeat import SessionManager
sm = SessionManager()
sid = sm.open_session('$CALLSIGN', b'test_anticheat', b'test_fgfs', b'test_aircraft')
print(sid)
" 2>/dev/null || echo "placeholder-session-id")
echo "[launcher] 会话 ID: ${SESSION_ID:0:8}..."

# ===== 部署遥测协议 =====
echo "[launcher] 正在部署遥测协议..."
if [ -w "$FG_ROOT/Protocol" ] || [ -w "$FG_ROOT" ]; then
  cp -f "$HERE/client/Protocol/ctf-telemetry.xml" "$FG_ROOT/Protocol/"
  echo "[launcher] Protocol/ctf-telemetry.xml 已部署"
else
  echo "⚠ 无法写入 $FG_ROOT/Protocol，请手动拷贝" >&2
fi

# ===== 构建 FG 启动参数 =====
ARGS=(
  --fg-root="$FG_ROOT"
  --fg-scenery="$SCENERY_ROOT;$FG_ROOT/Scenery"
  --disable-terrasync
  --aircraft=c172p
  --airport=KSFO
  --callsign="$CALLSIGN"
  --telnet=5401
  --httpd=5400
  --prop:/ctf/mode=$MODE
  --prop:/ctf/session-id=$SESSION_ID
  --prop:/sim/time/speed-up=1
  --start-date-lat=2026-05-01T10:00:00
  --visibility=20000
)

if [ "$MODE" = "competitive" ]; then
  ARGS+=(
    --generic=socket,out,30,127.0.0.1,5510,udp,ctf-telemetry
    --multiplay=out,10,"$CTF_SERVER",5000
    --multiplay=in,10,127.0.0.1,5001
  )
else
  ARGS+=( --prop:/ctf/training=1 )
fi

echo "[launcher] mode=$MODE callsign=$CALLSIGN fg_root=$FG_ROOT"
exec "$FG_BIN" "${ARGS[@]}"

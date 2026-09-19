# 飞行模拟 CTF「MAYDAY」· 代码实现包

按《飞行模拟CTF-系统设计.md》《开发计划.md》《题解与裁判手册.md》实现的
可运行骨架。**两道 flag 的服务端判决链路已完整实现并通过自验**；
FlightGear 侧（addon / generic 遥测 / launcher）为参考实现，需在
真实 FG 2024.1 + 真实机场数据上完成 P0 校准。

**当前状态（2026-09-20）**：
- ✅ C++ native anticheatd 已编译成功（`anticheatd.exe`）
- ✅ ATC 语音已集成（`server/atc_full.wav`，Base32编码flag key）
- ✅ 所有22项测试通过
- ⏳ P0基线采集待完成（阈值目前为占位值）
- ⏳ fgms私有化部署待完成

## 项目结构

```
flightgear-ctf/
├── README.md
├── launcher.sh                  # FG 启动器（含 L0 启动校验 + L5 会话）
├── anticheatd/                  # C++ 反作弊（生产环境）
│   ├── CMakeLists.txt
│   └── src/                     # L0-L5 + Anti-VM 实现
│       └── build/bin/Release/
│           └── anticheatd.exe   # 已编译
├── server/                      # 判决服务器（Python）
│   ├── poller.py                #   入口：MP-UDP:5000 / FDM-UDP:3001
│   ├── mp.py                    #   MP 协议（36B 头 + MsgId=7）
│   ├── localfdm.py              #   FGNetFDM v24 编解码
│   ├── geodesy.py               #   WGS84 / haversine / ECEF
│   ├── trackdb.py               #   轨迹/会话 SQLite 存储
│   ├── verdict.py               #   会话收口 → 判决 → flag 下发
│   ├── challenge.py             #   challenge 注入与响应校验
│   ├── scores.py                #   flag = HMAC(K_server, uid‖checkpoint)
│   ├── checkers/
│   │   ├── flag1.py             #   到达上海张江判定 + ATC 语音下发
│   │   ├── flag2.py             #   物理不可能状态判定（飞天/遁地/超速）
│   │   └── flag3.py             #   兼容重定向到 flag2
│   └── atc_full.wav             #   ATC 语音文件（Base32 编码 flag key）
├── tools/
│   ├── gen_testdata.py          #   测试轨迹生成
│   ├── demo_bot.py              #   回放器
│   ├── ctf2gen.py               #   flag2 谜题生成
│   └── verify_all.py            #   一键自验
├── client/
│   └── ctf-addon/               #   FG addon（参考实现）
├── doc/
│   ├── 飞行模拟CTF-系统设计.md
│   ├── 飞行模拟CTF-题面.md
│   ├── 飞行模拟CTF-题解与裁判手册.md
│   └── 飞行模拟CTF-开发计划.md
└── build/
    └── env.lock                 #   环境锁定文件（FG版本+主要文件哈希）
```

## 快速开始（判决服务器全链路自验）

```bash
cd flightgear-ctf

# 1. 激活虚拟环境
.\.venv\Scripts\activate

# 2. 生成测试轨迹
python -m tools.gen_testdata --out build/track.csv --segments walk,arc,ceil,taxi,speed

# 3. 一键自验
python -m tools.verify_all

# 4. 启动判决服务器（两个终端）
python -m server.poller --db build/ctf.db          # 终端 1
python -m tools.demo_bot --csv build/track.csv --mode mp --callsign TEST01  # 终端 2
```

## 反作弊系统

### C++ Native 版（生产环境）

```powershell
# 编译
cd anticheatd\build
cmake .. -G "Visual Studio 18 2026" -A x64
cmake --build . --config Release

# 运行自检
.\Release\anticheatd.exe --mode selfcheck
```

### Python 版（参考实现）

| 层级 | 模块 | 功能 |
|------|------|------|
| L0 | `l0_args.py` | 启动参数白名单（禁止 `--fdm=external` 等） |
| L1 | `l1_integrity.py` | **主要游戏文件哈希校验**（fgfs.exe、核心DLL；不包含 aircraft/set.xml 和 scenery 地景） |
| L2 | `l2_property_audit.py` | 属性树写入审计 |
| L3 | `l3_fdm_tracker.py` | FDM 源可信度追踪 |
| L4 | `l4_integrity.py` | 进程完整性检查（CRC、注入扫描） |
| L5 | `l5_heartbeat.py` | 心跳票据系统（HMAC 链，中断即作废） |
| Anti-VM | `selfcheck.py` | **虚拟化检测（要求关闭 VBS/Hyper-V）** |

**Anti-VM 检测项**：
- Windows: VBS（虚拟机分支）、Hyper-V、核心隔离/内存完整性
- CPUID hypervisor bit、DMI/SMBIOS、MAC OUI、进程检测

## Flag Key

Flag1 的 flag key 通过 ATC 语音的摩斯密码部分编码：
- Base32: `JRCVIU27IZGFSX2UJ5PVISCFL5JUWWK7KREECTSLL5MU6VK7IZHVEX2GJRMUSTSH`
- 解码后: `LETS_FLY_TO_THE_SKY_THANK_YOU_FOR_FLYING`

## 心跳机制说明

**两道 flag 都需要心跳验证**：

| Flag | 心跳要求 | 说明 |
|------|----------|------|
| flag1 | ✅ 必须有心跳 | 无心跳 → 判决返回 reached=false |
| flag2 | ✅ 必须有心跳 | 无心跳 → hb_ok=false → 直接判定 FAIL |

**心跳断连处理**：
- 会话层：超过 `grace_missed`（默认5次）未收到心跳 → **session 关闭，选手被踢出连飞平台**
- 判决层：flag1/flag2 判决时检查 `hb_ok`，无心跳则无法得分

**如果选手不运行 anticheatd**：
- FG 遥测仍会被 poller 接收，但心跳端口无数据
- 30s 无心跳 → session 关闭 → 被踢出
- flag1/flag2 均无法获得

## 已知待完成项

1. **P0 基线采集** — 用 stock AP 在真实 ZSPD 跑 20 次重校阈值
2. **fgms 私有化部署** — docker 镜像 `flightgear/fgms:0.13.4`
3. **Web 提交界面** — flag1 key 验证 + flag2 状态提交
4. **真实机场数据** — 当前用虚构坐标占位，需替换为真实上海区域数据

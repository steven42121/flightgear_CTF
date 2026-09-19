# 飞行模拟 CTF「MAYDAY」· 代码实现包

按《飞行模拟CTF-系统设计.md》《开发计划.md》《题解与裁判手册.md》实现的
可运行骨架。三道 flag 的**服务端判决链路已完整实现并通过自验**；
FlightGear 侧（addon / generic 遥测 / launcher）为参考实现，需在
真实 FG 2024.1 + 真实机场数据上完成 P0 校准。

```
flightgear-ctf/
├── README.md
├── launcher.sh                  # FG 启动器（含 L0 启动校验 + L5 会话）
├── server/                      # 判决服务器（Python，依赖 pyyaml）
│   ├── poller.py                #   入口：MP-UDP:5000 / FDM-UDP:3001 / TEXT-TCP:3002
│   ├── mp.py                    #   MP 协议（36B 头 + MsgId=7）编码/解码
│   ├── localfdm.py              #   FGNetFDM v24 (408B) 编码/解码
│   ├── geodesy.py               #   WGS84 / haversine / ECEF↔大地坐标
│   ├── trackdb.py               #   轨迹/会话 SQLite 存储
│   ├── verdict.py               #   会话收口 → 三题判决 → flag 下发
│   ├── challenge.py             #   challenge 注入与响应校验
│   ├── rules.yaml / rules_loader.py
│   ├── scores.py                #   flag = HMAC(K_server, uid‖checkpoint)
│   ├── anticheat/               #   反作弊模块（基于 VMAware + UltimateAntiCheat 设计）
│   │   ├── __init__.py          #     模块导出
│   │   ├── l0_args.py           #     L0: 启动参数白名单校验
│   │   ├── l1_integrity.py      #     L1: 文件哈希校验
│   │   ├── l2_property_audit.py #     L2: 属性树写入审计
│   │   ├── l3_fdm_tracker.py    #     L3: FDM 源可信度追踪
│   │   ├── l4_integrity.py      #     L4: 进程完整性检查（CRC/注入扫描）
│   │   ├── l5_heartbeat.py      #     L5: 心跳票据系统（HMAC 链）
│   │   ├── anticheatd.py        #     反作弊守护进程入口
│   │   └── selfcheck.py         #     自检工具（anti-VM + 环境检查）
│   └── checkers/flag{1,2,3}.py  #   三题判决器（阈值全部集中在 rules.yaml）
├── tools/
│   ├── gen_testdata.py          #   测试轨迹生成（walk/arc/ils/ceil/taxi/speed）
│   ├── demo_bot.py              #   回放器：mp / fdm / text 三种出流
│   ├── ctf2gen.py               #   flag2 谜题生成 + 参数自检
│   ├── search_repos.py          #   GitHub 开源反作弊项目搜索
│   └── verify_all.py            #   一键自验（协议 roundtrip + 三题判决）
├── client/
│   ├── ctf-addon/               #   FG addon（metadata + Nasal 入口）
│   └── Protocol/ctf-telemetry.xml  # generic 30Hz 遥测定义
└── doc/
    ├── 飞行模拟CTF-开发计划.md
    ├── 飞行模拟CTF-系统设计.md
    ├── 飞行模拟CTF-题解与裁判手册.md
    └── 飞行模拟CTF-题面.md
```

## 快速开始（判决服务器全链路自验）

```bash
cd flightgear-ctf

# 1. 生成测试轨迹（平飞 + 绕圈 + ILS 落地 + 三个物理不可能段）
python -m tools.gen_testdata --out build/track.csv --segments walk,arc,ils,ceil,taxi,speed

# 2. 一键自验：MP/FDM 协议 roundtrip + 三题判决
python -m tools.verify_all --csv build/track.csv

# 3. 反作弊自检
python -m server.anticheat.selfcheck

# 3. 反作弊自检
python -m server.anticheat.selfcheck

# 4. 启动判决服务器（两个终端）
python -m server.poller --db build/ctf.db          # 终端 1
python -m tools.demo_bot --csv build/track.csv --mode mp --callsign TEST01  # 终端 2
# 静默 30s 后 poller 打印 VERDICT 并发放 flag
```

## flag2 谜题下发（示例）

```bash
python -m tools.ctf2gen --uid TEAM01 --station-a 36.05,-115.20 --station-b 36.30,-115.10 --station-c 36.10,-115.00
```

## 反作弊模块（基于 VMAware + UltimateAntiCheat 设计）

| 层级 | 模块 | 功能 |
|------|------|------|
| L0 | `l0_args.py` | 启动参数白名单校验（禁止 `--fdm=external` 等） |
| L1 | `l1_integrity.py` | 文件哈希校验（fgfs/机型/addon SHA256） |
| L2 | `l2_property_audit.py` | 属性树写入审计（监控 `/position/*` 等关键路径） |
| L3 | `l3_fdm_tracker.py` | FDM 源可信度追踪（区分合法 FDM 与外部注入） |
| L4 | `l4_integrity.py` | 进程完整性检查（CRC、注入扫描） |
| L5 | `l5_heartbeat.py` | 心跳票据系统（HMAC 链，中断即作废） |
| — | `selfcheck.py` | 启动前自检（anti-VM + 环境检查） |
| — | `anticheatd.py` | 守护进程入口 |

```bash
# 运行自检
python -m server.anticheat.selfcheck

# 测试启动参数校验
python -m server.anticheat.anticheatd.py --mode check -- --aircraft=c172p --addon=./ctf-addon

# 创建会话并获取 ticket
python -m server.anticheat.anticheatd.py --mode session --userid TEAM01
```

## 已实现 ↔ 文档映射

| 文档条目 | 代码 |
|---|---|
| doc2 §5.1 MP 头 / 位置消息 | server/mp.py（36B 头，MsgId=7，pad=0x1face002） |
| doc2 §5.2 权威时间戳/差分地速 | server/poller.py（recv_time）+ mp.parse_position（ECEF 速度） |
| doc2 §5.2 challenge 注入 | server/challenge.py |
| doc3 §1.3 flag1 判据 | server/checkers/flag1.py（含 3 处勘误，见 docs/1） |
| doc3 §2.2/§2.3 flag2 解算/自检 | tools/ctf2gen.py（双圆交点 + C 台方位消歧） |
| doc3 §2.4 flag2 触发判定 | server/checkers/flag2.py（含"擦边悬停"修正） |
| doc3 §3.4 flag3 判定 | server/checkers/flag3.py |
| doc3 §4 flag 下发 | server/scores.py（K_server 独立，满足 R7） |
| doc2 §8.4 addon 最小结构 | client/ctf-addon/ |
| doc2 §8.2 generic 30Hz 遥测 | client/Protocol/ctf-telemetry.xml |
| doc3 §4.1-L5 反作弊架构 | server/anticheat/（L0-L5 全层实现） |
| doc3 §4.5 anti-VM | server/anticheat/selfcheck.py（跨平台检测） |

## 明确未实现（需要独立排期）

1. **native 版 anticheatd（C/C++ 二进制）**——当前 Python 实现仅作参考，
   正式比赛需用 native 进程（反调试、内存保护、密钥擦除）。
   设计参考 UltimateAntiCheat 架构，VMAware 提供 VM 检测算法。
2. **fgms 私有化部署**——docker 镜像 `flightgear/fgms:0.13.4`，
   关 relay/tracked/is_hub；MP 流量当前由本仓库 `server/poller.py` 直接接收，
   fgms 是正式部署的可选前置。
3. **P0 基线采集**——阈值是占位值，必须用 stock AP 在锁定环境跑 20 次重校。
4. **真实机场/导航台数据**——当前用虚构坐标（36.15,-115.15）占位。

## 环境要求

- 服务端：Python ≥ 3.8，无第三方依赖
- 客户端：FlightGear 2024.1（锁定版本，见 doc1 P0）
- 判决服务器开放端口：UDP 5000 (MP) / UDP 3001 (FDM) / TCP 3002 (debug)

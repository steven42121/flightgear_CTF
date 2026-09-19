# 飞行模拟 CTF「MAYDAY」· 代码实现包

按《飞行模拟CTF-系统设计.md》《开发计划.md》《题解与裁判手册.md》实现的
可运行骨架。三道 flag 的**服务端判决链路已完整实现并通过自验**；
FlightGear 侧（addon / generic 遥测 / launcher）为参考实现，需在
真实 FG 2024.1 + 真实机场数据上完成 P0 校准。

```
flightgear-ctf/
├── README.md
├── launcher.sh                  # FG 启动器（参考实现）
├── server/                      # 判决服务器（Python，零第三方依赖）
│   ├── poller.py                #   入口：MP-UDP:5000 / FDM-UDP:3001 / TEXT-TCP:3002
│   ├── mp.py                    #   MP 协议（36B 头 + MsgId=7）编码/解码
│   ├── localfdm.py              #   FGNetFDM v24 (408B) 编码/解码
│   ├── geodesy.py               #   WGS84 / haversine / ECEF↔大地坐标
│   ├── trackdb.py               #   轨迹/会话 SQLite 存储
│   ├── verdict.py               #   会话收口 → 三题判决 → flag 下发
│   ├── challenge.py             #   challenge 注入与响应校验
│   ├── rules.yaml / rules_loader.py
│   ├── scores.py                #   flag = HMAC(K_server, uid‖checkpoint)
│   └── checkers/flag{1,2,3}.py  #   三题判决器（阈值全部集中在 rules.yaml）
├── tools/
│   ├── gen_testdata.py          #   测试轨迹生成（walk/arc/ils/ceil/taxi/speed）
│   ├── demo_bot.py              #   回放器：mp / fdm / text 三种出流
│   ├── ctf2gen.py               #   flag2 谜题生成 + 参数自检
│   └── verify_all.py            #   一键自验（协议 roundtrip + 三题判决）
├── client/
│   ├── ctf-addon/               #   FG addon（metadata + Nasal 入口）
│   └── Protocol/ctf-telemetry.xml  # generic 30Hz 遥测定义
└── docs/
    ├── 1-勘误与修正.md           #   文档勘误（头长/psi/FGFS 大端/文档笔误）
    ├── 2-平台侧.md              #   fgms 部署 + MP 解析 + 判决
    ├── 3-反作弊设计.md          #   L0–L5 + KDF/心跳/蜜罐（不含源码）
    └── 4-客户端侧.md            #   addon / 遥测 / launcher / P0 清单
```

## 快速开始（判决服务器全链路自验）

```bash
cd flightgear-ctf

# 1. 生成测试轨迹（平飞 + 绕圈 + ILS 落地 + 三个物理不可能段）
python -m tools.gen_testdata --out build/track.csv --segments walk,arc,ils,ceil,taxi,speed

# 2. 一键自验：MP/FDM 协议 roundtrip + 三题判决
python -m tools.verify_all --csv build/track.csv

# 3. 端到端联调（两个终端）
python -m server.poller --db build/ctf.db          # 终端 1
python -m tools.demo_bot --csv build/track.csv --mode mp --callsign TEST01  # 终端 2
# 静默 30s 后 poller 打印 VERDICT 并发放 flag
```

## flag2 谜题下发（示例）

```bash
python -m tools.ctf2gen --uid TEAM01 --station-a 36.05,-115.20 --station-b 36.30,-115.10 --station-c 36.10,-115.00
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
| doc2 §4.5 anti-VM | 未实现（属反作弊 native 进程，见 docs/3） |

## 明确未实现（需要独立排期）

1. **反作弊 native 进程（doc2 §4 / doc1 P3，关键路径 7 人日）**——C/C++ 项目，
   含 anti-VM、CRC、心跳 HMAC 链与蜜罐分支。设计要点已写入 docs/3，
   包括"必须用 `K_server` 发 flag、不能用 K"这条连带崩塌红线。
2. **fgms 私有化部署**——docker 镜像 `flightgear/fgms:0.13.4`，
   关 relay/tracked/is_hub；MP 流量当前由本仓库 `server/poller.py` 直接接收，
   fgms 是正式部署的可选前置。
3. **P0 基线采集**——阈值是占位值，必须用 stock AP 在锁定环境跑 20 次重校。
4. **真实机场/导航台数据**——当前用虚构坐标（36.15,-115.15）占位。

## 环境要求

- 服务端：Python ≥ 3.8，无第三方依赖
- 客户端：FlightGear 2024.1（锁定版本，见 doc1 P0）
- 判决服务器开放端口：UDP 5000 (MP) / UDP 3001 (FDM) / TCP 3002 (debug)

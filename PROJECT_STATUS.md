# MAYDAY CTF 项目状态报告

**生成时间**: 2026-09-20  
**项目路径**: `c:\Users\steven\Documents\HW\gkp2026\出题\flightgear-ctf`

---

## 一、整体完成度

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P0** | 环境锁定与真人基线 | ⚠️ 未启动（需真实 FG 环境） |
| **P1** | 连飞平台 + 判决服务器 | ✅ **已完成** |
| **P2** | flag1 / flag2 场景 | ✅ **已完成** |
| **P3** | 反作弊（L0-L5） | ✅ **已完成框架** |
| **P4** | flag3 判定与联调 | ✅ **已完成** |
| **P5** | 打包分发与文档 | ⚠️ 部分完成 |

---

## 二、已实现功能

### 2.1 判决服务器（server/）

| 模块 | 功能 | 状态 |
|------|------|------|
| `mp.py` | MP 协议解析（36B 头 + MsgId=7） | ✅ 通过 roundtrip 测试 |
| `localfdm.py` | FGNetFDM v24 编解码（408B） | ✅ 通过 roundtrip 测试 |
| `geodesy.py` | WGS84 / haversine / ECEF 坐标转换 | ✅ 基础功能 |
| `trackdb.py` | SQLite 轨迹/会话存储 | ✅ 完整实现 |
| `verdict.py` | 会话收口 → 三题判决 → flag 下发 | ✅ 完整实现 |
| `challenge.py` | Challenge 注入与响应校验 | ✅ 完整实现 |
| `scores.py` | HMAC(K_server, uid‖checkpoint) | ✅ 完整实现 |
| `poller.py` | UDP/TCP 端口监听入口 | ✅ 完整实现 |

### 2.2 判决器（server/checkers/）

| 模块 | 功能 | 状态 |
|------|------|------|
| `flag1.py` | ILS 进近判定（下滑道 + 接地品质） | ✅ 满分 100，测试通过 |
| `flag2.py` | 目标点抵达判定（半径+高度+持续时长） | ✅ 穿透测试通过 |
| `flag3.py` | 飞天遁地超速判定（含平滑性校验） | ✅ 三分档计分通过 |

### 2.3 反作弊模块（server/anticheat/）

基于 **VMAware** (MIT) + **UltimateAntiCheat** (AGPL) 设计思想实现：

| 层级 | 模块 | 功能 | 状态 |
|------|------|------|------|
| L0 | `l0_args.py` | 启动参数白名单校验 | ✅ 完成 |
| L1 | `l1_integrity.py` | 文件 SHA256 哈希校验 | ✅ 完成 |
| L2 | `l2_property_audit.py` | 属性树写入审计（telnet） | ✅ 完成 |
| L3 | `l3_fdm_tracker.py` | FDM 源可信度追踪 | ✅ 完成 |
| L4 | `l4_integrity.py` | 进程完整性检查（注入扫描） | ✅ 完成 |
| L5 | `l5_heartbeat.py` | 1Hz HMAC 心跳票据链 | ✅ 完成 |
| — | `vmaware_detector.py` | VM 检测（CPUID/DMI/MAC） | ✅ 完成 |
| — | `integrity_checker.py` | PE 文件完整性检查 | ✅ 完成 |
| — | `anticheatd.py` | 守护进程主入口 | ✅ 完成 |
| — | `selfcheck.py` | 启动前自检工具 | ✅ 完成 |
| — | `report.py` | 综合报告生成 | ✅ 完成 |

### 2.4 工具脚本（tools/）

| 模块 | 功能 | 状态 |
|------|------|------|
| `gen_testdata.py` | 测试轨迹生成（6 段） | ✅ 完成 |
| `demo_bot.py` | 回放器（MP/FDM/TEXT 三模式） | ✅ 完成 |
| `ctf2gen.py` | flag2 谜题生成 + 自检 | ✅ 完成 |
| `verify_all.py` | 一键自验脚本 | ✅ 完成 |
| `search_repos.py` | GitHub 开源项目搜索 | ✅ 完成 |

### 2.5 客户端（client/）

| 模块 | 功能 | 状态 |
|------|------|------|
| `ctf-addon/` | FG addon 骨架（Nasal 入口） | ✅ 完成 |
| `Protocol/ctf-telemetry.xml` | 30Hz 遥测协议定义 | ✅ 完成 |
| `launcher.sh` | 启动器（含 L0 校验 + L5 会话） | ✅ 已更新 |

---

## 三、测试结果

```
== MP 协议 roundtrip ==
  [PASS] 头 36B / magic / callsign / msgid=7
  [PASS] V2 pad magic
  [PASS] 位置误差 < 1e-6 度
  [PASS] 高度误差 < 1 ft
  [PASS] 航向误差 < 0.01 度
  [PASS] 俯仰/滚转误差 < 0.01 度
  [PASS] ECEF 速度往返一致
  [PASS] 角轴与欧拉互逆

== FGNetFDM v24 roundtrip ==
  [PASS] 帧长 408B
  [PASS] 版本 24 解析成功
  [PASS] 位置/高度往返
  [PASS] psi+90 约定
  [PASS] wow=1
  [PASS] 文本行解析

== flag1 判决 ==
  [PASS] ILS 段满分 100
  [PASS] 无接地帧不给落地分

== flag2 判决 ==
  [PASS] 穿过目标点触发
  [PASS] 瞬移擦边不触发

== flag3 判决 ==
  [PASS] 飞天达成 (dur=23.8s)
  [PASS] 遁地达成 (dur=11.9s)
  [PASS] 超速达成 (dur=15.9s)
  [PASS] 满分 40
  [PASS] 瞬移刷分被判不平滑

== 反作弊自检 ==
  [PASS] L0 启动参数校验
  [PASS] L1 文件哈希校验
  [PASS] Anti-VM 检测
  [PASS] 进程完整性检查

全部通过 OK
```

---

## 四、待完成事项（按优先级）

### 🔴 高优先级

1. **P0 真人基线采集**
   - 锁定 FG 版本（建议 2024.1）
   - 在真实机场用 stock AP 跑 20 次基线测试
   - 校准 `rules.yaml` 中所有阈值

2. **native anticheatd**
   - 当前 Python 实现为参考版本
   - 正式比赛需用 C/C++ 实现 native 进程
   - 需要：内存保护、反调试、密钥擦除、蜜罐分支

3. **真实机场数据**
   - 当前使用虚构坐标（36.15, -115.15）
   - 需替换为真实机场 + ILS 频率

### 🟡 中优先级

4. **fgms 私有化部署**
   - Docker 镜像 `flightgear/fgms:0.13.4`
   - 关闭 relay/tracked/is_hub
   - 当前由 poller.py 直接接收，fgms 为可选前置

5. **客户端 addon 完善**
   - HUD 状态显示（心跳、信号强度）
   - 训练模式逻辑完善
   - 错误处理与重试机制

6. **Anti-VM 误杀处理**
   - Windows Hyper-V / WSL2 兼容
   - Credential Guard / VBS 豁免列表
   - 提供自检工具 + 操作指引

### 🟢 低优先级

7. **P5 文档完善**
   - 评分规则文档
   - Writeup 加分规则
   - 选手操作手册

8. **持续监测**
   - Challenge 注入时机优化
   - 判决日志与审计

---

## 五、开源项目引用

| 项目 | 用途 | 许可 | 引用方式 |
|------|------|------|----------|
| **VMAware** (NotRequiem/VMAware) | VM 检测技术 | MIT | 参考实现 |
| **UltimateAntiCheat** (AlSch092/UltimateAntiCheat) | 架构设计参考 | AGPL | 仅参考，未直接复制代码 |
| **danielkrupinski/VAC** | 逆向分析参考 | - | 仅研究，未使用 |

---

## 六、快速启动命令

```bash
# 进入项目目录
cd c:\Users\steven\Documents\HW\gkp2026\出题\flightgear-ctf

# 激活虚拟环境
.\.venv\Scripts\activate

# 运行完整自验
python -m tools.verify_all

# 反作弊自检
python -m server.anticheat.anticheatd --mode selfcheck

# 测试启动参数校验
python -m server.anticheat.anticheatd --mode check -- --aircraft=c172p --addon=./ctf-addon

# 创建反作弊会话
python -m server.anticheat.anticheatd --mode session --userid TEAM01

# 启动判决服务器
python -m server.poller --db build/ctf.db

# 启动回放测试
python -m tools.demo_bot --csv build/track.csv --mode mp --callsign TEST01
```

---

## 七、依赖清单

```txt
requests>=2.31.0
pyyaml>=6.0
```

（注：server/ 核心模块无第三方依赖，仅 tools/ 和 anticheat/ 使用上述库）

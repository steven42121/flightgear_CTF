# 项目状态总览

> 更新时间：2026-09-20

## 已完成模块

### ✅ 核心判决系统
| 模块 | 状态 | 说明 |
|------|------|------|
| MP协议解析 | ✅ 完成 | 36B头 + MsgId=7，XDR编解码，角轴↔欧拉互逆验证通过 |
| FGNetFDM v24 | ✅ 完成 | 408B帧编码/解码，roundtrip测试通过 |
| flag1判决器 | ✅ 完成 | ILS进近判定，滑动道稳定度+决断高度+接地品质，满分100 |
| flag2判决器 | ✅ 完成 | 目标点抵达判定，半径+高度+持续时长，防瞬移擦边 |
| flag3判决器 | ✅ 完成 | 飞天遁地超速三检查点，含平滑性校验 |
| Challenge注入 | ✅ 完成 | 能见度/风向突变，响应时延校验 |
| Session管理 | ✅ 完成 | SQLite存储，空闲超时收口 |
| Flag下发 | ✅ 完成 | HMAC(K_server, uid‖checkpoint) |

### ✅ 反作弊系统（L0-L5）
| 层级 | 模块 | 状态 | 说明 |
|------|------|------|------|
| L0 | l0_args.py | ✅ 完成 | 启动参数白名单，拦截`--fdm=external`等危险参数 |
| L1 | l1_integrity.py | ✅ 完成 | 文件SHA256哈希校验 |
| L1扩展 | l1_envlock.py | ✅ 完成 | env.lock环境锁定，防止terrasync覆盖 |
| L2 | l2_property_audit.py | ✅ 完成 | 属性树写入审计（/position/* /velocities/* 等） |
| L3 | l3_fdm_tracker.py | ✅ 完成 | FDM源可信度追踪 |
| L4 | l4_integrity.py | ✅ 完成 | 进程完整性检查（/proc/self/maps扫描） |
| L5 | l5_heartbeat.py | ✅ 完成 | 1Hz HMAC心跳票据链，中断即作废 |
| — | vmaware_detector.py | ✅ 完成 | 参考VMAware的VM检测（CPUID/DMI/MAC OUI） |
| — | anticheatd.py | ✅ 完成 | 守护进程入口，整合L0-L5 |
| — | selfcheck.py | ✅ 完成 | 自检工具，赛前使用 |
| — | report.py | ✅ 完成 | 综合报告生成 |

### ✅ 工具链
| 工具 | 状态 | 说明 |
|------|------|------|
| gen_testdata.py | ✅ 完成 | 生成测试轨迹（walk/arc/ils/ceil/taxi/speed） |
| demo_bot.py | ✅ 完成 | 回放器，支持mp/fdm/text三种出流 |
| ctf2gen.py | ✅ 完成 | flag2谜题生成+参数自检 |
| verify_all.py | ✅ 完成 | 一键自验（协议+判决） |
| package_env.py | ✅ 完成 | 打包比赛环境 |
| verify_env.py | ✅ 完成 | env.lock哈希校验 |

### ✅ 客户端
| 组件 | 状态 | 说明 |
|------|------|------|
| ctf-addon/ | ✅ 完成 | Nasal入口，属性桥接 |
| Protocol/ctf-telemetry.xml | ✅ 完成 | 30Hz遥测定义 |
| launcher.sh | ✅ 已更新 | 集成L0校验和L5会话 |

### ✅ 配置与文档
| 文件 | 状态 | 说明 |
|------|------|------|
| rules.yaml | ✅ 完成 | 判决规则配置 |
| env.lock | ✅ 已生成 | FG 2024.1.7哈希清单（1260文件） |

---

## 待完成事项

### 🔴 P0 高优先级（影响判决准确性）
1. **真人基线采集**：用 stock AP 在锁定环境跑 20 次，校准 `rules.yaml` 阈值
2. **真实机场数据**：替换虚构坐标 (36.15, -115.15) 为实际比赛机场
3. **flag2 谜题设计**：实现"三地标交会"形态，生成 per-user 线索

### 🟡 P1 中优先级（影响稳定性）
4. **native anticheatd**：Python 版本为参考实现，正式比赛需 C/C++ 重写
   - 内存保护（`.text` 段 CRC）
   - 反调试（`PTRACE_TRACEME`、`TracerPid`、RDTSC）
   - 蜜罐分支（检测调试器时签出诱饵票据）
5. **FG 数据补全**：当前 Terrasync 只有 `w030n60` 一个瓦片，需按需预装目标区域

### 🟢 P2 低优先级（锦上添花）
6. **HUD 增强**：在 addon 中增加心跳状态、信号强度可视化
7. **多机型支持**：除 c172p 外支持其他飞机
8. **日志完善**：结构化日志，便于赛后复盘

---

## 快速命令速查

```bash
# 激活虚拟环境
source .venv/Scripts/activate  # Linux/Mac
.\.venv\Scripts\Activate.ps1   # Windows

# 运行全量自验
python -m tools.verify_all

# 生成测试数据
python -m tools.gen_testdata --out build/track.csv --segments walk,arc,ils,ceil,taxi,speed

# 反作弊自检
python -m server.anticheat.selfcheck

# 启动判决服务器
python -m server.poller --db build/ctf.db

# 回放测试
python -m tools.demo_bot --csv build/track.csv --mode mp --callsign TEST01

# 生成新环境的 env.lock
python -m tools.gen_envlock --fg-root "C:/Path/To/fgdata" --scenery "C:/Path/To/TerraSync"

# 验证环境完整性
python -m tools.verify_env --lock build/env.lock --fg-root "C:/Path/To/fgdata"
```

---

## 技术栈

- **后端**：Python 3.8+，零第三方依赖（仅 `pyyaml` 用于配置）
- **反作弊**：Python 实现（可移植至 C/C++）
- **客户端**：FlightGear 2024.1+，Nasal 脚本
- **数据存储**：SQLite
- **协议**：UDP (MP 10Hz + FDM 30Hz)，TCP (debug)

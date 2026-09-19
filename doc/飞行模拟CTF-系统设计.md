# 飞行模拟 CTF 附加题 · 系统设计文档

> 基于 FlightGear 的三段式附加题：连飞平台 + 本地反作弊 + 物理不可能状态判定
> 版本 v1.0 · 面向出题组内部

---

## 0. 一句话目标

出一道 **AI 无法独立完成** 的附加题：AI 可以做副驾（读代码、推公式、写脚本、解释协议），但**方向盘、调试器、以及本机那台 FlightGear 只能由人操作**。

难度定位：研究生课程级。不在乎劝退率，这是附加题。

---

## 1. 设计原理：为什么这套架构能反 AI

AI 的天花板只有四条够不着的：物理世界、实时私有信息、真人肉身、长时间注意力。本方案把题目压在第二条和第四条上：

| 反 AI 支点 | 本方案如何落地 |
|---|---|
| **实时私有信息** | 服务端在飞行中随机注入 challenge（风向突变等），AI 不在场上，无法预知 |
| **长时间注意力** | 一次进近 + 一次转场 + 一次逆向调试，全程数十分钟到数小时，AI 无法代跑 |
| **本地进程** | 反作弊是本机 native 进程，AI 够不着内存、够不着调试器会话 |
| **服务端旁观** | 判决依据来自连飞平台观测到的轨迹，不是客户端自证 |

关键认知：**不要追求"AI 完全做不了"，追求"AI 只能做到 70%"**。AI 帮选手读文档、写 UDP 客户端、推导风三角，这是应当被鼓励的正常工程行为。

---

## 2. 系统架构

```
┌───────────────────── 参赛者主机（物理机，禁用虚拟化）─────────────────────┐
│                                                                          │
│   launcher.sh  ──►  启动参数白名单校验  ──►  fgfs                          │
│                                              │                          │
│                        ┌─────────────────────┼──────────────────┐       │
│                        │                     │                  │       │
│                   --addon=./ctf-addon   --generic(遥测)   --multiplay      │
│                   (Nasal 场景/规则)      (30Hz UDP)       (out/in)        │
│                                                                          │
│   anticheatd  ──►  独立 native 进程                                      │
│      · 启动环境校验（FG版本/机型/scenery 哈希、fdm 类型、无 --load-tape）    │
│      · 运行时属性树审计（禁止写状态属性）                                   │
│      · 进程完整性（fgfs/自身 .text CRC、maps 注入扫描）                     │
│      · 反调试 / anti-VM                                                   │
│      · 1Hz 心跳票据 HMAC(K, 状态流摘要 ‖ seq)  ──────┐                    │
│                                                       │                  │
└───────────────────────────────────────────────────────┼──────────────────┘
                                                        │ 心跳 + 遥测
                                                        ▼
┌───────────────── 社团连飞平台（FGMS 分支 / 自写判决服务器）──────────────┐
│  · XDR/UDP MP 包解析（32B 头 + MsgId=7 位置消息）                        │
│  · 权威时间戳 + 位置差分地速（不由客户端报告）                             │
│  · 心跳验签、连续性检查、challenge 注入                                   │
│  · 「物理不可能状态」判定                                                 │
│  · flag 下发：flagN = HMAC(K_server, userid ‖ checkpoint)                │
└──────────────────────────────────────────────────────────────────────────┘
```

**三条铁律**

1. **flag 绝不静态存在于客户端**。客户端只产出"证据"，flag 由服务端验签后下发，且每人不同。否则题目退化为 `strings` + patch 判定，AI 三分钟解决。
2. **反作弊必须活着签字**。不是"不许你作弊"，而是"你作弊也得让一个正常运行、正常签票的反作弊为这个状态签出真票"。
3. **判决权在服务端**。客户端上报仅作交叉验证，不作为唯一依据。

---

## 3. 题目规格

### 3.1 flag1 —— 完成进近

**题面**：从指定起始点起飞，在指定机场指定跑道完成 ILS 进近并安全落地。

**设计约束（已确认）**：**允许使用内置 AP**。这是预期行为，不会飞的人不应该被飞行手感卡住。考点不是驾驶技术。

**判定属性**（全部可从属性树直接读取）：

| 属性 | 用途 |
|---|---|
| `/instrumentation/nav[n]/heading-needle-deflection` | 航向道偏离 |
| `/instrumentation/nav[n]/gs-needle-deflection-norm` | 下滑道偏离（归一化 -1~1） |
| `/instrumentation/nav[n]/gs-distance` | 距跑道距离（米） |
| `/velocities/vertical-speed-fps` | 接地垂直速度 |
| `/orientation/roll-deg` | 坡度 |
| `/position/altitude-agl-ft` | 离地高度（弹跳检测） |

**建议判据（阈值必须用真人基线校准，见 PLAN §2）**

- 距接地点 10nm 起，`|gs-needle-deflection-norm| < 0.3` 时间占比 ≥ 90%
- 决断高度 200ft 前不得出现偏离 > 0.8（不稳定进近）
- 接地瞬间：`|VS| < 150 fpm`、`|roll| < 5°`、横向偏中心 < 5m
- 接地后 2s 内 `altitude-agl` 不得重新上升（无弹跳）

**分档给分**：落地成功 40% / 稳定进近 30% / 接地品质 30%。让"飞得烂但飞下来了"的人拿部分分。

---

### 3.2 flag2 —— 飞到某个地方

**题面**：给定有限线索，解算出目标点，飞抵其上方。

三个可选形态（建议选 B，解题成分与飞行成分兼备）：

| 形态 | 描述 | 评价 |
|---|---|---|
| A. 纯转场 | 直给坐标，长途飞行 | 只剩体力活，AI 可完全代劳，不推荐 |
| **B. 领航解谜** | **给出模糊线索（航图残片 / 相对方位 / 地文描述），需自行解算目标点** | **推荐** |
| C. 机动挑战 | 目标点需低空穿越特定地形（峡谷、桥洞） | 可与 B 叠加作为加分项 |

**触发条件**：进入目标点水平半径 X 内、且高度低于 Y，持续 N 秒（防瞬擦边）。

**建议线索设计**：给出三个已知地标的相对方位与距离，选手用 VOR/DME 或自行解算交会点。`airportinfo()` 系列 Nasal 函数可用于辅助，但线索应设计为需要一步真实推理。

---

### 3.3 flag3 —— 绕过反作弊实现「飞天遁地」

**题面**：在**默认 FDM（JSBSim / YASim）+ 反作弊正常运行**的前提下，让模拟器报出超出飞机结构极限的空速（及高度/深度），并让反作弊为此签出真票。

**三个检查点**（均要求**连续、平滑、持续**，防瞬移刷分）：

| 名称 | 条件 | 持续 |
|---|---|---|
| 飞天 | 气压高度 > 100,000 ft | ≥ 10 s |
| 遁地 | `altitude-agl < -300 ft` | ≥ 10 s |
| 超速 | 空速 > 3 × VNE | ≥ 15 s |

**服务端速度计算**：MP 位置消息含 ECEF 速度矢量，但基础包可能不含 `vcas`。服务端**用自己的收包时间戳对位置做差分算地速**，再与客户端上报的马赫数交叉验证——两者对不上本身就是作弊信号。

**难度真相（重要）**：物理不可能本身是廉价的。FlightGear 自带后门：

- `--fdm=ufo` / `magic` / `null`：无物理约束的飞行模型，任意速度任意位置
- `--fdm=external` + `--native-fdm=socket,in,30,,5500,udp`：外部程序通过网络直接喂 FDM 状态，FG 照单全收

也就是说玩家不改一行二进制、不碰反作弊，光靠命令行 + 一个自建 UDP 服务端就能 Mach 5 钻地。

> **结论：flag3 的难度 100% 在反作弊，物理只是皮。** 工作量必须投在反作弊上，不要投在物理场景上。

---

## 4. 反作弊规格（本题核心）

### 4.1 强制使用机制

"使用我们自己的反作弊"不能靠自觉，靠耦合：

```
反作弊签发 session ticket  →  连飞平台要求 ticket 才接受注册
                           →  没有 ticket = 上不了平台 = 三道题全部做不了
```

心跳中断/跳号/重复 → 整场会话作废。这样"绕过反作弊"的语义从**删文件**变成**逆向 + 内存攻防**。

### 4.2 分层防护与对应攻击面

| 层 | 攻击手段 | 检测方式 | 处置 |
|---|---|---|---|
| L0 | 换 `--fdm` / `--prop:` 覆盖 / `--load-tape` | 启动参数白名单、`/sim/fdm*` 校验、tape 未加载 | 拒绝启动 |
| L1 | 改机型 XML（无阻力、超大推力） | 机型数据目录哈希 | 拒绝启动 |
| L2 | telnet / generic 写状态属性 | 审计写入 `/position/*` `/velocities/*` `/orientation/*` `/sim/freeze/*` `/sim/time/speed-up` `/environment/*` | 告警 + 心跳染色 |
| L3 | 自建外部 FDM 服务器喂假状态 | 启动参数 + 状态源可信度标记 | 心跳染色，不下发 flag3 |
| L4 | 内存 patch / hook fgfs | fgfs `.text` CRC 自检、`/proc/self/maps` 扫 frida / LD_PRELOAD / 注入库 | 告警 |
| L5 | 内存 patch 反作弊自身 | 自哈希 + 反调试 + 蜜罐分支 | 签出诱饵票据 |

### 4.3 密钥与票据

```
K = KDF( hash(anticheatd .text)
       ‖ hash(fgfs binary)
       ‖ hash(aircraft data dir)
       ‖ userid
       ‖ session_nonce )
```

- K **只在内存中派生并存活，用完即擦**，静态反编译拿不到
- 心跳：`HMAC(K, 状态流摘要 ‖ seq)`，1 Hz
- **flag 生成用服务端的 `K_server`，不用 K**。否则挖出反作弊 key 就能直接算出 flag1/flag2，造成连带崩塌

### 4.4 蜜罐分支（研究生难度的关键层）

检测到调试器时**不崩溃、不报错**，改为走一条假分支，签出**诱饵票据**。

后果：dump 内存只会拿到假 key。玩家必须静态分析定位检测点、精确 patch 掉、再让真分支在被调试状态下执行。这一步**不是问 AI 能问出来的**，必须坐在 IDA 前熬。

### 4.5 anti-VM（"要求参赛者关闭虚拟化"）

| 类别 | 检测项 |
|---|---|
| CPU | `CPUID.1:ECX[31]` hypervisor bit；leaf `0x40000000` hypervisor brand 字符串 |
| Linux | `/proc/cpuinfo` 的 `hypervisor` flag；`dmesg` "Hypervisor detected"；`/dev/kvm` 存在性 |
| 固件 | DMI/SMBIOS `/sys/class/dmi/id/{product_name,sys_vendor,bios_vendor}` 含 VMware/VirtualBox/QEMU/KVM |
| 网络 | 网卡 MAC OUI（VMware `00:50:56` / `00:0C:29`、VirtualBox `08:00:27` 等） |
| 背板 | VMware I/O backdoor port `0x5658` |
| Windows | 注册表磁盘/显卡/系统名；驱动名；`Win32_BaseBoard` / `Win32_BIOS` / `Win32_ComputerSystem` Model |
| 进程/服务 | `vmtoolsd` / `VBoxService` / `qemu-ga` 等 |
| 时序 | `RDTSC` / `CPUID` 指令开销异常（VM 下陷入开销显著） |

**误杀风险（必须提前处理）**：

- Windows 启用 Hyper-V / WSL2 / Windows Sandbox 时，**宿主本身** CPUID 会置 hypervisor bit
- Credential Guard、Device Guard、核心隔离（内存完整性 / VBS）同样基于虚拟化
- 部分杀软与第三方反作弊自带虚拟化层

→ 必须随题目发布**一页"关闭虚拟化操作指引"**（Windows：`bcdedit /set hypervisorlaunchtype off`、关闭核心隔离、关闭 WSL2；Linux：卸载 kvm 模块 / BIOS 关闭 VT-x），并提供**自检工具**让选手开赛前先跑一遍。

### 4.6 统一不变量（三题共用）

> **允许任何方式驱动操纵面（含内置 AP、外部脚本），但绝不允许绕过物理引擎。**

这条一句话覆盖 flag1/2/3，检测器实现量减半。注意：允许 AP 意味着**"人类操作抖动检测"彻底作废**（AP 本身就是完美等间距的），不要再尝试用它区分 bot 与人。

---

## 5. 连飞平台与服务端判决

### 5.1 MP 协议要点

- XDR over UDP，头部固定 **32 字节**
- `Magic = 0x46474653 ("FGFS")`、`Version = 0x00010001`
- `MsgId = 7` 为位置消息（1 为 chat，已废弃）
- 头字段顺序：Magic / Version / MsgId / MsgLen / RequestedRangeNm / ReplyPort / Callsign(8B)
- 位置消息第一部分：ECEF 位置、**角轴姿态（角度编码进轴长度）**、XYZ 速度、角速度
- 第二部分：属性 ID / 值对；2017.2+ 有 "Transmit As" 紧凑编码映射

**坑**：wiki 称可添加多个 `--multiplay=out` 把流量镜像到私有服务器，但社区有实测反馈"只有最后一个 out 生效"。说法冲突。→ **所有流量必须强制经过我方服务器**，不在客户端留可选项；动手前先抓包实测确认。

**fgms 私有化**：官方有 docker 镜像（`flightgear/fgms:0.13.4`），私有部署需关闭 `relay` / `tracked` / `is_hub`，配置 `server.name` / `server.port` / `out_of_reach` / `blacklist` / `admin_port`。

### 5.2 服务端判决能力

| 能力 | 说明 |
|---|---|
| 权威时间戳 | 服务端收包即打时戳，跨选手可比，跨会话不可重放 |
| 位置差分地速 | 自己算，不采信客户端上报 |
| 连续性检查 | 轨迹无跳变、无瞬移 |
| 心跳验签 | 连续、无中断、无跳号、无重复 |
| Challenge 注入 | 飞行中随机时刻推环境变更，校验响应时延与幅度 |
| flag 下发 | `flagN = HMAC(K_server, userid ‖ checkpoint)` |

**Challenge 机制**：离线生成的假轨迹不知道 challenge 何时来、内容是什么。伪造被迫变成实时，成本反超老实玩。

### 5.3 诚实的能力边界

**客户端完全不可信时，远程判定不可能做到不可伪造**（与 DRM 同一困境，无例外）。

本方案目标是：**让伪造成本 > 老实完成的成本**。

弱 flag 被强攻击者顺带拿下，在 CTF 里不算设计缺陷——能攻破 flag3 的人本来就该有 flag1。要防的是没做出 flag3 的人用轻量手段骗过 flag1/2。

---

## 6. 参赛者环境

### 6.1 硬性要求

- **物理机运行，关闭虚拟化**（提供自检工具与操作指引）
- 反作弊常驻运行（否则无法注册连飞）
- 统一 FG 版本、机型、机场、scenery、气象（全部写进 `launcher.sh`）
- 建议直接分发预装镜像 / 容器 + 一键脚本

> 环境不一致造成的"我跑不起来"，杀伤力远大于"我做不出来"。

### 6.2 启动流程

```
1. 选手运行 anticheat-selfcheck（自检 anti-VM、依赖、版本）
2. 运行 launcher.sh
   ├─ 校验启动参数白名单
   ├─ 校验机型/scenery 哈希
   ├─ 启动 anticheatd（拿到 session ticket）
   └─ 启动 fgfs：--addon / --generic / --multiplay / --telnet / --httpd
3. anticheatd 开始 1Hz 心跳
4. 连飞平台接受注册，会话开始
```

### 6.3 训练模式

允许不限次练习、允许任意 AP、允许 `--fdm=external`（熟悉 FDM 协议用），**但不产出任何证据**。手动飞 ILS 对没摸过飞行模拟的人曲线很陡，不给练习场第一天就没人做了。

---

## 7. 分值建议

| 题目 | 分值 | 性质 |
|---|---|---|
| flag1 | 30 | 分档给分，保底可拿 |
| flag2 | 30 | 全或无 |
| flag3 | 40 | 全或无，硬骨头 |
| Writeup 加分 | 10 | 鼓励记录过程 |

---

## 8. 附录

### 8.1 常用属性速查

```
/position/latitude-deg  /position/longitude-deg
/position/altitude-ft   /position/altitude-agl-ft
/orientation/roll-deg   /orientation/pitch-deg  /orientation/heading-deg
/velocities/airspeed-kt /velocities/vertical-speed-fps
/instrumentation/nav[n]/heading-needle-deflection
/instrumentation/nav[n]/gs-needle-deflection-norm
/instrumentation/nav[n]/gs-distance
/controls/flight/{aileron,elevator,rudder,throttle}
/autopilot/locks/*      /autopilot/settings/*
/sim/freeze/*           /sim/time/speed-up
/environment/*          /ai/aircraft[n]/controls/*
```

### 8.2 接口命令速查

```bash
# 属性树服务
--httpd=5400          # 浏览器浏览/修改属性树
--telnet=5401         # get/set/dump/run/subscribe/cd/ls 等命令
--props=5401          # 同 telnet，无 HTML 包装

# 遥测（generic protocol，XML 定义放 $FG_ROOT/Protocol）
--generic=socket,out,30,127.0.0.1,5510,udp,ctf-telemetry
--generic=socket,in,30,127.0.0.1,5511,udp,ctf-controls

# 连飞
--multiplay=out,10,<server>,5000 --multiplay=in,10,<local>,5000 --callsign=<uid>

# 加载 addon（需 addon-metadata.xml + addon-main.nas，后者须含 main()）
--addon=/path/to/ctf-addon
```

### 8.3 FDM 外部协议（练习模式用，正式题禁用）

- `--fdm=external --native-fdm=socket,in,30,,5500,udp`
- 定长二进制，**大端**：v24 = 408 字节，v25 = 552 字节
- 关键字段：`version, padding, lon_rad, lat_rad, alt_m, agl_m, phi_rad, theta_rad, psi_rad, alpha_rad, beta_rad, phidot, thetadot, psidot, vcas, climb_rate, v_north, v_east, v_down, v_wind_body_n/e/d, A_X/Y/Z_pilot, stall_warning, slip_deg, num_engines, eng_state[4], rpm[4], fuel_flow[4], egt[4], cht[4], mp_osi[4], tit[4], oil_temp[4], oil_px[4], num_tanks, fuel_quantity[4], num_wheels, wow[3], gear_pos[3], gear_steer[3], gear_compression[3], cur_time, warp, visibility, elevator, elevator_trim_tab, left_flap, right_flap, left_aileron, right_aileron, rudder, nose_wheel, speedbrake, spoilers`
- 数组上限：`FG_MAX_ENGINES=4`、`FG_MAX_WHEELS=3`、`FG_MAX_TANKS=4`

### 8.4 Addon 最小结构

```
ctf-addon/
├── addon-metadata.xml       # 必填：声明 id / name / version
├── addon-main.nas           # 必填：必须含 main()，加载进 __addon[ID]__ 命名空间
├── addon-config.xml         # 可选：覆盖 defaults.xml（可覆盖按键、自动驾驶、状态机）
├── addon-menubar-items.xml  # 可选：菜单项
└── gui/dialogs/*.xml        # 可选：自定义对话框
```

规则层与 Boss 靶机全部用 Nasal 实现，**不 fork FlightGear 一行 C++**：FG 是数百万行 C++，依赖 OSG/Boost/OpenAL/Qt，完整编译数小时，且每个新版本都可能让 patch 失效。

### 8.5 参考资料

- Property Tree Servers — https://wiki.flightgear.org/Property_Tree_Servers
- Telnet usage — https://wiki.flightgear.org/Telnet_usage
- Howto: Create a generic protocol — https://wiki.flightgear.org/Howto:Create_a_generic_protocol
- Multiplayer protocol — https://wiki.flightgear.org/Multiplayer_protocol
- Howto: Multiplayer — https://wiki.flightgear.org/Multiplayer
- Howto: Set up a multiplayer server — https://wiki.flightgear.org/Howto:Set_up_a_multiplayer_server
- Addons — https://wiki.flightgear.org/Addons
- Instant Replay / Flight Recorder — https://wiki.flightgear.org/Instant_Replay

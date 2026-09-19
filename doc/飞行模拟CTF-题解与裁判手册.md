# 飞行模拟 CTF · 题解与裁判手册

> **内部文档，禁止下发给参赛者**
> 配套：`飞行模拟CTF-系统设计.md` · `飞行模拟CTF-开发计划.md` · `飞行模拟CTF-题面.md`

---

## 0. 设计意图回顾

本题的核心不是"考飞行"，而是**让 AI 只能当副驾**。三条 flag 分别压在 AI 够不着的地方：

| 题 | AI 能帮的 | AI 帮不了的 |
|---|---|---|
| flag1 | 讲解 ILS 原理、AP 配置步骤 | 本机那台 FG 的调试与迭代 |
| flag2 | 推导交会解算公式 | 判断哪个交点可信（需读题面语义） |
| flag3 | 解释协议结构、给 patch 思路 | 调试器会话、内存布局、几十次试错 |

**关键取舍**：允许内置 AP。考点从"驾驶手感"移到"系统理解"，对 CS 学生才公平。代价是 L2 层检测中的"人类操作抖动"彻底作废，不要再用它区分 bot 与人。

---

## 1. flag1 · 进近

### 1.1 预期解

1. 起飞，爬升至指定高度
2. NAV1 调至跑道 ILS 频率
3. 截获航向道 → 接通 AP 的 `APP` / `NAV` 模式
4. 截获下滑道 → 保持
5. 决断高度断开 AP（或保持），接地

全程可 AP，零飞行基础可在 30 分钟内完成。

### 1.2 判定属性

```
/instrumentation/nav[n]/heading-needle-deflection      航向道偏离
/instrumentation/nav[n]/gs-needle-deflection-norm      下滑道偏离（归一化 -1~1）
/instrumentation/nav[n]/gs-distance                    距跑道（米）
/velocities/vertical-speed-fps                         垂直速度
/orientation/roll-deg                                  坡度
/position/altitude-agl-ft                              离地高度
/controls/flight/*                                     操纵面（交叉验证用）
/autopilot/locks/*                                     AP 状态（记录用，不作为扣分项）
```

### 1.3 判据（阈值必须用 P0 基线校准）

```python
def judge_flag1(track, gs_dist_ref=18520):  # 10 nm ≈ 18520 m
    # 1) 下滑道跟踪质量
    seg = [f for f in track if f.gs_distance < gs_dist_ref]
    stable = sum(1 for f in seg if abs(f.gs_needle_norm) < 0.3) / len(seg)
    score_track = 30 * (stable >= 0.90)

    # 2) 不稳定进近检查（决断高度前不得大幅偏离）
    dec = [f for f in track if f.alt_agl < 200 and f.gs_distance > 1000]
    unstable = any(abs(f.gs_needle_norm) > 0.8 for f in dec)
    score_stable = 30 * (not unstable)

    # 3) 接地品质
    t = touchdown_frame(track)          # 首个 wow==1 且 agl<1 的帧
    vs_ok   = abs(t.vs_fps) < 2.5       # 150 fpm ≈ 2.5 fps
    roll_ok = abs(t.roll_deg) < 5.0
    lat_ok  = abs(t.lateral_offset_m) < 5.0
    bounce  = any(f.alt_agl > 3.0 for f in track[t.idx:t.idx + 2*RATE])
    score_land = 40 * (vs_ok and roll_ok and lat_ok and not bounce)

    return score_track + score_stable + score_land   # 满分 100 → 折算 30 分
```

### 1.4 阈值校准方法

**必须**用 `baseline.csv`（P0 阶段 stock AP 跑 20 次）反推：

- `stable ≥ 0.90` 应让 stock AP **能过**（这是"不卡住不会飞的人"的承诺）
- 接地品质三项（`vs`/`roll`/`lat`）应让 stock AP **在无风条件下部分通过、在有风条件下失败**，从而让分档有意义
- 若 AP 满分率 > 80%，说明场景太简单，需加侧风

### 1.5 反作弊关注点

- `/sim/freeze/*`、`/sim/time/speed-up` 被改 → 作废
- 直接写 `/position/*`、`/velocities/*`、`/orientation/*` → 作废
- 场景参数用 `userid` 做 seed 随机化（风向、强度），防止硬编码过拟合

---

## 2. flag2 · 幽灵航迹

### 2.1 谜题设计（这才是本体）

**下发数据**（按 callsign 派生，每人不同）：

```
STATION A : ident=<VOR-A>  freq=<f>   DME=<dA> nm
STATION B : ident=<VOR-B>  freq=<f>   DME=<dB> nm
STATION C : ident=<VOR-C>  freq=<f>   RADIAL=<rC> °
```

**解算步骤**：

1. 查三个导航台的坐标（FG 的 navdata 或公开航图资料）
2. 以 A 为圆心、`dA` 为半径画圆；以 B 为圆心、`dB` 为半径画圆
3. 两圆交于 **P1、P2** 两点
4. 从 C 台观测 P1、P2 的方位角，与下发的 `rC` 比对，**吻合者即目标点**

**为什么这样设计**：

- 两个距离圈天然产生二义性 → 有真实的"决定"环节
- C 只给方位不给距离 → 无法反向跳到第 2 步，必须先算出两个候选
- 全程可在纸面/脚本完成，但**飞过去**需要人操作
- AI 能秒给公式，但题面里的"注：读数自目标点观测所得"这一句的方向性（是"目标点看台"不是"台看目标点"）是易错点，AI 也常搞反

### 2.2 解算参考实现

```python
import math
from geopy.distance import geodesic

def circle_intersections(A, B, rA_nm, rB_nm):
    """A, B: (lat, lon)；半径海里。返回两个交点。"""
    # 近似：在局部平面用米计算，再反算经纬度
    d = geodesic(A, B).meters
    rA, rB = rA_nm * 1852.0, rB_nm * 1852.0
    if d > rA + rB or d < abs(rA - rB):
        return []                      # 无解，说明出题参数有问题
    a = (rA**2 - rB**2 + d**2) / (2 * d)
    h = math.sqrt(rA**2 - a**2)

    # A→B 的单位向量（局部平面近似）
    dx = (B[1] - A[1]) * 111320 * math.cos(math.radians(A[0]))
    dy = (B[0] - A[0]) * 110540
    ux, uy = dx / d, dy / d
    px, py = -uy, ux                   # 垂直方向

    base = (A[0] + a * uy / 110540,
            A[1] + a * ux / (111320 * math.cos(math.radians(A[0]))))
    out = []
    for s in (+1, -1):
        lat = base[0] + s * h * py / 110540
        lon = base[1] + s * h * px / (111320 * math.cos(math.radians(A[0])))
        out.append((lat, lon))
    return out

def disambiguate(P1, P2, C, radial_from_target):
    """radial_from_target: 目标点观测 C 台的方位角。
       注意方向：目标是"从目标点看台"，故与"从台看目标点"相差 180°。"""
    def obs_bearing(target, station):
        # 目标点 → 台 的方位
        lat1, lon1 = map(math.radians, target)
        lat2, lon2 = map(math.radians, station)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
        return (math.degrees(math.atan2(y, x)) + 360) % 360

    e1 = min(abs(obs_bearing(P1, C) - radial_from_target) % 360,
             360 - abs(obs_bearing(P1, C) - radial_from_target) % 360)
    e2 = min(abs(obs_bearing(P2, C) - radial_from_target) % 360,
             360 - abs(obs_bearing(P2, C) - radial_from_target) % 360)
    return P1 if e1 < e2 else P2
```

### 2.3 出题参数自检

生成参数时必须断言：

- [ ] `|dA − dB| < dist(A,B) < dA + dB` → 确保**恰有两个**交点
- [ ] `dist(A,B)` 与交点分离度足够大（两交点相距 ≥ 5 nm），否则判定半径会重叠
- [ ] 两交点相对 C 台的方位角差 ≥ 30°，否则消歧失效
- [ ] 目标点不在禁飞区/水面上（避免无法到达）

### 2.4 触发判定

```python
def judge_flag2(uid, track, target, radius_m=2000, ceil_ft=8000, dur_s=10):
    inside = [f for f in track
              if geodesic((f.lat, f.lon), target).meters < radius_m
              and f.alt_ft < ceil_ft]
    if not inside:
        return False
    # 连续性：覆盖时间跨度 ≥ dur_s，且期间不得有跳出
    span = inside[-1].t - inside[0].t
    contig = len(inside) == (track.index(inside[-1]) - track.index(inside[0]) + 1)
    return span >= dur_s and contig
```

`contig` 这一条是关键：**瞬移擦边会在序列中留下空洞**，直接拒。

---

## 3. flag3 · 飞天遁地

### 3.1 难度真相（裁判必读）

**物理不可能本身是廉价的。** FlightGear 自带后门：

| 手段 | 效果 | 成本 |
|---|---|---|
| `--fdm=ufo` / `magic` / `null` | 无物理约束，任意速度任意位置 | 一个命令行参数 |
| `--fdm=external` + `--native-fdm=socket,in,30,,5500,udp` | 外部程序直接喂 FDM 状态，FG 照单全收 | 一个 UDP 客户端 |
| `--prop:` 覆盖状态属性 | 直接改 altitude/空速 | 一个命令行参数 |

**不改一行二进制、不碰反作弊，就能 Mach 5 钻地。**

> 因此：**flag3 的难度 100% 在反作弊，物理只是皮。** 工作量与难度旋钮都必须投在这里。

### 3.2 预期解族（按难度分档，不预设唯一答案）

| 档 | 路径 | 选手需做的事 | 预估耗时 |
|---|---|---|---|
| **A** | 骗过 L0 启动参数校验 | `LD_PRELOAD` hook `getenv`/`/proc` 读取；或让 launcher 传入合法参数后运行时切换 | 2–4 h |
| **B** | 自建外部 FDM 服务器 | 实现 FG 原生 FDM 二进制协议（v24 = 408B / v25 = 552B，大端），对齐字段布局与字节序；同时骗过 L0 | 1–2 天 |
| **C** | 内存 patch / hook fgfs | 定位 FDM 状态结构，运行时改写；绕过 L4 的 CRC 与 maps 扫描 | 2–3 天 |
| **D** | 攻破反作弊自身 | 定位并 patch L5 检测点，识别并规避蜜罐分支，让真分支在被调试态下执行 | 3–5 天 |

**建议将 B 作为「官方预期解」**：不用 patch 任何东西，但要自己实现真实网络协议——正经的协议逆向工作量，研究生级，且**可验证、可复现**。

**D 是满分档**：只有走过蜜罐分支的人才真正理解了这套反作弊。

### 3.3 必须在出题时堵死的低成本路径

验收时逐条实测，任一未堵住则该题作废：

- [ ] `--fdm=ufo` / `magic` / `null` / `external` → **L0 拒绝启动**
- [ ] `--load-tape=<file>` → **L0 拒绝启动**
- [ ] `--prop:/position/...` 等命令行覆盖 → **L0 拒绝启动**
- [ ] 改 JSBSim/YASim 机型 XML（去阻力、超大推力）→ **L1 哈希不匹配，拒绝启动**
- [ ] 换 scenery / 机场数据 → **L1 哈希不匹配**
- [ ] telnet `set /position/altitude-ft` → **L2 拦截 + 心跳染色**
- [ ] generic protocol input 写状态属性 → **L2 拦截**
- [ ] httpd(5400) 改属性 → **L2 拦截**（别只堵 telnet，三个入口都要堵）
- [ ] `/sim/freeze/*`、`/sim/time/speed-up` → **L2 拦截**
- [ ] `kill` / 挂起反作弊 → **心跳中断，整场作废**
- [ ] 挂调试器 → **拿到诱饵票据，非真 flag**

### 3.4 判定实现

```python
VNE_KIAS = 163            # c172p，按实际机型调整
CHECKPOINTS = {
    "soar":  lambda f: f.alt_baro_ft > 100_000,   dur=10,
    "dig":   lambda f: f.alt_agl_ft  <    -300,   dur=15 if False else 10,
    "speed": lambda f: f.ias_kt      > 3 * VNE_KIAS, dur=15,
}

def judge_flag3(track, rate_hz=10):
    results = {}
    for name, (pred, dur) in CHECKPOINTS.items():
        need = int(dur * rate_hz)
        run = best = 0
        smooth = True
        for i, f in enumerate(track):
            if pred(f):
                run += 1
                if i > 0 and not is_smooth(track[i-1], f):
                    smooth = False
                best = max(best, run)
            else:
                run = 0
        results[name] = (best >= need) and smooth
    return results

def is_smooth(a, b, max_accel_g=50):
    """相邻帧位置差分反推速度，跳变即判不平滑。"""
    dt = b.t - a.t
    dpos = geodesic((a.lat, a.lon), (b.lat, b.lon)).meters
    v = dpos / dt if dt > 0 else 0
    # 与前帧速度比较，加速度超阈值视为瞬移
    return abs(v - a.v_ground) / dt < max_accel_g * 9.81
```

**服务端自算地速**：MP 基础包可能不含 `vcas`。用收包时间戳对位置差分算地速，再与客户端上报的马赫数交叉验证——**两者对不上本身就是作弊信号**。

### 3.5 反作弊核心机制（裁判需理解，勿外泄）

```
K = KDF( hash(anticheatd .text)
       ‖ hash(fgfs binary)
       ‖ hash(aircraft data dir)
       ‖ userid
       ‖ session_nonce )

心跳（1 Hz）：HMAC(K, 状态流摘要 ‖ seq)
```

- K **只存在于内存，用完即擦** → 静态反编译拿不到
- **flag 用 `K_server` 生成，不用 K** → 挖出反作弊密钥也拿不到 flag1/flag2（防连带崩塌）
- 心跳中断/跳号/重复 → 整场作废 → "绕过"从「删文件」升级为「逆向 + 内存攻防」
- **蜜罐分支**：检测到调试器不崩溃，改签诱饵票据 → dump 内存只拿假 key

### 3.6 运营注意

- **flag3 必须在独立频道进行**。公共频道 Mach 5 穿地会撞穿他人飞机，且当场剧透
- 判定通过后才在排行榜显示
- 达成任意 2 个检查点给部分分（建议 15/40），全达成给满分

---

## 4. 判分与 flag 下发

```python
def issue_flag(uid, checkpoint):
    return "flag{" + hmac(K_server, f"{uid}|{checkpoint}".encode()).hexdigest()[:32] + "}"
```

每人不同，答案共享无效。

| 题 | 折算 |
|---|---|
| flag1 | 分档 → 0–30 |
| flag2 | 全或无 → 0/30 |
| flag3 | 2 个检查点 15，全达成 40 |
| Writeup | 0–10 |
| **上限** | **110** |

---

## 5. Hint 分级（按时间梯度在服务器公告释放）

| 时间 | 题 | Hint |
|---|---|---|
| T+2h | 1 | 「NAV1 频率调好之后，试试 AP 面板上的 APP 按钮。」 |
| T+4h | 1 | 「下滑道要在航向道截获之后才会捕获，别急着下降。」 |
| T+3h | 2 | 「两条距离圈会在图上画出两个交点，这是正常的。」 |
| T+5h | 2 | 「注意日志里那句『自目标点观测所得』——方位是有方向的。」 |
| T+6h | 3 | 「模拟器信任它收到的飞行状态。谁在给它喂数据？」 |
| T+10h | 3 | 「`--fdm` 不是唯一的后门。想想 FG 还接受什么输入。」 |
| T+14h | 3 | 「反作弊只检查它启动时的状态。它活着的每一秒都在签字。」 |

Hint 释放节奏是**难度旋钮**。若目标是"至少 1 人做出 flag3"，T+10h 的 hint 必须给；若目标是"零通过"，砍掉 T+6h 之后全部。

---

## 6. 常见作弊与处置

| 现象 | 判定 | 处置 |
|---|---|---|
| 提交轨迹与服务器观测时间戳不符 | 重放/伪造 | 作废，记录 |
| 心跳中断后恢复 | 会话断裂 | 整场作废 |
| 客户端上报马赫数与服务端差分地速严重不符 | 状态伪造 | 作废 |
| 多 callsign 提交相同解题思路但数值完全一致 | 共享 | 人工复核，双方扣分 |
| 在公共频道进行 flag3 操作 | 影响他人 | 警告，屡犯禁赛 |
| 攻击服务器 | 越界 | 立即禁赛 |

---

## 7. 出题组自验清单（上线前必须全过）

**flag1**
- [ ] stock AP 直飞能拿基础分但拿不满
- [ ] 手飞好进近能拿满分
- [ ] 摔地/偏离航道不给分

**flag2**
- [ ] 用 2.2 的参考实现能算出目标点
- [ ] 两交点确实存在且 C 台能消歧
- [ ] 瞬移擦边不触发

**flag3**
- [ ] **出题组自己完整走一遍 B 档路径并成功拿到 flag**
- [ ] 3.3 表中每一条低成本路径实测被堵
- [ ] 挂调试器确实拿到诱饵票据

**平台**
- [ ] 多人同时在线互不干扰
- [ ] 重放旧轨迹被 nonce/时间戳拒绝
- [ ] challenge 注入后响应时延校验生效

---

## 8. 若时间不够，砍什么

按此顺序砍，每题仍可独立成立：

1. **砍蜜罐分支**（flag3 掉一档难度，但仍需逆向反调试 → 可接受）
2. **砍 challenge 注入**（伪造成本降低，但 hash chain + nonce 仍在）
3. **砍 flag2 的谜题成分**（退化为直给坐标的转场题 → 只剩体力活，不推荐）
4. **保留**：hash chain、心跳票据、L0/L1 启动校验、flag 服务端派生

> 后三条是底线。砍掉任何一条，题目会退化为「AI 十分钟解决」。

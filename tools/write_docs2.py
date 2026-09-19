# -*- coding: utf-8 -*-
import os

ti_jie = """# 飞行模拟 CTF · 题解与裁判手册

> **内部文档，禁止下发给参赛者**
> 配套：`飞行模拟CTF-系统设计.md` · `飞行模拟CTF-开发计划.md` · `飞行模拟CTF-题面.md`

---

## 0. 设计意图回顾

本题的核心不是"考飞行"，而是**让 AI 只能当副驾**。两道 flag 分别压在 AI 够不着的地方：

| 题 | AI 能帮的 | AI 帮不了的 |
|---|---|---|
| flag1 | 讲解航路规划、AP配置步骤 | 本机那台 FG 的实时调试与决策 |
| flag2 | 解释协议结构、给 patch 思路 | 调试器会话、内存布局、几十次试错 |

**关键取舍**：允许内置 AP。考点从"驾驶手感"移到"系统理解"，对 CS 学生才公平。代价是 L2 层检测中的"人类操作抖动"彻底作废，不要再用它区分 bot 与人。

---

## 1. flag1 · 飞抵上海张江

### 1.1 预期解

1. 在浦东机场 (ZSPD) 起飞，使用 c172p 机型
2. 导航至目标点 (31.177°N, 121.596°E)，约 25nm 航程
3. 降低高度至 1000ft 以下，进入 500m 半径区域
4. 持续停留 ≥ 5s，触发 flag1
5. 服务器生成 ATC 语音，包含加密的 flag key
6. 选手解码音频获得 key，提交到 Web 界面

### 1.2 判决逻辑

```python
def judge_flag1(rows, cfg):
    target_lat = 31.177  # 上科大
    target_lon = 121.596
    radius_m = 500.0
    ceil_ft = 1000.0
    dur_s = 5.0
    
    for uid, seq in rows.groupby('callsign'):
        track = seq.sort_values('timestamp')
        reached = False
        for _, f in track.iterrows():
            d = haversine((f.lat, f.lon), (target_lat, target_lon))
            if d < radius_m and f.alt_ft < ceil_ft:
                if not reached:
                    start = f.timestamp
                    reached = True
                elif f.timestamp - start >= dur_s:
                    return True, d, f.alt_ft
            elif reached:
                reached = False
    return False, None, None
```

### 1.3 ATC 语音生成

```python
import base64, hashlib

def generate_atc_audio(uid, flag_key):
    # 明文："ATC: Welcome to ShanghaiTech. Your code is: XXXX"
    text = f"ATC: Welcome to ShanghaiUniversity of Science and Technology. Your code is: {flag_key}"
    
    # 可选加密层：
    # Level 1 (easy): base64 编码
    # Level 2 (medium): AES-128-CBC, IV=first 16 bytes of SHA256(uid)
    # Level 3 (hard): RSA-OAEP with challenge-specific public key
    
    audio_b64 = base64.b64encode(text.encode()).decode()
    return audio_b64
```

### 1.4 反作弊关注点

- `/sim/freeze/*`、`/sim/time/speed-up` 被改 → 作废
- 直接写 `/position/*`、`/velocities/*` → 作废
- 场景参数用 `userid` 做 seed 随机化（风向、强度），防止硬编码过拟合

---

## 2. flag2 · 幽灵航迹（物理不可能状态）

### 2.1 难度真相（裁判必读）

**物理不可能本身是廉价的。** FlightGear 自带后门：

| 手段 | 效果 | 成本 |
|---|---|---|
| `--fdm=ufo` / `magic` / `null` | 无物理约束，任意速度任意位置 | 一个命令行参数 |
| `--fdm=external` + `--native-fdm=socket,in,30,,5500,udp` | 外部程序通过网络直接喂 FDM 状态 | 一个小 UDP 服务端 |

> **结论：flag2 的难度 100% 在反作弊，物理只是皮。** 工作量必须投在反作弊上。

### 2.2 判决逻辑

```python
def judge_flag2(rows, cfg):
    soar_alt = cfg.get('soar_alt_ft', 100000)
    dig_agl = cfg.get('dig_agl_ft', -300)
    vne_kias = cfg.get('vne_kias', 163)
    speed_factor = cfg.get('speed_factor', 3.0)
    
    checkpoints = []
    
    for uid, seq in rows.groupby('callsign'):
        track = seq.sort_values('timestamp')
        
        # 飞天
        soar_frames = track[track['alt_pa_ft'] > soar_alt]
        if _continuous_duration(soar_frames, cfg.get('soar_dur_s', 10)):
            checkpoints.append('soar')
        
        # 遁地
        dig_frames = track[track['alt_agl_ft'] < dig_agl]
        if _continuous_duration(dig_frames, cfg.get('dig_dur_s', 10)):
            checkpoints.append('dig')
        
        # 超速
        speed_limit = vne_kias * speed_factor
        speed_frames = track[track['airspeed_kt'] > speed_limit]
        if _continuous_duration(speed_frames, cfg.get('speed_dur_s', 15)):
            checkpoints.append('speed')
    
    # 计分
    n = len(checkpoints)
    if n == 3:
        return 100.0, checkpoints
    elif n == 2:
        return 50.0, checkpoints
    elif n == 1:
        return 20.0, checkpoints
    return 0.0, []

def _continuous_duration(frames, min_s):
    if len(frames) == 0:
        return False
    span = (frames.iloc[-1]['timestamp'] - frames.iloc[0]['timestamp']).total_seconds()
    return span >= min_s
```

### 2.3 得分档位

| 达成检查点 | 得分 |
|---|---|
| 1 个 | 20 分 |
| 2 个 | 50 分 |
| 3 个 | 100 分 |

### 2.4 攻击路径分析（供裁判参考）

| 路径 | 可行性 | 反作弊是否拦截 |
|---|---|---|
| `--fdm=ufo` | 简单 | ✅ L0 拦截（启动参数白名单） |
| `--fdm=external` | 中等 | ⚠️ L3 检测（需绕过 FDM 源追踪） |
| 内存 patch fgfs | 困难 | ⚠️ L4 检测（需绕过进程完整性） |
| 修改反作弊自身 | 极困难 | ⚠️ L5 蜜罐分支（可能拿到假 key） |
| 利用 FG 漏洞 | 未知 | 取决于漏洞触发方式 |

---

## 3. 评分汇总

| Flag | 内容 | 满分 | 判据类型 |
|---|---|---|---|
| flag1 | 飞抵上科大张江 + ATC 解密 | 50 | 连续持续判定 + 解码验证 |
| flag2 | 物理不可能状态 | 100 | 分段计分（1/2/3个检查点） |
| **合计** | | **150** | |

---

## 4. 阈值校准

### flag1 阈值

| 参数 | 当前值 | 校准方法 |
|---|---|---|
| radius_m | 500 | 上科大校园实际尺寸 |
| ceil_ft | 1000 | 低空悬停要求 |
| dur_s | 5 | 防瞬移擦边 |

### flag2 阈值

| 参数 | 当前值 | 校准方法 |
|---|---|---|
| soar_alt_ft | 100000 | 民航机极限约 40000ft |
| dig_agl_ft | -300 | 地下300ft |
| vne_kias | 163 | c172p 结构极限 |
| speed_factor | 3.0 | 3×VNE |

**注意**：所有阈值需通过 P0 基线数据采集后校准，确保：
- flag1 不难也不易（stock AP 能过但需一定技巧）
- flag2 的物理不可能状态在正常飞行中绝不会出现
"""

with open(r'c:\Users\steven\Documents\HW\gkp2026\出题\flightgear-ctf\doc\飞行模拟CTF-题解与裁判手册.md', 'w', encoding='utf-8') as f:
    f.write(ti_jie)
print('题解与裁判手册.md written OK')

# 新方案：简化后的 CTF 题目

## 题目流程

### Flag1: 飞行 + 解密
1. **起飞**：从浦东机场 (ZSPD) 起飞
2. **飞行**：飞往上科大张江校区 (31.177°N, 121.596°E)
3. **到达判定**：在目标点半径 500m 内停留 ≥5s（高度 <1000ft）
4. **ATC 语音下发**：服务器播放 base64 编码的 ATC 语音，包含加密的 flag key
5. **解密提交**：选手解密音频得到 key，输入到独立 web 界面获得 flag1

### Flag2: 物理不可能状态（原 flag3）
绕过反作弊实现以下三种状态之一：
- **飞天**：气压高度 > 100,000 ft，持续 ≥ 10s
- **遁地**：AGL < -300 ft，持续 ≥ 10s  
- **超速**：空速 > 3×VNE (163 kias)，持续 ≥ 15s

要求状态连续平滑（防瞬移刷分），三选二得 50 分，三选三得 100 分。

## 技术要点

### ATC 语音设计
```python
# 服务端生成
import hashlib, base64
flag_key = hashlib.sha256(f"{userid}|flag1|{timestamp}".encode()).hexdigest()[:32]
audio_text = f"ATC: Welcome to Shanghai University. Your code is: {flag_key}"
audio_base64 = base64.b64encode(audio_text.encode()).decode()
# 实际部署时应替换为真实音频文件
```

### 解密挑战
- **初级**：base64 解码 + 提取 key
- **中级**：AES 加密音频，key 分散在多段语音中
- **高级**：RSA 公钥加密，需要逆向找到私钥

### 飞行难度
- 距离：约 20 km ≈ 11 nm
- 时间：正常飞行约 10-15 分钟
- 高度：建议 500-1000 ft 低空飞行（增加挑战性）

## 规则配置 (rules.yaml)

```yaml
flag1:
  airport: "ZSPD"
  target_lat: 31.1770
  target_lon: 121.5960
  radius_m: 500.0
  ceil_ft: 1000.0
  dur_s: 5.0
  atc_audio_base64: ""  # 运行时注入
  decryption_hint: "base64_decode_and_xor"

flag2:
  soar_alt_ft: 100000.0
  soar_dur_s: 10.0
  dig_agl_ft: -300.0
  dig_dur_s: 10.0
  vne_kias: 163.0
  speed_factor: 3.0
  speed_dur_s: 15.0
  max_accel_g: 50.0
```

## 优势

1. **更简单**：去掉复杂的 ILS 进近判定
2. **更多样**：结合飞行 + 密码学，考察不同技能
3. **更公平**：不需要精密飞行技巧，主要考导航和解密
4. **更有趣**：ATC 语音解密增加了 CTF 元素
5. **本地化**：以上科大为目标，增加亲切感

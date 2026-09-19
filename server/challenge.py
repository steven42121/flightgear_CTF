"""Challenge 注入（doc2 §5.2 / doc4 §T+hint：离线伪造不知道何时来、内容是什么）。

机制：
- 会话进行中随机时刻推环境变更（本次实现：能见度 + 风向突变）；
- 判决侧校验"响应时延与幅度"：challenge 发出后 T 秒内，遥测中的
  能见度/航向必须出现相应变化，否则该会话的轨迹被标记 SUSPECT。
- 训练模式不注入。
"""
import random
import time

# 校验窗口：发出后 ≤15s 内应观测到响应
RESPONSE_WINDOW_S = 15.0


class Challenge:
    def __init__(self, cid, kind, target_value, issued_at):
        self.cid = cid
        self.kind = kind            # "visibility" | "wind_shift"
        self.target = target_value
        self.issued_at = issued_at
        self.replied_at = None
        self.replied_value = None

    def observe(self, ts, visibility_m, heading):
        """遥测帧到达时调用，检查是否构成有效响应。"""
        if self.replied_at is not None or ts < self.issued_at:
            return
        if self.kind == "visibility" and visibility_m is not None:
            if abs(visibility_m - self.target) < 1000.0:
                self.replied_at = ts
                self.replied_value = visibility_m
        elif self.kind == "wind_shift" and heading is not None:
            # 风突变后航向应出现显著修正（±5° 以上）
            if abs(heading - self._heading_before) > 5.0:
                self.replied_at = ts
                self.replied_value = heading

    def __init_heading__(self, heading):
        self._heading_before = heading


def plan_challenge(session_started_at, seed=None, max_challenges=3,
                   interval_s=(180.0, 600.0)):
    """为一次会话生成 challenge 计划（触发时刻用随机数，回放者无法预知）。"""
    rng = random.Random(seed)  # seed=None → 每次会话独立
    plan = []
    t = session_started_at + rng.uniform(*interval_s)
    for i in range(max_challenges):
        if rng.random() < 0.5:
            kind, target = "visibility", float(rng.choice([2000.0, 5000.0, 9000.0]))
        else:
            kind, target = "wind_shift", float(rng.randint(0, 359))
        plan.append((t, kind, target))
        t += rng.uniform(*interval_s)
    return plan


def verify_response(challenges, final_ts):
    """返回每条 challenge 的响应状态。超窗未响应 → SUSPECT。"""
    out = []
    for ch in challenges:
        ok = (ch.replied_at is not None
              and ch.replied_at - ch.issued_at <= RESPONSE_WINDOW_S)
        out.append({"cid": ch.cid, "kind": ch.kind, "ok": ok})
    return out

# 开发态统一轨迹行：所有判决器与测试数据都使用这 11 个字段。
# ts 使用 Python time.time()（服务端权威时间戳，重放时由回放器替换）。
from dataclasses import dataclass, fields


@dataclass
class TrackRow:
    ts: float
    lat: float
    lon: float
    alt_ft: float
    agl_ft: float
    hdg: float
    pitch: float
    roll: float
    vcas_kt: float
    vs_fps: float
    wow: int = 0

    @classmethod
    def fieldnames(cls):
        return [f.name for f in fields(cls)]

    @classmethod
    def from_dict(cls, d):
        vals = []
        for f in fields(cls):
            v = d.get(f.name)
            if v is None and f.name == "wow":
                v = 0
            vals.append(v)
        return cls(*vals)

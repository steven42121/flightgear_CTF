import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.mp import angle_axis_to_euler, quat_to_angle_axis

# 在赤道 (0,0)：欧拉 → 角轴 → 欧拉 应自逆
lat, lon, hdg, pit, rol = 0.0, 0.0, 90.0, 0.0, 0.0
ang, ax, ay, az = quat_to_angle_axis(lat, lon, hdg, pit, rol)
print("angle(deg) =", math.degrees(ang), "axis =", (ax, ay, az))
h2, p2, r2 = angle_axis_to_euler(lat, lon, ax, ay, az, ang)
print("roundtrip  :", h2, p2, r2)

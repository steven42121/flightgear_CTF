import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.rules_loader import load_rules
from server.checkers.flag1 import judge_flag1, _gs_dev_norm
from server.checkers.flag2 import judge_flag2
from tools.verify_all import load_rows

REPO = Path(__file__).resolve().parent.parent
RULES = load_rules(str(REPO / "server" / "rules.yaml"))
rows = load_rows(str(REPO / "build" / "track.csv"))
print("total rows:", len(rows))

r = judge_flag1(rows, RULES["flag1"])
print("flag1:", r)

# 看看 ils 段（walk 之后）的指针分布
f1 = RULES["flag1"]
seg = [x for x in rows[11971:11971 + 4532]]
devs = [_gs_dev_norm(x, f1) for x in seg]
print("ils rows:", len(seg), "min/max dev:", min(devs), max(devs))
import collections
print("dev<0.3 ratio:", sum(1 for d in devs if abs(d) < 0.3) / len(devs))
wows = sum(1 for x in seg if x.wow)
print("wow rows in ils:", wows, "first wow idx:", next((i for i, x in enumerate(seg) if x.wow), None))
print("last row:", seg[-1])

f2 = RULES["flag2"]
tgt = (f2["target_lat"], f2["target_lon"])
ok, ev = judge_flag2(rows, tgt, radius_m=f2["radius_m"], ceil_ft=f2["ceil_ft"],
                     dur_s=f2["dur_s"], max_gap_s=f2["max_gap_s"],
                     move_away_min_m=f2["move_away_min_m"])
print("flag2:", ok, ev)

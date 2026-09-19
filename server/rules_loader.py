"""rules.yaml 加载器（无 PyYAML 依赖的最小子集：两层嵌套 key: value）。"""
import re
from pathlib import Path


def load_rules(path):
    rules = {}
    stack = [(rules, -1)]
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        m = re.match(r"^([A-Za-z0-9_]+):(?:\s+(.*))?$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        while stack and indent <= stack[-1][1]:
            stack.pop()
        parent = stack[-1][0]
        if val is None or val == "":
            d = {}
            parent[key] = d
            stack.append((d, indent))
        else:
            parent[key] = _parse_scalar(val)
    return rules


def _parse_scalar(v):
    v = v.split("#", 1)[0].strip()
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v

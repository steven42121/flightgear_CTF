"""L0 启动参数白名单校验。

验证 fgfs 启动参数是否包含禁止项，拒绝危险 FDM 类型。
设计参考 UltimateAntiCheat 的 Process::ValidateCommandLine 思路。
"""
import re
import sys
from typing import List, Tuple


# 禁止的启动参数模式
BANNED_PATTERNS = [
    r'--fdm=(ufo|magic|null|external)',  # 危险 FDM 类型
    r'--native-fdm=',                     # 外部 FDM 服务器
    r'--load-tape',                       # 自动回放
    r'--prop:/sim/fdm/',                  # FDM 属性覆盖
    r'--prop:/position/',                 # 位置覆盖
    r'--prop:/velocities/',               # 速度覆盖
    r'--prop:/orientation/',              # 姿态覆盖
    r'--telnet=',                         # 远程调试端口
]

# 必须存在的参数
REQUIRED_PATTERNS = [
    r'--addon=',   # 必须加载 CTF addon
    r'--multiplay=', # 必须使用连飞
]


def validate_args(args: List[str]) -> Tuple[bool, List[str]]:
    """校验启动参数。返回 (valid, issues)。"""
    issues = []
    
    for arg in args:
        # 检查禁止模式
        for pattern in BANNED_PATTERNS:
            if re.search(pattern, arg, re.IGNORECASE):
                issues.append(f"禁止参数: {arg}")
        
        # 检查 telnet 端口（如果有的话应该被禁止）
        if '--telnet=' in arg:
            issues.append(f"远程调试端口: {arg}")
    
    # 检查必需参数
    args_str = ' '.join(args)
    for pattern in REQUIRED_PATTERNS:
        if not re.search(pattern, args_str):
            issues.append(f"缺少必需参数，匹配: {pattern}")
    
    return len(issues) == 0, issues


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        (["--aircraft=c172p", "--addon=./ctf-addon", "--multiplay=out,10,127.0.0.1,5000"], True),
        (["--aircraft=c172p", "--fdm=external"], False),
        (["--aircraft=c172p", "--native-fdm=socket,in,30,,5500,udp"], False),
        (["--aircraft=c172p", "--load-tape=test"], False),
        (["--aircraft=c172p", "--telnet=5401"], False),
    ]
    
    for args, expected in test_cases:
        valid, issues = validate_args(args)
        status = "PASS" if valid == expected else "FAIL"
        print(f"[{status}] args={args} valid={valid} issues={issues}")

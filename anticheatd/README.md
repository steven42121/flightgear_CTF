# MAYDAY CTF Anti-Cheat Daemon (C++)

基于 VMAware + UltimateAntiCheat 设计的 FlightGear CTF 反作弊守护进程。

## 架构

分层防护（L0-L5）：
- **L0**: 启动参数白名单校验
- **L1**: env.lock 环境哈希校验
- **L2**: 属性树写入审计
- **L3**: FDM 源可信度追踪
- **L4**: 进程完整性检查
- **L5**: 1Hz HMAC 心跳票据链

## 编译要求

- C++17 编译器（MSVC 19.30+ / GCC 11+ / Clang 14+）
- CMake 3.16+
- Windows: Visual Studio 2022/2026
- Linux: gcc/g++ with libssl-dev, libz-dev

## 构建步骤

```bash
cd anticheatd
mkdir build && cd build

# Windows (VS 2026)
cmake .. -G "Visual Studio 18 2026" -A x64
cmake --build . --config Release

# Linux
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

## 用法

```bash
# 自检模式
./bin/anticheatd --mode selfcheck

# 验证启动参数
./bin/anticheatd --mode check -- --aircraft=c172p --addon=./ctf-addon --multiplay=out,10,127.0.0.1,5000

# 创建会话
./bin/anticheatd --mode session --userid TEAM01

# 守护进程模式
./bin/anticheatd --mode daemon --userid TEAM01
```

## 配置

```json
{
  "fg_root": "C:/Users/steven/FlightGear/Downloads/fgdata_2024_1",
  "fg_bin_dir": "C:/Program Files/FlightGear 2024.1/bin",
  "scenery_dir": "C:/Users/steven/FlightGear/Downloads/TerraSync",
  "lock_file": "./env.lock",
  "server_ip": "127.0.0.1",
  "server_port": 5000,
  "telnet_host": "127.0.0.1",
  "telnet_port": 5401
}
```

## 开源引用

- **VMAware** (MIT): VM 检测技术
  - https://github.com/NotRequiem/VMAware
- **UltimateAntiCheat** (AGPL): 用户态反作弊架构
  - https://github.com/AlSch092/UltimateAntiCheat

本项目代码为原创实现，参考上述项目的设计思路。

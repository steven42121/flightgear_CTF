"""生成 anticheatd C++ 密钥碎片。

用法：
    python -m tools.gen_key_fragments server/hb_secret.key

输出：hb_secret.cpp 中的 fragments[] 数组内容（复制到 anticheatd/src/hb_secret.cpp）

原理：
    密钥 K 为 32 字节随机数。
    将 K 分成 8 个 uint32_t（小端），每段与编译期常量 XOR。
    fragments[i] = K_dword[i] XOR xor_consts[i]

    二进制中不出现 K 的明文。选手需逆向 anticheatd 才能提取。
"""
import os
import sys
import struct

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

XOR_CONSTS = [
    0xDEADBEEF, 0xCAFEBABE, 0x8BADF00D, 0xBAADF00D,
    0xFEEDFACE, 0xC0FFEEEE, 0xB16B00B5, 0xDEFEC8ED
]


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m tools.gen_key_fragments <key_file>")
        print(f"  key_file: 32-byte raw binary key (e.g., server/hb_secret.key)")
        sys.exit(1)

    key_path = sys.argv[1]
    if not os.path.exists(key_path):
        print(f"ERROR: Key file not found: {key_path}")
        print(f"  Generate a key first:")
        print(f"    python -c \"import os; open('{key_path}','wb').write(os.urandom(32))\"")
        sys.exit(1)

    with open(key_path, "rb") as f:
        key = f.read()

    if len(key) != 32:
        print(f"ERROR: Key must be 32 bytes, got {len(key)}")
        sys.exit(1)

    dwords = struct.unpack("<8I", key)

    print("// ═══════════════════════════════════════════════════════")
    print("// Generated fragments — copy into anticheatd/src/hb_secret.cpp")
    print(f"// Source: {key_path}")
    print("// ═══════════════════════════════════════════════════════")
    print()
    print("ObfuscatedKey::ObfuscatedKey() {")
    for i, (dw, xc) in enumerate(zip(dwords, XOR_CONSTS)):
        fragment = dw ^ xc
        print(f"    fragments[{i}] = 0x{fragment:08X};  "
              f"// 0x{dw:08X} ^ 0x{xc:08X}")
    print("}")

    print()
    print("// Key hex (for verification, DO NOT include in source):")
    print(f"// {key.hex()}")


if __name__ == "__main__":
    main()
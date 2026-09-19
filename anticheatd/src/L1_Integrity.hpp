#pragma once
#include <string>
#include <unordered_map>
#include <vector>

/**
 * L1: 核心游戏文件完整性校验 (env.lock)。
 *
 * 仅校验 FG 主要二进制文件（fgfs.exe 等），不校验：
 *   - aircraft/set.xml（允许选手自定义飞机）
 *   - scenery 地景文件（允许选手使用自己的地景）
 *
 * env.lock 格式：
 * {
 *   "fg_version": "2024.1.7",
 *   "fg_binaries": {"fgfs.exe": "<sha256>", "osgDB\*.dll": "<sha256>", ...}
 * }
 */

class L1_Integrity {
public:
    struct CheckResult {
        bool passed;
        std::string layer;   // "L1"
        std::string detail;
        std::vector<std::string> issues;
    };

    explicit L1_Integrity(const std::string& lock_file_path);
    CheckResult verify(const std::string& fg_root,
                       const std::string& fg_bin_dir,
                       const std::string& scenery_dir) const;

private:
    std::string compute_file_hash(const std::string& filepath) const;
    bool load_lock(const std::string& path);

    std::string fg_version_;
    std::unordered_map<std::string, std::string> expected_hashes_;
    bool lock_loaded_ = false;
};
#pragma once
#include <string>
#include <vector>
#include <unordered_map>

/**
 * L0: Startup argument whitelist validation.
 *
 * Blocked patterns:
 *   --fdm=ufo|magic|null|external    → 非物理 FDM
 *   --native-fdm=                     → 外部 FDM 服务器
 *   --load-tape                       → 自动回放
 *   --telnet=                         → 远程调试端口
 *   --prop:/sim/fdm/                  → FDM 属性覆盖
 *   --prop:/position/                 → 位置覆盖
 *   --prop:/velocities/               → 速度覆盖
 *   --prop:/orientation/              → 姿态覆盖
 *
 * Required:
 *   --addon=    (CTF addon 必须加载)
 *   --multiplay= (连飞必须启用)
 */

class L0_ArgValidation {
public:
    struct ValidationResult {
        bool valid;
        std::vector<std::string> issues;
    };

    ValidationResult validate(const std::vector<std::string>& args) const;

private:
    // Forbidden argument patterns
    static const std::vector<std::string> banned_patterns_;
    // Required argument patterns
    static const std::vector<std::string> required_patterns_;

    bool contains_pattern(const std::string& arg_str,
                          const std::string& pattern) const;
};

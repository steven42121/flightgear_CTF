#include "L0_ArgValidation.hpp"
#include <algorithm>
#include <iostream>

const std::vector<std::string> L0_ArgValidation::banned_patterns_ = {
    "--fdm=ufo", "--fdm=magic", "--fdm=null", "--fdm=external",
    "--native-fdm=",
    "--load-tape",
    "--telnet=",
    "--prop:/sim/fdm/",
    "--prop:/position/",
    "--prop:/velocities/",
    "--prop:/orientation/",
    "--prop:/environment/",
};

const std::vector<std::string> L0_ArgValidation::required_patterns_ = {
    "--addon=",
    "--multiplay=",
};

bool L0_ArgValidation::contains_pattern(const std::string& text, 
                                         const std::string& pattern) const {
    return text.find(pattern) != std::string::npos;
}

L0_ArgValidation::ValidationResult L0_ArgValidation::validate(
    const std::vector<std::string>& args) const {
    
    ValidationResult result;
    std::string args_str;
    for (const auto& arg : args) {
        args_str += arg + " ";
    }
    
    // Check banned patterns
    for (const auto& pattern : banned_patterns_) {
        if (contains_pattern(args_str, pattern)) {
            result.issues.push_back("Banned argument: " + pattern);
        }
    }
    
    // Check required patterns
    for (const auto& pattern : required_patterns_) {
        if (!contains_pattern(args_str, pattern)) {
            result.issues.push_back("Missing required argument: " + pattern);
        }
    }
    
    result.valid = result.issues.empty();
    return result;
}

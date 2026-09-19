#pragma once
#include <string>
#include <vector>

class L4_ProcessIntegrity {
public:
    struct Result {
        bool passed = true;
        std::string detail;
        std::vector<std::string> issues;
    };
    
    Result check() const;
private:
    std::vector<std::string> scan_injections() const;
};

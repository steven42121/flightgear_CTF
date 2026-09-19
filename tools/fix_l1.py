# -*- coding: utf-8 -*-
content = r'''#include "L1_Integrity.hpp"
#include "Logger.hpp"
#include "common.hpp"
#include <fstream>
#include <sstream>
#include <filesystem>
#include <algorithm>

namespace fs = std::filesystem;

L1_Integrity::L1_Integrity(const std::string& lock_file_path) {
    load_lock(lock_file_path);
}

bool L1_Integrity::load_lock(const std::string& path) {
    std::ifstream file(path);
    if (!file) {
        Logger::warn("env.lock not found: " + path);
        return false;
    }
    
    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string content = buffer.str();
    
    // Parse fg_version
    size_t pos = content.find("\"fg_version\"");
    if (pos != std::string::npos) {
        pos = content.find(':', pos);
        pos = content.find('"', pos);
        if (pos != std::string::npos) {
            size_t end = content.find('"', pos + 1);
            fg_version_ = content.substr(pos + 1, end - pos - 1);
        }
    }
    
    // Parse fg_binaries hashes
    pos = content.find("\"fg_binaries\"");
    if (pos != std::string::npos) {
        pos = content.find('{', pos);
        size_t end = content.find('}', pos);
        std::string block = content.substr(pos + 1, end - pos - 1);
        
        size_t quote_pos = 0;
        while ((quote_pos = block.find('"', quote_pos)) != std::string::npos) {
            size_t key_end = block.find('"', quote_pos + 1);
            if (key_end == std::string::npos) break;
            std::string key = block.substr(quote_pos + 1, key_end - quote_pos - 1);
            
            size_t colon = block.find(':', key_end);
            if (colon == std::string::npos) break;
            colon = block.find('"', colon);
            if (colon == std::string::npos) break;
            size_t val_end = block.find('"', colon + 1);
            if (val_end == std::string::npos) break;
            std::string value = block.substr(colon + 1, val_end - colon - 1);
            
            expected_hashes_[key] = value;
            quote_pos = val_end + 1;
        }
    }
    
    Logger::info("Loaded env.lock: " + fg_version_ + 
                 ", " + std::to_string(expected_hashes_.size()) + " hashes");
    return true;
}

std::string L1_Integrity::compute_file_hash(const std::string& filepath) const {
    std::ifstream file(filepath, std::ios::binary);
    if (!file) return "";
    std::stringstream buffer;
    buffer << file.rdbuf();
    return ::sha256(buffer.str());
}

L1_Integrity::CheckResult L1_Integrity::verify(const std::string& fg_root,
                                               const std::string& fg_bin_dir,
                                               const std::string& scenery_dir) const {
    CheckResult result;
    result.passed = true;
    
    if (expected_hashes_.empty()) {
        result.detail = "No hashes in env.lock (quick mode)";
        return result;
    }
    
    for (const auto& [filename, expected_hash] : expected_hashes_) {
        std::string filepath = fg_bin_dir + "/" + filename;
        if (!fs::exists(filepath)) {
            result.issues.push_back("Missing: " + filename);
            result.passed = false;
            continue;
        }
        
        std::string actual_hash = compute_file_hash(filepath);
        if (actual_hash != expected_hash) {
            result.issues.push_back("Hash mismatch: " + filename);
            result.passed = false;
        }
    }
    
    result.detail = result.passed ? "All hashes verified" : 
                              std::to_string(result.issues.size()) + " issues found";
    return result;
}
'''

with open(r'c:\Users\steven\Documents\HW\gkp2026\出题\flightgear-ctf\anticheatd\src\L1_Integrity.cpp', 'w', encoding='utf-8') as f:
    f.write(content)
print('L1_Integrity.cpp rewritten OK')

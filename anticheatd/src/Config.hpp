#pragma once
#include <string>
#include <unordered_map>

/**
 * Configuration loader for anticheatd.
 */
class Config {
public:
    // Paths
    std::string config_path;
    std::string fg_root;
    std::string fg_bin_dir;
    std::string scenery_dir;
    std::string lock_file;
    
    // Network
    std::string server_ip = "127.0.0.1";
    int server_port = 5000;
    
    // Telnet
    std::string telnet_host = "127.0.0.1";
    int telnet_port = 5401;
    
    // Flags
    bool enable_logging = true;
    std::string log_file = "anticheatd.log";
    
    // Load from JSON config file
    bool load(const std::string& path);
    
    // Save to JSON config file
    bool save(const std::string& path) const;
    
private:
    // Simple JSON parsing (no external dependency)
    std::string read_file(const std::string& path) const;
    std::string get_json_string(const std::string& json, const std::string& key) const;
    int get_json_int(const std::string& json, const std::string& key, int default_val = 0) const;
    bool get_json_bool(const std::string& json, const std::string& key, bool default_val = false) const;
};
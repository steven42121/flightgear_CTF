#include "Config.hpp"
#include <fstream>
#include <sstream>
#include <algorithm>
#include <iostream>

bool Config::load(const std::string& path) {
    std::string content = read_file(path);
    if (content.empty()) return false;
    
    fg_root = get_json_string(content, "fg_root");
    fg_bin_dir = get_json_string(content, "fg_bin_dir");
    scenery_dir = get_json_string(content, "scenery_dir");
    lock_file = get_json_string(content, "lock_file");
    server_ip = get_json_string(content, "server_ip");
    server_port = get_json_int(content, "server_port", 5000);
    telnet_host = get_json_string(content, "telnet_host");
    telnet_port = get_json_int(content, "telnet_port", 5401);
    enable_logging = get_json_bool(content, "enable_logging", true);
    log_file = get_json_string(content, "log_file");
    
    return true;
}

bool Config::save(const std::string& path) const {
    std::ofstream out(path);
    if (!out) return false;
    
    out << "{\n";
    out << "  \"fg_root\": \"" << fg_root << "\",\n";
    out << "  \"fg_bin_dir\": \"" << fg_bin_dir << "\",\n";
    out << "  \"scenery_dir\": \"" << scenery_dir << "\",\n";
    out << "  \"lock_file\": \"" << lock_file << "\",\n";
    out << "  \"server_ip\": \"" << server_ip << "\",\n";
    out << "  \"server_port\": " << server_port << ",\n";
    out << "  \"telnet_host\": \"" << telnet_host << "\",\n";
    out << "  \"telnet_port\": " << telnet_port << ",\n";
    out << "  \"enable_logging\": " << (enable_logging ? "true" : "false") << ",\n";
    out << "  \"log_file\": \"" << log_file << "\"\n";
    out << "}\n";
    
    return out.good();
}

std::string Config::read_file(const std::string& path) const {
    std::ifstream in(path);
    if (!in) return "";
    std::stringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

std::string Config::get_json_string(const std::string& json, const std::string& key) const {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return "";
    
    pos = json.find(':', pos + search.size());
    if (pos == std::string::npos) return "";
    
    // Skip whitespace
    while (pos < json.size() && std::isspace(json[pos])) ++pos;
    
    // Find opening quote
    pos = json.find('"', pos);
    if (pos == std::string::npos) return "";
    ++pos;
    
    // Find closing quote
    size_t end = json.find('"', pos);
    if (end == std::string::npos) return "";
    
    return json.substr(pos, end - pos);
}

int Config::get_json_int(const std::string& json, const std::string& key, int default_val) const {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return default_val;
    
    pos = json.find(':', pos + search.size());
    if (pos == std::string::npos) return default_val;
    
    ++pos;
    while (pos < json.size() && std::isspace(json[pos])) ++pos;
    
    // Read number
    std::string num_str;
    while (pos < json.size() && (std::isdigit(json[pos]) || json[pos] == '-')) {
        num_str += json[pos++];
    }
    
    if (num_str.empty()) return default_val;
    try {
        return std::stoi(num_str);
    } catch (...) {
        return default_val;
    }
}

bool Config::get_json_bool(const std::string& json, const std::string& key, bool default_val) const {
    std::string search = "\"" + key + "\"";
    size_t pos = json.find(search);
    if (pos == std::string::npos) return default_val;
    
    pos = json.find(':', pos + search.size());
    if (pos == std::string::npos) return default_val;
    
    // Check for true/false
    return json.find("true", pos) < json.find(",", pos) && 
           json.find("true", pos) < json.find("}", pos);
}

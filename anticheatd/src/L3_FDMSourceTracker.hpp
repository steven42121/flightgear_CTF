#pragma once
#include <string>
#include <unordered_map>

class L3_FDMSourceTracker {
public:
    void register_session(const std::string& sid, const std::string& source, 
                          const std::string& addr);
    bool is_trusted(const std::string& sid) const;
    void mark_anomaly(const std::string& sid, const std::string& anomaly);
private:
    std::unordered_map<std::string, bool> sessions_;
};

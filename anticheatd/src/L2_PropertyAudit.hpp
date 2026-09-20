#pragma once
#include <string>
#include <vector>

class L2_PropertyAudit {
public:
    L2_PropertyAudit(const std::string& host, int port);
    bool check_property(const std::string& prop);
    std::string read_property(const std::string& prop);
    int alarm_count() const { return alarms_; }
private:
    std::string telnet_get(const std::string& query);
    std::string host_;
    int port_;
    int alarms_ = 0;
};
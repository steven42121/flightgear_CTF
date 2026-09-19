#include "L3_FDMSourceTracker.hpp"

void L3_FDMSourceTracker::register_session(const std::string& sid, 
                                           const std::string& source,
                                           const std::string& addr) {
    (void)addr;
    sessions_[sid] = (source == "mp" || source == "fdm");
}

bool L3_FDMSourceTracker::is_trusted(const std::string& sid) const {
    auto it = sessions_.find(sid);
    return it != sessions_.end() && it->second;
}

void L3_FDMSourceTracker::mark_anomaly(const std::string& sid, 
                                       const std::string& anomaly) {
    (void)anomaly;
    sessions_[sid] = false;
}
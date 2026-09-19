#pragma once
#include <string>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <cctype>

/**
 * Simple logger.
 */
class Logger {
public:
    enum Level { INFO, WARNING, ERROR_LEVEL, DEBUG };
    
    static void set_level(Level level);
    static void log(Level level, const std::string& message);
    static void info(const std::string& message);
    static void warn(const std::string& message);
    static void error(const std::string& message);
    static void debug(const std::string& message);
    
    static void set_log_file(const std::string& path);
    
private:
    static Level current_level_;
    static std::ofstream log_file_;
    static std::string level_to_string(Level level);
};

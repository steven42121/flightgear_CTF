#ifdef _WIN32
#define _CRT_SECURE_NO_WARNINGS
#endif

#include "Logger.hpp"
#include <iostream>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <sstream>

Logger::Level Logger::current_level_ = Logger::INFO;
std::ofstream Logger::log_file_;

void Logger::set_level(Level level) {
    current_level_ = level;
}

void Logger::set_log_file(const std::string& path) {
    if (log_file_.is_open()) {
        log_file_.close();
    }
    log_file_.open(path, std::ios::app);
}

void Logger::log(Level level, const std::string& message) {
    if (level < current_level_) return;
    
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    
    std::stringstream ss;
    ss << std::put_time(std::localtime(&time_t), "%Y-%m-%d %H:%M:%S");
    ss << "." << std::setfill('0') << std::setw(3) << ms.count();
    ss << " [" << level_to_string(level) << "] " << message;
    
    std::string line = ss.str();
    
    // In JSON mode (when output starts with '{'), write to stderr to avoid corrupting JSON
    // This is detected by checking if the line starts with a timestamp (warning/error) vs JSON
    if (line[0] == '2') {
        // Log line (starts with timestamp) - always go to stderr to preserve JSON
        std::cerr << line << std::endl;
    } else {
        std::cout << line << std::endl;
    }
    
    if (log_file_.is_open()) {
        log_file_ << line << std::endl;
    }
}

void Logger::info(const std::string& message) { log(INFO, message); }
void Logger::warn(const std::string& message) { log(WARNING, message); }
void Logger::error(const std::string& message) { log(ERROR_LEVEL, message); }
void Logger::debug(const std::string& message) { log(DEBUG, message); }

std::string Logger::level_to_string(Level level) {
    switch (level) {
        case INFO: return "INFO";
        case WARNING: return "WARN";
        case ERROR_LEVEL: return "ERROR";
        case DEBUG: return "DEBUG";
        default: return "UNKNOWN";
    }
}

#include "L2_PropertyAudit.hpp"
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cstring>

L2_PropertyAudit::L2_PropertyAudit(const std::string& host, int port)
    : host_(host), port_(port) {}

bool L2_PropertyAudit::check_property(const std::string& prop) {
    // Connect to FG telnet and query property
    int sock = socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return false;
    
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port_);
    inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);
    
    if (connect(sock, (sockaddr*)&addr, sizeof(addr)) < 0) {
        close(sock);
        return false;
    }
    
    std::string query = "get " + prop + "\r\n";
    send(sock, query.c_str(), query.size(), 0);
    
    // Read response (simplified)
    char buf[1024];
    ssize_t n = recv(sock, buf, sizeof(buf), 0);
    close(sock);
    
    return n > 0;
}

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#endif

#include "L2_PropertyAudit.hpp"
#include "Logger.hpp"
#include <cstring>
#include <string>

#ifdef _WIN32
static bool wsa_initialized = false;
static void init_wsa() {
    if (!wsa_initialized) {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
        wsa_initialized = true;
    }
}
#define CLOSE_SOCKET(s) closesocket(s)
#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#define CLOSE_SOCKET(s) close(s)
#endif

L2_PropertyAudit::L2_PropertyAudit(const std::string& host, int port)
    : host_(host), port_(port) {}

bool L2_PropertyAudit::check_property(const std::string& prop) {
#ifdef _WIN32
    init_wsa();
#endif

    int sock = (int)socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return false;

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port_);
    inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);

    if (connect(sock, (sockaddr*)&addr, sizeof(addr)) < 0) {
        CLOSE_SOCKET(sock);
        return false;
    }

    std::string query = "get " + prop + "\r\n";
    send(sock, query.c_str(), (int)query.size(), 0);

    char buf[1024];
    int n = recv(sock, buf, sizeof(buf), 0);
    CLOSE_SOCKET(sock);

    return n > 0;
}
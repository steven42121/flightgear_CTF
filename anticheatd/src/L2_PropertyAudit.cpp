﻿#ifdef _WIN32
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

std::string L2_PropertyAudit::telnet_get(const std::string& query) {
#ifdef _WIN32
    init_wsa();
#endif

    int sock = (int)socket(AF_INET, SOCK_STREAM, 0);
    if (sock < 0) return "";

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons((u_short)port_);
    inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);

    if (connect(sock, (sockaddr*)&addr, sizeof(addr)) < 0) {
        CLOSE_SOCKET(sock);
        return "";
    }

    std::string full_query = query + "\r\n";
    send(sock, full_query.c_str(), (int)full_query.size(), 0);

    char buf[4096];
    int n = recv(sock, buf, sizeof(buf) - 1, 0);
    CLOSE_SOCKET(sock);

    if (n <= 0) return "";
    buf[n] = '\0';
    return std::string(buf);
}

bool L2_PropertyAudit::check_property(const std::string& prop) {
    std::string resp = telnet_get("get " + prop);
    return !resp.empty();
}

std::string L2_PropertyAudit::read_property(const std::string& prop) {
    std::string resp = telnet_get("get " + prop);
    if (resp.empty()) return "";

    // FG telnet returns format like: "/prop = 'value' (type)"
    // Strip the property name prefix and quotes
    size_t eq = resp.find('=');
    if (eq == std::string::npos) return "";

    std::string tail = resp.substr(eq + 1);
    // Strip leading spaces
    while (!tail.empty() && tail.front() == ' ') tail.erase(0, 1);

    // Extract quoted value
    if (!tail.empty() && tail.front() == '\'') {
        tail.erase(0, 1);
        size_t endq = tail.find('\'');
        if (endq != std::string::npos) {
            return tail.substr(0, endq);
        }
    }

    // No quotes — return first token
    size_t sp = tail.find(' ');
    if (sp != std::string::npos) return tail.substr(0, sp);
    return tail;
}
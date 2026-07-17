#pragma once
// =============================================================================
//  CycloneX — agent/src/http_server.h
//  HTTP/1.1 + WebSocket server minimal usando Winsock2 (sem dependências).
//  Suporta: GET/POST, serve arquivos, WebSocket upgrade, broadcast.
// =============================================================================

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "Ws2_32.lib")

#include <string>
#include <vector>
#include <map>
#include <functional>
#include <thread>
#include <mutex>
#include <atomic>
#include <sstream>
#include <fstream>
#include <algorithm>
#include <memory>
#include <cstring>
#include <cstdint>
#include <iostream>

namespace cyclone {

// ── HTTP Request / Response ───────────────────────────────────────────────────
struct HttpRequest {
    std::string method;
    std::string path;
    std::string body;
    std::map<std::string, std::string> headers;
    std::map<std::string, std::string> params; // query string
};

struct HttpResponse {
    int status = 200;
    std::string content_type = "application/json";
    std::string body;
    std::map<std::string, std::string> headers;

    static HttpResponse json(const std::string& j) {
        HttpResponse r; r.body = j; r.content_type = "application/json"; return r;
    }
    static HttpResponse text(const std::string& t) {
        HttpResponse r; r.body = t; r.content_type = "text/plain"; return r;
    }
    static HttpResponse html(const std::string& h) {
        HttpResponse r; r.body = h; r.content_type = "text/html; charset=utf-8"; return r;
    }
    static HttpResponse err(int code, const std::string& msg) {
        HttpResponse r; r.status = code; r.body = "{\"error\":\"" + msg + "\"}"; return r;
    }
};

using RouteHandler = std::function<HttpResponse(const HttpRequest&)>;

// ── WebSocket Client ──────────────────────────────────────────────────────────
struct WsClient {
    SOCKET sock;
    std::string id;
    std::mutex send_mtx;
    bool alive = true;
};

// ── Base64 encode (for WebSocket handshake) ───────────────────────────────────
static const char b64_chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static std::string base64_encode(const unsigned char* data, size_t len) {
    std::string out;
    for (size_t i = 0; i < len; i += 3) {
        uint32_t b = (uint32_t)data[i] << 16;
        if (i+1 < len) b |= (uint32_t)data[i+1] << 8;
        if (i+2 < len) b |= data[i+2];
        out += b64_chars[(b>>18)&63];
        out += b64_chars[(b>>12)&63];
        out += (i+1<len) ? b64_chars[(b>>6)&63] : '=';
        out += (i+2<len) ? b64_chars[b&63]       : '=';
    }
    return out;
}

// ── SHA1 for WebSocket handshake ──────────────────────────────────────────────
static void sha1(const uint8_t* data, size_t len, uint8_t out[20]) {
    uint32_t h[5] = {0x67452301,0xEFCDAB89,0x98BADCFE,0x10325476,0xC3D2E1F0};
    auto lrot = [](uint32_t v, int n){ return (v<<n)|(v>>(32-n)); };

    std::vector<uint8_t> msg(data, data+len);
    msg.push_back(0x80);
    while (msg.size() % 64 != 56) msg.push_back(0);
    uint64_t bits = (uint64_t)len * 8;
    for (int i=7;i>=0;i--) msg.push_back((bits>>(i*8))&0xFF);

    for (size_t off=0; off<msg.size(); off+=64) {
        uint32_t w[80];
        for (int i=0;i<16;i++) {
            w[i]  = (uint32_t)msg[off+i*4+0]<<24;
            w[i] |= (uint32_t)msg[off+i*4+1]<<16;
            w[i] |= (uint32_t)msg[off+i*4+2]<<8;
            w[i] |= (uint32_t)msg[off+i*4+3];
        }
        for (int i=16;i<80;i++) w[i]=lrot(w[i-3]^w[i-8]^w[i-14]^w[i-16],1);
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4];
        for (int i=0;i<80;i++){
            uint32_t f,k;
            if (i<20){f=(b&c)|((~b)&d);k=0x5A827999;}
            else if (i<40){f=b^c^d;k=0x6ED9EBA1;}
            else if (i<60){f=(b&c)|(b&d)|(c&d);k=0x8F1BBCDC;}
            else{f=b^c^d;k=0xCA62C1D6;}
            uint32_t t=lrot(a,5)+f+e+k+w[i];
            e=d;d=c;c=lrot(b,30);b=a;a=t;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;
    }
    for (int i=0;i<5;i++){
        out[i*4+0]=(h[i]>>24)&0xFF; out[i*4+1]=(h[i]>>16)&0xFF;
        out[i*4+2]=(h[i]>> 8)&0xFF; out[i*4+3]=h[i]&0xFF;
    }
}

// ── HTTP Server ───────────────────────────────────────────────────────────────
class HttpServer {
public:
    std::map<std::string, std::map<std::string, RouteHandler>> routes_; // method → path → handler
    std::string static_dir_;   // serve static files from here
    std::string static_prefix_;

    std::vector<std::shared_ptr<WsClient>> ws_clients_;
    std::mutex ws_mutex_;
    std::function<void(std::shared_ptr<WsClient>, const std::string&)> ws_handler_;

    SOCKET listen_sock_ = INVALID_SOCKET;
    std::atomic<bool> running_{false};
    int port_ = 8080;

    HttpServer() {
        WSADATA wd;
        WSAStartup(MAKEWORD(2,2), &wd);
    }
    ~HttpServer() {
        stop();
        WSACleanup();
    }

    void get(const std::string& path, RouteHandler h)  { routes_["GET"][path]  = h; }
    void post(const std::string& path, RouteHandler h) { routes_["POST"][path] = h; }
    void del(const std::string& path, RouteHandler h)  { routes_["DELETE"][path] = h; }

    void serve_static(const std::string& url_prefix, const std::string& dir) {
        static_prefix_ = url_prefix; static_dir_ = dir;
    }

    void on_websocket(std::function<void(std::shared_ptr<WsClient>, const std::string&)> h) {
        ws_handler_ = h;
    }

    // Broadcast JSON string to all connected WS clients
    void ws_broadcast(const std::string& json) {
        std::vector<std::shared_ptr<WsClient>> dead;
        std::lock_guard<std::mutex> lk(ws_mutex_);
        for (auto& c : ws_clients_) {
            if (!c->alive) { dead.push_back(c); continue; }
            if (!ws_send_text(*c, json)) { c->alive = false; dead.push_back(c); }
        }
        for (auto& d : dead) ws_clients_.erase(std::remove(ws_clients_.begin(), ws_clients_.end(), d), ws_clients_.end());
    }

    void ws_send_client(std::shared_ptr<WsClient> c, const std::string& json) {
        std::lock_guard<std::mutex> lk(c->send_mtx);
        ws_send_text(*c, json);
    }

    bool start(int port) {
        port_ = port;
        listen_sock_ = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (listen_sock_ == INVALID_SOCKET) return false;

        int opt = 1;
        setsockopt(listen_sock_, SOL_SOCKET, SO_REUSEADDR, (char*)&opt, sizeof(opt));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = INADDR_ANY;
        addr.sin_port = htons((u_short)port);

        if (bind(listen_sock_, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR) {
            closesocket(listen_sock_); return false;
        }
        if (listen(listen_sock_, SOMAXCONN) == SOCKET_ERROR) {
            closesocket(listen_sock_); return false;
        }

        running_ = true;
        std::thread([this]{ accept_loop(); }).detach();
        return true;
    }

    void stop() {
        running_ = false;
        if (listen_sock_ != INVALID_SOCKET) { closesocket(listen_sock_); listen_sock_ = INVALID_SOCKET; }
    }

private:
    void accept_loop() {
        while (running_) {
            sockaddr_in client_addr{};
            int addr_len = sizeof(client_addr);
            SOCKET client = accept(listen_sock_, (sockaddr*)&client_addr, &addr_len);
            if (client == INVALID_SOCKET) continue;
            std::thread([this, client]{ handle_client(client); }).detach();
        }
    }

    void handle_client(SOCKET sock) {
        // Set recv timeout
        DWORD timeout = 10000;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));

        std::string raw;
        char buf[4096];
        while (true) {
            int n = recv(sock, buf, sizeof(buf)-1, 0);
            if (n <= 0) break;
            buf[n] = 0;
            raw.append(buf, n);
            if (raw.find("\r\n\r\n") != std::string::npos) break;
        }
        if (raw.empty()) { closesocket(sock); return; }

        HttpRequest req = parse_request(raw);

        // Check for WebSocket upgrade
        auto it = req.headers.find("upgrade");
        if (it != req.headers.end() && it->second == "websocket") {
            handle_websocket(sock, req);
            return;
        }

        // Read body if Content-Length present
        auto cl = req.headers.find("content-length");
        if (cl != req.headers.end()) {
            int content_len = std::stoi(cl->second);
            size_t header_end = raw.find("\r\n\r\n") + 4;
            int already = (int)raw.size() - (int)header_end;
            req.body = raw.substr(header_end);
            while ((int)req.body.size() < content_len) {
                int n = recv(sock, buf, (int)std::min((size_t)sizeof(buf)-1, (size_t)(content_len - req.body.size())), 0);
                if (n <= 0) break;
                buf[n] = 0; req.body.append(buf, n);
            }
        }

        HttpResponse resp = dispatch(req);
        send_response(sock, resp);
        closesocket(sock);
    }

    HttpRequest parse_request(const std::string& raw) {
        HttpRequest req;
        std::istringstream ss(raw);
        std::string line;
        // First line: METHOD PATH HTTP/1.x
        std::getline(ss, line);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        {
            std::istringstream ls(line);
            ls >> req.method >> req.path;
        }
        // Parse query string
        auto q = req.path.find('?');
        if (q != std::string::npos) {
            std::string qs = req.path.substr(q+1);
            req.path = req.path.substr(0, q);
            std::istringstream qss(qs);
            std::string tok;
            while (std::getline(qss, tok, '&')) {
                auto eq = tok.find('=');
                if (eq != std::string::npos) req.params[tok.substr(0,eq)] = tok.substr(eq+1);
            }
        }
        // Headers
        while (std::getline(ss, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) break;
            auto col = line.find(':');
            if (col != std::string::npos) {
                std::string key = line.substr(0, col);
                std::string val = line.substr(col+2);
                std::transform(key.begin(), key.end(), key.begin(), ::tolower);
                req.headers[key] = val;
            }
        }
        return req;
    }

    HttpResponse dispatch(const HttpRequest& req) {
        // CORS preflight
        if (req.method == "OPTIONS") {
            HttpResponse r; r.status = 204;
            r.headers["Access-Control-Allow-Origin"]  = "*";
            r.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS";
            r.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization";
            return r;
        }

        // Route match
        auto mit = routes_.find(req.method);
        if (mit != routes_.end()) {
            // Exact match
            auto rit = mit->second.find(req.path);
            if (rit != mit->second.end()) {
                auto resp = rit->second(req);
                resp.headers["Access-Control-Allow-Origin"] = "*";
                return resp;
            }
            // Prefix match (e.g. /api/job/123)
            for (auto& [pattern, handler] : mit->second) {
                if (!pattern.empty() && pattern.back() == '*') {
                    std::string prefix = pattern.substr(0, pattern.size()-1);
                    if (req.path.substr(0, prefix.size()) == prefix) {
                        auto resp = handler(req);
                        resp.headers["Access-Control-Allow-Origin"] = "*";
                        return resp;
                    }
                }
            }
        }

        // Serve index.html for /
        if (req.path == "/" && !static_dir_.empty()) {
            return serve_file(static_dir_ + "/index.html");
        }

        // Static files
        if (!static_dir_.empty() && !static_prefix_.empty()) {
            if (req.path.substr(0, static_prefix_.size()) == static_prefix_) {
                std::string file_path = static_dir_ + req.path.substr(static_prefix_.size());
                return serve_file(file_path);
            }
        }

        return HttpResponse::err(404, "Not found");
    }

    HttpResponse serve_file(const std::string& path) {
        std::ifstream f(path, std::ios::binary);
        if (!f) return HttpResponse::err(404, "File not found");
        std::string content((std::istreambuf_iterator<char>(f)), {});
        HttpResponse r;
        r.body = content;
        // Detect content type
        if (path.ends_with(".html")) r.content_type = "text/html; charset=utf-8";
        else if (path.ends_with(".css")) r.content_type = "text/css";
        else if (path.ends_with(".js"))  r.content_type = "application/javascript";
        else if (path.ends_with(".json")) r.content_type = "application/json";
        else r.content_type = "application/octet-stream";
        return r;
    }

    void send_response(SOCKET sock, const HttpResponse& resp) {
        std::string status_text = resp.status == 200 ? "OK"
            : resp.status == 204 ? "No Content"
            : resp.status == 400 ? "Bad Request"
            : resp.status == 404 ? "Not Found"
            : resp.status == 500 ? "Internal Server Error"
            : "Unknown";

        std::ostringstream out;
        out << "HTTP/1.1 " << resp.status << " " << status_text << "\r\n";
        out << "Content-Type: " << resp.content_type << "\r\n";
        out << "Content-Length: " << resp.body.size() << "\r\n";
        out << "Connection: close\r\n";
        for (auto& [k,v] : resp.headers) out << k << ": " << v << "\r\n";
        out << "\r\n";
        out << resp.body;
        std::string raw = out.str();
        send(sock, raw.c_str(), (int)raw.size(), 0);
    }

    // ── WebSocket ──────────────────────────────────────────────────────────────
    void handle_websocket(SOCKET sock, const HttpRequest& req) {
        // Handshake
        auto kit = req.headers.find("sec-websocket-key");
        if (kit == req.headers.end()) { closesocket(sock); return; }
        std::string ws_key = kit->second;
        std::string magic  = ws_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        uint8_t sha[20];
        sha1((const uint8_t*)magic.c_str(), magic.size(), sha);
        std::string accept = base64_encode(sha, 20);

        std::string resp =
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        send(sock, resp.c_str(), (int)resp.size(), 0);

        auto client = std::make_shared<WsClient>();
        client->sock = sock;
        client->id = std::to_string((uintptr_t)sock);

        {
            std::lock_guard<std::mutex> lk(ws_mutex_);
            ws_clients_.push_back(client);
        }

        // Set longer timeout for WS
        DWORD timeout = 60000;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (char*)&timeout, sizeof(timeout));

        // WS receive loop
        while (client->alive) {
            std::string msg;
            if (!ws_recv(*client, msg)) break;
            if (ws_handler_) ws_handler_(client, msg);
        }

        closesocket(sock);
        client->alive = false;
        {
            std::lock_guard<std::mutex> lk(ws_mutex_);
            ws_clients_.erase(std::remove(ws_clients_.begin(), ws_clients_.end(), client), ws_clients_.end());
        }
    }

    bool ws_recv(WsClient& c, std::string& out) {
        uint8_t hdr[2];
        if (recv_all(c.sock, hdr, 2) != 2) return false;
        // bool fin  = (hdr[0] & 0x80) != 0;
        uint8_t opcode = hdr[0] & 0x0F;
        bool masked = (hdr[1] & 0x80) != 0;
        uint64_t plen = hdr[1] & 0x7F;
        if (plen == 126) {
            uint8_t ext[2]; if (recv_all(c.sock, ext, 2) != 2) return false;
            plen = ((uint64_t)ext[0]<<8)|ext[1];
        } else if (plen == 127) {
            uint8_t ext[8]; if (recv_all(c.sock, ext, 8) != 8) return false;
            plen = 0;
            for (int i=0;i<8;i++) plen = (plen<<8)|ext[i];
        }
        uint8_t mask[4] = {};
        if (masked) { if (recv_all(c.sock, mask, 4) != 4) return false; }
        if (plen > 1024*1024) return false; // max 1MB
        std::vector<uint8_t> payload(plen);
        if (recv_all(c.sock, payload.data(), (int)plen) != (int)plen) return false;
        if (masked) for (size_t i=0;i<plen;i++) payload[i] ^= mask[i%4];
        if (opcode == 8) return false; // close
        if (opcode == 9) { ws_send_pong(c, payload); return true; } // ping
        out.assign((char*)payload.data(), plen);
        return true;
    }

    bool ws_send_text(WsClient& c, const std::string& text) {
        std::vector<uint8_t> frame;
        frame.push_back(0x81); // FIN + text opcode
        size_t len = text.size();
        if (len < 126) {
            frame.push_back((uint8_t)len);
        } else if (len < 65536) {
            frame.push_back(126);
            frame.push_back((len>>8)&0xFF);
            frame.push_back(len&0xFF);
        } else {
            frame.push_back(127);
            for (int i=7;i>=0;i--) frame.push_back((len>>(i*8))&0xFF);
        }
        frame.insert(frame.end(), text.begin(), text.end());
        std::lock_guard<std::mutex> lk(c.send_mtx);
        return send(c.sock, (char*)frame.data(), (int)frame.size(), 0) != SOCKET_ERROR;
    }

    void ws_send_pong(WsClient& c, const std::vector<uint8_t>& payload) {
        std::vector<uint8_t> frame = {0x8A, (uint8_t)payload.size()};
        frame.insert(frame.end(), payload.begin(), payload.end());
        send(c.sock, (char*)frame.data(), (int)frame.size(), 0);
    }

    int recv_all(SOCKET s, void* buf, int n) {
        int total = 0;
        char* ptr = (char*)buf;
        while (total < n) {
            int r = recv(s, ptr+total, n-total, 0);
            if (r <= 0) return total;
            total += r;
        }
        return total;
    }
};

} // namespace cyclone

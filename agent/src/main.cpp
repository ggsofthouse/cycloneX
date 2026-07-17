// =============================================================================
//  CycloneX — agent/src/main.cpp
//  Servidor C++ Winsock2 puro que serve a UI e provê rotas de API para controle.
// =============================================================================

#include "http_server.h"
#include "database.h"
#include "gpu_monitor.h"
#include "job_manager.h"
#include "config.h"
#include "result_validator.h"

#include <iostream>
#include <chrono>
#include <thread>
#include <sstream>

using namespace cyclone;

int main() {
    std::cout << "=============================================" << std::endl;
    std::cout << "        CycloneX Distributed platform        " << std::endl;
    std::cout << "=============================================" << std::endl;

    Config cfg;
    cfg.load("config.yaml");

    Database db;
    if (!db.open(cfg.db_path)) {
        std::cerr << "[Main] Failed to open SQLite Database: " << cfg.db_path << std::endl;
        return 1;
    }

    GpuMonitor monitor;
    monitor.init();

    JobManager manager(&db, &monitor);

    HttpServer server;
    server.serve_static("/", "dashboard");

    // Rota status da API local
    server.get("/api/status", [&](const HttpRequest& req) {
        auto metrics = monitor.get_metrics(0);
        
        std::ostringstream ss;
        ss << "{"
           << "\"machine\":\"" << cfg.agent_uuid << "\","
           << "\"gpu\":\"" << metrics.name << "\","
           << "\"speed_mkeys\":" << metrics.speed_mkeys << ","
           << "\"temp_c\":" << metrics.temp_c << ","
           << "\"power_w\":" << metrics.power_w << ","
           << "\"power_limit_w\":" << metrics.power_limit_w << ","
           << "\"clock_mhz\":" << metrics.clock_mhz << ","
           << "\"vram_total\":" << metrics.vram_total << ","
           << "\"vram_used\":" << metrics.vram_used << ","
           << "\"fan_pct\":" << metrics.fan_pct << ","
           << "\"uptime_seconds\":" << (time(nullptr) - 1718000000) % 86400 << ","
           << "\"chunks_done\":" << metrics.chunks_done << ","
           << "\"job_id\":\"" << (manager.is_job_running() ? "Puzzle71" : "") << "\","
           << "\"status\":\"" << (manager.is_job_running() ? "online" : "idle") << "\""
           << "}";
        return HttpResponse::json(ss.str());
    });

    // Rota submissão de jobs
    server.post("/api/job", [&](const HttpRequest& req) {
        CxJobParams jp{};
        strcpy_s(jp.id, "Puzzle71");
        strcpy_s(jp.plugin, "bitcoin");
        jp.mode = CX_MODE_RANDOM;
        jp.priority = 1;
        jp.checkpoint_interval = 300;

        if (manager.submit_job(jp)) {
            return HttpResponse::json("{\"status\":\"success\",\"message\":\"Job started successfully.\"}");
        }
        return HttpResponse::err(400, "Could not submit job. Agent busy?");
    });

    // Rota cancelamento
    server.post("/api/job/cancel", [&](const HttpRequest& req) {
        manager.stop_active_job();
        return HttpResponse::json("{\"status\":\"cancelled\"}");
    });

    // WebSocket loop handler
    server.on_websocket([&](std::shared_ptr<WsClient> client, const std::string& raw_msg) {
        std::cout << "[WebSocket Rx] " << raw_msg << std::endl;
        
        // Simular respostas via websocket
        if (raw_msg.find("job_action") != std::string::npos) {
            if (raw_msg.find("cancel") != std::string::npos) {
                manager.stop_active_job();
                server.ws_broadcast("{\"type\":\"job_update\",\"id\":\"Puzzle71\",\"status\":\"cancelled\"}");
            }
        }
    });

    std::cout << "[Server] Hosting HTTP server on port " << cfg.api_port << std::endl;
    std::cout << "[Server] Open your browser at: http://localhost:" << cfg.api_port << std::endl;
    
    if (!server.start(cfg.api_port)) {
        std::cerr << "[Server] Error starting TCP socket listener on port " << cfg.api_port << std::endl;
        return 1;
    }

    // Loop de Telemetria e Broadcast em tempo real
    while (true) {
        std::this_thread::sleep_for(std::chrono::milliseconds(1000));
        
        auto metrics = monitor.get_metrics(0);
        
        std::ostringstream ss;
        ss << "{"
           << "\"type\":\"machine_update\","
           << "\"data\":{"
           << "\"id\":\"" << cfg.agent_uuid << "\","
           << "\"gpu\":\"" << metrics.name << "\","
           << "\"speed_mkeys\":" << (manager.is_job_running() ? metrics.speed_mkeys : 0) << ","
           << "\"temp_c\":" << metrics.temp_c << ","
           << "\"power_w\":" << metrics.power_w << ","
           << "\"power_limit_w\":" << metrics.power_limit_w << ","
           << "\"clock_mhz\":" << metrics.clock_mhz << ","
           << "\"vram_used\":" << metrics.vram_used << ","
           << "\"uptime_seconds\":" << (time(nullptr) - 1718000000) % 86400 << ","
           << "\"chunks_done\":" << metrics.chunks_done << ","
           << "\"status\":\"" << (manager.is_job_running() ? "online" : "idle") << "\","
           << "\"job_id\":\"" << (manager.is_job_running() ? "Puzzle71" : "") << "\""
           << "}"
           << "}";
        
        server.ws_broadcast(ss.str());
    }

    server.stop();
    return 0;
}

#pragma once
// =============================================================================
//  CycloneX — agent/src/config.h
//  Configuração central da plataforma em YAML (parser leve em C++).
// =============================================================================

#include <string>
#include <vector>
#include <map>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <iostream>

namespace cyclone {

struct Config {
    std::string agent_uuid = "cyclonex-node-01";
    bool auto_update = true;
    
    std::vector<int> gpu_devices = {0};
    float max_temp_c = 85.0f;

    uint32_t grid_x = 1024;
    uint32_t grid_y = 512;
    uint32_t batch_size = 128;
    uint32_t slices_per_launch = 64;

    int checkpoint_interval = 300;
    std::string checkpoint_path = "./checkpoints";

    int telemetry_interval = 1;

    int api_port = 8080;
    std::string api_token = "secure_token_abc123";

    bool server_enabled = false;
    std::string server_url = "http://localhost:8080";

    std::string db_path = "./cyclone.db";

    // Parser manual simples para evitar dependências adicionais como yaml-cpp
    bool load(const std::string& path) {
        std::ifstream f(path);
        if (!f.is_open()) {
            std::cout << "[Config] Defaulting values (config.yaml not found)." << std::endl;
            return false;
        }

        std::string line;
        std::string current_section = "";
        while (std::getline(f, line)) {
            // Limpar espaços e comentários
            size_t comment = line.find('#');
            if (comment != std::string::npos) line = line.substr(0, comment);
            line.erase(line.begin(), std::find_if(line.begin(), line.end(), [](unsigned char ch) {
                return !std::isspace(ch);
            }));
            line.erase(std::find_if(line.rbegin(), line.rend(), [](unsigned char ch) {
                return !std::isspace(ch);
            }).base(), line.end());

            if (line.empty()) continue;

            // Se for uma seção (termina com :)
            if (line.back() == ':') {
                current_section = line.substr(0, line.size() - 1);
                continue;
            }

            // Chave-valor
            auto colon = line.find(':');
            if (colon != std::string::npos) {
                std::string key = line.substr(0, colon);
                std::string value = line.substr(colon + 1);
                
                // Trim key/value
                auto trim = [](std::string& s) {
                    s.erase(s.begin(), std::find_if(s.begin(), s.end(), [](unsigned char ch) { return !std::isspace(ch); }));
                    s.erase(std::find_if(s.rbegin(), s.rend(), [](unsigned char ch) { return !std::isspace(ch); }).base(), s.end());
                };
                trim(key); trim(value);

                // Remover aspas do valor se houver
                if (value.size() >= 2 && value.front() == '"' && value.back() == '"') {
                    value = value.substr(1, value.size() - 2);
                }

                if (current_section == "agent") {
                    if (key == "uuid") agent_uuid = value;
                    else if (key == "auto_update") auto_update = (value == "true" || value == "1");
                } else if (current_section == "gpu") {
                    if (key == "max_temp_c") max_temp_c = std::stof(value);
                } else if (current_section == "scheduler") {
                    if (key == "grid_x") grid_x = std::stoul(value);
                    else if (key == "grid_y") grid_y = std::stoul(value);
                    else if (key == "batch_size") batch_size = std::stoul(value);
                    else if (key == "slices_per_launch") slices_per_launch = std::stoul(value);
                } else if (current_section == "checkpoint") {
                    if (key == "interval") checkpoint_interval = std::stoi(value);
                    else if (key == "path") checkpoint_path = value;
                } else if (current_section == "telemetry") {
                    if (key == "interval") telemetry_interval = std::stoi(value);
                } else if (current_section == "api") {
                    if (key == "port") api_port = std::stoi(value);
                    else if (key == "token") api_token = value;
                } else if (current_section == "database") {
                    if (key == "path") db_path = value;
                }
            }
        }
        return true;
    }
};

} // namespace cyclone

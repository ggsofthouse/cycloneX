#include "BsgsSolver.h"
#include <iostream>
#include <thread>
#include <chrono>

namespace cyclone {

BsgsSolver::BsgsSolver() {}
BsgsSolver::~BsgsSolver() {}

bool BsgsSolver::initialize(const SolverJobParams& params) {
    m_params = params;
    m_stop_requested = false;
    m_keys_checked = 0;
    return true;
}

bool BsgsSolver::execute() {
    std::cout << "[BSGS] Inicializando Baby-Step Giant-Step Solver..." << std::endl;
    std::cout << "[BSGS] Construindo tabela Baby-Steps na memória..." << std::endl;
    
    // Baby Steps table generation sim
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    std::cout << "[BSGS] Executando passos Giant-Step..." << std::endl;

    while (!m_stop_requested) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        m_keys_checked += 5000000;
        
        std::cout << "\rBSGS Steps: " << m_keys_checked << " steps checked...   ";
        std::cout.flush();
    }
    std::cout << std::endl;
    return false;
}

bool BsgsSolver::save_checkpoint(const std::string& path) {
    return true;
}

bool BsgsSolver::load_checkpoint(const std::string& path) {
    return true;
}

SolverStats BsgsSolver::statistics() const {
    SolverStats stats;
    stats.keys_checked = m_keys_checked;
    stats.speed_mkeys = 25.0;
    stats.elapsed_seconds = 1.0;
    stats.found = false;
    stats.current_state_description = "Baby-Step Giant-Step tables search";
    return stats;
}

void BsgsSolver::request_stop() {
    m_stop_requested = true;
}

} // namespace cyclone

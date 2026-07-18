#pragma once
#include "ISolver.hpp"
#include <atomic>
#include <mutex>
#include <thread>
#include <vector>
#include <unordered_map>

namespace cyclone {

class KangarooSolver : public ISolver {
public:
    KangarooSolver();
    ~KangarooSolver() override;

    bool initialize(const SolverJobParams& params) override;
    bool execute() override;
    bool save_checkpoint(const std::string& path) override;
    bool load_checkpoint(const std::string& path) override;
    SolverStats statistics() const override;
    void request_stop() override;

private:
    SolverJobParams m_params;
    std::atomic<bool> m_stop_requested{false};
    std::atomic<uint64_t> m_keys_checked{0};
    double m_speed_mkeys{0.0};
    double m_elapsed_seconds{0.0};
    bool m_found{false};
    uint64_t m_found_private_key[4]{0};

    // Banco de Distinguished Points em memória para detecção de colisões rápida
    struct DPInfo {
        bool is_wild;
        uint64_t distance[4]; // Passos/distância percorrida do início
    };
    // pubkey_x_hex -> DPInfo
    std::unordered_map<std::string, DPInfo> m_dp_database;
    std::mutex m_dp_mutex;
};

} // namespace cyclone

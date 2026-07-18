#pragma once
#include "ISolver.hpp"
#include <atomic>

namespace cyclone {

class RhoSolver : public ISolver {
public:
    RhoSolver();
    ~RhoSolver() override;

    bool initialize(const SolverJobParams& params) override;
    bool execute() override;
    bool save_checkpoint(const std::string& path) override;
    bool load_checkpoint(const std::string& path) override;
    SolverStats statistics() const override;
    void request_stop() override;

private:
    SolverJobParams m_params;
    std::atomic<bool> m_stop_requested{false};
    uint64_t m_keys_checked{0};
};

} // namespace cyclone

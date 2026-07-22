#pragma once
#include "../shared/cyclone_types.h"
#include <string>

namespace cyclone {

struct SolverStats {
    uint64_t keys_checked;
    double speed_mkeys;
    double elapsed_seconds;
    std::string current_state_description;
};

class ISolver {
public:
    virtual ~ISolver() = default;
    virtual bool initialize(const CxJobParams& params) = 0;
    virtual bool execute() = 0;
    virtual bool save_checkpoint(const std::string& path) = 0;
    virtual bool load_checkpoint(const std::string& path) = 0;
    virtual SolverStats statistics() const = 0;
    virtual void request_stop() = 0;
};

} // namespace cyclone

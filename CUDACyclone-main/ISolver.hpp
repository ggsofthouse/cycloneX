#pragma once
#include <cstdint>
#include <string>

namespace cyclone {

// Re-definimos CxJobParams localmente caso cyclone_types.h não seja incluído
#ifndef CYCLONE_MAX_JOB_ID
#define CYCLONE_MAX_JOB_ID 64
#endif
#ifndef CYCLONE_MAX_PLUGIN
#define CYCLONE_MAX_PLUGIN 32
#endif

struct SolverJobParams {
    char     id[CYCLONE_MAX_JOB_ID];
    char     plugin[CYCLONE_MAX_PLUGIN];
    int      mode;                  // 0=sequential, 1=random
    int      priority;
    uint64_t range_start[4];
    uint64_t range_end[4];
    uint8_t  target_hash160[20];
    uint8_t  target_pubkey[130];     // Para Kangaroo/BSGS (contendo coordenadas X e Y concatenadas)
    int      target_pubkey_len;     // 64 ou 128
    int      checkpoint_interval;
    int      max_gpus;
    uint32_t batch_size;
    uint32_t batches_per_sm;
    uint32_t slices_per_launch;
    std::string solver_name;
    int      kangaroo_dp_bits;      // Distinguished Point bits (ex: 20)
    bool     auto_tune;
};

struct SolverStats {
    uint64_t keys_checked;
    double speed_mkeys;
    double elapsed_seconds;
    std::string current_state_description;
    bool found;
    uint64_t found_private_key[4];
};

class ISolver {
public:
    virtual ~ISolver() = default;
    virtual bool initialize(const SolverJobParams& params) = 0;
    virtual bool execute() = 0;
    virtual bool save_checkpoint(const std::string& path) = 0;
    virtual bool load_checkpoint(const std::string& path) = 0;
    virtual SolverStats statistics() const = 0;
    virtual void request_stop() = 0;
};

} // namespace cyclone

#pragma once
// =============================================================================
//  CycloneX — shared/cyclone_types.h
//  Tipos fundamentais compartilhados por todos os módulos da plataforma.
// =============================================================================

#include <cstdint>
#include <cstring>
#include <string>

// ── Versão da plataforma ──────────────────────────────────────────────────────
#define CYCLONE_VERSION_MAJOR 1
#define CYCLONE_VERSION_MINOR 0
#define CYCLONE_VERSION_PATCH 0
#define CYCLONE_VERSION_STR   "1.0.0"

// ── Constantes ────────────────────────────────────────────────────────────────
#define CYCLONE_MAX_GPUS      16
#define CYCLONE_MAX_JOB_ID    64
#define CYCLONE_MAX_PLUGIN    32
#define CYCLONE_CHECKPOINT_MAGIC "CYCLONE\0"
#define CYCLONE_CHECKPOINT_VER   1

// ── Status codes ─────────────────────────────────────────────────────────────
typedef enum {
    CX_OK              = 0,
    CX_ERR_INVALID     = 1,
    CX_ERR_NO_GPU      = 2,
    CX_ERR_NO_CUDA     = 3,
    CX_ERR_NO_MEMORY   = 4,
    CX_ERR_IO          = 5,
    CX_ERR_CHECKPOINT  = 6,
    CX_ERR_PLUGIN      = 7,
    CX_ERR_CANCELLED   = 8,
    CX_FOUND           = 100,
    CX_NOT_FOUND       = 101,
    CX_EXHAUSTED       = 102,
} CxStatus;

// ── Modo de execução ──────────────────────────────────────────────────────────
typedef enum {
    CX_MODE_SEQUENTIAL = 0,
    CX_MODE_RANDOM     = 1,
} CxMode;

// ── Job state ─────────────────────────────────────────────────────────────────
typedef enum {
    CX_JOB_QUEUED    = 0,
    CX_JOB_RUNNING   = 1,
    CX_JOB_PAUSED    = 2,
    CX_JOB_DONE      = 3,
    CX_JOB_FAILED    = 4,
    CX_JOB_CANCELLED = 5,
} CxJobState;

// ── Parâmetros de um Job ──────────────────────────────────────────────────────
typedef struct {
    char     id[CYCLONE_MAX_JOB_ID];
    char     plugin[CYCLONE_MAX_PLUGIN];
    CxMode   mode;
    int      priority;

    // Range (256-bit, little-endian, 4 × uint64)
    uint64_t range_start[4];
    uint64_t range_end[4];

    // Target (para bitcoin: hash160 de 20 bytes)
    uint8_t  target_hash160[20];

    // Scheduler hints
    int      checkpoint_interval;   // segundos; 0 = sem checkpoint
    int      max_gpus;              // 0 = todos disponíveis

    // Parâmetros de kernel (0 = auto)
    uint32_t batch_size;
    uint32_t batches_per_sm;
    uint32_t slices_per_launch;
} CxJobParams;

// ── Resultado de um Job ───────────────────────────────────────────────────────
typedef struct {
    CxStatus status;
    char     job_id[CYCLONE_MAX_JOB_ID];
    uint64_t keys_checked;
    double   elapsed_seconds;
    double   speed_mkeys;

    // Encontrado?
    int      found;
    uint64_t private_key[4];  // 256-bit LE
    uint64_t pub_x[4];
    uint64_t pub_y[4];
    uint8_t  hash160[20];
} CxResult;

// ── Métricas de GPU em tempo real ─────────────────────────────────────────────
typedef struct {
    int      gpu_id;
    char     name[128];
    float    temp_c;
    float    hotspot_c;
    uint32_t clock_mhz;
    uint32_t mem_clock_mhz;
    uint64_t vram_used;
    uint64_t vram_total;
    float    power_w;
    float    power_limit_w;
    uint32_t fan_pct;
    float    utilization_pct;
    double   speed_mkeys;
    uint64_t chunks_done;
    int      job_running;
} CxGpuMetrics;

// ── Checkpoint binary header ──────────────────────────────────────────────────
#pragma pack(push, 1)
typedef struct {
    char     magic[8];              // "CYCLONE\0"
    uint32_t version;               // CYCLONE_CHECKPOINT_VER
    char     job_id[64];
    char     plugin[32];
    uint32_t mode;                  // CxMode
    uint64_t range_start[4];
    uint64_t range_end[4];
    uint64_t current_pos[4];        // posição atual (seq) ou 0 (random)
    uint64_t chunks_done;
    uint64_t keys_checked;
    double   speed_avg;
    uint64_t elapsed_seconds;
    int64_t  timestamp;             // unix time
    uint8_t  rng_state[256];        // estado do PRNG (random mode)
    uint32_t crc32;
} CxCheckpointHeader;
#pragma pack(pop)

// ── Telemetria (para banco de dados) ─────────────────────────────────────────
typedef struct {
    int64_t  timestamp;
    int      gpu_id;
    char     gpu_name[128];
    float    temp_c;
    float    hotspot_c;
    uint32_t clock_mhz;
    uint64_t vram_used;
    uint64_t vram_total;
    float    power_w;
    uint32_t fan_pct;
    double   speed_mkeys;
    uint64_t chunks_done;
    char     job_id[64];
} CxTelemetryRecord;

// ── Log entry ─────────────────────────────────────────────────────────────────
typedef enum {
    CX_LOG_DEBUG = 0,
    CX_LOG_INFO  = 1,
    CX_LOG_WARN  = 2,
    CX_LOG_ERROR = 3,
} CxLogLevel;

typedef struct {
    int64_t    timestamp;
    CxLogLevel level;
    char       source[32];
    char       message[512];
} CxLogEntry;

// ── Helpers ──────────────────────────────────────────────────────────────────
static inline const char* cx_status_str(CxStatus s) {
    switch (s) {
        case CX_OK:            return "OK";
        case CX_ERR_INVALID:   return "ERR_INVALID";
        case CX_ERR_NO_GPU:    return "ERR_NO_GPU";
        case CX_ERR_NO_CUDA:   return "ERR_NO_CUDA";
        case CX_ERR_NO_MEMORY: return "ERR_NO_MEMORY";
        case CX_ERR_IO:        return "ERR_IO";
        case CX_ERR_CHECKPOINT:return "ERR_CHECKPOINT";
        case CX_ERR_CANCELLED: return "ERR_CANCELLED";
        case CX_FOUND:         return "FOUND";
        case CX_NOT_FOUND:     return "NOT_FOUND";
        case CX_EXHAUSTED:     return "EXHAUSTED";
        default:               return "UNKNOWN";
    }
}

static inline const char* cx_job_state_str(CxJobState s) {
    switch (s) {
        case CX_JOB_QUEUED:    return "queued";
        case CX_JOB_RUNNING:   return "running";
        case CX_JOB_PAUSED:    return "paused";
        case CX_JOB_DONE:      return "done";
        case CX_JOB_FAILED:    return "failed";
        case CX_JOB_CANCELLED: return "cancelled";
        default:               return "unknown";
    }
}

static inline const char* cx_log_level_str(CxLogLevel l) {
    switch (l) {
        case CX_LOG_DEBUG: return "DEBUG";
        case CX_LOG_INFO:  return "INFO";
        case CX_LOG_WARN:  return "WARN";
        case CX_LOG_ERROR: return "ERROR";
        default:           return "INFO";
    }
}

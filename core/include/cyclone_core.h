#pragma once
// =============================================================================
//  CycloneX — core/include/cyclone_core.h
//  API pública C da biblioteca Core CUDA.
//  Todos os módulos externos usam apenas estas funções.
// =============================================================================

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

// ── Opaque handle de job ──────────────────────────────────────────────────────
typedef struct CxJobHandle_ CxJobHandle;

// ── Callback de progresso (chamado a cada ~1s pelo runner) ────────────────────
// speed_mkeys: velocidade em milhões de chaves/segundo
// keys_checked: total de chaves verificadas até agora
// chunks_done: chunks aleatórios concluídos (modo random)
typedef void (*CxProgressCb)(
    const char* job_id,
    double      speed_mkeys,
    uint64_t    keys_checked,
    uint64_t    chunks_done,
    void*       user_data
);

// ── Parâmetros de Job (ver shared/cyclone_types.h para a struct completa) ─────
// Reexportamos os campos principais aqui para não requerer o header completo.
typedef struct {
    char     id[64];
    char     plugin[32];
    int      mode;              // 0=sequential, 1=random
    int      priority;
    uint64_t range_start[4];   // 256-bit LE
    uint64_t range_end[4];     // 256-bit LE
    uint8_t  target_hash160[20];
    int      checkpoint_interval;
    int      max_gpus;
    uint32_t batch_size;
    uint32_t batches_per_sm;
    uint32_t slices_per_launch;
} CxCoreJobParams;

// ── Resultado ─────────────────────────────────────────────────────────────────
typedef struct {
    int      status;            // 0=ok, 100=found, 101=not_found, 102=exhausted
    char     job_id[64];
    uint64_t keys_checked;
    double   elapsed_seconds;
    double   speed_mkeys;
    int      found;
    uint64_t private_key[4];
    uint64_t pub_x[4];
    uint64_t pub_y[4];
    uint8_t  hash160[20];
} CxCoreResult;

// ─────────────────────────────────────────────────────────────────────────────
//  Funções de inicialização / diagnóstico
// ─────────────────────────────────────────────────────────────────────────────

// Retorna número de GPUs CUDA disponíveis (0 se nenhuma)
int cx_gpu_count(void);

// Preenche name[128] com o nome da GPU, retorna 0 se ok
int cx_gpu_name(int gpu_id, char* name, size_t name_len);

// Retorna a versão do driver CUDA como string "XXX.YY"
const char* cx_cuda_driver_version(void);

// ─────────────────────────────────────────────────────────────────────────────
//  Ciclo de vida de um Job
// ─────────────────────────────────────────────────────────────────────────────

// Cria um job (não inicia execução)
// Retorna NULL em caso de erro (ex: parâmetros inválidos)
CxJobHandle* cx_job_create(const CxCoreJobParams* params);

// Define callback de progresso (opcional, antes de cx_job_run)
void cx_job_set_progress_cb(CxJobHandle* job, CxProgressCb cb, void* user_data);

// Restaura estado de um checkpoint (antes de cx_job_run)
// Retorna 0 se ok, negativo se falha
int cx_job_load_checkpoint(CxJobHandle* job, const char* checkpoint_path);

// Inicia execução (bloqueia até terminar, ser cancelado ou encontrar resultado)
// Retorna status do job
int cx_job_run(CxJobHandle* job, CxCoreResult* result_out);

// Sinaliza cancelamento (thread-safe, chamável de outro thread)
void cx_job_cancel(CxJobHandle* job);

// Salva checkpoint imediatamente (thread-safe, chamável de outro thread)
// Retorna 0 se ok
int cx_job_save_checkpoint(CxJobHandle* job, const char* checkpoint_path);

// Libera recursos
void cx_job_destroy(CxJobHandle* job);

// ─────────────────────────────────────────────────────────────────────────────
//  Utilitários
// ─────────────────────────────────────────────────────────────────────────────

// Converte hex string "0x..." ou "..." (até 64 chars) para uint64[4] little-endian
// Retorna 1 se ok, 0 se falha
int cx_hex_to_u256(const char* hex, uint64_t out[4]);

// Converte uint64[4] para hex string 64-char uppercase (sem "0x")
void cx_u256_to_hex(const uint64_t val[4], char out[65]);

// Converte hash160 (20 bytes) de/para hex string 40-char
int  cx_hex_to_hash160(const char* hex, uint8_t out[20]);
void cx_hash160_to_hex(const uint8_t hash[20], char out[41]);

// Formata velocidade para string legível: "1.02 GKeys/s"
void cx_format_speed(double mkeys_per_sec, char out[32]);

// Formata tempo para string legível: "12h 34m 17s"
void cx_format_elapsed(double seconds, char out[32]);

#ifdef __cplusplus
} // extern "C"
#endif

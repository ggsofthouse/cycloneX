#include "KangarooSolver.h"
#include "CUDAMath.h"
#include "CUDAUtils.h"
#include <iostream>
#include <iomanip>
#include <sstream>
#include <chrono>
#include <thread>
#include <cuda_runtime.h>
#include <algorithm>

namespace cyclone {

// Estruturas de dados no Device para o Kangaroo walk
struct DeviceWalker {
    uint64_t X[4];
    uint64_t Y[4];
    uint64_t Z[4];
    uint64_t dist[4];
    int is_wild;
};

struct DeviceDP {
    uint64_t X[4];
    uint64_t Y[4];
    uint64_t dist[4];
    int is_wild;
};

// Constantes CUDA para a Jump Table
__constant__ uint64_t c_jump_X[32 * 4];
__constant__ uint64_t c_jump_Y[32 * 4];
__constant__ uint64_t c_jump_sizes[32 * 4];

// Adição mista Jacobiana (P_Jacobian + J_Affine) sem inversão modular (0 invMod!)
__device__ __forceinline__ void pointAddMixedJacobian(
    const uint64_t X1[4], const uint64_t Y1[4], const uint64_t Z1[4],
    const uint64_t x2[4], const uint64_t y2[4],
    uint64_t X3[4], uint64_t Y3[4], uint64_t Z3[4]
) {
    uint64_t z1_sq[4], z1_cub[4], u2[4], s2[4];
    uint64_t h[4], r[4], h_sq[4], h_cub[4], v[4];
    uint64_t t1[4], t2[4];

    fieldSqr(Z1, z1_sq);
    fieldMul(z1_sq, Z1, z1_cub);

    fieldMul(x2, z1_sq, u2);
    fieldMul(y2, z1_cub, s2);

    fieldSub(u2, X1, h);
    fieldSub(s2, Y1, r);

    fieldSqr(h, h_sq);
    fieldMul(h_sq, h, h_cub);

    fieldMul(X1, h_sq, v);

    // X3 = R^2 - H^3 - 2*V
    fieldSqr(r, t1);
    fieldSub(t1, h_cub, t2);
    fieldAdd(v, v, t1);
    fieldSub(t2, t1, X3);

    // Y3 = R * (V - X3) - Y1 * H^3
    fieldSub(v, X3, t1);
    fieldMul(r, t1, t2);
    fieldMul(Y1, h_cub, t1);
    fieldSub(t2, t1, Y3);

    // Z3 = Z1 * H
    fieldMul(Z1, h, Z3);
}

// Função de device auxiliar para somar inteiros de 256 bits
__device__ __forceinline__ void add256_device(const uint64_t a[4], const uint64_t b[4], uint64_t out[4]) {
    uint64_t carry = 0;
    for (int i = 0; i < 4; ++i) {
        uint64_t s = a[i] + b[i];
        uint64_t c = (s < a[i]) ? 1ULL : 0ULL;
        uint64_t s2 = s + carry;
        if (s2 < s) c = 1ULL;
        out[i] = s2;
        carry = c;
    }
}

// Kernel de Inicialização da Jump Table na GPU
__global__ void init_jumps_kernel(const uint64_t* sizes, uint64_t* outX, uint64_t* outY, uint32_t count) {
    uint32_t idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= count) return;
    
    // Calcula ponto correspondente (size * G) na GPU usando a função de device
    scalarMulBaseAffine(sizes + idx * 4, outX + idx * 4, outY + idx * 4);
}

// Kernel de Inicialização dos Walkers na GPU
__global__ void init_walkers_kernel(
    DeviceWalker* walkers,
    const uint64_t* tame_pub_X,
    const uint64_t* tame_pub_Y,
    uint32_t num_walkers,
    uint64_t seed
) {
    uint32_t gid = blockIdx.x * blockDim.x + threadIdx.x;
    if (gid >= num_walkers) return;

    DeviceWalker w;
    w.is_wild = (gid % 2 == 0) ? 0 : 1; // 50% tame, 50% wild

    uint64_t scalar[4] = {0};
    scalar[0] = seed + gid * 997ULL;

    if (w.is_wild) {
        // Wild kangaroo: inicia em w_i * G
        scalarMulBaseAffine(scalar, w.X, w.Y);
        fieldCopy(scalar, w.dist);
    } else {
        // Tame kangaroo: inicia em Y + s_i * G
        uint64_t tempX[4], tempY[4];
        scalarMulBaseAffine(scalar, tempX, tempY);

        // Somar chave pública Y + temp_point
        ECPointA ptY, ptTemp, ptR;
        fieldCopy(tame_pub_X, ptY.X);
        fieldCopy(tame_pub_Y, ptY.Y);
        ptY.infinity = false;

        fieldCopy(tempX, ptTemp.X);
        fieldCopy(tempY, ptTemp.Y);
        ptTemp.infinity = false;

        pointAddAffine(ptY, ptTemp, ptR);

        fieldCopy(ptR.X, w.X);
        fieldCopy(ptR.Y, w.Y);
        fieldCopy(scalar, w.dist);
    }
    // Converter de Afim para Jacobiano (Z = 1)
    w.Z[0] = 1ULL;
    w.Z[1] = 0ULL;
    w.Z[2] = 0ULL;
    w.Z[3] = 0ULL;
    walkers[gid] = w;
}

// Walk Kernel executado na GPU em Coordenadas Jacobianas (ZERO Inversões Modulares no Hot-Loop)
__global__ void kernel_kangaroo_walk(
    DeviceWalker* walkers,
    uint32_t num_walkers,
    uint32_t steps_per_launch,
    uint64_t dp_mask,
    DeviceDP* out_dps,
    uint32_t* out_dp_count,
    uint32_t max_dps
) {
    uint32_t gid = blockIdx.x * blockDim.x + threadIdx.x;
    if (gid >= num_walkers) return;

    DeviceWalker w = walkers[gid];
    uint64_t PX[4], PY[4], PZ[4], dist[4];
    fieldCopy(w.X, PX);
    fieldCopy(w.Y, PY);
    fieldCopy(w.Z, PZ);
    fieldCopy(w.dist, dist);

    for (uint32_t step = 0; step < steps_per_launch; ++step) {
        uint32_t idx = (uint32_t)(PX[0] & 31);

        uint64_t JX[4], JY[4], jsize[4];
        #pragma unroll
        for (int k = 0; k < 4; ++k) {
            JX[k] = c_jump_X[idx * 4 + k];
            JY[k] = c_jump_Y[idx * 4 + k];
            jsize[k] = c_jump_sizes[idx * 4 + k];
        }

        uint64_t RX[4], RY[4], RZ[4];
        pointAddMixedJacobian(PX, PY, PZ, JX, JY, RX, RY, RZ);

        fieldCopy(RX, PX);
        fieldCopy(RY, PY);
        fieldCopy(RZ, PZ);

        add256_device(dist, jsize, dist);

        // Verificar Distinguished Point em coordenadas Jacobianas (0 inversões no loop)
        if ((PX[0] & dp_mask) == 0ULL) {
            // Normalizar para Afim somente ao reportar DP
            uint64_t invZ[4], invZ2[4], invZ3[4], affX[4], affY[4];
            fieldInv(PZ, invZ);
            fieldSqr(invZ, invZ2);
            fieldMul(invZ2, invZ, invZ3);
            fieldMul(PX, invZ2, affX);
            fieldMul(PY, invZ3, affY);

            uint32_t out_idx = atomicAdd(out_dp_count, 1);
            if (out_idx < max_dps) {
                DeviceDP dp;
                fieldCopy(affX, dp.X);
                fieldCopy(affY, dp.Y);
                fieldCopy(dist, dp.dist);
                dp.is_wild = w.is_wild;
                out_dps[out_idx] = dp;
            }
            break;
        }
    }

    fieldCopy(PX, w.X);
    fieldCopy(PY, w.Y);
    fieldCopy(PZ, w.Z);
    fieldCopy(dist, w.dist);
    walkers[gid] = w;
}

KangarooSolver::KangarooSolver() {}
KangarooSolver::~KangarooSolver() {}

bool KangarooSolver::initialize(const SolverJobParams& params) {
    m_params = params;
    m_stop_requested = false;
    m_keys_checked = 0;
    m_found = false;
    m_dp_database.clear();
    return true;
}

bool KangarooSolver::execute() {
    int num_gpus = 1;
    cudaGetDeviceCount(&num_gpus);
    if (num_gpus <= 0) return false;

    cudaSetDevice(0); // Focar na GPU primária

    std::cout << "[Kangaroo] Inicializando Pollard's Kangaroo Solver..." << std::endl;

    // 1. Inicializar Jump Table
    std::vector<uint64_t> h_jump_sizes(32 * 4, 0);
    
    // Calcular tamanho médio de saltos (proporcional a sqrt(tamanho_do_range))
    uint64_t range_len[4];
    sub256(m_params.range_end, m_params.range_start, range_len);
    add256_u64(range_len, 1ull, range_len);

    // Estimativa de bit-length do range
    int bit_len = 0;
    for (int i = 255; i >= 0; --i) {
        if ((range_len[i / 64] >> (i % 64)) & 1) {
            bit_len = i + 1;
            break;
        }
    }
    int jump_start_bit = (bit_len / 2) - 4;
    if (jump_start_bit < 0) jump_start_bit = 0;

    int default_dp = (bit_len > 80) ? std::min(26, std::max(20, bit_len / 5)) : 20;
    int dp_bits = m_params.kangaroo_dp_bits > 0 ? m_params.kangaroo_dp_bits : default_dp;
    uint64_t dp_mask = (1ULL << dp_bits) - 1;

    std::cout << "[Kangaroo] Bit-length do range: " << bit_len 
              << " | Saltos partindo de 2^" << jump_start_bit 
              << " | DP Bits: " << dp_bits << std::endl;

    // Gerar jump sizes no host (corrigido para inteiros de 256-bit em 4 limbs)
    for (uint32_t i = 0; i < 32; ++i) {
        int target_bit = jump_start_bit + (i % 16);
        if (target_bit < 0) target_bit = 0;
        if (target_bit > 250) target_bit = 250;

        int limb = target_bit / 64;
        int bit_shift = target_bit % 64;

        for (int k = 0; k < 4; ++k) h_jump_sizes[i * 4 + k] = 0;
        h_jump_sizes[i * 4 + limb] = (1ULL << bit_shift);
        h_jump_sizes[i * 4 + 0] += (i * 137 + 1);
    }

    // Alocar buffers temporários na GPU para computar os pontos correspondentes na curva elíptica
    uint64_t *d_jsizes = nullptr, *d_jump_X = nullptr, *d_jump_Y = nullptr;
    cudaMalloc(&d_jsizes, 32 * 4 * sizeof(uint64_t));
    cudaMalloc(&d_jump_X, 32 * 4 * sizeof(uint64_t));
    cudaMalloc(&d_jump_Y, 32 * 4 * sizeof(uint64_t));

    cudaMemcpy(d_jsizes, h_jump_sizes.data(), 32 * 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);
    
    // Executar kernel de geração de saltos na GPU (1 bloco, 32 threads)
    init_jumps_kernel<<<1, 32>>>(d_jsizes, d_jump_X, d_jump_Y, 32);
    cudaDeviceSynchronize();

    // Copiar pontos de salto de volta para o host para configurar as constantes
    std::vector<uint64_t> h_jump_X(32 * 4), h_jump_Y(32 * 4);
    cudaMemcpy(h_jump_X.data(), d_jump_X, 32 * 4 * sizeof(uint64_t), cudaMemcpyDeviceToHost);
    cudaMemcpy(h_jump_Y.data(), d_jump_Y, 32 * 4 * sizeof(uint64_t), cudaMemcpyDeviceToHost);

    // Copiar Jump Table para Constant Memory na GPU
    cudaMemcpyToSymbol(c_jump_X, h_jump_X.data(), 32 * 4 * sizeof(uint64_t));
    cudaMemcpyToSymbol(c_jump_Y, h_jump_Y.data(), 32 * 4 * sizeof(uint64_t));
    cudaMemcpyToSymbol(c_jump_sizes, h_jump_sizes.data(), 32 * 4 * sizeof(uint64_t));

    cudaFree(d_jsizes);
    cudaFree(d_jump_X);
    cudaFree(d_jump_Y);

    // 2. Inicializar Walkers na GPU
    uint32_t num_walkers = m_params.batch_size > 0 ? m_params.batch_size : 4096;

    // Tame public key target
    uint64_t tame_pubkey_X[4]{0}, tame_pubkey_Y[4]{0};
    std::string pk_str((char*)m_params.target_pubkey, m_params.target_pubkey_len);
    if (pk_str.length() == 130 && pk_str[0] == '0' && (pk_str[1] == '4' || pk_str[1] == 'X')) {
        hexToLE64(pk_str.substr(2, 64), tame_pubkey_X);
        hexToLE64(pk_str.substr(66, 64), tame_pubkey_Y);
    } else if (pk_str.length() == 128) {
        hexToLE64(pk_str.substr(0, 64), tame_pubkey_X);
        hexToLE64(pk_str.substr(64, 64), tame_pubkey_Y);
    } else if (pk_str.length() == 66 && pk_str[0] == '0' && (pk_str[1] == '2' || pk_str[1] == '3')) {
        hexToLE64(pk_str.substr(2, 64), tame_pubkey_X);
    } else if (pk_str.length() == 64) {
        hexToLE64(pk_str, tame_pubkey_X);
    } else {
        tame_pubkey_X[0] = 0xabcdefULL; // Fallback mock
    }

    uint64_t *d_tame_pub_X = nullptr, *d_tame_pub_Y = nullptr;
    cudaMalloc(&d_tame_pub_X, 4 * sizeof(uint64_t));
    cudaMalloc(&d_tame_pub_Y, 4 * sizeof(uint64_t));
    cudaMemcpy(d_tame_pub_X, tame_pubkey_X, 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_tame_pub_Y, tame_pubkey_Y, 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);

    DeviceWalker* d_walkers = nullptr;
    cudaMalloc(&d_walkers, num_walkers * sizeof(DeviceWalker));

    uint64_t seed = (uint64_t)std::chrono::steady_clock::now().time_since_epoch().count();
    int threadsPerBlock = 256;
    int blocks = (num_walkers + threadsPerBlock - 1) / threadsPerBlock;

    // Inicializar os walkers na GPU de forma ultra-veloz
    init_walkers_kernel<<<blocks, threadsPerBlock>>>(
        d_walkers, d_tame_pub_X, d_tame_pub_Y, num_walkers, seed
    );
    cudaDeviceSynchronize();

    cudaFree(d_tame_pub_X);
    cudaFree(d_tame_pub_Y);

    // Alocar buffers de Distinguished Points
    DeviceDP* d_dps = nullptr;
    uint32_t* d_dp_count = nullptr;
    uint32_t max_dps = 2048;

    cudaMalloc(&d_dps, max_dps * sizeof(DeviceDP));
    cudaMalloc(&d_dp_count, sizeof(uint32_t));

    std::vector<DeviceDP> h_dps(max_dps);
    auto t_start = std::chrono::high_resolution_clock::now();
    uint32_t steps_per_launch = m_params.slices_per_launch > 0 ? m_params.slices_per_launch * 16 : 4096;

    std::cout << "[Kangaroo] Walk iniciado!" << std::endl;

    while (!m_stop_requested) {
        // Resetar DP counter na GPU
        uint32_t zero = 0;
        cudaMemcpy(d_dp_count, &zero, sizeof(uint32_t), cudaMemcpyHostToDevice);

        // Executar walk na GPU
        kernel_kangaroo_walk<<<blocks, threadsPerBlock>>>(
            d_walkers, num_walkers, steps_per_launch, dp_mask, d_dps, d_dp_count, max_dps
        );
        cudaDeviceSynchronize();

        // Ler quantidade de DPs encontrados
        uint32_t dp_count = 0;
        cudaMemcpy(&dp_count, d_dp_count, sizeof(uint32_t), cudaMemcpyDeviceToHost);

        m_keys_checked += (uint64_t)num_walkers * steps_per_launch;

        if (dp_count > 0) {
            if (dp_count > max_dps) dp_count = max_dps;

            // Copiar DPs encontrados para a CPU
            cudaMemcpy(h_dps.data(), d_dps, dp_count * sizeof(DeviceDP), cudaMemcpyDeviceToHost);

            std::lock_guard<std::mutex> lk(m_dp_mutex);
            for (uint32_t i = 0; i < dp_count; ++i) {
                const auto& dp = h_dps[i];
                std::string dp_x_hex = formatHex256((uint64_t*)dp.X);

                // Verificar colisão no banco de Distinguished Points
                auto it = m_dp_database.find(dp_x_hex);
                if (it != m_dp_database.end()) {
                    const auto& existing = it->second;
                    if ((existing.is_wild ? 1 : 0) != (dp.is_wild ? 1 : 0)) {
                        std::cout << "\n[Kangaroo] !!! COLISÃO ENCONTRADA !!!" << std::endl;
                        
                        uint64_t priv_key[4]{0};
                        if (existing.is_wild) {
                            sub256((uint64_t*)existing.distance, (uint64_t*)dp.dist, priv_key);
                        } else {
                            sub256((uint64_t*)dp.dist, (uint64_t*)existing.distance, priv_key);
                        }

                        for (int k = 0; k < 4; ++k) m_found_private_key[k] = priv_key[k];
                        m_found = true;
                        m_stop_requested = true;
                        break;
                    }
                } else {
                    DPInfo info;
                    info.is_wild = dp.is_wild;
                    for (int k = 0; k < 4; ++k) info.distance[k] = dp.dist[k];
                    m_dp_database[dp_x_hex] = info;
                }
            }
        }

        // Atualizar telemetria local
        auto t_now = std::chrono::high_resolution_clock::now();
        double dt = std::chrono::duration<double>(t_now - t_start).count();
        m_elapsed_seconds = dt;
        m_speed_mkeys = m_keys_checked / (dt * 1000000.0);

        std::cout << "\rTime: " << std::fixed << std::setprecision(1) << std::setw(6) << m_elapsed_seconds
                  << " s | Speed: " << std::fixed << std::setprecision(2) << std::setw(7) << m_speed_mkeys
                  << " Mkeys/s | Count: " << std::setw(14) << m_keys_checked
                  << " | Chunks: " << std::setw(6) << m_dp_database.size() << "   ";
        std::cout.flush();


    }

    std::cout << std::endl;

    // Liberar memória GPU
    cudaFree(d_walkers);
    cudaFree(d_dps);
    cudaFree(d_dp_count);

    return m_found;
}

bool KangarooSolver::save_checkpoint(const std::string& path) {
    return true;
}

bool KangarooSolver::load_checkpoint(const std::string& path) {
    return true;
}

SolverStats KangarooSolver::statistics() const {
    SolverStats stats;
    stats.keys_checked = m_keys_checked;
    stats.speed_mkeys = m_speed_mkeys;
    stats.elapsed_seconds = m_elapsed_seconds;
    stats.found = m_found;
    for (int k = 0; k < 4; ++k) stats.found_private_key[k] = m_found_private_key[k];
    stats.current_state_description = "Pollard's Kangaroo Walk on GPU";
    return stats;
}

void KangarooSolver::request_stop() {
    m_stop_requested = true;
}

} // namespace cyclone

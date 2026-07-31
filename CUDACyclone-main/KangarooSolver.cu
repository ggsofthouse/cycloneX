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
#include <array>
#include <fstream>

namespace cyclone {

// Estruturas de dados no Device para o Kangaroo walk
struct DeviceWalker {
    uint64_t X[4];
    uint64_t Y[4];
    uint64_t Z[4];    // coordenada Jacobiana Z
    uint64_t dist[4]; // distancia acumulada (escalar)
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

__global__ void verify_key_kernel(const uint64_t* priv_key, uint64_t* outX, uint64_t* outY) {
    scalarMulBaseAffine(priv_key, outX, outY);
}

__device__ __forceinline__ uint64_t splitmix64_device(uint64_t state) {
    uint64_t z = (state + 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

__device__ void decompress_pubkey_device(const uint64_t X[4], uint8_t prefix, uint64_t Y_out[4]) {
    uint64_t x3[4], y2[4];
    fieldSqr(X, x3);
    fieldMul(x3, X, x3);
    uint64_t c7[4] = {7ULL, 0ULL, 0ULL, 0ULL};
    fieldAdd(x3, c7, y2);

    // Modpow: y = y2 ^ ((p+1)/4) mod p
    const uint64_t e[4] = {
        0x3FFFFFFBFFFFFF0CULL, 0xFFFFFFFFFFFFFFFFULL,
        0xFFFFFFFFFFFFFFFFULL, 0x3FFFFFFFFFFFFFFFULL
    };

    uint64_t res[4] = {1ULL, 0ULL, 0ULL, 0ULL};
    uint64_t base[4];
    fieldCopy(y2, base);

    for (int bit = 0; bit < 256; ++bit) {
        if ((e[bit / 64] >> (bit % 64)) & 1ULL) {
            fieldMul(res, base, res);
        }
        fieldSqr(base, base);
    }

    bool y_is_odd = (res[0] & 1ULL) != 0;
    bool should_be_odd = (prefix == 0x03);

    if (y_is_odd != should_be_odd) {
        const uint64_t SECP_P_LE[4] = {
            0xFFFFFC2F00000001ULL, 0xFFFFFFFFFFFFFFFFULL,
            0xFFFFFFFFFFFFFFFFULL, 0xFFFFFFFFFFFFFFFFULL
        };
        sub256(SECP_P_LE, res, Y_out);
    } else {
        fieldCopy(res, Y_out);
    }
}

// Kernel de Inicialização dos Walkers na GPU
__global__ void init_walkers_kernel(
    DeviceWalker* walkers,
    const uint64_t* tame_pub_X,
    const uint64_t* tame_pub_Y,
    uint8_t tame_pub_prefix,
    const uint64_t* range_start,
    uint32_t num_walkers,
    uint64_t seed,
    int bit_len,
    int force_wild
) {
    uint32_t gid = blockIdx.x * blockDim.x + threadIdx.x;
    if (gid >= num_walkers) return;

    DeviceWalker w;
    if (force_wild == 0) w.is_wild = 0;
    else if (force_wild == 1) w.is_wild = 1;
    else w.is_wild = (gid % 2 == 0) ? 0 : 1;

    uint64_t r0 = splitmix64_device(seed + gid * 0x9e3779b97f4a7c15ULL);
    uint64_t r1 = splitmix64_device(r0 ^ (gid * 0x140ULL));
    uint64_t r2 = splitmix64_device(r1 ^ 0xabcdefULL);

    uint64_t scalar[4] = {r0, r1, r2 & 0x0fffffffffffffffULL, 0};

    // Mask scalar para que os walkers iniciais permaneçam dentro do range do puzzle
    int max_bits = (bit_len > 1) ? (bit_len - 1) : 1;
    if (max_bits > 192) max_bits = 192;
    int limb_idx = max_bits / 64;
    int bit_rem = max_bits % 64;
    if (limb_idx < 4) {
        if (bit_rem == 0) scalar[limb_idx] = 0;
        else scalar[limb_idx] &= ((1ULL << bit_rem) - 1ULL);
        for (int i = limb_idx + 1; i < 4; ++i) scalar[i] = 0;
    }

    if (w.is_wild) {
        // Wild kangaroo: inicia em (range_start + scalar) * G
        uint64_t wild_scalar[4];
        add256(range_start, scalar, wild_scalar);
        scalarMulBaseAffine(wild_scalar, w.X, w.Y);
        fieldCopy(wild_scalar, w.dist);
    } else {
        // Tame kangaroo: inicia em K_pub + scalar * G => dist_T = scalar
        uint64_t pubY[4];
        if (tame_pub_Y[0] == 0 && tame_pub_Y[1] == 0 && tame_pub_Y[2] == 0 && tame_pub_Y[3] == 0) {
            decompress_pubkey_device(tame_pub_X, tame_pub_prefix, pubY);
        } else {
            fieldCopy(tame_pub_Y, pubY);
        }

        uint64_t tempX[4], tempY[4];
        scalarMulBaseAffine(scalar, tempX, tempY);

        ECPointA ptY, ptTemp, ptR;
        fieldCopy(tame_pub_X, ptY.X);
        fieldCopy(pubY, ptY.Y);
        ptY.infinity = false;

        fieldCopy(tempX, ptTemp.X);
        fieldCopy(tempY, ptTemp.Y);
        ptTemp.infinity = false;

        pointAddAffine(ptY, ptTemp, ptR);

        fieldCopy(ptR.X, w.X);
        fieldCopy(ptR.Y, w.Y);
        fieldCopy(scalar, w.dist);
    }
    // Iniciar Z = 1 (ponto afim -> Jacobiano)
    w.Z[0] = 1ULL;
    w.Z[1] = 0ULL;
    w.Z[2] = 0ULL;
    w.Z[3] = 0ULL;
    walkers[gid] = w;
}

// Walk Kernel executado na GPU com Warp Batch Inversion (100% Invariante e Afim)
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
    bool active = (gid < num_walkers);

    __shared__ uint64_t s_dx[256][4];
    __shared__ uint64_t s_inv[256][4];

    DeviceWalker w;
    uint64_t PX[4]{0}, PY[4]{0}, dist[4]{0};
    if (active) {
        w = walkers[gid];
        #pragma unroll
        for (int k = 0; k < 4; ++k) {
            PX[k]   = w.X[k];
            PY[k]   = w.Y[k];
            dist[k] = w.dist[k];
        }
    }

    uint32_t tid     = threadIdx.x;
    uint32_t warp_id = tid / 32;
    uint32_t lane_id = tid % 32;

    for (uint32_t step = 0; step < steps_per_launch; ++step) {
        uint32_t idx = 0;
        uint64_t JX[4]{0}, JY[4]{0}, jsize[4]{0}, dx[4]{0}, dy[4]{0};

        if (active) {
            // Seleção determinística e 100% invariante baseada na coordenada afim X
            idx = (uint32_t)(PX[0] & 31);
            #pragma unroll
            for (int k = 0; k < 4; ++k) {
                JX[k]    = c_jump_X[idx * 4 + k];
                JY[k]    = c_jump_Y[idx * 4 + k];
                jsize[k] = c_jump_sizes[idx * 4 + k];
            }
            fieldSub(JX, PX, dx);
            fieldSub(JY, PY, dy);
            #pragma unroll
            for (int k = 0; k < 4; ++k) s_dx[tid][k] = dx[k];
        } else {
            s_dx[tid][0] = 1ULL; s_dx[tid][1] = 0ULL; s_dx[tid][2] = 0ULL; s_dx[tid][3] = 0ULL;
        }

        __syncwarp();

        // Batch Inversion por Warp (32 threads) -> 1 única inversão modular por Warp!
        if (lane_id == 0) {
            uint64_t pref[32][4];
            fieldCopy(s_dx[warp_id * 32 + 0], pref[0]);
            for (int i = 1; i < 32; ++i) {
                fieldMul(pref[i - 1], s_dx[warp_id * 32 + i], pref[i]);
            }
            uint64_t invAll[4];
            fieldInv(pref[31], invAll);
            uint64_t accum[4];
            fieldCopy(invAll, accum);
            for (int i = 31; i > 0; --i) {
                fieldMul(pref[i - 1], accum, s_inv[warp_id * 32 + i]);
                fieldMul(accum, s_dx[warp_id * 32 + i], accum);
            }
            fieldCopy(accum, s_inv[warp_id * 32 + 0]);
        }

        __syncwarp();

        if (active) {
            uint64_t invdx[4], lambda[4], lambda2[4], tmp1[4], prod[4], newX[4], newY[4];
            #pragma unroll
            for (int k = 0; k < 4; ++k) invdx[k] = s_inv[tid][k];

            // lambda = dy / dx = dy * invdx
            fieldMul(dy, invdx, lambda);

            // newX = lambda^2 - PX - JX
            fieldSqr(lambda, lambda2);
            fieldSub(lambda2, PX, tmp1);
            fieldSub(tmp1, JX, newX);

            // newY = lambda * (PX - newX) - PY
            fieldSub(PX, newX, tmp1);
            fieldMul(lambda, tmp1, prod);
            fieldSub(prod, PY, newY);

            #pragma unroll
            for (int k = 0; k < 4; ++k) {
                PX[k] = newX[k];
                PY[k] = newY[k];
            }

            // Somar tamanho do salto a distancia acumulada
            add256(dist, jsize, dist);

            // DP check em coordenadas afins puras (100% invariante)
            if ((PX[0] & dp_mask) == 0ULL) {
                uint32_t out_idx = atomicAdd(out_dp_count, 1);
                if (out_idx < max_dps) {
                    DeviceDP dp;
                    #pragma unroll
                    for (int k = 0; k < 4; ++k) {
                        dp.X[k]    = PX[k];
                        dp.Y[k]    = PY[k];
                        dp.dist[k] = dist[k];
                    }
                    dp.is_wild = w.is_wild;
                    out_dps[out_idx] = dp;
                }
            }
        }
    }

    if (active) {
        #pragma unroll
        for (int k = 0; k < 4; ++k) {
            w.X[k]    = PX[k];
            w.Y[k]    = PY[k];
            w.Z[k]    = 1ULL;
            w.dist[k] = dist[k];
        }
        w.Z[1] = 0ULL; w.Z[2] = 0ULL; w.Z[3] = 0ULL;
        walkers[gid] = w;
    }
}


KangarooSolver::KangarooSolver() {}
KangarooSolver::~KangarooSolver() {}

bool KangarooSolver::initialize(const SolverJobParams& params) {
    m_params = params;
    m_stop_requested = false;
    m_keys_checked = 0;
    m_found = false;
    m_dp_database.clear();
    m_dp_database.reserve(10000000); // Pre-alocar 10M buckets para ZERO lag de rehash na CPU
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
    int mean_jump_bit = (bit_len / 2) - 3;
    if (mean_jump_bit < 2) mean_jump_bit = 2;
    int jump_start_bit = mean_jump_bit - 4;
    if (jump_start_bit < 0) jump_start_bit = 0;
    int jump_end_bit = jump_start_bit + 8;

    int default_dp = (bit_len > 80) ? 26 : std::max(4, (bit_len / 2) - 10);
    if (default_dp < 4) default_dp = 4;
    int dp_bits = m_params.kangaroo_dp_bits > 0 ? m_params.kangaroo_dp_bits : default_dp;
    uint64_t dp_mask = (1ULL << dp_bits) - 1;

    std::cout << "[Kangaroo] Bit-length do range: " << bit_len 
              << " | Saltos: 2^" << jump_start_bit << " a 2^" << jump_end_bit 
              << " | DP Bits: " << dp_bits << std::endl;

    // Gerar jump sizes no host (corrigido para inteiros de 256-bit em 4 limbs)
    for (uint32_t i = 0; i < 32; ++i) {
        int target_bit = jump_start_bit + (i % 9);
        if (target_bit < 0) target_bit = 0;
        if (target_bit > 250) target_bit = 250;

        int limb = target_bit / 64;
        int bit_shift = target_bit % 64;

        for (int k = 0; k < 4; ++k) h_jump_sizes[i * 4 + k] = 0;
        h_jump_sizes[i * 4 + limb] = (1ULL << bit_shift);
        h_jump_sizes[i * 4 + 0] += (i * 7 + 1);
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
    std::cout << "[Kangaroo] Target Pubkey X: " << formatHex256(tame_pubkey_X) << std::endl;
    std::cout << "[Kangaroo] Target Pubkey Y: " << formatHex256(tame_pubkey_Y) << std::endl;

    uint64_t *d_tame_pub_X = nullptr, *d_tame_pub_Y = nullptr, *d_range_start = nullptr;
    cudaMalloc(&d_tame_pub_X, 4 * sizeof(uint64_t));
    cudaMalloc(&d_tame_pub_Y, 4 * sizeof(uint64_t));
    cudaMalloc(&d_range_start, 4 * sizeof(uint64_t));
    cudaMemcpy(d_tame_pub_X, tame_pubkey_X, 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_tame_pub_Y, tame_pubkey_Y, 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_range_start, m_params.range_start, 4 * sizeof(uint64_t), cudaMemcpyHostToDevice);

    DeviceWalker* d_walkers = nullptr;
    cudaMalloc(&d_walkers, num_walkers * sizeof(DeviceWalker));

    uint64_t seed = (uint64_t)std::chrono::steady_clock::now().time_since_epoch().count();
    int threadsPerBlock = 256;
    int blocks = (num_walkers + threadsPerBlock - 1) / threadsPerBlock;

    uint8_t tame_pub_prefix = (pk_str.length() == 66 && pk_str[0] == '0' && pk_str[1] == '3') ? 0x03 : 0x02;

    // Alocar buffers de Distinguished Points
    DeviceDP* d_dps = nullptr;
    uint32_t* d_dp_count = nullptr;
    uint32_t max_dps = 1048576; // 1M buffer de DPs para prevenir overflow em faixas pequenas

    cudaMalloc(&d_dps, max_dps * sizeof(DeviceDP));
    cudaMalloc(&d_dp_count, sizeof(uint32_t));

    std::vector<DeviceDP> h_dps(max_dps);
    auto t_start = std::chrono::high_resolution_clock::now();
    uint32_t steps_per_launch = 512; // 512 passos por kernel launch previne TDR Watchdog e register spill

    // Fase 1: Criar Armadilhas Tame (Tame Walkers)
    init_walkers_kernel<<<blocks, threadsPerBlock>>>(
        d_walkers, d_tame_pub_X, d_tame_pub_Y, tame_pub_prefix, d_range_start, num_walkers, seed, bit_len, 0
    );
    cudaDeviceSynchronize();

    std::cout << "[Kangaroo] Fase 1: Gerando armadilhas Tame no alvo..." << std::endl;
    uint32_t tame_launches = 1; // 1 * 512 passos por Tame walker para manter a armadilha na janela ideal
    for (uint32_t step = 0; step < tame_launches; ++step) {
        uint32_t zero = 0;
        cudaMemcpy(d_dp_count, &zero, sizeof(uint32_t), cudaMemcpyHostToDevice);
        kernel_kangaroo_walk<<<blocks, threadsPerBlock>>>(
            d_walkers, num_walkers, steps_per_launch, dp_mask, d_dps, d_dp_count, max_dps
        );
        cudaDeviceSynchronize();
        uint32_t dp_count = 0;
        cudaMemcpy(&dp_count, d_dp_count, sizeof(uint32_t), cudaMemcpyDeviceToHost);
        if (dp_count > 0) {
            if (dp_count > max_dps) dp_count = max_dps;
            cudaMemcpy(h_dps.data(), d_dps, dp_count * sizeof(DeviceDP), cudaMemcpyDeviceToHost);
            std::lock_guard<std::mutex> lk(m_dp_mutex);
            for (uint32_t i = 0; i < dp_count; ++i) {
                const auto& dp = h_dps[i];
                std::array<uint64_t, 4> dp_key{dp.X[0], dp.X[1], dp.X[2], dp.X[3]};
                DPInfo info;
                info.is_wild = dp.is_wild;
                for (int k = 0; k < 4; ++k) { info.distance[k] = dp.dist[k]; info.Y[k] = dp.Y[k]; }
                m_dp_database[dp_key] = info;
            }
        }
    }
    std::cout << "[Kangaroo] Fase 1 Concluída: " << m_dp_database.size() << " armadilhas Tame armadas!" << std::endl;

    // Fase 2: Soltar Kangaroos Selvagens (Wild Walkers) para Caça
    init_walkers_kernel<<<blocks, threadsPerBlock>>>(
        d_walkers, d_tame_pub_X, d_tame_pub_Y, tame_pub_prefix, d_range_start, num_walkers, seed + 1, bit_len, 1
    );
    cudaDeviceSynchronize();

    cudaFree(d_tame_pub_X);
    cudaFree(d_tame_pub_Y);
    cudaFree(d_range_start);

    std::cout << "[Kangaroo] Fase 2: Soltando Kangaroos Selvagens para caçar..." << std::endl;

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
                std::array<uint64_t, 4> dp_key{dp.X[0], dp.X[1], dp.X[2], dp.X[3]};

                auto it = m_dp_database.find(dp_key);
                if (it != m_dp_database.end()) {
                    const auto& existing = it->second;
                    std::cout << "\n[DP MATCH DETECTADO] existing.is_wild=" << existing.is_wild 
                              << " | new.is_wild=" << dp.is_wild 
                              << " | DP X: " << std::hex << dp.X[0] << std::dec << std::endl;
                    if ((existing.is_wild ? 1 : 0) != (dp.is_wild ? 1 : 0)) {
                        uint64_t priv_key[4]{0};
                        uint64_t wild_dist[4]{0}, tame_dist[4]{0};
                        if (existing.is_wild) {
                            for (int k = 0; k < 4; ++k) { wild_dist[k] = existing.distance[k]; tame_dist[k] = dp.dist[k]; }
                        } else {
                            for (int k = 0; k < 4; ++k) { wild_dist[k] = dp.dist[k]; tame_dist[k] = existing.distance[k]; }
                        }

                        static auto ge256_host = [](const uint64_t a[4], const uint64_t b[4]) -> bool {
                            for (int i = 3; i >= 0; --i) {
                                if (a[i] > b[i]) return true;
                                if (a[i] < b[i]) return false;
                            }
                            return true;
                        };

                        const uint64_t SECP_N_LE[4] = {
                            0xBFD25E8CD0364141ULL, 0xBAAEDCE6AF48A03BULL,
                            0xFFFFFFFFFFFFFFFFULL, 0xFFFFFFFFFFFFFFFFULL
                        };

                        auto modSub256_N = [&](const uint64_t a[4], const uint64_t b[4], uint64_t out[4]) {
                            if (ge256_host(a, b)) {
                                sub256((uint64_t*)a, (uint64_t*)b, out);
                                if (ge256_host(out, SECP_N_LE)) sub256(out, SECP_N_LE, out);
                            } else {
                                uint64_t diff[4]{0};
                                sub256((uint64_t*)b, (uint64_t*)a, diff);
                                if (ge256_host(diff, SECP_N_LE)) sub256(diff, SECP_N_LE, diff);
                                sub256((uint64_t*)SECP_N_LE, diff, out);
                            }
                        };

                        auto modAdd256_N = [&](const uint64_t a[4], const uint64_t b[4], uint64_t out[4]) {
                            add256((uint64_t*)a, (uint64_t*)b, out);
                            if (ge256_host(out, SECP_N_LE)) sub256(out, SECP_N_LE, out);
                        };

                        bool same_Y = (existing.Y[0] == dp.Y[0] && existing.Y[1] == dp.Y[1] &&
                                       existing.Y[2] == dp.Y[2] && existing.Y[3] == dp.Y[3]);

                        if (same_Y) {
                            modSub256_N(wild_dist, tame_dist, priv_key);
                        } else {
                            uint64_t sum_dist[4]{0};
                            modAdd256_N(wild_dist, tame_dist, sum_dist);
                            modSub256_N(SECP_N_LE, sum_dist, priv_key);
                        }

                        // Verificação Matemática Rigorosa da Chave Privada Encontrada via GPU
                        uint64_t *d_pk=nullptr, *d_cX=nullptr, *d_cY=nullptr;
                        cudaMalloc(&d_pk, 4*sizeof(uint64_t));
                        cudaMalloc(&d_cX, 4*sizeof(uint64_t));
                        cudaMalloc(&d_cY, 4*sizeof(uint64_t));
                        cudaMemcpy(d_pk, priv_key, 4*sizeof(uint64_t), cudaMemcpyHostToDevice);

                        verify_key_kernel<<<1, 1>>>(d_pk, d_cX, d_cY);
                        cudaDeviceSynchronize();

                        uint64_t checkX[4]{0}, checkY[4]{0};
                        cudaMemcpy(checkX, d_cX, 4*sizeof(uint64_t), cudaMemcpyDeviceToHost);
                        cudaMemcpy(checkY, d_cY, 4*sizeof(uint64_t), cudaMemcpyDeviceToHost);
                        cudaFree(d_pk); cudaFree(d_cX); cudaFree(d_cY);

                        if (checkX[0] == tame_pubkey_X[0] && checkX[1] == tame_pubkey_X[1] &&
                            checkX[2] == tame_pubkey_X[2] && checkX[3] == tame_pubkey_X[3]) {
                            std::cout << "\n========================================================" << std::endl;
                            std::cout << " [SUCCESS] !!! SOLUÇÃO DO PUZZLE ENCONTRADA !!!" << std::endl;
                            std::cout << " Private Key (HEX): " << formatHex256(priv_key) << std::endl;
                            std::cout << "========================================================\n" << std::endl;

                            for (int k = 0; k < 4; ++k) m_found_private_key[k] = priv_key[k];
                            m_found = true;
                            m_stop_requested = true;
                            break;
                        }
                    }
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
    std::lock_guard<std::mutex> lk(m_dp_mutex);
    std::ofstream os(path, std::ios::binary);
    if (!os.is_open()) return false;
    uint64_t count = m_dp_database.size();
    os.write((const char*)&count, sizeof(count));
    for (const auto& kv : m_dp_database) {
        os.write((const char*)kv.first.data(), 4 * sizeof(uint64_t));
        os.write((const char*)&kv.second.is_wild, sizeof(bool));
        os.write((const char*)kv.second.distance, 4 * sizeof(uint64_t));
        os.write((const char*)kv.second.Y, 4 * sizeof(uint64_t));
    }
    return true;
}

bool KangarooSolver::load_checkpoint(const std::string& path) {
    std::lock_guard<std::mutex> lk(m_dp_mutex);
    std::ifstream is(path, std::ios::binary);
    if (!is.is_open()) return false;
    uint64_t count = 0;
    is.read((char*)&count, sizeof(count));
    for (uint64_t i = 0; i < count; ++i) {
        std::array<uint64_t, 4> key;
        DPInfo info;
        is.read((char*)key.data(), 4 * sizeof(uint64_t));
        is.read((char*)&info.is_wild, sizeof(bool));
        is.read((char*)info.distance, 4 * sizeof(uint64_t));
        is.read((char*)info.Y, 4 * sizeof(uint64_t));
        m_dp_database[key] = info;
    }
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

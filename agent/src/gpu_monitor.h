#pragma once
// =============================================================================
//  CycloneX — agent/src/gpu_monitor.h
//  Monitor de métricas de GPU usando NVML (NVIDIA Management Library).
//  Possui fallback dinâmico caso NVML não esteja instalado/disponível.
// =============================================================================

#include "../../shared/cyclone_types.h"
#include <string>
#include <vector>
#include <iostream>
#include <windows.h>

namespace cyclone {

// Definições simplificadas do NVML para carregar dinamicamente nvml.dll
typedef int nvmlReturn_t;
#define NVML_SUCCESS 0

typedef struct nvmlDevice_st* nvmlDevice_t;

typedef struct nvmlUtilization_st {
    unsigned int gpu;
    unsigned int memory;
} nvmlUtilization_t;

class GpuMonitor {
private:
    HMODULE nvml_lib_ = nullptr;
    bool nvml_initialized_ = false;
    int device_count_ = 0;
    std::vector<nvmlDevice_t> devices_;

    // Assinaturas de funções NVML
    nvmlReturn_t (*nvmlInit_v2)(void) = nullptr;
    nvmlReturn_t (*nvmlShutdown)(void) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetCount_v2)(unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetHandleByIndex_v2)(unsigned int, nvmlDevice_t*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetName)(nvmlDevice_t, char*, unsigned int) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetTemperature)(nvmlDevice_t, int, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetTemperatureThreshold)(nvmlDevice_t, int, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetClockInfo)(nvmlDevice_t, int, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetPowerUsage)(nvmlDevice_t, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetPowerManagementLimit)(nvmlDevice_t, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetMemoryInfo)(nvmlDevice_t, void*) = nullptr; // pointer to nvmlMemory_t
    nvmlReturn_t (*nvmlDeviceGetFanSpeed)(nvmlDevice_t, unsigned int*) = nullptr;
    nvmlReturn_t (*nvmlDeviceGetUtilizationRates)(nvmlDevice_t, nvmlUtilization_t*) = nullptr;

    struct nvmlMemory_t {
        unsigned long long total;
        unsigned long long free;
        unsigned long long used;
    };

public:
    GpuMonitor() = default;
    ~GpuMonitor() {
        shutdown();
    }

    bool init() {
        // Carrega nvml.dll do diretório padrão da NVIDIA
        nvml_lib_ = LoadLibraryA("nvml.dll");
        if (!nvml_lib_) {
            // Tenta caminhos alternativos
            nvml_lib_ = LoadLibraryA("C:\\Program Files\\NVIDIA Corporation\\NVSMI\\nvml.dll");
        }

        if (!nvml_lib_) {
            std::cout << "[GPU Monitor] nvml.dll not found. Running in simulated fallback mode." << std::endl;
            return false;
        }

        // Resolver símbolos
        nvmlInit_v2 = (nvmlReturn_t(*)(void))GetProcAddress(nvml_lib_, "nvmlInit_v2");
        nvmlShutdown = (nvmlReturn_t(*)(void))GetProcAddress(nvml_lib_, "nvmlShutdown");
        nvmlDeviceGetCount_v2 = (nvmlReturn_t(*)(unsigned int*))GetProcAddress(nvml_lib_, "nvmlDeviceGetCount_v2");
        nvmlDeviceGetHandleByIndex_v2 = (nvmlReturn_t(*)(unsigned int, nvmlDevice_t*))GetProcAddress(nvml_lib_, "nvmlDeviceGetHandleByIndex_v2");
        nvmlDeviceGetName = (nvmlReturn_t(*)(nvmlDevice_t, char*, unsigned int))GetProcAddress(nvml_lib_, "nvmlDeviceGetName");
        nvmlDeviceGetTemperature = (nvmlReturn_t(*)(nvmlDevice_t, int, unsigned int*))GetProcAddress(nvml_lib_, "nvmlDeviceGetTemperature");
        nvmlDeviceGetClockInfo = (nvmlReturn_t(*)(nvmlDevice_t, int, unsigned int*))GetProcAddress(nvml_lib_, "nvmlDeviceGetClockInfo");
        nvmlDeviceGetPowerUsage = (nvmlReturn_t(*)(nvmlDevice_t, unsigned int*))GetProcAddress(nvml_lib_, "nvmlDeviceGetPowerUsage");
        nvmlDeviceGetMemoryInfo = (nvmlReturn_t(*)(nvmlDevice_t, void*))GetProcAddress(nvml_lib_, "nvmlDeviceGetMemoryInfo");
        nvmlDeviceGetFanSpeed = (nvmlReturn_t(*)(nvmlDevice_t, unsigned int*))GetProcAddress(nvml_lib_, "nvmlDeviceGetFanSpeed");
        nvmlDeviceGetUtilizationRates = (nvmlReturn_t(*)(nvmlDevice_t, nvmlUtilization_t*))GetProcAddress(nvml_lib_, "nvmlDeviceGetUtilizationRates");

        if (!nvmlInit_v2 || nvmlInit_v2() != NVML_SUCCESS) {
            std::cout << "[GPU Monitor] nvmlInit failed. Using simulated fallback mode." << std::endl;
            return false;
        }

        nvml_initialized_ = true;
        unsigned int count = 0;
        if (nvmlDeviceGetCount_v2(&count) == NVML_SUCCESS && count > 0) {
            device_count_ = (int)count;
            devices_.resize(device_count_);
            for (int i = 0; i < device_count_; ++i) {
                nvmlDeviceGetHandleByIndex_v2(i, &devices_[i]);
            }
            std::cout << "[GPU Monitor] NVIDIA Management Library loaded successfully. Detected " << device_count_ << " GPU(s)." << std::endl;
        }
        return true;
    }

    void shutdown() {
        if (nvml_initialized_ && nvmlShutdown) {
            nvmlShutdown();
            nvml_initialized_ = false;
        }
        if (nvml_lib_) {
            FreeLibrary(nvml_lib_);
            nvml_lib_ = nullptr;
        }
    }

    int get_device_count() const {
        return nvml_initialized_ ? device_count_ : 1; // simulation returns 1 fake GPU
    }

    CxGpuMetrics get_metrics(int gpu_id) {
        CxGpuMetrics m{};
        m.gpu_id = gpu_id;
        m.job_running = 0;

        if (!nvml_initialized_ || gpu_id >= (int)devices_.size()) {
            // Simulated Fallback Mode (CPU simulation of an RTX 4070 Ti)
            strcpy_s(m.name, sizeof(m.name), "NVIDIA GeForce RTX 4070 Ti (Simulated)");
            m.temp_c = 68.0f + (float)(rand() % 5) - 2.5f;
            m.hotspot_c = m.temp_c + 11.2f;
            m.clock_mhz = 2610;
            m.mem_clock_mhz = 10500;
            m.vram_total = 12LL * 1024 * 1024 * 1024;
            m.vram_used = 4LL * 1024 * 1024 * 1024 + (rand() % 200) * 1024 * 1024;
            m.power_w = 185.0f + (float)(rand() % 20) - 10.0f;
            m.power_limit_w = 285.0f;
            m.fan_pct = 55;
            m.utilization_pct = 98.0f;
            m.speed_mkeys = 2450.0; // ~2.45 GKeys/s
            return m;
        }

        nvmlDevice_t dev = devices_[gpu_id];
        
        // Obter nome
        char name_buf[128];
        if (nvmlDeviceGetName(dev, name_buf, sizeof(name_buf)) == NVML_SUCCESS) {
            strcpy_s(m.name, sizeof(m.name), name_buf);
        }

        // Temperatura
        unsigned int temp = 0;
        if (nvmlDeviceGetTemperature(dev, 0, &temp) == NVML_SUCCESS) {
            m.temp_c = (float)temp;
            m.hotspot_c = m.temp_c + 10.0f; // NVML API para hotspot varia, usamos aproximação caso indisponível
        }

        // Clock
        unsigned int clock = 0;
        if (nvmlDeviceGetClockInfo(dev, 0, &clock) == NVML_SUCCESS) {
            m.clock_mhz = clock;
        }

        // Power Draw
        unsigned int power = 0;
        if (nvmlDeviceGetPowerUsage(dev, &power) == NVML_SUCCESS) {
            m.power_w = (float)power / 1000.0f; // NVML retorna em milliwatts
        }
        m.power_limit_w = 300.0f; // Default limite aproximado

        // VRAM
        nvmlMemory_t mem{};
        if (nvmlDeviceGetMemoryInfo(dev, &mem) == NVML_SUCCESS) {
            m.vram_total = mem.total;
            m.vram_used = mem.used;
        }

        // Fans
        unsigned int fan = 0;
        if (nvmlDeviceGetFanSpeed(dev, &fan) == NVML_SUCCESS) {
            m.fan_pct = fan;
        }

        // Utilization rates
        nvmlUtilization_t util{};
        if (nvmlDeviceGetUtilizationRates(dev, &util) == NVML_SUCCESS) {
            m.utilization_pct = (float)util.gpu;
        }

        return m;
    }
};

} // namespace cyclone

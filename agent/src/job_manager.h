#pragma once
// =============================================================================
//  CycloneX — agent/src/job_manager.h
//  Gerenciador de execução dos Jobs do Core CUDA e gravação de checkpoints.
// =============================================================================

#include "../../shared/cyclone_types.h"
#include "../../core/include/cyclone_core.h"
#include "database.h"
#include "gpu_monitor.h"
#include <thread>
#include <mutex>
#include <atomic>
#include <vector>
#include <iostream>

namespace cyclone {

class JobManager {
private:
    std::mutex mtx_;
    CxJobHandle* current_job_ = nullptr;
    std::thread runner_thread_;
    std::atomic<bool> is_running_{false};
    Database* db_ = nullptr;
    GpuMonitor* monitor_ = nullptr;

    CxCoreJobParams current_params_{};
    CxCoreResult current_result_{};

    // Callback de progresso do Core
    static void on_progress(const char* job_id, double speed_mkeys, uint64_t keys_checked, uint64_t chunks_done, void* user_data) {
        JobManager* self = (JobManager*)user_data;
        std::lock_guard<std::mutex> lk(self->mtx_);
        
        // Log & Telemetria no banco
        CxTelemetryRecord tr{};
        tr.timestamp = time(nullptr);
        tr.gpu_id = 0;
        strcpy_s(tr.gpu_name, "GPU-0");
        tr.speed_mkeys = speed_mkeys;
        tr.chunks_done = chunks_done;
        strcpy_s(tr.job_id, job_id);

        if (self->monitor_) {
            auto metrics = self->monitor_->get_metrics(0);
            tr.temp_c = metrics.temp_c;
            tr.hotspot_c = metrics.hotspot_c;
            tr.clock_mhz = metrics.clock_mhz;
            tr.vram_used = metrics.vram_used;
            tr.vram_total = metrics.vram_total;
            tr.power_w = metrics.power_w;
            tr.fan_pct = metrics.fan_pct;
        }

        if (self->db_) {
            self->db_->insert_telemetry(tr);
        }
    }

public:
    JobManager(Database* db, GpuMonitor* monitor) : db_(db), monitor_(monitor) {}
    ~JobManager() {
        stop_active_job();
    }

    bool submit_job(const CxJobParams& jp) {
        std::lock_guard<std::mutex> lk(mtx_);
        if (is_running_) {
            std::cout << "[Job Manager] Another job is currently running. Submission ignored." << std::endl;
            return false;
        }

        // Mapear parâmetros da struct compartilhada para a do core
        memset(&current_params_, 0, sizeof(current_params_));
        strcpy_s(current_params_.id, jp.id);
        strcpy_s(current_params_.plugin, jp.plugin);
        current_params_.mode = (int)jp.mode;
        memcpy(current_params_.range_start, jp.range_start, 32);
        memcpy(current_params_.range_end, jp.range_end, 32);
        memcpy(current_params_.target_hash160, jp.target_hash160, 20);
        current_params_.checkpoint_interval = jp.checkpoint_interval;
        current_params_.max_gpus = jp.max_gpus;
        current_params_.batch_size = jp.batch_size ? jp.batch_size : 128;
        current_params_.batches_per_sm = jp.batches_per_sm ? jp.batches_per_sm : 8;
        current_params_.slices_per_launch = jp.slices_per_launch ? jp.slices_per_launch : 64;

        current_job_ = cx_job_create(&current_params_);
        if (!current_job_) {
            std::cerr << "[Job Manager] Failed to create job handle." << std::endl;
            return false;
        }

        cx_job_set_progress_cb(current_job_, on_progress, this);

        is_running_ = true;
        runner_thread_ = std::thread([this]() {
            int status = cx_job_run(current_job_, &current_result_);
            
            std::lock_guard<std::mutex> lkl(mtx_);
            is_running_ = false;

            if (db_) {
                CxResult res{};
                res.status = (CxStatus)status;
                strcpy_s(res.job_id, current_result_.job_id);
                res.keys_checked = current_result_.keys_checked;
                res.elapsed_seconds = current_result_.elapsed_seconds;
                res.speed_mkeys = current_result_.speed_mkeys;
                res.found = current_result_.found;
                
                if (res.found) {
                    memcpy(res.private_key, current_result_.private_key, 32);
                    memcpy(res.pub_x, current_result_.pub_x, 32);
                    memcpy(res.pub_y, current_result_.pub_y, 32);
                    memcpy(res.hash160, current_result_.hash160, 20);

                    // Salvar resultado encontrado
                    db_->insert_result(res, "localhost", "GPU-0", std::to_string(res.elapsed_seconds) + "s");
                    std::cout << "[Job Manager] !!! MATCH FOUND !!! Job: " << res.job_id << std::endl;
                } else {
                    std::cout << "[Job Manager] Job finished: " << cx_status_str(res.status) << std::endl;
                }
            }

            cx_job_destroy(current_job_);
            current_job_ = nullptr;
        });

        if (db_) {
            db_->save_job(jp, "running");
        }

        return true;
    }

    void stop_active_job() {
        {
            std::lock_guard<std::mutex> lk(mtx_);
            if (current_job_) {
                cx_job_cancel(current_job_);
            }
        }
        if (runner_thread_.joinable()) {
            runner_thread_.join();
        }
    }

    bool is_job_running() {
        return is_running_.load();
    }

    CxCoreResult get_current_result() {
        std::lock_guard<std::mutex> lk(mtx_);
        return current_result_;
    }
};

} // namespace cyclone

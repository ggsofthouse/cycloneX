#pragma once
// =============================================================================
//  CycloneX — agent/src/database.h
//  Wrapper simples de banco de dados SQLite para telemetria, jobs e checkpoints.
// =============================================================================

#include "../../vendor/sqlite3.h"
#include "../../shared/cyclone_types.h"
#include <string>
#include <vector>
#include <mutex>
#include <iostream>

namespace cyclone {

class Database {
private:
    sqlite3* db_ = nullptr;
    std::mutex mtx_;

    void execute(const std::string& sql) {
        char* errMsg = nullptr;
        int rc = sqlite3_exec(db_, sql.c_str(), nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK) {
            std::cerr << "[DB Error] " << (errMsg ? errMsg : "Unknown error") << " executing: " << sql << std::endl;
            if (errMsg) sqlite3_free(errMsg);
        }
    }

public:
    Database() = default;
    ~Database() {
        close();
    }

    bool open(const std::string& db_path) {
        std::lock_guard<std::mutex> lk(mtx_);
        int rc = sqlite3_open(db_path.c_str(), &db_);
        if (rc != SQLITE_OK) {
            std::cerr << "[DB] Cannot open database: " << sqlite3_errmsg(db_) << std::endl;
            return false;
        }

        // Criar tabelas
        execute(
            "CREATE TABLE IF NOT EXISTS jobs ("
            "id TEXT PRIMARY KEY, "
            "plugin TEXT, "
            "mode TEXT, "
            "range_start TEXT, "
            "range_end TEXT, "
            "target_hash160 TEXT, "
            "status TEXT, "
            "priority INTEGER, "
            "checkpoint_interval INTEGER, "
            "created_at INTEGER"
            ");"
        );

        execute(
            "CREATE TABLE IF NOT EXISTS checkpoints ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "job_id TEXT, "
            "path TEXT, "
            "current_pos TEXT, "
            "chunks_done INTEGER, "
            "created_at INTEGER"
            ");"
        );

        execute(
            "CREATE TABLE IF NOT EXISTS telemetry ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "gpu_id INTEGER, "
            "gpu_name TEXT, "
            "temp_c REAL, "
            "hotspot_c REAL, "
            "clock_mhz INTEGER, "
            "vram_used INTEGER, "
            "vram_total INTEGER, "
            "power_w REAL, "
            "fan_pct INTEGER, "
            "speed_mkeys REAL, "
            "chunks_done INTEGER, "
            "timestamp INTEGER"
            ");"
        );

        execute(
            "CREATE TABLE IF NOT EXISTS logs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "level TEXT, "
            "source TEXT, "
            "message TEXT, "
            "timestamp INTEGER"
            ");"
        );

        execute(
            "CREATE TABLE IF NOT EXISTS results ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "job_id TEXT, "
            "machine TEXT, "
            "gpu TEXT, "
            "private_key TEXT, "
            "public_key TEXT, "
            "address TEXT, "
            "keys_checked INTEGER, "
            "duration TEXT, "
            "timestamp INTEGER"
            ");"
        );

        return true;
    }

    void close() {
        std::lock_guard<std::mutex> lk(mtx_);
        if (db_) {
            sqlite3_close(db_);
            db_ = nullptr;
        }
    }

    void save_job(const CxJobParams& job, const std::string& status) {
        std::lock_guard<std::mutex> lk(mtx_);
        std::string sql = "INSERT OR REPLACE INTO jobs (id, plugin, mode, range_start, range_end, target_hash160, status, priority, checkpoint_interval, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'));";
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, job.id, -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, job.plugin, -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 3, job.mode == CX_MODE_RANDOM ? "random" : "sequential", -1, SQLITE_TRANSIENT);
            
            char hex_start[65], hex_end[65], hex_target[41];
            // Hex conversions
            // (Utilizaremos placeholders simplificados nas strings para evitar acoplamento no db)
            sqlite3_bind_text(stmt, 4, "0x0000000000000000", -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 5, "0xffffffffffffffff", -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 6, "target_placeholder", -1, SQLITE_TRANSIENT);

            sqlite3_bind_text(stmt, 7, status.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_int(stmt, 8, job.priority);
            sqlite3_bind_int(stmt, 9, job.checkpoint_interval);
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        }
    }

    void insert_telemetry(const CxTelemetryRecord& t) {
        std::lock_guard<std::mutex> lk(mtx_);
        std::string sql = "INSERT INTO telemetry (gpu_id, gpu_name, temp_c, hotspot_c, clock_mhz, vram_used, vram_total, power_w, fan_pct, speed_mkeys, chunks_done, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);";
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_int(stmt, 1, t.gpu_id);
            sqlite3_bind_text(stmt, 2, t.gpu_name, -1, SQLITE_TRANSIENT);
            sqlite3_bind_double(stmt, 3, t.temp_c);
            sqlite3_bind_double(stmt, 4, t.hotspot_c);
            sqlite3_bind_int(stmt, 5, t.clock_mhz);
            sqlite3_bind_int64(stmt, 6, t.vram_used);
            sqlite3_bind_int64(stmt, 7, t.vram_total);
            sqlite3_bind_double(stmt, 8, t.power_w);
            sqlite3_bind_int(stmt, 9, t.fan_pct);
            sqlite3_bind_double(stmt, 10, t.speed_mkeys);
            sqlite3_bind_int64(stmt, 11, t.chunks_done);
            sqlite3_bind_int64(stmt, 12, t.timestamp);
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        }
    }

    void insert_log(const CxLogEntry& log) {
        std::lock_guard<std::mutex> lk(mtx_);
        std::string sql = "INSERT INTO logs (level, source, message, timestamp) VALUES (?, ?, ?, ?);";
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, cx_log_level_str(log.level), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, log.source, -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 3, log.message, -1, SQLITE_TRANSIENT);
            sqlite3_bind_int64(stmt, 4, log.timestamp);
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        }
    }

    void insert_result(const CxResult& r, const std::string& machine, const std::string& gpu, const std::string& duration) {
        std::lock_guard<std::mutex> lk(mtx_);
        std::string sql = "INSERT INTO results (job_id, machine, gpu, private_key, public_key, address, keys_checked, duration, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'));";
        sqlite3_stmt* stmt = nullptr;
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &stmt, nullptr) == SQLITE_OK) {
            sqlite3_bind_text(stmt, 1, r.job_id, -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 2, machine.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 3, gpu.c_str(), -1, SQLITE_TRANSIENT);
            
            // Simples formatação de exemplo para as chaves
            sqlite3_bind_text(stmt, 4, "priv_placeholder", -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 5, "pub_placeholder", -1, SQLITE_TRANSIENT);
            sqlite3_bind_text(stmt, 6, "addr_placeholder", -1, SQLITE_TRANSIENT);
            
            sqlite3_bind_int64(stmt, 7, r.keys_checked);
            sqlite3_bind_text(stmt, 8, duration.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        }
    }
};

} // namespace cyclone

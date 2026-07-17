# =============================================================================
//  CycloneX — agent/CMakeLists.txt
// =============================================================================

cmake_minimum_required(VERSION 3.18)
project(cyclone_agent LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# SQLite mock integration (compilação mock simples do amalgamation)
set(SQLITE_SOURCES
    ../vendor/sqlite3.c
)

# Definir código do mock do amalgamation SQLite para compilar rapidamente
# sem requerer download externo do arquivo sqlite3.c inteiro de 8MB.
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../vendor/sqlite3.c")
    file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/../vendor/sqlite3.c" [=[
        #include "../vendor/sqlite3.h"
        #include <stdlib.h>
        int sqlite3_open(const char *filename, sqlite3 **ppDb) { return 0; }
        int sqlite3_close(sqlite3* db) { return 0; }
        int sqlite3_exec(sqlite3* db, const char *sql, int (*cb)(void*,int,char**,char**), void *arg, char **err) { return 0; }
        int sqlite3_prepare_v2(sqlite3 *db, const char *sql, int n, sqlite3_stmt **st, const char **tail) { return 0; }
        int sqlite3_step(sqlite3_stmt* st) { return 101; }
        int sqlite3_finalize(sqlite3_stmt *st) { return 0; }
        int sqlite3_reset(sqlite3_stmt *st) { return 0; }
        int sqlite3_bind_int(sqlite3_stmt* st, int i, int v) { return 0; }
        int sqlite3_bind_int64(sqlite3_stmt* st, int i, long long int v) { return 0; }
        int sqlite3_bind_double(sqlite3_stmt* st, int i, double v) { return 0; }
        int sqlite3_bind_text(sqlite3_stmt* st, int i, const char* v, int n, void(*f)(void*)) { return 0; }
        int sqlite3_bind_null(sqlite3_stmt* st, int i) { return 0; }
        int sqlite3_column_int(sqlite3_stmt* st, int c) { return 0; }
        long long int sqlite3_column_int64(sqlite3_stmt* st, int c) { return 0; }
        double sqlite3_column_double(sqlite3_stmt* st, int c) { return 0.0; }
        const unsigned char *sqlite3_column_text(sqlite3_stmt* st, int c) { return (const unsigned char*)""; }
        int sqlite3_column_bytes(sqlite3_stmt* st, int c) { return 0; }
        const char *sqlite3_errmsg(sqlite3* db) { return ""; }
        void sqlite3_free(void* p) { free(p); }
    ]=])
endif()

add_executable(cyclone_agent
    src/main.cpp
    ${SQLITE_SOURCES}
)

target_link_libraries(cyclone_agent PRIVATE
    cyclone_core
    Ws2_32
)

target_include_directories(cyclone_agent PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/../shared
    ${CMAKE_CURRENT_SOURCE_DIR}/../vendor
)

# =============================================================================
//  CycloneX — core/CMakeLists.txt
// =============================================================================

cmake_minimum_required(VERSION 3.18)
project(cyclone_core LANGUAGES CXX CUDA)

set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED ON)

set(CORE_SOURCES
    kernels/ecc_kernel.cu
    scheduler/gpu_runner.cu
    crypto/hash_kernels.cu
)

add_library(cyclone_core STATIC ${CORE_SOURCES})

target_include_directories(cyclone_core PUBLIC 
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

set_target_properties(cyclone_core PROPERTIES
    CUDA_SEPARABLE_COMPILATION ON
    CUDA_RESOLVE_DEVICE_SYMBOLS ON
)

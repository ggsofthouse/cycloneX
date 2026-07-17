# =============================================================================
//  CycloneX — CMakeLists.txt (root)
// =============================================================================

cmake_minimum_required(VERSION 3.18)
project(CycloneX LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Procurar compilador CUDA para compilar a biblioteca core
include(CheckLanguage)
check_language(CUDA)

if(CMAKE_CUDA_COMPILER)
    enable_language(CUDA)
    add_subdirectory(core)
else()
    message(WARNING "CUDA compiler not found. Core library will compile in emulation mode.")
    # Adicionar stub/mock para o core em sistemas sem nvcc
    add_library(cyclone_core STATIC 
        core/scheduler/gpu_runner.cu
        core/kernels/ecc_kernel.cu
    )
    set_target_properties(cyclone_core PROPERTIES
        LINKER_LANGUAGE CXX
    )
    target_include_directories(cyclone_core PUBLIC core/include)
endif()

add_subdirectory(agent)
add_subdirectory(launcher)

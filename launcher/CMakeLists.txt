# =============================================================================
//  CycloneX — launcher/CMakeLists.txt
// =============================================================================

cmake_minimum_required(VERSION 3.18)
project(cyclone_launcher LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(cyclone_launcher
    src/main.cpp
)

target_link_libraries(cyclone_launcher PRIVATE
    Shell32
)

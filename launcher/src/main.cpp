# =============================================================================
//  CycloneX — launcher/src/main.cpp
//  Iniciador visual (CLI amigável) que verifica driver, CUDA e spawna o Agent.
// =============================================================================

#include <iostream>
#include <windows.h>
#include <string>
#include <thread>
#include <chrono>

void check_driver() {
    std::cout << "[Launcher] 1/3 Checking NVIDIA Driver... ";
    HMODULE nv = LoadLibraryA("napi.dll");
    if (!nv) nv = LoadLibraryA("nvapi64.dll");
    
    if (nv) {
        std::cout << "OK (Driver found)" << std::endl;
        FreeLibrary(nv);
    } else {
        std::cout << "WARN (Driver not found, running emulator mode)" << std::endl;
    }
}

void check_cuda() {
    std::cout << "[Launcher] 2/3 Checking CUDA Runtime... ";
    HMODULE cu = LoadLibraryA("cudart64_12.dll");
    if (!cu) cu = LoadLibraryA("cudart64_11.dll");
    if (!cu) cu = LoadLibraryA("cudart.dll");

    if (cu) {
        std::cout << "OK (CUDA Toolkit active)" << std::endl;
        FreeLibrary(cu);
    } else {
        std::cout << "WARN (CUDA missing on system path, virtualizing GPU)" << std::endl;
    }
}

void launch_agent() {
    std::cout << "[Launcher] 3/3 Launching CycloneX Agent daemon..." << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(800));

    STARTUPINFOA si{};
    PROCESS_INFORMATION pi{};
    si.cb = sizeof(si);

    // Spawn agent process
    BOOL success = CreateProcessA(
        "cyclone_agent.exe",
        nullptr, nullptr, nullptr, FALSE,
        CREATE_NEW_CONSOLE,
        nullptr, nullptr, &si, &pi
    );

    if (success) {
        std::cout << "[Launcher] Agent started successfully in background. PID: " << pi.dwProcessId << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        
        // Auto-open browser dashboard
        ShellExecuteA(nullptr, "open", "http://localhost:8080", nullptr, nullptr, SW_SHOWNORMAL);
        
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        std::cerr << "[Launcher] ERROR: Could not spawn cyclone_agent.exe. Ensure it has compiled and is in path." << std::endl;
    }
}

int main() {
    std::cout << "=============================================" << std::endl;
    std::cout << "           CycloneX Launcher Engine          " << std::endl;
    std::cout << "=============================================" << std::endl;

    check_driver();
    check_cuda();
    launch_agent();

    std::cout << "\nLauncher process finishing. You can safely close this window." << std::endl;
    std::this_thread::sleep_for(std::chrono::milliseconds(3000));
    return 0;
}

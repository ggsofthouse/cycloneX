@echo off

rem Localizar VS
set VS_PATH=
for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -property installationPath`) do (
    set VS_PATH=%%i
)

if "%VS_PATH%"=="" (
    echo Visual Studio not found
    exit /b 1
)

echo VS Path: %VS_PATH%

rem Carregar vcvars
call "%VS_PATH%\VC\Auxiliary\Build\vcvarsall.bat" x64

rem Compilar Agent
cl.exe /O2 /EHsc /std:c++20 /I"shared" /I"vendor" /I"core/include" /I"agent/src" agent/src/main.cpp vendor/sqlite3.c core/scheduler/gpu_runner.cu core/kernels/ecc_kernel.cu /Fe"cyclone_agent.exe" /link Ws2_32.lib Shell32.lib

if %ERRORLEVEL% NEQ 0 (
    echo Compilation failed
    exit /b 1
)

rem Compilar Launcher
cl.exe /O2 /EHsc /std:c++20 launcher/src/main.cpp /Fe"cyclone_launcher.exe" /link Shell32.lib

del *.obj
echo Build success!

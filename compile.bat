@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo          CycloneX Real GPU Compilation Engine
echo ========================================================
echo.

:: Procurar vcvarsall.bat
set "VCVARS="
if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
) else if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"
) else if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat" (
    set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat"
)

if "%VCVARS%"=="" (
    echo [ERROR] VC++ Compiler Environment not found. Ensure Visual Studio is installed.
    exit /b 1
)

echo [1/3] Loading MSVC variables from: %VCVARS%
call "%VCVARS%" x64 >nul

echo [2/3] Checking nvcc compiler (CUDA Toolkit)...
where nvcc.exe >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] nvcc compiler not found on PATH. Ensure CUDA Toolkit is installed.
    exit /b 1
)
nvcc --version | findstr /i "release"

echo [3/3] Compiling CUDACyclone.cu real GPU solver...
cd CUDACyclone-main

rem Adicionado -rdc=true para habilitar relocatable device code e resolver chamadas de kernel cruzadas
nvcc -O3 -std=c++17 -rdc=true -o CUDACyclone.exe CUDACyclone.cu CUDAHash.cu -lversion

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] nvcc compilation failed!
    exit /b 1
)

echo.
echo ========================================================
echo [SUCCESS] Real CUDACyclone.exe compiled successfully!
echo ========================================================
cd ..
copy CUDACyclone-main\CUDACyclone.exe CUDACyclone.exe /y >nul

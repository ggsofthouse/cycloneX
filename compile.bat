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

echo [3/3] Compilando CUDACyclone.cu com flags otimizadas para T4 e GPUs modernas...
cd CUDACyclone-main

rem Flags adicionadas:
rem   --use_fast_math     : melhor scheduling de instrucoes (seguro para codigo inteiro)
rem   -Xptxas -O3         : otimizador PTX nivel 3
rem   -gencode sm_75      : Tesla T4 (Kaggle/Colab) - evita JIT na primeira execucao
rem   -gencode sm_86      : RTX 30xx (Ampere)
rem   -gencode sm_89      : RTX 40xx (Ada Lovelace)
nvcc -O3 -std=c++17 -rdc=true ^
  --use_fast_math ^
  -Xptxas -O3 ^
  -gencode arch=compute_75,code=sm_75 ^
  -gencode arch=compute_86,code=sm_86 ^
  -gencode arch=compute_89,code=sm_89 ^
  -o CUDACyclone.exe CUDACyclone.cu CUDAHash.cu -lversion

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

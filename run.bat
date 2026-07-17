@echo off
chcp 65001 > nul
title CycloneX v2.0 - Distributed GPU Compute Platform
echo.
echo  ============================================================
echo   CycloneX Distributed Engine  v2.0
echo   Powered by Real CUDA + Python Agent
echo  ============================================================
echo.

REM Verificar se Python está instalado
python --version > nul 2>&1
if errorlevel 1 (
    echo  [ERRO] Python nao encontrado! Instale Python 3.10+
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Verificar se CUDACyclone.exe existe
if not exist "CUDACyclone.exe" (
    echo  [AVISO] CUDACyclone.exe nao encontrado na pasta!
    echo          Coloque o executavel aqui: %cd%\CUDACyclone.exe
    echo.
)

echo  Iniciando servidor e job CUDA automaticamente...
echo  Dashboard: http://localhost:8080
echo.
echo  Pressione Ctrl+C para parar.
echo.

python cyclone_agent.py
pause

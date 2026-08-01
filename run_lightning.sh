#!/bin/bash
# =================================================================
# CycloneX — Script de Execução Dedicado para Lightning.ai / Linux
# Uso: bash run_lightning.sh
# =================================================================

set -e

echo "==================================================================="
echo " 🦘 CycloneX Worker v4.0 — Lightning.ai / Linux GPU"
echo " Motor: RCKangaroo SOTA K=1.15 (auto-compilado via NVCC/CMake)"
echo "==================================================================="

# Garantir dependências de compilação no Linux se não existirem
if ! command -v cmake &> /dev/null; then
    echo "📦 Instalando dependências de build (cmake)..."
    apt-get update -qq && apt-get install -y -qq cmake build-essential || true
fi

# Executa o worker principal
python3 cyclone_worker.py --server http://valyrafi.com.br --name Lightning_GPU "$@"

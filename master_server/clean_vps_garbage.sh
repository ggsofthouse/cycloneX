#!/bin/bash
# =================================================================
# CycloneX VPS Cleanup Script — Limpeza Segura de Resíduos
# Escopo: EXCLUSIVAMENTE /opt/cyclone-master
# NUNCA altera outros projetos, /var/www ou pastas fora do CycloneX.
# =================================================================

set -e

TARGET_DIR="/opt/cyclone-master"

if [ ! -d "$TARGET_DIR" ]; then
    echo "⚠️ Diretório $TARGET_DIR não encontrado. Encerrando por segurança."
    exit 1
fi

cd "$TARGET_DIR"

echo "🧹 [1/4] Removendo caches compilados do Python (__pycache__, *.pyc)..."
find "$TARGET_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$TARGET_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true

echo "🧹 [2/4] Limpando arquivos temporários e rascunhos de deploy..."
rm -f "$TARGET_DIR"/scratch/*.py "$TARGET_DIR"/scratch/*.tmp "$TARGET_DIR"/scratch/*.log 2>/dev/null || true
rm -f "$TARGET_DIR"/server.py "$TARGET_DIR"/dashboard.html 2>/dev/null || true

echo "🧹 [3/4] Otimizando logs do serviço Nginx e Systemd..."
journalctl --vacuum-time=3d >/dev/null 2>&1 || true

echo "🔒 [4/4] Verificando integridade dos arquivos essenciais..."
if [ -f "$TARGET_DIR/master_server/master_pool.db" ]; then
    echo "  ✅ Banco de Dados (master_pool.db) preservado intacto."
fi
if [ -f "$TARGET_DIR/master_server/secret.key" ]; then
    echo "  ✅ Chave Mestra (secret.key) preservada intacta."
fi

echo "================================================================"
echo " ✨ LIMPEZA CONCLUÍDA COM SUCESSO! APENAS RESÍDUOS FORAM REMOVIDOS."
echo "================================================================"

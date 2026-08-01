"""
CycloneX — Script dedicado para Google Colab / Kaggle (sessões longas)
Usa o Worker v4.0 com RCKangaroo SOTA K=1.15 como motor primário.
Cole este arquivo em uma célula e execute com: !python3 run_kaggle.py
"""

import os
import sys
import subprocess

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SERVER = "http://valyrafi.com.br"
WORKER_NAME = "Colab_Kaggle_GPU"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

print("=" * 60)
print("  🦘 CycloneX Worker v4.0 — Colab/Kaggle Launcher")
print("  Motor: RCKangaroo SOTA K=1.15 (auto-compilado)")
print("=" * 60, flush=True)

# Garante que o worker principal existe
worker_script = os.path.join(REPO_DIR, "cyclone_worker.py")
if not os.path.exists(worker_script):
    print("❌ cyclone_worker.py não encontrado. Clone o repositório primeiro.")
    sys.exit(1)

# Delega para o worker principal com parâmetros de Colab/Kaggle
cmd = [
    sys.executable,
    worker_script,
    "--server", SERVER,
    "--name",   WORKER_NAME,
    "--gpu",    "0",
]

print(f"🚀 Iniciando: {' '.join(cmd)}", flush=True)
os.execv(sys.executable, cmd)

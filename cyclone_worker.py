#!/usr/bin/env python3
"""
CycloneX Worker Client — Conecta qualquer GPU ao Master Server via CMD/Terminal
Uso: python cyclone_worker.py --server https://valyrafi.com.br --name MinhaRTX4090
"""

import os
import sys
import time
import argparse
import subprocess
import re
import uuid
import json
import urllib.request
import urllib.parse

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CUDA_DIR = os.path.join(REPO_DIR, "CUDACyclone-main")

def resolve_cuda_exe():
    if sys.platform == "win32":
        exe = os.path.join(REPO_DIR, "CUDACyclone.exe")
        if os.path.exists(exe): return exe
        exe_sub = os.path.join(CUDA_DIR, "CUDACyclone.exe")
        if os.path.exists(exe_sub): return exe_sub
        return "CUDACyclone.exe"
    else:
        # Linux / Colab / Kaggle
        bin_paths = [
            os.path.join(REPO_DIR, "CUDACyclone"),
            os.path.join(CUDA_DIR, "CUDACyclone"),
            os.path.join(REPO_DIR, "CUDACyclone.exe")
        ]
        for p in bin_paths:
            if os.path.exists(p):
                os.chmod(p, 0o755)
                return p
        
        # Se o binário não existir no Linux, compila automaticamente com 'make'
        print("🛠️ Binário Linux não encontrado. Compilando CUDACyclone via NVCC...", flush=True)
        if os.path.exists(CUDA_DIR):
            res = subprocess.run(["make"], cwd=CUDA_DIR)
            compiled = os.path.join(CUDA_DIR, "CUDACyclone")
            if os.path.exists(compiled):
                os.chmod(compiled, 0o755)
                return compiled
        return "./CUDACyclone"

CUDA_EXE = resolve_cuda_exe()

def http_post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'CycloneX-Worker/3.0'}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))

def main():
    parser = argparse.ArgumentParser(description="CycloneX Pool Worker Client")
    parser.add_argument("--server", type=str, default="https://valyrafi.com.br", help="URL do Master Server (ex: https://valyrafi.com.br ou http://179.197.231.166:8000)")
    parser.add_argument("--name", type=str, default=f"Worker-{uuid.uuid4().hex[:6]}", help="Nome/ID do Nó")
    parser.add_argument("--gpu", type=int, default=0, help="ID da GPU local")
    args = parser.parse_args()

    server_url = args.server.rstrip('/')
    worker_id = f"{args.name}-{uuid.uuid4().hex[:8]}"

    print("================================================================")
    print(" 🦘 CYCLONEX WORKER CLIENT — CONECTANDO À POOL")
    print("================================================================")
    print(f"Master Server : {server_url}")
    print(f"Nome do Nó    : {args.name}")
    print(f"ID do Worker  : {worker_id}")
    print("----------------------------------------------------------------", flush=True)

    while True:
        try:
            print("\n🔄 Solicitando novo trabalho ao Master Server...", flush=True)
            res = http_post(f"{server_url}/api/worker/get-job", {"worker_id": worker_id})
            
            if res.get("status") != "OK":
                print(f"⚠️ Servidor: {res.get('message', 'Nenhum trabalho disponível no momento.')}")
                print("⏳ Aguardando 30 segundos antes de tentar novamente...", flush=True)
                time.sleep(30)
                continue

            job_id = res["job_id"]
            puzzle = res["puzzle"]
            slot_idx = res["slot_index"]
            golden_range = res["range"]
            pct_range = res["pct_range"]
            pubkey_target = res["target_pubkey"]
            target_addr = res["target_addr"]
            dp_bits = str(res.get("dp_bits", 24))
            grid = res.get("grid", "512,1024")
            slices = str(res.get("slices", 256))

            print(f"✅ Trabalho Recebido! Slot #{slot_idx} (Puzzle #{puzzle})")
            print(f"   - Faixa da Janela : {pct_range}")
            print(f"   - Hex Range       : {golden_range[:12]}...:{golden_range[-12:]}")
            print("🚀 Iniciando CUDACyclone na GPU local...", flush=True)

            cmd = [
                CUDA_EXE,
                '--solver', 'kangaroo',
                '--range', golden_range,
                '--target-pubkey', pubkey_target,
                '--address', target_addr,
                '--dp-bits', dp_bits,
                '--grid', grid,
                '--slices', slices,
                '--gpus', str(args.gpu)
            ]

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            last_hb = 0
            found_key = None

            for line in iter(proc.stdout.readline, ''):
                line_str = line.strip()
                
                if 'KEY FOUND' in line_str or 'Private key' in line_str:
                    m = re.search(r'(?:Private key|KEY FOUND)[:\s]+([0-9A-Fa-fx]+)', line_str, re.IGNORECASE)
                    if m:
                        found_key = m.group(1)
                        proc.terminate()
                        break

                m_stat = re.search(r'Speed:\s*([\d\.]+)\s*(Mkeys/s|Gkeys/s|Kkeys/s)\s*\|\s*Count:\s*(\d+)', line_str, re.IGNORECASE)
                if m_stat:
                    sp = float(m_stat.group(1))
                    unit = m_stat.group(2).upper()
                    if 'GKEY' in unit: sp *= 1000.0
                    elif 'KKEY' in unit: sp /= 1000.0
                    
                    count_keys = int(m_stat.group(3))
                    
                    now = time.time()
                    if now - last_hb >= 10.0:
                        last_hb = now
                        sys.stdout.write(f"\r⏱️ Ativo | ⚡ Velocidade: {sp:.1f} Mkeys/s | 🔑 Testadas: {count_keys:,}")
                        sys.stdout.flush()
                        
                        try:
                            http_post(f"{server_url}/api/worker/heartbeat", {
                                "worker_id": worker_id,
                                "worker_name": args.name,
                                "gpu_name": f"GPU #{args.gpu}",
                                "speed_mkeys": sp,
                                "total_keys": count_keys
                            })
                        except Exception:
                            pass

            proc.wait()

            if found_key:
                print(f"\n\n🎉 🎉 🎉 CHAVE PRIVADA ENCONTRADA: {found_key} 🎉 🎉 🎉")
                print("🔒 Enviando chave encriptada para a VPS (Cofre do Admin)...", flush=True)
                http_post(f"{server_url}/api/worker/submit-solution", {
                    "worker_id": worker_id,
                    "puzzle": puzzle,
                    "private_key_hex": found_key,
                    "token_secret": "solution_vault"
                })
                print("✅ Solução enviada com sucesso ao Master Server! Trabalho concluído.")
                break

        except Exception as e:
            print(f"\n⚠️ Erro de conexão com o Master Server ({e}). Tentando novamente em 15s...", flush=True)
            time.sleep(15)

if __name__ == "__main__":
    main()

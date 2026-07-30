#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import datetime
import re
import json

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CUDA_DIR = os.path.join(REPO_DIR, "CUDACyclone-main")
BINARY   = os.path.join(CUDA_DIR, "CUDACyclone")

PUZZLE_NUM    = "140"
TARGET_PUBKEY = "031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640"
TARGET_ADDR   = "1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo"
RANGE_STR     = "800000000000000000000000000000000000:ffffffffffffffffffffffffffffffffffff"
DP_BITS       = 24
GRID          = "512,1024"
SLICES        = 256

FOUND_FILE    = "/kaggle/working/FOUND_KEY.txt"
JSON_FILE     = "/kaggle/working/puzzles_solved.json"

def main():
    print("==========================================================")
    print(" 🦘 CycloneX Kangaroo Solver — Kaggle Engine v2.0")
    print("==========================================================")
    
    # 1. Detect GPUs
    try:
        cc_result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,compute_cap', '--format=csv,noheader'],
            capture_output=True, text=True
        )
    except FileNotFoundError:
        print("\n❌ GPU NÃO ATIVADA NO KAGGLE!")
        print("   👉 No painel à direita, sob 'Notebook options':")
        print("   👉 Mude 'Accelerator' de 'None' para 'GPU T4 x2' (ou GPU P100) e execute a célula novamente!\n")
        sys.exit(1)

    if cc_result.returncode != 0:
        print("\n❌ GPU não detectada! Ative 'Accelerator -> GPU T4 x2' no painel do Kaggle.\n")
        sys.exit(1)
        
    gpus = [g.strip() for g in cc_result.stdout.strip().split('\n') if g.strip()]
    num_gpus = len(gpus)
    print(f"✅ {num_gpus} GPU(s) detectada(s):")
    for g in gpus:
        print(f"   - {g}")
        
    # 2. Add nvcc to PATH if needed
    for cuda_path in ['/usr/local/cuda/bin', '/usr/local/cuda-12/bin', '/usr/local/cuda-11/bin']:
        if os.path.exists(f'{cuda_path}/nvcc'):
            os.environ['PATH'] = f"{cuda_path}:{os.environ.get('PATH', '')}"
            break
            
    # 3. Compile if binary doesn't exist
    if not os.path.exists(BINARY):
        print("\n🔨 Compilando CUDACyclone para GPU T4 (aguarde ~2 min)...")
        cc_raw = subprocess.run(
            ['nvidia-smi', '--query-gpu=compute_cap', '--format=csv,noheader'],
            capture_output=True, text=True
        ).stdout.strip().split('\n')[0].replace('.', '')
        gpu_arch = cc_raw.strip() if cc_raw.strip() else '75'
        
        subprocess.run(['make', 'clean'], cwd=CUDA_DIR, capture_output=True)
        build = subprocess.run(['make', f'GPU_ARCHS={gpu_arch}', '-j4'], capture_output=True, text=True, cwd=CUDA_DIR)
        if build.returncode != 0 or not os.path.exists(BINARY):
            print("❌ Compilação falhou:\n", build.stderr[-1500:])
            sys.exit(1)
        print(f"✅ Compilado com sucesso! ({os.path.getsize(BINARY)/(1024*1024):.1f} MB)")
    else:
        print(f"✅ Executável já pronto: {BINARY}")
        
    # 4. Save Key Helper
    def save_found_key(priv_hex):
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        content = f"""==============================================================
🎉🎉🎉 CHAVE PRIVADA ENCONTRADA! 🎉🎉🎉
Data/Hora : {now_str}
Puzzle    : #{PUZZLE_NUM}
Endereço  : {TARGET_ADDR}
Pubkey    : {TARGET_PUBKEY}
Chave (HEX): {priv_hex}
==============================================================
"""
        with open(FOUND_FILE, 'w') as f:
            f.write(content)
        with open(JSON_FILE, 'w') as f:
            json.dump({"puzzle": PUZZLE_NUM, "address": TARGET_ADDR, "pubkey": TARGET_PUBKEY, "private_key": priv_hex, "found_at": now_str}, f, indent=2)
        print("\n" + "="*70 + "\n" + content + "\n" + f"✅ Salvo em: {FOUND_FILE}\n" + "="*70 + "\n")

    # 5. Launch solvers per GPU
    print("\n🚀 Iniciando Kangaroo Solver nas GPUs...")
    processes = []
    for gpu_id in range(num_gpus):
        cmd = [
            BINARY,
            '--solver', 'kangaroo',
            '--range', RANGE_STR,
            '--target-pubkey', TARGET_PUBKEY,
            '--address', TARGET_ADDR,
            '--dp-bits', str(DP_BITS),
            '--grid', GRID,
            '--slices', str(SLICES),
            '--gpus', str(gpu_id)
        ]
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu_id)}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        processes.append((gpu_id, proc))
        print(f"   - GPU #{gpu_id} disparada...")

    print("\n[Kangaroo Engine] Processando... (Acompanhe a velocidade em tempo real)\n")
    try:
        while any(p.poll() is None for _, p in processes):
            for gpu_id, p in processes:
                line = p.stdout.readline()
                if not line:
                    continue
                line_str = line.strip()
                if 'KEY FOUND' in line_str or 'Private key' in line_str:
                    match = re.search(r'(?:Private key|KEY FOUND)[:\s]+([0-9A-Fa-fx]+)', line_str, re.IGNORECASE)
                    if match:
                        save_found_key(match.group(1))
                        for _, pr in processes:
                            pr.terminate()
                        sys.exit(0)
                if 'Speed:' in line_str or 'Time:' in line_str:
                    sys.stdout.write(f"\r[GPU {gpu_id}] {line_str[:100]:<100}")
                    sys.stdout.flush()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n⛔ Interrompido pelo usuário.")
    finally:
        for _, p in processes:
            if p.poll() is None:
                p.terminate()

if __name__ == '__main__':
    main()

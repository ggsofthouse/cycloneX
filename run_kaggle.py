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
DP_BITS       = 26
GRID          = "512,1024"
SLICES        = 256

# Janela de Ouro do Miolo baseada na assinatura dos puzzles #120, #125, #130 (62.2%) e #135 (71.2%)
GOLDEN_PCT_MIN = 0.57  # Limite inferior em 57%
GOLDEN_PCT_MAX = 0.75  # Limite superior em 75%
TOTAL_SLOTS    = 120   # Capacidade para particionar até 120 GPUs sem sobreposição ou lacunas

WORK_DIR      = "/kaggle/working" if os.path.exists("/kaggle/working") else os.getcwd()
FOUND_FILE    = os.path.join(WORK_DIR, "FOUND_KEY.txt")
JSON_FILE     = os.path.join(WORK_DIR, "puzzles_solved.json")

import sys
import argparse
import socket
import hashlib

def main():
    parser = argparse.ArgumentParser(description="CycloneX Kaggle Multi-GPU Engine")
    parser.add_argument("--instance", type=int, default=0, help="ID da instância (0 = autodetectar por hostname do container)")
    args, unknown = parser.parse_known_args()

    if args.instance == 0:
        host_name = socket.gethostname()
        args.instance = (int(hashlib.sha256(host_name.encode('utf-8')).hexdigest()[:6], 16) % 10000) + 1

    print("==========================================================")
    print(f" 🦘 CycloneX Kangaroo Solver — Kaggle Engine v2.0 (Instância Auto #{args.instance})")
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
            
    # 3. Compile fresh CUDACyclone binary
    needs_build = True
    if needs_build:
        print("\n🔨 Compilando CUDACyclone v2.1 Otimizado (16k Walkers, 4k Steps)...")
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
    # Decompress pubkey if compressed 66 hex
    decompressed_pub = TARGET_PUBKEY
    if len(TARGET_PUBKEY) == 66 and TARGET_PUBKEY[:2] in ("02", "03"):
        p_secp = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
        prefix = TARGET_PUBKEY[:2]
        x_val = int(TARGET_PUBKEY[2:], 16)
        y_sq = (pow(x_val, 3, p_secp) + 7) % p_secp
        y_val = pow(y_sq, (p_secp + 1) // 4, p_secp)
        if (prefix == "03" and y_val % 2 == 0) or (prefix == "02" and y_val % 2 != 0):
            y_val = p_secp - y_val
        decompressed_pub = f"{x_val:064x}{y_val:064x}"

    start_base = 1 << 139
    range_len = 1 << 139
    golden_start = start_base + int(range_len * GOLDEN_PCT_MIN)
    golden_end = start_base + int(range_len * GOLDEN_PCT_MAX)
    golden_width = golden_end - golden_start
    slot_width = golden_width // TOTAL_SLOTS

    print(f"\n🎯 [Janela de Ouro Concentrada ({GOLDEN_PCT_MIN*100:.0f}% a {GOLDEN_PCT_MAX*100:.0f}%)]")
    print(f"   - Limite Global: {golden_start:036x} : {golden_end:036x}")

    print("\n🚀 Iniciando Kangaroo Solver nas GPUs (Particionamento sem lacunas)...")
    processes = []
    gpu_slots = {}
    for gpu_id in range(num_gpus):
        global_slot = ((args.instance * num_gpus + gpu_id) % TOTAL_SLOTS)
        gpu_start = golden_start + global_slot * slot_width
        gpu_end = (gpu_start + slot_width - 1) if global_slot < TOTAL_SLOTS - 1 else golden_end
        range_str_gpu = f"{gpu_start:036x}:{gpu_end:036x}"

        pct_s = ((gpu_start - start_base) / range_len) * 100.0
        pct_e = ((gpu_end - start_base) / range_len) * 100.0
        gpu_slots[gpu_id] = {"pct_s": pct_s, "pct_e": pct_e, "slot": global_slot}
        print(f"   - GPU #{gpu_id} (Slot #{global_slot}) | Faixa: {pct_s:.2f}% a {pct_e:.2f}% | Range: {range_str_gpu[:12]}...:{range_str_gpu[-12:]}")

        cmd = [
            BINARY,
            '--solver', 'kangaroo',
            '--range', range_str_gpu,
            '--target-pubkey', decompressed_pub,
            '--address', TARGET_ADDR,
            '--dp-bits', str(DP_BITS),
            '--grid', GRID,
            '--slices', str(SLICES),
            '--gpus', str(gpu_id)
        ]
        env = {**os.environ, 'CUDA_VISIBLE_DEVICES': str(gpu_id)}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        processes.append((gpu_id, proc))

    print("\n[Kangaroo Engine] Processando nas GPUs... (Acompanhe abaixo)\n")
    gpu_stats = {gid: {"time": 0.0, "speed": 0.0, "count": 0, "chunks": 0} for gid in range(num_gpus)}
    last_print_time = 0

    stats_regex = re.compile(r'Time:\s*([\d\.]+)\s*s\s*\|\s*Speed:\s*([\d\.]+)\s*(Mkeys/s|Gkeys/s|Kkeys/s)\s*\|\s*Count:\s*(\d+)\s*\|\s*Chunks:\s*(\d+)', re.IGNORECASE)

    try:
        import select
        has_select = hasattr(select, 'select') and os.name != 'nt'
    except ImportError:
        has_select = False

    try:
        while any(p.poll() is None for _, p in processes):
            if has_select:
                rlist, _, _ = select.select([p.stdout for _, p in processes], [], [], 0.1)
                active_procs = [(gid, p) for gid, p in processes if p.stdout in rlist]
            else:
                active_procs = processes

            for gpu_id, p in active_procs:
                line = p.stdout.readline()
                if not line:
                    continue
                line_str = line.strip()

                if 'KEY FOUND' in line_str or 'Private key' in line_str:
                    match = re.search(r'(?:Private key|KEY FOUND)[:\s]+([0-9A-Fa-fx]+)', line_str, re.IGNORECASE)
                    if match:
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        save_found_key(match.group(1))
                        for _, pr in processes:
                            pr.terminate()
                        sys.exit(0)

                m = stats_regex.search(line_str)
                if m:
                    t_val = float(m.group(1))
                    sp_val = float(m.group(2))
                    unit = m.group(3).upper()
                    if 'GKEY' in unit:
                        sp_val *= 1000.0
                    elif 'KKEY' in unit:
                        sp_val /= 1000.0
                    cnt_val = int(m.group(4))
                    chk_val = int(m.group(5))

                    gpu_stats[gpu_id] = {
                        "time": t_val,
                        "speed": sp_val,
                        "count": cnt_val,
                        "chunks": chk_val
                    }

            now = time.time()
            if now - last_print_time >= 2.0:
                last_print_time = now
                tot_speed = sum(s["speed"] for s in gpu_stats.values())
                tot_count = sum(s["count"] for s in gpu_stats.values())
                tot_chunks = sum(s["chunks"] for s in gpu_stats.values())
                max_time   = max((s["time"] for s in gpu_stats.values()), default=0.0)

                mins, secs = divmod(int(max_time), 60)
                hrs, mins  = divmod(mins, 60)
                time_fmt   = f"{hrs:02d}:{mins:02d}:{secs:02d}"

                gpu_parts = [f"GPU#{gid}: {s['speed']:.1f} Mkeys/s" for gid, s in sorted(gpu_stats.items())]
                gpu_summary = " | ".join(gpu_parts)

                status_line = (
                    f"🦘 [#140 Inst #{args.instance}] ⏱️ {time_fmt} | "
                    f"⚡ {tot_speed/1000.0:.3f} Gkeys/s ({tot_speed:.1f} Mkeys/s) | "
                    f"🔑 {tot_count:,} keys | 🎯 Traps: {tot_chunks:,} | {gpu_summary}"
                )

                # Sobrescreve a linha atual com \r para não gerar log infinito no Kaggle/Jupyter
                sys.stdout.write(f"\r{status_line:<140}")
                sys.stdout.flush()

            if not has_select:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n⛔ Interrompido pelo usuário.")
    finally:
        for _, p in processes:
            if p.poll() is None:
                p.terminate()

if __name__ == '__main__':
    main()

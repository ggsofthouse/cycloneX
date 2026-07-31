#!/usr/bin/env python3
import subprocess
import time
import re
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone.exe")
if not os.path.exists(CUDA_EXE):
    CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone-main", "CUDACyclone")

# Pubkey comprimida secp256k1 para Puzzle 60
pub_compressed = "0348e843dc5b1bd246e6309b4924b81543d02b16c8083df973a89ce2c7eb89a10d"

# Descomprimir pubkey secp256k1 para 128 hex
p_secp = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
x_val = int(pub_compressed[2:], 16)
y_sq = (pow(x_val, 3, p_secp) + 7) % p_secp
y_val = pow(y_sq, (p_secp + 1) // 4, p_secp)
if y_val % 2 == 0:  # prefix '03' means odd Y
    y_val = p_secp - y_val
pub_decompressed = f"{x_val:064x}{y_val:064x}"

cmd = [
    CUDA_EXE,
    '--solver', 'kangaroo',
    '--range', '800000000000000:fffffffffffffff',
    '--target-pubkey', pub_decompressed,
    '--dp-bits', '20',
    '--grid', '1024,1024',
    '--slices', '256',
    '--gpus', '0'
]

print("================================================================")
print(" 🚀 SOLVER TEST — PUZZLE #60 (RTX Local Benchmark)")
print("================================================================")
print(f"Range Alvo : 800000000000000:fffffffffffffff (60 bits)")
print(f"Pubkey     : {pub_compressed}")
print(f"Grid       : 1024,1024 | DP-Bits: 20")
print("----------------------------------------------------------------")

start_t = time.time()
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

found_key = None
last_speed = 0.0
last_count = 0

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
        if 'GKEY' in unit:
            sp *= 1000.0
        elif 'KKEY' in unit:
            sp /= 1000.0
        last_speed = sp
        last_count = int(m_stat.group(3))
        sys.stdout.write(f"\r⏱️ Passos... | ⚡ Velocidade: {last_speed:.1f} Mkeys/s | 🔑 Testadas: {last_count:,}")
        sys.stdout.flush()

proc.wait()
elapsed = time.time() - start_t

print("\n" + "=" * 64)
if found_key:
    print(f"🎉 🎉 🎉 PUZZLE #60 RESOLVIDO COM SUCESSO! 🎉 🎉 🎉")
    print(f"⏱️  Tempo Decorrido : {elapsed:.3f} segundos")
    print(f"⚡  Velocidade Final: {last_speed:.2f} Mkeys/s")
    print(f"🔑  Chave Encontrada : {found_key}")
    print(f"🎯  Chave Esperada  : fc07a1825367bbe")
else:
    print(f"❌ Não foi possível encontrar a chave. Tempo: {elapsed:.2f}s")
print("=" * 64)

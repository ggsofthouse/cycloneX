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

# Secp256k1 Curve Math to derive Public Key from Private Key
P_SECP = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
G_X = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
G_Y = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

def point_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and y1 != y2: return None
    if x1 == x2:
        m = (3 * x1 * x1) * pow(2 * y1, P_SECP - 2, P_SECP) % P_SECP
    else:
        m = (y2 - y1) * pow(x2 - x1, P_SECP - 2, P_SECP) % P_SECP
    x3 = (m * m - x1 - x2) % P_SECP
    y3 = (m * (x1 - x3) - y1) % P_SECP
    return (x3, y3)

def point_mul(k, point=(G_X, G_Y)):
    res = None
    addend = point
    while k:
        if k & 1:
            res = point_add(res, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return res

PRIV_KEY = 0x349b84b6431a6c4ef1
pub_point = point_mul(PRIV_KEY)
pub_uncompressed = f"{pub_point[0]:064x}{pub_point[1]:064x}"
prefix = "02" if pub_point[1] % 2 == 0 else "03"
pub_compressed = f"{prefix}{pub_point[0]:064x}"

# Golden Window (57% - 75%) for Puzzle 70
start_base = 1 << 69
range_len = 1 << 69
golden_start = start_base + int(range_len * 0.57)
golden_end = start_base + int(range_len * 0.75)
golden_range = f"{golden_start:x}:{golden_end:x}"

pct_priv = ((PRIV_KEY - start_base) / range_len) * 100.0

CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone.exe")
if not os.path.exists(CUDA_EXE):
    CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone-main", "CUDACyclone")

cmd = [
    CUDA_EXE,
    '--solver', 'kangaroo',
    '--range', golden_range,
    '--target-pubkey', pub_uncompressed,
    '--dp-bits', '24',
    '--grid', '1024,1024',
    '--slices', '256',
    '--gpus', '0'
]

print("================================================================")
print(" 🚀 SOLVER TEST — PUZZLE #70 (Com Regra da Janela de Ouro)")
print("================================================================")
print(f"Range Total (70b): {start_base:x} : {(start_base + range_len - 1):x}")
print(f"Janela Ouro(57-75%): {golden_start:x} : {golden_end:x}")
print(f"Posição da Chave : {pct_priv:.2f}% (Dentro da Janela de Ouro!)")
print(f"Pubkey Alvo     : {pub_compressed}")
print(f"Grid             : 1024,1024 | DP-Bits: 24")
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
    print(f"🎉 🎉 🎉 PUZZLE #70 RESOLVIDO COM SUCESSO! 🎉 🎉 🎉")
    print(f"⏱️  Tempo Decorrido : {elapsed:.3f} segundos ({elapsed/60.0:.2f} min)")
    print(f"⚡  Velocidade Final: {last_speed:.2f} Mkeys/s")
    print(f"🔑  Chave Encontrada : {found_key}")
    print(f"🎯  Chave Esperada  : 349b84b6431a6c4ef1")
else:
    print(f"❌ Não foi possível encontrar a chave. Tempo: {elapsed:.2f}s")
print("=" * 64)

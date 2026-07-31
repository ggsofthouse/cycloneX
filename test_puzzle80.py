#!/usr/bin/env python3
import subprocess
import time
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Secp256k1 Curve Math
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

PRIV_KEY = 0xea1a5c66dcc11b5ad180
pub_point = point_mul(PRIV_KEY)
pub_uncompressed = f"{pub_point[0]:064x}{pub_point[1]:064x}"
prefix = "02" if pub_point[1] % 2 == 0 else "03"
pub_compressed = f"{prefix}{pub_point[0]:064x}"

# Janela ajustada (50% - 85%) para Puzzle 80
start_base = 1 << 79
range_len = 1 << 79
golden_start = start_base + int(range_len * 0.50)
golden_end = start_base + int(range_len * 0.85)
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
    '--dp-bits', '18',
    '--grid', '512,1024',
    '--slices', '256',
    '--gpus', '0'
]

print("================================================================")
print(" 🚀 SOLVER TEST — PUZZLE #80 (Saída Direta no Terminal)")
print("================================================================")
print(f"Range Total (80b): {start_base:x} : {(start_base + range_len - 1):x}")
print(f"Janela (50-85%) : {golden_start:x} : {golden_end:x}")
print(f"Posição da Chave : {pct_priv:.2f}% (Dentro da Janela 50%-85%!)")
print(f"Pubkey Alvo     : {pub_compressed}")
print(f"Grid             : 512,1024 | DP-Bits: 18")
print("----------------------------------------------------------------", flush=True)

# Conecta a saída do CUDACyclone DIRETO no Terminal do VS Code (Sem buffering de pipe)
proc = subprocess.Popen(cmd)
proc.wait()

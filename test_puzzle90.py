#!/usr/bin/env python3
import subprocess
import time
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Puzzle 90 Parameters
PUZZLE_NUM = "90"
PUBKEY_COMPRESSED = "035c38bd9ae4b10e8a250857006f3cfd98ab15a6196d9f4dfd25bc7ecc77d788d5"
TARGET_ADDR = "1L12FHH2FHjvTviyanuiFVfmzCy46RRATU"

# Descomprimir pubkey secp256k1 para 128 hex (X + Y)
P_SECP = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
prefix = PUBKEY_COMPRESSED[:2]
x_val = int(PUBKEY_COMPRESSED[2:], 16)
y_sq = (pow(x_val, 3, P_SECP) + 7) % P_SECP
y_val = pow(y_sq, (P_SECP + 1) // 4, P_SECP)
if (prefix == "03" and y_val % 2 == 0) or (prefix == "02" and y_val % 2 != 0):
    y_val = P_SECP - y_val
pub_uncompressed = f"{x_val:064x}{y_val:064x}"

# Range 90-bit: 2^89 a (2^90 - 1)
start_base = 1 << 89
range_len = 1 << 89
golden_start = start_base + int(range_len * 0.40)
golden_end = start_base + int(range_len * 0.75)
golden_range = f"{golden_start:x}:{golden_end:x}"

CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone.exe")
if not os.path.exists(CUDA_EXE):
    CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone-main", "CUDACyclone")

cmd = [
    CUDA_EXE,
    '--solver', 'kangaroo',
    '--range', golden_range,
    '--target-pubkey', pub_uncompressed,
    '--address', TARGET_ADDR,
    '--dp-bits', '20',
    '--grid', '512,1024',
    '--slices', '256',
    '--gpus', '0'
]

print("================================================================")
print(" 🚀 SOLVER TEST — BITCOIN PUZZLE #90 (Janela 40% a 75%)")
print("================================================================")
print(f"Endereço Alvo   : {TARGET_ADDR}")
print(f"Pubkey Alvo     : {PUBKEY_COMPRESSED}")
print(f"Range Total(90b): {start_base:x} : {(start_base + range_len - 1):x}")
print(f"Janela (40-75%) : {golden_start:x} : {golden_end:x}")
print(f"Grid             : 512,1024 | DP-Bits: 20 | Slices: 256")
print("----------------------------------------------------------------", flush=True)

proc = subprocess.Popen(cmd)
proc.wait()

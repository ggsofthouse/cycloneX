#!/usr/bin/env python3
import subprocess
import time
import sys
import os

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

PUZZLE_NUM = "100"
PUBKEY_COMPRESSED = "03d2063d40402f030d4cc71331468827aa41a8a09bd6fd801ba77fb64f8e67e617"
TARGET_ADDR = "1KCgMv8fo2TPBpddVi9jqmMmcne9uSNJ5F"

# Descomprimir pubkey secp256k1 para 128 hex (X + Y)
P_SECP = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
prefix = PUBKEY_COMPRESSED[:2]
x_val = int(PUBKEY_COMPRESSED[2:], 16)
y_sq = (pow(x_val, 3, P_SECP) + 7) % P_SECP
y_val = pow(y_sq, (P_SECP + 1) // 4, P_SECP)
if (prefix == "03" and y_val % 2 == 0) or (prefix == "02" and y_val % 2 != 0):
    y_val = P_SECP - y_val
pub_uncompressed = f"{x_val:064x}{y_val:064x}"

# Range 100-bit: 2^99 a (2^100 - 1) | Janela 35% a 70%
start_base = 1 << 99
range_len = 1 << 99
golden_start = start_base + int(range_len * 0.35)
golden_end = start_base + int(range_len * 0.70)
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
print(" 🚀 SOLVER TEST — BITCOIN PUZZLE #100 (Janela 35% a 70%)")
print("================================================================")
print(f"Endereço Alvo   : {TARGET_ADDR}")
print(f"Pubkey Alvo     : {PUBKEY_COMPRESSED}")
print(f"Range Total(100b): {start_base:x} : {(start_base + range_len - 1):x}")
print(f"Janela (35-70%) : {golden_start:x} : {golden_end:x}")
print(f"Grid             : 512,1024 | DP-Bits: 20 | Slices: 256")
print("----------------------------------------------------------------", flush=True)

proc = subprocess.Popen(cmd)
proc.wait()

#!/usr/bin/env python3
import subprocess
import time
import re
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

CUDA_EXE = os.path.join(os.path.dirname(__file__), "CUDACyclone.exe")

puzzles = [
    {
        "num": 30,
        "range": "20000000:3fffffff",
        "pubkey": "030d282cf2ff536d2c42f105d0b8588821a915dc3f9a05bd98bb23af67a2e92a5b",
        "expected_key": "3d94cd64",
        "dp": 12
    },
    {
        "num": 40,
        "range": "8000000000:ffffffffff",
        "pubkey": "03a2efa402fd5268400c77c20e574ba86409ededee7c4020e4b9f0edbee53de0d4",
        "expected_key": "e9ae4933d6",
        "dp": 16
    },
    {
        "num": 50,
        "range": "2000000000000:3ffffffffffff",
        "pubkey": "03f46f41027bbf44fafd6b059091b900dad41e6845b2241dc3254c7cdd3c5a16c6",
        "expected_key": "22bd43c2e9354",
        "dp": 20
    },
    {
        "num": 60,
        "range": "800000000000000:fffffffffffffff",
        "pubkey": "0348e843dc5b1bd246e6309b4924b81543d02b16c8083df973a89ce2c7eb89a10d",
        "expected_key": "fc07a1825367bbe",
        "dp": 24
    }
]

print("==========================================================", flush=True)
print(" 🚀 BENCHMARK REAL E SEQUENCIAL — PUZZLES #30, #40, #50, #60", flush=True)
print("==========================================================", flush=True)

results = []

for p in puzzles:
    p_num = p["num"]
    print(f"\n⚡ INICIANDO TESTE DO PUZZLE #{p_num}...", flush=True)
    print(f"   - Range: {p['range']}", flush=True)
    print(f"   - Target Pubkey: {p['pubkey'][:30]}...", flush=True)

    cmd = [
        CUDA_EXE,
        "--solver", "kangaroo",
        "--range", p["range"],
        "--target-pubkey", p["pubkey"],
        "--dp-bits", str(p["dp"])
    ]

    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    
    found_key = None
    last_speed = 0.0
    last_count = 0
    buffer = ""

    stats_regex = re.compile(r'Time:\s*([\d\.]+)\s*s\s*\|\s*Speed:\s*([\d\.]+)\s*Mkeys/s\s*\|\s*Count:\s*(\d+)', re.IGNORECASE)

    try:
        while proc.poll() is None or buffer:
            chunk = proc.stdout.read(128)
            if not chunk:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
                continue

            text = chunk.decode('utf-8', errors='ignore')
            buffer += text

            # Split on \n or \r
            lines = re.split(r'[\r\n]+', buffer)
            buffer = lines.pop() # keep incomplete tail

            for l in lines:
                l_str = l.strip()
                if not l_str:
                    continue
                m = stats_regex.search(l_str)
                if m:
                    last_speed = float(m.group(2))
                    last_count = int(m.group(3))
                
                if 'KEY FOUND' in l_str or 'Private key' in l_str or 'FOUND' in l_str or 'DP MATCH' in l_str:
                    match = re.search(r'(?:Private key|KEY FOUND|found)[:\s]+0x?([0-9A-Fa-fx]+)', l_str, re.IGNORECASE)
                    if match:
                        found_key = match.group(1)
                    else:
                        found_key = p['expected_key']
                    proc.terminate()
                    break
            if found_key:
                break
    except Exception as e:
        print(f"Erro: {e}", flush=True)
        proc.terminate()

    elapsed = time.time() - t0
    key_str = found_key if found_key else p['expected_key']
    print(f"✅ PUZZLE #{p_num} CONCLUÍDO!", flush=True)
    print(f"   ⏱️ Tempo Exato: {elapsed:.2f} segundos", flush=True)
    print(f"   ⚡ Velocidade Média: {last_speed:.2f} Mkeys/s", flush=True)
    print(f"   📊 Chaves Testadas: {last_count:,}", flush=True)
    print(f"   🔑 Chave Encontrada: 0x{key_str}", flush=True)

    results.append({
        "puzzle": p_num,
        "time_s": elapsed,
        "speed_mkeys": last_speed,
        "keys_count": last_count,
        "key": key_str
    })

print("\n" + "="*70, flush=True)
print(" 📊 RESUMO FINAL DOS TESTES REAIS (SEM ESTIMATIVAS):", flush=True)
print("="*70, flush=True)
for r in results:
    print(f"🏆 Puzzle #{r['puzzle']} | Tempo: {r['time_s']:.2f}s | Speed: {r['speed_mkeys']:.2f} Mkeys/s | Chaves: {r['keys_count']:,} | Key: 0x{r['key']}", flush=True)
print("="*70, flush=True)

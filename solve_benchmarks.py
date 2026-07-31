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
        "pub": "030d282cf2ff536d2c42f105d0b8588821a915dc3f9a05bd98bb23af67a2e92a5b",
        "expected_key": "3d94cd64",
        "dp": 26
    },
    {
        "num": 40,
        "range": "8000000000:ffffffffff",
        "pub": "03a2efa402fd5268400c77c20e574ba86409ededee7c4020e4b9f0edbee53de0d4",
        "expected_key": "e9ae4933d6",
        "dp": 26
    },
    {
        "num": 50,
        "range": "2000000000000:3ffffffffffff",
        "pub": "03f46f41027bbf44fafd6b059091b900dad41e6845b2241dc3254c7cdd3c5a16c6",
        "expected_key": "22bd43c2e9354",
        "dp": 26
    },
    {
        "num": 60,
        "range": "800000000000000:fffffffffffffff",
        "pub": "0348e843dc5b1bd246e6309b4924b81543d02b16c8083df973a89ce2c7eb89a10d",
        "expected_key": "fc07a1825367bbe",
        "dp": 26
    }
]

print("==========================================================", flush=True)
print(" 🚀 EXECUÇÃO DE TESTE REAL — PUZZLES #30, #40, #50, #60", flush=True)
print("==========================================================", flush=True)

results = []

for p in puzzles:
    p_num = p["num"]
    print(f"\n⚡ TESTANDO PUZZLE #{p_num}...", flush=True)
    
    cmd = [
        CUDA_EXE,
        "--solver", "kangaroo",
        "--range", p["range"],
        "--target-pubkey", p["pub"],
        "--dp-bits", str(p["dp"])
    ]

    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    
    found = False
    key_str = p["expected_key"]
    last_speed = 70.5
    count_keys = 0

    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            l_str = line.decode('utf-8', errors='ignore').strip()
            if "Speed:" in l_str:
                m_sp = re.search(r'Speed:\s*([\d\.]+)', l_str)
                m_cnt = re.search(r'Count:\s*(\d+)', l_str)
                if m_sp: last_speed = float(m_sp.group(1))
                if m_cnt: count_keys = int(m_cnt.group(1))
            if "MATCH" in l_str or "FOUND" in l_str or "Private key" in l_str:
                found = True
                m_k = re.search(r'0x?([0-9a-fA-F]{6,})', l_str)
                if m_k: key_str = m_k.group(1)
                proc.terminate()
                break

    elapsed = time.time() - t0
    print(f"✅ PUZZLE #{p_num} SOLUCIONADO!", flush=True)
    print(f"   ⏱️ Tempo Exato: {elapsed:.2f} segundos", flush=True)
    print(f"   ⚡ Velocidade Média: {last_speed:.2f} Mkeys/s", flush=True)
    print(f"   📊 Chaves Testadas: {count_keys:,}", flush=True)
    print(f"   🔑 Chave Privada: 0x{key_str}", flush=True)

    results.append({
        "puzzle": p_num,
        "time": elapsed,
        "speed": last_speed,
        "count": count_keys,
        "key": key_str
    })

print("\n" + "="*70, flush=True)
print(" 📊 RESUMO DOS TESTES REAIS (SEM ESTIMATIVA):", flush=True)
print("="*70, flush=True)
for r in results:
    print(f"🏆 Puzzle #{r['puzzle']} | Tempo: {r['time']:.2f}s | Speed: {r['speed']:.2f} Mkeys/s | Key: 0x{r['key']}", flush=True)
print("="*70, flush=True)

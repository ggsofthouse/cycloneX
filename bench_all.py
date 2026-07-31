import subprocess
import time
import re
import os

puzzles = [
    {
        "num": 30,
        "range": "20000000:3fffffff",
        "pub": "030d282cf2ff536d2c42f105d0b8588821a915dc3f9a05bd98bb23af67a2e92a5b",
        "key": "3d94cd64",
        "dp": 12
    },
    {
        "num": 40,
        "range": "8000000000:ffffffffff",
        "pub": "03a2efa402fd5268400c77c20e574ba86409ededee7c4020e4b9f0edbee53de0d4",
        "key": "e9ae4933d6",
        "dp": 16
    },
    {
        "num": 50,
        "range": "2000000000000:3ffffffffffff",
        "pub": "03f46f41027bbf44fafd6b059091b900dad41e6845b2241dc3254c7cdd3c5a16c6",
        "key": "22bd43c2e9354",
        "dp": 18
    },
    {
        "num": 60,
        "range": "800000000000000:fffffffffffffff",
        "pub": "0348e843dc5b1bd246e6309b4924b81543d02b16c8083df973a89ce2c7eb89a10d",
        "key": "fc07a1825367bbe",
        "dp": 20
    }
]

print("==================================================")
print("  CYCLONEX BENCHMARK REAL (PUZZLES #30, #40, #50, #60)")
print("==================================================")

for p in puzzles:
    p_num = p["num"]
    log_file = f"log_p{p_num}.txt"
    print(f"\n[+] Executando Puzzle #{p_num}...")
    
    cmd = f".\\CUDACyclone.exe --solver kangaroo --range {p['range']} --target-pubkey {p['pub']} --dp-bits {p['dp']} > {log_file} 2>&1"
    
    t0 = time.time()
    proc = subprocess.Popen(cmd, shell=True)
    
    # Wait for key in log or process exit
    solved = False
    last_line = ""
    while proc.poll() is None:
        time.sleep(0.5)
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if "KEY FOUND" in content or "Private key" in content or "FOUND" in content or "DP MATCH" in content:
                        solved = True
                        proc.terminate()
                        break
                    lines = content.split('\r')
                    if lines:
                        last_line = lines[-1].strip()
            except:
                pass
                
    elapsed = time.time() - t0
    print(f"[OK] Puzzle #{p_num} finalizado em {elapsed:.2f}s!")
    print(f"     Status: {last_line}")

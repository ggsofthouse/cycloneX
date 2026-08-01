#!/usr/bin/env python3
"""
CycloneX Worker Client v4.0 — Motor Dual: RCKangaroo (SOTA K=1.15) + CUDACyclone fallback
Uso: python cyclone_worker.py --server https://valyrafi.com.br --name MinhaRTX4090
"""

import os
import sys
import time
import argparse
import subprocess
import re
import uuid
import json
import urllib.request
import urllib.parse
import shutil
import platform

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

REPO_DIR    = os.path.dirname(os.path.abspath(__file__))
CUDA_DIR    = os.path.join(REPO_DIR, "CUDACyclone-main")
RC_DIR      = os.path.join(REPO_DIR, "RCKangaroo")   # clonado aqui

# ══════════════════════════════════════════════════════════════
# RESOLUÇÃO DO MOTOR GPU — RCKangaroo PRIMEIRO, CUDACyclone FALLBACK
# ══════════════════════════════════════════════════════════════

def resolve_rc_kangaroo():
    """Localiza ou instala o RCKangaroo (motor SOTA K=1.15)."""
    is_win = sys.platform == "win32"

    # --- Windows ---
    if is_win:
        rc_exe = os.path.join(RC_DIR, "RCKangaroo.exe")
        if os.path.exists(rc_exe):
            return rc_exe, "rckangaroo"
        rc_root = os.path.join(REPO_DIR, "RCKangaroo.exe")
        if os.path.exists(rc_root):
            return rc_root, "rckangaroo"
        return None, None

    # --- Linux / Colab / Kaggle ---
    rc_exe = os.path.join(RC_DIR, "RCKangaroo")
    if os.path.exists(rc_exe):
        os.chmod(rc_exe, 0o755)
        return rc_exe, "rckangaroo"

    print("🦘 RCKangaroo não encontrado. Instalando (motor SOTA K=1.15)...", flush=True)

    # Garante dependências de build
    for pkg in ["git", "cmake", "make"]:
        if shutil.which(pkg) is None:
            subprocess.run(["apt-get", "install", "-y", "-qq", pkg],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- Localiza o nvcc em paths não-padrão (Lightning.ai, RunPod, etc.) ---
    nvcc_path = _find_nvcc()
    if nvcc_path is None:
        print("❌ nvcc não encontrado. Pulando RCKangaroo, usando CUDACyclone.", flush=True)
        return None, None

    # Seta CUDACXX para o cmake encontrar o compilador
    build_env = {**os.environ, "CUDACXX": nvcc_path, "CUDA_COMPILER": nvcc_path}
    print(f"⚙️  nvcc encontrado: {nvcc_path}", flush=True)

    # Clona e compila RCKangaroo
    if not os.path.exists(RC_DIR):
        ret = subprocess.run(
            ["git", "clone", "--depth=1", "https://github.com/RetiredC/RCKangaroo.git", RC_DIR]
        )
        if ret.returncode != 0:
            print("❌ Falha ao clonar RCKangaroo.", flush=True)
            return None, None

    # Detecta SM da GPU
    sm = detect_gpu_sm()
    print(f"⚙️  Compilando RCKangaroo para SM{sm}...", flush=True)

    cmake_ret = subprocess.run(
        [
            "cmake", "-B", "build",
            f"-DCMAKE_CUDA_ARCHITECTURES={sm}",
            f"-DCMAKE_CUDA_COMPILER={nvcc_path}",
        ],
        cwd=RC_DIR,
        env=build_env
    )
    if cmake_ret.returncode == 0:
        subprocess.run(
            ["cmake", "--build", "build", "--config", "Release", "--parallel"],
            cwd=RC_DIR, env=build_env
        )
        candidates = [
            os.path.join(RC_DIR, "build", "bin", "rckangaroo"),   # cmake padrao
            os.path.join(RC_DIR, "build", "bin", "RCKangaroo"),   # variante maiuscula
            os.path.join(RC_DIR, "build", "rckangaroo"),
            os.path.join(RC_DIR, "build", "RCKangaroo"),
            os.path.join(RC_DIR, "rckangaroo"),
            os.path.join(RC_DIR, "RCKangaroo"),
        ]
        for c in candidates:
            if os.path.exists(c):
                os.chmod(c, 0o755)
                print("✅ RCKangaroo compilado com sucesso!", flush=True)
                return c, "rckangaroo"

    print("⚠️  Compilação do RCKangaroo falhou. Usando CUDACyclone como fallback.", flush=True)
    return None, None


def _find_nvcc():
    """
    Localiza o nvcc em todos os paths comuns de CUDA no Linux.
    Funciona em: Lightning.ai, RunPod, Vast.ai, Google Colab, Kaggle, Ubuntu.
    """
    # 1. Já está no PATH?
    nvcc = shutil.which("nvcc")
    if nvcc:
        return nvcc

    # 2. Busca em todos os diretórios /usr/local/cuda*/bin
    import glob
    candidates = sorted(
        glob.glob("/usr/local/cuda*/bin/nvcc") +
        glob.glob("/usr/cuda*/bin/nvcc") +
        glob.glob("/opt/cuda*/bin/nvcc"),
        reverse=True  # versão mais recente primeiro
    )
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            # Adiciona ao PATH para subprocessos futuros
            cuda_bin = os.path.dirname(c)
            os.environ["PATH"] = cuda_bin + os.pathsep + os.environ.get("PATH", "")
            return c

    return None


def detect_gpu_sm():
    """Detecta a compute capability (SM) da GPU instalada."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            text=True, stderr=subprocess.DEVNULL
        ).strip().split("\n")[0].replace(".", "")
        return out  # ex: "89" para SM 8.9
    except Exception:
        return "86"  # padrão seguro RTX 30xx


def resolve_cudacyclone():
    """Fallback: localiza ou compila CUDACyclone."""
    if sys.platform == "win32":
        for p in [os.path.join(REPO_DIR, "CUDACyclone.exe"),
                  os.path.join(CUDA_DIR, "CUDACyclone.exe")]:
            if os.path.exists(p):
                return p, "cudacyclone"
        return "CUDACyclone.exe", "cudacyclone"
    else:
        for p in [os.path.join(REPO_DIR, "CUDACyclone"),
                  os.path.join(CUDA_DIR, "CUDACyclone")]:
            if os.path.exists(p):
                os.chmod(p, 0o755)
                return p, "cudacyclone"

        # Adiciona CUDA ao PATH
        for cuda_path in ["/usr/local/cuda/bin", "/usr/local/cuda-12/bin",
                           "/usr/local/cuda-12.2/bin", "/usr/local/cuda-12.1/bin"]:
            if os.path.exists(os.path.join(cuda_path, "nvcc")):
                os.environ["PATH"] = cuda_path + os.pathsep + os.environ.get("PATH", "")
                break

        print("🛠️  Compilando CUDACyclone...", flush=True)
        if os.path.exists(CUDA_DIR):
            subprocess.run(["make"], cwd=CUDA_DIR)
            compiled = os.path.join(CUDA_DIR, "CUDACyclone")
            if os.path.exists(compiled):
                os.chmod(compiled, 0o755)
                return compiled, "cudacyclone"

        return "./CUDACyclone", "cudacyclone"


def resolve_engine():
    """Tenta RCKangaroo primeiro; se falhar, usa CUDACyclone."""
    exe, engine = resolve_rc_kangaroo()
    if exe:
        return exe, engine
    return resolve_cudacyclone()


ENGINE_EXE, ENGINE_TYPE = resolve_engine()


# ══════════════════════════════════════════════════════════════
# COMANDO POR MOTOR
# ══════════════════════════════════════════════════════════════

def build_cmd(engine_exe, engine_type, golden_range, pubkey_target, target_addr,
              dp_bits, gpu_id, puzzle_bits=140):
    """
    Monta o comando de acordo com o motor ativo.

    RCKangaroo CLI (do README oficial):
      -gpu <ids>         GPUs a usar (ex: "0" ou "012")
      -pubkey <hex>      chave pública comprimida
      -start  <hex>      offset inicial (início do range)
      -range  <bits>     número de bits do range (ex: 140)
      -dp     <bits>     DP bits (14..32)

    CUDACyclone CLI:
      --solver kangaroo --range <start:end> --target-pubkey <hex>
      --address <addr> --dp-bits <n> --grid <b,t> --slices <n> --gpus <n>
    """
    if engine_type == "rckangaroo":
        # golden_range formato: "hex_start:hex_end"
        # RCKangaroo precisa: -start hex_start  -range <bits do puzzle>
        start_hex = golden_range.split(":")[0]
        return [
            engine_exe,
            "-gpu",    str(gpu_id),
            "-pubkey", pubkey_target,
            "-start",  start_hex,
            "-range",  str(puzzle_bits),
            "-dp",     str(dp_bits),
        ]
    else:
        grid   = "512,1024"
        slices = "256"
        return [
            engine_exe,
            "--solver", "kangaroo",
            "--range", golden_range,
            "--target-pubkey", pubkey_target,
            "--address", target_addr,
            "--dp-bits", str(dp_bits),
            "--grid", grid,
            "--slices", slices,
            "--gpus", str(gpu_id)
        ]


def parse_line(line_str, engine_type):
    """
    Extrai speed, count e chave encontrada da linha de output.
    Retorna (speed_mkeys, count_keys, found_key_hex_or_None)
    """
    speed = None
    count = None
    found = None

    # ── RCKangaroo output format (do código-fonte e fóruns):
    #    t:12.3s  speed:4567 MH/s  ops:1234567M  dp:89
    #    PRIVATE KEY: 0000000000000000000000000000000000000000000011720C4F
    if engine_type == "rckangaroo":
        # Speed: pode ser MH/s ou GH/s
        m = re.search(r'speed[:\s]+(\d+\.?\d*)\s*([MGK])H', line_str, re.I)
        if m:
            sp = float(m.group(1))
            unit = m.group(2).upper()
            if unit == 'G': sp *= 1000.0
            elif unit == 'K': sp /= 1000.0
            speed = sp

        # ops count
        m = re.search(r'ops[:\s]+([\d.]+)([MK]?)', line_str, re.I)
        if m:
            val = float(m.group(1))
            unit = m.group(2).upper()
            if unit == 'M': val *= 1_000_000
            elif unit == 'K': val *= 1_000
            count = int(val)

        # Chave encontrada — formato: PRIVATE KEY: HEX
        m = re.search(r'PRIVATE KEY[:\s]+([0-9A-Fa-f]+)', line_str, re.I)
        if m:
            found = m.group(1).lstrip('0') or '0'

    # ── CUDACyclone output format:
    #    Time:  80.5 s | Speed:   20.85 Mkeys/s | Count:   1677721600 | Chunks: 262205
    else:
        m = re.search(r'Speed:\s*([\d.]+)\s*(Mkeys/s|Gkeys/s|Kkeys/s)', line_str, re.I)
        if m:
            sp = float(m.group(1))
            unit = m.group(2).upper()
            if 'GKEY' in unit:  sp *= 1000.0
            elif 'KKEY' in unit: sp /= 1000.0
            speed = sp

        m = re.search(r'Count:\s*(\d+)', line_str, re.I)
        if m:
            count = int(m.group(1))

        m = re.search(r'(?:KEY FOUND|Private key)[:\s]+([0-9A-Fa-fx]+)', line_str, re.I)
        if m:
            found = m.group(1)

    return speed, count, found


# ══════════════════════════════════════════════════════════════
# REDE
# ══════════════════════════════════════════════════════════════

def http_post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'User-Agent': 'CycloneX-Worker/4.0'}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


# ══════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="CycloneX Pool Worker Client v4.0")
    parser.add_argument("--server", type=str, default="https://valyrafi.com.br")
    parser.add_argument("--name",   type=str, default=f"Worker-{uuid.uuid4().hex[:6]}")
    parser.add_argument("--gpu",    type=int, default=0)
    args = parser.parse_args()

    server_url = args.server.rstrip('/')
    worker_id  = f"{args.name}-{uuid.uuid4().hex[:8]}"
    engine_label = "RCKangaroo K=1.15 [SOTA]" if ENGINE_TYPE == "rckangaroo" else "CUDACyclone K=2.1"

    print("================================================================")
    print(" 🦘 CYCLONEX WORKER v4.0 — MOTOR DUAL GPU")
    print("================================================================")
    print(f"Master Server : {server_url}")
    print(f"Nome do Nó    : {args.name}")
    print(f"ID do Worker  : {worker_id}")
    print(f"Motor GPU     : {engine_label}")
    print(f"Executável    : {ENGINE_EXE}")
    print("----------------------------------------------------------------", flush=True)

    while True:
        try:
            print("\n🔄 Solicitando trabalho ao Master Server...", flush=True)
            res = http_post(f"{server_url}/api/worker/get-job", {"worker_id": worker_id})

            if res.get("status") != "OK":
                print(f"⚠️  {res.get('message', 'Sem trabalho disponível.')}")
                print("⏳ Aguardando 30 segundos...", flush=True)
                time.sleep(30)
                continue

            job_id         = res["job_id"]
            puzzle         = res["puzzle"]
            slot_idx       = res["slot_index"]
            golden_range   = res["range"]
            pct_range      = res["pct_range"]
            pubkey_target  = res["target_pubkey"]
            target_addr    = res["target_addr"]
            dp_bits        = int(res.get("dp_bits", 24))

            print(f"✅ Slot #{slot_idx} (Puzzle #{puzzle}) — {pct_range}")
            print(f"   Motor: {engine_label}")
            print(f"🚀 Iniciando varredura Kangaroo...", flush=True)

            cmd = build_cmd(ENGINE_EXE, ENGINE_TYPE, golden_range, pubkey_target,
                            target_addr, dp_bits, args.gpu, puzzle_bits=int(puzzle))

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1,
                                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})

            last_hb    = 0
            found_key  = None
            last_speed = 0.0
            last_count = 0

            for line in iter(proc.stdout.readline, ''):
                line_str = line.strip()

                sp, cnt, found = parse_line(line_str, ENGINE_TYPE)
                if sp  is not None: last_speed = sp
                if cnt is not None: last_count = cnt
                if found:
                    found_key = found
                    proc.terminate()
                    break

                now = time.time()
                if last_speed > 0 and now - last_hb >= 10.0:
                    last_hb = now
                    sys.stdout.write(
                        f"\r⏱️ Ativo | ⚡ {last_speed:.1f} Mkeys/s | "
                        f"🔑 {last_count:,} | 🏷️ {engine_label}"
                    )
                    sys.stdout.flush()
                    try:
                        http_post(f"{server_url}/api/worker/heartbeat", {
                            "worker_id":   worker_id,
                            "worker_name": args.name,
                            "gpu_name":    f"GPU#{args.gpu} ({ENGINE_TYPE})",
                            "speed_mkeys": last_speed,
                            "total_keys":  last_count
                        })
                    except Exception:
                        pass

            proc.wait()

            if found_key:
                print(f"\n\n🎉🎉🎉 CHAVE PRIVADA ENCONTRADA: {found_key} 🎉🎉🎉")
                print("🔒 Enviando ao Cofre do Admin na VPS...", flush=True)
                http_post(f"{server_url}/api/worker/submit-solution", {
                    "worker_id":      worker_id,
                    "puzzle":         puzzle,
                    "private_key_hex": found_key,
                    "token_secret":   "solution_vault"
                })
                print("✅ Solução enviada com sucesso! Missão concluída.")
                break

        except Exception as e:
            print(f"\n⚠️ Erro ({e}). Tentando novamente em 15s...", flush=True)
            time.sleep(15)


if __name__ == "__main__":
    main()

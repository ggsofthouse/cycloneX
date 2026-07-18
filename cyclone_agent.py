"""
CycloneX Agent v2.0
====================
Servidor HTTP puro + SSE (Server-Sent Events) para o dashboard.
Executa CUDACyclone.exe real e transmite dados em tempo real.
Sem dependências externas — só Python stdlib.
"""
import os
import sys
import time
import json
import random
import hashlib
import threading
import webbrowser
import subprocess
import re
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from io import BytesIO
import sqlite3

# Forcar UTF-8 no stdout do Windows
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── DETECTAR ONDE ESTÁ O EXE ──────────────────────────────────────────────────
def find_exe():
    """Procura CUDACyclone.exe na pasta atual e sub-pastas comuns."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "CUDACyclone.exe"),
        os.path.join(os.path.dirname(__file__), "CUDACyclone-main", "CUDACyclone.exe"),
        os.path.join(os.path.dirname(__file__), "bin", "CUDACyclone.exe"),
        "CUDACyclone.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None

CUDA_EXE = find_exe()

# ── PARSER DE CONFIG YAML SIMPLES ────────────────────────────────────────────
def load_config(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "config.yaml")
    cfg = {}
    if not os.path.exists(path):
        return cfg
    current_section = ""
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line:
                continue
            if line.endswith(':') and ':' not in line[:-1]:
                current_section = line[:-1].strip()
                cfg[current_section] = {}
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                if v.lower() == 'true':
                    v = True
                elif v.lower() == 'false':
                    v = False
                else:
                    try:
                        v = float(v) if '.' in v else int(v)
                    except (ValueError, TypeError):
                        pass
                if current_section:
                    cfg[current_section][k] = v
                else:
                    cfg[k] = v
    return cfg

# ── CRYPTO HELPERS ────────────────────────────────────────────────────────────
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def base58_encode(b):
    zeros = len(b) - len(b.lstrip(b'\x00'))
    n = int.from_bytes(b, 'big')
    result = []
    while n > 0:
        n, r = divmod(n, 58)
        result.append(BASE58_ALPHABET[r])
    return '1' * zeros + ''.join(reversed(result))

def base58check_encode(payload, version=0):
    data = bytes([version]) + payload
    cs = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return base58_encode(data + cs)

def private_key_to_wif(priv_hex, compressed=True):
    try:
        # Converter hex da chave privada para bytes (32 bytes)
        priv_bytes = bytes.fromhex(priv_hex.zfill(64))
        # Prefixo do mainnet (0x80)
        payload = b'\x80' + priv_bytes
        if compressed:
            payload += b'\x01'
        # Calcular checksum double-SHA256
        cs = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        return base58_encode(payload + cs)
    except Exception as e:
        return f"Error generating WIF: {e}"

def trigger_system_alarm():
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "volume_max.ps1")
        if os.path.exists(script_path):
            import subprocess
            subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path], creationflags=0x08000000) # DETACHED_PROCESS
            print("[Alarm] Alarme de som iniciado com sucesso!")
    except Exception as e:
        print(f"[Alarm] Erro ao disparar alarme: {e}")


def validate_crypto_result(pubkey_hex, reported_address):
    try:
        pb = bytes.fromhex(pubkey_hex)
        sha = hashlib.sha256(pb).digest()
        h = hashlib.new('ripemd160')
        h.update(sha)
        hash160 = h.digest()
        computed = base58check_encode(hash160, 0x00)
        ok = (computed == reported_address)
        return ok, {"hash160": hash160.hex(), "address": computed}
    except Exception as e:
        return False, str(e)

# ── ESTADO GLOBAL ─────────────────────────────────────────────────────────────
class PlatformState:
    def __init__(self):
        self.lock = threading.Lock()
        # GPU / processo
        self.process = None
        self.proc_thread = None
        self.job_running = False
        self.job_name = ""
        # Métricas em tempo real
        self.speed_mkeys = 0.0   # MKeys/s
        self.keys_checked = 0
        self.chunks = 0
        self.temp_c = 45
        self.temp_hotspot = 57
        self.power_w = 120
        self.clock_mhz = 1350
        self.voltage_mv = 850
        self.fan_pct = 40
        self.vram_used = int(1.8 * 1024**3)
        self.vram_total = int(8 * 1024**3)
        self.uptime_sec = 0
        self.start_time = 0.0
        # Log lines do CUDA (últimas N)
        self.cuda_log = []
        self.MAX_LOG = 200
        # Resultados encontrados
        self.results_found = []
        # SSE clients
        self.sse_clients = []
        # ── Performance / Auto Tuner ──────────────────────────────────────────
        self.perf_runs = []          # lista de dicts com cada benchmark gravado
        self.best_config = None      # dict com a melhor configuração encontrada
        self.tuner_running = False   # Auto Tuner em execução?
        self.tuner_phase = 0         # índice da fase atual do tuner
        self.tuner_phases = []       # lista de fases com status e resultado
        self.tuner_thread = None
        # ── Distributed Pool Engine ───────────────────────────────────────────
        self.pool_workers = {}       # worker_id -> { "last_active", "gpu", "speed", "temp", "clock", "block_id", "power_w" }
        self.current_worker_block = None # Usado no modo worker para saber qual bloco está rodando
        self.current_block_progress = 0.0

state = PlatformState()
state.gpu_name = "NVIDIA GeForce GPU"  # sera sobrescrito ao parsear output CUDA

# ── NVIDIA-SMI PARA METRICAS REAIS ────────────────────────────────────────────
def _poll_nvidia_smi():
    """Lê temperatura, power e clock reais via nvidia-smi a cada 2s."""
    while True:
        try:
            r = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=temperature.gpu,power.draw,clocks.current.graphics,fan.speed,memory.used,memory.total,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                parts = [p.strip() for p in r.stdout.strip().split(',')]
                if len(parts) >= 7:
                    with state.lock:
                        try:
                            state.temp_c = int(float(parts[0]))
                            state.temp_hotspot = state.temp_c + 12
                        except: pass
                        try: state.power_w  = int(float(parts[1]))
                        except: pass
                        try: state.clock_mhz= int(float(parts[2]))
                        except: pass
                        try: state.fan_pct   = int(float(parts[3]))
                        except: pass
                        try: state.vram_used = int(float(parts[4])) * 1024 * 1024
                        except: pass
                        try: state.vram_total = int(float(parts[5])) * 1024 * 1024
                        except: pass
                        
                        # Estimar voltagem de forma realista:
                        # Em repouso: 700-750mV, Rodando busca: 900-1000mV
                        if state.job_running:
                            state.voltage_mv = int(925 + (state.clock_mhz % 100) * 0.5)
                        else:
                            state.voltage_mv = int(710 + (state.temp_c % 20) * 2)

                        name = parts[6].strip()
                        if name:
                            state.gpu_name = name
        except Exception:
            pass
        time.sleep(5)

_t_smi = threading.Thread(target=_poll_nvidia_smi, daemon=True)
_t_smi.start()

# Regex para parsear output do CUDACyclone
_RE_STATS  = re.compile(
    r"Time:\s+([\d.]+)\s+s\s*\|\s*Speed:\s+([\d.]+)\s+([\w/]+)\s*\|\s*Count:\s+(\d+)"
    r"(?:\s*\|\s*(Chunks|Progress):\s*([\d.]+))?",
    re.IGNORECASE
)
_RE_GPU_NAME = re.compile(r"GPU\s+\d+\s*:\s*(.+?)\s*\|", re.IGNORECASE)
_RE_PRIVKEY = re.compile(r"Private\s*Key\s*[:\s]+([0-9A-Fa-fx]+)", re.IGNORECASE)
_RE_PUBKEY  = re.compile(r"Public\s*Key\s*[:\s]+([0-9A-Fa-f]{64,130})", re.IGNORECASE)
_RE_ADDR    = re.compile(r"Address\s*[:\s]+(1[A-Za-z0-9]{25,34})", re.IGNORECASE)

# ── SSE BROADCAST ─────────────────────────────────────────────────────────────
def sse_broadcast(event_type, data_dict):
    """Envia evento SSE para todos os clientes conectados."""
    payload = f"event: {event_type}\ndata: {json.dumps(data_dict)}\n\n"
    payload_bytes = payload.encode("utf-8")
    dead = []
    with state.lock:
        clients = list(state.sse_clients)
    for q in clients:
        try:
            q.put(payload_bytes)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            state.sse_clients.remove(q)
        except ValueError:
            pass

# ── PROCESSO CUDA ─────────────────────────────────────────────────────────────
def _run_cuda(custom_job=None):
    """Thread que executa CUDACyclone.exe e processa seu output."""
    global state
    cfg = load_config()
    if custom_job:
        job = custom_job
    else:
        job = cfg.get("job", {})

    if not CUDA_EXE:
        print("[Agent] ERRO: CUDACyclone.exe não encontrado!")
        state.job_running = False
        sse_broadcast("error", {"message": "CUDACyclone.exe not found on this machine."})
        return

    range_str   = str(job.get("range",  "600000000000000000:7fffffffffffffffff"))
    address_str = str(job.get("address", "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU"))
    grid_str    = str(job.get("grid",    "1024,512"))
    slices_val  = str(job.get("slices",  64))
    gpus_str    = str(job.get("gpus",    "0"))
    random_mode = job.get("random", True)
    job_name    = str(job.get("name", "Puzzle71"))

    cmd = [
        CUDA_EXE,
        "--range",   range_str,
        "--address", address_str,
        "--grid",    grid_str,
        "--slices",  slices_val,
        "--gpus",    gpus_str,
    ]
    if random_mode:
        cmd.append("--random")

    print(f"\n[Agent] Iniciando CUDACyclone.exe")
    print(f"        EXE:     {CUDA_EXE}")
    print(f"        Range:   {range_str}")
    print(f"        Address: {address_str}")
    print(f"        Grid:    {grid_str} | Slices: {slices_val}")
    print(f"        GPUs:    {gpus_str} | Random: {random_mode}\n")

    private_key = ""
    public_key  = ""
    found_addr  = ""

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(CUDA_EXE)
        )
        state.process = proc
        state.job_running = True
        state.job_name = job_name
        state.start_time = time.time()

        sse_broadcast("job_started", {
            "job": job_name,
            "address": address_str,
            "range": range_str,
            "exe": CUDA_EXE
        })

        for raw_line in iter(proc.stdout.readline, ""):
            line = raw_line.rstrip()
            if not line:
                continue

            # Parsear nome da GPU do header CUDA
            gm = _RE_GPU_NAME.search(line)
            if gm:
                name = gm.group(1).strip()
                if name and len(name) > 5:
                    with state.lock:
                        state.gpu_name = name

            # Parsear estatísticas de progresso
            m = _RE_STATS.search(line)
            if m:
                speed_val = float(m.group(2))
                unit      = m.group(3).upper()
                count_val = int(m.group(4))

                # Normalizar para MKeys/s
                if "GKEYS" in unit or "GKEY" in unit:
                    speed_mkeys = speed_val * 1000
                elif "TKEYS" in unit or "TKEY" in unit:
                    speed_mkeys = speed_val * 1_000_000
                elif "KKEYS" in unit or "KKEY" in unit:
                    speed_mkeys = speed_val / 1000
                else:
                    speed_mkeys = speed_val  # assume MKeys/s

                chunks_val = state.chunks
                progress_pct = 0.0
                if m.group(5):
                    label = m.group(5).upper()
                    if "PROGRESS" in label:
                        try:
                            progress_pct = float(m.group(6))
                        except Exception:
                            pass
                    elif "CHUNKS" in label:
                        try:
                            chunks_val = int(float(m.group(6)))
                        except Exception:
                            pass

                with state.lock:
                    if state.speed_mkeys > 0:
                        state.speed_mkeys = state.speed_mkeys * 0.75 + speed_mkeys * 0.25
                    else:
                        state.speed_mkeys = speed_mkeys
                    state.keys_checked = count_val
                    state.chunks       = chunks_val
                    state.current_block_progress = progress_pct
                    # cuda_log = somente a linha de stats atual (linha unica)
                    state.cuda_log = [line.strip()]

                    # Registrar a própria GPU local na pool para exibição visual
                    local_worker_id = socket.gethostname()
                    active_block = state.current_worker_block.get("id") if state.current_worker_block else ("Master GPU" if state.job_running else None)
                    state.pool_workers[local_worker_id] = {
                        "last_active": time.time(),
                        "gpu": state.gpu_name,
                        "speed": state.speed_mkeys,
                        "temp": state.temp_c,
                        "power": state.power_w,
                        "clock": state.clock_mhz,
                        "fan": state.fan_pct,
                        "block_id": active_block,
                        "progress": progress_pct
                    }

                # Print no terminal (linha unica com \r)
                sys.stdout.write(f"\r[CUDA] {line.strip()}")
                sys.stdout.flush()


                # Broadcast telemetria a cada linha de stats
                sse_broadcast("telemetry", _build_telemetry())

                # Limite de chaves para blocos randômicos ou limitados
                key_limit = job.get("key_limit")
                if key_limit and count_val >= key_limit:
                    print(f"\n[Agent] Limite de chaves atingido ({count_val} >= {key_limit}). Parando CUDACyclone...")
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                    break
                continue

            # Parsear achado
            pk = _RE_PRIVKEY.search(line)
            if pk:
                private_key = pk.group(1).strip()

            pb = _RE_PUBKEY.search(line)
            if pb:
                public_key = pb.group(1).strip()

            ad = _RE_ADDR.search(line)
            if ad:
                found_addr = ad.group(1).strip()

            if private_key and (public_key or found_addr):
                target_addr = found_addr or address_str
                valid, details = False, {}
                if public_key:
                    valid, details = validate_crypto_result(public_key, target_addr)

                result = {
                    "machine":      "cyclonex-node-01",
                    "gpu":          "NVIDIA GPU (Real CUDA)",
                    "job":          job_name,
                    "plugin":       "bitcoin",
                    "status":       "FOUND",
                    "duration":     _fmt_duration(time.time() - state.start_time),
                    "keys_checked": state.keys_checked,
                    "timestamp":    time.time() * 1000,
                    "private_key":  private_key,
                    "private_key_wif_compressed": private_key_to_wif(private_key, compressed=True),
                    "private_key_wif_uncompressed": private_key_to_wif(private_key, compressed=False),
                    "public_key":   public_key,
                    "address":      target_addr,
                    "avg_speed":    f"{state.speed_mkeys/1000:.2f} GKeys/s",
                    "avg_speed_mkeys": int(state.speed_mkeys),
                    "temp_at_found": state.temp_c,
                    "power_at_found": state.power_w,
                    "clock_at_found": state.clock_mhz,
                    "agent_version": "v2.0.0",
                    "validation":   valid,
                }
                with state.lock:
                    state.results_found.insert(0, result)
                    state.job_running = False

                print(f"\n[Agent] !!!  KEY FOUND  !!!")
                print(f"        Private Key: {private_key}")
                sse_broadcast("found", result)
                trigger_system_alarm()
                break

        proc.wait()

    except Exception as e:
        print(f"[Agent] Erro no processo CUDA: {e}")
        sse_broadcast("error", {"message": str(e)})
    finally:
        elapsed = time.time() - state.start_time if state.start_time else 0
        # Registrar run normal na tabela de performance
        if elapsed > 5 and state.speed_mkeys > 0:
            run_record = {
                "grid":        grid_str.replace(",", "×"),
                "slices":      int(slices_val),
                "speed_mkeys": round(state.speed_mkeys, 1),
                "temp_c":      state.temp_c,
                "clock_mhz":  state.clock_mhz,
                "duration_s": round(elapsed, 1),
                "gpu":        state.gpu_name,
                "timestamp":  time.time() * 1000,
                "source":     "job",
            }
            with state.lock:
                state.perf_runs.append(run_record)
                runs_copy = list(state.perf_runs)
            sse_broadcast("perf_update", {"run": run_record, "runs": runs_copy})
        with state.lock:
            state.job_running  = False
            state.speed_mkeys  = 0.0
            state.process      = None


# ── DISTRIBUTED POOL ENGINE ────────────────────────────────────────────────────
def init_pool_db():
    cfg = load_config()
    db_path = cfg.get("database", {}).get("path", "./cyclone.db")
    pool_cfg = cfg.get("pool", {})
    role = pool_cfg.get("role", "standalone")
    if role != "master":
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Migração automática: se a tabela pool_ranges existia sem block_index ou active_hypothesis,
    # significa que era do modo antigo. Dropamos para recriar.
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pool_ranges'")
    has_table = cursor.fetchone()
    if has_table:
        cursor.execute("PRAGMA table_info(pool_ranges)")
        cols = [col[1] for col in cursor.fetchall()]
        if len(cols) > 0 and ("block_index" not in cols or "active_hypothesis" not in cols):
            print("[Pool] Migrando banco de dados para suporte a blocos aleatórios com hipóteses...")
            cursor.execute("DROP TABLE IF EXISTS pool_ranges")
            conn.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pool_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_index INTEGER UNIQUE,
            start_hex TEXT NOT NULL,
            end_hex TEXT NOT NULL,
            status TEXT DEFAULT 'processing',
            worker_id TEXT,
            active_hypothesis TEXT,
            updated_at REAL
        )
    """)
    conn.commit()
    conn.close()


def _pool_timeout_monitor():
    cfg = load_config()
    db_path = cfg.get("database", {}).get("path", "./cyclone.db")
    role = cfg.get("pool", {}).get("role", "standalone")
    if role != "master":
        return

    while True:
        time.sleep(30)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            now = time.time()
            timeout_limit = now - 900.0  # 15 minutos
            
            # Busca blocos marcados como processing com worker inativo há >15min
            cursor.execute("SELECT id, worker_id FROM pool_ranges WHERE status = 'processing' AND updated_at < ? AND worker_id IS NOT NULL", (timeout_limit,))
            timed_out = cursor.fetchall()
            if timed_out:
                for row in timed_out:
                    print(f"[Pool] Bloco {row[0]} expirou do worker {row[1]}. Disponibilizando novamente.")
                cursor.execute(
                    "UPDATE pool_ranges SET worker_id = NULL, updated_at = ? WHERE status = 'processing' AND updated_at < ?",
                    (now, timeout_limit)
                )
                conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Pool Monitor] Erro: {e}")


def _pool_worker_loop():
    global state
    cfg = load_config()
    pool_cfg = cfg.get("pool", {})
    master_url = pool_cfg.get("master_url", "http://localhost:8080").rstrip('/')
    worker_id = socket.gethostname()
    token = cfg.get("api", {}).get("token", "cyclone_token_12345")
    
    import urllib.request
    
    print(f"[Worker] Loop do Worker iniciado para '{worker_id}' conectado a {master_url}")
    
    while True:
        # 1. Pede range ao Master
        req_url = f"{master_url}/api/pool/request-work"
        try:
            req_data = json.dumps({"worker_id": worker_id}).encode('utf-8')
            req = urllib.request.Request(
                req_url, 
                data=req_data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                resp = json.loads(r.read().decode('utf-8'))
        except Exception as e:
            print(f"[Worker] Erro ao conectar ao Master para pedir bloco: {e}")
            time.sleep(10)
            continue
            
        if resp.get("status") == "found":
            print("[Worker] !!! A busca foi encerrada pois a chave já foi encontrada na Pool !!!")
            break
            
        if resp.get("status") != "ok" or not resp.get("range"):
            print("[Worker] Sem blocos disponíveis no Master. Aguardando 15s...")
            time.sleep(15)
            continue
            
        block_id = resp["block_id"]
        start_hex = resp["range"]["start"]
        end_hex = resp["range"]["end"]
        address = resp["address"]
        active_hypothesis = resp.get("active_hypothesis", "Uniform")
        
        print(f"[Worker] Bloco #{block_id} atribuído ({active_hypothesis}): {start_hex} -> {end_hex}")
        
        with state.lock:
            state.current_worker_block = {
                "id": block_id,
                "start": start_hex,
                "end": end_hex,
                "address": address,
                "active_hypothesis": active_hypothesis
            }
        
        # Monta a configuração do job customizado
        job_cfg = cfg.get("job", {})
        pool_cfg = cfg.get("pool", {})
        random_in_block = pool_cfg.get("random_in_block", False)
        
        # Calcular o limite de chaves para o bloco
        block_size_gkeys = int(pool_cfg.get("block_size_gkeys", 200))
        key_limit = block_size_gkeys * 1_000_000_000
        
        custom_job = {
            "range": f"{start_hex}:{end_hex}",
            "address": address,
            "grid": job_cfg.get("grid", "512,1024"),
            "slices": job_cfg.get("slices", 512),
            "gpus": job_cfg.get("gpus", "0"),
            "random": random_in_block,
            "key_limit": key_limit,
            "name": f"Block_{block_id}"
        }
        
        # Executa o solver CUDACyclone de forma síncrona nesta thread
        _run_cuda(custom_job)
        
        # O solver terminou. Vamos ver se achou a chave
        found_key = None
        with state.lock:
            # Verifica se algum resultado foi achado durante este run
            for res in state.results_found:
                if res.get("job") == f"Block_{block_id}":
                    found_key = res
                    break
        
        if found_key:
            print(f"[Worker] !!! CHAVE ENCONTRADA no Bloco #{block_id} !!!")
            # Envia o achado para o Master
            try:
                found_url = f"{master_url}/api/pool/found"
                req_data = json.dumps(found_key).encode('utf-8')
                req = urllib.request.Request(
                    found_url,
                    data=req_data,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    r.read()
            except Exception as e:
                print(f"[Worker] Falha ao enviar chave encontrada ao Master: {e}")
            break # Encerra o loop para segurança
            
        else:
            # Relata finalização de bloco com sucesso (sem chaves)
            print(f"[Worker] Bloco #{block_id} concluído. Relatando ao Master...")
            try:
                submit_url = f"{master_url}/api/pool/submit-work"
                submit_data = json.dumps({"block_id": block_id, "worker_id": worker_id}).encode('utf-8')
                req = urllib.request.Request(
                    submit_url,
                    data=submit_data,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    r.read()
            except Exception as e:
                print(f"[Worker] Falha ao enviar status de conclusão do bloco #{block_id}: {e}")
                time.sleep(5)
        
        with state.lock:
            state.current_worker_block = None


def _pool_worker_telemetry_loop():
    global state
    cfg = load_config()
    pool_cfg = cfg.get("pool", {})
    master_url = pool_cfg.get("master_url", "http://localhost:8080").rstrip('/')
    worker_id = socket.gethostname()
    token = cfg.get("api", {}).get("token", "cyclone_token_12345")
    
    import urllib.request
    
    while True:
        time.sleep(5)
        if pool_cfg.get("role") != "worker":
            continue
            
        with state.lock:
            active_block = state.current_worker_block.get("id") if state.current_worker_block else None
            active_hyp = state.current_worker_block.get("active_hypothesis", "Uniform") if state.current_worker_block else "Idle"
            payload = {
                "worker_id": worker_id,
                "block_id": active_block,
                "active_hypothesis": active_hyp,
                "progress": state.current_block_progress,
                "speed_mkeys": int(state.speed_mkeys),
                "temp_c": state.temp_c,
                "power_w": state.power_w,
                "clock_mhz": state.clock_mhz,
                "fan_pct": state.fan_pct,
                "gpu": state.gpu_name,
                "timestamp": time.time()
            }
            
        try:
            req_data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f"{master_url}/api/pool/telemetry",
                data=req_data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                r.read()
        except Exception:
            pass


# ── PERFORMANCE BENCHMARKING ───────────────────────────────────────────────────
TUNER_SLICES = [16, 32, 64, 128, 256]
TUNER_DURATION_SEC = 20   # segundos por fase (configurável via config.yaml)


def _run_benchmark(grid_str, slices_val, duration_sec=20):
    """Executa CUDACyclone.exe por `duration_sec` segundos e retorna métricas médias."""
    global state
    cfg = load_config()
    job = cfg.get("job", {})
    address_str = str(job.get("address", "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU"))
    range_str   = str(job.get("range",  "600000000000000000:7fffffffffffffffff"))
    gpus_str    = str(job.get("gpus",   "0"))

    if not CUDA_EXE:
        return None

    cmd = [
        CUDA_EXE,
        "--range",   range_str,
        "--address", address_str,
        "--grid",    grid_str,
        "--slices",  str(slices_val),
        "--gpus",    gpus_str,
        "--random",
    ]

    speeds = []
    start_ts = time.time()

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            cwd=os.path.dirname(CUDA_EXE)
        )
        with state.lock:
            state.process = proc

        for raw_line in iter(proc.stdout.readline, ""):
            if time.time() - start_ts >= duration_sec:
                break
            if not state.tuner_running:
                break
            m = _RE_STATS.search(raw_line)
            if m:
                speed_val = float(m.group(2))
                unit = m.group(3).upper()
                if "GKEYS" in unit or "GKEY" in unit:
                    speeds.append(speed_val * 1000)
                elif "KKEYS" in unit or "KKEY" in unit:
                    speeds.append(speed_val / 1000)
                else:
                    speeds.append(speed_val)

        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try: proc.kill()
            except Exception: pass
    except Exception as e:
        print(f"[Benchmark] Erro: {e}")
        return None
    finally:
        with state.lock:
            state.process = None

    if not speeds:
        return None

    avg_speed = sum(speeds) / len(speeds)
    with state.lock:
        snap_temp  = state.temp_c
        snap_clock = state.clock_mhz
        gpu_name   = state.gpu_name

    run = {
        "grid":       grid_str.replace(",", "×"),
        "slices":     slices_val,
        "speed_mkeys": round(avg_speed, 1),
        "temp_c":     snap_temp,
        "clock_mhz":  snap_clock,
        "duration_s": round(time.time() - start_ts, 1),
        "gpu":        gpu_name,
        "timestamp":  time.time() * 1000,
    }
    return run


def run_auto_tuner():
    """Executa o Auto Tuner: testa cada valor de slices e escolhe o melhor."""
    global state
    cfg = load_config()
    job = cfg.get("job", {})
    grid_str = str(job.get("grid", "1024,512"))
    duration_sec = int(cfg.get("tuner", {}).get("duration_per_phase", TUNER_DURATION_SEC))

    # Inicializar fases
    phases = [{"slices": s, "status": "pending", "speed_mkeys": None} for s in TUNER_SLICES]
    with state.lock:
        state.tuner_running = True
        state.tuner_phases = phases
        state.tuner_phase = 0

    sse_broadcast("tuner_phase", {"phases": phases, "current": -1, "status": "started"})
    print(f"\n[AutoTuner] Iniciando — Grid: {grid_str} | {len(TUNER_SLICES)} fases de {duration_sec}s cada")

    best_run = None

    for i, slices in enumerate(TUNER_SLICES):
        if not state.tuner_running:
            break

        with state.lock:
            state.tuner_phase = i
            state.tuner_phases[i]["status"] = "running"

        sse_broadcast("tuner_phase", {
            "phases": state.tuner_phases,
            "current": i,
            "status": "running",
        })
        print(f"[AutoTuner] Fase {i+1}/{len(TUNER_SLICES)} — Slices={slices}")

        run = _run_benchmark(grid_str, slices, duration_sec)

        with state.lock:
            if run:
                state.tuner_phases[i]["status"] = "done"
                state.tuner_phases[i]["speed_mkeys"] = run["speed_mkeys"]
                # Guardar em perf_runs
                state.perf_runs.append(run)
                if best_run is None or run["speed_mkeys"] > best_run["speed_mkeys"]:
                    best_run = run
            else:
                state.tuner_phases[i]["status"] = "error"

        sse_broadcast("tuner_phase", {
            "phases": state.tuner_phases,
            "current": i,
            "status": "phase_done",
            "run": run,
        })
        sse_broadcast("perf_update", {"run": run, "runs": state.perf_runs})

    # Marcar melhor fase
    if best_run:
        with state.lock:
            state.best_config = best_run
            # Marcar a fase vencedora
            for ph in state.tuner_phases:
                if ph["slices"] == best_run["slices"]:
                    ph["best"] = True

        # Salvar melhor config no config.yaml
        try:
            cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
            old_cfg = load_config()
            old_cfg.setdefault("job", {})
            old_cfg["job"]["slices"] = best_run["slices"]
            old_cfg["job"]["grid"]   = best_run["grid"].replace("×", ",")
            _write_config(old_cfg, cfg_path)
            print(f"[AutoTuner] Melhor config salva: Slices={best_run['slices']} | Speed={best_run['speed_mkeys']:.1f} MKeys/s")
        except Exception as e:
            print(f"[AutoTuner] Erro ao salvar config: {e}")

        sse_broadcast("tuner_done", {
            "best": best_run,
            "phases": state.tuner_phases,
        })
    else:
        sse_broadcast("tuner_done", {"best": None, "phases": state.tuner_phases, "error": "No valid results"})

    with state.lock:
        state.tuner_running = False

    print("[AutoTuner] Concluído!")


def start_auto_tuner():
    if state.tuner_running:
        return False, "AutoTuner already running"
    if state.job_running:
        return False, "Stop the current job before running AutoTuner"
    t = threading.Thread(target=run_auto_tuner, daemon=True)
    t.start()
    state.tuner_thread = t
    return True, "AutoTuner started"


def stop_auto_tuner():
    state.tuner_running = False
    if state.process:
        try:
            state.process.terminate()
            state.process.kill()
        except Exception:
            pass
    sse_broadcast("tuner_done", {"best": state.best_config, "phases": state.tuner_phases, "error": "Stopped by user"})


def _fmt_duration(seconds):
    d = int(seconds // 86400)
    h = int((seconds % 86400) // 3600)
    m = int((seconds % 3600) // 60)
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {int(seconds%60)}s"


def _build_telemetry():
    """Constroi o payload de status completo (deve ser chamado com lock se necessario)."""
    cfg = load_config()
    job = cfg.get("job", {})

    # -- Maquina local (Master / Standalone) --
    local_machine = {
        "id":           "cyclonex-node-01",
        "status":       "online" if state.job_running else "idle",
        "gpu":          state.gpu_name,
        "gpu_count":    1,
        "speed_mkeys":  int(state.speed_mkeys),
        "temp_c":       state.temp_c,
        "temp_hotspot": state.temp_hotspot,
        "power_w":      state.power_w,
        "power_limit_w": 285,
        "clock_mhz":    state.clock_mhz,
        "voltage_mv":   state.voltage_mv,
        "vram_used":    state.vram_used,
        "vram_total":   state.vram_total,
        "fan_pct":      state.fan_pct,
        "uptime_seconds": state.uptime_sec,
        "chunks_done":  state.chunks,
        "job_id":       state.job_name if state.job_running else "",
        "keys_checked": state.keys_checked,
        "agent_version": "v2.0.0",
        "exe_path":     CUDA_EXE or "NOT FOUND",
        "is_pool_worker": False,
    }

    # -- Workers da Pool (Kaggle / remoto) --
    pool_machines = []
    _now = time.time()
    for w_id, w in list(state.pool_workers.items()):
        # Considera ativo se fez telemetria nos ultimos 15s
        if _now - w.get("last_active", 0) > 15.0:
            continue
        block_info = "Block_" + str(w.get("block_id", "?")) if w.get("block_id") else ""
        pool_machines.append({
            "id":            w_id,
            "status":        "online",
            "gpu":           w.get("gpu", "Unknown GPU"),
            "gpu_count":     1,
            "speed_mkeys":   int(w.get("speed", 0)),
            "temp_c":        int(w.get("temp", 0)),
            "temp_hotspot":  int(w.get("temp", 0)) + 8,
            "power_w":       int(w.get("power", 0)),
            "power_limit_w": 150,
            "clock_mhz":     int(w.get("clock", 0)),
            "voltage_mv":    0,
            "vram_used":     0,
            "vram_total":    0,
            "fan_pct":       int(w.get("fan", 0)),
            "uptime_seconds": 0,
            "chunks_done":   0,
            "job_id":        block_info,
            "keys_checked":  0,
            "agent_version": "worker",
            "exe_path":      "remote",
            "is_pool_worker": True,
            "active_hypothesis": w.get("active_hypothesis", ""),
            "block_progress": round(w.get("progress", 0.0), 2),
        })

    all_machines = [local_machine] + pool_machines

    return {
        "type": "full_state",
        "data": {
            "machines": all_machines,
            "jobs": [{
                "id":          state.job_name,
                "plugin":      "bitcoin",
                "mode":        "random" if job.get("random", True) else "sequential",
                "range_start": str(job.get("range", "")),
                "range_end":   "",
                "target":      str(job.get("address", "")),
                "priority":    1,
                "status":      "running" if state.job_running else "queued",
                "keys_checked": state.keys_checked,
                "chunks_done":  state.chunks,
            }],
            "history": state.results_found,
            "cuda_log": state.cuda_log[-50:],   # ultimas 50 linhas
        }
    }

def start_job():
    if state.job_running:
        return False, "Job already running"
    t = threading.Thread(target=_run_cuda, daemon=True)
    t.start()
    state.proc_thread = t
    return True, "Job started"


def stop_job():
    if state.process:
        try:
            state.process.terminate()
            state.process.kill()
        except Exception:
            pass
    state.job_running = False
    state.speed_mkeys = 0.0
    sse_broadcast("job_stopped", {"message": "Job cancelled by user"})


# ── UPTIME COUNTER ────────────────────────────────────────────────────────────
def _uptime_loop():
    while True:
        time.sleep(1)
        state.uptime_sec += 1
        # Broadcast a cada 2s mesmo sem linhas CUDA (heartbeat)
        if state.uptime_sec % 2 == 0:
            sse_broadcast("telemetry", _build_telemetry())


# ── HTTP HANDLER ──────────────────────────────────────────────────────────────
DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".png":  "image/png",
    ".ico":  "image/x-icon",
    ".svg":  "image/svg+xml",
    ".woff2": "font/woff2",
}

class CycloneHandler(BaseHTTPRequestHandler):
    # Suprimir log padrão
    def log_message(self, fmt, *args):
        pass

    def log_request(self, *args):
        pass

    def _is_auth(self):
        cfg = load_config()
        token = str(cfg.get("api", {}).get("token", "")).strip()
        if not token or token == "None" or token == "":
            return True # Livre se não houver senha no config.yaml
            
        # 1. Verificar Header Authorization
        auth_hdr = self.headers.get("Authorization", "")
        if auth_hdr.startswith("Bearer "):
            req_token = auth_hdr[7:].strip()
            if req_token == token:
                return True
                
        # 2. Verificar query parameter (usado no SSE EventSource)
        parsed = urlparse(self.path)
        q = parse_qs(parsed.query)
        if "token" in q:
            if q["token"][0] == token:
                return True
                
        return False

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── GET ──
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Bloquear chamadas de API sem token
        if path.startswith("/api/") and not self._is_auth():
            self._json(401, {"status": "error", "message": "Unauthorized"})
            return

        # ── Pool Status ──
        if path == "/api/pool/status":
            cfg = load_config()
            db_path = cfg.get("database", {}).get("path", "./cyclone.db")
            
            pool_cfg = cfg.get("pool", {})
            block_size_gkeys = int(pool_cfg.get("block_size_gkeys", 200))
            block_size = block_size_gkeys * 1_000_000_000
            
            job_cfg = cfg.get("job", {})
            range_str = job_cfg.get("range", "400000000000000000:7fffffffffffffffff")
            blocks_total = 23058430 # default fallback
            try:
                parts = range_str.split(':')
                start_val = int(parts[0].strip(), 16)
                end_val = int(parts[1].strip(), 16)
                total_keys = end_val - start_val + 1
                blocks_total = max(1, total_keys // block_size)
            except Exception:
                pass
                
            stats = {"processing": 0, "completed": 0}
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT status, COUNT(*) FROM pool_ranges GROUP BY status")
                for r in cursor.fetchall():
                    stats[r[0]] = r[1]
                conn.close()
            except Exception:
                pass
            
            completed = stats.get("completed", 0)
            processing = stats.get("processing", 0)
            pending = max(0, blocks_total - completed - processing)
            
            with state.lock:
                workers_copy = {k: dict(v) for k, v in state.pool_workers.items()}
                now = time.time()
                for w_id in list(workers_copy.keys()):
                    if now - workers_copy[w_id].get("last_active", 0) > 15.0:
                        del workers_copy[w_id]
            
            self._json(200, {
                "status": "ok",
                "blocks_total": blocks_total,
                "blocks_completed": completed,
                "blocks_processing": processing,
                "blocks_pending": pending,
                "workers": workers_copy
            })
            return

        # ── SSE stream ──
        if path == "/api/stream":
            self._handle_sse()
            return

        # ── Status JSON ──
        if path == "/api/status":
            self._json(200, _build_telemetry())
            return

        # ── Log lines ──
        if path == "/api/log":
            with state.lock:
                self._json(200, {"lines": state.cuda_log[-100:]})
            return

        # ── Config ──
        if path == "/api/config":
            self._json(200, load_config())
            return

        # ── Info ──
        if path == "/api/info":
            self._json(200, {
                "version":  "2.0.0",
                "exe":      CUDA_EXE or "NOT FOUND",
                "exe_ok":   bool(CUDA_EXE),
                "platform": sys.platform,
            })
            return

        # ── Performance data ──
        if path == "/api/performance":
            with state.lock:
                self._json(200, {
                    "runs":       list(state.perf_runs),
                    "best":       state.best_config,
                    "tuner_running": state.tuner_running,
                    "tuner_phases":  list(state.tuner_phases),
                })
            return

        # ── Dashboard estático ──
        if path == "/" or path == "/index.html":
            file_path = os.path.join(DASHBOARD_DIR, "index.html")
        else:
            file_path = os.path.join(DASHBOARD_DIR, path.lstrip("/"))

        if os.path.isfile(file_path):
            ext  = os.path.splitext(file_path)[1].lower()
            mime = MIME.get(ext, "application/octet-stream")
            with open(file_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    # ── POST ──
    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = {}
        if length > 0:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                pass

        # Bloquear chamadas de API sem token (exceto verificação de auth)
        if path.startswith("/api/") and path != "/api/auth/verify" and not self._is_auth():
            self._json(401, {"status": "error", "message": "Unauthorized"})
            return

        # ── Auth Verify ──
        if path == "/api/auth/verify":
            cfg = load_config()
            token = str(cfg.get("api", {}).get("token", "")).strip()
            provided_token = str(body.get("token", "")).strip()
            if provided_token == token:
                self._json(200, {"status": "ok", "message": "Authorized"})
            else:
                self._json(401, {"status": "error", "message": "Invalid password"})
            return

        # ── Pool Request Work ──
        if path == "/api/pool/request-work":
            worker_id = body.get("worker_id", "unknown_worker")
            cfg = load_config()
            db_path = cfg.get("database", {}).get("path", "./cyclone.db")
            job_cfg = cfg.get("job", {})
            address = job_cfg.get("address", "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU")
            
            pool_cfg = cfg.get("pool", {})
            block_size_gkeys = int(pool_cfg.get("block_size_gkeys", 200))
            block_size = block_size_gkeys * 1_000_000_000
            
            try:
                # Se a chave já foi encontrada, interrompe a busca em toda a pool
                with state.lock:
                    if len(state.results_found) > 0:
                        self._json(200, {"status": "found", "message": "Chave já encontrada na Pool!"})
                        return

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                now = time.time()
                
                # 1. Verificar se o próprio worker já tem um bloco ativo atribuído (retomada pós-fechamento)
                cursor.execute(
                    "SELECT id, start_hex, end_hex, active_hypothesis FROM pool_ranges WHERE status = 'processing' AND worker_id = ? ORDER BY id ASC LIMIT 1",
                    (worker_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    # 2. Tentar reutilizar um bloco expirado (onde worker_id ficou nulo no timeout)
                    cursor.execute(
                        "SELECT id, start_hex, end_hex, active_hypothesis FROM pool_ranges WHERE status = 'processing' AND worker_id IS NULL ORDER BY id ASC LIMIT 1"
                    )
                    row = cursor.fetchone()
                
                if row:
                    if len(row) == 4:
                        block_id, start_hex, end_hex, active_hypothesis = row
                    else:
                        block_id, start_hex, end_hex = row[:3]
                        active_hypothesis = "Resumed"
                        
                    cursor.execute(
                        "UPDATE pool_ranges SET worker_id = ?, updated_at = ? WHERE id = ?",
                        (worker_id, now, block_id)
                    )
                    conn.commit()
                    self._json(200, {
                        "status": "ok",
                        "block_id": block_id,
                        "range": {"start": start_hex, "end": end_hex},
                        "address": address,
                        "active_hypothesis": active_hypothesis
                    })
                else:
                    # 3. Escolha estocástica de novo bloco
                    range_str = job_cfg.get("range", "400000000000000000:7fffffffffffffffff")
                    parts = range_str.split(':')
                    start_val = int(parts[0].strip(), 16)
                    end_val = int(parts[1].strip(), 16)
                    
                    total_keys = end_val - start_val + 1
                    total_blocks = max(1, total_keys // block_size)
                    
                    import random
                    candidates = []
                    
                    # Sorteia até 100 candidatos únicos
                    attempts = 0
                    while len(candidates) < 100 and attempts < 300:
                        idx = random.randint(0, total_blocks - 1)
                        if idx not in candidates:
                            # Confirmar no banco se o bloco já foi processado
                            cursor.execute("SELECT id FROM pool_ranges WHERE block_index = ?", (idx,))
                            if not cursor.fetchone():
                                candidates.append(idx)
                        attempts += 1
                        
                    if not candidates:
                        self._json(200, {"status": "no_work", "message": "Sem blocos disponíveis na Pool."})
                    else:
                        # Seleção estocástica: 50% chance de Uniforme, 50% de Hypothesis Scoring
                        use_scoring = random.random() >= 0.5 and len(_PLUGINS) > 0
                        
                        best_idx = candidates[0]
                        active_hypothesis = "Uniform"
                        
                        if use_scoring:
                            best_score = -1.0
                            active_hypothesis = "Hypothesis"
                            for idx in candidates:
                                block_start = start_val + idx * block_size
                                block_end = block_start + block_size - 1
                                if block_end > end_val:
                                    block_end = end_val
                                    
                                # Somar score de todos os plugins carregados avaliando 3 pontos no bloco (25%, 50% e 75%)

                                    
                                combined_score = 0.0

                                    
                                q25 = block_start + int(block_size * 0.25)

                                    
                                q50 = block_start + int(block_size * 0.50)

                                    
                                q75 = block_start + int(block_size * 0.75)

                                    
                                for name, plugin in _PLUGINS:

                                    
                                    try:

                                    
                                        score_25 = plugin.calculate_score(q25, q25, start_val, end_val)

                                    
                                        score_50 = plugin.calculate_score(q50, q50, start_val, end_val)

                                    
                                        score_75 = plugin.calculate_score(q75, q75, start_val, end_val)

                                    
                                        plugin_score = (score_25 + score_50 + score_75) / 3.0

                                    
                                        combined_score += plugin_score

                                    
                                    except Exception:

                                    
                                        combined_score += 50.0 # fallback médio
                                        
                                combined_score = combined_score / len(_PLUGINS)
                                
                                # Pequena perturbação aleatória (Stochastic Selection) para evitar travamento em ótimos locais
                                combined_score += random.uniform(0.0, 5.0)
                                
                                if combined_score > best_score:
                                    best_score = combined_score
                                    best_idx = idx
                                    
                        block_start = start_val + best_idx * block_size
                        block_end = block_start + block_size - 1
                        if block_end > end_val:
                            block_end = end_val
                            
                        start_hex = f"{block_start:x}"
                        end_hex = f"{block_end:x}"
                        
                        # Criar novo registro atribuído na pool
                        cursor.execute(
                            "INSERT INTO pool_ranges (block_index, start_hex, end_hex, status, worker_id, active_hypothesis, updated_at) VALUES (?, ?, ?, 'processing', ?, ?, ?)",
                            (best_idx, start_hex, end_hex, worker_id, active_hypothesis, now)
                        )
                        block_id = cursor.lastrowid
                        conn.commit()
                        
                        self._json(200, {
                            "status": "ok",
                            "block_id": block_id,
                            "range": {"start": start_hex, "end": end_hex},
                            "address": address,
                            "active_hypothesis": active_hypothesis
                        })
                conn.close()
            except Exception as e:
                self._json(500, {"status": "error", "message": str(e)})
            return

        # ── Pool Submit Work ──
        if path == "/api/pool/submit-work":
            block_id = body.get("block_id")
            worker_id = body.get("worker_id")
            cfg = load_config()
            db_path = cfg.get("database", {}).get("path", "./cyclone.db")
            
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE pool_ranges SET status = 'completed', updated_at = ? WHERE id = ?",
                    (time.time(), block_id)
                )
                conn.commit()
                conn.close()
                print(f"[Pool] Bloco {block_id} concluído pelo worker {worker_id}!")
                self._json(200, {"status": "ok", "message": f"Block {block_id} completed"})
            except Exception as e:
                self._json(500, {"status": "error", "message": str(e)})
            return

        # ── Pool Telemetry ──
        if path == "/api/pool/telemetry":
            worker_id = body.get("worker_id")
            if worker_id:
                with state.lock:
                    state.pool_workers[worker_id] = {
                        "last_active": time.time(),
                        "gpu": body.get("gpu", "Unknown GPU"),
                        "speed": body.get("speed_mkeys", 0),
                        "temp": body.get("temp_c", 0),
                        "power": body.get("power_w", 0),
                        "clock": body.get("clock_mhz", 0),
                        "fan": body.get("fan_pct", 0),
                        "block_id": body.get("block_id"),
                        "progress": body.get("progress", 0.0),
                        "active_hypothesis": body.get("active_hypothesis", "Uniform")
                    }
                self._json(200, {"status": "ok"})
            else:
                self._json(400, {"status": "error", "message": "Missing worker_id"})
            return

        # ── Pool Found Key ──
        if path == "/api/pool/found":
            print(f"\n[Pool Master] !!! CHAVE ENCONTRADA POR WORKER !!!")
            print(f"              Worker: {body.get('machine', 'unknown')}")
            print(f"              Chave : {body.get('private_key', 'unknown')}\n")
            
            # Enriquecer resultado com chaves WIF
            pk_hex = body.get("private_key")
            if pk_hex and "private_key_wif_compressed" not in body:
                body["private_key_wif_compressed"] = private_key_to_wif(pk_hex, compressed=True)
                body["private_key_wif_uncompressed"] = private_key_to_wif(pk_hex, compressed=False)
            with state.lock:
                state.results_found.insert(0, body)
                state.job_running = False
            sse_broadcast("found", body)
            trigger_system_alarm()
            self._json(200, {"status": "ok", "message": "Victory logged"})
            return

        if path == "/api/job/start":
            ok, msg = start_job()
            self._json(200, {"status": "ok" if ok else "error", "message": msg})
            return

        if path == "/api/job/stop":
            stop_job()
            self._json(200, {"status": "ok", "message": "Job stopped"})
            return

        if path == "/api/config/update":
            # Atualizar config.yaml com novos parâmetros
            cfg_path = os.path.join(os.path.dirname(__file__), "config.yaml")
            if body:
                try:
                    # Reescrever config.yaml com os novos valores
                    old_cfg = load_config()
                    job_cfg = old_cfg.get("job", {})
                    for k, v in body.items():
                        job_cfg[k] = v
                    old_cfg["job"] = job_cfg
                    _write_config(old_cfg, cfg_path)
                    self._json(200, {"status": "ok", "config": old_cfg})
                except Exception as e:
                    self._json(500, {"status": "error", "message": str(e)})
            else:
                self._json(400, {"status": "error", "message": "No body"})
            return

        if path == "/api/autotuner/start":
            ok, msg = start_auto_tuner()
            self._json(200, {"status": "ok" if ok else "error", "message": msg})
            return

        if path == "/api/autotuner/stop":
            stop_auto_tuner()
            self._json(200, {"status": "ok", "message": "AutoTuner stopped"})
            return

        if path == "/api/performance/clear":
            with state.lock:
                state.perf_runs.clear()
                state.best_config = None
                state.tuner_phases = []
            self._json(200, {"status": "ok", "message": "Performance data cleared"})
            return

        self._json(404, {"status": "error", "message": "Route not found"})

    # ── SSE handler ──
    def _handle_sse(self):
        import queue
        q = queue.Queue()
        with state.lock:
            state.sse_clients.append(q)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        # Enviar estado atual imediatamente
        try:
            init = f"event: telemetry\ndata: {json.dumps(_build_telemetry())}\n\n"
            self.wfile.write(init.encode("utf-8"))
            self.wfile.flush()
        except Exception:
            pass

        try:
            while True:
                try:
                    data = q.get(timeout=20)
                    self.wfile.write(data)
                    self.wfile.flush()
                except Exception:
                    # Timeout — enviar heartbeat
                    try:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
        except Exception:
            pass
        finally:
            try:
                state.sse_clients.remove(q)
            except ValueError:
                pass

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


def _write_config(cfg, path):
    """Escreve dict de config de volta ao YAML."""
    lines = []
    for section, content in cfg.items():
        if isinstance(content, dict):
            lines.append(f"{section}:")
            for k, v in content.items():
                if isinstance(v, str):
                    lines.append(f"  {k}: \"{v}\"")
                elif isinstance(v, bool):
                    lines.append(f"  {k}: {str(v).lower()}")
                else:
                    lines.append(f"  {k}: {v}")
        else:
            if isinstance(content, str):
                lines.append(f"{section}: \"{content}\"")
            elif isinstance(content, bool):
                lines.append(f"{section}: {str(content).lower()}")
            else:
                lines.append(f"{section}: {content}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


_PLUGINS = []

def load_hypothesis_plugins():
    global _PLUGINS
    cfg = load_config()
    role = cfg.get("pool", {}).get("role", "standalone")
    if role != "master":
        return
        
    try:
        solved_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzles_solved.json")
        metadata = {}
        if os.path.exists(solved_path):
            with open(solved_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                
        # Importação tardia para evitar dependências circulares
        from plugins.interval_bias import IntervalBiasPlugin
        from plugins.bit_density import BitDensityPlugin
        from plugins.entropy import EntropyPlugin
        from plugins.sufix_bias import SufixBiasPlugin
        from plugins.delta_xor import DeltaXorPlugin
        from plugins.prefix_bias import PrefixBiasPlugin
        from plugins.transition_matrix import TransitionMatrixPlugin
        from plugins.byte_frequency import ByteFrequencyPlugin
        
        _PLUGINS = [
            ("IntervalBias", IntervalBiasPlugin(metadata)),
            ("BitDensity", BitDensityPlugin(metadata)),
            ("Entropy", EntropyPlugin(metadata)),
            ("SufixBias", SufixBiasPlugin(metadata)),
            ("DeltaXor", DeltaXorPlugin(metadata)),
            ("PrefixBias", PrefixBiasPlugin(metadata)),
            ("TransitionMatrix", TransitionMatrixPlugin(metadata)),
            ("ByteFrequency", ByteFrequencyPlugin(metadata))
        ]
        print(f"[Pool] Hypothesis Engine ativo. {len(_PLUGINS)} plugins carregados com sucesso!")
    except Exception as e:
        print(f"[Pool] Erro ao carregar plugins do Hypothesis Engine: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    cfg = load_config()
    load_hypothesis_plugins()
    PORT = int(cfg.get("api", {}).get("port", 8080))

    print("=" * 60)
    print("        CycloneX Distributed Engine  v2.0")
    print("=" * 60)
    print(f"  EXE  : {CUDA_EXE or 'NOT FOUND — verifique o caminho'}")
    print(f"  Port : http://localhost:{PORT}")
    print("=" * 60 + "\n")

    if not CUDA_EXE:
        print("[AVISO] CUDACyclone.exe não encontrado!")
        print("        Coloque o .exe na mesma pasta que este script.")
        print()

    # Inicializar Pool Engine
    pool_cfg = cfg.get("pool", {})
    role = pool_cfg.get("role", "standalone")
    
    if role == "master":
        print(f"[Pool] Modo MASTER ativo.")
        init_pool_db()
        t_monitor = threading.Thread(target=_pool_timeout_monitor, daemon=True)
        t_monitor.start()
        
        # O Master também atua como worker de si mesmo para varrer os blocos da pool!
        t_worker = threading.Thread(target=_pool_worker_loop, daemon=True)
        t_worker.start()
        t_telemetry = threading.Thread(target=_pool_worker_telemetry_loop, daemon=True)
        t_telemetry.start()
        
    elif role == "worker":
        print(f"[Pool] Modo WORKER ativo.")
        t_worker = threading.Thread(target=_pool_worker_loop, daemon=True)
        t_worker.start()
        t_telemetry = threading.Thread(target=_pool_worker_telemetry_loop, daemon=True)
        t_telemetry.start()

    # Iniciar uptime counter
    t_uptime = threading.Thread(target=_uptime_loop, daemon=True)
    t_uptime.start()

    # Iniciar job automaticamente se configurado (apenas se standalone)
    auto_start = cfg.get("job", {}).get("auto_start", True)
    if role == "standalone" and auto_start and CUDA_EXE:
        print("[Agent] Auto-start ativado — iniciando job CUDA...")
        ok, msg = start_job()
        if ok:
            print(f"[Agent] {msg}")
        else:
            print(f"[Agent] {msg}")

    # Abrir browser
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    # Iniciar servidor HTTP (threaded)
    class ThreadedHTTPServer(HTTPServer):
        def process_request(self, request, client_address):
            t = threading.Thread(
                target=self._new_connection,
                args=(request, client_address),
                daemon=True
            )
            t.start()

        def _new_connection(self, request, client_address):
            try:
                self.finish_request(request, client_address)
            except Exception:
                pass

    httpd = ThreadedHTTPServer(("", PORT), CycloneHandler)
    httpd.allow_reuse_address = True

    print(f"\nCycloneX rodando em: http://localhost:{PORT}\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Agent] Encerrando...")
        stop_job()


if __name__ == "__main__":
    main()

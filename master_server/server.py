#!/usr/bin/env python3
"""
CycloneX Master Server — Pool Coordinator & Admin/Member Dashboard
Hospedado na VPS (179.197.231.166) | Domínio: valyrafi.com.br
"""

import os
import sys
import time
import json
import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "master_pool.db")
SECRET_KEY = os.environ.get("CYCLONE_SECRET", secrets.token_hex(32))

# Inicialização do Banco de Dados SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Tabela de Usuários (Admin e Cotistas/Membros)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',  -- 'admin' ou 'member'
            quota_percent REAL NOT NULL DEFAULT 1.0, -- % da cota do prêmio
            created_at TEXT NOT NULL
        )
    ''')
    
    # Tabela de Slots/Trabalhos (Janela de Ouro 57% a 75% do Puzzle #140)
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            puzzle INTEGER NOT NULL DEFAULT 140,
            slot_index INTEGER NOT NULL,
            range_start TEXT NOT NULL,
            range_end TEXT NOT NULL,
            pct_start REAL NOT NULL,
            pct_end REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'AVAILABLE', -- 'AVAILABLE', 'ASSIGNED', 'COMPLETED'
            assigned_worker TEXT,
            assigned_at TEXT,
            completed_at TEXT
        )
    ''')
    
    # Tabela de Workers Ativos
    c.execute('''
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            worker_name TEXT NOT NULL,
            gpu_name TEXT NOT NULL,
            current_job_id INTEGER,
            speed_mkeys REAL NOT NULL DEFAULT 0.0,
            last_heartbeat TEXT NOT NULL,
            total_keys_tested INTEGER DEFAULT 0
        )
    ''')
    
    # Tabela do Cofre de Soluções (Chave Privada — SÓ VISÍVEL PARA ADMIN)
    c.execute('''
        CREATE TABLE IF NOT EXISTS vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            puzzle INTEGER NOT NULL,
            found_by_worker TEXT NOT NULL,
            private_key_hex TEXT NOT NULL,
            found_at TEXT NOT NULL
        )
    ''')

    # Garantir a existência do usuário ADMIN principal (Lê de variável de ambiente ou arquivo local seguro na VPS)
    admin_user = os.environ.get("ADMIN_USER", "admin")
    admin_pass = os.environ.get("ADMIN_PASS", "admin12345")
    
    # Se existir arquivo local de configuração de admin na VPS (não enviado ao Git)
    admin_cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_credentials.json")
    if os.path.exists(admin_cfg_path):
        try:
            with open(admin_cfg_path, 'r') as f:
                cfg = json.load(f)
                admin_user = cfg.get("username", admin_user)
                admin_pass = cfg.get("password", admin_pass)
        except Exception:
            pass

    pwd_hash = hashlib.sha256((admin_pass + SECRET_KEY).encode()).hexdigest()
    c.execute("SELECT id FROM users WHERE role = 'admin'")
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (username, password_hash, role, quota_percent, created_at) VALUES (?, ?, 'admin', 100.0, ?)",
                  (admin_user, pwd_hash, datetime.utcnow().isoformat()))
    else:
        c.execute("UPDATE users SET username = ?, password_hash = ? WHERE id = ?", (admin_user, pwd_hash, row[0]))

    # Popular os 120 slots da Janela de Ouro do Puzzle #140 (57% a 75%) se a tabela estiver vazia
    c.execute("SELECT COUNT(*) FROM jobs WHERE puzzle = 140")
    if c.fetchone()[0] == 0:
        start_base = 1 << 139
        range_len = 1 << 139
        g_min = start_base + int(range_len * 0.57)
        g_max = start_base + int(range_len * 0.75)
        g_len = g_max - g_min
        total_slots = 120
        step = g_len // total_slots
        
        for i in range(total_slots):
            s = g_min + (i * step)
            e = g_min + ((i + 1) * step) if i < total_slots - 1 else g_max
            p_s = ((s - start_base) / range_len) * 100.0
            p_e = ((e - start_base) / range_len) * 100.0
            range_str = f"{s:x}:{e:x}"
            c.execute('''
                INSERT INTO jobs (puzzle, slot_index, range_start, range_end, pct_start, pct_end, status)
                VALUES (140, ?, ?, ?, ?, ?, 'AVAILABLE')
            ''', (i, f"{s:x}", f"{e:x}", p_s, p_e))

    conn.commit()
    conn.close()

init_db()

app = FastAPI(title="CycloneX Master Server", version="3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# Modelos Pydantic
class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    quota_percent: float = 1.0

class WorkerHeartbeat(BaseModel):
    worker_id: str
    worker_name: str
    gpu_name: str
    speed_mkeys: float
    total_keys: int

class SolutionSubmit(BaseModel):
    worker_id: str
    puzzle: int
    private_key_hex: str
    token_secret: str

# Auxiliares de Autenticação Básica com Token Simples
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Token formato: username:hash
    try:
        username, thash = token.split(":", 1)
        c.execute("SELECT username, role, quota_percent FROM users WHERE username = ?", (username,))
        u = c.fetchone()
        conn.close()
        if u and hmac.compare_digest(thash, hashlib.sha256((username + SECRET_KEY).encode()).hexdigest()):
            return {"username": u[0], "role": u[1], "quota_percent": u[2]}
    except Exception:
        conn.close()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado")

def get_admin_user(user: dict = Depends(verify_token)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso exclusivo para Administrador")
    return user

# ==================== ENDPOINTS DE AUTENTICAÇÃO E PAINEL ====================

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pwd_hash = hashlib.sha256((req.password + SECRET_KEY).encode()).hexdigest()
    c.execute("SELECT username, role, quota_percent FROM users WHERE username = ? AND password_hash = ?",
              (req.username, pwd_hash))
    user = c.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    
    token = f"{user[0]}:{pwd_hash}"
    return {"token": token, "username": user[0], "role": user[1], "quota_percent": user[2]}

class ChangePasswordRequest(BaseModel):
    new_password: str

@app.post("/api/auth/change-password")
def change_password(req: ChangePasswordRequest, user: dict = Depends(verify_token)):
    username = user["username"]
    new_hash = hashlib.sha256((req.new_password + SECRET_KEY).encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
    conn.commit()
    conn.close()
    new_token = f"{username}:{new_hash}"
    return {"status": "SUCCESS", "message": f"Senha do usuário {username} alterada com sucesso!", "token": new_token}

@app.get("/api/admin/users")
def list_users(admin: dict = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, username, role, quota_percent, created_at FROM users")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "username": r[1], "role": r[2], "quota_percent": r[3], "created_at": r[4]} for r in rows]

@app.post("/api/admin/users")
def create_user(u: UserCreate, admin: dict = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pwd_hash = hashlib.sha256((u.password + SECRET_KEY).encode()).hexdigest()
    try:
        c.execute("INSERT INTO users (username, password_hash, role, quota_percent, created_at) VALUES (?, ?, 'member', ?, ?)",
                  (u.username, pwd_hash, u.quota_percent, datetime.utcnow().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Usuário já existe")
    conn.close()
    return {"message": f"Membro {u.username} criado com sucesso"}

@app.delete("/api/admin/users/{username}")
def delete_user(username: str, admin: dict = Depends(get_admin_user)):
    if username == "admin":
        raise HTTPException(status_code=400, detail="Não é possível remover a conta admin principal")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {"message": f"Usuário {username} removido"}

@app.get("/api/admin/vault")
def view_vault(admin: dict = Depends(get_admin_user)):
    """COFRE DE CHAVES: Apenas o ADMIN consegue visualizar a Chave Privada encontrada!"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, puzzle, found_by_worker, private_key_hex, found_at FROM vault")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "puzzle": r[1], "found_by_worker": r[2], "private_key_hex": r[3], "found_at": r[4]} for r in rows]

# ==================== ENDPOINTS DOS WORKERS / CMD / POOL ====================

@app.post("/api/worker/get-job")
def get_job(data: dict):
    worker_id = data.get("worker_id", "unknown_worker")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Procura um slot DISPONÍVEL ou reatribui um slot inativo há mais de 30 minutos
    cutoff = (datetime.utcnow() - timedelta(minutes=30)).isoformat()
    c.execute('''
        SELECT id, puzzle, slot_index, range_start, range_end, pct_start, pct_end 
        FROM jobs 
        WHERE status = 'AVAILABLE' OR (status = 'ASSIGNED' AND assigned_at < ?)
        ORDER BY slot_index ASC LIMIT 1
    ''', (cutoff,))
    job = c.fetchone()
    
    if not job:
        conn.close()
        return {"status": "NO_JOBS", "message": "Todos os slots da Janela de Ouro estão em varredura ativa."}
    
    job_id, puzzle, slot_idx, r_start, r_end, pct_s, pct_e = job
    now_str = datetime.utcnow().isoformat()
    
    c.execute("UPDATE jobs SET status = 'ASSIGNED', assigned_worker = ?, assigned_at = ? WHERE id = ?",
              (worker_id, now_str, job_id))
    conn.commit()
    conn.close()
    
    return {
        "status": "OK",
        "job_id": job_id,
        "puzzle": puzzle,
        "slot_index": slot_idx,
        "range": f"{r_start}:{r_end}",
        "pct_range": f"{pct_s:.2f}% a {pct_e:.2f}%",
        "target_pubkey": "031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640",
        "target_addr": "1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo",
        "dp_bits": 24,
        "grid": "512,1024",
        "slices": 256
    }

@app.post("/api/worker/heartbeat")
def worker_heartbeat(hb: WorkerHeartbeat):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    
    c.execute('''
        INSERT INTO workers (worker_id, worker_name, gpu_name, speed_mkeys, last_heartbeat, total_keys_tested)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(worker_id) DO UPDATE SET
            speed_mkeys = excluded.speed_mkeys,
            last_heartbeat = excluded.last_heartbeat,
            total_keys_tested = total_keys_tested + excluded.total_keys_tested
    ''', (hb.worker_id, hb.worker_name, hb.gpu_name, hb.speed_mkeys, now_str, hb.total_keys))
    conn.commit()
    conn.close()
    return {"status": "OK"}

@app.post("/api/worker/submit-solution")
def submit_solution(sub: SolutionSubmit):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    
    # Salva a solução encontrada no Cofre Privado do Admin
    c.execute("INSERT INTO vault (puzzle, found_by_worker, private_key_hex, found_at) VALUES (?, ?, ?, ?)",
              (sub.puzzle, sub.worker_id, sub.private_key_hex, now_str))
    
    # Atualiza status do job
    c.execute("UPDATE jobs SET status = 'COMPLETED', completed_at = ? WHERE assigned_worker = ?",
              (now_str, sub.worker_id))
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": "Solução recebida e armazenada com segurança no cofre do Admin!"}

# ==================== TELEMETRIA PÚBLICA DO DASHBOARD ====================

@app.get("/api/dashboard/stats")
def dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Filtra trabalhadores ativos nos últimos 60 segundos
    cutoff = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
    c.execute("SELECT worker_id, worker_name, gpu_name, speed_mkeys, last_heartbeat, total_keys_tested FROM workers WHERE last_heartbeat >= ?", (cutoff,))
    active_workers = c.fetchall()
    
    total_speed = sum(w[3] for w in active_workers)
    
    c.execute("SELECT COUNT(*) FROM jobs WHERE puzzle = 140 AND status = 'COMPLETED'")
    completed_jobs = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM jobs WHERE puzzle = 140 AND status = 'ASSIGNED'")
    assigned_jobs = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM vault WHERE puzzle = 140")
    has_found_key = c.fetchone()[0] > 0
    
    conn.close()
    
    return {
        "puzzle": 140,
        "target_addr": "1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo",
        "active_workers_count": len(active_workers),
        "total_speed_gkeys": total_speed / 1000.0,
        "total_speed_mkeys": total_speed,
        "completed_slots": completed_jobs,
        "assigned_slots": assigned_jobs,
        "total_slots": 120,
        "solved": has_found_key,
        "workers": [{"name": w[1], "gpu": w[2], "speed_mkeys": w[3]} for w in active_workers]
    }

# Frontend Dashboard Single-Page App (SPA)
@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>CycloneX Master Server Rodando na VPS!</h1>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

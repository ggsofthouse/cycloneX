#!/bin/bash
# =================================================================
# CycloneX Master Server — Auto Setup Script para VPS Ubuntu/Debian
# IP da VPS: 179.197.231.166 | Domínio: valyrafi.com.br
# =================================================================

set -e

echo "🚀 Iniciando configuração do CycloneX Master Server na VPS..."

# 1. Atualizar e instalar dependências básicas
apt-get update -y
apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git ufw

# 2. Criar diretório seguro do servidor Master em /opt/cyclone-master
INSTALL_DIR="/opt/cyclone-master"
mkdir -p "$INSTALL_DIR"

echo "📦 Copiando arquivos do servidor Master..."
cp server.py "$INSTALL_DIR/"
cp dashboard.html "$INSTALL_DIR/"

# 3. Criar Ambiente Virtual Python (venv) e instalar dependências
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install fastapi uvicorn pydantic

# 4. Criar Serviço Systemd para rodar 24/7 em segundo plano
cat << 'EOF' > /etc/systemd/system/cyclone-master.service
[Unit]
Description=CycloneX Master Coordinator Server
After=network.target

[Service]
User=root
WorkingDirectory=/opt/cyclone-master
ExecStart=/opt/cyclone-master/venv/bin/python /opt/cyclone-master/server.py
Restart=always
RestartSec=5

[Section]
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cyclone-master
systemctl restart cyclone-master

echo "✅ Serviço cyclone-master ativo e rodando na porta 8000!"

# 5. Configurar o Nginx como Proxy Reverso sem interferir em outros sites
NGINX_CONF="/etc/nginx/sites-available/valyrafi"

cat << 'EOF' > "$NGINX_CONF"
server {
    listen 80;
    server_name valyrafi.com.br www.valyrafi.com.br;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/valyrafi
nginx -t
systemctl reload nginx

echo "================================================================"
echo " 🎉 INSTALAÇÃO NA VPS CONCLUÍDA COM SUCESSO!"
echo "================================================================"
echo " Master Server Ativo em: http://179.197.231.166:8000"
echo " Domínio Configurado: http://valyrafi.com.br"
echo "----------------------------------------------------------------"

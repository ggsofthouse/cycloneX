# 🌐 CycloneX — Guia de Rede: Master & Workers

> Conecte múltiplas máquinas com GPU para trabalhar em conjunto na mesma busca, dividindo o espaço de chaves automaticamente.

---

## 📐 Arquitetura da Rede

```
┌──────────────────────────────────────────────────────┐
│                  MASTER (você)                       │
│   IP Local: ex. 192.168.1.100  |  Porta: 8080        │
│                                                      │
│  ┌─────────────────────────────────────────────┐    │
│  │  Pool Engine  ←→  SQLite DB (cyclone.db)    │    │
│  │  Distribui blocos de chaves para Workers    │    │
│  └─────────────────────────────────────────────┘    │
│                  ↑ HTTP REST API                     │
└──────────────────┬───────────────────────────────────┘
                   │
       ┌───────────┼───────────────┐
       ↓           ↓               ↓
  [Worker 1]  [Worker 2]      [Worker N]
  PC-Sala     PC-Escritório   Servidor
  RTX 3080    RTX 4090        RTX 2080 Ti
```

- O **Master** divide o range de chaves em blocos e distribui via API REST
- Os **Workers** pedem blocos ao Master, processam com sua GPU e reportam o resultado
- O Master **também trabalha** como worker de si mesmo (usa sua própria GPU)
- Se um worker travar ou desconectar, o bloco é **automaticamente redistribuído** após 15 minutos

---

## 🖥️ PASSO 1 — Configurar o Master (você)

No PC que vai ser o Master (o seu), edite o arquivo `config.yaml`:

```yaml
job:
  range: "400000000000000000:7fffffffffffffffff"
  address: "1PWo3JeB9jrGwfHDNpdGK54CRas7fsVzXU"
  grid: "512,1024"
  slices: 512
  random: false
  gpus: "0"

gpu:
  max_temp_c: 85

telemetry:
  interval: 1

api:
  port: 8080
  token: "SEU_TOKEN_SECRETO_AQUI"   # ← Crie um token forte (ex: "CycloneX-2025-abc123")

database:
  path: "./cyclone.db"

pool:
  role: "master"                    # ← MASTER
  master_url: "http://localhost:8080"
  block_size_gkeys: 200             # Tamanho de cada bloco em GigaKeys
  random_in_block: false
```

> **⚠️ Importante:** Altere o `token` para algo único. Todos os Workers precisarão usar o mesmo token.

### Iniciar o Master

```bat
run.bat
```

Ou diretamente:

```bash
python cyclone_agent.py
```

O dashboard abrirá em: **http://localhost:8080**

---

## 💻 PASSO 2 — Configurar cada Worker

Em cada PC worker, copie a pasta do CycloneX e edite o `config.yaml`:

```yaml
job:
  grid: "512,1024"        # Ajuste para a GPU de cada worker
  slices: 512
  gpus: "0"

gpu:
  max_temp_c: 85

api:
  port: 8080
  token: "SEU_TOKEN_SECRETO_AQUI"   # ← Mesmo token do Master!

database:
  path: "./cyclone.db"

pool:
  role: "worker"                              # ← WORKER
  master_url: "http://192.168.1.100:8080"     # ← IP do Master na rede local
  block_size_gkeys: 200
  random_in_block: false
```

> **⚠️ Substitua `192.168.1.100`** pelo IP real do PC Master na sua rede.

### Iniciar o Worker

```bat
run.bat
```

O worker se conectará automaticamente ao Master e começará a pedir blocos.

---

## 🔍 Como descobrir o IP do Master

No PC **Master**, abra o Prompt de Comando e rode:

```cmd
ipconfig
```

Procure pelo **Endereço IPv4** da sua placa de rede local. Exemplo:

```
Adaptador de Rede Ethernet:
   Endereço IPv4. . . . . . . . . . . . .: 192.168.1.100
```

Esse é o IP que os Workers devem usar em `master_url`.

---

## 🌍 Conexão pela Internet (WAN)

Se os Workers estiverem em redes diferentes (Internet), você precisa de uma das opções abaixo:

### Opção A — Port Forward no Roteador (mais simples)

1. Acesse o painel do seu roteador (geralmente `192.168.1.1`)
2. Vá em **NAT / Port Forwarding**
3. Redirecione a porta **8080 TCP** para o IP local do Master (`192.168.1.100`)
4. Descubra seu IP público em [https://whatismyip.com](https://whatismyip.com)
5. Configure os Workers com:

```yaml
pool:
  master_url: "http://SEU_IP_PUBLICO:8080"
```

### Opção B — Ngrok (sem port forward)

```bash
# Instale o ngrok: https://ngrok.com
ngrok http 8080
```

O ngrok fornecerá uma URL pública como `https://abc123.ngrok.io`.
Configure os Workers com essa URL.

### Opção C — VPN (mais seguro)

Use Tailscale, ZeroTier ou WireGuard para criar uma rede privada virtual entre os PCs.
Todos ficam no mesmo endereçamento e conectam-se como se fossem rede local.

---

## 🔒 Segurança

| Item | Recomendação |
|------|-------------|
| **Token** | Use um token forte e único (min. 16 chars) |
| **Firewall** | Libere apenas a porta 8080 para IPs confiáveis |
| **Internet** | Prefira VPN ao invés de expor diretamente |
| **HTTPS** | Para produção, use um proxy reverso (nginx) com SSL |

---

## 📊 Monitorar a Rede no Dashboard

No **Master**, acesse `http://localhost:8080` e navegue até a aba **Pool / Workers**.

Você verá em tempo real:

| Informação | Descrição |
|-----------|-----------|
| **Worker ID** | Nome do PC (hostname) |
| **Status** | Online / Idle / Processando |
| **Bloco Atual** | ID do bloco sendo processado |
| **Speed** | MKeys/s em tempo real |
| **Temp** | Temperatura da GPU |
| **Power** | Consumo em Watts |
| **Hipótese** | Estratégia ativa (IntervalBias, BitDensity, Entropy) |

---

## ⚙️ Parâmetros Avançados do Pool

| Parâmetro | Onde | Descrição |
|-----------|------|-----------|
| `block_size_gkeys` | Master | Tamanho de cada bloco em GigaKeys (padrão: 200) |
| `random_in_block` | Master/Worker | Busca aleatória dentro do bloco |
| `role` | Todos | `master`, `worker` ou `standalone` |
| `master_url` | Workers | URL completa do Master com porta |
| `token` | Todos | Chave de autenticação compartilhada |

**Timeout automático:** Se um Worker não reportar progresso por **15 minutos**, seu bloco é automaticamente devolvido ao pool para redistribuição.

---

## 🐛 Resolução de Problemas

### Worker não conecta ao Master

```
[Worker] Erro ao conectar ao Master para pedir bloco: <URLError>
```

- Verifique se o Master está rodando e acessível na porta 8080
- Confirme o IP em `master_url` no `config.yaml` do Worker
- Verifique se o Firewall do Master permite a porta 8080:
  ```cmd
  netsh advfirewall firewall add rule name="CycloneX" protocol=TCP dir=in localport=8080 action=allow
  ```

### Token inválido / 401 Unauthorized

- Confirme que o `token` no `config.yaml` do Worker é **idêntico** ao do Master
- Não use espaços no início/fim do token

### Worker recebe "Sem blocos disponíveis"

```
[Worker] Sem blocos disponíveis no Master. Aguardando 15s...
```

- Normal: significa que todos os blocos do range já foram distribuídos
- O Master está processando o range completo e ainda não criou novos blocos
- Aguarde ou reduza o `block_size_gkeys` para blocos menores

### CUDACyclone.exe não encontrado no Worker

- Copie o `CUDACyclone.exe` para a mesma pasta do `cyclone_agent.py` no Worker
- Verifique com: `dir CUDACyclone.exe` na pasta do projeto

---

## 📋 Checklist Rápido

### No Master (você):
- [ ] `config.yaml` com `role: "master"`
- [ ] Token definido em `api.token`
- [ ] Porta 8080 liberada no Firewall
- [ ] `python cyclone_agent.py` rodando
- [ ] Dashboard acessível em `http://localhost:8080`

### Em cada Worker:
- [ ] `config.yaml` com `role: "worker"`
- [ ] `master_url` apontando para o IP do Master
- [ ] Mesmo `token` do Master
- [ ] `CUDACyclone.exe` presente na pasta
- [ ] `python cyclone_agent.py` rodando
- [ ] Logs mostrando `[Worker] Bloco #X atribuído`

---

*CycloneX v2.0 — Distributed GPU Compute Platform*

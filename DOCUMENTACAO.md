# 📚 Documentação Completa — API-IA

> API em **Python + FastAPI** que automatiza o **ChatGPT** (chatgpt.com) via **Selenium**
> (`undetected-chromedriver`) e devolve as respostas da IA como JSON.
>
> Este documento cobre **tudo**: como o sistema funciona por dentro, os requisitos,
> a instalação passo a passo num VPS Linux do zero, o uso da API, e um guia completo
> de correção de erros (com os problemas reais que já enfrentamos e como foram resolvidos).

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Como funciona por dentro (arquitetura)](#2-como-funciona-por-dentro-arquitetura)
3. [Estrutura de arquivos](#3-estrutura-de-arquivos)
4. [Requisitos](#4-requisitos)
5. [Instalação num VPS do zero (passo a passo)](#5-instalação-num-vps-do-zero-passo-a-passo)
6. [Rodar como serviço permanente (systemd)](#6-rodar-como-serviço-permanente-systemd)
7. [Rede, firewall e acesso externo](#7-rede-firewall-e-acesso-externo)
8. [Segurança (API Key + HTTPS via Nginx)](#8-segurança-api-key--https-via-nginx)
9. [Referência da API](#9-referência-da-api)
10. [Referência do `.env` (todas as variáveis)](#10-referência-do-env-todas-as-variáveis)
11. [Modos de operação: headless vs Xvfb](#11-modos-de-operação-headless-vs-xvfb)
12. [Correção de erros (troubleshooting completo)](#12-correção-de-erros-troubleshooting-completo)
13. [Operação e manutenção](#13-operação-e-manutenção)
14. [Ambiente de teste local (WSL) — como reproduzir](#14-ambiente-de-teste-local-wsl--como-reproduzir)

---

## 1. Visão geral

O ChatGPT **não é acessado via API oficial** aqui. Em vez disso, um navegador **Chrome**
real é controlado por **Selenium** para abrir o site `chatgpt.com` (modo público, sem
login), digitar o prompt, esperar a resposta ser gerada e extrair o texto. Esse texto é
devolvido por uma **API HTTP (FastAPI)**.

**Fluxo resumido:**

```
Cliente HTTP  ──POST /chat──▶  FastAPI (uvicorn)  ──▶  ChatGPTClient (lock)
                                                          │
                                                          ▼
                                          Selenium + undetected-chromedriver
                                                          │
                                                          ▼
                                             Chrome (real, dentro do Xvfb)
                                                          │
                                                          ▼
                                                   chatgpt.com
```

**Vantagens:** não precisa de chave da OpenAI, usa o ChatGPT web "de graça".
**Limitações:** é frágil (o site muda), tem **anti-bot (Cloudflare)**, e processa
**uma requisição por vez** (um único navegador serializado por lock).

---

## 2. Como funciona por dentro (arquitetura)

### 2.1 Componentes

| Componente | Papel |
|-----------|-------|
| **FastAPI** (`app/main.py`) | Expõe os endpoints HTTP `POST /chat` e `GET /health`. Sobe o navegador no *startup* e o fecha no *shutdown* (via `lifespan`). |
| **Uvicorn** | Servidor ASGI que roda o FastAPI. |
| **ChatGPTClient** (`app/chatgpt.py`) | Envolve **um único** driver Selenium. Serializa o acesso com um `threading.Lock` (thread-safe) e implementa a lógica de digitar/esperar/extrair. |
| **build_driver** (`app/browser.py`) | Cria o Chrome com flags de servidor (`--no-sandbox`, `--disable-dev-shm-usage`, etc.) via `undetected-chromedriver` (stealth). |
| **Settings** (`app/config.py`) | Lê toda a configuração do `.env` (Pydantic Settings). Inclusive os **seletores CSS** — para ajustar quando o ChatGPT mudar de layout, sem tocar no código. |
| **Xvfb** | "Tela virtual" (X server sem monitor). Necessário quando `HEADLESS=false`, para o Chrome ter onde desenhar. |

### 2.2 Ciclo de vida de uma requisição `/chat`

1. Chega `POST /chat` com `{prompt, context}`.
2. Se `API_KEY` está configurada, o header `X-API-Key` é validado.
3. Se o browser não estiver pronto → `503`.
4. O `ChatGPTClient.ask()` **adquire o lock** (garante uma requisição por vez).
5. `_build_prompt()` monta o texto final: se há `context`, ele é prefixado como
   `### Contexto da conversa` + as mensagens + `### Pergunta atual` + o prompt.
6. Fecha modais de login/onboarding que aparecem no modo deslogado (`_dismiss_modals`).
7. Digita o prompt no editor (`#prompt-textarea`), usando **Shift+Enter** para quebras
   de linha (para não enviar antes da hora), e clica no botão de enviar.
8. Espera surgir uma **nova** mensagem do assistente (compara a contagem antes/depois).
9. `_wait_generation_finished()` espera a geração terminar: enquanto o botão "parar"
   existir, ainda está gerando; depois confirma por **estabilidade do texto** (~1,5s sem mudar).
10. Extrai o texto da última resposta e devolve `{response, elapsed_seconds}`.

### 2.3 Por que "um por vez"?

Há **um único navegador** compartilhado, protegido por lock. Requisições simultâneas
**esperam a vez**. Para paralelismo real seria preciso um *pool* de navegadores (não incluído).

---

## 3. Estrutura de arquivos

```
API-IA/
├── app/
│   ├── __init__.py
│   ├── main.py       # FastAPI: endpoints /chat e /health, lifespan do browser
│   ├── config.py     # Settings (Pydantic) lidas do .env, incluindo seletores CSS
│   ├── models.py     # Schemas de request/response (Message, ChatRequest, ...)
│   ├── browser.py    # build_driver(): cria o Chrome stealth
│   └── chatgpt.py    # ChatGPTClient: automação + lock thread-safe
├── deploy/
│   └── api-ia.service  # unit do systemd (roda como serviço)
├── requirements.txt    # dependências Python (versões fixadas)
├── run.sh              # script de inicialização (gerencia Xvfb + uvicorn)
├── .env.example        # modelo de configuração — copie para .env
├── README.md           # guia rápido
└── DOCUMENTACAO.md     # este documento
```

---

## 4. Requisitos

### 4.1 Hardware / VPS

| Recurso | Mínimo | Recomendado |
|--------|--------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 2 GB | 4 GB (o Chrome é pesado) |
| Disco | 5 GB | 10 GB |
| Rede | IPv4 público | IPv4 público |

> ⚠️ **Menos de 2 GB de RAM** faz o Chrome ser morto pelo OOM killer. Se só tiver 1 GB,
> crie **swap** (ver [seção 12](#12-correção-de-erros-troubleshooting-completo)).

### 4.2 Sistema operacional

- **Recomendado: Ubuntu Server 22.04 LTS.** Motivo: já vem com **Python 3.10** nativo,
  que é a versão em que este projeto foi testado e para a qual as dependências foram fixadas.
- Debian 11/12 também funcionam.
- ❗ **Evite distros muito novas** (ex.: Ubuntu 24.04+ com Python 3.12/3.14). As
  dependências fixadas (`undetected-chromedriver`, `pydantic-core`) **não são compatíveis
  com Python 3.12+** (o módulo `distutils` foi removido e falta wheel do `pydantic-core`).
  Nesse caso você terá que **instalar o Python 3.10 manualmente** (ver [seção 5.4](#54-python-versão-crítica)).

### 4.3 Software (instalado durante o passo a passo)

- **Python 3.10** (ou 3.11) + `venv` + `pip`
- **Google Chrome** (estável) — o `undetected-chromedriver` baixa o chromedriver compatível sozinho
- **Xvfb** (tela virtual, para o modo anti-bot)
- Utilitários: `wget`, `curl`

### 4.4 Versões Python das dependências (`requirements.txt`)

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
selenium==4.27.1
undetected-chromedriver==3.5.5
python-dotenv==1.0.1
```

> Testado e validado com **Python 3.10.15** + **Google Chrome 150** + **chromedriver 150**.

---

## 5. Instalação num VPS do zero (passo a passo)

Este guia assume um **VPS Ubuntu Server 22.04 LTS** recém-criado (ex.: DigitalOcean,
Hetzner, Contabo, AWS EC2, Oracle Cloud, etc.), acessado por SSH como usuário com `sudo`.

### 5.1 Conectar por SSH

```bash
ssh usuario@SEU_IP_DO_VPS
```

### 5.2 Atualizar o sistema

```bash
sudo apt update && sudo apt upgrade -y
```

### 5.3 Dependências de sistema + Google Chrome

```bash
# Ferramentas + Python + Xvfb
sudo apt install -y python3 python3-venv python3-pip python3-dev \
  wget curl xvfb ca-certificates fonts-liberation

# Google Chrome (estável)
cd /tmp
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# Conferir
google-chrome --version    # ex.: Google Chrome 150.x
```

### 5.4 Python (versão CRÍTICA)

Confirme a versão do Python:

```bash
python3 --version
```

- Se for **3.10 ou 3.11** → ✅ pode seguir para o passo 5.5.
- Se for **3.12 ou mais novo** → ⚠️ **as dependências vão quebrar**. Instale o Python 3.10
  a partir do código-fonte oficial (foi exatamente o que fizemos no ambiente de teste):

<details>
<summary><b>Compilar Python 3.10 do python.org (só se necessário)</b></summary>

```bash
# dependências de compilação
sudo apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev libffi-dev liblzma-dev tk-dev libncursesw5-dev xz-utils

# baixar e compilar
cd /usr/src
sudo wget https://www.python.org/ftp/python/3.10.15/Python-3.10.15.tgz
sudo tar xzf Python-3.10.15.tgz
cd Python-3.10.15
sudo ./configure --enable-shared --prefix=/usr/local LDFLAGS=-Wl,-rpath=/usr/local/lib
sudo make -j"$(nproc)"
sudo make altinstall     # instala como /usr/local/bin/python3.10 (não substitui o do sistema)

/usr/local/bin/python3.10 --version   # Python 3.10.15
```

Nos passos seguintes, use `/usr/local/bin/python3.10` no lugar de `python3`.
</details>

### 5.5 Colocar o código no VPS

Escolha **um** dos métodos:

**Opção A — via `scp` (do seu PC para o VPS):**
```bash
# no SEU computador (não no VPS):
scp -r "C:/Users/Fabiano/Music/API-IA" usuario@SEU_IP:/tmp/API-IA
# depois, no VPS:
sudo mkdir -p /opt/api-ia
sudo cp -r /tmp/API-IA/* /opt/api-ia/
```

**Opção B — via Git (se o projeto estiver num repositório):**
```bash
sudo mkdir -p /opt/api-ia
sudo git clone SEU_REPOSITORIO /opt/api-ia
```

Ajuste a posse do diretório:
```bash
sudo chown -R $USER:$USER /opt/api-ia
cd /opt/api-ia
```

> ⚠️ **Quebras de linha:** se você editou arquivos no Windows, `run.sh` pode ter vindo
> com CRLF e quebrar no Linux (`bad interpreter`). Corrija com:
> ```bash
> sudo apt install -y dos2unix
> dos2unix run.sh
> ```

### 5.6 Ambiente virtual + dependências

```bash
cd /opt/api-ia
python3 -m venv .venv           # ou /usr/local/bin/python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.7 Configuração (`.env`)

```bash
cp .env.example .env
nano .env
```

Ajustes recomendados para produção (ver [seção 10](#10-referência-do-env-todas-as-variáveis)):

```ini
API_KEY=uma-chave-secreta-forte     # protege a API
HEADLESS=false                      # usa Xvfb (menos detectável pelo anti-bot)
CHROME_BINARY=/usr/bin/google-chrome
```

### 5.8 Teste manual

```bash
chmod +x run.sh
./run.sh
```

Você deve ver nos logs:
```
Rodando com Xvfb (DISPLAY=:99)...
INFO:     Started server process [...]
... Browser pronto em https://chatgpt.com/
INFO:     Application startup complete.
```

Em **outra aba/terminal**, teste:
```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","browser_ready":true}

curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: uma-chave-secreta-forte" \
  -d '{"prompt":"Diga apenas: teste ok","context":[]}'
# {"response":"teste ok","elapsed_seconds":8.6}
```

Se funcionou, pare com `Ctrl+C` e configure o serviço (próxima seção).

---

## 6. Rodar como serviço permanente (systemd)

Para a API subir sozinha no boot e reiniciar se cair:

```bash
# 1. Criar um usuário de sistema dedicado (sem shell)
sudo useradd -r -s /usr/sbin/nologin apiia || true

# 2. Dar a posse dos arquivos a ele
sudo chown -R apiia:apiia /opt/api-ia

# 3. Instalar a unit
sudo cp deploy/api-ia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now api-ia

# 4. Conferir
sudo systemctl status api-ia
journalctl -u api-ia -f        # logs ao vivo (Ctrl+C para sair)
```

O arquivo `deploy/api-ia.service` já vem pronto:

```ini
[Unit]
Description=API-IA (ChatGPT via Selenium)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=apiia
WorkingDirectory=/opt/api-ia
EnvironmentFile=/opt/api-ia/.env
ExecStart=/opt/api-ia/run.sh
Restart=always
RestartSec=5
PrivateTmp=true          # /tmp isolado (bom para os locks do Xvfb/Chrome)

[Install]
WantedBy=multi-user.target
```

**Comandos úteis:**
```bash
sudo systemctl restart api-ia     # reiniciar
sudo systemctl stop api-ia        # parar
sudo systemctl disable api-ia     # não subir no boot
journalctl -u api-ia --since "10 min ago"   # logs recentes
```

---

## 7. Rede, firewall e acesso externo

Por padrão a API escuta em `0.0.0.0:8000` (todas as interfaces).

**Liberar a porta no firewall (UFW):**
```bash
sudo ufw allow 8000/tcp
sudo ufw status
```

**No painel do provedor de VPS** (DigitalOcean/AWS Security Group/etc.), libere também
a porta **8000/TCP** de entrada, se houver firewall de nuvem.

Teste de fora:
```bash
curl http://SEU_IP:8000/health
```

> 🔒 **Recomendação:** não exponha a `8000` diretamente à internet sem `API_KEY`.
> Melhor ainda: coloque um **Nginx com HTTPS** na frente (seção 8) e mantenha a `8000`
> acessível só internamente.

---

## 8. Segurança (API Key + HTTPS via Nginx)

### 8.1 API Key

Defina `API_KEY` no `.env`. Toda chamada a `/chat` passa a exigir o header:
```
X-API-Key: <sua-chave>
```
Sem o header correto → `401 Unauthorized`.

### 8.2 Proxy reverso com HTTPS (opcional, recomendado)

```bash
sudo apt install -y nginx
```

Crie `/etc/nginx/sites-available/api-ia`:
```nginx
server {
    listen 80;
    server_name seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;   # /chat pode demorar
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/api-ia /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# HTTPS grátis com Let's Encrypt:
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d seu-dominio.com
```

Com o Nginx na frente, mude a API para escutar só localmente: `HOST=127.0.0.1` no `.env`.

---

## 9. Referência da API

Documentação interativa automática (Swagger) em: **`http://SEU_IP:8000/docs`**

### `GET /health`

Verifica se a API está de pé e se o navegador está pronto.

**Resposta:**
```json
{ "status": "ok", "browser_ready": true }
```
- `browser_ready=false` significa que o Chrome não subiu — veja o [troubleshooting](#12-correção-de-erros-troubleshooting-completo).

### `POST /chat`

Envia um prompt (e contexto opcional) ao ChatGPT e retorna a resposta.

**Headers:**
- `Content-Type: application/json`
- `X-API-Key: <sua-chave>` — **somente se** `API_KEY` estiver definida no `.env`.

**Corpo (request):**
```json
{
  "prompt": "Resuma o texto acima em 3 tópicos.",
  "context": [
    { "role": "user",      "content": "Olá, preciso analisar um contrato." },
    { "role": "assistant", "content": "Claro, envie o contrato." }
  ]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `prompt` | string | ✅ | A pergunta/instrução atual. Não pode ser vazio. |
| `context` | lista de mensagens | ❌ (default `[]`) | Histórico. Cada item: `{role, content}`. |
| `context[].role` | `"system"` \| `"user"` \| `"assistant"` | ✅ | Papel da mensagem. |
| `context[].content` | string | ✅ | Texto da mensagem. |

**Resposta (200):**
```json
{ "response": "1. ...\n2. ...\n3. ...", "elapsed_seconds": 12.4 }
```

**Códigos de erro:**
| Código | Significado |
|--------|-------------|
| `400` | `prompt` vazio. |
| `401` | `X-API-Key` ausente/inválida (quando `API_KEY` está setada). |
| `502` | A IA não começou a responder — provável **bloqueio anti-bot** ou **seletor CSS errado**. |
| `503` | Browser não está pronto (falhou no startup). |
| `500` | Erro interno inesperado. |

**Exemplos de uso:**

```bash
# curl
curl -X POST http://SEU_IP:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: minha-chave" \
  -d '{"prompt":"Diga olá em 3 idiomas."}'
```

```python
# Python (requests)
import requests
r = requests.post("http://SEU_IP:8000/chat",
    headers={"X-API-Key": "minha-chave"},
    json={"prompt": "Explique o que é uma API em uma frase.", "context": []},
    timeout=200)
print(r.json()["response"])
```

```javascript
// JavaScript (fetch)
const r = await fetch("http://SEU_IP:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-API-Key": "minha-chave" },
  body: JSON.stringify({ prompt: "Resuma a fotossíntese.", context: [] })
});
console.log((await r.json()).response);
```

---

## 10. Referência do `.env` (todas as variáveis)

```ini
# --- API ---
API_KEY=                 # se preenchido, exige header X-API-Key nas chamadas /chat
HOST=0.0.0.0             # interface de escuta (use 127.0.0.1 se tiver Nginx na frente)
PORT=8000                # porta

# --- Site alvo ---
TARGET_URL=https://chatgpt.com/

# --- Browser ---
HEADLESS=true            # true = headless puro; false = Chrome real dentro do Xvfb (anti-bot)
CHROME_BINARY=           # caminho do Chrome; em produção: /usr/bin/google-chrome
USER_DATA_DIR=           # perfil persistente (mantém cookies entre reinícios). Ex.: /opt/api-ia/chrome-profile
WINDOW_SIZE=1280,900     # tamanho da janela (vira 1280x900x24 no Xvfb)
USER_AGENT=              # user-agent custom (vazio = padrão do Chrome)

# --- Timeouts (segundos) ---
PAGE_LOAD_TIMEOUT=60         # carregamento da página
RESPONSE_TIMEOUT=180         # tempo máx. esperando a resposta terminar
GENERATION_START_TIMEOUT=30  # tempo máx. para a resposta começar a aparecer

# --- Seletores CSS (ajuste se o ChatGPT mudar de layout) ---
INPUT_SELECTOR=#prompt-textarea
SEND_BUTTON_SELECTOR=button[data-testid='send-button']
STOP_BUTTON_SELECTOR=button[data-testid='stop-button']
ASSISTANT_MESSAGE_SELECTOR=div[data-message-author-role='assistant']
DISMISS_SELECTORS=button[data-testid='close-button'],a[href*='auth']
```

> 💡 **Perfil persistente (`USER_DATA_DIR`):** recomendado no servidor. Mantém cookies e
> "confiança" do Cloudflare entre reinícios, reduzindo bloqueios. Ex.:
> `USER_DATA_DIR=/opt/api-ia/chrome-profile` (garanta que o usuário `apiia` tenha escrita nela).

---

## 11. Modos de operação: headless vs Xvfb

| Modo | `.env` | Como roda | Quando usar |
|------|--------|-----------|-------------|
| **Headless puro** | `HEADLESS=true` | `uvicorn` direto, Chrome com `--headless` | Mais leve. Mas **mais detectável** pelo Cloudflare. |
| **Xvfb (tela virtual)** | `HEADLESS=false` | `run.sh` sobe um **Xvfb em `:99`** e roda o Chrome "normal" nele | **Recomendado em produção** — bem menos detectável pelo anti-bot. |

**Como o `run.sh` trata o modo Xvfb** (importante — foi corrigido, veja [seção 12](#12-correção-de-erros-troubleshooting-completo)):
- Inicia um **Xvfb persistente no display fixo `:99`** (`Xvfb :99 -screen 0 1280x900x24 -nolisten tcp`)
- Exporta `DISPLAY=:99`
- Roda `uvicorn` normalmente

Ele **não usa mais `xvfb-run`**, porque com o uvicorn isso causava o Chrome a morrer no
startup (detalhes abaixo).

---

## 12. Correção de erros (troubleshooting completo)

### 🔴 `browser_ready:false` + logs com `chrome not reachable` / `Missing X server or $DISPLAY`

**Sintoma:** a API sobe, mas `/health` mostra `browser_ready:false`; nos logs aparece
`SessionNotCreatedException: cannot connect to chrome ... chrome not reachable` após ~60s,
e antes disso `Missing X server or $DISPLAY` / `The platform failed to initialize. Exiting.`

**Causa (bug real que corrigimos):** com `HEADLESS=false`, o `run.sh` antigo usava
`xvfb-run`. Quando o **uvicorn** lança o Chrome como subprocesso, o Chrome **não alcança**
o servidor X efêmero criado pelo `xvfb-run` → o processo do Chrome morre imediatamente
(vira zumbi `[chrome] <defunct>`) → o chromedriver fica sem conseguir falar com ele.

**Solução (já aplicada no `run.sh`):** usar um **Xvfb persistente num display fixo `:99`**
(sem autenticação, `-nolisten tcp`) e exportar `DISPLAY=:99`, rodando o `uvicorn` direto —
**sem** `xvfb-run`. Se você editou o `run.sh` e o problema voltar, confirme que ele está no
formato novo (seção 11).

**Diagnóstico útil:**
```bash
pgrep -ax Xvfb                    # o Xvfb :99 está rodando?
journalctl -u api-ia -n 50        # ver o erro exato
```

### 🔴 `pip install` falha em `pydantic-core` / erro de `distutils` / PyO3

**Sintoma:** `error: the configured Python interpreter version (3.14) is newer than PyO3's
maximum supported version` ou `ModuleNotFoundError: No module named 'distutils'`.

**Causa:** Python **3.12+** no sistema. As dependências fixadas são para **Python 3.10**.

**Solução:** instale o Python 3.10 (seção [5.4](#54-python-versão-crítica)) e recrie o venv com ele:
```bash
rm -rf .venv
/usr/local/bin/python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 🔴 `502` no `/chat` — "A resposta não começou a ser gerada"

**Causa A — bloqueio anti-bot (Cloudflare/CAPTCHA):**
- Mude para o modo Xvfb: `HEADLESS=false` no `.env` e reinicie.
- Configure um **perfil persistente** (`USER_DATA_DIR`) para acumular confiança.
- Reduza a frequência de chamadas.

**Causa B — seletor CSS desatualizado (o ChatGPT mudou o layout):**
- Abra o site num navegador normal, inspecione os elementos e atualize os `*_SELECTOR`
  no `.env` (`INPUT_SELECTOR`, `SEND_BUTTON_SELECTOR`, `ASSISTANT_MESSAGE_SELECTOR`, etc.).
- Reinicie a API.

### 🔴 Chrome é morto por falta de memória (OOM)

**Sintoma:** o serviço reinicia sozinho; `dmesg` mostra `Out of memory: Killed process ... chrome`.

**Solução:** garanta ≥2 GB de RAM ou crie **swap**:
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
As flags `--no-sandbox` e `--disable-dev-shm-usage` já estão ativas no `browser.py` para
ajudar nisso.

### 🔴 `run.sh: bad interpreter` / `\r: command not found`

**Causa:** arquivo salvo com quebras de linha do Windows (CRLF).
**Solução:** `dos2unix run.sh` (ou `sed -i 's/\r$//' run.sh`).

### 🔴 `chromedriver` incompatível com a versão do Chrome

**Sintoma:** `This version of ChromeDriver only supports Chrome version X`.
**Causa:** o `undetected-chromedriver` normalmente baixa o driver certo sozinho. Se travar,
o cache pode estar velho.
**Solução:** limpe o cache e reinicie:
```bash
rm -rf ~/.local/share/undetected_chromedriver
sudo systemctl restart api-ia
```

### 🔴 A porta 8000 não responde de fora

- Firewall do SO: `sudo ufw allow 8000/tcp`
- Firewall de nuvem (painel do provedor): liberar 8000/TCP de entrada.
- Confirme `HOST=0.0.0.0` no `.env` (não `127.0.0.1`, a não ser que use Nginx).

### 🔎 Comandos de diagnóstico rápido

```bash
sudo systemctl status api-ia            # o serviço está ativo?
journalctl -u api-ia -f                 # logs ao vivo
curl http://127.0.0.1:8000/health       # browser_ready?
pgrep -ax Xvfb; pgrep -af chrome        # processos do X e do Chrome
free -h                                 # memória/swap
google-chrome --version                 # versão do Chrome
source .venv/bin/activate && python --version   # versão do Python do venv
```

---

## 13. Operação e manutenção

- **Concorrência:** um navegador só, requisições serializadas por lock. Chamadas
  simultâneas esperam a vez. Dimensione os timeouts do cliente de acordo (o `/chat` pode
  levar de segundos a alguns minutos).
- **Contexto vs. memória do site:** cada chamada monta o prompt completo (`context` +
  `prompt`) e envia na conversa atual da aba. O ChatGPT também mantém seu próprio histórico
  na aba aberta; para conversas 100% isoladas, reinicie o browser entre chamadas.
- **Atualização do Chrome:** o Chrome se auto-atualiza no Ubuntu (via repositório da
  Google). O `undetected-chromedriver` acompanha a versão automaticamente. Se algo quebrar
  após uma atualização, limpe o cache do driver (seção 12).
- **Quando as respostas pararem:** 95% das vezes é (a) **anti-bot** → use Xvfb + perfil
  persistente, ou (b) **seletor CSS desatualizado** → ajuste os `*_SELECTOR` no `.env`.
- **Logs:** `journalctl -u api-ia` (systemd) ou o stdout do `./run.sh` em teste manual.

---

## 14. Ambiente de teste local (WSL) — como reproduzir

Este projeto foi validado localmente no **Windows via WSL 2 (Ubuntu)**, que simula bem o
Ubuntu Server de produção. Resumo do que foi necessário (útil se você quiser testar antes
de subir ao VPS):

1. **Habilitar o WSL 2** (requer virtualização VT-x/AMD-V ligada na BIOS):
   ```powershell
   wsl --install -d Ubuntu        # como Administrador
   ```
   Confirme com `wsl --status` e `wsl -l -v`.
2. **Dentro do Ubuntu (WSL)**, seguir os mesmos passos da [seção 5](#5-instalação-num-vps-do-zero-passo-a-passo):
   dependências de sistema, Google Chrome, Python 3.10, venv, `pip install`, `.env`.
3. **Atenção:** o Ubuntu do WSL pode ser uma versão muito nova (ex.: 26.04 com Python 3.14).
   Nesse caso, **compile o Python 3.10** (seção 5.4) — foi o que fizemos.
4. Subir com `./run.sh` (modo Xvfb) e testar com `curl` no `/chat`, exatamente como no VPS.

> Diferença principal para produção: no VPS use **Ubuntu 22.04 LTS**, que já vem com
> Python 3.10 e dispensa a compilação manual.

---

*Documentação gerada e validada com testes end-to-end reais (respostas do ChatGPT via `/chat`).*

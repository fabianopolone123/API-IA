# API-IA

API em **Python + FastAPI** que automatiza o **ChatGPT** (chatgpt.com) usando **Selenium**
(via `undetected-chromedriver`) e devolve as respostas da IA como JSON.

Você envia um `prompt` (a pergunta atual) e, opcionalmente, um `context` com o histórico
de conversas. A API digita isso no navegador, espera a IA responder e retorna o texto.

> ⚠️ **Aviso importante:** o ChatGPT usa proteção anti-bot (Cloudflare). No modo
> **headless puro** há chance de bloqueio/CAPTCHA. Se isso acontecer, use o modo
> **Xvfb** (tela virtual) — veja a seção correspondente. Os seletores CSS do ChatGPT
> mudam com frequência; todos estão em variáveis de ambiente (`.env`) para ajuste rápido
> sem mexer no código.

---

## Estrutura

```
API-IA/
├── app/
│   ├── main.py       # FastAPI: endpoints /chat e /health
│   ├── config.py     # configurações via .env
│   ├── models.py     # modelos de request/response
│   ├── browser.py    # criação do driver Selenium (stealth, headless)
│   └── chatgpt.py    # automação da página + serialização por lock
├── deploy/
│   └── api-ia.service  # unit do systemd
├── requirements.txt
├── run.sh
├── .env.example
└── README.md
```

## API

### `POST /chat`
```json
{
  "prompt": "Resuma o texto acima em 3 tópicos.",
  "context": [
    { "role": "user", "content": "Olá, preciso analisar um contrato." },
    { "role": "assistant", "content": "Claro, envie o contrato." }
  ]
}
```
Resposta:
```json
{ "response": "1. ...\n2. ...\n3. ...", "elapsed_seconds": 12.4 }
```

Se `API_KEY` estiver definida no `.env`, envie o header `X-API-Key: <sua-chave>`.

### `GET /health`
```json
{ "status": "ok", "browser_ready": true }
```

Documentação interativa automática em `http://SEU_IP:8000/docs`.

---

## Instalação no Ubuntu Server

```bash
# 1. Dependências do sistema + Google Chrome
sudo apt update
sudo apt install -y python3 python3-venv python3-pip wget xvfb
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# 2. Projeto
sudo mkdir -p /opt/api-ia && sudo chown $USER /opt/api-ia
# copie os arquivos do projeto para /opt/api-ia, depois:
cd /opt/api-ia
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configuração
cp .env.example .env
nano .env          # ajuste API_KEY, HEADLESS, etc.

# 4. Rodar (teste)
chmod +x run.sh
./run.sh
```

Teste em outra máquina:
```bash
curl -X POST http://SEU_IP:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Diga olá em 3 idiomas."}'
```

## Se o headless for bloqueado (Xvfb)

Edite o `.env`:
```
HEADLESS=false
```
O `run.sh` detecta isso e sobe o Chrome "normal" dentro de uma tela virtual com `xvfb-run`.
É mais pesado, porém bem menos detectável pelo anti-bot.

## Rodar como serviço (systemd)

```bash
sudo useradd -r -s /usr/sbin/nologin apiia || true
sudo chown -R apiia /opt/api-ia
sudo cp deploy/api-ia.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now api-ia
sudo systemctl status api-ia
journalctl -u api-ia -f      # ver logs
```

---

## Notas de operação

- **Concorrência:** há **um único navegador** compartilhado. As requisições `/chat` são
  serializadas por um lock — chamadas simultâneas esperam sua vez. Para paralelismo real,
  seria preciso um pool de browsers (não incluído nesta versão).
- **Contexto vs. memória do site:** cada chamada monta o prompt completo (`context` + `prompt`)
  e o envia na conversa atual do navegador. O ChatGPT também mantém o próprio histórico na
  aba aberta; se quiser conversas totalmente isoladas, reinicie o browser entre chamadas.
- **Manutenção:** se as respostas pararem de vir, quase sempre é (a) bloqueio anti-bot →
  troque para Xvfb, ou (b) seletor CSS desatualizado → ajuste os `*_SELECTOR` no `.env`.
```

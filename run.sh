#!/usr/bin/env bash
set -euo pipefail

# Ativa o venv se existir
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# Carrega variáveis do .env (HEADLESS, WINDOW_SIZE, etc.)
source .env 2>/dev/null || true

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Se HEADLESS=false, o Chrome abre uma janela real e precisa de um servidor X.
# Usamos um Xvfb dedicado num display fixo (:99) e exportamos DISPLAY.
#
# Obs: NÃO usamos 'xvfb-run' de propósito. Quando o uvicorn lança o Chrome como
# subprocesso, o Chrome não alcança o X server efêmero do xvfb-run
# ("Missing X server or $DISPLAY") e morre no startup. Um Xvfb persistente num
# display fixo resolve isso de forma determinística.
if [ "${HEADLESS:-true}" = "false" ]; then
  DISPLAY_NUM="${DISPLAY_NUM:-99}"
  SIZE="$(echo "${WINDOW_SIZE:-1280,900}" | tr ',' 'x')x24"
  if ! pgrep -x Xvfb >/dev/null 2>&1; then
    echo "Iniciando Xvfb em :${DISPLAY_NUM} (${SIZE})..."
    rm -f "/tmp/.X${DISPLAY_NUM}-lock"
    Xvfb ":${DISPLAY_NUM}" -screen 0 "${SIZE}" -nolisten tcp &
    sleep 2
  fi
  export DISPLAY=":${DISPLAY_NUM}"
  echo "Rodando com Xvfb (DISPLAY=${DISPLAY})..."
fi

exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"

"""API FastAPI que expõe o ChatGPT automatizado via Selenium."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .chatgpt import client
from .config import settings
from .models import ChatRequest, ChatResponse, HealthResponse

_STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api-ia")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Subindo browser...")
    try:
        client.start()
    except Exception:  # noqa: BLE001
        logger.exception("Falha ao iniciar o browser no startup")
    yield
    logger.info("Encerrando browser...")
    client.stop()


app = FastAPI(
    title="API-IA",
    description="API que automatiza o ChatGPT via Selenium e devolve as respostas.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS liberado: permite testar a API a partir de qualquer origem (o /chat continua
# protegido pela API_KEY quando configurada).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index() -> HTMLResponse:
    """Serve o console de testes (interface gráfica) da API."""
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Se settings.api_key estiver definido, exige o header X-API-Key."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente.")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", browser_ready=client.ready)


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(req: ChatRequest) -> ChatResponse:
    """Envia prompt + contexto para o ChatGPT e retorna a resposta.

    Endpoint síncrono de propósito: o FastAPI o executa em threadpool e o
    ChatGPTClient serializa o acesso ao browser com um lock interno.
    """
    if not client.ready:
        raise HTTPException(status_code=503, detail="Browser não está pronto.")
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt não pode ser vazio.")

    started = time.time()
    try:
        answer = client.ask(req.prompt, req.context)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro inesperado ao consultar a IA")
        raise HTTPException(status_code=500, detail=f"Erro interno: {exc}") from exc

    return ChatResponse(response=answer, elapsed_seconds=round(time.time() - started, 2))

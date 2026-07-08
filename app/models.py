"""Modelos de entrada/saída da API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Uma mensagem do histórico de conversa."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="A pergunta/instrução atual a ser enviada.")
    context: list[Message] = Field(
        default_factory=list,
        description="Histórico de conversas anteriores usado como contexto.",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Texto da resposta gerada pela IA (bruto).")
    elapsed_seconds: float
    data: dict | None = Field(
        default=None,
        description=(
            "Se a resposta da IA for um JSON válido, aqui vai o objeto já "
            "parseado (ex.: {'setor': 'financeiro'}). Caso contrário, null."
        ),
    )


class HealthResponse(BaseModel):
    status: str
    browser_ready: bool

"""Configurações da aplicação, carregadas de variáveis de ambiente / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- API ----
    api_key: str = ""  # se preenchido, exige header X-API-Key nas requisições
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- Site alvo ----
    target_url: str = "https://chatgpt.com/"

    # ---- Browser ----
    headless: bool = True
    # caminho opcional para um binário específico do Chrome/Chromium
    chrome_binary: str | None = None
    # diretório de perfil persistente (mantém cookies/estado entre reinícios)
    user_data_dir: str | None = None
    window_size: str = "1280,900"
    # user-agent customizado (vazio = usa o padrão do Chrome)
    user_agent: str = ""

    # ---- Timeouts (segundos) ----
    page_load_timeout: int = 60
    # tempo máximo esperando a resposta terminar de ser gerada
    response_timeout: int = 180
    # início da geração (aparecer a primeira resposta)
    generation_start_timeout: int = 30

    # ---- Seletores (CSS) — ChatGPT muda com frequência, ajuste aqui sem tocar no código ----
    input_selector: str = "#prompt-textarea"
    send_button_selector: str = "button[data-testid='send-button']"
    stop_button_selector: str = "button[data-testid='stop-button']"
    assistant_message_selector: str = "div[data-message-author-role='assistant']"
    # botões/links de modais que aparecem no modo deslogado (fechados se existirem)
    dismiss_selectors: str = "button[data-testid='close-button'],a[href*='auth']"


settings = Settings()

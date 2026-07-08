"""Criação e gerenciamento do driver Selenium (undetected-chromedriver)."""
from __future__ import annotations

import logging

import undetected_chromedriver as uc

from .config import settings

logger = logging.getLogger(__name__)


def build_driver() -> uc.Chrome:
    """Cria uma instância do Chrome com opções de stealth, pronta para servidor."""
    options = uc.ChromeOptions()

    # Flags essenciais para rodar em servidor headless (Ubuntu)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={settings.window_size}")
    options.add_argument("--lang=pt-BR")

    if settings.user_agent:
        options.add_argument(f"--user-agent={settings.user_agent}")

    if settings.chrome_binary:
        options.binary_location = settings.chrome_binary

    if settings.user_data_dir:
        # perfil persistente: cookies e estado sobrevivem a reinícios
        options.add_argument(f"--user-data-dir={settings.user_data_dir}")

    logger.info("Iniciando Chrome (headless=%s)...", settings.headless)
    driver = uc.Chrome(options=options, headless=settings.headless, use_subprocess=True)
    driver.set_page_load_timeout(settings.page_load_timeout)
    return driver

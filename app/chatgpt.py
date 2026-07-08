"""Automação da página do ChatGPT: envia prompt e extrai a resposta."""
from __future__ import annotations

import logging
import threading
import time

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .browser import build_driver
from .config import settings
from .models import Message

logger = logging.getLogger(__name__)


class ChatGPTClient:
    """Envolve um único driver Selenium. Acesso serializado por lock (thread-safe)."""

    def __init__(self) -> None:
        self._driver = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        with self._lock:
            if self._driver is not None:
                return
            self._driver = build_driver()
            self._driver.get(settings.target_url)
            self._dismiss_modals()
            logger.info("Browser pronto em %s", settings.target_url)

    def stop(self) -> None:
        with self._lock:
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:  # noqa: BLE001 - shutdown best-effort
                    logger.exception("Erro ao fechar o browser")
                self._driver = None

    @property
    def ready(self) -> bool:
        return self._driver is not None

    # ------------------------------------------------------------------ API pública
    def ask(self, prompt: str, context: list[Message]) -> str:
        """Envia prompt + contexto e devolve a resposta. Serializado por lock."""
        with self._lock:
            if self._driver is None:
                raise RuntimeError("Browser não iniciado")
            full_prompt = self._build_prompt(prompt, context)
            return self._send_and_wait(full_prompt)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _build_prompt(prompt: str, context: list[Message]) -> str:
        if not context:
            return prompt
        labels = {"system": "Instrução", "user": "Usuário", "assistant": "Assistente"}
        linhas = ["### Contexto da conversa"]
        for msg in context:
            linhas.append(f"{labels.get(msg.role, msg.role)}: {msg.content}")
        linhas.append("\n### Pergunta atual")
        linhas.append(prompt)
        return "\n".join(linhas)

    def _dismiss_modals(self) -> None:
        """Fecha modais de login/onboarding que aparecem no modo deslogado."""
        for selector in settings.dismiss_selectors.split(","):
            selector = selector.strip()
            if not selector:
                continue
            try:
                for el in self._driver.find_elements(By.CSS_SELECTOR, selector):
                    if el.is_displayed():
                        el.click()
                        time.sleep(0.5)
            except Exception:  # noqa: BLE001 - modal pode não existir
                pass

    def _type_prompt(self, editor, text: str) -> None:
        """Digita texto multi-linha usando Shift+Enter para não enviar antes da hora."""
        editor.click()
        actions = ActionChains(self._driver)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                actions.send_keys(line)
            if i < len(lines) - 1:
                actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
        actions.perform()

    def _send_and_wait(self, full_prompt: str) -> str:
        driver = self._driver
        wait = WebDriverWait(driver, settings.generation_start_timeout)

        self._dismiss_modals()

        # quantas respostas já existem antes de enviar
        prior_count = len(driver.find_elements(By.CSS_SELECTOR, settings.assistant_message_selector))

        editor = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, settings.input_selector))
        )
        self._type_prompt(editor, full_prompt)

        # clica no botão de enviar; se não achar, manda Enter
        try:
            send_btn = driver.find_element(By.CSS_SELECTOR, settings.send_button_selector)
            send_btn.click()
        except NoSuchElementException:
            editor.send_keys(Keys.ENTER)

        # espera surgir uma nova mensagem do assistente
        try:
            wait.until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, settings.assistant_message_selector))
                > prior_count
            )
        except TimeoutException as exc:
            raise RuntimeError(
                "A resposta não começou a ser gerada (possível bloqueio anti-bot ou seletor errado)."
            ) from exc

        self._wait_generation_finished()
        return self._extract_last_answer()

    def _wait_generation_finished(self) -> None:
        """Espera o fim da geração: botão 'parar' some e o texto estabiliza."""
        driver = self._driver
        deadline = time.time() + settings.response_timeout

        # 1) enquanto o botão "stop" existir, ainda está gerando
        while time.time() < deadline:
            try:
                driver.find_element(By.CSS_SELECTOR, settings.stop_button_selector)
                time.sleep(0.5)
            except NoSuchElementException:
                break

        # 2) confirmação por estabilidade do texto (fallback caso o seletor mude)
        last_text = None
        stable = 0
        while time.time() < deadline:
            current = self._extract_last_answer(silent=True)
            if current == last_text and current:
                stable += 1
                if stable >= 3:  # ~1.5s estável
                    return
            else:
                stable = 0
                last_text = current
            time.sleep(0.5)

    def _extract_last_answer(self, silent: bool = False) -> str:
        try:
            msgs = self._driver.find_elements(
                By.CSS_SELECTOR, settings.assistant_message_selector
            )
            if not msgs:
                return ""
            return msgs[-1].text.strip()
        except (StaleElementReferenceException, NoSuchElementException):
            if silent:
                return ""
            raise


client = ChatGPTClient()

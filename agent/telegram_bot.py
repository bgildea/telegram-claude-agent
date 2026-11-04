"""Telegram long-polling loop. No webhook or public server needed."""

from __future__ import annotations

import logging
import time

import httpx

from .core import Agent
from .guardrails import AllowList

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Split long replies on paragraph or line breaks so Telegram accepts them."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


class TelegramBot:
    def __init__(self, token: str, agent: Agent, allow_list: AllowList, http: httpx.Client | None = None) -> None:
        self.api = f"https://api.telegram.org/bot{token}"
        self.agent = agent
        self.allow_list = allow_list
        self.http = http or httpx.Client(timeout=40)
        self.offset = 0

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text")
        if chat_id is None or text is None:
            return
        if not self.allow_list.allows(chat_id):
            log.warning("ignored message from chat %s (not on allow list)", chat_id)
            return
        if text.strip() == "/reset":
            self.agent.memory.clear_history(chat_id)
            self.send(chat_id, "Conversation cleared. Saved notes are kept.")
            return
        if text.strip() == "/start":
            self.send(chat_id, "Hi. Ask me anything, or tell me something to remember.")
            return
        reply = self.agent.handle(chat_id, text)
        for part in split_message(reply.text):
            self.send(chat_id, part)

    def send(self, chat_id: int, text: str) -> None:
        self.http.post(f"{self.api}/sendMessage", json={"chat_id": chat_id, "text": text})

    def poll_forever(self) -> None:
        log.info("polling Telegram for updates")
        while True:
            try:
                response = self.http.get(
                    f"{self.api}/getUpdates", params={"timeout": 30, "offset": self.offset}
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    self.offset = update["update_id"] + 1
                    try:
                        self.handle_update(update)
                    except Exception:
                        log.exception("failed to handle update %s", update.get("update_id"))
            except httpx.HTTPError as exc:
                log.warning("Telegram request failed: %s; retrying in 5s", exc)
                time.sleep(5)

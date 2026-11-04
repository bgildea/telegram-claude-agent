"""Guardrails applied around every model call.

These are deliberately simple and deterministic, so they can be unit tested and
don't depend on the model behaving well.
"""

from __future__ import annotations

import re

# 13 to 19 digits, optionally separated by spaces or dashes: likely a payment card.
_CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_API_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|sk-ant-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,})\b")

MAX_INPUT_CHARS = 4000


def luhn_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def redact(text: str) -> str:
    """Remove payment card numbers and API keys before text reaches the model or the log."""

    def card(match: re.Match[str]) -> str:
        return "[card number removed]" if luhn_valid(match.group(0)) else match.group(0)

    text = _CARD_RE.sub(card, text)
    return _API_KEY_RE.sub("[secret removed]", text)


def check_input(text: str) -> str | None:
    """Return a refusal message if the input should not be processed, else None."""
    if not text.strip():
        return "Send me a message and I'll do my best."
    if len(text) > MAX_INPUT_CHARS:
        return f"That's a long one. Please keep messages under {MAX_INPUT_CHARS} characters."
    return None


class AllowList:
    """Only listed Telegram chat IDs may use the bot. An empty list allows nobody."""

    def __init__(self, chat_ids: set[int]) -> None:
        self._chat_ids = chat_ids

    @classmethod
    def from_env(cls, value: str | None) -> AllowList:
        ids = {int(part) for part in (value or "").replace(" ", "").split(",") if part}
        return cls(ids)

    def allows(self, chat_id: int) -> bool:
        return chat_id in self._chat_ids

"""Run the bot: python -m agent"""

from __future__ import annotations

import logging
import os
import sys

from .core import Agent, AgentConfig
from .guardrails import AllowList
from .memory import Memory
from .telegram_bot import TelegramBot


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY (see .env.example).", file=sys.stderr)
        return 1

    allow_list = AllowList.from_env(os.environ.get("ALLOWED_CHAT_IDS"))

    import anthropic  # imported here so tests don't need the SDK configured

    client = anthropic.Anthropic()
    budget = os.environ.get("DAILY_TOKEN_BUDGET", "").strip()
    if budget and not budget.isdigit():
        print("DAILY_TOKEN_BUDGET must be a whole number of tokens, or empty for no limit.", file=sys.stderr)
        return 1

    config = AgentConfig(
        model=os.environ.get("ANTHROPIC_MODEL", AgentConfig.model),
        default_timezone=os.environ.get("DEFAULT_TIMEZONE", AgentConfig.default_timezone),
        daily_token_budget=int(budget) if budget else None,
    )
    agent = Agent(client.messages, Memory(os.environ.get("MEMORY_PATH", "agent.db")), config)
    TelegramBot(token, agent, allow_list).poll_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

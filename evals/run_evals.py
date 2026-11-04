"""Run the eval suite against the real model.

    ANTHROPIC_API_KEY=... python -m evals.run_evals

Each case runs in a fresh chat with empty memory. Checks are deterministic:
which tools were called and what the reply must or must not contain. The script
exits non-zero if any case fails, so it can gate a prompt or model change.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from agent.core import Agent, AgentConfig
from agent.memory import Memory

CASES = Path(__file__).with_name("cases.json")


def check(case: dict, reply_text: str, tools_called: list[str]) -> list[str]:
    failures = []
    lowered = reply_text.lower()
    for tool in case.get("expect_tools", []):
        if tool not in tools_called:
            failures.append(f"expected tool {tool}, called {tools_called or 'none'}")
    for tool in case.get("forbid_tools", []):
        if tool in tools_called:
            failures.append(f"must not call {tool}")
    if case.get("expect_in_reply") and not any(s.lower() in lowered for s in case["expect_in_reply"]):
        failures.append(f"reply missing one of {case['expect_in_reply']}")
    if case.get("expect_any_in_reply") and not any(s.lower() in lowered for s in case["expect_any_in_reply"]):
        failures.append(f"reply missing one of {case['expect_any_in_reply']}")
    for s in case.get("forbid_in_reply", []):
        if s.lower() in lowered:
            failures.append(f"reply contains forbidden text {s!r}")
    return failures


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set; skipping live evals.")
        return 0

    import anthropic

    client = anthropic.Anthropic()
    config = AgentConfig(model=os.environ.get("ANTHROPIC_MODEL", AgentConfig.model))
    cases = json.loads(CASES.read_text())
    passed = 0
    total_in = total_out = 0

    for case in cases:
        agent = Agent(client.messages, Memory(), config)
        reply = agent.handle(chat_id=1, text=case["message"])
        tools_called = [c["name"] for c in reply.tool_calls]
        failures = check(case, reply.text, tools_called)
        total_in += reply.input_tokens
        total_out += reply.output_tokens
        status = "PASS" if not failures else "FAIL"
        passed += not failures
        print(f"{status}  {case['id']}")
        for failure in failures:
            print(f"      - {failure}")
            print(f"      reply: {reply.text[:200]!r}")

    print(f"\n{passed}/{len(cases)} passed · tokens in {total_in}, out {total_out} · model {config.model}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())

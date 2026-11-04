"""A scripted stand-in for the Anthropic messages client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def text(content: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=content)


def tool_use(name: str, args: dict[str, Any], id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=args)


def response(*blocks: SimpleNamespace, stop: str | None = None) -> SimpleNamespace:
    if stop is None:
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


class ScriptedModel:
    """Returns the queued responses in order and records every request."""

    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot messages: the agent keeps appending to the same list.
        self.requests.append({**kwargs, "messages": [dict(m) for m in kwargs["messages"]]})
        if not self.responses:
            raise AssertionError("ScriptedModel ran out of responses")
        return self.responses.pop(0)

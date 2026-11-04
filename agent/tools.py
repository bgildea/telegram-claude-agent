"""Tools the agent can call.

Each tool is a plain function plus a JSON schema the model sees. Tools receive a
ToolContext so they can reach per-chat memory without global state.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .memory import Memory


@dataclass
class ToolContext:
    chat_id: int
    memory: Memory
    default_timezone: str = "Asia/Bangkok"


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[ToolContext, dict[str, Any]], str]
    tags: set[str] = field(default_factory=set)

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


class ToolError(Exception):
    """Raised for bad tool input. The message is shown to the model so it can recover."""


# --- current time -----------------------------------------------------------


def _current_time(ctx: ToolContext, args: dict[str, Any]) -> str:
    tz_name = args.get("timezone") or ctx.default_timezone
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except ZoneInfoNotFoundError as exc:
        raise ToolError(f"Unknown timezone '{tz_name}'. Use an IANA name like Europe/Dublin.") from exc
    return now.strftime(f"%A %d %B %Y, %H:%M ({tz_name})")


# --- calculator -------------------------------------------------------------

_OPERATORS: dict[type, Callable[..., float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str) -> float:
    """Evaluate arithmetic only. No names, calls or attribute access."""
    if len(expression) > 200:
        raise ToolError("Expression too long.")

    def walk(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ToolError("Exponent too large.")
            return _OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](walk(node.operand))
        raise ToolError("Only numbers and + - * / // % ** are allowed.")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError("That isn't a valid arithmetic expression.") from exc
    try:
        return walk(tree)
    except ZeroDivisionError as exc:
        raise ToolError("Division by zero.") from exc


def _calculate(ctx: ToolContext, args: dict[str, Any]) -> str:
    result = safe_eval(str(args.get("expression", "")))
    return f"{result:g}" if isinstance(result, float) else str(result)


# --- notes ------------------------------------------------------------------


def _remember(ctx: ToolContext, args: dict[str, Any]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ToolError("Nothing to remember.")
    if len(text) > 500:
        raise ToolError("Notes are limited to 500 characters.")
    note = ctx.memory.save_note(ctx.chat_id, text)
    return f"Saved note #{note.id}."


def _recall(ctx: ToolContext, args: dict[str, Any]) -> str:
    notes = ctx.memory.search_notes(ctx.chat_id, str(args.get("query", "")))
    if not notes:
        return "No matching notes."
    return "\n".join(f"#{n.id}: {n.text}" for n in notes)


def _forget(ctx: ToolContext, args: dict[str, Any]) -> str:
    note_id = args.get("note_id")
    if not isinstance(note_id, int):
        raise ToolError("note_id must be an integer.")
    return f"Deleted note #{note_id}." if ctx.memory.delete_note(ctx.chat_id, note_id) else f"No note #{note_id}."


DEFAULT_TOOLS: list[Tool] = [
    Tool(
        name="get_current_time",
        description="Get the current date and time, optionally in a given IANA timezone.",
        input_schema={
            "type": "object",
            "properties": {"timezone": {"type": "string", "description": "e.g. Europe/Dublin. Defaults to the user's timezone."}},
        },
        run=_current_time,
        tags={"read"},
    ),
    Tool(
        name="calculate",
        description="Evaluate an arithmetic expression exactly. Use this instead of doing maths in your head.",
        input_schema={
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "e.g. (1299 * 12) * 0.93"}},
            "required": ["expression"],
        },
        run=_calculate,
        tags={"read"},
    ),
    Tool(
        name="remember",
        description="Save a note the user explicitly asked you to remember. Do not save things they didn't ask you to keep.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        run=_remember,
        tags={"write"},
    ),
    Tool(
        name="recall",
        description="Search the user's saved notes. Call with an empty query to list recent notes.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        run=_recall,
        tags={"read"},
    ),
    Tool(
        name="forget",
        description="Delete a saved note by its number, when the user asks.",
        input_schema={
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
        run=_forget,
        tags={"write"},
    ),
]

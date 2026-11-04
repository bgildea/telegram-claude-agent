import pytest

from agent.guardrails import AllowList, check_input, luhn_valid, redact
from agent.memory import Memory
from agent.telegram_bot import split_message
from agent.tools import DEFAULT_TOOLS, ToolContext, ToolError, safe_eval

TOOLS = {t.name: t for t in DEFAULT_TOOLS}


@pytest.fixture
def ctx():
    return ToolContext(chat_id=7, memory=Memory())


@pytest.mark.parametrize(
    "expr,expected",
    [("2 + 2", 4), ("(1299 * 12) * 0.5", 7794.0), ("-3 ** 2", -9), ("7 // 2", 3), ("10 % 4", 2)],
)
def test_safe_eval_arithmetic(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "a + 1", "2 ** 1000", "1 / 0", "2 +"])
def test_safe_eval_rejects_anything_else(expr):
    with pytest.raises(ToolError):
        safe_eval(expr)


def test_current_time_rejects_unknown_timezone(ctx):
    with pytest.raises(ToolError, match="Unknown timezone"):
        TOOLS["get_current_time"].run(ctx, {"timezone": "Mars/Base"})


def test_current_time_uses_requested_zone(ctx):
    assert "Europe/Dublin" in TOOLS["get_current_time"].run(ctx, {"timezone": "Europe/Dublin"})


def test_remember_recall_forget_round_trip(ctx):
    assert TOOLS["remember"].run(ctx, {"text": "Dentist on Friday"}) == "Saved note #1."
    assert TOOLS["recall"].run(ctx, {"query": "dentist"}) == "#1: Dentist on Friday"
    assert TOOLS["forget"].run(ctx, {"note_id": 1}) == "Deleted note #1."
    assert TOOLS["recall"].run(ctx, {}) == "No matching notes."


def test_memory_history_is_trimmed_and_starts_with_user():
    memory = Memory(history_limit=3)
    for i in range(3):
        memory.add_message(1, "user", f"q{i}")
        memory.add_message(1, "assistant", f"a{i}")
    history = memory.history(1)
    assert history[0]["role"] == "user"
    assert len(history) <= 3


def test_luhn():
    assert luhn_valid("4242424242424242")
    assert not luhn_valid("4242424242424241")


def test_redact_keeps_ordinary_numbers():
    assert redact("Order 1234567890123 shipped") == "Order 1234567890123 shipped"


def test_redact_removes_keys():
    assert "[secret removed]" in redact("key sk-ant-abcdefghijklmnopqrstuv")


def test_check_input_limits():
    assert check_input("") is not None
    assert check_input("x" * 5000) is not None
    assert check_input("hello") is None


def test_allow_list_from_env():
    allow = AllowList.from_env("123, 456")
    assert allow.allows(123) and allow.allows(456)
    assert not allow.allows(789)
    assert not AllowList.from_env("").allows(123)


def test_split_message_respects_limit():
    long_text = ("paragraph " * 50 + "\n\n") * 20
    parts = split_message(long_text, limit=500)
    assert all(len(p) <= 500 for p in parts)
    assert "".join(parts).replace(" ", "").replace("\n", "") == long_text.replace(" ", "").replace("\n", "")

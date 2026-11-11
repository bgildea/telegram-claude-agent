from datetime import datetime
from zoneinfo import ZoneInfo

from agent.core import BUDGET_MESSAGE, Agent, AgentConfig
from agent.memory import Memory

from .fakes import ScriptedModel, response, text, tool_use


class FixedClock:
    """Returns a set UTC moment, converted to whatever zone the agent asks for."""

    def __init__(self, utc: datetime) -> None:
        self.utc = utc

    def __call__(self, tz: ZoneInfo) -> datetime:
        return self.utc.astimezone(tz)


NOON_UTC = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("UTC"))


def make_agent(model, budget, clock=None, memory=None):
    return Agent(model, memory or Memory(), AgentConfig(daily_token_budget=budget), clock=clock or FixedClock(NOON_UTC))


def test_usage_is_recorded_per_chat_and_day():
    model = ScriptedModel(response(tool_use("get_current_time", {})), response(text("Noon.")))
    agent = make_agent(model, budget=None)

    agent.handle(1, "time?")

    assert agent.memory.tokens_used(1, "2026-11-11") == 30  # two calls of 10 in + 5 out
    assert agent.memory.tokens_used(2, "2026-11-11") == 0
    assert agent.memory.tokens_used(1, "2026-11-12") == 0


def test_no_budget_means_no_limit():
    memory = Memory()
    memory.add_usage(1, "2026-11-11", 1_000_000, 1_000_000)
    model = ScriptedModel(response(text("Still here.")))

    reply = make_agent(model, budget=None, memory=memory).handle(1, "hi")

    assert reply.text == "Still here."
    assert reply.over_budget is False


def test_chat_over_budget_is_refused_without_calling_the_model():
    memory = Memory()
    memory.add_usage(1, "2026-11-11", 80, 20)
    model = ScriptedModel()

    reply = make_agent(model, budget=100, memory=memory).handle(1, "hi")

    assert reply.over_budget is True
    assert reply.text == BUDGET_MESSAGE
    assert model.requests == []
    assert memory.history(1) == []  # refused messages are not added to history


def test_budget_is_per_chat():
    memory = Memory()
    memory.add_usage(1, "2026-11-11", 100, 0)
    model = ScriptedModel(response(text("Hi chat 2.")))

    reply = make_agent(model, budget=100, memory=memory).handle(2, "hi")

    assert reply.text == "Hi chat 2."


def test_turn_under_budget_runs_and_can_finish_above_it():
    memory = Memory()
    memory.add_usage(1, "2026-11-11", 90, 0)
    model = ScriptedModel(response(tool_use("get_current_time", {})), response(text("Noon.")))
    agent = make_agent(model, budget=100, memory=memory)

    first = agent.handle(1, "time?")
    second = agent.handle(1, "and now?")

    assert first.text == "Noon."
    assert memory.tokens_used(1, "2026-11-11") == 120
    assert second.over_budget is True


def test_budget_resets_on_a_new_day_in_the_configured_timezone():
    memory = Memory()
    # 18:00 UTC on 11 Nov is already 01:00 on 12 Nov in Bangkok (UTC+7).
    late_utc = datetime(2026, 11, 11, 18, 0, tzinfo=ZoneInfo("UTC"))
    memory.add_usage(1, "2026-11-11", 500, 0)
    model = ScriptedModel(response(text("New day.")))

    reply = make_agent(model, budget=100, memory=memory, clock=FixedClock(late_utc)).handle(1, "hi")

    assert reply.text == "New day."
    assert memory.tokens_used(1, "2026-11-12") == 15

from agent.core import Agent, AgentConfig
from agent.memory import Memory

from .fakes import ScriptedModel, response, text, tool_use


def make_agent(model: ScriptedModel, **config) -> Agent:
    return Agent(model, Memory(), AgentConfig(**config))


def test_plain_reply_is_returned_and_stored():
    model = ScriptedModel(response(text("Hello Barry")))
    agent = make_agent(model)

    reply = agent.handle(1, "hi")

    assert reply.text == "Hello Barry"
    assert agent.memory.history(1) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello Barry"},
    ]


def test_tool_call_runs_and_result_goes_back_to_model():
    model = ScriptedModel(
        response(tool_use("calculate", {"expression": "1299 * 12"})),
        response(text("That's 15,588 a year.")),
    )
    agent = make_agent(model)

    reply = agent.handle(1, "1299 a month, what's that per year?")

    assert reply.text == "That's 15,588 a year."
    assert reply.tool_calls == [{"name": "calculate", "input": {"expression": "1299 * 12"}, "error": False}]
    tool_result = model.requests[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["content"] == "15588"
    assert tool_result["is_error"] is False


def test_bad_tool_input_is_reported_to_model_not_raised():
    model = ScriptedModel(
        response(tool_use("calculate", {"expression": "__import__('os')"})),
        response(text("I can only do arithmetic.")),
    )
    reply = make_agent(model).handle(1, "run this")

    assert reply.tool_calls[0]["error"] is True
    assert "Only numbers" in model.requests[1]["messages"][-1]["content"][0]["content"]


def test_unknown_tool_is_an_error_result():
    model = ScriptedModel(response(tool_use("delete_everything", {})), response(text("Sorry.")))
    reply = make_agent(model).handle(1, "do it")
    assert reply.tool_calls[0]["error"] is True


def test_loop_stops_after_max_tool_rounds():
    looping = [response(tool_use("get_current_time", {}, id=f"t{i}")) for i in range(10)]
    model = ScriptedModel(*looping)
    reply = make_agent(model, max_tool_rounds=2).handle(1, "time?")

    assert reply.stopped_early is True
    assert len(model.requests) == 3  # first call + 2 tool rounds


def test_card_numbers_are_redacted_before_reaching_the_model():
    model = ScriptedModel(response(text("Noted, but please don't share card numbers.")))
    agent = make_agent(model)

    agent.handle(1, "my card is 4242 4242 4242 4242")

    sent = model.requests[0]["messages"][-1]["content"]
    assert "4242 4242" not in sent
    assert "[card number removed]" in sent


def test_empty_message_never_calls_the_model():
    model = ScriptedModel()
    reply = make_agent(model).handle(1, "   ")
    assert model.requests == []
    assert reply.text


def test_token_usage_is_summed_across_rounds():
    model = ScriptedModel(response(tool_use("get_current_time", {})), response(text("It's noon.")))
    reply = make_agent(model).handle(1, "time?")
    assert (reply.input_tokens, reply.output_tokens) == (20, 10)


def test_chats_do_not_share_memory():
    model = ScriptedModel(
        response(tool_use("remember", {"text": "likes oat milk"})),
        response(text("Saved.")),
        response(tool_use("recall", {"query": ""})),
        response(text("Nothing saved yet.")),
    )
    agent = make_agent(model)
    agent.handle(1, "remember I like oat milk")
    agent.handle(2, "what do you know about me?")

    recall_result = model.requests[3]["messages"][-1]["content"][0]["content"]
    assert recall_result == "No matching notes."

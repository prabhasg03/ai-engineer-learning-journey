"""pytest tests for the Topic 17 tool-calling loop.

All tests run offline using the scripted LLM, so they're deterministic.
"""

from tool_calling import (
    ScriptedLLM,
    assistant_text,
    check_protocol,
    execute_tool,
    parallel_tool_call_request,
    run_tool_call_loop,
    tool_call_request,
)


def weather_final_answer(messages: list) -> dict:
    seen = {}
    for message in [m for m in messages if m.get("role") == "tool"]:
        import json

        data = json.loads(message["content"])
        if "temperature" in data:
            seen[data["city"]] = (
                data["city"] + " is " + str(data["temperature"]) + " deg " + data["units"].upper()
            )
    if not seen:
        return assistant_text("I could not get the weather.")
    return assistant_text("; ".join(seen.values()) + ".")


def explain_missing_tool(messages: list) -> dict:
    import json

    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    last = tool_msgs[-1]["content"] if tool_msgs else "{}"
    return assistant_text("I cannot do that: " + last)


def test_execute_tool_runs_valid_call():
    out = execute_tool("get_weather", '{"city": "Seattle"}')
    assert out["city"] == "Seattle"
    assert out["temperature"] == 15.0


def test_execute_tool_rejects_bad_enum():
    out = execute_tool("get_weather", '{"city": "Seattle", "units": "kelvin"}')
    assert out["error"] == "invalid arguments"


def test_execute_tool_unknown_tool():
    out = execute_tool("send_email", "{}")
    assert out["error"].startswith("unknown tool")


def test_execute_tool_bad_json():
    out = execute_tool("calculate", "not json")
    assert out["error"].startswith("arguments were not valid JSON")


def test_loop_single_call():
    llm = ScriptedLLM(
        [
            tool_call_request("call_weather_1", "get_weather", {"city": "Seattle", "units": "c"}),
            weather_final_answer,
        ],
    )
    result = run_tool_call_loop("What is the weather in Seattle?", llm, verbose=False)
    assert result.answer == "Seattle is 15.0 deg C."
    assert result.tool_calls_made == 1
    assert check_protocol(result.messages) == []


def test_loop_parallel_calls():
    llm = ScriptedLLM(
        [
            parallel_tool_call_request(
                [
                    ("call_par_1", "get_weather", {"city": "Seattle", "units": "c"}),
                    ("call_par_2", "get_weather", {"city": "Portland", "units": "f"}),
                    ("call_par_3", "get_weather", {"city": "Tokyo", "units": "c"}),
                ]
            ),
            weather_final_answer,
        ],
    )
    result = run_tool_call_loop("Compare weather in Seattle, Portland and Tokyo.", llm, verbose=False)
    assert result.tool_calls_made == 3
    assert "Seattle" in result.answer and "Tokyo" in result.answer
    assert check_protocol(result.messages) == []


def test_loop_corrects_hallucinated_arguments():
    llm = ScriptedLLM(
        [
            tool_call_request("call_bad_1", "get_weather", {"city": "Tokyo", "units": "kelvin"}),
            tool_call_request("call_good_1", "get_weather", {"city": "Tokyo", "units": "c"}),
            weather_final_answer,
        ],
    )
    result = run_tool_call_loop("Weather in Tokyo?", llm, verbose=False)
    assert result.tool_calls_made == 2
    assert "22.0" in result.answer
    assert check_protocol(result.messages) == []


def test_loop_unknown_tool():
    llm = ScriptedLLM(
        [
            tool_call_request("call_unknown_1", "send_email", {"to": "team@example.com"}),
            explain_missing_tool,
        ],
    )
    result = run_tool_call_loop("Email the team.", llm, verbose=False)
    assert "unknown tool" in result.answer
    assert check_protocol(result.messages) == []


def test_check_protocol_detects_problems():
    messages = [
        {"role": "tool", "tool_call_id": "ghost", "content": "{}"},
    ]
    problems = check_protocol(messages)
    assert any("no matching request" in p for p in problems)

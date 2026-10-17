"""Agent-loop tests: the hand-written loop, streaming, and the live client.

Everything here is offline.  The scripted ``MockLLM`` lets a test dictate exactly
what the "model" asks for - including an unknown tool and hallucinated
arguments - so the failures a real model produces are reproducible.  The live
client is exercised with ``httpx.MockTransport``, which is also how the
"transient failure is retried / permanent error is not" requirement is proven
for the outbound call itself.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx
import pytest

from app.agent import SYSTEM_PROMPT, build_messages, run_agent, stream_agent
from app.config import Settings
from app.llm import (
    LLMDelta,
    LLMError,
    LLMResponse,
    MockLLM,
    MockTurn,
    OpenAICompatibleLLM,
    sse_payload,
)
from app.models import AssistantRequest, ToolCall, Usage
from app.retry import RetryPolicy
from app.tools import TOOL_SCHEMAS


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _live_settings() -> Settings:
    """Live-client settings with retries that never actually sleep."""
    return Settings(
        use_mock_llm=False,
        llm_model="test-model",
        retry=RetryPolicy(
            max_attempts=3,
            base=0.0,
            multiplier=1.0,
            max_delay=0.0,
            jitter="none",
            max_elapsed=None,
        ),
    )


def _http_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _chat_completion(content: str | None = "Hello", tool_calls: list | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "model": "test-model",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }


class _RecordingLLM:
    """Wrap a MockLLM and remember every call, to prove usage is summed."""

    name = "recording"
    model = "recording-model"

    def __init__(self, inner: MockLLM) -> None:
        self._inner = inner
        self.calls = 0
        self.usage = Usage()

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = self._inner.complete(messages, tools, temperature)
        self.calls += 1
        self.usage = self.usage + response.usage
        return response

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> Iterator[LLMDelta]:
        yield from self._inner.stream(messages, tools, temperature)


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #


def test_a_single_tool_call_produces_a_final_answer(catalog, settings):
    request = AssistantRequest(message="show me wireless headphones under $150")

    result = run_agent(request, catalog, MockLLM(), settings)

    assert result.stop_reason == "final"
    assert result.iterations == 2  # one tool turn + one answer turn
    assert [call.name for call in result.tool_calls] == ["search_products"]
    assert result.tool_calls[0].ok is True
    assert [p.sku for p in result.products] == ["SKU-001"]
    assert "Aurora Wireless Headphones" in result.answer
    assert result.model == "mock-shopping-llm"

    # Same input, fresh client: the mock is deterministic, like temperature 0.
    again = run_agent(request, catalog, MockLLM(), settings)
    assert again.answer == result.answer
    assert [p.sku for p in again.products] == [p.sku for p in result.products]


def test_parallel_tool_calls_in_one_turn_are_all_executed(catalog, settings):
    request = AssistantRequest(message="where is ORD-1001 and is SKU-002 in stock?")

    result = run_agent(request, catalog, MockLLM(), settings)

    assert [call.name for call in result.tool_calls] == ["get_order_status", "check_inventory"]
    assert all(call.ok for call in result.tool_calls)
    assert result.order_status is not None
    assert result.order_status.order_id == "ORD-1001"
    assert "35 unit" in result.answer  # the inventory result made it into the answer


def test_an_unknown_tool_request_is_recorded_and_the_loop_still_finishes(catalog, settings):
    """The model cannot execute anything; a bogus name must not crash the loop."""
    script = [
        MockTurn(tool_calls=[ToolCall(id="call_1", name="teleport_product", arguments={"x": 1})]),
        MockTurn(content="I don't have a tool for that, sorry."),
    ]

    result = run_agent(AssistantRequest(message="teleport a laptop to me"), catalog, MockLLM(script), settings)

    assert result.stop_reason == "final"
    assert result.iterations == 2
    record = result.tool_calls[0]
    assert record.ok is False
    assert "unknown tool" in (record.error or "")
    assert result.answer == "I don't have a tool for that, sorry."


def test_hallucinated_arguments_from_the_model_are_corrected(catalog, settings):
    """String numbers are repaired rather than rejected, so no extra round trip."""
    script = [
        MockTurn(
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="search_products",
                    arguments={"query": "headphones", "max_price": "150", "limit": "1"},
                )
            ]
        ),
        MockTurn(content="Here is one option."),
    ]

    result = run_agent(AssistantRequest(message="cheap headphones"), catalog, MockLLM(script), settings)

    record = result.tool_calls[0]
    assert record.ok is True
    assert record.arguments["max_price"] == "150"  # logged as the model sent it
    assert record.result is not None
    assert record.result["count"] == 1
    assert result.products[0].sku == "SKU-001"  # 129.99 <= 150 after coercion


def test_the_iteration_budget_stops_a_runaway_loop(catalog, settings):
    """A model that only ever asks for tools must still terminate cleanly."""
    always_tools = [
        MockTurn(tool_calls=[ToolCall(id=f"call_{i}", name="check_inventory", arguments={"sku": "SKU-001"})])
        for i in range(1, 6)
    ]
    llm = MockLLM(always_tools)

    result = run_agent(AssistantRequest(message="loop please", max_iterations=3), catalog, llm, settings)

    assert result.iterations == 3
    assert result.stop_reason == "max_iterations"
    assert len(result.tool_calls) == 3
    assert result.answer  # a graceful degraded answer, not an exception
    assert llm.script_remaining == 2  # it really did stop early


def test_usage_is_accumulated_across_every_iteration(catalog, settings):
    recorder = _RecordingLLM(MockLLM())

    result = run_agent(
        AssistantRequest(message="where is ORD-1003?"),
        catalog,
        recorder,
        settings,
    )

    assert recorder.calls == 2
    assert result.usage == recorder.usage
    assert result.usage.total_tokens == (
        result.usage.prompt_tokens + result.usage.completion_tokens
    )
    assert result.usage.prompt_tokens > 0


def test_messages_are_rebuilt_from_the_stateless_conversation(settings):
    request = AssistantRequest(
        message="and the cheaper one?",
        conversation=[
            {"role": "user", "content": "show me speakers"},
            {"role": "assistant", "content": "Here is a speaker."},
        ],
    )

    messages = build_messages(request)

    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "search_products" in messages[0]["content"]
    assert messages[-1]["content"] == "and the cheaper one?"


# --------------------------------------------------------------------------- #
# Streaming loop
# --------------------------------------------------------------------------- #


def test_streaming_yields_ordered_events_and_ends_with_the_structured_answer(catalog, settings):
    request = AssistantRequest(message="show me wireless headphones under $150")

    events = list(stream_agent(request, catalog, MockLLM(), settings))

    assert events[0].event == "start"
    assert events[-1].event == "final"
    assert [e.seq for e in events] == list(range(len(events)))

    names = [e.event for e in events]
    assert "tool_call" in names
    assert "token" in names

    tokens = "".join(e.data["text"] for e in events if e.event == "token")
    final = events[-1].data
    assert tokens == final["answer"]
    assert [p["sku"] for p in final["products"]] == ["SKU-001"]
    assert final["stop_reason"] == "final"

    tool_event = next(e for e in events if e.event == "tool_call")
    assert tool_event.data["arguments"]["max_price"] == 150.0
    assert tool_event.data["ok"] is True

    # A failure after the first byte cannot change the status code (topic 14),
    # so the loop reports it as an error event instead of pretending.
    class ExplodingLLM:
        name = "exploding"
        model = "exploding"

        def complete(self, messages, tools=None, temperature=0.2):  # pragma: no cover
            raise RuntimeError("should not be called")

        def stream(self, messages, tools=None, temperature=0.2):
            raise ConnectionError("model server went away")

    broken = list(
        stream_agent(AssistantRequest(message="hello"), catalog, ExplodingLLM(), settings)
    )
    assert [e.event for e in broken] == ["start", "error"]
    assert "went away" in broken[-1].data["message"]


# --------------------------------------------------------------------------- #
# The live client: payloads, SSE parsing, and retry placement
# --------------------------------------------------------------------------- #


def test_live_client_builds_the_request_and_parses_tool_calls_and_usage():
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json=_chat_completion(
                content=None,
                tool_calls=[
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {
                            "name": "search_products",
                            "arguments": '{"query": "wireless", "limit": 2}',
                        },
                    }
                ],
            ),
        )

    llm = OpenAICompatibleLLM(_live_settings(), client=_http_client(handler))
    response = llm.complete(
        [{"role": "user", "content": "wireless please"}],
        tools=TOOL_SCHEMAS,
    )

    assert seen["payload"]["model"] == "test-model"
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["tools"][0]["function"]["name"] == "search_products"
    assert seen["payload"]["tool_choice"] == "auto"
    assert seen["authorization"] == "Bearer not-needed"

    assert response.content is None
    assert response.tool_calls[0].name == "search_products"
    assert response.tool_calls[0].arguments == {"query": "wireless", "limit": 2}
    assert response.usage.total_tokens == 12
    assert response.model == "test-model"


def test_a_transient_outbound_failure_is_retried_but_a_permanent_one_is_not():
    """The retry contract, asserted on the real outbound call."""
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(200, json=_chat_completion("Hello"))

    llm = OpenAICompatibleLLM(_live_settings(), client=_http_client(flaky))
    response = llm.complete([{"role": "user", "content": "hi"}])

    assert response.content == "Hello"
    assert response.attempts == 2
    assert calls["n"] == 2

    denied = {"n": 0}

    def unauthorized(request: httpx.Request) -> httpx.Response:
        denied["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    bad = OpenAICompatibleLLM(_live_settings(), client=_http_client(unauthorized))
    with pytest.raises(LLMError) as excinfo:
        bad.complete([{"role": "user", "content": "hi"}])

    assert denied["n"] == 1  # a 401 is permanent: tried exactly once
    assert excinfo.value.attempts == 1


def test_live_stream_parses_sse_and_the_payload_helper_is_lenient():
    body = (
        "data: " + json.dumps({"choices": [{"delta": {"content": "Hel"}}]}) + "\n\n"
        "data: " + json.dumps({"choices": [{"delta": {"content": "lo"}}]}) + "\n\n"
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=body.encode("utf-8"), headers={"content-type": "text/event-stream"}
        )

    llm = OpenAICompatibleLLM(_live_settings(), client=_http_client(handler))
    deltas = list(llm.stream([{"role": "user", "content": "hi"}]))

    assert "".join(d.text for d in deltas if d.text) == "Hello"
    assert deltas[-1].done is True

    assert sse_payload('data: {"a": 1}') == '{"a": 1}'
    assert sse_payload("data: [DONE]") == "[DONE]"
    assert sse_payload(":heartbeat") is None
    assert sse_payload("event: token") is None
    assert sse_payload("") is None


def test_live_path_is_skippable_when_no_server_is_running():
    """``health_check`` is how a caller decides to skip the live path (not fail)."""

    def alive(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    assert OpenAICompatibleLLM(_live_settings(), client=_http_client(alive)).health_check() is True
    assert OpenAICompatibleLLM(_live_settings(), client=_http_client(dead)).health_check() is False

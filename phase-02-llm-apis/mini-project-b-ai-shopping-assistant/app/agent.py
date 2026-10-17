"""The hand-written tool-call loop (topics 17 and 38).

This module is the heart of the project and it is deliberately a plain
``while`` loop.  There is no framework and no hidden machinery:

1. send the conversation plus the tool schemas to the model;
2. if the model returns **tool-call requests**, execute them against the
   catalogue, append the results as ``tool`` messages, and go round again;
3. if it returns text, that is the final answer, stop;
4. stop anyway at the iteration budget, so a confused model cannot loop forever.

The single most important idea (topic 17): *the model never executes
anything.*  It emits a structured request; ``app.tools.execute_tool`` is the
code that runs, and it validates the model's arguments first.

Two entry points:

* :func:`run_agent` - returns one structured ``AssistantResponse``;
* :func:`stream_agent` - yields ``StreamEvent`` objects, so the client sees
  tool activity and answer tokens as they happen and still receives the same
  structured result as the final event.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .catalog import Catalog
from .config import Settings
from .llm import LLMClient, LLMResponse
from .models import (
    AssistantRequest,
    AssistantResponse,
    OrderStatus,
    Product,
    StreamEvent,
    ToolCallRecord,
    Usage,
)
from .tools import TOOL_SCHEMAS, execute_tool

__all__ = [
    "SYSTEM_PROMPT",
    "build_messages",
    "collect_order_status",
    "collect_products",
    "run_agent",
    "stream_agent",
]


SYSTEM_PROMPT = """You are a helpful shopping assistant for an online electronics store.

You have tools. Use them whenever a question depends on catalogue facts:
- search_products: find items matching what the shopper describes.
- check_inventory: check live stock for a specific SKU.
- get_order_status: look up an order by its id.

Rules:
- Never invent products, prices, stock levels or delivery dates. If a tool did
  not return a fact, do not state it.
- If a lookup returns nothing, say so plainly and suggest a next step.
- Prefer one tool call; use several in one turn only when the shopper asked
  about genuinely separate things (for example two different SKUs).
- Answer in one or two short sentences, in the shopper's language.
"""


# --------------------------------------------------------------------------- #
# Message construction
# --------------------------------------------------------------------------- #


def build_messages(request: AssistantRequest) -> list[dict[str, Any]]:
    """Assemble the message list for one request.

    The API is stateless (topic 4): the client resends the prior turns, and we
    rebuild the whole list on every call.  The system prompt is always first so
    a provider's prompt cache has a stable prefix to hit.
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in request.conversation:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": request.message})
    return messages


def _tool_content(record: ToolCallRecord, max_chars: int) -> str:
    """Serialise a tool result for the model, truncating pathological payloads.

    Tool output is context (topic 35): a search that returned 200 products would
    crowd out the actual question, so the payload is capped and the cap is
    visible to the model rather than silently losing data.
    """
    payload = record.result if record.ok else {"error": record.error}
    text = json.dumps(payload, separators=(",", ":"), default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + '...{"truncated":true}'
    return text


# --------------------------------------------------------------------------- #
# Result extraction
# --------------------------------------------------------------------------- #


def collect_products(records: list[ToolCallRecord]) -> list[Product]:
    """Products found by any successful ``search_products`` call (deduplicated)."""
    seen: dict[str, Product] = {}
    for record in records:
        if not record.ok or record.name != "search_products" or not record.result:
            continue
        for raw in record.result.get("products", []):
            try:
                product = Product.model_validate(raw)
            except Exception:
                continue
            seen.setdefault(product.sku, product)
    return list(seen.values())


def collect_order_status(records: list[ToolCallRecord]) -> OrderStatus | None:
    """The last successfully fetched order, if any."""
    order: OrderStatus | None = None
    for record in records:
        if not record.ok or record.name != "get_order_status" or not record.result:
            continue
        raw = record.result.get("order")
        if not raw:
            continue
        try:
            order = OrderStatus.model_validate(raw)
        except Exception:
            continue
    return order


def _fallback_answer(records: list[ToolCallRecord]) -> str:
    """What to say when the model never produced prose within its budget."""
    if not records:
        return "I wasn't able to answer that within the time budget. Please try rephrasing."
    failures = [r for r in records if not r.ok]
    if failures:
        return (
            "I looked that up but hit a problem: "
            + failures[0].error
            + " Please check the details and try again."
        )
    return (
        "I gathered the product information but ran out of turns before writing "
        "a summary. The details are in the structured fields of this response."
    )


# --------------------------------------------------------------------------- #
# Non-streaming loop
# --------------------------------------------------------------------------- #


def run_agent(
    request: AssistantRequest,
    catalog: Catalog,
    llm: LLMClient,
    settings: Settings,
) -> AssistantResponse:
    """Run the tool-call loop to a final, structured answer.

    The loop is bounded twice: by ``max_iterations`` (total LLM round trips) and
    implicitly by the fact that every tool is side-effect free, so a repeated
    call is harmless.  ``stop_reason`` tells the caller *why* it stopped, which
    is the difference between an answer and a graceful degradation.
    """
    budget = request.max_iterations or settings.max_iterations
    messages = build_messages(request)
    records: list[ToolCallRecord] = []
    usage = Usage()
    model = getattr(llm, "model", llm.name)
    answer: str | None = None
    stop_reason: str = "max_iterations"
    iterations = 0

    for iteration in range(1, budget + 1):
        iterations = iteration
        response: LLMResponse = llm.complete(
            messages, tools=TOOL_SCHEMAS, temperature=settings.temperature
        )
        usage = usage + response.usage
        model = response.model or model

        if response.tool_calls:
            # The assistant turn *with* tool_calls must go into history before
            # the matching tool results - order matters to every provider.
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [call.model_dump(mode="json") for call in response.tool_calls],
                }
            )
            for call in response.tool_calls:
                record = execute_tool(call.name, call.arguments, catalog, tool_call_id=call.id)
                records.append(record)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": _tool_content(record, settings.max_tool_output_chars),
                    }
                )
            continue

        if response.content:
            answer = response.content
            stop_reason = "final"
        else:
            answer = None
            stop_reason = "no_content"
        break

    if answer is None:
        answer = _fallback_answer(records)
        if stop_reason == "no_content":
            answer = "I don't have enough information to answer that. Could you rephrase?"

    return AssistantResponse(
        answer=answer,
        products=collect_products(records),
        order_status=collect_order_status(records),
        tool_calls=records,
        model=model,
        usage=usage,
        iterations=iterations,
        stop_reason=stop_reason,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Streaming loop
# --------------------------------------------------------------------------- #


class _EventCounter:
    """Monotonic ``seq`` for stream events (clients use it to spot gaps)."""

    def __init__(self) -> None:
        self._value = 0

    def next(self, event: str, data: dict[str, Any]) -> StreamEvent:
        event_model = StreamEvent(event=event, seq=self._value, data=data)  # type: ignore[arg-type]
        self._value += 1
        return event_model


def stream_agent(
    request: AssistantRequest,
    catalog: Catalog,
    llm: LLMClient,
    settings: Settings,
) -> Iterator[StreamEvent]:
    """Same loop as :func:`run_agent`, but yielding events as work happens.

    Event order for a tool-using question::

        start -> tool_call -> token ... -> final

    The final event carries the identical ``AssistantResponse`` payload that
    ``POST /assistant`` would have returned, so a streaming client never has to
    re-request the structured result.  A failure *after* the first byte cannot
    change the HTTP status any more, so it is delivered as an ``error`` event.
    """
    counter = _EventCounter()
    budget = request.max_iterations or settings.max_iterations
    messages = build_messages(request)
    records: list[ToolCallRecord] = []
    usage = Usage()
    model = getattr(llm, "model", llm.name)

    yield counter.next(
        "start",
        {
            "model": model,
            "max_iterations": budget,
            "message": request.message,
        },
    )

    answer: str | None = None
    stop_reason = "max_iterations"
    iterations = 0

    try:
        for iteration in range(1, budget + 1):
            iterations = iteration
            parts: list[str] = []
            tool_calls = []

            for delta in llm.stream(messages, tools=TOOL_SCHEMAS, temperature=settings.temperature):
                if delta.text:
                    parts.append(delta.text)
                    yield counter.next("token", {"text": delta.text})
                if delta.tool_calls:
                    tool_calls = delta.tool_calls
                if delta.usage is not None:
                    usage = usage + delta.usage

            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": "".join(parts),
                        "tool_calls": [call.model_dump(mode="json") for call in tool_calls],
                    }
                )
                for call in tool_calls:
                    record = execute_tool(call.name, call.arguments, catalog, tool_call_id=call.id)
                    records.append(record)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "name": call.name,
                            "content": _tool_content(record, settings.max_tool_output_chars),
                        }
                    )
                    yield counter.next(
                        "tool_call",
                        {
                            "tool_call_id": record.tool_call_id,
                            "name": record.name,
                            "arguments": record.arguments,
                            "ok": record.ok,
                            "error": record.error,
                            "duration_ms": record.duration_ms,
                        },
                    )
                continue

            if "".join(parts):
                answer = "".join(parts)
                stop_reason = "final"
            else:
                stop_reason = "no_content"
            break
    except Exception as exc:  # mid-stream failure: report, do not pretend
        yield counter.next("error", {"message": str(exc), "type": type(exc).__name__})
        return

    if answer is None:
        if stop_reason == "no_content":
            answer = "I don't have enough information to answer that. Could you rephrase?"
        else:
            answer = _fallback_answer(records)

    final = AssistantResponse(
        answer=answer,
        products=collect_products(records),
        order_status=collect_order_status(records),
        tool_calls=records,
        model=model,
        usage=usage,
        iterations=iterations,
        stop_reason=stop_reason,  # type: ignore[arg-type]
    )
    yield counter.next("final", final.model_dump(mode="json"))

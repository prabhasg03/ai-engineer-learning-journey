"""LLM clients behind one tiny protocol (topics 12, 14, 17, 19).

The agent loop must not care which model answers, so both clients implement
the same two methods::

    complete(messages, tools) -> LLMResponse     # one full answer
    stream(messages, tools)   -> Iterator[LLMDelta]  # incremental answer

Two implementations:

**MockLLM** - deterministic, offline, and the default.  It either plays back a
``script`` (what the tests use, so a test can force an unknown tool or a
hallucinated argument) or heuristically *plans* a tool call from the shopper's
message and then summarises the tool results.  It never calls a network, so the
suite is reproducible on any machine - this is the LLM-specific testing
decision that makes the whole project testable.

**OpenAICompatibleLLM** - the live path.  It is plain ``httpx`` against
``{base_url}/chat/completions``, and **every** outbound call is wrapped in
``app.retry.retry_call``.  Two LLM-specific cautions are baked in:

* non-streaming calls are retried freely because they are all-or-nothing;
* streaming calls retry only the *handshake*.  Once the first token has been
  flushed to the client you cannot rewind it, so a mid-stream failure is
  surfaced as an error event instead of a silent re-run (topic 14).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol, runtime_checkable

from .config import Settings
from .models import ToolCall, Usage
from .retry import ApiError, ErrorKind, RetryPolicy, retry_call

__all__ = [
    "LLMClient",
    "LLMDelta",
    "LLMError",
    "LLMResponse",
    "MockLLM",
    "MockTurn",
    "OpenAICompatibleLLM",
    "build_llm",
    "sse_payload",
]


# --------------------------------------------------------------------------- #
# Wire types
# --------------------------------------------------------------------------- #


class LLMError(RuntimeError):
    """Raised when an outbound LLM call fails after its retry budget."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 1,
        kind: ErrorKind | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind


@dataclass
class LLMResponse:
    """One complete model turn."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str | None = None
    attempts: int = 1


@dataclass
class LLMDelta:
    """One increment of a streamed model turn.

    ``tool_calls`` is only populated on the final delta of the stream - tool
    arguments arrive as fragments and cannot be executed until the arguments
    string is complete.
    """

    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    usage: Usage | None = None
    done: bool = False


@runtime_checkable
class LLMClient(Protocol):
    """The only interface the agent loop knows about."""

    name: str

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse: ...

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> Iterator[LLMDelta]: ...


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def estimate_tokens(text: str) -> int:
    """Cheap token estimate (~4 characters per token).

    Only ever used by the mock and as a last-resort fallback, so a heuristic is
    honest here; the real path uses the provider's ``usage`` block.
    """
    return max(1, len(text) // 4)


def _messages_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            parts.extend(json.dumps(call) for call in calls)
    return "\n".join(parts)


def sse_payload(line: str) -> str | None:
    """Extract the ``data:`` payload from one Server-Sent Event line.

    Returns ``None`` for blank lines, comments (``:heartbeat``) and any line
    that is not a ``data:`` field.  ``"[DONE]"`` is returned verbatim so the
    caller can distinguish the terminator from a JSON chunk.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    return stripped[len("data:") :].strip()


# --------------------------------------------------------------------------- #
# MockLLM - deterministic, offline
# --------------------------------------------------------------------------- #


@dataclass
class MockTurn:
    """A canned model turn: either some text, or a set of tool requests."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


#: Words stripped from a shopper's message before it becomes a search query.
_QUERY_NOISE = frozenset(
    """
    a an the do does did you your i me my we our is are was were be been
    have has had any some of for to with and or in on at from that this these
    find show give list search looking look want need buy get please product
    products item items thing things under below less than cheaper about
    around max maximum up over stock inventory available availability
    """.split()
)

_PRICE_RE = re.compile(
    r"(?:under|below|less than|cheaper than|max|maximum|up to|around)\s*\$?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ORDER_RE = re.compile(r"\bORD-\d{4}\b", re.IGNORECASE)
_SKU_RE = re.compile(r"\bSKU-\d{3}\b", re.IGNORECASE)


def _extract_query(text: str) -> str:
    """Turn a shopper's sentence into search terms.

    Price phrases are removed first: ``max_price`` is extracted separately, and
    leaving ``150`` in the query would make the search look for a product whose
    text contains the number.
    """
    without_prices = _PRICE_RE.sub(" ", text)
    without_prices = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", without_prices)
    cleaned = "".join(ch if ch.isalnum() else " " for ch in without_prices.lower())
    tokens = [tok for tok in cleaned.split() if len(tok) > 1 and tok not in _QUERY_NOISE]
    return " ".join(tokens) or "products"


class MockLLM:
    """A deterministic stand-in for a chat model.

    * With a ``script`` it plays the turns back in order - the tests use this
      to force parallel calls, unknown tools and bad arguments.
    * Without one it *plans*: an order id means ``get_order_status``, a SKU plus
      a stock question means ``check_inventory``, anything else means
      ``search_products`` - then it summarises whatever the tools returned.
    """

    name = "mock-llm"

    def __init__(
        self,
        script: list[MockTurn] | None = None,
        model: str = "mock-shopping-llm",
        chunk_size: int = 16,
    ) -> None:
        self._script: list[MockTurn] = list(script or [])
        self._cursor = 0
        self.model = model
        self.chunk_size = max(1, chunk_size)

    # -- script handling --------------------------------------------------- #

    def reset(self) -> None:
        """Rewind the script so the same client can be reused."""
        self._cursor = 0

    @property
    def script_remaining(self) -> int:
        return max(0, len(self._script) - self._cursor)

    def _next_turn(self, messages: list[dict[str, Any]]) -> MockTurn:
        if self._cursor < len(self._script):
            turn = self._script[self._cursor]
            self._cursor += 1
            return turn
        return self._plan(messages)

    # -- the heuristic planner --------------------------------------------- #

    def _plan(self, messages: list[dict[str, Any]]) -> MockTurn:
        tool_results: list[dict[str, Any]] = []
        for message in messages:
            if message.get("role") != "tool":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                tool_results.append(decoded)

        if tool_results:
            return MockTurn(content=_compose_answer(tool_results))

        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                user_text = message["content"]
                break

        turn_index = 1 + sum(
            1
            for m in messages
            if m.get("role") == "assistant" and m.get("tool_calls")
        )
        calls: list[ToolCall] = []

        def _call(name: str, arguments: dict[str, Any]) -> ToolCall:
            return ToolCall(
                id=f"call_{turn_index}_{len(calls) + 1}",
                name=name,
                arguments=arguments,
            )

        lower = user_text.lower()
        order_ids = _ORDER_RE.findall(user_text)
        skus = _SKU_RE.findall(user_text)
        asks_inventory = any(
            word in lower for word in ("stock", "inventory", "available", "how many")
        )

        if order_ids:
            calls.append(_call("get_order_status", {"order_id": order_ids[0].upper()}))
        if skus and asks_inventory:
            calls.append(_call("check_inventory", {"sku": skus[0].upper()}))
        if not calls and skus:
            # A bare SKU still deserves an inventory answer.
            calls.append(_call("check_inventory", {"sku": skus[0].upper()}))
        if not calls:
            arguments: dict[str, Any] = {"query": _extract_query(user_text), "limit": 5}
            price = _PRICE_RE.search(user_text)
            if price:
                arguments["max_price"] = float(price.group(1))
            calls.append(_call("search_products", arguments))

        return MockTurn(tool_calls=calls)

    # -- the protocol ------------------------------------------------------ #

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        turn = self._next_turn(messages)
        return LLMResponse(
            content=turn.content,
            tool_calls=turn.tool_calls,
            usage=Usage(
                prompt_tokens=estimate_tokens(_messages_text(messages)),
                completion_tokens=estimate_tokens(turn.content or ""),
            ),
            model=self.model,
            finish_reason="tool_calls" if turn.tool_calls else "stop",
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> Iterator[LLMDelta]:
        turn = self._next_turn(messages)
        usage = Usage(
            prompt_tokens=estimate_tokens(_messages_text(messages)),
            completion_tokens=estimate_tokens(turn.content or ""),
        )
        if turn.tool_calls:
            yield LLMDelta(tool_calls=turn.tool_calls, done=True, usage=usage)
            return
        text = turn.content or ""
        for start in range(0, len(text), self.chunk_size):
            yield LLMDelta(text=text[start : start + self.chunk_size])
        yield LLMDelta(done=True, usage=usage)


def _compose_answer(tool_results: list[dict[str, Any]]) -> str:
    """Turn raw tool payloads into a short shopper-facing answer."""
    parts: list[str] = []
    for result in tool_results:
        if "products" in result:
            products = result.get("products") or []
            if products:
                listing = ", ".join(
                    f"{p['name']} ({p['sku']}) at ${float(p['price']):.2f}" for p in products
                )
                parts.append(f"I found {result.get('count', len(products))} matching product(s): {listing}.")
            else:
                parts.append("I couldn't find any products matching that request.")
        elif "order" in result:
            order = result["order"]
            sentence = f"Order {order['order_id']} is {order['status']}"
            if order.get("eta"):
                sentence += f" and is estimated to arrive on {order['eta']}"
            if order.get("carrier"):
                sentence += f" via {order['carrier']}"
            sentence += (
                f". It contains {len(order.get('lines', []))} line(s) "
                f"totalling ${float(order.get('total', 0)):.2f}."
            )
            parts.append(sentence)
        elif result.get("found") is False:
            parts.append(str(result.get("message", "I couldn't find that.")))
        elif "available" in result or "quantity" in result:
            parts.append(
                str(
                    result.get("message")
                    or f"{result.get('sku')} has {result.get('available')} available."
                )
            )
        elif "error" in result:
            parts.append(f"I couldn't complete one lookup: {result.get('message', result['error'])}.")
    return " ".join(parts) or "I couldn't find anything to help with that."


# --------------------------------------------------------------------------- #
# OpenAICompatibleLLM - the live path, retry-wrapped
# --------------------------------------------------------------------------- #


class OpenAICompatibleLLM:
    """A minimal, hand-written client for ``/v1/chat/completions``.

    Deliberately not an SDK: the request body, the SSE parsing and the retry
    placement are all visible, and ``client`` can be injected (tests pass an
    ``httpx.MockTransport``-backed client to exercise the retry path offline).
    """

    name = "openai-compatible"

    def __init__(self, settings: Settings, client: Any = None) -> None:
        import httpx

        self._settings = settings
        self._client = client if client is not None else httpx.Client(timeout=settings.llm_timeout_s)
        self._policy: RetryPolicy = settings.retry
        self.model = settings.llm_model

    # -- request shaping --------------------------------------------------- #

    def _url(self) -> str:
        return self._settings.llm_base_url.rstrip("/") + "/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.llm_api_key}",
        }

    def _payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        temperature: float,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if stream:
            # Ask the server to include usage in the final chunk; not every
            # server supports it, which is why the parser tolerates its absence.
            payload["stream_options"] = {"include_usage": True}
        return payload

    # -- non-streaming ----------------------------------------------------- #

    def _post(self, payload: dict[str, Any]) -> Any:
        response = self._client.post(
            self._url(),
            json=payload,
            headers=self._headers(),
            timeout=self._settings.llm_timeout_s,
        )
        if response.status_code >= 400:
            # Our own error type keeps the retry classifier simple and makes the
            # Retry-After header available to it.
            raise ApiError(
                response.status_code,
                response.text[:500],
                headers=dict(response.headers),
            )
        return response

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        payload = self._payload(messages, tools, stream=False, temperature=temperature)
        outcome = retry_call(lambda: self._post(payload), policy=self._policy)
        if not outcome.ok:
            raise LLMError(
                f"LLM request failed after {outcome.attempts} attempt(s): {outcome.error}",
                attempts=outcome.attempts,
                kind=outcome.kind,
            )
        response = outcome.value
        try:
            data = response.json()
        except Exception as exc:  # malformed body from the server
            raise LLMError(f"LLM returned a non-JSON body: {exc}") from exc
        return self._parse_response(data, attempts=outcome.attempts)

    def _parse_response(self, data: dict[str, Any], attempts: int = 1) -> LLMResponse:
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else None) or {}
        return LLMResponse(
            content=message.get("content"),
            tool_calls=[_tool_call_from_wire(tc) for tc in (message.get("tool_calls") or [])],
            usage=_usage_from(data.get("usage")),
            model=data.get("model") or self._settings.llm_model,
            finish_reason=(choices[0].get("finish_reason") if choices else None),
            attempts=attempts,
        )

    # -- streaming --------------------------------------------------------- #

    def _open_stream(self, payload: dict[str, Any]) -> tuple[Any, Any]:
        """Open the stream and check the status *before* yielding anything.

        This is the retryable part: a connection that fails here has not sent a
        single token to our client yet, so re-running it is safe.
        """
        manager = self._client.stream(
            "POST",
            self._url(),
            json=payload,
            headers=self._headers(),
            timeout=self._settings.llm_timeout_s,
        )
        response = manager.__enter__()
        if response.status_code >= 400:
            body = b""
            try:
                body = response.read()
            except Exception:
                pass
            headers = dict(response.headers)
            manager.__exit__(None, None, None)
            raise ApiError(
                response.status_code,
                body.decode("utf-8", "replace")[:500] if body else "",
                headers=headers,
            )
        return manager, response

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
    ) -> Iterator[LLMDelta]:
        payload = self._payload(messages, tools, stream=True, temperature=temperature)
        outcome = retry_call(lambda: self._open_stream(payload), policy=self._policy)
        if not outcome.ok:
            raise LLMError(
                f"LLM stream failed to start after {outcome.attempts} attempt(s): {outcome.error}",
                attempts=outcome.attempts,
                kind=outcome.kind,
            )
        manager, response = outcome.value

        fragments: dict[int, dict[str, Any]] = {}
        usage: Usage | None = None
        try:
            for line in response.iter_lines():
                payload_text = sse_payload(line)
                if payload_text is None:
                    continue
                if payload_text == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                if chunk.get("usage"):
                    usage = _usage_from(chunk["usage"])
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield LLMDelta(text=text)
                for fragment in delta.get("tool_calls") or []:
                    _accumulate_fragment(fragments, fragment)
        finally:
            manager.__exit__(None, None, None)

        calls = _assemble_tool_calls(fragments)
        yield LLMDelta(tool_calls=calls or None, usage=usage, done=True)

    # -- availability ------------------------------------------------------ #

    def health_check(self, timeout: float = 2.0) -> bool:
        """True when the endpoint answers ``GET /models``.

        Used to *skip the live path* instead of failing noisily when there is no
        server running - the default deployment is the mock.
        """
        url = self._settings.llm_base_url.rstrip("/") + "/models"
        policy = RetryPolicy(max_attempts=1, max_elapsed=None)

        def _probe() -> bool:
            response = self._client.get(url, headers=self._headers(), timeout=timeout)
            if response.status_code >= 400:
                raise ApiError(response.status_code, "health probe failed")
            return True

        return retry_call(_probe, policy=policy).ok


def _usage_from(raw: Any) -> Usage:
    """Map an OpenAI-shaped ``usage`` block onto our model (tolerant of gaps)."""
    if not isinstance(raw, dict):
        return Usage()
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
    )


def _tool_call_from_wire(raw: dict[str, Any]) -> ToolCall:
    """Decode one non-streamed ``tool_calls[]`` entry."""
    function = raw.get("function") or {}
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            decoded = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            decoded = {"__invalid_json__": arguments[:200]}
    elif isinstance(arguments, dict):
        decoded = arguments
    else:
        decoded = {}
    return ToolCall(
        id=str(raw.get("id") or "call_unknown"),
        name=str(function.get("name") or ""),
        arguments=decoded if isinstance(decoded, dict) else {},
    )


def _accumulate_fragment(fragments: dict[int, dict[str, Any]], fragment: dict[str, Any]) -> None:
    """Merge one streamed tool-call delta into the in-progress call.

    Streamed tool calls arrive as fragments keyed by ``index``; ``arguments`` is
    a JSON string that is only valid once the last fragment has landed.
    """
    index = int(fragment.get("index") or 0)
    slot = fragments.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if fragment.get("id"):
        slot["id"] = fragment["id"]
    function = fragment.get("function") or {}
    if function.get("name"):
        slot["name"] = function["name"]
    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _assemble_tool_calls(fragments: dict[int, dict[str, Any]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index in sorted(fragments):
        slot = fragments[index]
        raw_args = slot.get("arguments") or ""
        try:
            decoded = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            decoded = {"__invalid_json__": raw_args[:200]}
        calls.append(
            ToolCall(
                id=slot.get("id") or f"call_{index}",
                name=slot.get("name") or "",
                arguments=decoded if isinstance(decoded, dict) else {},
            )
        )
    return calls


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #


def build_llm(settings: Settings, client: Any = None) -> LLMClient:
    """Return the mock (default) or the live client, from settings.

    ``use_mock_llm`` defaults to ``True`` so the service is useful without any
    external dependency.  Set ``SHOPPING_USE_MOCK_LLM=0`` to talk to a real
    OpenAI-compatible server.
    """
    if settings.use_mock_llm:
        return MockLLM(model="mock-shopping-llm")
    return OpenAICompatibleLLM(settings, client=client)

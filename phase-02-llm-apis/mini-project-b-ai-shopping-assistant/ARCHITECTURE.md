# ARCHITECTURE — AI Shopping Assistant

How a request travels through the service, what the structured-output contract guarantees, where
retries live, and how the stream is produced.

---

## 1. Component map

```text
                        client (curl / browser / your app)
                                   │
        POST /assistant            │            POST /assistant/stream
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ app/main.py — FastAPI                                                    │
│  typed routes · response_model · Depends(get_store) · Depends(get_llm)    │
└──────────────────────────────────────────────────────────────────────────┘
                                   │  AssistantRequest (Pydantic-validated)
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ app/agent.py — the hand-written loop                                     │
│  build_messages → [messages, TOOL_SCHEMAS] → model → execute → repeat     │
│  run_agent()  : one AssistantResponse                                    │
│  stream_agent(): Iterator[StreamEvent]                                    │
└───────────────┬────────────────────────────────┬─────────────────────────┘
                │ complete()/stream()            │ execute_tool(name, args)
                ▼                                ▼
┌───────────────────────────────┐  ┌──────────────────────────────────────┐
│ app/llm.py — LLMClient        │  │ app/tools.py — trust boundary        │
│  MockLLM            (default) │  │  ARG_MODELS validate the arguments   │
│  OpenAICompatibleLLM  (live)  │  │  HANDLERS run against the catalogue  │
└───────────────┬───────────────┘  └────────────────┬─────────────────────┘
                │ every outbound call              │ reads
                ▼                                  ▼
┌───────────────────────────────┐  ┌──────────────────────────────────────┐
│ app/retry.py — retry_call     │  │ app/catalog.py — the system of record│
│  classify → backoff+jitter →  │  │  products · inventory · orders       │
│  honour Retry-After → sleep   │  │  (deterministic seed data)           │
└───────────────────────────────┘  └──────────────────────────────────────┘
                                   ▲
                                   │ app/models.py — the shared vocabulary
```

`app/models.py` has no arrows pointing out of it: it is the vocabulary every other module
agrees on, and nothing in it performs IO.

---

## 2. Request flow

### 2.1 From HTTP to a validated request

1. **FastAPI receives the body** and validates it against `AssistantRequest`
   (`message` 1–2000 chars, `conversation` ≤ 24 turns of `user`/`assistant`, `max_iterations`
   1–8). A bad body is rejected with `422` before any of our code runs — the contract fails at
   the boundary, which is the whole point of topic 11.
2. **Dependencies resolve.** `get_store` returns the process-shared read-only `Catalog`;
   `get_llm` returns the process-shared client, which is `MockLLM` unless
   `SHOPPING_USE_MOCK_LLM=0`.
3. **Settings resolve** from the cached `get_settings()` (`app/config.py`).

### 2.2 The agent loop (`run_agent`)

```text
messages = [system] + conversation + [user]          # rebuilt every call (stateless)
for iteration in 1..budget:                           # budget = request.max_iterations or settings
    response = llm.complete(messages, tools=TOOL_SCHEMAS, temperature=0.2)
    usage   += response.usage
    if response.tool_calls:                           # the model asked, it did not run anything
        append assistant turn WITH tool_calls
        for each requested call:
            record = execute_tool(name, raw_arguments, catalog, tool_call_id)
            append {"role":"tool", "tool_call_id":..., "content": json(record)}
        continue
    if response.content:  answer = content; stop_reason = "final"; break
    else:                 stop_reason = "no_content"; break
# loop exhausted without an answer -> _fallback_answer(records), stop_reason = "max_iterations"
```

Three details matter:

- **The model never executes anything** (topic 17). It returns *requests*; `execute_tool` is the
  only code that touches the catalogue. The assistant turn carrying `tool_calls` is appended
  **before** its matching `tool` messages, because that ordering is what every provider expects.
- **Widget-free termination.** The loop stops on a final answer, on an empty answer, or on the
  iteration budget — and `stop_reason` records which. A degraded answer is still a valid
  `AssistantResponse`; the failure is visible rather than thrown.
- **Usage is summed across iterations** (`Usage.__add__`), because one HTTP request can be three
  model round trips and the caller is paying for all of them.

### 2.3 Result assembly

After the loop the agent builds one `AssistantResponse` from the *tool-call records*, not from
the prose:

| Field | Source |
|---|---|
| `answer` | the model's final text (or the fallback) |
| `products` | every successful `search_products` payload, re-validated as `Product`, deduplicated by SKU |
| `order_status` | the last successful `get_order_status` payload, re-validated as `OrderStatus` |
| `tool_calls` | the audit record of every call, successful or not |
| `model`, `usage`, `iterations`, `stop_reason` | loop bookkeeping |

The structured fields are therefore **grounded in tool output**: if a tool did not return a
product, no product appears in the response. That is the cheapest anti-hallucination control in
the whole project.

---

## 3. The structured-output contract

### 3.1 Three boundaries, one vocabulary

| Boundary | In | Out | Enforced by |
|---|---|---|---|
| HTTP | `AssistantRequest` | `AssistantResponse`, `Product`, `OrderStatus`, `HealthResponse` | FastAPI + `response_model` |
| LLM | message list + `TOOL_SCHEMAS` | `ToolCall`, `Usage` | `_parse_response` / stream assembly, then `ToolCall` |
| Tools | `dict | str` raw arguments | JSON payload | `SearchProductsArgs` / `CheckInventoryArgs` / `GetOrderStatusArgs` |

### 3.2 Why the answer is a model, not "please reply in JSON" (topic 12)

The service never asks the model for JSON. It asks for a **tool call** (a structured request), and
the *service* composes the JSON response from the tool output it already holds. A model that
writes invalid prose cannot corrupt `products` or `order_status`, because those fields are never
copied out of prose.

Where the model *does* produce structured data — tool arguments — it is validated before use:

```text
raw arguments (JSON string / object)
        │
        ▼  _coerce_arguments()      decode a JSON string, one nested decode for double-encoding
        ▼  ARG_MODELS[name].model_validate()
        ├── ok ─────────────► HANDLERS[name](args, catalog)
        └── ValidationError ► {"error": "invalid_arguments", "message": "<field> <problem>"}
```

The failure is returned to the model as an ordinary tool result, so it can correct itself on the
next iteration. Note the deliberate leniency: Pydantic coerces `"19.99" → 19.99` and `"3" → 3`, and
`mode="before"` validators normalise `sku-001 → SKU-001`. Repairing a sloppy argument is cheaper
than another round trip; rejecting a *wrong* one (missing `query`, `limit=99`) still happens.

### 3.3 Derived fields

`available`, `in_stock`, `line_total` and `total` are `computed_field`s. They cannot be sent by a
client and cannot disagree with the stored numbers — an inconsistency that would otherwise be a
classic source of support tickets.

---

## 4. Retry and backoff placement (topic 19)

### 4.1 Where it sits

```text
OpenAICompatibleLLM.complete()
        └── retry_call(lambda: self._post(payload), policy=settings.retry)   ← retried
                     └── httpx POST /chat/completions
OpenAICompatibleLLM.stream()
        └── retry_call(lambda: self._open_stream(payload), policy=...)       ← retried (handshake only)
                     └── httpx stream POST  → SSE iteration                ← NOT retried
```

Everything that leaves the process goes through `retry_call`. The catalogue and the tool
handlers are in-process and side-effect free, so they are not retried — retrying them would add
latency and prove nothing.

The non-streaming path is retried wholesale because it is all-or-nothing. The streaming path is
retried **only** until the response headers arrive: once bytes have been yielded to the client you
cannot rewind them, so a mid-stream failure becomes an `error` event (topic 14).

`OpenAICompatibleLLM.health_check()` probes `GET {base_url}/models` with a single attempt and no
retries. It exists so a caller (or a test suite) can *skip* the live path when no server is
running, instead of failing noisily — the mock is the default precisely so that path is optional.

### 4.2 The policy

| Knob | Default | Meaning |
|---|---|---|
| `max_attempts` | 3 | total tries (1 initial + 2 retries) |
| `base` | 0.5 s | first backoff |
| `multiplier` | 2.0 | exponential growth |
| `max_delay` | 8 s | ceiling for any single sleep, including `Retry-After` |
| `jitter` | `full` | `uniform(0, delay)` — spreads a thundering herd |
| `max_elapsed` | 20 s | total sleep budget; the interactive latency guard |

Delay for failure *n*: `min(base · multiplier^(n-1), max_delay)`, then jittered. A `Retry-After`
header overrides the computed delay (capped at `max_delay`), because the server knows better than
our jitter how long it needs.

### 4.3 Which errors are retried

| Class | Examples | Retried |
|---|---|---|
| rate limit | 429 | yes (usually with `Retry-After`) |
| overload | 529 | yes |
| server | 500/502/503/504 | yes |
| timeout | 408, connect/read timeout | yes |
| network | connection reset, DNS, refused | yes |
| client (permanent) | 400/401/403/404/422 | **no** |

Retrying a 401 cannot succeed and retrying a 400 repeats a request we know is malformed. The
classifier is duck-typed (`status_code`, `.response.status_code`, `str(exc)`), so `app/retry.py`
imports nothing from the HTTP library and can be unit-tested with `ApiError`.

### 4.4 Why the tests do not sleep

`retry_call` takes `clock`, `rng` and `sleep` as parameters. Production passes `SystemClock` and
the `random` module; the tests pass `FakeClock`, `FakeRng([...])` and read `outcome.delays`
directly. The retry tests assert the exact schedule (`[1.0, 2.0]`) instead of waiting for it, and
the live-client tests set `base=0.0` so the real path is exercised without real time passing.

---

## 5. Streaming design (topic 14)

### 5.1 The wire format

`POST /assistant/stream` returns `text/event-stream`. One `StreamEvent` (`app/models.py`) becomes
one SSE frame:

```text
event: token
data: {"text":"5 unit(s) availa","seq":2}
                        ▲
                        └── one SSE frame = event name + JSON payload + blank line
```

| Event | Payload | When |
|---|---|---|
| `start` | model, budget, echo of the message | first, always |
| `tool_call` | name, arguments, ok, error, duration | after each executed tool |
| `token` | `{"text": "..."}` | as the final answer is generated |
| `final` | the complete `AssistantResponse` | last, on success |
| `error` | message + exception type | instead of `final` if the run fails after the first byte |

`seq` is a monotonic counter, so a client can detect a dropped frame.

### 5.2 Producing it

```text
stream_agent()
  yield start
  for iteration in 1..budget:
      for delta in llm.stream(messages, tools):        # text deltas yielded immediately
          if delta.text:  yield token
          if delta.tool_calls: remember them           # assembled fragments arrive last
      if tool_calls: execute each, yield tool_call, continue
      else: answer = joined text; break
  yield final(AssistantResponse)
```

The loop still runs the tool-call protocol: tool turns produce `tool_call` events and no tokens;
the final turn produces tokens and no tool calls. The `final` event carries **the same**
`AssistantResponse` that `POST /assistant` would return, so a streaming client never has to make a
second request to get the structured data.

On the client side, concatenating every `token` event's `text` reproduces `final["answer"]`
exactly — which is precisely what `tests/test_api.py` asserts, and what `tests/test_agent.py`
asserts against the structured path.

### 5.3 Two deliberate choices

**Sync generators, not async.** FastAPI routes here are `def`, so Starlette runs them in a
threadpool, and the `StreamingResponse` iterates a *synchronous* generator. That lets the same
synchronous `retry_call` wrap the LLM call and the same `httpx` client be reused, without an
`asyncio` layer that would add nothing to an IO-bound call chain that is already off the event
loop. (Topic 13's async model is why this is safe to state rather than assume.)

**Mid-stream errors cannot change the status code.** Once the first frame is flushed the response
is `200`. Rather than hide that, the generator catches the failure and yields an `error` event;
the client sees a partial answer *and* knows it is partial.

### 5.4 The provider side

`OpenAICompatibleLLM.stream` sends `stream: true` (plus `stream_options.include_usage` where
supported) and parses `data:` lines:

- `data: [DONE]` terminates;
- `choices[0].delta.content` becomes an `LLMDelta.text`;
- `choices[0].delta.tool_calls[]` fragments are accumulated **by index** — `arguments` is a JSON
  string that is only valid once the last fragment has landed — and the assembled `ToolCall`s are
  emitted on the final delta.

That last point is the "streaming + tool calls" complication from topic 14, handled explicitly
rather than assumed.

---

## 6. Testing seams

The design is shaped by the need for a deterministic, offline suite:

| Seam | Production | Test |
|---|---|---|
| Model | `OpenAICompatibleLLM` | `MockLLM` (heuristic or scripted) |
| HTTP | real socket | `httpx.MockTransport` injected into the client |
| Time / randomness | `SystemClock`, `random` | `FakeClock`, `FakeRng` |
| Catalogue | process-shared singleton | fresh `build_catalog()` per test via `dependency_overrides` |
| Settings | `get_settings()` from env | `Settings(...)` built inline |

No test opens a socket, needs an API key, or sleeps. That is what lets the "runs on a fresh
machine from the README alone" requirement hold.

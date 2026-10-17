# Mini-project B — AI Shopping Assistant

A typed FastAPI service that answers shopping questions by **calling tools over a
product catalogue**: product search, inventory, and order status. It returns a
**structured** answer, it **streams** its response token by token, it wraps every
outbound call in a **hand-written retry with exponential backoff and jitter**, and
it runs with **no API key and no network** out of the box thanks to a deterministic
mock model.

Phase 2 capstone (topics 11–21) of the AI-engineering curriculum. Hand-written
throughout: no LangChain, no LiteLLM, no provider SDK, no agent framework.

---

## What it is

- A small in-memory shop (12 products, stock per SKU, 5 orders) in `app/catalog.py`.
- **Three tools** the model may request: `search_products`, `check_inventory`, `get_order_status`.
- A **hand-written tool-call loop** (`app/agent.py`): send messages + tool schemas → execute the
  requested tools → feed the results back → repeat until a final answer, bounded by an
  iteration budget.
- A **structured response** (`app/models.py`): prose answer plus the products found, the order
  status, an audit record of every tool call, the model name and the token usage.
- **Retries with backoff + jitter** (`app/retry.py`) around every outbound call, honouring
  `Retry-After`.
- A **streaming endpoint** (`text/event-stream`) that emits tool-call events and answer tokens
  as they happen, and ends with the same structured result.

By default the "model" is a deterministic `MockLLM`, so the service and the whole test suite
work offline. Point it at any OpenAI-compatible server to use a real model — see
[Using a real model](#using-a-real-model).

---

## Prerequisites

- **Python 3.12** (the project targets 3.12; 3.11+ should work).
- `pip` (bundled with Python).
- Windows, macOS or Linux. The `.bat` helpers are Windows-only; the commands below are
  cross-platform.
- No API key, no model server and no database are required for the default mock mode.

Check your interpreter:

```bat
python --version
:: expected: Python 3.12.x
```

---

## Install on a fresh machine

From the repository root:

```bat
cd phase-02-llm-apis\mini-project-b-ai-shopping-assistant

python -m venv .venv

:: Windows cmd.exe
.venv\Scripts\activate.bat
:: Windows PowerShell instead:
::   .venv\Scripts\Activate.ps1
:: macOS / Linux instead:
::   source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` installs `fastapi`, `uvicorn[standard]`, `pydantic`, `httpx` (used by the
live model client and by the tests) and `pytest`.

---

## Run the server

With the virtual environment active, from the project folder:

```bat
python -m uvicorn app.main:app --reload
```

Or double-click / run **`run.bat`**, which does the same thing, creating and populating the
virtual environment first if it does not exist yet.

Then open:

| URL | What it is |
|---|---|
| <http://127.0.0.1:8000/docs> | Swagger UI — try every endpoint from the browser |
| <http://127.0.0.1:8000/redoc> | ReDoc reference |
| <http://127.0.0.1:8000/openapi.json> | Machine-readable schema |
| <http://127.0.0.1:8000/health> | Liveness and current model mode |

Stop the server with **CTRL+C**.

---

## Run the tests

```bat
python -m pytest -q
```

Or double-click / run **`click-to-run.bat`**.

The suite is **offline and deterministic**: no network, no API key, no live model. It swaps in a
fresh catalogue and a scripted `MockLLM` for every test. Expected: all tests pass in under a
second.

---

## HTTP endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | status, version, active model, `use_mock_llm`, product count |
| `GET` | `/products` | list of products; query params `q`, `max_price`, `tag` (repeatable), `limit` |
| `GET` | `/products/{sku}` | one product, or `404` |
| `GET` | `/orders/{order_id}` | one order with lines and total, or `404` |
| `POST` | `/assistant` | `AssistantResponse` — the structured answer |
| `POST` | `/assistant/stream` | `text/event-stream`: `start`, `tool_call`, `token` … events, then `final` |

Every response is validated by a Pydantic `response_model`; bad request bodies get `422`
automatically.

### curl examples

On Windows use `curl.exe` (the real curl, not the PowerShell alias) and run these from
`cmd.exe`. On macOS/Linux/macOS just use `curl`.

```bat
:: health
curl.exe http://127.0.0.1:8000/health

:: catalogue search: audio products at 100.00 or less
curl.exe "http://127.0.0.1:8000/products?tag=audio&max_price=100"

:: free-text search, 3 rows at most
curl.exe "http://127.0.0.1:8000/products?q=mechanical+keyboard&limit=3"

:: one product / one order
curl.exe http://127.0.0.1:8000/products/SKU-001
curl.exe http://127.0.0.1:8000/orders/ORD-1001

:: structured assistant answer
curl.exe -X POST http://127.0.0.1:8000/assistant ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"show me some headphones under $150\"}"

:: streaming answer (curl.exe -N disables buffering so you see the events as they arrive)
curl.exe -N -X POST http://127.0.0.1:8000/assistant/stream ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"do you have SKU-003 in stock?\"}"
```

PowerShell equivalents (single quotes stop `$150` being treated as a variable):

```powershell
curl.exe http://127.0.0.1:8000/health

$body = '{"message": "show me some headphones under $150"}'
Invoke-RestMethod -Uri http://127.0.0.1:8000/assistant -Method Post `
  -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 6
```

### Request body for the assistant endpoints

```json
{
  "message": "show me some headphones under $150",
  "conversation": [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "Hello! What are you shopping for?"}
  ],
  "max_iterations": 4
}
```

`conversation` (optional) carries prior turns, because the API is stateless: the client resends
the history on every call. `max_iterations` (optional, 1–8) overrides the tool-call budget.

---

## Example shopping conversation

All three examples below are real output from the default mock model.

**1. A product search** — one tool call, a structured product list:

```bat
curl.exe -X POST http://127.0.0.1:8000/assistant -H "Content-Type: application/json" ^
  -d "{\"message\": \"show me some headphones under $150\"}"
```

```json
{
  "answer": "I found 1 matching product(s): Aurora Wireless Headphones (SKU-001) at $129.99.",
  "products": [
    {
      "sku": "SKU-001",
      "name": "Aurora Wireless Headphones",
      "description": "Over-ear Bluetooth headphones with 40 h battery life and active noise cancelling.",
      "price": 129.99,
      "tags": ["audio", "headphones", "wireless", "over-ear"]
    }
  ],
  "order_status": null,
  "tool_calls": [
    {
      "tool_call_id": "call_1_1",
      "name": "search_products",
      "arguments": {"query": "headphones", "limit": 5, "max_price": 150.0},
      "ok": true,
      "result": {"query": "headphones", "count": 1, "products": ["…the SKU-001 object above…"]},
      "error": null,
      "duration_ms": 0.06
    }
  ],
  "model": "mock-shopping-llm",
  "usage": {"prompt_tokens": 473, "completion_tokens": 20, "total_tokens": 493},
  "iterations": 2,
  "stop_reason": "final"
}
```

**2. An order question** — the answer plus the order embedded in the response:

```bat
curl.exe -X POST http://127.0.0.1:8000/assistant -H "Content-Type: application/json" ^
  -d "{\"message\": \"where is my order ORD-1002?\"}"
```

```json
{
  "answer": "Order ORD-1002 is processing and is estimated to arrive on 2026-10-24. It contains 1 line(s) totalling $349.00.",
  "order_status": {
    "order_id": "ORD-1002",
    "status": "processing",
    "placed_at": "2026-10-15",
    "eta": "2026-10-24",
    "carrier": null,
    "lines": [
      {"sku": "SKU-003", "name": "Vertex 27-inch 4K Monitor", "quantity": 1, "unit_price": 349.0, "line_total": 349.0}
    ],
    "total": 349.0
  },
  "stop_reason": "final"
}
```

*(Abridged: `products`, `tool_calls`, `model`, `usage` and `iterations` are present in the real
response but omitted here for length.)*

**3. A stock question, streamed** — the same turn as Server-Sent Events:

```bat
curl.exe -N -X POST http://127.0.0.1:8000/assistant/stream -H "Content-Type: application/json" ^
  -d "{\"message\": \"do you have SKU-003 in stock?\"}"
```

```text
event: start
data: {"model":"mock-shopping-llm","max_iterations":4,"message":"do you have SKU-003 in stock?"}

event: tool_call
data: {"tool_call_id":"call_1_1","name":"check_inventory","arguments":{"sku":"SKU-003"},"ok":true,"error":null,"duration_ms":0.06}

event: token
data: {"text":"5 unit(s) availa"}

event: token
data: {"text":"ble at WH-WEST."}

event: final
data: {"answer":"5 unit(s) available at WH-WEST.","products":[],"order_status":null,"tool_calls":[...],"model":"mock-shopping-llm","usage":{"prompt_tokens":440,"completion_tokens":8,"total_tokens":448},"iterations":2,"stop_reason":"final"}
```

Reading the stream: `seq` (shown omitted above for brevity, present on the wire) is a monotonic
counter; concatenating every `token` event's `text` reproduces the `answer` in the `final` event.

### What the mock model does

`MockLLM` is a planner, not a language model. It decides:

- an order id in the message (for example `ORD-1001`) → `get_order_status`;
- a SKU plus a stock word → `check_inventory`;
- both → **two parallel tool requests** in one turn;
- otherwise → `search_products`, turning the sentence into search terms and pulling a
  "under $150" style figure out as `max_price`.

It then summarises whatever the tools returned. That is enough to exercise the entire tool-call
loop deterministically; the tests additionally script exact turns to force unknown tools,
hallucinated arguments and runaway loops.

---

## Configuration

All settings have safe defaults; none are required.

| Environment variable | Default | Meaning |
|---|---|---|
| `SHOPPING_USE_MOCK_LLM` | `1` | `0` switches to the live OpenAI-compatible client |
| `SHOPPING_LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Base URL of the chat-completions server |
| `SHOPPING_LLM_MODEL` | `local-openai-compatible` | Model id sent in the payload |
| `SHOPPING_LLM_API_KEY` | `not-needed` | Sent as `Authorization: Bearer …` |
| `SHOPPING_LLM_TIMEOUT_S` | `30` | Per-request timeout, seconds |
| `SHOPPING_TEMPERATURE` | `0.2` | Sampling temperature |
| `SHOPPING_MAX_ITERATIONS` | `4` | Tool-call round trips per request |

### Using a real model

The live client speaks the plain OpenAI `/chat/completions` shape and needs no SDK. For example,
against a local [llama.cpp](https://github.com/ggml-org/llama.cpp) server:

```bat
llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M --host 127.0.0.1 --port 8080
```

```bat
set SHOPPING_USE_MOCK_LLM=0
set SHOPPING_LLM_BASE_URL=http://127.0.0.1:8080/v1
set SHOPPING_LLM_MODEL=Qwen/Qwen3-4B-GGUF:Q4_K_M
python -m uvicorn app.main:app --reload
```

For a hosted OpenAI-compatible endpoint, additionally set `SHOPPING_LLM_API_KEY`. If the
endpoint is unreachable the service returns `502` for `/assistant` and an `error` event for
`/assistant/stream`; the tests never depend on it (see
`OpenAICompatibleLLM.health_check`).

---

## Architecture (short version)

```text
curl / browser
   │  POST /assistant  (or /assistant/stream)
   ▼
FastAPI (app/main.py)              typed routes, response_model, one store dependency
   ▼
agent loop (app/agent.py)          messages + tool schemas -> model -> execute tools -> repeat
   │            ▲                          │
   │            │ tool results             ▼
   │            └────────────── tools (app/tools.py)   validate args, never raise
   ▼                                                   │
LLM client (app/llm.py)                                ▼
   MockLLM (default)  |  OpenAICompatibleLLM       catalog (app/catalog.py)
   every call → retry (app/retry.py):                 products / inventory / orders
   exponential backoff + jitter + Retry-After
```

Full detail — request flow, the structured-output contract, where retries sit, and the
streaming design — is in [`ARCHITECTURE.md`](ARCHITECTURE.md). Requirements, scope and
non-goals are in [`PROJECT_SPEC.md`](PROJECT_SPEC.md).

---

## Project layout

```text
mini-project-b-ai-shopping-assistant/
├── README.md              this file
├── PROJECT_SPEC.md        requirements, scope, non-goals, done-when, syllabus checklist
├── ARCHITECTURE.md        request flow, structured-output contract, retry + streaming design
├── requirements.txt       fastapi, uvicorn[standard], pydantic, httpx, pytest
├── run.bat                create/activate .venv and start uvicorn
├── click-to-run.bat       create/activate .venv and run pytest
├── app/
│   ├── __init__.py
│   ├── config.py          settings + environment variables
│   ├── catalog.py         deterministic seed data (products, inventory, orders)
│   ├── models.py          Pydantic contracts for every boundary
│   ├── retry.py           backoff + jitter + Retry-After, hand-written
│   ├── tools.py           JSON-schema tool definitions + typed args + executor
│   ├── llm.py             LLMClient protocol, MockLLM, OpenAI-compatible client
│   ├── agent.py           the hand-written tool-call loop (structured + streaming)
│   └── main.py            FastAPI app and routes
└── tests/
    ├── conftest.py        fresh catalogue + fresh MockLLM per test
    ├── test_catalog.py
    ├── test_tools.py
    ├── test_retry.py
    ├── test_api.py
    └── test_agent.py
```

---

## Done-when checklist (from the syllabus)

- [x] Typed FastAPI service with structured outputs
- [x] Tool calling over product search / inventory / order status
- [x] Retries and backoff around every outbound call
- [x] Streaming responses
- [x] Written without autocomplete/AI generation

## Known limitations

- The catalogue is in-memory and read-only; restarting the server resets it.
- `MockLLM` is a heuristic planner, not a language model — it is a test double that happens to
  make a good demo, not a measure of model quality.
- Live streaming retries the connection handshake only; once tokens have been flushed a failure
  is surfaced as an `error` event rather than silently re-run (see `ARCHITECTURE.md`).
- The search is a simple all-tokens-must-match substring match. Phase 3 replaces it with
  embeddings, but the interface (`search_products`) stays the same.

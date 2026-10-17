# PROJECT_SPEC — Mini-project B: AI Shopping Assistant

**Phase:** 2 — LLM APIs as a backend engineer
**Topics:** 11–21 (type hints & Pydantic · structured output · async · streaming · decorators ·
FastAPI essentials · tool calling · MCP · failure handling · fallbacks · gateways · routing ·
reasoning models · when not to use an LLM)
**Rules:** FastAPI + structured output + tool calling over product search / inventory / order
status. Hand-written throughout.
**Completion standard:** it runs on a fresh machine from `README.md` alone.

---

## 1. Goal

Build a small HTTP service that answers shopping questions by *using tools* against a product
catalogue, returns a **validated, structured** answer, **streams** its response, and treats every
outbound call as an unreliable dependency by wrapping it in a **hand-written retry with
exponential backoff and jitter**.

The point is not the shop. The point is to demonstrate, end to end and without a framework, the
Phase 2 stack: typed I/O, a schema-constrained answer, a tool-call loop you wrote yourself,
backoff you can reason about, and a stream you can consume.

---

## 2. Functional requirements

| # | Requirement |
|---|---|
| FR-1 | `GET /health` reports status, version, active model, mock/live mode and catalogue size. |
| FR-2 | `GET /products` lists/searches products with `q`, `max_price`, repeatable `tag` and `limit`. |
| FR-3 | `GET /products/{sku}` returns one product or `404`. |
| FR-4 | `GET /orders/{order_id}` returns one order with lines and computed total, or `404`. |
| FR-5 | `POST /assistant` runs the tool-call loop and returns a structured `AssistantResponse`. |
| FR-6 | `POST /assistant/stream` streams `text/event-stream` and ends with the structured result. |
| FR-7 | The model may request `search_products`, `check_inventory`, `get_order_status`; args are validated before execution. |
| FR-8 | Tool execution never raises: unknown tools, bad arguments and unknown rows become data. |
| FR-9 | The loop is bounded by an iteration budget and reports why it stopped (`stop_reason`). |
| FR-10 | Every outbound call goes through one retry implementation (backoff, jitter, `Retry-After`, cap, elapsed budget). |
| FR-11 | The service runs with no API key and no network (mock model is the default). |
| FR-12 | Every response body is validated by a Pydantic `response_model`; bad requests get `422`. |
| FR-13 | `/docs`, `/redoc` and `/openapi.json` are available automatically. |

### Non-functional requirements

- **Typed:** every function annotated; `from __future__ import annotations` everywhere; no `Any`
  in the public models beyond `dict[str, Any]` payloads.
- **Readable:** docstrings explain the LLM-specific decisions, not the Python.
- **Deterministic tests:** no network, no API key, no sleeping; injected clock and RNG.
- **Small dependency surface:** FastAPI, uvicorn, pydantic, httpx, pytest. Nothing else.

---

## 3. Scope

In scope:

- One in-memory catalogue: 12 products, stock per SKU, 5 orders.
- One hand-written tool-call loop, non-streaming and streaming.
- Two LLM clients behind one protocol: a deterministic mock and an OpenAI-compatible HTTP client.
- One retry implementation used by the live client (and available to anything else that makes an
  outbound call).
- A typed HTTP surface with automatic docs.

## 4. Non-goals

Explicitly **out of scope** for this project — each is a later phase or a deliberate refusal:

| Non-goal | Why |
|---|---|
| Persistence / a database | The catalogue is a deterministic fixture; phase 3 introduces pgvector. |
| Authentication / users / sessions | The API is stateless by design (topic 4); history is resent by the client. |
| Semantic or hybrid search | Phase 3–4. `search_products` is a plain token match; the *interface* is the point. |
| Real payments, carts, checkout | Side effects would make retries unsafe and the demo untestable. |
| An agent framework (LangChain, Pydantic AI, …) | The syllabus requires the loop hand-written first. |
| An LLM provider SDK | Raw HTTP keeps the retry placement and SSE parsing visible. |
| Fallback/failover chains and gateways (19a–19c) | Topics 19a–c are studied separately; this project implements 19 only. |
| MCP servers/clients (topic 18) | Covered by topic 18 itself; adding it here would hide the tool loop. |
| Multi-agent orchestration, memory, planning | Phase 6. |
| Evaluation harness / metrics dashboards | Phase 7–8. |

---

## 5. Done-when

The project is done when, **on a fresh machine**, all of the following hold after following
`README.md` alone:

1. `python -m venv .venv` + activate + `pip install -r requirements.txt` succeed.
2. `python -m uvicorn app.main:app --reload` starts the service and `/docs` loads.
3. `curl /health` returns `{"status":"ok", ...}`.
4. A `POST /assistant` for a product question returns product rows; for an order question returns
   an `order_status`; for a stock question returns inventory data.
5. `POST /assistant/stream` returns `text/event-stream` with `token` deltas and a final structured
   event whose answer equals the concatenated deltas.
6. `python -m pytest -q` passes with no network access and no API key.
7. `run.bat` and `click-to-run.bat` work on Windows.

---

## 6. File map

| Path | Responsibility |
|---|---|
| `README.md` | What it is, install, run, curl examples, example conversation, architecture summary. |
| `PROJECT_SPEC.md` | This document. |
| `ARCHITECTURE.md` | Request flow, structured-output contract, retry placement, streaming design. |
| `requirements.txt` | Runtime + test dependencies. |
| `run.bat` | `cd` to the project, ensure `.venv`, run uvicorn, pause. |
| `click-to-run.bat` | `cd` to the project, ensure `.venv`, run pytest, pause. |
| `app/__init__.py` | Package docstring and version. |
| `app/config.py` | `Settings` dataclass, `from_env()`, cached `get_settings()`. |
| `app/catalog.py` | `Catalog` + deterministic seed data; product search. |
| `app/models.py` | Every Pydantic contract, with `Field` constraints and derived fields. |
| `app/retry.py` | `RetryPolicy`, error classification, `backoff_delay`, `retry_call`, clock/RNG seams. |
| `app/tools.py` | Tool JSON schemas, typed argument models, `execute_tool` (never raises). |
| `app/llm.py` | `LLMClient` protocol, `MockLLM`, `OpenAICompatibleLLM`, SSE helpers, `build_llm`. |
| `app/agent.py` | `build_messages`, `run_agent`, `stream_agent`, result collection. |
| `app/main.py` | FastAPI app, dependencies, typed routes, streaming response. |
| `tests/conftest.py` | Fresh catalogue + fresh `MockLLM` fixtures; `sys.path` for the project root. |
| `tests/test_catalog.py` | Seed consistency, search semantics, derived stock, order totals. |
| `tests/test_tools.py` | Schemas vs argument models, happy paths, failure paths, coercion. |
| `tests/test_retry.py` | Backoff/exhaustion/permanence/`Retry-After`/classification, all with a fake clock. |
| `tests/test_api.py` | TestClient: health, catalogue, orders, structured answer, SSE stream, OpenAPI. |
| `tests/test_agent.py` | The loop (single/parallel/unknown/hallucinated/budget), streaming, live-client retry. |

---

## 7. How each syllabus bullet is satisfied

| Syllabus bullet | Where | How |
|---|---|---|
| **Typed FastAPI service with structured outputs** | `app/main.py`, `app/models.py` | Every route declares `response_model` and an explicit `status_code`; `AssistantResponse` is prose **plus** typed products, order status, tool-call records and usage. `Field` constraints (`ge`, `pattern`, `min_length`, `max_length`) reject bad input with `422`; `computed_field` derives `available`, `in_stock`, `line_total`, `total`. |
| **Tool calling over product search / inventory / order status** | `app/tools.py`, `app/agent.py` | Three JSON-schema tools are sent to the model each turn; the model returns *requests*, `execute_tool` validates the arguments with typed Pydantic models and runs the catalogue function, and `run_agent` feeds the results back as `tool` messages until the model answers. Parallel requests in one turn are all executed. |
| **Retries and backoff around every outbound call** | `app/retry.py`, `app/llm.py` | There is exactly one retry implementation. `OpenAICompatibleLLM.complete` and `.stream` wrap their HTTP call in `retry_call`; the error classifier decides transient vs permanent, backoff is exponential with injectable jitter, and a `Retry-After` header overrides the computed delay up to a cap. Tests prove a 503 is retried and a 401 is not. |
| **Streaming responses** | `app/agent.py` (`stream_agent`), `app/main.py` | `POST /assistant/stream` returns a `StreamingResponse` over a generator of `StreamEvent`s (`start`, `token`, `tool_call`, `final`, `error`) rendered as SSE. The live client consumes the provider's SSE, assembling tool-call fragments; the mock chunks its answer. A test collects the body and asserts the token deltas reassemble exactly into the final structured answer. |
| **Written without autocomplete/AI generation** | whole repository | Plain, framework-free code with explanatory docstrings; no scaffolding, no code generators, no provider SDKs. Every decision that a generator would hide (retry placement, SSE parsing, tool dispatch) is written out. |

### Secondary topics folded in

| Topic | Where it shows up |
|---|---|
| 11 — type hints & Pydantic | `app/models.py` is the single source of vocabulary; validators repair case/whitespace. |
| 12 — structured output | The agent's answer is a Pydantic model, not "please reply in JSON"; arguments are validated and errors fed back. |
| 13 — async/await | Routes are sync (`def`) and FastAPI runs them in a threadpool, so the synchronous retry helper can wrap the LLM call — a deliberate choice, documented in `ARCHITECTURE.md`. |
| 14 — streaming | SSE framing, delta assembly, and mid-stream errors surfaced as an `error` event. |
| 15 — decorators | FastAPI's `@app.get`/`@app.post` and `@computed_field` are used with the mechanics understood, not as magic. |
| 16 — FastAPI essentials | Typed routes, query/path params, `Depends` store dependency, `response_model`, status codes, automatic docs, `TestClient`. |
| 17 — tool calling | The full loop, argument hallucination (repaired or reported), parallel calls, "the model never executes anything". |
| 19 — failure handling | Error taxonomy, backoff + jitter, `Retry-After`, injected clock/RNG for deterministic tests. |
| 20 — reasoning models | `temperature=0.2` default and a note that a reasoning model would fit the same client protocol unchanged. |
| 21 — when NOT to use an LLM | Catalogue lookups are deterministic code; the LLM is used only to map language to those lookups and to phrase the result. `README.md` states this explicitly. |

---

## 8. Acceptance checklist

Functional:

- [x] `/health`, `/products`, `/products/{sku}`, `/orders/{order_id}` behave as specified.
- [x] `POST /assistant` returns answer + products + order status + tool records + usage.
- [x] `POST /assistant/stream` streams and ends with the structured result.
- [x] Unknown tools, malformed and invalid arguments are reported, never raised.
- [x] The loop stops at the iteration budget with `stop_reason="max_iterations"`.
- [x] A transient outbound failure is retried; a permanent one is not.

Quality:

- [x] `python -m pytest -q` passes offline; no network, no API key.
- [x] `python -c "from app.main import app"` succeeds.
- [x] Every module and public function has a docstring/annotations.
- [x] Dependencies are limited to fastapi, uvicorn, pydantic, httpx, pytest.

Documentation:

- [x] `README.md` is sufficient to install, run and test on a fresh machine.
- [x] `ARCHITECTURE.md` explains flow, contract, retry placement and streaming.
- [x] `run.bat` / `click-to-run.bat` use Windows-friendly relative paths (`%~dp0`).

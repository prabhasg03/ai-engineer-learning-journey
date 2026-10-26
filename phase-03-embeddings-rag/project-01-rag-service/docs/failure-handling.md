# Failure Handling — Sourceline (Topic 19 Applied)

**Done when:** every outbound call is classified, bounded, retried only when safe, protected by a
deadline and a circuit breaker, and every failure produces a documented response instead of a stack
trace.

This is the topic 19 contract applied to a RAG service. It covers the embedding provider, the chat
provider, PostgreSQL, and the service's own limits. The implementation lives under
`src/sourceline/resilience/` and is exercised by `tests/unit/`, `tests/chaos/`, and
`tests/integration/`.

---

## 1. Principles

1. **Classify first.** A status code alone is not a policy. `429` from a provider, `429` from our
   limiter, and `429` from a database lock mean different things.
2. **Retry only safe work.** Embeddings and chat completions have no external side effects in this
   service; ingestion writes are idempotent by content. There is no non-idempotent write to retry.
3. **Bound everything.** Every attempt has a timeout, every operation has an attempt limit, and every
   request has an overall deadline. A retry that cannot finish before the deadline is not attempted.
4. **Break the loop.** A dead dependency must not be hammered. The breaker fails fast with a
   `Retry-After`.
5. **Degrade visibly.** A fallback is labelled in the response, logged, and metered. No silent
   substitution.
6. **One owner for retries.** SDK automatic retries are disabled; the service's wrapper owns policy.
   Otherwise attempts multiply (`3 × 3 = 9`) and `Retry-After` is honoured inconsistently.
7. **Surface a request ID.** Every error is traceable to a log line and a metric.

---

## 2. Error taxonomy

`classify_error(exc) -> ClassifiedError(kind, retryable, retry_after, status_code, safe_message)`

| Kind | Typical cause | Retryable? | HTTP to client | Notes |
|---|---|---:|---|---|
| `rate_limit` | Provider 429 | yes | 503 `upstream_rate_limited` | Honour `Retry-After`; cap it |
| `overload` | Provider 5xx, 529, 503 | yes | 503 `upstream_unavailable` | Backoff + jitter |
| `server` | Other provider 5xx | yes | 503 `upstream_unavailable` | Treat as transient |
| `timeout` | Connect/read/total timeout | yes | 504 `deadline_exceeded` | Stop at overall deadline |
| `connection` | DNS, reset, TLS, refused | yes | 503 `upstream_unavailable` | Retry with jitter |
| `auth` | 401, invalid key | no | 500 `internal_error` | Configuration bug; alert; never echo the key |
| `permission` | 403, model not enabled | no | 500 `internal_error` | Configuration/account issue |
| `not_found` | 404 model/deployment | no | 500 `internal_error` | Configuration bug |
| `invalid_request` | 400, malformed request | no | 500 `internal_error` | Our bug; log sanitised body |
| `validation` | 422 provider validation | no | 500 `internal_error` | Our payload/schema bug |
| `content_policy` | Provider content filter | no | 200 abstained `insufficient_evidence` | Do not retry; do not leak policy detail |
| `context_length` | Prompt exceeds model window | no | 500 `internal_error` | Budget bug; alert; fix assembly |
| `conflict` | Provider 409 (rare) | no | 503 `upstream_unavailable` | Treat as transient only if documented |
| `db_serialization` | Postgres serialization/deadlock | yes | 503 `database_unavailable` | Retry the transaction once |
| `db_connection` | Pool exhaustion, connection lost | yes | 503 `database_unavailable` | Retry acquisition, not arbitrary SQL |
| `db_constraint` | FK/unique/check violation | no | 500 `internal_error` | Bug/invariant failure |
| `unknown` | Unclassified | maybe | 500 `internal_error` | Log class/status, never the raw body |

Rules:

- A provider **400/401/403/404/422** is never retried. It is a configuration or payload bug; retrying
  burns money and hides the cause.
- A provider **429** is retryable, but the client sees **503**, not 429: our limiter owns client 429.
- A provider **529** (overloaded) is retryable like 5xx.
- A **content policy** refusal is not an outage. The model declined; map it to an abstention with a
  neutral reason, not a 5xx.
- A **context length** error means our token accounting is wrong. Fail the request, alert, and fix the
  budget; do not truncate the prompt blindly and retry.
- A **schema-invalid model output** is not an HTTP retry. It gets one **repair** call (see §8), then
  abstention.
- An **invalid citation** is not a provider failure. It gets one repair, then abstention.

---

## 3. Retry policy

### 3.1 Formula

```text
base_delay = min(cap, base * 2 ** (attempt - 1))
jittered  = uniform(0, base_delay)                  # full jitter
if Retry-After is present:
    delay = max(jittered, min(retry_after, retry_after_cap))
else:
    delay = jittered
delay = min(delay, max_delay, remaining_deadline - min_attempt_time)
if delay <= 0: stop and raise the classified error
sleep(delay)
```

Full jitter spreads retries across clients; it is not "base ± 10%". `Retry-After` wins over a shorter
backoff, but is capped so a provider cannot pin a worker for an hour. If the required wait exceeds the
remaining deadline, fail now with `Retry-After` set to the remaining cooldown; do not sleep past the
deadline.

### 3.2 Attempt limits by operation

| Operation | Attempts | Base | Cap | Max delay | Per-attempt timeout | Total budget | Retry on |
|---|---:|---:|---:|---:|---:|---:|---|
| Query embedding | 3 | 0.4 s | 3 s | 3 s | 3 s | 6 s | 429, 5xx/529, timeout, connection |
| Ingest embedding batch | 5 | 1 s | 20 s | 30 s | 30 s | 2 min/batch | same |
| Chat completion | 3 | 0.6 s | 6 s | 8 s | 20 s | 25 s | same |
| DB connection acquire | 2 | 0.1 s | 0.5 s | 1 s | 3 s | 3 s | pool timeout, connection lost |
| DB transaction retry | 1 extra | 0.05 s | 0.2 s | 0.2 s | — | — | serialization/deadlock only |
| Readiness DB ping | 1 | — | — | — | 1 s | 1 s | no retry |
| Admin reindex (HTTP request) | 1 | — | — | — | — | 2 s to accept | no retry; the run is async |

Attempt counts are **total attempts**, not retries. `attempts=3` means one initial call plus at most
two retries. The report/log records `attempt_count`.

### 3.3 `Retry-After` parsing

Accept both forms defined by HTTP:

```text
Retry-After: 120
Retry-After: Wed, 21 Oct 2026 07:28:00 GMT
```

Rules:

- Header lookup is case-insensitive.
- Integer seconds: non-negative; `0` means retry immediately (subject to jitter).
- HTTP-date: parse with the standard HTTP-date parser; `retry_after = date - now`; clamp to 0 if past.
- Cap at `retry_after_cap` (default 30 s for ingestion, 10 s for query paths).
- Never trust a provider's `Retry-After` beyond the request deadline. If it exceeds the remaining
  budget, fail fast and propagate a capped value to the client.
- A malformed value is treated as absent; log a warning with the provider and attempt, not the body.

### 3.4 What is not retried

- Authentication, permission, not-found, invalid-request, validation, content-policy, and
  context-length errors.
- A response that fails JSON schema validation (use repair, once).
- A response with invalid citations (use repair, once).
- A user question that fails validation.
- A full reindex that fails an invariant (operator action required).
- Any write after an ambiguous commit outcome unless it is idempotent by key. In v1, ingestion uses
  content-addressed IDs and upserts; admin reindex uses an idempotency key.

### 3.5 Why SDK retries are disabled

The OpenAI/Azure/Anthropic SDKs retry by default (commonly 2 retries with exponential backoff and
jitter, and they may honour `Retry-After`). Leaving that on while adding our own wrapper produces
multiplicative attempts and hides the real count.

The provider adapter is constructed with `max_retries=0` (or the provider-equivalent). At startup:

```text
assert provider.max_retries == 0
```

If a provider does not expose the setting, wrap it in a client whose retry layer is disabled or set
our attempt count to 1 and document the residual. The integration test asserts a 429 produces exactly
the configured number of HTTP requests, not a multiple.

---

## 4. Deadlines

Two levels:

1. **Per-attempt timeout** on the HTTP/SQL call (connect + read). A hung socket must not outlive its
   attempt.
2. **Overall request deadline** (30 s for `/v1/query`), created at admission from a monotonic clock.
   Every stage receives the remaining budget. No stage starts work that cannot finish.

| Stage | Typical | Max | On exhaustion |
|---|---:|---:|---|
| Admission/validation | < 5 ms | 50 ms | 400/422 |
| Readiness/profile check | 5 ms | 100 ms | 503 |
| Query embedding | 150 ms | 6 s | lexical fallback or 503/504 |
| Retrieval | 20 ms | 2 s | 503 |
| Assembly | 5 ms | 200 ms | abstain/500 |
| Chat | 2 s | 25 s | extractive or 504 |
| Validation/response | 3 ms | 100 ms | abstain/500 |
| **Total** | 2 s | **30 s** | 504 + request ID |

The deadline is checked:

- before each provider attempt;
- after the response, before the next attempt;
- before any sleep (never sleep past it);
- before the extractive fallback (only if enough time remains);
- before writing the response/log (logging must not extend the request indefinitely).

If the deadline expires after the LLM produced a valid answer but before validation, the service may
still validate and return if the remaining time is sufficient; otherwise `504`. Do not stream a
partial answer without a `done` event (streaming is deferred).

---

## 5. Circuit breakers

### 5.1 Scope

One breaker per dependency key:

| Key | Guards |
|---|---|
| `embedding` | Query and ingest embedding calls |
| `chat` | Chat completion calls |
| `database` | Connection acquisition / readiness ping (not every SQL statement) |

Breakers are per process. With multiple workers, each process has its own; a future Redis-backed
breaker would share state, but the local breaker still prevents a thundering herd per worker.

### 5.2 State machine

```text
            failure threshold reached
  CLOSED ───────────────────────────────► OPEN
     ▲                                     │
     │                                     │ cooldown elapsed
     │       2 consecutive successes       ▼
     └──────────────────────────────── HALF_OPEN
                                           │
                                           │ probe fails
                                           └──────► OPEN (longer cooldown, capped)
```

| Parameter | Default |
|---|---:|
| Failure threshold | 5 retryable failures in a 30 s window (or 5 consecutive) |
| Open duration | 30 s |
| Open duration cap | 5 min (exponential on repeated failures) |
| Half-open probes | 1 concurrent |
| Successes to close | 2 consecutive |
| Counted failures | retryable classes only (429/5xx/timeout/connection) |
| Ignored failures | 4xx config bugs, validation, content policy, schema repair failures |

When open:

- The call fails immediately with `503 circuit_open` and `Retry-After` = remaining cooldown.
- For chat, the service may use the extractive fallback instead of failing the request (§7).
- For embeddings at query time, lexical fallback may be used.
- For ingestion, the document fails fast; the run continues with other documents and reports
  `dependency_unavailable`.

When half-open:

- One probe is allowed. Other concurrent calls fail fast or wait? They fail fast; the probe decides.
- Two consecutive successes close the breaker and reset the open duration.
- A probe failure reopens with a doubled cooldown, capped.

Breaker state changes are logged and exported as a gauge (`sourceline_circuit_state{dependency}` with
0=closed, 1=half-open, 2=open).

---

## 6. Bulkheads, rate limits, and concurrency

| Control | Limit | Behaviour |
|---|---:|---|
| Query concurrency per IP | 5 | `429 rate_limited` |
| Query concurrency global | 8 | `503 overloaded` / queue briefly, then 503 |
| Admin concurrency | 1 reindex | `409 ingest_locked` |
| Ingest embedding concurrency | 2 batches | Queue; backpressure |
| Chat concurrency | 8 | Semaphore; deadline-aware |
| DB pool | min 2, max 10 (config) | Pool timeout → 503 |
| Query rate | 60/min/IP, burst 10 | Token bucket → 429 |
| Admin rate | 10/min/IP | Token bucket → 429 |
| Request body | 32 KB | 413 |

Our limiter is separate from the provider's. A client `429` means **we** are limiting; a provider
`429` becomes `503 upstream_rate_limited`. Do not conflate them in metrics or docs.

In-memory limiter caveats:

- Single process only. With multiple workers, each has its own budget; the effective limit is
  `workers × limit`. Document this and move to Redis at 10× traffic.
- IP extraction must use the trusted proxy header only when `TRUST_PROXY=true`; otherwise use the
  socket address. Never trust `X-Forwarded-For` blindly.
- The hosted demo adds a daily spend cap independent of request rate.

Graceful shutdown: stop accepting new requests, wait up to 10 s for in-flight queries, close the DB
pool, release the ingest advisory lock. A killed process leaves the lock to session cleanup; the run
is marked `interrupted` at next startup.

---

## 7. Degraded modes

A degraded mode is a **labelled, tested** response, not an ad-hoc `except` branch.

| Failure | Detection | Behaviour | Response label | HTTP |
|---|---|---|---|---|
| Chat provider down/breaker open | classified failure/breaker | Extractive answer from top evidence; validate citations | `degraded.mode=extractive`, `reason=llm_unavailable` | 200 |
| Chat unavailable, no usable evidence | same | Clean failure | — | 503 `upstream_unavailable` |
| Chat timeout, deadline remains | timeout | Extractive if time permits, else 504 | `extractive` or — | 200/504 |
| Query embedding down, lexical enabled | breaker/classified | FTS retrieval, separate floor; same answer pipeline | `degraded.mode=lexical`, `reason=embedding_unavailable` | 200 |
| Query embedding down, lexical disabled | same | Fail closed | — | 503 |
| Ingest embedding down | classified | Document fails; others continue; run partial | run stats | CLI 3/4 |
| DB down | pool/connection failure | Fail closed; no cached answer | — | 503 `database_unavailable` |
| Index building/empty/failed | readiness | Fail closed | — | 503 `index_not_ready` |
| Profile mismatch | readiness | Fail closed | — | 503 `index_profile_mismatch` |
| Model returns invalid JSON | schema validation | One repair; then abstain | `abstained`, `invalid_model_output` | 200 |
| Model cites invalid marker | validator | One repair; then abstain | `abstained`, `ungrounded_answer` | 200 |
| Provider 429 after retries | classifier | Clean failure with capped `Retry-After` | — | 503 `upstream_rate_limited` |
| Our limiter | token bucket | Reject | — | 429 `rate_limited` |
| Daily budget exhausted | counter | Reject | — | 503 `budget_exhausted` |
| Stale index | readiness age/commit | Answer with `index.stale=true` (or 503 if configured strict) | not degraded | 200 |

The extractive fallback is only allowed if:

1. At least one evidence block survived budgeting.
2. The remaining deadline is > 50 ms (local operation).
3. The output passes the same citation validator.
4. The label is set before the response is written. A test asserts the label is present whenever the
   chat provider is forced down.

The lexical fallback is only allowed if `SOURCELINE_LEXICAL_FALLBACK=true` and the FTS index exists.
Its scores are not compared to cosine scores; use a separate floor. If it returns nothing, the result
is an abstention (labelled degraded) or 503, never an unlabelled guess.

---

## 8. Repair vs retry (model output failures)

| Failure | Action | Limit | Then |
|---|---|---|---|
| Invalid JSON / wrong schema | Repair call with the error and allowed markers | 1 | Abstain `invalid_model_output` |
| Missing citations / invalid marker | Repair call listing offending sentences/markers | 1 | Abstain `ungrounded_answer` |
| Model says insufficient evidence | No repair | 0 | Abstain `insufficient_evidence` |
| Provider 5xx/429/timeout | Retry per policy | 3 | Extractive/503/504 |
| Content policy refusal | No repair/retry | 0 | Abstain `insufficient_evidence` |
| Context length error | No retry | 0 | 500 + alert (budget bug) |

Repair and retry are different mechanisms. A repair changes the model's output instructions; a retry
repeats the same request. Conflating them causes either infinite loops or expensive duplicate calls.

---

## 9. Idempotency

| Operation | Key | Guarantee |
|---|---|---|
| Ingest document | `doc_id` + content-addressed `chunk_id` | Replay is a no-op; upserts + set-difference delete |
| Ingest run | advisory lock + run ID | No concurrent interleaving; restart marks `interrupted` |
| Admin reindex | `Idempotency-Key` + request hash | Same key/body returns the same run; different body 409 |
| Query | none (read-only) | Safe to retry; duplicate spend possible but no state change |
| Embedding request | input content hash (implicit) | Same text → same vector; no write side effect |
| Chat request | none (no tools/writes) | Safe to retry; duplicate cost only |
| Citation read | `chunk_id` | Read-only |

There are no non-idempotent writes in v1: no orders, no emails, no tool side effects. The chat model
has no tools. That is a deliberate safety property, not an accident.

For ingestion, the set-difference delete is what makes replay safe: insert missing IDs, update
metadata for existing IDs, delete IDs not present in the new set. A partial transaction rolls back;
the old document remains.

Admin idempotency record:

```text
key + endpoint + sha256(body) -> (status, response_body, run_id)
```

Insert after acceptance, inside the same transaction as the run row. If the insert conflicts, read the
existing row: same hash → return it; different hash → 409. Expire after 24 h.

---

## 10. Provider-specific notes

### OpenAI-compatible chat/embeddings

- 429 responses usually include `Retry-After` and rate-limit headers; honour both but cap.
- 5xx and 529 are transient; retry.
- 400 for context length is ours to fix; do not truncate and retry blindly.
- SDK `max_retries` defaults to 2; set it to 0.
- Timeouts: set connect/read explicitly; the SDK default may be too long for a 30 s request budget.
- Streaming is not used in v1; a stream that dies mid-answer would need a different error contract.
- Azure OpenAI uses the same shapes but different deployment names/URLs; the adapter normalises them.
- Ollama's OpenAI-compatible endpoint may not support structured outputs; fall back to JSON mode +
  Pydantic validation, and expect a higher repair rate. The eval profile records which provider was
  used; do not mix results.

### PostgreSQL / psycopg

- Pool acquisition timeout → `db_connection` (retry once, then 503).
- Statement timeout: 5 s for query path, 60 s for ingest.
- Serialization/deadlock (`40001`, `40P01`) → one transaction retry with jitter. Do not retry a
  constraint violation.
- Connection loss mid-transaction → rollback; the document remains old; re-run.
- Advisory lock is session-scoped; release on exit and let the pool close on shutdown.
- Readiness ping uses a 1 s timeout; never let it hang a probe.

### Our own HTTP layer

- Pydantic validation errors → 422 with field details.
- Unhandled exceptions → 500 with a generic message + request ID; log the stack server-side.
- A `CancelledError` from a client disconnect stops work at the next deadline check; do not write a
  response to a closed socket.
- Response serialization failure is a 500; never return a partial JSON object.

---

## 11. Observability of failure

Every classified failure emits:

```json
{
  "event": "dependency_call_failed",
  "request_id": "req_...",
  "dependency": "chat",
  "operation": "chat.completions",
  "kind": "rate_limit",
  "retryable": true,
  "attempt": 2,
  "max_attempts": 3,
  "status_code": 429,
  "retry_after_s": 4.0,
  "breaker_state": "closed",
  "elapsed_ms": 812,
  "error_class": "RateLimitError"
}
```

Never log: API keys, authorization headers, full provider bodies, prompt text, document text, or the
raw question (unless opt-in). Log the provider request ID when available; it is useful for support and
contains no secret.

Metrics:

- `sourceline_dependency_attempts_total{dependency,kind,outcome}`
- `sourceline_dependency_latency_seconds{dependency,operation}`
- `sourceline_retry_total{dependency,kind}`
- `sourceline_circuit_state{dependency}`
- `sourceline_circuit_open_total{dependency}`
- `sourceline_errors_total{code}`
- `sourceline_degraded_total{mode}`
- `sourceline_deadline_exceeded_total{stage}`

Alerts:

| Alert | Condition | Action |
|---|---|---|
| High provider error rate | > 5% 5xx/429 over 5 min | Check provider status; inspect retry/breaker |
| Circuit open | state=open for > 1 min | Page/check dependency; verify fallback |
| Deadline exhaustion | > 1% of queries over 10 min | Inspect stage timings; lower top_k; provider latency |
| Database unavailable | readiness fail 1 min | Runbook: DB |
| Ingest failures | partial/failed run | Inspect failed docs; re-run |
| Budget exhausted | daily cap hit | Wait or raise cap deliberately |

---

## 12. Fault-injection test matrix

Tests use fake providers, a fake clock, and a disposable database. No real sleeps, no network.

| Test | Injection | Expected |
|---|---|---|
| 429 seconds | 429 + `Retry-After: 2` then success | 2 attempts; sleep ~2 s (fake clock); success |
| 429 HTTP-date | 429 + future date | Parsed; capped; success/failure as configured |
| 429 malformed | `Retry-After: soon` | Treated as absent; backoff used |
| 429 beyond deadline | `Retry-After: 60`, 10 s deadline | No sleep; 503/504 with capped `Retry-After` |
| 500 exhaustion | 500 × 3 | 3 attempts; 503 `upstream_unavailable` |
| 529 overload | 529 then success | Retried like 5xx |
| Timeout | read timeout × 3 | 3 attempts; 504 if deadline gone |
| Connection reset | reset then success | Retried |
| 400 no retry | 400 | 1 attempt; 500 internal + alert |
| Content policy | policy refusal | 200 abstained; no retry |
| Breaker opens | 5 failures | Open; next call 503 + `Retry-After` |
| Half-open success | cooldown, then success ×2 | Closed; failures reset |
| Half-open failure | cooldown, then failure | Reopened with longer cooldown |
| LLM down | chat breaker open | Extractive answer, label, citations |
| Embedding down | query embed fails | Lexical fallback or 503 |
| DB down | pool/connection failure | 503; readiness fail; no 500 |
| Invalid JSON | scripted bad JSON, then valid | Repair; success |
| Invalid JSON twice | bad JSON ×2 | 200 abstained `invalid_model_output` |
| Invalid citation | `[9]` with 3 chunks | Repair; then abstain if repeated |
| Deadline during sleep | slow provider + short deadline | No sleep past deadline; 504 |
| Concurrent ingest | two CLI runs | Second exits 5 / 409 |
| Admin replay | same key/body twice | Same run ID |
| Admin conflict | same key/different body | 409 |
| Partial ingest | one doc fails embedding | Old doc intact; run partial; exit 3 |

Unit tests use a `FakeClock` and a `FakeProvider` that records attempts. Integration tests use a
counter on the embedding provider to prove zero calls on unchanged re-ingest.

---

## 13. Runbook mapping

| Symptom | Check | Action |
|---|---|---|
| `503 upstream_unavailable` spike | provider status, `sourceline_retry_total`, breaker state | Wait for cooldown; verify key/model; check status page |
| `503 upstream_rate_limited` | `Retry-After` logs, provider quota | Back off; raise quota; reduce concurrency |
| `503 circuit_open` | breaker gauge | Wait for half-open; fix dependency; do not restart-loop |
| `504 deadline_exceeded` | stage timings, provider latency | Lower `top_k`/output; raise deadline only with evidence |
| `503 database_unavailable` | DB health, pool saturation | Restore DB; check long transactions; restart pool |
| Ingest partial | `ingest_runs.error_code`, failed docs | Fix file/provider; re-run; unchanged docs skip |
| Index not ready | `/v1/ready` checks | Migrate, ingest, or fix profile |
| Extractive spike | chat breaker/logs | Restore chat provider; verify labels |
| Lexical spike | embedding breaker | Restore embeddings; verify FTS quality |
| High cost | tokens/query, model IDs | Reduce budget/top_k; check repair rate; cap |

The full operational procedure is in [`deployment-and-runbook.md`](deployment-and-runbook.md).

---

## 14. Anti-patterns (explicitly rejected)

- Retrying every exception because "it might work".
- Sleeping `2**n` seconds without jitter, synchronising a retry storm.
- Ignoring `Retry-After` and then blaming the provider.
- Layering SDK retries under app retries and reporting the wrong attempt count.
- Retrying a 400/401/422 and burning quota.
- A circuit breaker that counts validation failures and opens because the model emitted bad JSON.
- A fallback that returns an unlabelled answer so the demo looks green.
- Catching `Exception` around a whole request and returning `{"answer": "Something went wrong"}` with
  HTTP 200.
- Storing the raw provider error body (which may contain keys or user data) in logs or responses.
- A retry that outlives the client deadline and then writes to a closed socket.
- Using a global breaker for all dependencies, so a chat outage blocks embeddings.
- Claiming "production-grade" without a single fault-injection test.

---

## 15. Acceptance checklist

- [ ] Classifier table tests cover every row in §2.
- [ ] Retry tests prove attempts, jitter bounds, `Retry-After` (seconds/date/malformed/cap), and
      deadline behaviour with a fake clock.
- [ ] SDK retry disabling is asserted at startup and by request-count tests.
- [ ] Breakers exist for embedding, chat, and DB acquisition; state transitions are tested.
- [ ] Deadlines are created per request and checked before every attempt/sleep.
- [ ] Idempotency: unchanged ingest = 0 embedding calls; admin replay = same run.
- [ ] LLM-down produces a labelled extractive answer or a clean 503, never a 500.
- [ ] Embedding-down produces lexical fallback or a clean 503, never a silent empty answer.
- [ ] DB-down produces 503 and readiness failure, never a cached/fabricated answer.
- [ ] Every error response has a request ID and a safe message.
- [ ] Logs redact secrets, prompts, and raw questions by default.
- [ ] Alerts/dashboards cover retries, breaker state, deadlines, and ingest failures.
- [ ] Runbook scenarios have been exercised at least once (manual drill) and recorded.

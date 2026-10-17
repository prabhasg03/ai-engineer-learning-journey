# Topic 19 — Failure handling: retries, backoff + jitter, Retry-After

**Done when:** a retry wrapper with exponential backoff + jitter that honours `Retry-After` is running around your calls, and you classify any API error on sight.

**Not this topic:** provider/model *fallback* chains ("primary failed, try the backup")
belong to **Topic 19a — Fallbacks / failover**. There is deliberately no
`fallback_chain` here.

---

## 1. Purpose of This Topic

Hand-write the reliability layer that sits around every LLM call:

- a **taxonomy** that turns any API error into `(kind, retryable)`;
- a **retry wrapper** with exponential backoff + jitter, honouring `Retry-After`;
- **caps** on retries and total elapsed time, so a bad day does not become an outage;
- **idempotency** rules so retries cannot double-charge or double-create;
- a **circuit breaker** so a dead dependency is not hammered;
- an accurate picture of **what the SDKs already retry** — and what is still your job.

You will not use `tenacity`, `backoff` or `urllib3.Retry`. You write the loop, then
you can read any SDK's retry code and know exactly what it does.

---

## 2. Prerequisites

**Before: 6, 17**

- **Topic 6 — first LLM API call.** You need the raw HTTP shape of errors: status
  codes, response bodies, headers such as `Retry-After`.
- **Topic 17 — tool calling.** Retries interact with side effects: a retried tool
  call is a retried side effect. You need the request/response contract in mind.

Also assumed: passing a callable around, dataclasses, and injecting a clock/RNG for
deterministic tests.

---

## 3. Error taxonomy

Classify first; everything else (retry, alert, fall back) is a consequence. In this
repo that is `classify_error(exc) -> (ErrorKind, retryable)`.

| Status / error | Meaning | Kind | Retry? | Notes |
|---|---|---|---|---|
| `429` | Rate limit | `RATE_LIMIT` | ✅ transient | Often carries `Retry-After`; also covers quota/spend limits |
| `529` | Overloaded (Anthropic) | `OVERLOAD` | ✅ transient | Server load, not your request |
| `500` / `502` / `503` / `504` | Server error | `SERVER` | ✅ transient | 503 also carries `Retry-After` |
| connect / read / overall timeout | Timeout | `TIMEOUT` | ✅ transient | Wall-clock and per-socket; the request may still have landed |
| `408` | Request timeout | `TIMEOUT` | ✅ transient | Server gave up waiting |
| `409` | Conflict | `CONFLICT` | ✅ transient | Retried by the OpenAI SDK; usually a concurrent-write race |
| connection reset / DNS | Network | `NETWORK` | ✅ transient | Nothing reached the API |
| `400` | Invalid request | `CLIENT_PERMANENT` | ❌ | The request is wrong; retrying re-sends the same wrong request |
| `401` / `403` | Auth / permission | `CLIENT_PERMANENT` | ❌ | Don't retry — fix the key or the scopes |
| `404` | Not found | `CLIENT_PERMANENT` | ❌ | Wrong model/deployment name |
| `422` | Validation | `CLIENT_PERMANENT` | ❌ | Schema/parameter problem |
| anything else | Unclassified | `UNKNOWN` | ❌ | Fail closed: treat as permanent until proven transient |

```python
kind, retryable = classify_error(ApiError(429, "rate limit exceeded"))
# -> (ErrorKind.RATE_LIMIT, True)

kind, retryable = classify_error(ApiError(401, "invalid api key"))
# -> (ErrorKind.CLIENT_PERMANENT, False)
```

`classify_error` is deliberately forgiving about *where* the status lives: it reads
`exc.status_code`, `exc.status`, `exc.response.status_code`, and finally scans the
message text (SDKs like to say `Error code: 503 - ...`).

**One-sentence interview answer:** transient = the same request could succeed later
(429/5xx/529/408/409/timeouts/network); permanent = the same request will keep
failing until *you* change it (400/401/403/404/422).

---

## 4. Retry: exponential backoff + jitter (+ Retry-After)

### The delay

```text
delay = min(base * multiplier ** (attempt - 1), max_delay)
```

With `base = 0.5s`, `multiplier = 2`: `0.5, 1, 2, 4, 8, ...` capped at `max_delay`.

### Why jitter

Without jitter, every client that got a 503 retries at the *same* instant — the
**thundering herd** — and knocks the recovering service over again. Jitter spreads
the retries out. Four modes, all implemented in `backoff_delay`:

| Mode | Formula | Character |
|---|---|---|
| `none` | `delay` | Deterministic; good for tests only |
| `full` | `uniform(0, delay)` | Max spread; can retry almost immediately |
| `equal` | `delay/2 + uniform(0, delay/2)` | Guarantees at least half the backoff |
| `decorrelated` | `min(max_delay, uniform(base, prev * 3))` | Uses the *previous* delay as a random cloud |

```python
policy = RetryPolicy(max_attempts=5, base=0.5, multiplier=2.0, max_delay=8.0, jitter="full")
outcome = retry_call(fn, policy, clock, rng)
outcome.delays      # the exact schedule, recorded
outcome.attempts    # total tries = 1 + len(delays)
outcome.total_slept
```

### Bounding the pain

- `max_attempts` — total tries (1 initial + `max_attempts - 1` retries), matching
  the vendors' `max_retries = max_attempts - 1`.
- `max_delay` — ceiling for any single sleep (also caps a server `Retry-After`).
- `max_elapsed` — total sleep budget. Topic 6's lesson: an endpoint that hangs and
  is retried without a budget turns a 30-second timeout into a five-minute one.

### Retry-After

A 429/503 may carry `Retry-After`. It is either

- a number of **seconds**: `Retry-After: 3`, or
- an **HTTP-date**: `Retry-After: Wed, 01 Jan 2026 12:00:05 GMT`.

Rules that matter:

- Parse **both** forms (`parse_retry_after`); for the date form you need a `now`.
- **Prefer the server's value** over your computed backoff; it knows when capacity
  returns.
- Still **cap at `max_delay`** — a rogue `Retry-After: 3600` must not park your request
  for an hour.
- Header lookup must be **case-insensitive** (`Retry-After`, `retry-after`,
  `RETRY-AFTER` all appear in the wild).

```python
parse_retry_after("3")                                # -> 3.0
parse_retry_after("Wed, 01 Jan 2026 12:00:05 GMT", now=...)  # -> seconds from now
retry_after_from_headers({"retry-after": "3"})        # -> 3.0
```

---

## 5. Idempotency: making retries safe to actually run

Retrying is only safe when a second execution has the same effect as the first.

```text
Idempotent / safe:      GET a model list, read a cached result, "set temperature=0"
NOT idempotent:         POST /charges, POST /orders, "append a row", "send an email"
```

Two ways to make a retry safe:

1. **Only retry idempotent work.** A read is safe to re-send. A write is not, unless…
2. **Carry an `Idempotency-Key`.** The client generates a UUID **once** for the
   logical operation and reuses it on every retry:

```text
POST /v1/payments
Idempotency-Key: 8f1c1f2e-...-9c1a   # generated before the first try, reused on retries
```

The server caches the result under that key; a duplicate request returns the original
response instead of charging twice. What *you* must get right:

- generate the key **before** the first attempt, never inside the retry loop;
- the key identifies the **logical operation**, not the attempt;
- the key depends on the request body — a changed body needs a new key;
- retention is finite (servers expire keys), so a retry after the TTL can still
  double-execute.

If neither holds, do **not** retry. Report the error and let the caller decide.

---

## 6. Circuit breaker

Retries handle *one* request. A breaker handles *many*: it stops calling a
dependency that is clearly down, so you fail fast instead of paying timeouts.

```text
        failures >= threshold (inside window)
CLOSED ─────────────────────────────────────▶ OPEN
   ▲                                            │ cooldown elapsed
   │                                            ▼
   └──────────── success ─────────────── HALF_OPEN
                                                │ failure
                                                └──────▶ OPEN
```

- **CLOSED** — normal; failures are counted in a rolling `window`.
- **OPEN** — `allow()` returns `False` and calls short-circuit (`BreakerOpen`)
  without touching the dependency.
- **HALF_OPEN** — after `cooldown`, one trial call is let through. Success →
  CLOSED (counters reset); failure → OPEN again with a fresh cooldown.

```python
breaker = CircuitBreaker(failure_threshold=3, window=60.0, cooldown=30.0, clock=clock)
call_with_breaker(fn, breaker)          # raises BreakerOpen when OPEN
```

Two deliberate design choices here:

- the counter **rolls** (old failures fall out of the window), so a slow trickle of
  errors never trips it — production breakers also support a *failure ratio* over a
  minimum request volume;
- only **transient** failures count. A 400 means the request was wrong, not that the
  dependency is dead, so it must not trip the breaker.

Retries and the breaker compose cleanly: `retry_call` (inside a request) around
`call_with_breaker` (across requests). Fallback *targets* are Topic 19a.

---

## 7. What the SDKs do by default vs what remains your problem

**openai-python:** retries **2 times** (3 attempts total) by default, with
exponential backoff (base ≈ 0.5 s) plus jitter, and it honours `Retry-After`. It
retries `408`, `409`, `429`, `>= 500` and connection errors. Configure with
`max_retries` (`openai.OpenAI(max_retries=4)`), or `0` to disable.

**anthropic-sdk:** also retries **2 times** by default with backoff and honours
`Retry-After`.

So the loop you just wrote is, for the common case, already in the client. What the
SDKs *do not* do for you:

| SDK handles | You still own |
|---|---|
| ~2 retries with backoff + jitter | **overall / circuit-level timeout** across all attempts |
| `Retry-After` on 429/503 | **idempotency keys** for write-like calls |
| `max_retries` knob | **circuit breaking** across requests |
| transient status classification | **budget / spend protection** (a 429 may be a spend cap) |
| — | **cross-provider fallback** (Topic 19a) |
| — | **streaming reconnection** (a dropped stream is not a failed request) |
| — | retrying **only** the safely-retryable work (not the whole pipeline) |

Rule of thumb: keep one layer in charge of retries. If the SDK retries 2× and your
wrapper also retries 3×, you have 6 attempts and a surprise bill.

---

## 8. Implementation walkthrough

`implementation/failure_core.py` is the single source of truth:

| Piece | What it does |
|---|---|
| `ErrorKind`, `classify_error`, `ApiError`, `error_headers` | taxonomy; reads status from attribute, nested response, or message text |
| `parse_retry_after`, `retry_after_from_headers` | seconds **and** HTTP-date; case-insensitive lookup; never negative |
| `RetryPolicy` | `max_attempts`, `base`, `multiplier`, `max_delay`, `jitter`, `max_elapsed` |
| `backoff_delay` | the formula + the four jitter modes |
| `RetryOutcome`, `retry_call` | the wrapper; records `attempts`, `delays`, `total_slept`, `retry_after_used`, `kind` |
| `CircuitBreaker`, `BreakerState`, `BreakerOpen`, `call_with_breaker` | rolling-window breaker with cooldown and HALF_OPEN trial |
| `FakeClock`, `FakeRng` | injected clock/RNG so tests assert exact delay sequences |

`retry_call` main loop, in words:

```text
for attempt in 1..max_attempts:
    try fn()                       -> return outcome(ok=True, attempts=attempt)
    except exc:
        kind, retryable = classify_error(exc)
        if not retryable or attempt == max_attempts: give up
        delay = Retry-After (capped)  or  backoff_delay(policy, attempt, rng, prev)
        if total + delay > max_elapsed: give up
        record delay; sleep; continue
```

`implementation/test_failure.py` — 42 test cases (parametrised), all deterministic:

- taxonomy per code class: 429/529/5xx/408/409/network vs 400/401/403/404/422; status
  found in message text and in a nested `response`;
- backoff sequence exact with `FakeClock`/`FakeRng` (`[0.5, 1.0, 2.0]`), cap at
  `max_delay`, full/equal/decorrelated jitter bounds, bad jitter mode rejected;
- `Retry-After` as seconds, as HTTP-date, case-insensitive, and capped at `max_delay`;
- permanent error is **not** retried (one call, no delays); gives up after
  `max_attempts`; succeeds after *k* transient failures; `max_elapsed` stops early;
- breaker CLOSED→OPEN→HALF_OPEN→CLOSED, re-open on HALF_OPEN failure, rolling window,
  OPEN short-circuits, and only transient failures count.

`implementation/failure_demo.ipynb` demonstrates: classifying a table of mock errors,
a retry that succeeds on the third try (printing the delay schedule), `Retry-After`
override (seconds + HTTP-date + cap), and the breaker transitions including a
short-circuited call.

Run everything: `implementation/click-to-run.bat`.

---

## 9. Pitfalls

- **Retrying permanent errors.** A 401 retried three times is three failed auth
  attempts and a slower failure. Classify first.
- **Retrying non-idempotent writes without a key.** Double charges, duplicate rows.
- **No jitter.** Synchronised retries rebuild the load spike you were backing off from.
- **No caps.** Unbounded retries turn a 5-second error into minutes of hanging and
  burn tokens on every attempt.
- **Ignoring `Retry-After`** (or letting it exceed `max_delay`).
- **Case-sensitive header lookup.** `get("Retry-After")` misses `retry-after`.
- **Double retrying.** SDK retries *and* your wrapper → attempt counts multiply.
- **Sleeping on the last failure.** The final attempt must not sleep; the loop here
  only sleeps *between* tries.
- **Counting 400s against the breaker.** The dependency is fine; your request is not.
- **Retrying a dropped stream as if it were a failed request** — partially produced
  output cannot be re-requested for free.
- **Treating every 429 as "slow down".** 429 also covers quota and spend caps, where
  waiting will not help until the limit is raised.

---

## 10. Exercises

1. Add `failure_ratio` support to `CircuitBreaker` (trip when failures/requests >
   `ratio` with at least `min_requests` samples) and test the boundary.
2. Add a `budget` to `RetryPolicy` that stops retrying once the estimated token cost
   of attempts exceeds a cap, and unit-test the stop reason.
3. Write `retry_call_async` (Topic 13) that matches `retry_call`'s delay schedule
   exactly using the same `backoff_delay`.
4. Add an idempotency-key helper (`new_idempotency_key()`, UUID4, generated once
   outside the loop) and a test proving the key is identical across attempts.
5. Prove the thundering-herd difference: run 1,000 simulated clients with `jitter="none"`
   vs `jitter="full"` and histogram the retry instants.
6. Take a real SDK exception class you have seen, feed it to `classify_error`, and fix
   the gap if the status is not found.
7. Wrap `retry_call` *inside* `call_with_breaker` and show a request storm that
   a retry loop alone would amplify but the breaker contains.

---

## 11. Sources

- [Claude API errors](https://platform.claude.com/docs/en/api/errors) — the taxonomy:
  429 rate limit, 500/529 overloaded, 400/401/403/404/413/422 client errors, timeouts.
- [openai-python README](https://github.com/openai/openai-python) — default retry
  behaviour (`max_retries`, which statuses, jitter, `Retry-After`); see also
  `api/_base_client.py` in the repo.
- Supplementary, for the jitter variants: AWS Architecture Blog,
  *Exponential Backoff and Jitter* (`full`, `equal`, `decorrelated`).

**Next:** Topic 19a — Fallbacks / failover (ordered failover after retries,
`context_window` and `content_policy` fallbacks, attribution in spend logs).

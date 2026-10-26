# Testing Strategy — Sourceline

**Rule:** the test suite must prove the failure modes, not just the happy path. It runs offline for
unit/contract/chaos tests and against a disposable PostgreSQL for integration tests. No test calls a
real embedding or chat provider.

---

## 1. Test pyramid

| Layer | Share | Speed | Dependencies | What it proves |
|---|---:|---|---|---|
| Unit | ~60% | milliseconds | none | pure logic: chunking, budget, citations, retry, breaker |
| Integration | ~25% | seconds | Postgres + pgvector | SQL, transactions, idempotency, filters, migrations |
| Contract | ~10% | seconds | FastAPI TestClient + fakes | HTTP shapes, errors, auth, limits |
| Chaos | ~3% | seconds | fakes | dependency failures, degraded modes |
| E2E | ~2% | seconds | seeded DB + fakes | reviewer path: ingest → ask → citation |

Target: **120–160 tests**, not a vanity number. Each test maps to a requirement or a documented
failure mode. A test that asserts an implementation detail (a private helper's call count) without a
behavioural reason is deleted in review.

---

## 2. Determinism

- **No network** in unit/contract/chaos. Provider protocols are injected; the fake provider is
  scripted.
- **No real sleeps.** A `FakeClock` advances monotonic time; retry tests assert scheduled delays, not
  wall-clock pauses. One optional `@pytest.mark.slow` test can use real sleeps to sanity-check the
  clock, excluded from CI.
- **No random jitter in assertions.** Inject a seeded RNG; assert delay bounds and distribution, not
  an exact value.
- **Fixed IDs/time.** Inject `Clock` and `IdFactory`; default tests use deterministic `req_`/`run_`
  values. Production uses `uuid4`/monotonic time.
- **Stable ordering.** Retrieval ties break by `chunk_id`; tests assert exact order.
- **No timezone surprises.** All timestamps UTC; tests set `TZ=UTC` where relevant.
- **No order dependence.** Tests pass in random order (`pytest-randomly` optional) and individually.

---

## 3. Fixtures

| Fixture | Scope | Purpose |
|---|---|---|
| `settings` | function | Frozen config with fake provider, temp DB URL, test profile |
| `fake_embedder` | function | Deterministic vectors; counts calls; can fail N times |
| `fake_chat` | function | Scripted JSON/refusals/invalid output; records prompts (redacted) |
| `fake_clock` | function | Monotonic time; `advance(seconds)` |
| `db` | session | Applies migrations once to a disposable database |
| `db_tx` | function | Transaction rolled back after each test; isolates rows |
| `corpus_tree` | function | Copies `tests/fixtures/corpus/` to a temp dir |
| `seeded_db` | function | Ingests the fixture corpus with the fake embedder |
| `api_client` | function | `TestClient` with injected services/providers |
| `golden_smoke` | session | Loads the smoke JSONL, validates schema |

The fixture corpus contains:

- two topic notes with H1/H2/H3 headings;
- one fenced code block with a known line range;
- one table;
- a near-duplicate paragraph across two files;
- one answerable question's gold passage;
- one deliberately unanswerable topic;
- one "ignore previous instructions" injection paragraph (for sanitisation tests).

It is small enough to read in one screen and specific enough to assert line numbers.

---

## 4. Unit tests

### 4.1 Chunking

| Test | Assertion |
|---|---|
| H2 split | Each section becomes a chunk; heading path is correct |
| H3 split | Oversized H2 splits at H3 before paragraphs |
| Size cap | No normal chunk > 450 tokens; oversized code flagged |
| Overlap | Boundary prose appears in both adjacent chunks; overlap ≤ 150 chars |
| Fence atomicity | No chunk starts/ends inside a fence; language preserved |
| Table atomicity | No row split; table kept with header |
| Heading-only | A heading with no body merges forward, not a junk chunk |
| Line ranges | Slice of source at `[start,end]` equals `content` |
| Content-addressed IDs | Same text/heading → same ID; earlier edit does not shift unrelated IDs |
| Occurrence duplicates | Identical text in the same heading gets distinct IDs |
| Normalisation | CRLF/LF and BOM produce the same hash; line count stable |
| Unicode | Emoji/CJK preserved; no mojibake; NFKC only where specified |

### 4.2 Token budget

- Sum of components ≤ total.
- Oversized evidence block is skipped; next candidate can fit.
- Zero fitting blocks → abstention, no LLM call.
- Actual instruction tokens below cap allow more evidence; reserve is never spent.
- Tokenizer mismatch/overflow is surfaced, not silently truncated.
- `max_words` is reflected in the reserve/instructions.

### 4.3 Prompt and sanitisation

- Static skeleton: retrieved text never appears in the system message.
- Slot rendering happens once; `{...}` in evidence is not re-rendered (no double templating).
- `<context>`, `</evidence>`, `<question>` inside content are escaped and cannot close a tag.
- Control characters removed; code fences preserved.
- Question is last; evidence order matches the assembly report.
- Injection fixture cannot add a marker outside `1..n` to the allowed set.
- Full prompt hash is stable for the same inputs and changes when evidence changes.

### 4.4 Dedupe and ordering

- Exact duplicate keeps higher score; tie by chunk ID.
- Jaccard 0.90 boundary: 0.89 kept, 0.91 dropped.
- Dropped reasons recorded with `kept` ID.
- Sandwich order for n=1..8 is deterministic; strongest at edges; weakest middle.
- Plain-order comparison is available for the eval ablation.

### 4.5 Citations and validation

- Markers contiguous after budget; no gaps; dropped chunks absent.
- `[0]`, `[9]`, `[a]`, `[]` invalid.
- Answer with no marker and `abstained=false` fails.
- Sentence coverage 0.5 fails; 1.0 passes.
- Code blocks/inline code do not create false "factual sentences".
- Abstention truth table (§7.1 of retrieval doc) holds.
- `used_markers` mismatch is recorded but answer markers are authoritative.
- Citation objects are built from DB rows, not model text.
- Weak-support diagnostic flags a paraphrased/unsupported sentence.

### 4.6 Abstention policy

- No candidates → `no_relevant_evidence`, no chat call.
- Top score below floor → same.
- Model `abstained=true` → `insufficient_evidence`.
- Invalid JSON after repair → `invalid_model_output`.
- Invalid citation after repair → `ungrounded_answer`.
- `closest_sources` present only when candidates existed.
- Answerable question above floor is not pre-abstained.

### 4.7 Resilience

| Test | Assertion |
|---|---|
| Classifier table | Each status/exception maps to the documented kind/retryable |
| Retry success | 429 then 200 → 2 attempts, jittered delay within bounds |
| Retry exhaustion | 5xx × 3 → classified failure, attempt_count=3 |
| `Retry-After` seconds | Delay ≥ header value, capped |
| `Retry-After` date | Parsed relative to fake now |
| Malformed header | Ignored; backoff used |
| Deadline | No sleep past deadline; 504/stop |
| Breaker open | 5 failures → open; next call fails fast |
| Half-open | One probe; 2 successes close; failure reopens |
| Non-retryable | 400/401/403/422 → 1 attempt |
| Content policy | No retry, abstention mapping |
| Context length | No retry, internal error + alert |
| Idempotency | Same key/body → same response; different body → 409 |

### 4.8 Config

- Profile key derivation is stable and changes with each component.
- Missing API key fails startup with a readable error (unless the fake/test profile is explicit).
- `SOURCELINE_PUBLIC_DEBUG` is rejected in hosted mode.
- SDK retry disabling is asserted.
- Budget/limit validation rejects impossible combinations (`top_k > candidate_k`, negative tokens).
- Unknown settings are rejected or warned, not silently ignored.

---

## 5. Integration tests

Require `SOURCELINE_DATABASE_URL`; skip with a clear message if absent. CI provides a `pgvector/pgvector:pg16`
service. Each test runs in a transaction that is rolled back, except migration tests that need a
fresh schema.

| Test | Assertion |
|---|---|
| Migrations | Fresh DB applies all; re-apply no-op; checksum mismatch fails; advisory lock |
| Extension | `vector` available; version ≥ 0.8; HNSW index exists |
| Documents/chunks CRUD | FK cascade; constraints; JSON round-trip; pagination |
| Ingest idempotency | Unchanged corpus: `embedded=0`, `inserted=0`, counts identical |
| Edit one section | Only affected chunk IDs change; others reused; line shifts update metadata |
| Delete/prune | Rows removed; query logs survive |
| Profile change | Full rebuild required; readiness mismatch fails |
| Partial failure | Failed doc transaction rolls back; old version queryable |
| Advisory lock | Concurrent ingest exits 5/409 |
| Retrieval filters | Phase/topic/type/prefix correctness; no post-truncation underfill |
| ANN plan | `EXPLAIN` uses HNSW for unfiltered query; not a seq scan |
| Profile guard | Wrong profile vector → 503, no results |
| Tie-break | Equal scores ordered by `chunk_id` |
| Citation slice | `content` equals source lines for every fixture chunk |
| Retention | 30/90-day boundaries delete only old rows |
| Idempotency table | Replay/conflict/expiry |
| Index invariants | Counts/profile/zero-norm checks after ingest |

Integration tests do not assert wall-clock latency; CI runners are noisy. They may assert plan shape
and row counts.

---

## 6. Contract tests

Using `TestClient` and fake services/providers:

- Every endpoint in [`openapi.yaml`](openapi.yaml) exists with the documented method.
- Request validation: missing/unknown fields, ranges, filter enums, 32 KB body, 2,000-char question.
- Response schema: answered, abstained, degraded, debug; citations required fields.
- Error envelope: every code in the table has a test; `request_id` present; no stack traces.
- Headers: `X-Request-ID` echo/generate; rate-limit headers; `Retry-After` on 429/503.
- Auth: admin token required; constant-time compare (behavioural test, not timing assertion);
  public debug rejected unless flag.
- Documents: list pagination, detail 404, URL-encoded path, citation 404 after prune.
- Admin: idempotency replay/conflict, 409 lock, full-reindex confirmation.
- Debug redaction: no prompt/secret/provider body.
- OpenAPI schema validates a sample of every response.

Contract tests must not hit Postgres; services are fakes. One E2E test covers the real wiring.

---

## 7. Chaos tests

| Scenario | Expected |
|---|---|
| Chat 429 then success | Retry; success; attempt count 2 |
| Chat 500 ×3 | 503 `upstream_unavailable`; breaker failure count |
| Chat timeout ×3 | 504/503 per deadline |
| Chat breaker open | 200 extractive, `degraded.mode=extractive`, citations valid |
| Embedding 429 ×3 | Lexical fallback if enabled; otherwise 503 |
| Embedding zero vector | 500/503 fail closed; no search |
| Invalid JSON ×2 | 200 abstained `invalid_model_output` |
| Invalid citation ×2 | 200 abstained `ungrounded_answer` |
| DB pool down | 503 `database_unavailable`; readiness fail |
| Ingest provider down | Run partial; old docs intact; exit 3/4 |
| Deadline exhausted | 504; no background work |
| Concurrent reindex | 409; no second run |
| Client disconnect | Work stops at next deadline check; no write to closed socket |

Chaos tests use a `FaultyProvider` wrapper configured by a table, so adding a failure case is one row,
not a new test file.

---

## 8. E2E tests

With a seeded fixture DB and fake providers:

1. `GET /v1/ready` → ready.
2. `POST /v1/query` for the known answerable question → 200, `grounded=true`, citation resolves to
   the exact fixture lines.
3. `POST /v1/query` for the unanswerable question → 200, `abstained=true`, no LLM call.
4. `POST /v1/query?debug=1` with admin auth → candidates/drops/timings present, no prompt text.
5. Re-run ingest → zero embedding calls; counts unchanged.
6. Resolve a citation after deleting its document → 404 `chunk_not_found`.
7. Static UI loads and contains a form; submit is covered by a DOM smoke test, not a browser E2E
   (Playwright is out of v1 scope).

The E2E test is the "reviewer path" guard. If it fails, the README instructions are suspect.

---

## 9. Coverage and quality tools

| Tool | Scope | Gate |
|---|---|---|
| `pytest` | all | green |
| `pytest-cov` | `src/sourceline` | ≥ 85% line coverage on domain/services/resilience; not a substitute for assertions |
| `ruff` | lint/format | clean |
| `mypy` | `src/` | strict-ish (`disallow_untyped_defs`, `no_implicit_optional`) |
| `pip-audit` | dependencies | no known critical/high vulns (warn for moderate) |
| `scripts/check_no_frameworks.py` | imports | bans `langchain`, `llama_index`, ORMs, etc. |
| OpenAPI validation | contract | runtime schema matches the committed spec |

Coverage exclusions: migrations SQL, `main.py` wiring, generated clients. Do not chase 100%; chase
the failure branches.

---

## 10. CI pipeline

```yaml
jobs:
  quality:
    services: [postgres: pgvector/pgvector:pg16]
    steps:
      - install (locked deps)
      - ruff check
      - mypy src
      - pytest unit contract chaos e2e (with SOURCELINE_DATABASE_URL)
      - pytest integration
      - eval smoke (in-process, fakes)
      - check_no_frameworks
  docker:
    steps:
      - docker build
      - compose up db + api
      - migrate + ingest fixture corpus
      - curl health/ready/query
      - compose down
```

No provider keys in CI. The Docker job uses the fake profile and the fixture corpus; it proves the
container, migrations, and HTTP path, not model quality.

---

## 11. Manual QA checklist (before a demo/release)

- [ ] Fresh clone → Docker quickstart in the README works, in order, without edits.
- [ ] `/v1/ready` is `ready` and shows the expected profile/counts.
- [ ] Three demo questions return cited answers; click each citation and verify the lines.
- [ ] One unanswerable question abstains with a reason.
- [ ] Debug panel shows candidates/drops/timings; no secret/prompt leakage.
- [ ] Re-ingest reports zero embeddings for unchanged docs.
- [ ] Edit a note, re-ingest, confirm only affected chunks changed and the citation updates.
- [ ] Kill the chat provider (fake/flag) → extractive labelled answer; no 500.
- [ ] Kill the DB → readiness 503; query 503; no cached answer.
- [ ] 429 drill → retry/`Retry-After`; 400 drill → no retry.
- [ ] The eval report matches the README numbers.
- [ ] Logs contain request IDs and no secrets; metrics endpoint works.
- [ ] Stop the service: no orphan process, advisory lock released.

---

## 12. What is not tested (and why)

- Real provider quality in CI: nondeterministic, costs money, requires secrets. Covered by the
  release eval/human review.
- Browser rendering across engines: the UI is static and thin; a DOM smoke test plus manual check is
  proportionate.
- Multi-worker rate limiting: v1 is single-process; the scaling path documents Redis and its tests
  belong to that milestone.
- Adversarial prompt-injection robustness: v1 has no tools and validates outputs; a red-team suite is a
  future security milestone, not a claim of immunity.
- Disaster recovery at scale: the runbook covers a single-node backup/restore drill; multi-region is
  out of scope.

Stating the gaps is part of the engineering; an untested surface that is claimed as production-grade
is the real failure.

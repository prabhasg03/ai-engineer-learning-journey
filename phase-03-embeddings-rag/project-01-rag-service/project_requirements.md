# Project Requirements — Sourceline

| Field | Value |
|---|---|
| Project | Project 1 — RAG service over a real document set |
| Codename | Sourceline |
| Version | 1.0 (blueprint) |
| Status | Design complete; implementation pending |
| Owner | Repository author |
| Phase | 3 — Embeddings and RAG (topics 22–28) |
| Canonical spec | This document + [`architecture.md`](architecture.md) + [`docs/api-contract.md`](docs/api-contract.md) |
| Definition of done | A hiring manager can run the service from the README on a fresh machine |

---

## 1. Problem and goals

### 1.1 Problem

The repository contains 28 topics of dense technical notes (38 Markdown files, 83,348 words). Finding
a specific explanation means remembering which topic covered it and scanning a 500-line file. A
general-purpose chatbot answers from parametric memory and cannot show where the claim came from.

### 1.2 Product goal

Build a service that answers questions **about this corpus** and shows the exact supporting passages,
so a reader can verify every claim in one click. The service must refuse to answer when the corpus
does not support an answer.

### 1.3 Portfolio goal

Demonstrate, in one runnable artifact:

- a real ingestion pipeline (chunk → embed → pgvector) with idempotent upserts and reindex triggers;
- retrieval, prompt assembly, citation validation, and abstention designed as separate, testable stages;
- production failure handling (topic 19): retries, jitter, `Retry-After`, deadlines, circuit breakers,
  idempotency, degraded modes;
- evaluation and failure diagnosis (topic 28), not just a demo;
- a README a non-author can follow without help.

### 1.4 Success metrics

| Dimension | Metric | Target |
|---|---|---:|
| Answer quality | Groundedness on golden set | ≥ 0.95 |
| Answer quality | Citation validity on answered responses | 100% |
| Retrieval | Recall@10 (any gold chunk) | ≥ 0.90 |
| Safety | False-answer rate on unanswerable set | ≤ 5% |
| Reliability | Query success rate with one provider outage | 100% labelled degraded response, no 500 |
| Performance | p95 end-to-end (real providers) | ≤ 6 s |
| Performance | p95 retrieval (local DB) | ≤ 150 ms |
| Cost | Blended cost per query | ≤ $0.01 |
| Operability | Full-corpus ingest | ≤ 3 min |
| Reproducibility | Fresh-machine README run | Passes checklist without undocumented steps |

---

## 2. Personas

| Persona | Need | What success looks like |
|---|---|---|
| **Hiring manager / reviewer** | Judge engineering ability in 10 minutes | `docker compose up`, ingest, ask 3 questions, see citations and an eval table |
| **Curriculum reader** | Find and verify an explanation | Answer + clickable citation to file/heading/lines |
| **Operator** | Keep the index fresh and the service healthy | `/v1/ready`, ingest report, runbook, metrics |
| **Developer** | Change retrieval/prompt safely | Pure stages, fixtures, tests, debug output, eval gate |
| **Interviewer** | Probe depth | Design docs, failure matrix, measured numbers, ADRs |

---

## 3. User stories

| ID | Story | Acceptance |
|---|---|---|
| US-01 | As a reader, I ask a natural-language question and get a concise answer with citations. | Response has `answer`, ≥1 citation for every factual sentence, `grounded=true`, and markers resolve. |
| US-02 | As a reader, I click a citation and see the exact source lines. | Citation contains `doc_id`, `heading`, `lines`, `url`/local path, and an excerpt that matches the indexed chunk. |
| US-03 | As a reader, I ask something outside the corpus and get an honest refusal. | `abstained=true`, `abstention_reason="no_relevant_evidence"` or `"insufficient_evidence"`, no fabricated claim. |
| US-04 | As a reader, I narrow a question to a phase or topic. | `filters.phase`/`filters.topic` restrict retrieval; citations all satisfy the filter. |
| US-05 | As an operator, I re-run ingestion without duplicating rows or paying to re-embed unchanged text. | Second run: `embedded=0`, `unchanged=docs`, identical counts. |
| US-06 | As an operator, I edit one section and re-ingest. | Only affected chunks change; stale chunks are deleted. |
| US-07 | As an operator, I can tell whether the index is stale or incomplete. | `/v1/ready` reports profile, document/chunk counts, `built_at`, `age_seconds`, `stale` flag. |
| US-08 | As a developer, I can see why a question failed. | `?debug=1` returns candidate scores, drop reasons, evidence tokens, per-stage timings, and validation flags. |
| US-09 | As a developer, I can run the whole suite offline. | `pytest -q` passes with fake providers and no network. |
| US-10 | As an interviewer, I can see failure behaviour. | Fault-injection tests show 429/`Retry-After`, timeout, circuit-open, LLM-down, and DB-down paths. |
| US-11 | As a reviewer, I can run it on a fresh machine. | Docker quickstart works with one documented key and no hidden setup. |
| US-12 | As an operator, I can trigger a reindex safely. | Admin endpoint requires a token and `Idempotency-Key`; concurrent runs return 409. |

---

## 4. Scope

### 4.1 In scope (v1)

- Markdown corpus from this repository: the Phase 1–3 notes (38 files). Root `README.md`/`SYLLABUS.md`
  are optional via `--include-meta`, not part of the default corpus.
- Structural chunking, deterministic chunk IDs, line-level provenance.
- Dense retrieval over pgvector with metadata filters.
- Prompt assembly with dedupe, ordering, token budget, and citation markers.
- Grounded answer via an OpenAI-compatible chat model, with one schema-repair attempt.
- Deterministic citation validation and fail-closed abstention.
- FastAPI query/readiness/documents/admin endpoints + a static demo UI.
- Ingestion CLI, migrations, run reports.
- Topic 19 resilience layer and explicit degraded modes.
- Golden evaluation set, smoke CI gate, and a query log for diagnosis.
- Docker Compose quickstart; optional hosted demo.

### 4.2 Out of scope (v1)

- Hybrid BM25+dense fusion (Phase 4, topic 30). A lexical **fallback** exists only for embedding
  outages and is labelled degraded.
- Learned reranking (topic 31). Ordering is deterministic.
- Multi-user accounts, per-document ACLs, SSO.
- Agentic tools, browsing, writes, or any model-initiated side effect.
- Streaming responses (P2; the API shape is reserved).
- Distributed ingestion workers, queues, or multi-region.
- Fine-tuning or self-hosted GPU inference (an OpenAI-compatible local endpoint is optional).
- Claim-level NLI groundedness in production (topic 37); v1 validates citations deterministically and
  measures semantic groundedness in the eval harness.

---

## 5. Functional requirements

Each requirement is testable. "MUST" is a release gate; "SHOULD" may slip with a written note.

### 5.1 Corpus and ingestion

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-01 | The ingester MUST discover corpus documents deterministically by path. | Same checkout produces the same ordered manifest; re-run bytes identical. |
| FR-02 | It MUST include only allow-listed Markdown files and exclude implementation, cache, VCS, virtualenv, and the project folder itself. | Unit test on a fixture tree; corpus report lists included/excluded counts. |
| FR-03 | Each document MUST have a stable `doc_id` (POSIX relative path), title, phase/topic metadata, SHA-256 content hash, and source commit. | DB row matches manifest; editing a file changes only its hash. |
| FR-04 | Chunking MUST be structural: H2/H3 boundaries, paragraph/sentence fallback, code fences and tables preserved. | Snapshot tests on notes with fenced code and tables; no chunk splits a fence. |
| FR-05 | Chunk size MUST target 250–350 tokens, hard cap 450, with 40–60 token overlap only at safe boundaries. | Chunker report: p50/p95 tokens; no chunk > cap except flagged oversized code. |
| FR-06 | Every chunk MUST store heading path, start line, end line, token count, content hash, and chunker version. | Citation resolves to the exact source slice in an integration test. |
| FR-07 | Embeddings MUST be generated in batches with a pinned model, dimensions, and profile key. | Report shows `chunks/64` requests (ceil); profile stored per row. |
| FR-08 | Ingestion MUST be idempotent: unchanged documents cause zero embedding calls and zero row writes. | Second run asserts `embedded=0`, `inserted=0`, `updated=0`, counts unchanged. |
| FR-09 | A changed document MUST insert/update only changed chunks and delete chunks no longer present. | Edit-one-section test; shrink test; row counts match. |
| FR-10 | A changed embedding model, dimension, chunker version, or size profile MUST trigger a full corpus reindex. | `reindex_reason` test for each trigger. |
| FR-11 | Ingestion MUST run under a database advisory lock so two runs cannot interleave. | Concurrent-run integration test returns exit code 5 / 409. |
| FR-12 | An ingest run MUST produce an auditable report and a documented exit code (`0` success, `2` usage/config, `3` partial, `4` dependency, `5` locked, `6` invariant failure). | CLI transcript; `ingest_runs` row with stats JSON. |
| FR-13 | A failed document MUST leave its previous indexed version intact (per-document transaction). | Fault injection during upsert; old chunks remain queryable. |
| FR-14 | `--prune` MUST remove documents no longer present in the corpus. | Delete a fixture file, re-ingest, document count drops. |

### 5.2 Retrieval

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-15 | `POST /v1/query` MUST validate question length (3–2,000 chars), `top_k` (1–20), `candidate_k` (≥ top_k, ≤ 100), and allow-listed filters. | 422 for each invalid case; unknown fields rejected. |
| FR-16 | The query MUST be embedded with the **active profile**; a profile mismatch MUST fail closed (503). | Integration test with altered profile returns `index_profile_mismatch`. |
| FR-17 | Retrieval MUST use pgvector cosine over an HNSW index, over-fetching `candidate_k`, with `ef_search` configurable. | SQL plan shows index scan; recall measured against exact search on a fixture. |
| FR-18 | Metadata filters MUST be applied in SQL (pre-filter), not after truncation. | Filtered responses contain only matching docs; no short results for narrow filters on the fixture. |
| FR-19 | Exact and near-duplicate chunks MUST be collapsed before budgeting, keeping the highest score and recording removals. | Duplicate fixture returns one citation; debug lists the removal reason. |
| FR-20 | Evidence MUST be ordered with the strongest chunks at the edges (sandwich), question last. | Unit test on ordering; debug shows prompt order. |
| FR-21 | The decoder MUST use deterministic tie-breaking (score desc, then chunk ID) so results are reproducible. | Same query returns the same order across runs. |

### 5.3 Answer and citations

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-22 | The prompt MUST be rendered from a static skeleton with dynamic slots; retrieved text MUST NOT enter the instruction region. | Template test; injection fixture cannot close `<context>`. |
| FR-23 | The prompt MUST fit an explicit budget: total 6,000 tokens by default, answer reserve 700, instructions ≤ 400, question ≤ 100, overhead ≤ 100. | Assembly asserts `used ≤ total`; debug reports each component. |
| FR-24 | Citation markers MUST be assigned after pruning, contiguously `1..n`, and stored in a chunk→marker map. | No gaps; dropped chunks have no marker. |
| FR-25 | The answer MUST be structured JSON: `answer`, `abstained`, optional `abstention_reason`, and markers in the prose. | Pydantic validation; one repair attempt on schema failure. |
| FR-26 | Every factual sentence in a non-abstained answer MUST contain at least one valid marker. | Sentence-coverage validator; failure triggers repair then abstention. |
| FR-27 | Invalid or hallucinated markers MUST be rejected deterministically. | Validator unit test with `[9]` when only 5 chunks exist. |
| FR-28 | The service MUST abstain before generation when no candidate clears the calibrated score floor. | Unanswerable fixture: no LLM call, `abstained=true`. |
| FR-29 | The service MUST abstain when the model reports insufficient evidence or validation fails after repair. | Scripted fake LLM responses; `abstention_reason` is machine-readable. |
| FR-30 | `grounded` MUST be true only when citation validity and sentence coverage both pass. | Truth table tests for the four combinations. |
| FR-31 | Responses MUST include `request_id`, citations with source/line metadata, usage, timings, index profile, and `degraded`. | Contract test against the OpenAPI schema. |

### 5.4 API, operations, and diagnostics

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-32 | `GET /v1/health` MUST report liveness without touching dependencies. | Returns 200 while DB is down (liveness only). |
| FR-33 | `GET /v1/ready` MUST verify DB, pgvector, migrations, active profile, non-empty index, and freshness; return 503 with a machine reason otherwise. | Each failure injected in tests. |
| FR-34 | `GET /v1/documents` MUST paginate document summaries with counts and hashes. | Cursor pagination test; no full corpus in one response. |
| FR-35 | `GET /v1/documents/{doc_key}` MUST return metadata and chunk count, 404 when absent. | URL-encoded path test; traversal rejected. |
| FR-36 | `GET /v1/citations/{chunk_id}` MUST return the stored source excerpt and line range. | Chunk from a query resolves byte-for-byte. |
| FR-37 | `POST /v1/admin/reindex` MUST require a bearer admin token and an `Idempotency-Key`; concurrent runs → 409. | Auth/conflict/idempotency tests. |
| FR-38 | `GET /v1/admin/runs/{run_id}` MUST expose status and stats. | Run lifecycle test. |
| FR-39 | `?debug=1` MUST require admin auth by default and return retrieval/assembly diagnostics, never the system prompt or secrets. A local-only `SOURCELINE_PUBLIC_DEBUG=true` may relax auth and MUST be rejected in hosted config. | Redaction + hosted-config test. |
| FR-40 | The service MUST serve a static demo UI at `/` with answer, citations, source excerpt, and an unanswerable example. | Manual checklist + DOM smoke test. |
| FR-41 | Query logs MUST capture the four sets (retrieved/prompted/cited), timings, tokens, abstention, degraded mode, and errors, with a 30-day retention job. | Log schema test; retention query documented. |
| FR-42 | Request IDs MUST be accepted (`X-Request-ID`) or generated and echoed; every error includes one. | Middleware test. |

### 5.5 Failure handling (topic 19)

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-43 | Every outbound call MUST pass through one classifier returning `(kind, retryable)` for 429, 5xx/529, timeout, connection, and 4xx classes. | Table-driven classifier tests. |
| FR-44 | Retries MUST use bounded exponential backoff with full jitter and honour `Retry-After` in seconds and HTTP-date form, capped by policy. | Fake clock tests; no real sleeps. |
| FR-45 | Retries MUST stop at the overall request deadline; a timeout returns 504, not a hung request. | Deadline test with a slow fake provider. |
| FR-46 | A circuit breaker MUST guard embedding, chat, and DB connectivity, with CLOSED→OPEN→HALF_OPEN transitions. | State-machine test; open breaker returns 503 + `Retry-After`. |
| FR-47 | SDK automatic retries MUST be disabled or accounted for so attempts do not multiply. | Configuration test / startup assertion. |
| FR-48 | Ingestion writes MUST be idempotent (content-addressed chunks, upserts, run lock); admin reindex MUST be idempotent by key. | Replay test; repeated admin call returns the same run. |
| FR-49 | When the LLM is unavailable, the service MUST return a labelled extractive answer from retrieved chunks or a clean 503, never a 500. | LLM-down test asserts `degraded.mode="extractive"` and citations. |
| FR-50 | When the embedding provider is unavailable at query time, the service MUST use lexical fallback if enabled, labelled `degraded.mode="lexical"`, or return 503. | Embedding-down test. |
| FR-51 | Provider errors MUST NOT leak keys, raw bodies, or stack traces to clients. | Error-envelope test with a sensitive fake body. |

### 5.6 Evaluation

| ID | Requirement | Acceptance / test |
|---|---|---|
| FR-52 | A versioned golden set of ≥ 80 cases MUST exist, covering factual, comparison, procedural, and unanswerable questions. | Dataset schema validation; category counts. |
| FR-53 | The eval runner MUST report retrieval, citation, groundedness, abstention, latency, and cost metrics per category and overall. | JSON + Markdown report with commit/profile metadata. |
| FR-54 | CI MUST run a smoke subset offline and fail on citation-validity or false-answer regressions. | GitHub Actions job. |
| FR-55 | Failed cases MUST be attributable to retrieval, ranking, or generation using the topic 28 decision procedure. | Attribution counts in the report. |

---

## 6. Non-functional requirements

| ID | Area | Requirement | Target / verification |
|---|---|---|---|
| NFR-01 | Latency | Query p95 end-to-end with real providers | ≤ 6 s; p50 ≤ 2.5 s |
| NFR-02 | Latency | Retrieval stage p95 (local Postgres) | ≤ 150 ms for candidate_k=40 |
| NFR-03 | Latency | Cold start to first request | ≤ 10 s |
| NFR-04 | Throughput | Single instance demo capacity | 10 queries/s sustained with fake LLM; 5 concurrent real-provider queries |
| NFR-05 | Reliability | Dependency failure behaviour | Every failure returns a documented 4xx/5xx or labelled degraded 200; no unhandled 500 |
| NFR-06 | Reliability | Index freshness | `/v1/ready` exposes age; alert if > 7 days in a deployed environment |
| NFR-07 | Quality | Citation validity | 100% on answered responses |
| NFR-08 | Quality | Groundedness | ≥ 0.95 golden set |
| NFR-09 | Quality | Unanswerable safety | ≤ 5% false answers |
| NFR-10 | Security | SQL injection | 100% parameterised SQL; no string interpolation of user input |
| NFR-11 | Security | Secrets | Environment only; never logged, returned, or committed |
| NFR-12 | Security | Admin surface | Bearer token; constant-time comparison; rate-limited |
| NFR-13 | Privacy | Query logs | Question hashed + optional redacted text; 30-day retention; no PII in corpus |
| NFR-14 | Cost | Blended query cost | ≤ $0.01; per-day hosted budget cap |
| NFR-15 | Cost | Re-ingest | Unchanged corpus = $0; full re-embed ≤ $0.05 at current corpus size |
| NFR-16 | Maintainability | Layering | API → services → domain/repositories/providers; no circular imports |
| NFR-17 | Maintainability | Type safety | `mypy` on `src/`; `ruff` clean |
| NFR-18 | Testability | Offline suite | `pytest -q` passes with no network; deterministic clock/RNG |
| NFR-19 | Portability | Runtime | Docker Compose on Windows/macOS/Linux; Python 3.12 local path |
| NFR-20 | Observability | Signals | Structured logs, Prometheus metrics, per-stage timings, request IDs |
| NFR-21 | Accessibility | Demo UI | Keyboard submit, labelled controls, readable contrast, no build step |
| NFR-22 | Documentation | Reviewer path | README quickstart ≤ 6 commands; architecture + eval + failure docs linked |
| NFR-23 | Reproducibility | Determinism | Same corpus + profile + model temperature 0 → stable retrieval/citation ordering |

---

## 7. Data requirements

| Requirement | Decision |
|---|---|
| Corpus source | This repository: `phase-01-llm-fundamentals/`, `phase-02-llm-apis/`, `phase-03-embeddings-rag/` (38 notes). Root `README.md`/`SYLLABUS.md` are optional (`--include-meta`). |
| Include rule | `**/*.md`, excluding `**/implementation/**`, `**/__pycache__/**`, `**/.pytest_cache/**`, `**/.venv/**`, and `project-01-rag-service/**` |
| Encoding | UTF-8, BOM stripped, CRLF→LF normalised before hashing |
| File size cap | 2 MB per file; oversized files rejected and reported |
| Symlinks | Rejected during discovery (no traversal outside root) |
| Document ID | POSIX relative path from repository root, e.g. `phase-03-embeddings-rag/topic-25-pgvector/notes.md` |
| Chunk ID | Content-addressed: `c_` + first 24 hex of SHA-256(doc_id, heading_path, content, occurrence), where occurrence disambiguates identical text in the same heading |
| Chunk key | Human-readable `<heading-slug>#<ordinal>` (document implied by `doc_id`) for debugging |
| Embedding profile | `markdown-h2-v1|1200|150|<model>|<dims>`; one active profile per index |
| Source URL | `{SOURCELINE_SOURCE_BASE_URL}/{commit}/{doc_id}#L{start}-L{end}` when configured; local path otherwise |
| Retention | `query_logs` 30 days; `ingest_runs` 90 days; chunks/documents life of corpus |
| Provenance | Every chunk stores heading path and inclusive line range; every citation resolves to it |

---

## 8. Constraints and rules

1. **Hand-written throughout.** No RAG framework, no ORM, no scaffold generator, no copied
   end-to-end project. Infrastructure libraries are allowed (FastAPI, Pydantic, psycopg, provider
   SDK, pytest, ruff, mypy). See ADR-012.
2. **pgvector is mandatory** for the primary retrieval path. A dedicated vector database is out of
   scope; the reasoning is recorded in ADR-001.
3. **One active embedding profile.** Mixing models/dimensions in one index is forbidden; switching
   profiles requires a full rebuild.
4. **No hidden model upgrades.** Model IDs and dimensions are pinned in configuration; changing them
   is a deployment event with a reindex.
5. **Offline tests.** Unit/integration tests never call a real provider. Provider contract tests use
   recorded/fake responses.
6. **Fail closed on grounding.** An answer without valid citations is not returned as grounded.
7. **No invented metrics.** The README reports only numbers produced by the eval runner.
8. **Windows-first developer, portable deployment.** Commands documented for PowerShell and POSIX;
   Docker is the reviewer path.

---

## 9. Acceptance criteria (syllabus traceability)

| Syllabus bullet | Acceptance evidence |
|---|---|
| Real document set ingested (chunk → embed → pgvector) | Corpus report (38 docs), `documents`/`chunks` counts, HNSW index present, zero-call re-ingest, edit/prune tests, ingest transcript |
| Query endpoint returning grounded answers with citations | `POST /v1/query` contract tests, citation resolver, 100% citation validity on answered golden cases, abstention path, UI screenshot |
| Failure handling from topic 19 applied | Classifier/retry/`Retry-After`/deadline/breaker tests, degraded-mode tests, fault matrix, runbook |
| Hand-written throughout | No framework imports, raw SQL, ADR-012, review checklist, commit history |
| Hiring manager can run it from README | Fresh-machine Docker checklist passes in ≤ 10 minutes with one documented key |

### 9.1 Release checklist

- [ ] `docker compose up` from a clean clone reaches `ready`.
- [ ] Full ingest completes and reports expected counts.
- [ ] Three demo questions return cited, grounded answers.
- [ ] One unanswerable question abstains with a reason.
- [ ] `?debug=1` shows candidates, drops, and timings.
- [ ] Re-ingest reports `embedded=0`.
- [ ] `pytest -q` passes offline; `ruff` and `mypy` clean.
- [ ] Eval smoke gate passes; full report committed.
- [ ] Failure drills pass (429, timeout, breaker, LLM down, DB down).
- [ ] README has a GIF, measured metrics, limitations, and a hosted link or run instructions.
- [ ] No secrets or generated caches committed.

---

## 10. Assumptions and dependencies

| Assumption | Impact if false |
|---|---|
| PostgreSQL 16 with pgvector ≥ 0.8 is available | HNSW/iterative scan behaviour changes; use exact search fallback |
| An OpenAI-compatible chat + embedding endpoint is available at build/demo time | Demo needs the fake profile; real quality unevaluated |
| Corpus stays Markdown | Parser adapter needed for PDF/HTML |
| ~100k tokens of corpus fits comfortably in one pgvector table | Scale path needed beyond ~1M chunks |
| A single API process is enough for the demo | Rate limiting/circuit state need Redis for multi-worker |
| The repository is public when citations link to GitHub | Use local-path citations instead |
| The reviewer can obtain an API key or run Ollama | Hosted demo link becomes the fallback |

---

## 11. Open questions and defaults

These do not block implementation; defaults are binding unless changed in an ADR.

| Question | Default |
|---|---|
| Include root `README.md`/`SYLLABUS.md`? | No by default; `--include-meta` opts in, tagged `doc_type=meta` |
| Streaming? | Deferred (P2); reserve `/v1/query/stream` in the contract |
| Hosted public demo? | Recommended; rate-limited, daily budget cap, no admin surface |
| Local Ollama profile? | Supported if OpenAI-compatible; not a CI gate |
| Query auth? | Public demo with IP rate limit; optional API key via config |
| Store raw questions? | SHA-256 only by default; optional redacted text with `SOURCELINE_LOG_QUESTIONS=true`; 30-day retention |
| Reranker? | No learned reranker in v1; deterministic ordering only |
| Hybrid search? | No; lexical only as an embedding-outage fallback |
| Exact model IDs? | Pin in `.env.example` at M1; never auto-upgrade |
| Licence? | MIT for code; corpus remains author-owned |

---

## 12. Glossary

| Term | Meaning |
|---|---|
| **Chunk** | A retrievable slice of a document with provenance (heading, lines) |
| **Profile** | The tuple of embedding model, dimensions, chunker version, and chunk sizes; switching invalidates vectors |
| **Candidate set** | `candidate_k` chunks returned by the vector search before dedupe/budget |
| **Prompted set** | Chunks that survived dedupe, ordering, and token budgeting into the final prompt |
| **Citation validity** | Every marker in the answer maps to an assembled chunk |
| **Grounded** | Citation validity passes **and** every factual sentence has a marker |
| **Abstention** | A deliberate refusal when evidence is absent or insufficient |
| **False answer** | A non-abstained answer to an unanswerable question |
| **Degraded mode** | A labelled fallback (extractive answer, lexical retrieval) used when a dependency fails |
| **Profile key** | Canonical string stored on every row and checked at query time |

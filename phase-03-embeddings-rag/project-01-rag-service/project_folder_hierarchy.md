# Project Folder Hierarchy — Sourceline

This is the **target** tree for the completed project. Only `[now]` files exist at the blueprint
stage; every `[build]` path is created during implementation. The hierarchy is a contract: module
boundaries, naming, and generated-vs-hand-written rules are part of the design.

Legend: **[now]** blueprint artifact · **[build]** hand-written during implementation ·
**[generated]** produced by a command, not edited · **[fixture]** test/eval data.

```text
phase-03-embeddings-rag/project-01-rag-service/
│
├── README.md                                  [now]   reviewer-facing overview + quickstart contract
├── project_requirements.md                    [now]   personas, FR/NFR, acceptance criteria
├── architecture.md                            [now]   context, components, flows, deployment
├── project_folder_hierarchy.md                [now]   this file
├── LICENSE                                    [build] MIT for application code
│
├── .env.example                               [now]   every setting, no secrets
├── .gitignore                                 [build] ignores .env, caches, snapshots, raw reports
├── .dockerignore                              [build] excludes tests/docs from the image
├── pyproject.toml                             [build] package metadata, pinned dependencies, tool config
├── requirements.lock                          [generated] resolved lockfile
├── Dockerfile                                 [build] multi-stage: builder + slim runtime, non-root
├── docker-compose.yml                         [build] api + db (pgvector/pgvector:pg16)
├── Makefile                                   [build] POSIX shortcuts (migrate, ingest, eval, test)
├── tasks.ps1                                  [build] Windows equivalents
│
├── docs/                                      [now]   design + operating documents
│   ├── api-contract.md                        [now]
│   ├── data-model.md                          [now]
│   ├── ingestion.md                           [now]
│   ├── retrieval-and-answering.md             [now]
│   ├── failure-handling.md                    [now]
│   ├── evaluation.md                          [now]
│   ├── testing.md                             [now]
│   ├── observability.md                       [now]
│   ├── security-and-privacy.md                [now]
│   ├── deployment-and-runbook.md              [now]
│   ├── milestones.md                          [now]
│   ├── demo-script.md                         [now]
│   ├── risk-register.md                       [now]
│   ├── interview-notes.md                     [now]
│   ├── decisions.md                           [now]   ADR-001 … ADR-012
│   ├── openapi.yaml                           [now]   machine-readable API contract
│   ├── diagrams/
│   │   ├── architecture.mmd                   [now]
│   │   ├── ingest-sequence.mmd                [now]
│   │   ├── query-sequence.mmd                 [now]
│   │   ├── data-model.mmd                     [now]
│   │   └── circuit-breaker.mmd                [now]
│   └── templates/
│       ├── eval-report-template.md            [now]
│       └── incident-template.md               [now]
│
├── corpus/
│   ├── README.md                              [now]   include/exclude rules, provenance, refresh
│   ├── manifest.schema.json                   [now]   manifest contract
│   └── snapshot/                              [generated] optional portable corpus for image builds
│
├── evals/
│   ├── README.md                              [now]   dataset rules, metrics, how to run
│   ├── dataset.schema.json                    [now]   eval-case contract
│   ├── datasets/
│   │   ├── smoke.jsonl                        [fixture] 12–15 fast gate cases
│   │   └── golden.jsonl                       [fixture] ≥ 80 labelled cases
│   └── reports/
│       └── <YYYY-MM-DD>-<commit>/             [generated] summary.md + results.json
│
├── db/
│   ├── README.md                              [build] migration procedure and ordering
│   └── migrations/
│       ├── 001_init.sql                       [build] extension, tables, constraints
│       ├── 002_indexes.sql                    [build] HNSW, FTS, btree indexes
│       └── 003_seed_index_state.sql           [build] single-row state bootstrap
│
├── src/
│   └── sourceline/
│       ├── __init__.py                        [build] version only
│       ├── main.py                            [build] `app = create_app()` for uvicorn
│       ├── config.py                          [build] pydantic-settings, profile derivation, validation
│       ├── errors.py                          [build] typed application errors + HTTP mapping
│       ├── ingest.py                          [build] CLI entry: `python -m sourceline.ingest`
│       ├── migrate.py                         [build] CLI entry: `python -m sourceline.migrate`
│       ├── eval.py                            [build] CLI entry: `python -m sourceline.eval`
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py                         [build] create_app: routers, middleware, lifespan
│       │   ├── deps.py                        [build] request-scoped services, auth, settings
│       │   ├── middleware.py                  [build] request-id, body limit, access log
│       │   ├── errors.py                      [build] exception handlers → error envelope
│       │   ├── routes_query.py                [build] POST /v1/query (+ /stream reserved)
│       │   ├── routes_documents.py            [build] GET /v1/documents, /v1/citations
│       │   ├── routes_health.py               [build] /v1/health, /v1/ready, /v1/stats
│       │   └── routes_admin.py                [build] reindex, run status
│       │
│       ├── domain/                            [build] pure functions, no I/O
│       │   ├── __init__.py
│       │   ├── models.py                      [build] dataclasses: Document, Chunk, Evidence, CitationSet
│       │   ├── corpus.py                      [build] discovery rules, doc metadata, hashing
│       │   ├── chunking.py                    [build] Markdown structural chunker
│       │   ├── tokens.py                      [build] token counting + budget arithmetic
│       │   ├── prompt.py                      [build] static skeleton, slots, render, sanitise
│       │   ├── citations.py                   [build] marker assignment + validation
│       │   ├── abstention.py                  [build] pre/post-generation policy
│       │   └── validation.py                  [build] schema + sentence coverage helpers
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── query.py                       [build] orchestration, no FastAPI imports
│       │   ├── ingest.py                      [build] plan/diff/embed/upsert/prune/report
│       │   ├── documents.py                   [build] read-side document/citation queries
│       │   └── eval_runner.py                 [build] run dataset, score, attribute failures
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py                        [build] EmbeddingProvider, ChatProvider protocols
│       │   ├── openai_compatible.py           [build] one adapter for OpenAI/Ollama/Azure-compatible
│       │   └── fake.py                        [build] deterministic embeddings + scripted chat
│       │
│       ├── resilience/
│       │   ├── __init__.py
│       │   ├── errors.py                      [build] ErrorKind, ClassifiedError
│       │   ├── classify.py                    [build] status/exception → (kind, retryable)
│       │   ├── retry.py                       [build] policy, full jitter, Retry-After, deadlines
│       │   ├── breaker.py                     [build] CLOSED/OPEN/HALF_OPEN state machine
│       │   ├── deadline.py                    [build] monotonic budget, remaining-time checks
│       │   └── ratelimit.py                   [build] in-memory token bucket per client/IP
│       │
│       ├── persistence/
│       │   ├── __init__.py
│       │   ├── pool.py                        [build] psycopg_pool lifecycle, timeouts
│       │   ├── repositories.py                [build] all SQL: documents, chunks, runs, logs
│       │   ├── migrations.py                  [build] checksummed migration runner
│       │   └── sql.py                         [build] named SQL constants (parameterized only)
│       │
│       └── observability/
│           ├── __init__.py
│           ├── logging.py                     [build] JSON formatter, redaction
│           ├── metrics.py                     [build] Prometheus registry + helpers
│           └── timing.py                      [build] stage timer context manager
│
├── static/                                    [build] demo UI, no build step
│   ├── index.html
│   ├── app.js
│   └── styles.css
│
├── scripts/
│   ├── build_corpus_snapshot.py               [build] copy included docs for container builds
│   ├── check_no_frameworks.py                 [build] CI guard: forbid banned imports
│   └── fresh_machine_check.ps1                [build] README acceptance checklist
│
├── tests/
│   ├── conftest.py                            [build] settings, fake clock/RNG, DB fixture
│   ├── unit/
│   │   ├── test_chunking.py                   [build] structure, fences, tables, line ranges
│   │   ├── test_tokens_budget.py              [build] accounting and overflow
│   │   ├── test_prompt.py                     [build] skeleton, slots, injection, ordering
│   │   ├── test_citations.py                  [build] contiguous markers, validation, coverage
│   │   ├── test_abstention.py                 [build] floor/model/validation paths
│   │   ├── test_classify.py                   [build] taxonomy table
│   │   ├── test_retry.py                      [build] jitter bounds, Retry-After, deadline
│   │   ├── test_breaker.py                    [build] state transitions
│   │   └── test_config.py                     [build] profile derivation, bad config
│   ├── integration/
│   │   ├── test_migrations.py                 [build] idempotent apply, checksum mismatch
│   │   ├── test_repositories.py               [build] SQL, constraints, pagination
│   │   ├── test_ingest_idempotency.py         [build] 0 calls, edit, prune, delete
│   │   ├── test_ingest_partial_failure.py     [build] old version survives
│   │   ├── test_retrieval_filters.py          [build] pre-filter, profile guard, tie-break
│   │   └── test_logs_retention.py             [build] 30-day cleanup query
│   ├── contract/
│   │   ├── test_query_api.py                  [build] schema, citations, abstention, debug
│   │   ├── test_error_envelope.py             [build] every mapped error, request id
│   │   ├── test_documents_api.py              [build] list/detail/citation resolution
│   │   └── test_admin_api.py                  [build] auth, idempotency, conflict
│   ├── chaos/
│   │   ├── test_provider_429.py               [build] Retry-After honoured, capped
│   │   ├── test_provider_timeout.py           [build] 504 at deadline
│   │   ├── test_breaker_open.py               [build] 503 + Retry-After
│   │   ├── test_llm_down.py                   [build] extractive degraded answer
│   │   └── test_db_down.py                    [build] readiness/query fail closed
│   ├── e2e/
│   │   ├── test_ask_and_cite.py               [build] seed → ask → citation lines match
│   │   ├── test_unanswerable.py               [build] no LLM call, abstain
│   │   └── test_ui_smoke.py                   [build] page loads, form present
│   └── fixtures/
│       ├── corpus/                            [fixture] small markdown tree with known answers
│       ├── recorded/                          [fixture] fake provider responses (JSON)
│       └── golden_smoke.jsonl                 [fixture] copy/symlink of smoke set
│
└── .github/
    └── workflows/
        └── ci.yml                             [build] ruff · mypy · pytest · eval smoke · docker build
```

---

## 1. Layer rules

| Layer | May import | Must never import | Why |
|---|---|---|---|
| `api` | `services`, `config`, `errors`, `observability` | SQL, `psycopg`, provider SDKs | HTTP concerns stay thin |
| `services` | `domain`, `providers`, `persistence`, `resilience`, `observability` | `fastapi`, `starlette` | Testable without HTTP |
| `domain` | stdlib, `domain` | anything I/O | Pure, deterministic, fast tests |
| `providers` | `resilience`, `errors`, provider SDK/httpx | `services`, `persistence` | One capability each |
| `persistence` | `pool`, `errors` | `services`, `providers`, `domain` prompt code | SQL is isolated |
| `resilience` | stdlib | app layers | Reusable primitive |
| `observability` | stdlib, metrics client | app layers | No control-flow coupling |
| `tests` | anything (via public interfaces) | private helpers where avoidable | Tests document the contract |

**One-way flow.** A pull request that adds `fastapi` to `services/` or `psycopg` to `api/` is
rejected in review. `scripts/check_no_frameworks.py` additionally rejects banned RAG-framework
imports anywhere in `src/`.

---

## 2. Naming conventions

| Kind | Convention | Example |
|---|---|---|
| Python module | `snake_case` | `retrieval_and_answering` is a doc; code uses `query.py` |
| Class | `PascalCase` | `QueryService`, `CircuitBreaker` |
| Function | `snake_case`, verb-first | `assemble_prompt`, `classify_error` |
| Constant | `UPPER_SNAKE` | `DEFAULT_CONTEXT_BUDGET` |
| DB table | plural `snake_case` | `documents`, `chunks`, `query_logs` |
| DB column | `snake_case`; FK `<entity>_id` | `doc_id`, `chunk_id` |
| Env var | `SOURCELINE_` prefix for app settings | `SOURCELINE_LLM_MODEL` |
| JSON field | `snake_case` | `request_id`, `abstained` |
| API path | lowercase, `/v1/...` | `/v1/query`, `/v1/admin/reindex` |
| Error code | `snake_case` | `index_profile_mismatch` |
| Request ID | `req_` + 32 hex | `req_9f2c…` |
| Run ID | `run_` + 32 hex | `run_4a1e…` |
| Chunk ID | `c_` + 24 hex (content-addressed) | `c_7b1e…` |
| Document ID | POSIX relative path | `phase-03-…/topic-25-pgvector/notes.md` |
| Citation marker | contiguous integer `[n]` | `[1]`, `[2]` |
| Profile key | pipe-separated, versioned | `markdown-h2-v1|1200|150|text-embedding-3-small|1536` |

**No abbreviations that hide meaning.** `cfg` → `config`, `req` → `request`, `emb` → `embedding`,
except the stable external prefixes above.

---

## 3. Generated vs hand-written

| Path | Rule |
|---|---|
| `src/**`, `tests/**`, `db/migrations/**`, `static/**`, `scripts/**` | Hand-written; reviewed like production code |
| `docs/**`, root `*.md`, `.env.example`, schemas | Hand-written design artifacts (this blueprint) |
| `requirements.lock` | Generated by the lock tool; committed |
| `evals/reports/**` | Generated; commit the `summary.md` and small `results.json` |
| `corpus/snapshot/**` | Generated; ignored by default, produced for image builds |
| `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.venv`, `.env` | Never committed |
| `docs/openapi.yaml` | **Hand-maintained source of truth**; runtime `/openapi.json` must match it |
| `static/**` | Hand-written; no bundler, no `node_modules` |

---

## 4. What is committed now (blueprint)

```text
README.md
project_requirements.md
architecture.md
project_folder_hierarchy.md
.env.example
docs/** (including diagrams, templates, openapi.yaml)
corpus/README.md
corpus/manifest.schema.json
evals/README.md
evals/dataset.schema.json
```

No `src/`, `tests/`, `db/`, `static/` yet. Creating empty directories is noise; the implementation
milestones create each path with its first real file and test.

---

## 5. Test tree mirrors the layers

| Source | Test home | Style |
|---|---|---|
| `domain/chunking.py` | `tests/unit/test_chunking.py` | Pure snapshot/property tests |
| `domain/prompt.py` | `tests/unit/test_prompt.py` | Slot/injection/budget |
| `resilience/*` | `tests/unit/test_retry.py`, `test_breaker.py` | Fake clock, no sleeps |
| `persistence/*` | `tests/integration/*` | Real Postgres (service container or local) |
| `api/*` | `tests/contract/*` | FastAPI `TestClient`, fake services |
| Cross-layer failures | `tests/chaos/*` | Injected provider/DB faults |
| Reviewer path | `tests/e2e/*` | Seed → query → citation resolution |

Integration tests must skip with a clear message when `DATABASE_URL` is absent, but CI always sets
it. Unit and contract tests must run with no network and no database.

---

## 6. Configuration and secrets

- `.env.example` is committed with placeholders only; `.env` is ignored.
- The app reads settings once at startup; request handlers receive a frozen settings object.
- The profile key is derived, never hand-set inconsistently. A startup check compares it to
  `index_state.profile_key`.
- Secrets (`SOURCELINE_OPENAI_API_KEY`, `SOURCELINE_ADMIN_TOKEN`, `SOURCELINE_DATABASE_URL`) are
  never logged, never returned in errors, and never included in eval reports.
- CI uses dummy values; chaos/contract tests use fake providers, not real keys.

---

## 7. Documentation map

| Reader question | Document |
|---|---|
| What is this and how do I run it? | `README.md` |
| What exactly must it do? | `project_requirements.md` |
| How is it put together? | `architecture.md` |
| Where does each file go? | this file |
| What does the API look like? | `docs/api-contract.md` + `docs/openapi.yaml` |
| What is stored? | `docs/data-model.md` |
| How is the corpus ingested? | `docs/ingestion.md` |
| How are answers grounded? | `docs/retrieval-and-answering.md` |
| What happens when a provider fails? | `docs/failure-handling.md` |
| How is quality measured? | `docs/evaluation.md` |
| How is it tested? | `docs/testing.md` |
| How is it operated? | `docs/observability.md`, `docs/deployment-and-runbook.md` |
| Why these choices? | `docs/decisions.md` |
| How do I demo it? | `docs/demo-script.md` |

# Architecture — Sourceline

**Scope:** the v1 portfolio build. This document describes the system that the implementation must
produce; it contains no application code.

Companion diagrams (Mermaid source, rendered by GitHub):

- [`docs/diagrams/architecture.mmd`](docs/diagrams/architecture.mmd) — component view
- [`docs/diagrams/ingest-sequence.mmd`](docs/diagrams/ingest-sequence.mmd) — ingestion sequence
- [`docs/diagrams/query-sequence.mmd`](docs/diagrams/query-sequence.mmd) — query sequence
- [`docs/diagrams/data-model.mmd`](docs/diagrams/data-model.mmd) — entity relationships
- [`docs/diagrams/circuit-breaker.mmd`](docs/diagrams/circuit-breaker.mmd) — breaker states

---

## 1. Design goals

1. **Evidence first.** Retrieval and citation integrity are the product; prose is the presentation.
2. **Every stage observable.** A wrong answer must be attributable to retrieval, ranking, or generation.
3. **Idempotent by construction.** Re-running ingestion is boring: no duplicates, no wasted embeddings.
4. **Fail visibly and gracefully.** No silent truncation, no unlabelled fallback, no 500 for a provider outage.
5. **Boring infrastructure.** One Postgres, one API process, raw SQL, no distributed system.
6. **Reviewable in ten minutes.** Docker Compose, a seeded corpus, a demo UI, and a README that works.

**Constraints:** hand-written application code; pgvector required; one active embedding profile;
offline test suite; Windows developer, portable deployment.

---

## 2. System context (C4 level 1)

```text
                    ┌──────────────────────────────────────────────┐
                    │  Curriculum corpus (this repository)         │
                    │  38 Markdown docs · 83k words · git history  │
                    └──────────────────────┬───────────────────────┘
                                           │ files
                    ┌──────────────────────▼───────────────────────┐
                    │  Ingestion CLI / admin reindex job           │
                    └──────────────────────┬───────────────────────┘
                                           │ batches
┌──────────┐    HTTPS/JSON    ┌────────────▼─────────────┐   SQL    ┌─────────────────────┐
│ Reader   │ ───────────────► │  Sourceline API          │ ───────► │ PostgreSQL 16 +     │
│ (browser │ ◄─────────────── │  FastAPI + static UI     │ ◄─────── │ pgvector            │
│  or curl)│   answer+cites   └──────┬──────────┬────────┘          └─────────────────────┘
└──────────┘                         │          │
                                     │ HTTPS    │ HTTPS
                              ┌──────▼───┐  ┌───▼────────┐
                              │Embedding │  │ Chat LLM   │
                              │ provider │  │ provider   │
                              └──────────┘  └────────────┘

┌───────────────┐   reads JSONL + calls API/in-process   ┌──────────────────────┐
│ Eval runner   │ ──────────────────────────────────────► │ Golden set + reports │
└───────────────┘                                        └──────────────────────┘
```

**External dependencies:** an OpenAI-compatible embeddings endpoint and chat endpoint. The provider
interface is narrow enough to point at OpenAI, Azure OpenAI, or a local Ollama server without changing
the query path. No other network dependency exists at runtime.

---

## 3. Container / component view

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                                      API process                                         │
│                                                                                          │
│  ┌────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ HTTP layer                                                                         │  │
│  │  middleware: request-id · access-log · body-limit · rate-limit · error-envelope    │  │
│  │  routers:    /v1/query · /v1/documents · /v1/citations · /v1/ready · /v1/admin     │  │
│  │  static:     / (demo UI) · /docs (Swagger) · /metrics (internal)                  │  │
│  └───────────────┬──────────────────────────────┬─────────────────────────────────────┘  │
│                  │                              │                                        │
│  ┌───────────────▼──────────────┐  ┌────────────▼─────────────────────────────────────┐  │
│  │ QueryService                 │  │ IngestService / DocumentService                  │  │
│  │  1 validate + resolve profile│  │  1 discover corpus + manifest                    │  │
│  │  2 embed query               │  │  2 diff against indexed documents                │  │
│  │  3 retrieve candidates       │  │  3 parse → chunk → embed → upsert → prune        │  │
│  │  4 dedupe → order → budget   │  │  4 update index state + run report               │  │
│  │  5 generate structured answer│  └────────────┬─────────────────────────────────────┘  │
│  │  6 validate citations        │               │                                        │
│  │  7 abstain or respond        │               │                                        │
│  └───────┬──────────────┬───────┘               │                                        │
│          │              │                       │                                        │
│  ┌───────▼──────────────▼───────────────────────▼─────────────────────────────────────┐  │
│  │ Domain (pure, no I/O)                                                              │  │
│  │  corpus rules · markdown chunker · token budget · prompt skeleton · dedupe ·       │  │
│  │  ordering · citation map · sentence validator · abstention policy · error taxonomy │  │
│  └───────┬────────────────────────────────────────────────────────────────────────────┘  │
│          │                                                                               │
│  ┌───────▼────────────────┐  ┌───────────────────────┐  ┌─────────────────────────────┐  │
│  │ Providers              │  │ Resilience            │  │ Persistence                 │  │
│  │  EmbeddingProvider     │  │  classify_error       │  │  psycopg pool               │  │
│  │  ChatProvider          │  │  retry_call + jitter  │  │  repositories (raw SQL)     │  │
│  │  Fake* for tests       │  │  Retry-After parser   │  │  migrations                 │  │
│  │  OpenAI-compatible     │  │  CircuitBreaker       │  │  transaction per document   │  │
│  └────────────────────────┘  │  Deadline / bulkhead  │  └──────────────┬──────────────┘  │
│                              └───────────────────────┘                 │                 │
└────────────────────────────────────────────────────────────────────────┼─────────────────┘
                                                                         │
                                                                         ▼
                                                    ┌─────────────────────────────────────┐
                                                    │ PostgreSQL 16 + pgvector            │
                                                    │ documents · chunks (HNSW + FTS)     │
                                                    │ ingest_runs · query_logs · index_state │
                                                    │ idempotency_keys · migrations       │
                                                    └─────────────────────────────────────┘
```

### 3.1 Component responsibilities

| Component | Responsibility | Must not do |
|---|---|---|
| **HTTP layer** | Parse/validate requests, auth, rate limits, request IDs, error envelope, static UI | Business logic, SQL, provider calls |
| **QueryService** | Orchestrate embed → retrieve → assemble → generate → validate → abstain | Import FastAPI, format HTTP errors |
| **IngestService** | Discover, diff, chunk, embed, upsert, prune, report | Serve queries |
| **Domain** | Pure functions: chunking, token accounting, prompt rendering, citation validation | I/O, network, DB, clock unless injected |
| **Providers** | One narrow method per capability (`embed`, `chat`), normalize provider errors | Retry policy, prompt construction, logging secrets |
| **Resilience** | Classify, retry, backoff/jitter, `Retry-After`, breaker, deadline, rate limit | Know about RAG concepts |
| **Persistence** | Parameterized SQL, transactions, migrations, row mapping | Embedding or LLM calls |
| **Observability** | Structured logs, metrics, timings, redaction | Change control flow |
| **Eval runner** | Load JSONL, execute queries, score, report | Run in the request path |

### 3.2 Dependency rule

```text
api ──► services ──► domain
 │          │
 │          ├──► providers ──► resilience
 │          ├──► persistence ──► PostgreSQL
 │          └──► observability
 └──► config / errors
```

Arrows point in the direction of imports. `domain` imports nothing from the application except its
own types. `providers` never import `services`. `persistence` never imports `providers`. Circular
imports are a review failure.

---

## 4. Query path

### 4.1 Sequence

```text
Client            API              QueryService        Postgres         Embed API        Chat API
  │  POST /v1/query  │                   │                │                 │               │
  ├─────────────────►│                   │                │                 │               │
  │                  │ validate, auth,   │                │                 │               │
  │                  │ rate-limit, req-id│                │                 │               │
  │                  ├──────────────────►│                │                 │               │
  │                  │                   │ ready/profile? │                 │               │
  │                  │                   ├───────────────►│                 │               │
  │                  │                   │◄───────────────┤                 │               │
  │                  │                   │ embed(question)│                 │               │
  │                  │                   ├────────────────┼────────────────►│               │
  │                  │                   │◄───────────────┼─────────────────┤               │
  │                  │                   │ vector search  │                 │               │
  │                  │                   │ (candidate_k)  │                 │               │
  │                  │                   ├───────────────►│                 │               │
  │                  │                   │◄───────────────┤                 │               │
  │                  │                   │ dedupe/order/  │                 │               │
  │                  │                   │ budget/citations                 │               │
  │                  │                   │                │                 │               │
  │                  │                   │ no evidence ───┼──► abstain (no LLM call)        │
  │                  │                   │                │                 │               │
  │                  │                   │ chat(structured)                 │               │
  │                  │                   ├────────────────┼─────────────────┼──────────────►│
  │                  │                   │◄───────────────┼─────────────────┼───────────────┤
  │                  │                   │ validate schema/citations        │               │
  │                  │                   │ (one repair)   │                 │               │
  │                  │◄──────────────────┤                │                 │               │
  │◄─────────────────┤  answer + cites   │                │                 │               │
  │                  │  log query event  │                │                 │               │
```

### 4.2 Numbered flow and failure branches

1. **Admission.** Request ID assigned/echoed; body size, JSON schema, question length, `top_k`,
   `candidate_k`, filters validated. Unknown fields rejected. Rate limit checked.
2. **Readiness.** Database reachable, migrations current, `index_state.status=ready`, non-empty
   index, and request profile equals active profile. Failure → `503 index_not_ready` /
   `index_profile_mismatch` with `Retry-After`.
3. **Query embedding.** Same model/dimensions/prefix as documents. Provider call goes through the
   breaker and retry wrapper. If the breaker is open and lexical fallback is enabled → degraded
   retrieval; otherwise `503 upstream_unavailable`.
4. **Retrieval.** One SQL statement over `chunks JOIN documents`, pre-filtered by phase/topic/doc
   type, ordered by cosine distance, limited to `candidate_k` (default 40). `hnsw.ef_search`
   set per transaction (default 80). Zero-vector queries fail closed.
5. **Assembly.** Exact/near dedupe; sandwich ordering; token budget; static prompt skeleton;
   contiguous markers; source metadata per block. Assembly report kept for diagnostics.
6. **Pre-generation abstention.** If no candidates, all scores below the calibrated floor, or the
   evidence budget fits zero chunks → `abstained=true`, `reason=no_relevant_evidence`, no chat call.
7. **Generation.** Chat provider returns structured JSON. Schema failure → one repair request. If
   the breaker is open → labelled extractive fallback (top sentences from top chunks) or `503`,
   depending on configuration; never an unlabelled answer.
8. **Validation.** Marker range check, sentence coverage check, optional weak-support heuristic.
   Failure → one repair attempt with the offending sentences and allowed markers; failure again →
   `abstained=true`, `reason=ungrounded_answer`, `grounded=false`.
9. **Response.** Answer, citations with source/line/URL/excerpt, usage, timings, index metadata,
   degraded label, request ID. Query event logged without secrets.
10. **Deadline.** The whole request has a 30 s budget; each stage checks remaining time. Exhaustion →
    `504 deadline_exceeded`; no background work continues after the response.

### 4.3 Why retrieval is one SQL statement

The candidate query is deliberately a single round trip: pre-filter, ANN order, and limit happen
together in Postgres. Doing retrieval in Python (fetch-all then sort) would hide index behaviour and
break at scale. It also makes the `EXPLAIN` check meaningful in tests.

---

## 5. Ingestion path

### 5.1 Sequence

```text
Operator        CLI/IngestService      Corpus FS        Embed API        Postgres
  │ ingest --root │                       │                │               │
  ├──────────────►│ acquire advisory lock │                │               │
  │               ├──────────────────────►│                │               │
  │               │ discover + manifest   │                │               │
  │               │◄──────────────────────┤                │               │
  │               │ plan: new/changed/    │                │               │
  │               │ unchanged/deleted/    │                │               │
  │               │ profile-changed       │                │               │
  │               │                       │                │               │
  │               │ for each changed doc: │                │               │
  │               │  parse → chunk        │                │               │
  │               │  embed batches        │                │               │
  │               ├───────────────────────┼───────────────►│               │
  │               │  BEGIN; upsert chunks;│                │               │
  │               │  delete stale;        │                │               │
  │               │  update document;     │                │               │
  │               │  COMMIT               │                │               │
  │               ├───────────────────────┼────────────────┼──────────────►│
  │               │ update index_state    │                │               │
  │               │ write run report      │                │               │
  │◄──────────────┤ release lock          │                │               │
```

### 5.2 Guarantees

- **Plan before work.** Discovery and hashing produce a diff plan; only changed documents reach the
  embedder. `--dry-run` prints the plan and exits.
- **Per-document transaction.** A failure rolls back that document only; previously indexed versions
  remain queryable. The run is marked `partial`, not `success`.
- **Content-addressed chunks.** Unchanged chunks keep their IDs; changed/moved text produces new IDs;
  stale IDs are deleted by set difference. No orphan tail.
- **Profile invalidation.** A model/dimension/chunker/size change marks every document
  `profile_changed` and rebuilds. One profile per index; mixed profiles fail readiness.
- **Locking.** `pg_try_advisory_lock` prevents concurrent ingestion. A second run exits 5.
- **Audit.** `ingest_runs` stores mode, scope, counts, duration, commit, profile, status, and error.

### 5.3 Index build

HNSW is built/maintained by pgvector on insert. For a full rebuild at this corpus size, the run
creates the index after bulk load (or drops/recreates it) to avoid incremental-build overhead. The
blueprint recommends: load → `ANALYZE` → create HNSW with `m=16, ef_construction=64` → verify counts
→ mark `index_state.ready`. A future blue/green profile rebuild is described in §11.

---

## 6. Storage

| Store | Contents | Notes |
|---|---|---|
| `documents` | One row per source file: path, title, phase/topic, hash, commit, counts | Manifest for freshness and diff |
| `chunks` | Text, heading path, line range, token count, embedding, profile | HNSW + FTS indexes |
| `index_state` | Single row: active profile, status, built_at, counts | Readiness contract |
| `ingest_runs` | Run history and stats | 90-day retention |
| `query_logs` | Four sets, timings, tokens, outcome | 30-day retention |
| `idempotency_keys` | Admin reindex replay protection | 24-hour TTL |
| `schema_migrations` | Applied migrations + checksum | Startup/readiness check |

Detailed columns, constraints, and indexes are in [`docs/data-model.md`](docs/data-model.md).

---

## 7. Deployment topology

### 7.1 Local reviewer topology (primary)

```text
docker compose
┌───────────────────────────────┐        ┌────────────────────────────────────┐
│ api container                 │  SQL   │ db container                       │
│  uvicorn :8000                │───────►│  pgvector/pgvector:pg16            │
│  static UI + /docs            │        │  volume: sourceline_pgdata         │
│  mounts repo root at /corpus  │        │  healthcheck: pg_isready           │
│  env from .env                │        └────────────────────────────────────┘
└──────────────┬────────────────┘
               │ HTTPS
        ┌──────▼───────┐   ┌──────────────┐
        │ Embedding API│   │ Chat API     │
        └──────────────┘   └──────────────┘
```

The corpus is mounted read-only from the repository root (`../..` relative to the project folder).
No corpus copy is required for local use. One `docker compose up` plus a migration and an ingest is
the reviewer path.

### 7.2 Hosted demo topology (optional, recommended)

```text
Internet ──► API container (Fly.io / Render / small VM)
                 │ private network
                 ▼
             Managed Postgres with pgvector
                 │
                 ├── corpus snapshot baked into the image at build time
                 └── secrets injected by the platform

Ingest: release step or one-off admin job, not on every request.
Controls: per-IP rate limit, daily spend cap, admin token disabled publicly,
          no raw SQL console, logs retained 7 days.
```

The hosted demo exists so a reviewer can try the service without a key. It is not a production
multi-tenant deployment. Cold starts are acceptable if the UI shows a loading state.

### 7.3 Runtime ports and health

| Port | Purpose | Exposure |
|---|---|---|
| `8000` | HTTP API + UI | Public (demo) / private (local) |
| `5432` | Postgres | Compose-internal only; never public |
| `/v1/health` | Liveness (no dependencies) | Platform probe |
| `/v1/ready` | Readiness (DB, index, profile) | Platform probe |

---

## 8. Trust boundaries and threat model summary

```text
 UNTRUSTED                SEMI-TRUSTED                 TRUSTED
┌──────────────┐   ┌────────────────────────┐   ┌─────────────────────────┐
│ HTTP client  │   │ Corpus Markdown        │   │ Application code        │
│ question,    │   │ (authored, but may     │   │ DB credentials          │
│ filters,     │   │ contain injection or   │   │ Provider API keys       │
│ headers      │   │ stale claims)          │   │ Admin token             │
└──────┬───────┘   └───────────┬────────────┘   └────────────┬────────────┘
       │ validation            │ sanitise + treat as data     │
       ▼                       ▼                              ▼
  rate limit, schema,     prompt data slot,             least-privilege DB role,
  length caps             tag neutralisation            secrets from env
```

- **Client input** is untrusted: validate schema/length, parameterize SQL, never interpolate into
  prompts as instructions.
- **Corpus text** is semi-trusted: it is authored here, but the pipeline must still treat it as data
  (tag neutralisation, instruction-line stripping) because a future corpus adapter may ingest
  third-party documents.
- **Provider responses** are untrusted: validate JSON schema, citation ranges, and lengths.
- **Admin endpoints** are privileged: bearer token, constant-time compare, separate rate limit, no
  public exposure in the hosted demo.
- **Secrets** live only in environment variables; logs and errors are redacted.

Full controls and residual risks: [`docs/security-and-privacy.md`](docs/security-and-privacy.md).

---

## 9. Cross-cutting concerns

### 9.1 Configuration and startup

- `pydantic-settings` loads `SOURCELINE_*`/documented env vars; unknown or missing required values
  fail startup with a readable error (not a traceback dump).
- The profile key is derived from model/dimensions/chunker/size config and compared to
  `index_state.profile_key` at readiness. Mismatch is a first-class error.
- The app refuses to start if SDK automatic retries are enabled alongside the owned retry policy
  (prevents multiplicative retries).
- Startup does not embed or ingest; it only opens the pool and checks configuration.

### 9.2 Resilience

Every provider/SQL call goes through the same primitives:

```text
classify_error → retry_call(policy, deadline) → circuit breaker → typed error → mapped HTTP response
```

Policy details, degraded modes, and fault-injection tests: [`docs/failure-handling.md`](docs/failure-handling.md).

### 9.3 Observability

- JSON logs with `request_id`, route, status, stage timings, retry count, breaker state, profile,
  abstention, grounded, degraded.
- Prometheus metrics for golden signals plus RAG-specific counters (citation invalid, abstention,
  index age, ingest counts).
- Optional OpenTelemetry spans around embed/retrieve/generate/validate.
- Query log stores the four sets for diagnosis without storing secrets or full prompts.

Details: [`docs/observability.md`](docs/observability.md).

### 9.4 Evaluation

The eval runner is a first-class component, not a notebook afterthought: JSONL golden cases, the
same service code path (in-process or HTTP), per-category metrics, attribution of failures to
retrieval/ranking/generation, and a committed report with commit/profile metadata.

Details: [`docs/evaluation.md`](docs/evaluation.md).

---

## 10. Failure boundaries at a glance

| Stage | What breaks | How the system notices | What it does |
|---|---|---|---|
| Corpus discovery | file skipped/renamed | document count vs manifest; run diff | fail run on unexpected zero/duplicate; report |
| Chunking | answer split, code fence cut | chunk invariant tests; oversize flags | structural split; hard-cap warning |
| Embedding | truncation, zero vector, provider down | token guard; norm check; breaker/retry | reject/flag; retry; degraded lexical at query |
| Storage | partial write, stale rows, missing index | per-doc transaction; counts; readiness | rollback; prune; 503 index_not_ready |
| Query embedding | empty/OOV, wrong profile | zero-norm check; profile check | 400/503; never search with a bad vector |
| Retrieval | ANN recall, filters drop all | recall eval; result counts | tune ef_search; pre-filter; abstain |
| Assembly | gold dropped/truncated, prompt injection | debug drop reasons; citation validator | record drops; fail closed; sanitise |
| Generation | hallucination, bad citation, refusal | sentence coverage; marker validation; eval | repair once; abstain; extractive fallback |
| Operations | stale index, cost spike, key leak | index age; spend metrics; log redaction | alert; reindex; rotate |

This table is the implementation-level version of topic 28's boundary habit. Each row gets a probe
and a runbook link.

---

## 11. Scaling path

| Scale | Change | Why |
|---|---|---|
| **v1 (this build)** | One API process, one Postgres, in-memory rate limit/breaker | Simplest thing that demonstrates the engineering |
| 10× traffic | Redis for rate limits/idempotency/breaker state; 2–4 API workers; connection pool sizing | In-memory state is per process |
| 10× corpus | Separate ingest worker; batch queue; `COPY` staging; build HNSW after load | Ingest competes with queries |
| 100× corpus | Partition by phase/source; read replica for retrieval; consider a dedicated vector store | Postgres still viable with tuning; measure before migrating |
| Quality step | Hybrid BM25+dense + RRF (topic 30), cross-encoder rerank (topic 31) | Exact names/codes and top-k precision |
| Model change | Blue/green table or schema, re-embed, eval, alias switch | One profile per index; no mixed vectors |

---

## 12. Deliberately simple (and why)

- **No LangChain/LlamaIndex.** The point is to show the pipeline, not a framework call.
- **No ORM.** Six tables and a handful of queries; raw SQL is clearer and demonstrates pgvector.
- **No queue.** Ingestion is a CLI/admin job at this scale; advisory locking is enough.
- **No learned reranker.** Deterministic ordering first; reranking is a Phase 4 upgrade with its own eval.
- **No streaming.** JSON response first; SSE is reserved but deferred.
- **No multi-tenancy.** One corpus, one profile, one deployment.
- **No claim-level NLI in production.** Deterministic citation validation now; semantic groundedness
  is measured in eval and can become a guardrail later.

These are choices, not omissions. Each has an ADR in [`docs/decisions.md`](docs/decisions.md).

---

## 13. Architecture decisions (summary)

| ADR | Decision |
|---|---|
| 001 | PostgreSQL + pgvector over a dedicated vector database |
| 002 | Raw SQL + psycopg over an ORM |
| 003 | Dense-only retrieval in v1; hybrid deferred |
| 004 | JSON query endpoint first; SSE reserved |
| 005 | Content-addressed chunk IDs + per-document transactions |
| 006 | One active embedding profile; reindex on change |
| 007 | Structured LLM output + deterministic citation validator |
| 008 | Fail-closed abstention over best-effort answers |
| 009 | Labelled degraded modes (extractive/lexical), not silent fallbacks |
| 010 | Corpus = this curriculum, adapter interface for future sources |
| 011 | In-memory rate limit/breaker for v1; Redis at 10× |
| 012 | Hand-written application code; infrastructure libraries only |

Full context, alternatives, and consequences: [`docs/decisions.md`](docs/decisions.md).

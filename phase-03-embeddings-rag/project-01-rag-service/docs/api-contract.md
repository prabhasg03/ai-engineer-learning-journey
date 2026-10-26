# API Contract — Sourceline v1

**Base URL:** `http://127.0.0.1:8000` locally; the hosted demo uses the same paths.
**Content type:** `application/json; charset=utf-8` for API requests/responses.
**Field naming:** `snake_case` everywhere (request, response, errors).
**Versioning:** path-versioned (`/v1`). Additive fields may appear without a version bump; clients must
ignore unknown response fields. Breaking changes require `/v2`.

The machine-readable source of truth is [`openapi.yaml`](openapi.yaml). This document explains
semantics, examples, and limits; if the two disagree, the OpenAPI file wins and this document is fixed.

---

## 1. Surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/` | public | Static demo UI |
| `GET` | `/docs` | public | Swagger UI (FastAPI) |
| `GET` | `/openapi.json` | public | Runtime schema (must match `openapi.yaml`) |
| `GET` | `/v1/health` | public | Liveness only; no dependency checks |
| `GET` | `/v1/ready` | public | Readiness: DB, migrations, index, profile |
| `GET` | `/v1/stats` | public | Aggregate counts and 24 h rates |
| `POST` | `/v1/query` | public* | Ask a question; grounded answer + citations |
| `GET` | `/v1/documents` | public | Paginated document list |
| `GET` | `/v1/documents/{doc_key}` | public | Document metadata + chunk summaries |
| `GET` | `/v1/citations/{chunk_id}` | public | Resolve a citation to its source text |
| `POST` | `/v1/admin/reindex` | admin | Plan/execute ingestion |
| `GET` | `/v1/admin/runs/{run_id}` | admin | Ingest run status and stats |
| `GET` | `/v1/admin/queries/{request_id}` | admin | Query log/diagnostic record |
| `GET` | `/metrics` | internal | Prometheus exposition (not proxied publicly) |

\* Public by default for the portfolio demo, rate-limited per client IP. Setting
`SOURCELINE_QUERY_API_KEY` requires `Authorization: Bearer <key>` for query and document endpoints.
The hosted demo keeps the public mode and enforces a daily spend cap.

`POST /v1/query/stream` is **reserved** for a later SSE implementation and returns `501
not_implemented` in v1. It appears in OpenAPI only to reserve the path; no streaming semantics are
defined in v1.

---

## 2. Authentication and authorization

| Surface | Rule |
|---|---|
| Public query/documents | No auth by default; optional bearer API key via config |
| Admin (`/v1/admin/*`) | `Authorization: Bearer <SOURCELINE_ADMIN_TOKEN>`; constant-time compare |
| Debug diagnostics | Admin auth by default; `SOURCELINE_PUBLIC_DEBUG=true` may allow `?debug=1` **only** in local/demo config. Hosted config must set it false. |
| Metrics | Bound to the app but blocked at the reverse proxy in hosted deployments |

Failures: missing/invalid token → `401 unauthorized` (never reveal whether the token exists).
An authenticated but disabled surface (e.g. admin in the hosted demo) → `403 forbidden`.

---

## 3. Common headers

| Header | Direction | Semantics |
|---|---|---|
| `X-Request-ID` | request/response | Client may supply `req_` + 32 hex; otherwise generated. Echoed on every response, including errors. |
| `X-RateLimit-Limit` | response | Requests allowed in the current window |
| `X-RateLimit-Remaining` | response | Requests left |
| `X-RateLimit-Reset` | response | Unix epoch seconds when the window resets |
| `Retry-After` | response | Seconds (or HTTP-date) for `429`, `503 dependency_*`, `503 circuit_open` |
| `Idempotency-Key` | request (admin) | Required on `POST /v1/admin/reindex`; 8–128 visible ASCII chars |
| `X-Index-Profile` | response | Active profile key (query/ready responses also include it in the body) |
| `Cache-Control` | response | `no-store` on query and diagnostics |

CORS is disabled by default. If the UI is served from the same origin (it is), no CORS is needed.
A separate frontend origin must be allow-listed explicitly.

---

## 4. `POST /v1/query`

### 4.1 Request

```json
{
  "question": "How does HNSW trade recall for speed?",
  "top_k": 6,
  "candidate_k": 40,
  "filters": {
    "phase": 3,
    "topic": 25,
    "doc_type": "notes"
  },
  "answer": {
    "max_words": 180,
    "style": "concise"
  },
  "debug": false
}
```

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `question` | string | yes | — | 3–2,000 chars after trim; no NUL/control chars except `\n\t` |
| `top_k` | integer | no | 8 | 1–20 |
| `candidate_k` | integer | no | 40 | ≥ `top_k`, ≤ 100 |
| `filters` | object | no | `{}` | Only the keys below; unknown keys → 422 |
| `filters.phase` | integer | no | null | 1–4 |
| `filters.topic` | integer | no | null | 1–64 |
| `filters.doc_type` | string | no | null | `notes`, `meta`, `readme`, `other` |
| `filters.path_prefix` | string | no | null | ≤ 200 chars; POSIX prefix; no `..` |
| `answer.max_words` | integer | no | 200 | 40–400 |
| `answer.style` | string | no | `concise` | `concise`, `detailed` |
| `debug` | boolean | no | false | Requires admin auth or the local public-debug flag |

Unknown top-level fields are rejected (`422`) so typos cannot silently change behaviour. `question`
is NFKC-normalised and whitespace-collapsed before validation; the original is not logged.

### 4.2 Response — answered

```json
{
  "request_id": "req_4f8c2a4e0b7d4f0e9a1c3b5d7e9f0a1b",
  "answer": "HNSW searches a layered proximity graph, entering at the top layer and descending ... [1][2]",
  "citations": [
    {
      "marker": 1,
      "chunk_id": "c_2f9a1c7e5b3d4a6f8e0c1d2b",
      "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
      "title": "Topic 25 — pgvector",
      "heading": "5.3 HNSW — hierarchical navigable small world graphs",
      "lines": [134, 158],
      "url": "https://github.com/<owner>/<repo>/blob/<commit>/phase-03-embeddings-rag/topic-25-pgvector/notes.md#L134-L158",
      "score": 0.6231,
      "excerpt": "HNSW builds a multi-layer graph; the upper layers are sparse long-range links ..."
    },
    {
      "marker": 2,
      "chunk_id": "c_8b1d4e6f0a2c3e5d7f9b1a3c",
      "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
      "title": "Topic 25 — pgvector",
      "heading": "5.4 Tuning ef_search and ef_construction",
      "lines": [160, 188],
      "url": "https://github.com/<owner>/<repo>/blob/<commit>/phase-03-embeddings-rag/topic-25-pgvector/notes.md#L160-L188",
      "score": 0.5874,
      "excerpt": "ef_search controls the candidate list at query time: higher values improve recall ..."
    }
  ],
  "abstained": false,
  "abstention_reason": null,
  "grounded": true,
  "degraded": null,
  "usage": {
    "prompt_tokens": 4120,
    "completion_tokens": 154,
    "total_tokens": 4274,
    "evidence_tokens": 3680,
    "budget_tokens": 6000,
    "estimated_cost_usd": 0.0018
  },
  "timings_ms": {
    "embed": 143,
    "retrieve": 21,
    "assemble": 3,
    "generate": 1840,
    "validate": 2,
    "total": 2012
  },
  "index": {
    "profile": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
    "built_at": "2026-10-26T10:12:31Z",
    "age_seconds": 3600,
    "document_count": 38,
    "chunk_count": 312,
    "source_commit": "a01637a"
  },
  "model": {
    "embedding": "text-embedding-3-small",
    "chat": "gpt-4.1-mini"
  },
  "debug": null
}
```

`answer` may contain Markdown. `citations[].excerpt` is a short (≤ 240 chars) verbatim slice for the
UI; the full text is available from `GET /v1/citations/{chunk_id}`. `url` is omitted when
`SOURCELINE_SOURCE_BASE_URL` is unset; `doc_id`, `heading`, and `lines` are always present.

### 4.3 Response — abstained

Abstention is a successful HTTP response (`200`) with a deliberate refusal. It is not an error.

```json
{
  "request_id": "req_1c2d3e4f5a6b7c8d9e0f1a2b",
  "answer": "I don't have enough evidence in the corpus to answer that.",
  "citations": [],
  "abstained": true,
  "abstention_reason": "no_relevant_evidence",
  "grounded": false,
  "degraded": null,
  "closest_sources": [
    {
      "doc_id": "phase-03-embeddings-rag/topic-28-where-rag-fails/notes.md",
      "heading": "Failure boundaries",
      "lines": [88, 104],
      "score": 0.1842
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "evidence_tokens": 0,
    "budget_tokens": 6000,
    "estimated_cost_usd": 0.0
  },
  "timings_ms": {
    "embed": 131,
    "retrieve": 18,
    "assemble": 1,
    "generate": 0,
    "validate": 0,
    "total": 151
  },
  "index": { "...": "same shape as answered" },
  "model": { "...": "same shape as answered" },
  "debug": null
}
```

`abstention_reason` values:

| Reason | Stage | Meaning |
|---|---|---|
| `no_relevant_evidence` | pre-generation | No candidate above the calibrated score floor, or zero candidates |
| `insufficient_evidence` | post-generation | The model reported that the evidence does not answer the question |
| `ungrounded_answer` | post-validation | Citation/sentence validation failed after one repair |
| `invalid_model_output` | post-generation | Structured output invalid after one repair |
| `index_empty` | readiness | Index has no chunks (usually `503` instead; see §8) |

`closest_sources` is present for pre- and post-generation abstentions when candidates existed. It
is explicitly **not** evidence for an answer; it helps the user pick a better question. It is omitted
when nothing was retrieved.

### 4.4 Debug payload (`?debug=1`)

Requires admin auth unless `SOURCELINE_PUBLIC_DEBUG=true`. Never includes the system prompt, API
keys, raw provider bodies, or full document text beyond citation excerpts.

```json
{
  "debug": {
    "retrieval": {
      "candidate_k": 40,
      "ef_search": 80,
      "returned": 31,
      "filters_applied": {"phase": 3, "topic": 25, "doc_type": "notes"},
      "top_score": 0.6231,
      "score_floor": 0.2,
      "candidates": [
        {"rank": 1, "chunk_id": "c_2f9a...", "doc_id": "phase-03.../notes.md", "heading": "5.3 HNSW", "score": 0.6231}
      ],
      "dropped": [
        {"chunk_id": "c_aa11...", "reason": "duplicate", "kept": "c_2f9a..."},
        {"chunk_id": "c_bb22...", "reason": "budget"},
        {"chunk_id": "c_cc33...", "reason": "score_floor"}
      ]
    },
    "assembly": {
      "evidence_count": 6,
      "evidence_tokens": 3680,
      "budget_tokens": 6000,
      "instruction_tokens": 212,
      "question_tokens": 12,
      "reserve_tokens": 700,
      "overhead_tokens": 84,
      "order": ["c_2f9a...", "c_8b1d..."],
      "prompt_sha256": "9c1e...",
      "citation_map": {"1": "c_2f9a...", "2": "c_8b1d..."}
    },
    "validation": {
      "citation_valid": true,
      "sentence_coverage": 1.0,
      "invalid_markers": [],
      "repair_attempted": false,
      "weak_support": []
    }
  }
}
```

`prompt_sha256` lets a reviewer correlate logs with a prompt without storing the prompt. The full
`candidates` list is capped at `candidate_k`; `dropped` is capped at 100 entries.

---

## 5. `GET /v1/health`, `/v1/ready`, `/v1/stats`

### 5.1 Health (liveness)

```json
{
  "status": "ok",
  "service": "sourceline",
  "version": "1.0.0",
  "uptime_seconds": 412
}
```

Always `200` if the process can serve HTTP. It does not touch Postgres or providers. Use it for
container liveness only.

### 5.2 Ready (readiness)

```json
{
  "status": "ready",
  "checks": {
    "database": {"status": "ok", "latency_ms": 3},
    "pgvector": {"status": "ok", "version": "0.8.0"},
    "migrations": {"status": "ok", "current": "003_seed_index_state"},
    "index": {
      "status": "ok",
      "profile": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
      "document_count": 38,
      "chunk_count": 312,
      "built_at": "2026-10-26T10:12:31Z",
      "age_seconds": 3600,
      "stale": false,
      "source_commit": "a01637a"
    },
    "providers": {
      "embedding": {"configured": true, "model": "text-embedding-3-small"},
      "chat": {"configured": true, "model": "gpt-4.1-mini"}
    }
  }
}
```

- `200` when `status` is `ready` or `degraded` (degraded means the index is usable but stale or a
  non-critical probe failed; the body says which).
- `503` when `status` is `not_ready`: DB down, migrations missing, index empty/building/failed, or
  profile mismatch. Include `reason` and `Retry-After` where meaningful.
- Provider readiness is **configuration presence**, not a live API call. A live probe would cost
  money and add latency to every orchestration check. The breaker reports live health.
- `age_seconds` is computed from `index_state.built_at`. `stale` is true when
  `SOURCELINE_MAX_INDEX_AGE_SECONDS` is configured and exceeded, or when
  `SOURCELINE_EXPECTED_COMMIT` is set and differs from `index_state.source_commit`.

### 5.3 Stats

```json
{
  "documents": 38,
  "chunks": 312,
  "index_age_seconds": 3600,
  "last_ingest": {
    "run_id": "run_...",
    "status": "success",
    "finished_at": "2026-10-26T10:12:31Z"
  },
  "queries_24h": 57,
  "abstention_rate_24h": 0.14,
  "p95_latency_ms_24h": 2104
}
```

Public aggregates only. No questions, answers, client IPs, or token spend.

---

## 6. Documents and citations

### 6.1 List documents

`GET /v1/documents?phase=3&topic=25&doc_type=notes&limit=50&cursor=<opaque>`

| Query | Type | Default | Notes |
|---|---|---|---|
| `phase` | int | null | 1–4 |
| `topic` | int | null | 1–64 |
| `doc_type` | string | null | enum |
| `limit` | int | 50 | 1–100 |
| `cursor` | string | null | Opaque; from `next_cursor` |

```json
{
  "items": [
    {
      "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
      "title": "Topic 25 — pgvector",
      "phase": 3,
      "topic": 25,
      "doc_type": "notes",
      "chunk_count": 8,
      "content_hash": "5e2c...",
      "word_count": 3180,
      "indexed_at": "2026-10-26T10:12:31Z",
      "source_url": "https://github.com/<owner>/<repo>/blob/<commit>/phase-03-embeddings-rag/topic-25-pgvector/notes.md"
    }
  ],
  "next_cursor": null,
  "total": 1
}
```

Ordering is `doc_id ASC`. The cursor encodes the last `doc_id`; it is opaque and versioned. `total`
is the count for the filtered set (acceptable at this corpus size; document the cost if the corpus
grows).

### 6.2 Document detail

`GET /v1/documents/phase-03-embeddings-rag/topic-25-pgvector/notes.md`

The `doc_key` is the POSIX relative path. The server route uses a path converter, so slashes are part
of the value; URL-encode spaces and Unicode, not the `/` separators. The server normalises the value,
rejects `..`, backslashes, absolute paths, and anything outside the corpus root. Response adds chunk
summaries (no full text):

```json
{
  "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
  "title": "Topic 25 — pgvector",
  "phase": 3,
  "topic": 25,
  "doc_type": "notes",
  "content_hash": "5e2c...",
  "word_count": 3180,
  "indexed_at": "2026-10-26T10:12:31Z",
  "source_url": "https://github.com/...",
  "chunks": [
    {
      "chunk_id": "c_2f9a...",
      "heading": "5.3 HNSW — hierarchical navigable small world graphs",
      "lines": [134, 158],
      "token_count": 284,
      "ordinal": 4
    }
  ]
}
```

404: `document_not_found`.

### 6.3 Resolve a citation

`GET /v1/citations/c_2f9a1c7e5b3d4a6f8e0c1d2b`

```json
{
  "chunk_id": "c_2f9a1c7e5b3d4a6f8e0c1d2b",
  "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
  "title": "Topic 25 — pgvector",
  "heading": "5.3 HNSW — hierarchical navigable small world graphs",
  "lines": [134, 158],
  "content": "HNSW builds a multi-layer graph ...",
  "content_hash": "9a1b...",
  "source_url": "https://github.com/.../notes.md#L134-L158"
}
```

Returns the **stored** chunk text, which is what the model saw. A 404 means the chunk was pruned by
a re-ingest; the UI falls back to the document and shows a "source changed" notice.

---

## 7. Admin reindex

### 7.1 Start a run

```http
POST /v1/admin/reindex
Authorization: Bearer <admin token>
Idempotency-Key: reindex-2026-10-26-01
Content-Type: application/json

{
  "scope": "changed",
  "prune": true,
  "dry_run": false
}
```

| Field | Type | Default | Rules |
|---|---|---|---|
| `scope` | string | `changed` | `changed` or `full` |
| `prune` | boolean | true | Remove documents absent from the corpus |
| `dry_run` | boolean | false | Plan only; no DB writes, no embedding calls |
| `confirm` | string | null | Required value `FULL_REINDEX` when `scope=full` |

- `202 Accepted` for a real run: `{"run_id": "...", "status": "queued", "plan": {...}}`.
- `200 OK` for `dry_run=true`: the plan, with no run created.
- `409 ingest_locked`: another ingest holds the advisory lock or is running.
- `422 invalid_request`: missing confirmation for a full reindex.
- `401/403`: auth failure or admin disabled.
- Replaying the same `Idempotency-Key` with the same body returns the original response and run ID.
  Reusing the key with a different body → `409 idempotency_conflict`.

The admin endpoint runs ingestion in a background thread in v1. The CLI is the canonical path for
long runs; the endpoint is for the demo/operator convenience. A process restart while a run is
`running` marks it `failed` on next startup ("interrupted"), never `success`.

### 7.2 Run status

`GET /v1/admin/runs/run_4a1e...`

```json
{
  "run_id": "run_4a1e...",
  "status": "success",
  "mode": "changed",
  "trigger": "admin",
  "started_at": "2026-10-26T10:10:00Z",
  "finished_at": "2026-10-26T10:12:31Z",
  "profile_key": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
  "source_commit": "a01637a",
  "stats": {
    "documents_seen": 38,
    "documents_new": 0,
    "documents_changed": 1,
    "documents_unchanged": 37,
    "documents_deleted": 0,
    "documents_failed": 0,
    "chunks_inserted": 2,
    "chunks_updated": 0,
    "chunks_deleted": 1,
    "chunks_reused": 310,
    "chunks_embedded": 2,
    "embedding_calls": 1,
    "embedding_tokens": 534,
    "duration_ms": 151000
  },
  "error": null
}
```

Statuses: `queued`, `running`, `success`, `partial`, `failed`, `skipped` (lock held).
On `partial`, `stats.documents_failed > 0` and `error` describes the first failure class without
secrets.

### 7.3 Query diagnostics

`GET /v1/admin/queries/req_...` returns the stored event:

```json
{
  "request_id": "req_...",
  "created_at": "2026-10-26T10:20:11Z",
  "question_sha256": "b1e2...",
  "question_redacted": "How does HNSW trade recall for speed?",
  "filters": {"phase": 3, "topic": 25},
  "retrieved": [{"chunk_id": "c_2f9a...", "score": 0.6231, "rank": 1}],
  "prompted": ["c_2f9a...", "c_8b1d..."],
  "cited": ["c_2f9a...", "c_8b1d..."],
  "abstained": false,
  "abstention_reason": null,
  "grounded": true,
  "degraded": null,
  "timings_ms": {"embed": 143, "retrieve": 21, "generate": 1840, "total": 2012},
  "usage": {"prompt_tokens": 4120, "completion_tokens": 154},
  "error_code": null
}
```

This is the diagnostic input for topic 28 attribution: retrieval miss (gold absent from `retrieved`),
ranking miss (gold in `retrieved` but absent from `prompted`), generation miss (gold in `prompted`
but answer unsupported). `question_redacted` is stored only when `SOURCELINE_LOG_QUESTIONS=true`;
otherwise it is null and only the hash remains.

---

## 8. Errors

All non-2xx responses use one envelope:

```json
{
  "error": {
    "code": "index_profile_mismatch",
    "message": "The active index was built with a different embedding profile.",
    "retryable": false,
    "request_id": "req_...",
    "details": {
      "active_profile": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
      "configured_profile": "markdown-h2-v1|1200|150|nomic-embed-text|768"
    }
  }
}
```

`message` is safe for end users. `details` is optional, allow-listed per code, and never includes
secrets, raw provider bodies, SQL, or stack traces. The request ID is always present.

| HTTP | Code | Retryable | Cause / client action |
|---:|---|---|---|
| 400 | `invalid_question` | no | Empty/overlong/control characters; rewrite |
| 400 | `invalid_filter` | no | Unsupported filter value; fix |
| 401 | `unauthorized` | no | Missing/invalid bearer token |
| 403 | `forbidden` | no | Admin/debug disabled or insufficient scope |
| 404 | `document_not_found` | no | Unknown doc ID |
| 404 | `chunk_not_found` | no | Citation pruned or unknown |
| 404 | `run_not_found` | no | Unknown run ID |
| 409 | `ingest_locked` | yes | Another ingest is running; retry after it finishes |
| 409 | `idempotency_conflict` | no | Same key, different body; use a new key |
| 413 | `payload_too_large` | no | Body > 32 KB |
| 422 | `validation_error` | no | JSON schema/type/range failure; details list fields |
| 429 | `rate_limited` | yes | Client rate limit; honour `Retry-After` |
| 500 | `internal_error` | maybe | Unclassified bug; report request ID |
| 501 | `not_implemented` | no | Reserved streaming endpoint |
| 502 | `invalid_upstream_response` | yes | Provider returned malformed JSON/schema |
| 503 | `index_not_ready` | yes | Building/empty/failed index; retry later |
| 503 | `index_profile_mismatch` | no | Reindex with the configured profile |
| 503 | `upstream_unavailable` | yes | Provider unavailable after retries; `Retry-After` |
| 503 | `upstream_rate_limited` | yes | Provider 429 exhausted; `Retry-After` capped |
| 503 | `circuit_open` | yes | Breaker open; `Retry-After` = remaining cooldown |
| 503 | `database_unavailable` | yes | Postgres/pool failure; retry |
| 503 | `budget_exhausted` | no | Hosted daily spend cap reached; retry after midnight UTC |
| 504 | `deadline_exceeded` | yes | Overall request budget exhausted |

Mapping rules:

- A provider `429` is **our** `503 upstream_rate_limited`, not a client `429`. The client is not the
  rate limiter; our rate limiter owns `429 rate_limited`.
- A provider timeout/connection reset after retries → `503 upstream_unavailable` or `504
  deadline_exceeded` if the overall budget is gone.
- Do not retry `400/401/403/404/422` from a provider; they are configuration/content bugs.
- An invalid model output after one repair is **not** a 5xx: return `200` with `abstained=true`,
  `reason=invalid_model_output` (the service succeeded in refusing).
- A validation failure after one repair is `200 abstained` with `ungrounded_answer`.

---

## 9. Limits, timeouts, and cost controls

| Limit | Value | Enforced |
|---|---:|---|
| Request body | 32 KB | Middleware, 413 |
| Question | 2,000 chars | Pydantic, 422 |
| `top_k` | 20 | Pydantic, 422 |
| `candidate_k` | 100 | Pydantic, 422 |
| Query rate | 60/min/IP, burst 10 | Token bucket, 429 |
| Concurrent queries | 5/IP, 8 global | Semaphore, 429/503 |
| Admin rate | 10/min/IP | Token bucket, 429 |
| Query deadline | 30 s | Deadline object, 504 |
| Query embed | 6 s total | Retry policy + deadline |
| Chat | 25 s total | Retry policy + deadline |
| Daily spend (hosted) | Disabled by default; hosted example $5 | Budget counter, 503 `budget_exhausted` |
| `query_logs` retention | 30 days | Maintenance job |
| `ingest_runs` retention | 90 days | Maintenance job |
| Idempotency TTL | 24 h | `idempotency_keys.expires_at` |

The hosted cap is disabled by default (`SOURCELINE_DAILY_BUDGET_USD=0`); when enabled, `budget_exhausted`
is non-retryable until the UTC day resets.

---

## 10. Idempotency and retry semantics

| Operation | Idempotent? | Client retry guidance |
|---|---|---|
| `POST /v1/query` | Read-only; safe but costs money | Retry on 429/503/504 with backoff; use the same `X-Request-ID` to correlate |
| `GET` endpoints | Yes | Retry freely |
| `POST /v1/admin/reindex` | Yes by `Idempotency-Key` | Retry the same key/body; reuse returns the original run |
| Ingest CLI | Yes by design (content-addressed chunks) | Re-run; unchanged docs cost zero embeddings |

Server-side retries are governed by [`failure-handling.md`](failure-handling.md), not by this
contract. Provider SDK retries are disabled to avoid multiplication.

---

## 11. Examples

```bash
# Health and readiness
curl -s http://127.0.0.1:8000/v1/health
curl -s http://127.0.0.1:8000/v1/ready

# Ask, with a filter
curl -s http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"When should I use HNSW instead of IVFFlat?","filters":{"phase":3,"topic":25}}'

# Diagnostics (admin token required unless local public debug)
curl -s 'http://127.0.0.1:8000/v1/query?debug=1' \
  -H "Authorization: Bearer $SOURCELINE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does HNSW trade recall for speed?","top_k":6}'

# Resolve a citation
curl -s http://127.0.0.1:8000/v1/citations/c_2f9a1c7e5b3d4a6f8e0c1d2b

# Trigger a changed-only reindex
curl -s -X POST http://127.0.0.1:8000/v1/admin/reindex \
  -H "Authorization: Bearer $SOURCELINE_ADMIN_TOKEN" \
  -H 'Idempotency-Key: demo-reindex-1' \
  -H 'Content-Type: application/json' \
  -d '{"scope":"changed","prune":true}'
```

Windows PowerShell equivalent:

```powershell
$body = @{ question = "How does HNSW trade recall for speed?"; top_k = 6 } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/query -Method Post -ContentType "application/json" -Body $body
```

---

## 12. Contract tests

The OpenAPI schema and this document are verified by `tests/contract/`:

- every documented endpoint exists with the documented method and status codes;
- response models reject unknown required fields and accept additive fields;
- every error code in the table is produced by at least one test;
- `X-Request-ID` is echoed on 2xx and 4xx/5xx;
- `Retry-After` is present on 429/503 where specified;
- citations resolve to chunks whose `doc_id`/lines match the source slice;
- debug is rejected without auth unless the local flag is set;
- admin replay returns the same run and a conflicting body returns 409.

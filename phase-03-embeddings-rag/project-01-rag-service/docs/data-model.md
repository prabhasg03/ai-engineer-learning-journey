# Data Model — Sourceline

**Database:** PostgreSQL 16 with pgvector ≥ 0.8.
**Access:** hand-written SQL through psycopg 3. No ORM, no query builder.
**Source of truth:** `db/migrations/*.sql`; this document explains the schema and invariants. If they
disagree during implementation, fix the migration and this document together.

All identifiers are `snake_case`. Timestamps are `timestamptz` in UTC. JSON is `jsonb`. Hashes are
lowercase hex SHA-256. The schema is forward-only; destructive changes require a backup and a
recorded migration.

---

## 1. Entity overview

```text
documents 1 ──── n chunks
    │                 │
    │                 └── embedding vector(1536) ── HNSW index
    │                 └── FTS index (lexical fallback)
    │
    ├── n ingest_runs (logical reference by run metadata; no FK)
    └── n query_logs  (logical reference by doc/chunk IDs in JSON; no FK)

index_state (single row) ── active profile, build status, counts
schema_migrations         ── applied migration versions
idempotency_keys          ── admin reindex replay protection
```

`ingest_runs` and `query_logs` deliberately do **not** foreign-key to `documents`/`chunks`: logs must
survive pruning, and a deleted document should not cascade-delete audit history. They store IDs as
text/JSON.

---

## 2. DDL (v1, 1536 dimensions)

### 2.1 Extension and migration ledger

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE schema_migrations (
    version     text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
```

The migration runner computes SHA-256 of each file, applies pending files in lexical order inside a
transaction, and refuses to start if an already-applied checksum differs. It takes
`pg_advisory_lock(hashtext('sourceline:migrate'))` so two containers cannot migrate concurrently.

### 2.2 Documents

```sql
CREATE TABLE documents (
    doc_id          text PRIMARY KEY,
    title           text NOT NULL,
    doc_type        text NOT NULL
                    CHECK (doc_type IN ('notes', 'meta', 'readme', 'other')),
    phase           smallint
                    CHECK (phase IS NULL OR phase BETWEEN 1 AND 4),
    topic           smallint
                    CHECK (topic IS NULL OR topic BETWEEN 1 AND 64),
    source_commit   text,
    content_hash    char(64) NOT NULL,
    byte_size       integer NOT NULL CHECK (byte_size >= 0),
    word_count      integer NOT NULL CHECK (word_count >= 0),
    chunk_count     integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    profile_key     text NOT NULL,
    indexed_at      timestamptz NOT NULL DEFAULT now(),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT documents_doc_id_is_posix_path
        CHECK (doc_id <> '' AND doc_id !~ '\\' AND doc_id !~ '(^|/)\.\.(/|$)')
);
```

`doc_id` is the POSIX relative path from the repository root, e.g.
`phase-03-embeddings-rag/topic-25-pgvector/notes.md`. It is both the identity and the source path;
there is no separate `source_path` column to drift. `metadata` may hold `{"h1": "...", "h2_count": 9,
"has_code": true}` for diagnostics, not for query-critical fields.

### 2.3 Chunks

```sql
CREATE TABLE chunks (
    chunk_id              text PRIMARY KEY,
    chunk_key             text NOT NULL,
    doc_id                text NOT NULL
                          REFERENCES documents(doc_id) ON DELETE CASCADE,
    ordinal               integer NOT NULL CHECK (ordinal >= 0),
    heading_path          text NOT NULL,
    content               text NOT NULL CHECK (content <> ''),
    content_hash          char(64) NOT NULL,
    token_count           integer NOT NULL CHECK (token_count > 0),
    char_count            integer NOT NULL CHECK (char_count > 0),
    start_line            integer NOT NULL CHECK (start_line >= 1),
    end_line              integer NOT NULL CHECK (end_line >= start_line),
    embedding             vector(1536) NOT NULL,
    embedding_model       text NOT NULL,
    embedding_dimensions  smallint NOT NULL CHECK (embedding_dimensions = 1536),
    profile_key           text NOT NULL,
    chunker_version       text NOT NULL,
    indexed_at            timestamptz NOT NULL DEFAULT now(),
    metadata              jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT chunks_unique_position UNIQUE (doc_id, ordinal),
    CONSTRAINT chunks_unique_key UNIQUE (doc_id, chunk_key)
);
```

**Chunk identity.** `chunk_id = 'c_' || substr(sha256(doc_id || '\x1f' || heading_path || '\x1f' ||
content || '\x1f' || occurrence), 1, 24)`, where `occurrence` is the 0-based count of identical
`(heading_path, content)` pairs earlier in the same document. This makes IDs stable when unrelated
sections are edited; an edit inside a chunk produces a new ID and a deletion of the old one.

**`chunk_key`** is human-readable: `<heading-slug>#<ordinal>` (document implied by `doc_id`). It is
for logs/debugging, not identity. `ordinal` is the display/order position in the document and may
shift after edits without changing content-addressed IDs; the ingestion diff updates ordinal and
line ranges without re-embedding when the text is unchanged.

**`content`** is the verbatim chunk text, without the breadcrumb. The embedding input is constructed
at ingest time as:

```text
{phase} > {topic title} > {heading_path}

{content}
```

The breadcrumb is not stored separately because it is derivable from `documents` and
`heading_path`; if the profile is re-embedded, chunks are rebuilt from source anyway. This avoids a
second text column that can drift.

**Line numbers** are 1-based inclusive ranges in the normalised source file (LF line endings). They
are validated against the source in integration tests for the fixture corpus.

### 2.4 Index state (single row)

```sql
CREATE TABLE index_state (
    singleton             boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    profile_key           text NOT NULL,
    embedding_model       text NOT NULL,
    embedding_dimensions  smallint NOT NULL,
    chunker_version       text NOT NULL,
    status                text NOT NULL
                          CHECK (status IN ('building', 'ready', 'failed')),
    built_at              timestamptz,
    source_commit         text,
    document_count        integer NOT NULL DEFAULT 0,
    chunk_count           integer NOT NULL DEFAULT 0,
    updated_at            timestamptz NOT NULL DEFAULT now()
);
```

One row only. `profile_key` is the readiness contract:

```text
markdown-h2-v1|1200|150|<embedding-model>|<dimensions>
```

`status='building'` is used only for a **full** rebuild; changed-only ingests keep `ready` and update
counts at the end. `failed` requires an operator reindex. `built_at` drives `/v1/ready` age.

### 2.5 Ingest runs

```sql
CREATE TABLE ingest_runs (
    run_id          text PRIMARY KEY,
    mode            text NOT NULL CHECK (mode IN ('changed', 'full', 'dry_run')),
    trigger         text NOT NULL CHECK (trigger IN ('cli', 'admin')),
    status          text NOT NULL
                    CHECK (status IN ('queued', 'running', 'success', 'partial', 'failed', 'skipped')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    profile_key     text NOT NULL,
    source_commit   text,
    stats           jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_code      text,
    error_message   text,

    CONSTRAINT ingest_runs_finished_after_start
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);
```

`stats` is the report shape documented in [`ingestion.md`](ingestion.md):

```json
{
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
}
```

`error_message` is sanitised (no API keys, no full provider body). A process restart marks
`running`/`queued` runs as `failed` with `error_code='interrupted'` at startup.

### 2.6 Query logs

```sql
CREATE TABLE query_logs (
    id                  bigserial PRIMARY KEY,
    request_id          text NOT NULL UNIQUE,
    question_sha256     char(64) NOT NULL,
    question_redacted   text,
    filters             jsonb NOT NULL DEFAULT '{}'::jsonb,
    retrieved           jsonb NOT NULL DEFAULT '[]'::jsonb,
    prompted            jsonb NOT NULL DEFAULT '[]'::jsonb,
    cited               jsonb NOT NULL DEFAULT '[]'::jsonb,
    answer_sha256       char(64),
    answer_redacted     text,
    abstained           boolean NOT NULL,
    abstention_reason   text,
    grounded            boolean,
    degraded            jsonb,
    top_score           real,
    embed_ms            integer,
    retrieve_ms         integer,
    assemble_ms         integer,
    generate_ms         integer,
    validate_ms         integer,
    total_ms            integer,
    prompt_tokens       integer,
    completion_tokens   integer,
    model                text,
    profile_key         text,
    error_code          text,
    created_at          timestamptz NOT NULL DEFAULT now()
);
```

`retrieved` is an ordered array of `{"chunk_id": "...", "score": 0.62, "rank": 1, "doc_id": "..."}`.
`prompted` and `cited` are arrays of chunk IDs. The four sets are the diagnostic backbone:

| Set | Question it answers |
|---|---|
| `retrieved` | Did the retriever find the gold chunk at all? |
| `prompted` | Did dedupe/ordering/budget keep it? |
| `cited` | Did the model actually use it? |
| `answer` | Does the prose faithfully reflect it? |

`question_redacted` is populated only when `SOURCELINE_LOG_QUESTIONS=true`; the hash is always stored.
`answer_redacted` is similarly opt-in. No IP address, user agent, API key, or prompt body is stored
here; those belong in aggregate metrics, not durable query rows.

### 2.7 Idempotency keys

```sql
CREATE TABLE idempotency_keys (
    key              text PRIMARY KEY,
    endpoint         text NOT NULL,
    request_hash     char(64) NOT NULL,
    response_status  smallint NOT NULL,
    response_body    jsonb NOT NULL,
    run_id           text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    expires_at       timestamptz NOT NULL,

    CONSTRAINT idempotency_keys_expiry_after_creation
        CHECK (expires_at > created_at)
);
```

Used only for admin reindex in v1. Insert after the operation is accepted; a replay with the same
`request_hash` returns the stored status/body; a different hash returns `409 idempotency_conflict`.
Expired rows are deleted by maintenance.

---

## 3. Indexes

```sql
-- Primary retrieval index. Cosine distance (`<=>`) matches normalised embeddings.
CREATE INDEX chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Lexical fallback only (embedding-provider outage), not the primary ranker.
CREATE INDEX chunks_content_fts
    ON chunks USING gin (to_tsvector('english', content));

-- Ordering, diff, and detail lookups.
CREATE INDEX chunks_doc_ordinal ON chunks (doc_id, ordinal);
CREATE INDEX chunks_profile_key ON chunks (profile_key);

-- Filters are applied through documents.
CREATE INDEX documents_phase_topic_type ON documents (phase, topic, doc_type);
CREATE INDEX documents_profile_key ON documents (profile_key);

-- Operations.
CREATE INDEX ingest_runs_started_at ON ingest_runs (started_at DESC);
CREATE INDEX query_logs_created_at ON query_logs (created_at DESC);
CREATE INDEX idempotency_keys_expires_at ON idempotency_keys (expires_at);
```

**HNSW settings.** `m=16`, `ef_construction=64` are starting points for a small corpus. `ef_search` is
set per transaction (default 80). Measure recall against exact search in the evaluation harness before
changing. For highly selective filters, pgvector 0.8's iterative scan reduces under-filled results:

```sql
BEGIN;
SET LOCAL hnsw.ef_search = 80;
SET LOCAL hnsw.iterative_scan = relaxed_order;   -- pgvector >= 0.8
SELECT ...;
COMMIT;
```

If the deployed pgvector is older than 0.8, omit `iterative_scan` and document the recall risk for
narrow filters. Readiness reports the extension version.

**Why not index `documents(phase, topic)` only?** The candidate query joins `documents` for filters;
the composite index gives the planner a cheap pre-filter path. Verify with `EXPLAIN (ANALYZE,
BUFFERS)` in an integration test rather than assuming.

---

## 4. Query patterns

### 4.1 Candidate retrieval

```sql
BEGIN;
SET LOCAL hnsw.ef_search = 80;

WITH query_vector AS (
    SELECT $1::vector AS v
)
SELECT
    c.chunk_id,
    c.doc_id,
    c.heading_path,
    c.start_line,
    c.end_line,
    c.token_count,
    1 - (c.embedding <=> q.v) AS score
FROM chunks c
JOIN documents d USING (doc_id)
CROSS JOIN query_vector q
WHERE c.profile_key = $2
  AND ($3::smallint IS NULL OR d.phase = $3)
  AND ($4::smallint IS NULL OR d.topic = $4)
  AND ($5::text IS NULL OR d.doc_type = $5)
  AND ($6::text IS NULL OR c.doc_id LIKE $6 || '%')
ORDER BY c.embedding <=> q.v
LIMIT $7;

COMMIT;
```

Parameters: vector, profile key, phase, topic, doc_type, path prefix, candidate_k. No string
interpolation. `LIKE` uses `%` only from the validated prefix (reject `%`/`_` in user input or escape
them).

### 4.2 Chunk resolution for citations

```sql
SELECT chunk_id, doc_id, heading_path, content, start_line, end_line,
       content_hash, profile_key
FROM chunks
WHERE chunk_id = ANY($1::text[]);
```

The API preserves request order when building citation objects; it does not trust the database order.

### 4.3 Ingest diff

```sql
SELECT chunk_id, chunk_key, ordinal, heading_path, content_hash,
       start_line, end_line, token_count
FROM chunks
WHERE doc_id = $1
ORDER BY ordinal;
```

The service compares this set with the newly chunked set. It inserts missing IDs, updates metadata
(ordinal/lines/heading) for existing IDs, and deletes IDs absent from the new set, all inside one
document transaction.

### 4.4 Upsert and prune

```sql
INSERT INTO chunks (
    chunk_id, chunk_key, doc_id, ordinal, heading_path, content, content_hash,
    token_count, char_count, start_line, end_line, embedding,
    embedding_model, embedding_dimensions, profile_key, chunker_version
)
VALUES (...)
ON CONFLICT (chunk_id) DO UPDATE SET
    ordinal = EXCLUDED.ordinal,
    chunk_key = EXCLUDED.chunk_key,
    heading_path = EXCLUDED.heading_path,
    start_line = EXCLUDED.start_line,
    end_line = EXCLUDED.end_line,
    indexed_at = now();

DELETE FROM chunks
WHERE doc_id = $1
  AND chunk_id <> ALL($2::text[]);
```

An upsert never rewrites `embedding` for an existing content-addressed ID; the text is identical by
construction, so the vector is still valid. If the embedding model changes, the whole document is
rebuilt under the new profile, not updated in place.

### 4.5 Advisory lock

```sql
SELECT pg_try_advisory_lock(hashtext('sourceline:ingest')) AS locked;
-- ... run ...
SELECT pg_advisory_unlock(hashtext('sourceline:ingest'));
```

The lock is session-scoped; the CLI must release it on every exit path. A second ingest exits `5`
(`skipped`, reason `ingest_locked`).

---

## 5. Invariants

These are checked after every ingest and by readiness/integration tests:

1. Every `chunks.doc_id` has a `documents` row (FK guarantees it; cascade delete).
2. Every chunk's `profile_key`, `embedding_model`, and `embedding_dimensions` equal the active
   `index_state` values.
3. Every document's `chunk_count` equals `count(chunks)` for that document.
4. Every chunk has a non-empty embedding and a non-zero norm (application check; cosine distance is
   undefined for a zero vector).
5. `start_line <= end_line`; the source slice at those lines contains the chunk text after
   normalisation (spot-check for every chunk in the fixture corpus; sampled in production).
6. No duplicate `(doc_id, ordinal)` or `(doc_id, chunk_key)`.
7. `index_state` has exactly one row; `document_count` and `chunk_count` match actual counts when
   `status='ready'`.
8. `documents.content_hash` is the hash of the normalised source; `chunks.content_hash` is the hash of
   `content`.
9. No chunk exceeds the hard token cap unless `metadata->>'oversized' = 'true'` and the run report
   records it.

A failed invariant after an ingest marks the run `failed` (or `partial` for one document) and prevents
`index_state.status='ready'` from being set.

---

## 6. Lifecycle

### 6.1 Changed-only ingest (online)

```text
discover + hash
      │
      ▼
plan: new / changed / unchanged / deleted / profile_changed
      │
      ├── unchanged ──► skip (zero reads beyond the manifest)
      │
      ├── changed ──► parse → chunk → embed new chunks (network)
      │                    │
      │                    ▼
      │              BEGIN
      │                upsert chunks + update line metadata
      │                delete stale chunk IDs
      │                update documents row
      │              COMMIT
      │
      └── deleted ──► BEGIN; DELETE document (cascade); COMMIT

after all docs: update index_state counts + built_at; finish run
```

While this runs, queries continue against the last committed state (MVCC). A document is either fully
old or fully new; no half-document is visible. `index_state.status` stays `ready`, so readiness does
not flap during a normal edit.

### 6.2 Full rebuild (maintenance)

A full rebuild is required when the embedding model, dimensions, chunker version, or size profile
changes. Because one table holds one vector dimension and one active profile, v1 uses a maintenance
window:

```text
1. Set index_state.status = 'building' (readiness → 503; queries fail closed).
2. Stop ingest; wait for in-flight queries (or accept brief errors).
3. TRUNCATE chunks; DELETE documents (or build into a new table; see §9).
4. Re-run discovery/chunk/embed for all documents.
5. ANALYZE; verify invariants; set status='ready', built_at=now().
```

This is honest for a portfolio: a full model change is an operational event. The scaling path is a
blue/green `chunks_v2` table or a separate database, built while the old one serves, then switched by
updating `index_state` and the relation name (or a view). That is out of v1 scope but designed for.

### 6.3 Document deletion

`DELETE FROM documents WHERE doc_id = $1` cascades to chunks. Query logs keep old chunk IDs; citation
resolution returns 404 with `chunk_not_found`, and the UI shows "source changed/pruned". This is the
correct audit behaviour: do not silently rewrite history.

### 6.4 Retention

| Table | Retention | Mechanism |
|---|---|---|
| `query_logs` | 30 days | `DELETE ... WHERE created_at < now() - interval '30 days'` in maintenance |
| `ingest_runs` | 90 days | same, 90 days |
| `idempotency_keys` | 24 h | `DELETE ... WHERE expires_at < now()` |
| `documents`/`chunks` | life of corpus | pruned by ingest |
| `schema_migrations` | forever | audit |

Maintenance runs via a small CLI (`python -m sourceline.maintenance`) and is safe to run repeatedly.
It is not on the request path. If the deployment has no scheduler, the README documents a manual
quarterly cleanup; the portfolio demo does not accumulate enough rows to matter.

---

## 7. Size and performance estimates

For the measured corpus (38 docs, ~83k words, ~110k tokens):

| Item | Estimate |
|---|---:|
| Chunks at ~300 tokens with overlap | ~300–380 |
| Text storage (`content`) | ~0.5 MB |
| Embeddings (1536 × 4 bytes) | ~2.3 MB |
| HNSW graph + overhead | ~2–10 MB |
| Documents + logs (demo) | < 20 MB |
| Total database | well under 100 MB |

A full re-embed is ~100k–120k tokens. At a list price of $0.02 per million embedding tokens, that is
roughly **$0.002–0.003**; the exact figure is computed by the eval/ingest report from provider usage,
not hard-coded. The point of idempotency is not just cost: it makes re-ingest fast enough to run in
CI and safe to run on every corpus edit.

Query cost is dominated by the chat call: ~4k–5k prompt tokens plus ~150–300 output tokens. The
per-query estimate is stored in `usage.estimated_cost_usd`; the hosted demo enforces a daily cap.

---

## 8. Security and privacy properties

- **Parameterized SQL only.** No user value is interpolated into a statement. `path_prefix` is
  validated and escaped for `LIKE`.
- **Least privilege (hosted).** The API role needs `SELECT/INSERT/UPDATE/DELETE` on the six tables and
  `USAGE` on sequences; it does not need `CREATE EXTENSION` or superuser. Migrations run under a
  separate role. The vector extension is installed once by an operator.
- **No secrets in the database.** Provider keys and the admin token are environment-only.
- **Log minimisation.** Questions are hashed by default; redacted text is opt-in. Answers are hashed by
  default. No IP/user-agent storage in `query_logs`.
- **Corpus is public by design** (this repository). A future private corpus requires per-document
  authorization before retrieval; the schema has no ACL column in v1, and ADR-010 records that
  limitation.
- **Backups** contain corpus text and logs; treat them as repository-confidential, encrypt at rest,
  and apply the same retention to backup copies.

---

## 9. Migration and evolution rules

1. **Forward-only.** Every migration is applied once, in order, checksummed. There are no automatic
   down-migrations. To undo, write a new migration.
2. **Additive first.** Add nullable columns or new tables; backfill; then enforce `NOT NULL` in a later
   migration. Avoid table rewrites while serving.
3. **Vector dimension changes are special.** Postgres cannot alter `vector(1536)` to `vector(768)` in
   place. Use a new column/table, rebuild, switch the read path, then drop old data. Document the
   maintenance window.
4. **HNSW index changes** (`m`, `ef_construction`, distance operator) require `DROP INDEX` +
   `CREATE INDEX`; do it after bulk load, not per row, and measure build time.
5. **Profile changes** update `index_state` only after a successful full rebuild. Never mix profiles
   in a `ready` index.
6. **Backups before destructive migrations.** `pg_dump -Fc` and a restore check are part of the
   runbook.
7. **Schema drift check.** Readiness compares `schema_migrations` to the files shipped in the image;
   a missing migration is `not_ready`.

---

## 10. Test coverage for this schema

| Test | Assertion |
|---|---|
| `test_migrations.py` | Fresh DB → all migrations apply; re-apply is a no-op; checksum mismatch fails |
| `test_repositories.py` | CRUD, FK cascade, constraints, pagination, JSON round-trip |
| `test_ingest_idempotency.py` | Unchanged doc = zero writes/embeddings; edit = only changed IDs; delete = cascade |
| `test_ingest_partial_failure.py` | Failed document transaction leaves the old rows intact |
| `test_retrieval_filters.py` | Pre-filter correctness; profile guard; deterministic tie-break |
| `test_citations_api.py` | Stored content/lines match the source slice |
| `test_logs_retention.py` | 30/90-day deletion boundaries |
| `test_invariants.py` | Every invariant in §5 holds after a seeded ingest |

`EXPLAIN` checks are assertions about plan shape, not timing: the candidate query must use the HNSW
index when unfiltered, and must not sequentially scan `chunks` for a normal query. Timing assertions
are left to the benchmark/eval harness because CI runners are noisy.

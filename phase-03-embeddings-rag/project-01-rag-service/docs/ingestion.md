# Ingestion Design — Sourceline

**Goal:** turn the curriculum's Markdown into retrievable, provenance-preserving chunks in pgvector,
idempotently and with an auditable plan.

The pipeline is deliberately boring: discover → hash → plan → chunk → embed → upsert → prune →
verify. The interesting part is what it refuses to do: re-embed unchanged text, mix embedding
profiles, or commit a half-updated document.

---

## 1. Corpus inventory

Measured on 2026-10-26 across the three phase folders:

| Property | Value |
|---|---:|
| Markdown documents | 38 |
| Words | 83,348 |
| Raw bytes | ~594 KB |
| Approx. tokens | ~105,000–115,000 |
| Files with fenced code | most topic notes |
| Files with tables | most topic notes |
| Average file size | ~15.6 KB |
| Largest file | several thousand words (topic 19/25/28 notes) |

The count is **phase notes only**: `phase-01-llm-fundamentals/`, `phase-02-llm-apis/`,
`phase-03-embeddings-rag/`. Root `README.md` and `SYLLABUS.md` are excluded by default because they
are navigation/checklists rather than teaching content. `--include-meta` can add them for a "what is
this curriculum?" demo; it changes the corpus hash and is a deliberate re-ingest, not a silent default.

The ingest report is the authoritative count. If a note is added, the report and README table must be
updated; the docs must not claim a stale number.

### 1.1 Include / exclude rules

| Rule | Value |
|---|---|
| Include | `phase-01-llm-fundamentals/**/*.md`, `phase-02-llm-apis/**/*.md`, `phase-03-embeddings-rag/**/*.md` |
| Exclude directories | `**/implementation/**`, `**/__pycache__/**`, `**/.pytest_cache/**`, `**/.venv/**`, `**/.git/**`, `**/node_modules/**`, `**/project-01-rag-service/**` |
| Exclude files | hidden files/directories, anything not ending in `.md`, files > 2 MB, symlinks |
| Include `README.md` inside phase folders? | Yes if it exists; it is part of that phase's docs |
| Root `README.md`/`SYLLABUS.md` | Only with `--include-meta` |
| Encoding | UTF-8 (strict); reject invalid bytes; strip BOM |
| Ordering | POSIX relative path, ascending, case-sensitive byte order |
| Duplicate paths | Reject on case-insensitive collision (Windows/macOS safety) |

Excluding the project folder prevents a self-ingestion loop in which the service indexes its own
design docs and answers questions about itself instead of the curriculum. A reviewer can still ask
about the project via the README and docs, which are outside the corpus.

### 1.2 Document metadata

| Field | Source |
|---|---|
| `doc_id` | POSIX relative path from the corpus root |
| `title` | First ATX H1 (`# ...`); fallback to filename stem |
| `phase` | Path regex `phase-(\d+)`; null if absent |
| `topic` | Path regex `topic-(\d+)`; null if absent |
| `doc_type` | `notes` for topic files, `readme` for README, `meta` for root meta, `other` |
| `source_commit` | `git rev-parse HEAD` at ingest time; `"unknown"` if not a git checkout |
| `content_hash` | SHA-256 of normalised bytes |
| `byte_size`, `word_count` | Normalised content |
| `metadata` | `{"h1": ..., "h2_count": n, "has_code": bool, "has_table": bool}` |

`title` is used in citation headers and document lists, never as identity. If the H1 changes, the
document hash changes (title is part of content), but chunk identity is based on heading path +
content, so a title-only edit re-embeds only chunks whose heading path includes the H1. That is
acceptable; the profile is not invalidated.

---

## 2. Normalisation

Before hashing, chunking, or line numbering:

1. Decode UTF-8 strictly; a decode error fails that document with `invalid_encoding`.
2. Strip a UTF-8 BOM.
3. Convert CRLF and lone CR to LF (important on the Windows development machine).
4. Strip trailing spaces/tabs on each line; preserve leading indentation (code blocks matter).
5. Ensure exactly one trailing newline.
6. Do **not** collapse blank lines, reflow prose, strip HTML comments, or rewrite links. The stored
   text must match the source a reader opens.

Line numbers refer to the normalised file. Because step 3 changes CRLF to LF but not line count, and
steps 4/5 do not add/remove lines, a citation's `[start, end]` matches the repository file viewed on
GitHub (which normalises line endings the same way). Integration tests assert this for the fixture
corpus.

Hashing is over the normalised bytes (UTF-8). A checkout with different line endings therefore
produces the same hash, which is the point.

---

## 3. Chunking

### 3.1 Profile

| Parameter | Value |
|---|---|
| Chunker | `markdown-h2-v1` |
| Target size | 1,200 characters (~250–350 chat tokens) |
| Hard cap | 1,800 characters (~450 tokens), except flagged oversized code/tables |
| Minimum | 300 characters; merge into a neighbour if smaller |
| Overlap | 150 characters (~40 tokens), only at paragraph/section boundaries |
| Split hierarchy | H2 → H3/H4 → blank-line paragraphs → sentence boundaries → hard character split |
| Atomic units | fenced code blocks and Markdown tables (never cut unless oversized) |
| Breadcrumb | `Phase N > Topic title > H1 > H2 > H3`, prepended only to the embedding text |
| Version | bump `markdown-h2-v1` on any rule change; this invalidates all chunks |

The profile key is:

```text
markdown-h2-v1|1200|150|<embedding-model>|<dimensions>
```

Changing any component is a **full reindex**, not an incremental patch. The key is stored on every
document and chunk and in `index_state`.

### 3.2 Algorithm

```text
normalize(text) -> lines
parse ATX headings and fenced-code/table spans (a heading inside a fence is not a heading)
build a tree of sections: (level, title, start_line, end_line, parent)
for each leaf section:
    if section <= 1800 chars:
        emit one chunk (unless < 300 chars -> merge with next sibling under the same parent)
    else:
        split at H3/H4 first, then blank-line paragraphs
        pack paragraphs until adding the next would exceed 1200 (+ tolerance)
        add 150 chars of trailing context from the previous chunk when the boundary is prose
        never start/end inside a fence or table; if an atomic unit is > 1800:
            - code: split at blank lines inside the fence, exact source slices,
              metadata.oversized=true, metadata.part_of_code=true
            - table: split between rows, exact source slices, metadata.oversized=true
            - hard-cap at 3000 chars and flag; never silently truncate without a report entry
emit ordinal per document in reading order
derive heading_path from the section ancestors
compute start_line/end_line from the exact slice (including overlap)
compute content_hash = sha256(content)
compute chunk_key = slug(heading_path leaf) + "#" + ordinal
compute chunk_id = "c_" + sha256(doc_id|heading_path|content|occurrence)[:24]
```

### 3.3 Rules that prevent silent retrieval failures

- **Never split a fence.** A chunk that starts mid-code loses the language/fence context and embeds
  as noise. If a fence must be split because it is enormous, the slices are exact and flagged; the
  report counts them.
- **Never drop a heading.** The heading path is part of every chunk's embedding text and citation
  metadata. A section with only a heading merges forward rather than becoming a useless chunk.
- **Never split a table row.** Tables answer comparison questions; a half-row is misleading.
- **Overlap is not duplication.** Overlap exists so a sentence at a boundary is retrievable from
  either side. Deduplication in the query path (topic 27) removes near-identical evidence before the
  prompt, so overlap does not waste context.
- **Line ranges are exact.** The stored `content` is the exact source slice. The breadcrumb is not
  stored in `content`; it is reconstructed for embedding and for the prompt header.
- **Token guard.** Every chunk is tokenized before embedding. A chunk over the embedding model's
  limit (8,191 tokens for `text-embedding-3-small`) is a hard ingest error. This should never trigger
  at the 1,800-character cap, but the guard prevents a silent truncated vector.

### 3.4 What a chunk looks like

Source:

```markdown
## 5.3 HNSW — hierarchical navigable small world graphs

HNSW builds a multi-layer graph. The upper layers contain sparse, long-range links;
the lower layers contain dense, short-range links. A search enters at the top layer
and descends, keeping a candidate list of size `ef_search`.
```

Stored:

```json
{
  "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
  "heading_path": "Topic 25 — pgvector > 5.3 HNSW — hierarchical navigable small world graphs",
  "content": "HNSW builds a multi-layer graph. The upper layers contain sparse, long-range links;\nthe lower layers contain dense, short-range links. A search enters at the top layer\nand descends, keeping a candidate list of size `ef_search`.",
  "start_line": 134,
  "end_line": 139,
  "token_count": 58,
  "chunk_key": "5-3-hnsw-hierarchical-navigable-small-world-graphs#4",
  "chunk_id": "c_2f9a1c7e5b3d4a6f8e0c1d2b"
}
```

Embedding text:

```text
Phase 3 > Topic 25 — pgvector > 5.3 HNSW — hierarchical navigable small world graphs

HNSW builds a multi-layer graph. ...
```

The citation excerpt and the model's evidence block use `content` (plus a metadata header), not the
embedding text.

---

## 4. Embedding

### 4.1 Default profile (OpenAI-compatible)

| Setting | Value |
|---|---|
| Provider | OpenAI-compatible embeddings endpoint |
| Model | `text-embedding-3-small` (pinned) |
| Dimensions | 1536 (`dimensions` parameter explicit) |
| Batch size | 64 chunks per request |
| Input | Breadcrumb + `\n\n` + content |
| Similarity | Cosine (`<=>` in pgvector); vectors need not be unit length |
| Timeout/retry | Per [`failure-handling.md`](failure-handling.md): 5 attempts, base 1 s, cap 20 s, full jitter, `Retry-After` honoured |
| Token limit guard | 8,191 tokens per input; hard fail if exceeded |

The adapter is OpenAI-compatible, so an Azure OpenAI deployment or a local Ollama server can be used
by changing `BASE_URL` and model names. The default schema is `vector(1536)`; a 768-dimension local
embedding requires the documented schema migration/full rebuild. That is a feature: the profile check
prevents a 1536-dim index from being queried with 768-dim vectors.

### 4.2 Batching and cost

`ceil(new_chunks / 64)` requests. For 312 chunks, that is 5 requests. The report records
`embedding_calls` and `embedding_tokens` (from provider usage when available, otherwise a tokenizer
estimate).

Approximate full-corpus re-embed: 105k–120k tokens. At a list price of $0.02 per million tokens, this
is roughly **$0.002–0.003**. The exact cost is computed, never hard-coded. Incremental ingest of one
edited section embeds only its new chunks.

### 4.3 Determinism and quality checks

- Temperature/seed do not apply to embeddings; the same input and model should return the same vector.
  The pipeline does not depend on byte-identical vectors, only on stable chunk identity and profile.
- Reject empty input, all-whitespace chunks, and vectors with zero norm. A zero vector produces
  meaningless cosine distances and must fail closed.
- Store `embedding_model`, `embedding_dimensions`, `profile_key`, and `chunker_version` on every row.
- Do not normalise vectors in application code; cosine distance handles magnitude, and pgvector's
  operator is the contract.

---

## 5. Manifest, diff, and idempotency

### 5.1 Manifest

Discovery produces an in-memory manifest (also writable with `--write-manifest`):

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-26T10:10:00Z",
  "source_commit": "a01637a",
  "profile_key": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
  "root": ".",
  "documents": [
    {
      "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
      "title": "Topic 25 — pgvector",
      "phase": 3,
      "topic": 25,
      "doc_type": "notes",
      "content_hash": "5e2c...",
      "byte_size": 18234,
      "word_count": 3180,
      "line_count": 412
    }
  ]
}
```

The schema lives in [`corpus/manifest.schema.json`](../corpus/manifest.schema.json). The manifest is
deterministic for a checkout: same files, same order, same hashes. It is the diff input; it is not a
second source of truth for chunk text.

### 5.2 Plan

For each manifest document, compare with `documents` + `chunks`:

| Plan state | Condition | Action |
|---|---|---|
| `new` | no `documents` row | chunk + embed all + insert |
| `changed` | `content_hash` differs, profile same | chunk; diff chunk IDs; embed only new IDs |
| `unchanged` | hash same, profile same | skip entirely (no parse, no embed) |
| `profile_changed` | model/dimensions/chunker/sizes differ | force full rebuild of the document (or entire corpus) |
| `deleted` | no file, row exists | delete document + cascade (only with `--prune`) |

A changed document is parsed and chunked, but **metadata-only changes do not embed**. If an earlier
section grows by three lines, later chunks keep the same `chunk_id` (content and heading path
unchanged); the diff updates their `ordinal`, `start_line`, and `end_line` only. This is why chunk
identity excludes line numbers and absolute position.

`updated` in the report means a row metadata update without an embedding call; `inserted` means a new
chunk ID that required an embedding. Do not conflate them.

### 5.3 Reindex triggers

| Trigger | Scope | Why |
|---|---|---|
| File content hash changed | document | Normal edit |
| Embedding model or dimensions changed | full corpus | Vectors are incomparable |
| Chunker version / target size / overlap changed | full corpus | Chunk boundaries change |
| Tokenizer/encoding changed (`token_count` contract) | full corpus | Budget accounting changes |
| HNSW distance operator changed | rebuild index | Index semantics change |
| Source commit changed with no file hashes | none | Citations update only; no re-embed |
| Corruption/partial rows detected | document or full | Invariant failure |
| Manual `scope=full` | full corpus | Operator choice |

A source-commit change alone does **not** re-embed. Citations resolve against the current source
commit recorded in `index_state`/`documents`; if the commit advanced but content did not, only the
citation URL changes, which is a metadata update.

### 5.4 Idempotency guarantees

1. Re-running on an unchanged corpus: `documents_unchanged=38`, `chunks_embedded=0`,
   `embedding_calls=0`, row counts identical.
2. Re-running after one section edit: only new chunk IDs are embedded; unchanged IDs are reused.
3. Re-running a failed run resumes safely; already committed documents are `unchanged`.
4. Deleting a file and re-running with `--prune` removes exactly its rows.
5. Replaying an admin reindex with the same `Idempotency-Key` returns the same run.
6. Two concurrent ingests cannot interleave (advisory lock).

The integration test asserts not just row counts but the **number of embedding calls** via a counting
fake provider. A count of zero for an unchanged corpus is the strongest idempotency proof.

---

## 6. Transactions and failure handling

- **Embedding before write.** Network calls happen before the document transaction. A provider
  failure leaves the old document rows untouched.
- **One transaction per document.** Upsert chunks, delete stale IDs, update the document row, commit.
  A crash mid-document rolls back; readers see the previous version.
- **Run-level status.** `success` only if every planned document committed. `partial` if at least one
  failed and others succeeded. `failed` for a fatal plan/schema error. `skipped` if the lock is held.
- **Retries.** Embedding batches retry on 429/5xx/timeout with jitter and `Retry-After`; 4xx
  validation/auth errors fail the document immediately. See [`failure-handling.md`](failure-handling.md).
- **No silent skips.** Every failed document appears in `stats.failures` with a code and sanitised
  message; the exit code is non-zero.
- **Index state.** Changed-only runs keep `ready` and update counts at the end. Full runs set
  `building` at the start, and only set `ready` after invariants pass. A failed full run leaves
  `failed` and readiness returns 503.

### 6.1 Failure matrix

| Failure | Effect | Recovery |
|---|---|---|
| File unreadable/invalid UTF-8 | document failed; others continue | fix file; re-run |
| File > 2 MB | rejected in discovery | split or exclude deliberately |
| Embedding 429/5xx | retry per policy; document fails after exhaustion | re-run; unchanged docs skipped |
| Embedding 400 (bad input/dimensions) | document failed, no retry | fix chunk/model config |
| Zero vector | document failed | investigate provider/model |
| DB connection lost | transaction rolls back | re-run; advisory lock released on session end |
| DB constraint violation | transaction rolls back | bug; inspect invariant |
| Process killed | run `running` → marked `interrupted` at next startup | re-run |
| Concurrent ingest | second exits 5 | wait; retry |
| Disk full | DB error, run failed | free space; re-run |

---

## 7. CLI contract

```bash
# Canonical changed-only ingest
python -m sourceline.ingest --root ../..

# Plan only, no writes, no embedding calls
python -m sourceline.ingest --root ../.. --dry-run

# One document
python -m sourceline.ingest --root ../.. --doc phase-03-embeddings-rag/topic-25-pgvector/notes.md

# Full rebuild (profile/chunker change or corruption)
python -m sourceline.ingest --root ../.. --scope full --confirm-full

# Remove documents no longer on disk
python -m sourceline.ingest --root ../.. --prune

# Machine-readable report
python -m sourceline.ingest --root ../.. --json
```

| Flag | Default | Meaning |
|---|---|---|
| `--root` | `SOURCELINE_CORPUS_ROOT` or repo root | Corpus root |
| `--scope` | `changed` | `changed` or `full` |
| `--confirm-full` | false | Required with `--scope full` |
| `--prune` | false | Delete absent documents |
| `--dry-run` | false | Plan/report only |
| `--doc` | none | Restrict to one relative path (repeatable in a later version) |
| `--include-meta` | false | Include root README/SYLLABUS |
| `--json` | false | JSON report to stdout |
| `--write-manifest` | none | Write manifest JSON to a path |
| `--profile` | from config | Must match the configured embedding profile |

**Exit codes:**

| Code | Meaning |
|---:|---|
| 0 | Success (including a no-op unchanged run) |
| 2 | Usage/config error (bad flag, missing key, profile mismatch) |
| 3 | Partial: at least one document failed, others committed |
| 4 | Dependency unavailable (DB/embedding provider after retries) |
| 5 | Locked: another ingest is running |
| 6 | Invariant failure after writes (index marked failed) |

### 7.1 Human report (illustrative shape)

```text
run_id: run_4a1e...
profile: markdown-h2-v1|1200|150|text-embedding-3-small|1536
plan: new=0 changed=1 unchanged=37 deleted=0 profile_changed=0
chunks: inserted=2 updated=0 deleted=1 reused=310 embedded=2
embedding: calls=1 tokens=534 cost=$0.00001
duration: 2.4s
status: success
```

The numbers come from the run, not from this document. `--json` emits the same fields as
`ingest_runs.stats`.

---

## 8. Verification after ingest

The run must execute and pass these checks before marking `ready`:

```sql
-- Counts match the report
SELECT count(*) FROM documents;
SELECT count(*) FROM chunks;

-- No mixed profiles
SELECT count(*) FROM chunks
WHERE profile_key <> (SELECT profile_key FROM index_state);

-- Document counts match
SELECT count(*) FROM documents d
WHERE d.chunk_count <> (SELECT count(*) FROM chunks c WHERE c.doc_id = d.doc_id);

-- No orphan chunks (FK should make this impossible)
SELECT count(*) FROM chunks c
LEFT JOIN documents d USING (doc_id)
WHERE d.doc_id IS NULL;

-- No empty/zero-norm embeddings (application check for norm)
SELECT count(*) FROM chunks WHERE content = '' OR embedding IS NULL;
```

Plus application-level checks:

- every chunk's line slice, re-read from source, equals `content` (all chunks in the fixture corpus;
  a sample in production);
- every chunk has `token_count <= 450` unless flagged oversized;
- `index_state.document_count`/`chunk_count` equal actual counts;
- a known-answer smoke query returns the expected `doc_id` in the top 10.

If any check fails, the run is `failed`, `index_state.status='failed'`, and readiness returns 503 with
`index_invariant_failed`. Do not serve a partially verified index.

---

## 9. Freshness and citations

- `documents.source_commit` and `index_state.source_commit` record the git commit at ingest.
- `SOURCE_BASE_URL` (e.g. `https://github.com/<owner>/<repo>/blob`) builds citation URLs:
  `{base}/{commit}/{doc_id}#L{start}-L{end}`.
- If `SOURCE_BASE_URL` is unset, citations carry `doc_id`/`lines` only; the UI shows a local path. This
  is the correct fallback for a private or non-GitHub checkout.
- `/v1/ready` reports `age_seconds`. If `SOURCELINE_EXPECTED_COMMIT` is set and differs from
  `index_state.source_commit`, `stale=true` with a warning; the service still answers, because a stale
  index is often better than no answer, but the flag is visible.
- Deployment order: migrate → ingest (changed) → start/roll API. A profile change is a maintenance
  window (full rebuild), documented in the runbook.

**Known limitation:** a renamed file is treated as delete + new, even if its content is identical.
Content-hash-based rename detection is a future optimization; at 38 documents the extra embedding cost
is trivial, and the plan report makes it visible.

---

## 10. Test plan (summary)

| Area | Tests |
|---|---|
| Discovery | includes/excludes, deterministic order, symlink rejection, size cap, case collision |
| Normalisation | CRLF/LF hash equality, BOM, trailing spaces, line count stability |
| Chunking | H2/H3 splits, target/cap, overlap, fences, tables, heading-only merge, line ranges, content-addressed IDs, occurrence duplicates |
| Token guard | oversize chunk rejection/flag; embedding token cap |
| Manifest | deterministic JSON, schema validation, source commit |
| Idempotency | unchanged = 0 embedding calls/0 writes; edit = only new IDs; line shift = 0 embeddings; delete/prune |
| Profile | each trigger forces rebuild; mismatch fails readiness |
| Failure | provider down, partial run, rollback preserves old rows, lock conflict |
| Verification | counts, profile, line slices, zero vectors, invariant failure marks index failed |
| Cost/report | call count, tokens, exit codes, JSON schema |

The fixture corpus is a small tree with known headings, a fenced code block, a table, and two files
that share a near-duplicate paragraph. It is committed under `tests/fixtures/corpus/`; the integration
suite copies it to a temp directory and ingests it against a disposable database.

---

## 11. Extension points

| Extension | Interface impact |
|---|---|
| PDF/HTML corpus | New `CorpusAdapter` that emits normalised text + heading map; chunker unchanged if headings are supplied |
| External public corpus | Adapter + license/provenance fields; same document/chunk schema |
| Code-aware chunker | New `chunker_version`, full reindex, tokenizer per language |
| Hybrid lexical retrieval | Add an FTS ranker and RRF; chunk schema unchanged |
| Learned reranker | Post-retrieval stage; no schema change |
| Blue/green profile rebuild | New `chunks_v2` table + view switch; `index_state` points at the active relation |
| Incremental embedding model migration | Dual-write/dual-read columns or a separate embedding table; out of v1 |

The schema is intentionally narrow. Every extension above can be added without changing the citation
contract: a citation is still `(chunk_id, doc_id, heading, lines, content, source_url)`.

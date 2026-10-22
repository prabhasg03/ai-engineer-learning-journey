# Topic 26 — The Retrieval Pipeline End to End

## 1. Purpose of This Topic

Most RAG failures are **pipeline failures wearing a model costume**. The model is blamed for an answer that was never supported, when the real cause was a truncated chunk, a stale vector, a dropped batch, a pruned candidate, or a citation that pointed at the wrong block.

This topic treats retrieval as eight stages with explicit contracts:

```text
ingest → chunk → embed → store → query → retrieve → assemble → answer
```

Each stage has an input, an output, and a promise. A **silent failure** is a broken promise that raises no exception: the job exits 0, the response looks plausible, and the damage is only visible in evaluation or an incident. The deliverable is the ability to trace one document through all eight stages and say, at every boundary, *what would go wrong here without anyone noticing*.

The implementation is `implementation/pipeline.py`, a deterministic offline pipeline. It uses a hashing embedder and an extractive answerer instead of network calls, so every contract in this topic is executable in pytest:

- **idempotent upserts** — re-ingesting an unchanged document embeds nothing;
- **incremental repair** — editing one paragraph re-embeds one chunk; shrinking a document deletes the orphaned chunks;
- **re-index triggers** — content change and profile change (model / dimensions / chunker) are distinguished;
- **batch embedding** — requests are counted, not texts;
- **silent-failure instrumentation** — `diagnose()` turns the invisible conditions into warnings;
- **a one-document trace** — `trace_document()` is the done-when artifact.

**Done when:** you can trace one document across ingest → answer, name where each stage can fail silently, and demonstrate idempotent re-ingestion.

### Sources and what each contributes

- **Learn RAG From Scratch (LangChain)** — the indexing path (load → split → embed → store) is most of the work; the query path is short. It also frames retrieval improvements (multi-query, compression, hybrid) as changes to one stage, not to "the model".
- **DeepLearning.AI — RAG course (LlamaIndex)** — sentence-window retrieval and auto-merging retrieval are chunk/assembly-stage techniques; the RAG triad (context relevance, groundedness, answer relevance) is how you notice a miss after the fact.
- **Hugging Face cookbook** — the canonical small recipe: fixed-size overlapping chunks → sentence-transformers embeddings → FAISS index → top-k → LLM. Useful as the minimal reference pipeline this module mirrors.
- **Applied LLMs** — retrieval quality is bounded by the *relevance, density, and detail* of retrieved documents; keyword/hybrid search is not optional for names and IDs.

---

## 2. Prerequisites

**Before: Topics 22–25**

- Topic 22: what an embedding is, dimensions, normalisation, batching, model drift.
- Topic 23: cosine similarity/distance, ordering, NaN for zero vectors.
- Topic 24: chunking, overlap, metadata, token estimation.
- Topic 25: vector columns, ANN indexes, filters, upsert-shaped SQL.

You also need the ordinary engineering vocabulary: idempotency, content hashing, transactions, retries, and manifests.

---

## 3. The Eight Stages and Their Contracts

| # | Stage | Input | Output | Contract | Typical silent failure |
|---|-------|-------|--------|----------|------------------------|
| 1 | **ingest** | source bytes (file, HTML, API) | `Document` records | every source becomes one identified, hashed document; re-running is safe | loader returns zero documents; duplicate IDs overwrite silently |
| 2 | **chunk** | `Document` | `Chunk` records | deterministic boundaries, stable IDs, size ≤ budget | answer split across chunks; stub chunk; table sliced mid-row |
| 3 | **embed** | chunk text | vectors | same model/prefix/dimensions for documents and queries; failures surface | truncation; zero vector; dropped retry rows |
| 4 | **store** | chunks + vectors | rows | idempotent upsert by chunk ID; removed chunks pruned | stale rows; partial write; missing index |
| 5 | **query** | user question | query vector | same embedding contract as documents | empty/OOV query; rewriting changed the meaning |
| 6 | **retrieve** | query vector + k/filters | ranked chunks | return up to k, with a known recall target | `k > rows`; ANN under-recall; filter removes everything |
| 7 | **assemble** | ranked chunks | one prompt string | budget respected, citations baked in, best evidence positioned | answer chunk dropped/truncated/buried |
| 8 | **answer** | prompt | answer + citations | every claim supported by cited evidence, or abstain | hallucination; citation mismatch; over-abstention |

Two observations that organise everything:

1. **The indexing path is the expensive path.** Stages 1–4 run once per document version; stages 5–8 run once per question. This is why indexing bugs are so costly: a bad chunk or stale row poisons *every future query* until it is fixed.
2. **The query path is where failures become visible.** A wrong answer is a symptom; the cause is usually in stages 1–4 or 7. Topic 28 turns this into a diagnostic procedure.

---

## 4. Stage 1 — Ingest

Ingest is not "read the file". It is **identity, normalisation, and change detection**.

### 4.1 Document identity

Choose an ID that survives re-crawls and re-exports:

- a canonical URL or path,
- a database primary key,
- a stable external ID (`ticket:1234`, `sku:ABC`),
- **never** a random UUID regenerated on every run — that turns every re-ingest into a brand-new document and doubles your index.

Keep metadata with the text: source, title, section, URL, `updated_at`, tenant, ACL. Metadata is what retrieval filters and citations use, and it is much cheaper to preserve at ingest than to reconstruct later.

### 4.2 Normalisation

Loaders are lossy in different ways:

- HTML → text drops table structure and keeps navigation chrome unless you extract the main content;
- PDF → text can reorder columns, break hyphenated words, and insert page headers between sentences;
- CSV → text needs a deliberate serialisation (`column: value` per row) or each row becomes meaningless prose;
- code → keep fences and indentation; a chunker that strips whitespace destroys Python.

Normalise deterministically (Unicode form, whitespace, line endings) and **hash the normalised text**, not the raw bytes. Otherwise an irrelevant CRLF change triggers a full re-embed.

### 4.3 The manifest

For each document, store a small manifest:

```json
{
  "doc_id": "returns",
  "content_hash": "sha256 of normalised text",
  "profile_key": "model|dimensions|chunker_version|max_chars",
  "chunk_hashes": {"returns#00": "…", "returns#01": "…"},
  "chunks": 2
}
```

The manifest is the source of truth for **"is this document current?"** It answers three questions without re-embedding anything:

- Is the document new? (`no manifest`)
- Did its content change? (`content_hash` differs)
- Is the stored vector profile still valid? (`profile_key` differs)

`Pipeline.reindex_reason()` in the module is exactly this function. The value set is small and deliberate:

```text
None               → up to date, zero embedding calls
"new_document"     → chunk + embed + insert
"content_changed"  → diff chunks, embed only changed/removed
"profile_changed"  → rebuild every chunk of this document
```

---

## 5. Stage 2 — Chunk

Topic 24 covered the policy. For the pipeline, the contract that matters is **stability**:

```python
chunk_id = f"{doc_id}#{ordinal:02d}"
content_hash = sha256(chunk_text)
```

- Re-running the chunker on unchanged text produces the same IDs and hashes → the upsert can skip every row.
- Editing a paragraph changes that chunk's hash but usually not its ordinal → one embedding call, one `UPDATE`.
- Removing a paragraph shifts later ordinals → some chunks look "changed" even if their text is identical. That is acceptable for paragraph-sized documents; for very large documents, content-addressed IDs (`doc_id#sha1(text)[:12]`) avoid the cascade, at the cost of needing to detect duplicates and delete stale rows by set difference.
- Chunk boundaries must be deterministic: no timestamps, no `hash()`, no unordered set iteration.

The module's chunker is paragraph-first, sentence-second, hard-split last:

```python
chunks = chunk_document(document, max_chars=200, chunker_version="paragraph-v1")
# warranty#00: 112 chars, warranty#01: 112 chars  (warranty sample)
```

A long single sentence becomes multiple `hard_split=True` chunks rather than one oversized chunk. That flag is a diagnostic: hard splits are where answers get cut in half.

---

## 6. Stage 3 — Embed (and Batch Embedding)

### 6.1 The embedding contract

Documents and queries must use:

- the **same model** (a query embedded by model A cannot be compared to documents embedded by model B),
- the **same dimensions** (some APIs let you request a shortened dimension; the choice is part of the profile),
- the **same prefix/task instruction** if the model expects one (E5 uses `query:` for questions and `passage:` for documents; several models distinguish query vs document input types),
- the **same normalisation** (many models return unit vectors; do not re-normalise inconsistently),
- a **known input limit** (tokens, not characters).

The API may help you get this wrong silently: some providers accept a `dimensions` parameter, some truncate long inputs, and some return a vector for an empty string instead of rejecting it. Pin the model name and dimensions in the index metadata and refuse to query a table whose profile does not match.

### 6.2 Batch embedding

One request per chunk is the most common cost/latency mistake in a first implementation. Embedding APIs take an array of inputs:

```python
vectors = embedder.embed_batch([chunk.text for chunk in chunks], batch_size=100)
```

Arithmetic worth internalising:

- 9 chunks at `batch_size=4` → **3 requests**, not 9 (the module's test asserts this);
- 2,000 chunks at 100 per request → **20 requests**, not 2,000;
- the OpenAI embeddings API documents **2,048 inputs** and **300,000 tokens per request** for the text-embedding-3 family (at the time of writing), so the token cap usually binds before the input count.

Batch sizing is a trade-off:

- larger batches → fewer requests, better throughput, more memory, larger retry unit;
- smaller batches → finer-grained retries and progress, but more overhead;
- always make the operation **resumable**: chunks are keyed by ID, so a failed batch can be retried without duplicating rows.

### 6.3 The cost of re-embedding

Illustrative arithmetic (check current prices): 1M chunks × 300 tokens = **300M tokens**. At roughly $0.02 per million tokens for a small embedding model that is about **$6**; a 6.5× more expensive model is about **$39**. Cheap enough to rebuild occasionally, expensive enough that "we changed the model and re-embedded on every deploy" is a real budget bug. Batch, diff, and re-index deliberately.

### 6.4 Silent embedding failures

- **Truncation:** the provider embeds only the first N tokens. The chunk is stored, retrievable, and missing its conclusion. Detect by measuring tokens before the call; the module warns when a chunk exceeds `MAX_EMBED_INPUT_CHARS`.
- **Zero vectors:** empty text or text with no recognised tokens becomes all zeros. Cosine is NaN, the row never ranks, and no error is raised. The module records `zero_vectors` per ingest and `diagnose()` flags them.
- **Dropped retry rows:** a retry wrapper that catches a batch error and continues with the successful subset leaves holes. The ingest report's `embedded` count is how you catch it: it must equal the number of chunks you intended to embed.
- **Model drift:** one deploy uses `model-v1`, the next `model-v2`, and the old rows remain. Retrieval returns plausible neighbours from a mixed vector space. The fix is the profile key and a forced rebuild.

---

## 7. Stage 4 — Store (Idempotent Upserts)

### 7.1 The row

A practical chunk table:

```sql
CREATE TABLE chunks (
    chunk_id        text PRIMARY KEY,      -- doc_id#ordinal
    doc_id          text NOT NULL,
    content         text NOT NULL,
    content_hash    text NOT NULL,
    embedding       vector(1536) NOT NULL,
    model           text NOT NULL,
    dimensions      int  NOT NULL,
    chunker_version text NOT NULL,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

`chunk_id` is the idempotency key. `content_hash`, `model`, `dimensions`, and `chunker_version` are the **lineage columns** without which you cannot tell why a row is stale.

### 7.2 The upsert

```sql
INSERT INTO chunks (chunk_id, doc_id, content, content_hash, embedding, model, dimensions, chunker_version)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (chunk_id) DO UPDATE
SET content        = EXCLUDED.content,
    content_hash   = EXCLUDED.content_hash,
    embedding      = EXCLUDED.embedding,
    model          = EXCLUDED.model,
    dimensions     = EXCLUDED.dimensions,
    chunker_version= EXCLUDED.chunker_version,
    updated_at     = now()
WHERE chunks.content_hash IS DISTINCT FROM EXCLUDED.content_hash
   OR chunks.model        IS DISTINCT FROM EXCLUDED.model
   OR chunks.dimensions   IS DISTINCT FROM EXCLUDED.dimensions
   OR chunks.chunker_version IS DISTINCT FROM EXCLUDED.chunker_version;
```

The `WHERE` clause is the difference between "upsert" and "rewrite every row on every run": unchanged rows are not touched. In application code, the same logic is:

```python
status = store.upsert(row)   # "inserted" | "updated" | "unchanged"
```

### 7.3 Pruning removed chunks

Upserting new chunks is only half an idempotent ingest. When a document shrinks, the old tail must go:

```sql
DELETE FROM chunks c
WHERE c.doc_id = $1
  AND NOT EXISTS (
      SELECT 1 FROM staging s WHERE s.chunk_id = c.chunk_id
  );
```

Or, in the module, `store.delete_document_except(doc_id, keep=new_ids)`. The dangerous pattern is **delete-then-insert** without a transaction: a failure between the two leaves the document missing, and the next query confidently returns nothing.

### 7.4 Transaction and verification

- Wrap one document's diff (inserts + updates + deletes + manifest update) in a transaction. A partial document is worse than an old document.
- Emit counts: `inserted`, `updated`, `unchanged`, `deleted`, `embedded`, `embed_batches`.
- Assert the invariants: `inserted + updated + unchanged == chunks_total`; `embedded == inserted + updated`; `deleted` matches the removed chunk set.
- Build or refresh ANN indexes **after** bulk loads; index maintenance during millions of inserts is slower and can leave the index in a poor state (Topic 25).

### 7.5 Idempotency, demonstrated

The module's fixture (`returns`, three paragraphs, `max_chars=200`, `batch_size=2`):

| Scenario | `embedded` | `unchanged` | `deleted` | Meaning |
|---|---:|---:|---:|---|
| first ingest | 3 | 0 | 0 | new document |
| immediate re-ingest | **0** | 3 | 0 | byte-identical → zero embedding calls |
| edit "30 days" → "45 days" | 1 | 2 | 0 | only the changed chunk re-embedded |
| drop the last paragraph | 0 | 1 | 2 | stale chunks pruned, the surviving chunk unchanged |
| change chunker version | 3 | 0 | 3 | profile change → full rebuild |

This is the operational definition of "idempotent upserts working": replaying the same input costs **zero** embedding calls, and changing the input repairs exactly the affected rows.

---

## 8. Re-index Triggers

A re-index is not only "the document changed". The complete trigger table:

| Trigger | Detection | Scope | Action | Cost |
|---|---|---|---|---|
| new document | no manifest | one document | chunk + embed + insert | small |
| content change | `content_hash` differs | one document | chunk diff, embed changed | proportional to edit |
| document deleted | source no longer present | one document | delete rows + manifest | small |
| chunker/size/overlap change | `profile_key` differs | **all documents** | re-chunk + re-embed everything | full rebuild |
| embedding model change | `profile_key` differs | **all documents** | re-embed everything | full rebuild + API budget |
| dimensions change | `profile_key` differs | **all documents** | new column/table, re-embed | full rebuild + migration |
| query/document prefix change | `profile_key` differs | **all documents** | re-embed with the correct prefix | full rebuild |
| metadata/filter schema change | migration version | affected rows | backfill metadata | cheap if no re-embed |
| ANN index/algorithm change | index build version | index only | rebuild index | CPU, no API |
| bug in normalisation/loader | code version | affected documents | re-ingest those sources | proportional |

Two production patterns keep full rebuilds safe:

1. **Blue/green index:** write the new embeddings into a new table (or a new collection), evaluate, then switch an alias/pointer. The old index keeps serving until the new one passes retrieval evals.
2. **Dual-write during migration:** new documents go to both profiles until the backfill completes, so there is no window in which new content is missing from the live index.

The profile key in the module is deliberately one string:

```text
hashing-8192-v1|8192|paragraph-v1|200
```

Any component change → `profile_changed` → every chunk rebuilt. That is the safe default; a smarter system can re-embed only documents whose chunks actually changed *and* whose old vectors used the old profile.

---

## 9. Stage 5–6 — Query and Retrieve

### 9.1 Query contract

- Embed the query with the **same** model, dimensions, and prefix as the documents.
- Keep the raw question for logging; rewriting is an optimisation that can silently change meaning. If you rewrite, compare rewritten-vs-raw retrieval on a labelled set before shipping.
- Empty or stopword-only queries produce a zero vector in this module. The store still returns rows (with NaN scores) unless you check. `Retrieval.zero_query` exists so the caller can refuse.
- Log the query vector norm. A norm of 0 is a bug, not a query.

### 9.2 Retrieval knobs

- `k` is a cap, not a promise. If the store has two rows and `k=3`, you get two hits; the module's `Retrieval.missing` reports the shortfall. Downstream code that assumes `len(hits) == k` breaks silently.
- Exact search has perfect recall and O(n) cost. ANN trades recall for speed; measure recall against exact search on a labelled set (Topic 25).
- Filters can remove the only useful row. Post-filtering after an ANN scan is the classic version of this failure.
- Hybrid retrieval (BM25 + vectors) is the standard fix for exact names, SKUs, error codes, and rare terms that embeddings blur (`Applied LLMs` makes this point directly).

### 9.3 The morphology miss, live

The module's hashing embedder matches words, not morphology. With all three documents ingested:

```text
query: "How long is the warranty?"
hits:  warranty#01  0.1400   ("Warranty claims require the original receipt…")
       returns#00   0.0000
       returns#01   0.0000
answer: "Warranty claims require the original receipt and the serial number…" [1]
```

The chunk that actually contains the answer (`warranty#00`: "Manufacturer warranties cover defects for 12 months…") is **not in the top 3**, because `warranty` ≠ `warranties`. The answer is extractive, cites a real chunk, and is still wrong. No exception. This is exactly the class of failure a stronger embedding model, stemming, or hybrid search fixes — and exactly the class a "the answer has a citation, so it must be grounded" check misses.

---

## 10. Stage 7–8 — Assemble and Answer

Topic 27 owns assembly in detail; here the pipeline only needs the contracts:

- **Budget:** the prompt has a hard token budget; chunks that do not fit are dropped (or truncated) and the drop must be recorded. Silent truncation is how the answer-bearing chunk disappears.
- **Citations:** every included chunk gets a marker and a source header *at assembly time*. The answer stage must cite those markers, and a validator must reject markers that do not exist.
- **Order:** the strongest evidence should sit at an edge, not in the middle (lost-in-the-middle; Topic 27).
- **Answer:** a real system calls an LLM here; the module's extractive answerer quotes the best-matching sentence and attaches a citation. The contract is the same: **answer from the provided evidence or abstain**. The deterministic stand-in makes the grounding contract testable without a model.

A minimal real call (the shape, not a tested integration):

```python
response = client.chat.completions.create(
    model="…",
    temperature=0,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": assembled.text},
    ],
)
```

The pipeline is only as good as its weakest contract. A flawless LLM given a prompt that omitted the answer will produce a confident wrong answer; the generation stage cannot recover evidence that assembly dropped.

---

## 11. Where Each Stage Fails Silently

"Silent" means **no exception, plausible output, delayed detection**. The catalogue below is the module's `SILENT_FAILURES`, with the detection each one needs.

### Ingest

- A loader returns zero documents for an unsupported/corrupt file, and the job reports success. **Detect:** assert source count > 0 and compare source count to indexed count.
- A duplicate `doc_id` overwrites the previous version without a diff. **Detect:** manifests and content hashes; log `new_document` vs `content_changed`.
- An HTML/PDF loader returns navigation chrome as content. **Detect:** sample chunks; boilerplate ratio; strip selectors.

### Chunk

- A document shorter than the window becomes one giant chunk that the embedder truncates. **Detect:** token count per chunk before embedding.
- The final chunk is a 30-character stub that weakly matches everything. **Detect:** minimum chunk size; merge stubs with neighbours.
- Tables/code fences are sliced mid-structure, so the answer is split across chunks. **Detect:** structural chunking; inspect boundaries around gold answers (Topic 24).

### Embed

- Input past the model window is truncated by the provider. **Detect:** tokenizer count + a hard warning; never trust character counts for the real limit.
- Empty/OOV text becomes a zero vector: stored, NaN cosine, never retrieved. **Detect:** reject or flag zero vectors at ingest (`report.zero_vectors`).
- A retried batch drops failed rows but the job still says "done". **Detect:** `embedded` must equal intended; reconcile row count by document.
- Query and documents use different models/prefixes. **Detect:** profile key per row; refuse cross-profile queries.

### Store

- Stale chunks from the previous version remain and can outrank fresh ones. **Detect:** `delete_document_except` + an orphan scan (`diagnose()` flags `stale_rows`).
- Batched writes partially succeed. **Detect:** transaction per document + count reconciliation.
- The index is missing or was built before the data. **Detect:** `EXPLAIN`; freshness canary; row counts.

### Query

- Empty/all-stopword query → zero vector → meaningless rows, no error. **Detect:** `zero_query` flag; reject with a user-facing message.
- A rewriting step changes the question's meaning. **Detect:** log raw + rewritten queries; evaluate both.
- The wrong distance operator is used for a normalised store. **Detect:** one metric per index; ranking sanity tests.

### Retrieve

- `k` exceeds the number of stored rows, so fewer rows reach the prompt. **Detect:** compare returned count to k; pad explicitly or lower k.
- Post-filtering returns fewer than k rows for narrow filters. **Detect:** count after filtering; pre-filter or iterative scan.
- ANN under-recall omits the answer-bearing row. **Detect:** recall@k vs exact search on labelled queries; monitor ef_search/probes.

### Assemble

- The context budget drops the chunk that held the answer. **Detect:** record dropped chunk IDs and reasons; assert the gold chunk is cited in evals.
- Near-duplicate chunks eat the budget. **Detect:** dedupe at assembly (Topic 27).
- The question is buried mid-context. **Detect:** fixed layout with the question at an edge; measure answer accuracy by position.

### Answer

- The model answers from parametric memory and cites nothing (or the wrong source). **Detect:** citation validation + groundedness checks.
- A confident answer with no support arrives instead of an abstention. **Detect:** abstention calibration on unanswerable questions.
- Citation numbers are renumbered after pruning and no longer match. **Detect:** assign citations after pruning; validate markers against the map.

---

## 12. Tracing One Document Through the Entire Path

This is the actual output of

```python
pipeline = Pipeline(max_chars=200, batch_size=4)
trace = pipeline.trace_document(SAMPLE_DOCUMENTS[2], "How long do manufacturer warranties cover defects?")
print(trace.format())
```

```text
trace: warranty -> 'How long do manufacturer warranties cover defects?'
  ingest    new_document: 2 embedded, 0 unchanged, 0 pruned
            warnings: ['none']
  chunk     2 chunks, max 112 chars
            chunk_ids: ['warranty#00', 'warranty#01']
  embed     2 rows x 8192 dims, 0 zero vectors
            batches: 1
            model: hashing-8192-v1
  store     2 rows total; profile hashing-8192-v1|8192|paragraph-v1|200
            chunks_for_document: 2
  query     query vector norm 1.000
            zero_query: False
  retrieve  2 hits for k=3 (missing 1)
            hits: [('warranty#00', 0.4865), ('warranty#01', 0.0)]
  assemble  228/700 chars, 2 citations
            dropped: ['none']
  answer    quoted 1 citation(s)
            text: Manufacturer warranties cover defects for 12 months from the purchase date. [1]
            citations: [1]
```

Read it as a chain of evidence:

1. **ingest** — `new_document`, both chunks embedded in one batch. If this said `unchanged`, we would expect zero embedding calls.
2. **chunk** — two stable IDs, maximum 112 characters. The chunker did not hard-split; the document's paragraph structure survived.
3. **embed** — 8,192 dimensions, no zero vectors. A zero here would mean a row that can never be retrieved.
4. **store** — two rows, profile pinned. The profile is what a later model change will invalidate.
5. **query** — norm 1.0. A zero query would make every score NaN.
6. **retrieve** — the gold chunk at 0.4865; the other at 0.0. `missing 1` is not an error: `k=3` but the store contains only this document's two rows. This is the "k is a cap, not a promise" failure in miniature.
7. **assemble** — 228 of 700 characters, two citations. Nothing dropped, but the budget is a policy: a smaller budget would silently remove the second chunk.
8. **answer** — an extractive quote from the gold chunk with `[1]`, the marker assigned during assembly.

Now change the question to the morphology case from §9.3 and the chain still "succeeds": retrieval returns three rows, assembly cites them, the answer quotes `warranty#01`, and the output looks perfectly grounded. The stage that failed is **retrieval**, and nothing in the trace would alert you unless you know what the gold chunk is. That is why tracing is not enough on its own — you also need labelled cases (Topic 28).

---

## 13. Implementation Walkthrough — `pipeline.py`

One module, no network, no randomness:

- **`HashingEmbedder`** — signed feature hashing over content words + bigrams, 8,192 dimensions, L2-normalised. `embed_batch(texts, batch_size)` counts **requests** (`calls`) and texts separately, so tests can prove batching and idempotency. Empty text → zero vector, deliberately.
- **`Document`, `Chunk`, `chunk_document`** — deterministic `doc_id#ordinal` IDs; paragraph-first, sentence-second, hard-split last; per-chunk SHA-256 content hash; `hard_split` flag.
- **`VectorStore`** — `upsert` returns `inserted|updated|unchanged`; `delete_document_except` prunes stale chunks; `search` is cosine with NaN-last ordering; `where=` filter mirrors SQL metadata filters.
- **`Pipeline`** — `reindex_reason`, `ingest`, `reindex`, `remove_document`, `retrieve`, `assemble`, `answer`, `query`, `trace_document`, `diagnose`.
- **`IngestReport`** — the numbers that make ingest auditable: `chunks_total`, `inserted`, `updated`, `unchanged`, `deleted`, `embedded`, `embed_batches`, `zero_vectors`, `warnings`.
- **`SILENT_FAILURES`** — two to three concrete silent failures per stage; `silent_failure_notes(stage)`.
- **`SAMPLE_DOCUMENTS`** — returns, shipping, warranty fixtures used by tests and the notebook.

Run it:

```bat
cd phase-03-embeddings-rag\topic-26-retrieval-pipeline\implementation
python -m pytest -q          :: 49 passed
python pipeline.py           :: demo: ingest, idempotency, edit, trace, diagnosis
```

The 49 tests cover: stable chunk IDs and verbatim text; batching and zero vectors; first ingest vs replay; partial re-embed; stale pruning; profile triggers; forced reindex; retrieval ranking; zero-query flagging; assembly budget/citations; grounded vs abstained answers; all eight trace stages; and each diagnostic detector.

---

## 14. Pitfalls

1. **Treating ingest as a one-off script.** Re-ingestion is the normal case (cron, webhook, re-export). Without IDs, hashes, and pruning, every run either duplicates rows or leaves stale ones.
2. **Generating IDs from timestamps or random UUIDs.** The index grows without bound and retrieval returns multiple versions of the same document.
3. **Embedding one chunk per request.** Correct but 100–2,000× more requests than necessary; batch, but keep the retry unit small enough to be useful.
4. **Ignoring the token limit because your chunks are "small".** Characters ≠ tokens; code/JSON/Unicode inflate the ratio. Measure with the real tokenizer.
5. **Upserting without `WHERE content_hash IS DISTINCT FROM …`.** Every re-ingest rewrites every row and calls `updated_at = now()` on unchanged data, destroying freshness metrics.
6. **Forgetting to delete removed chunks.** The old paragraph outranks the new one, and the citation points at text that no longer exists.
7. **Changing the embedding model without changing the profile key.** Two incompatible vector spaces share one index; scores look plausible and retrieval quietly degrades.
8. **Assuming `len(hits) == k`.** Short results are normal with small stores, narrow filters, and deletions; downstream code must handle them.
9. **Letting the assembler truncate silently.** The one chunk that held the answer is often the one that does not fit.
10. **Logging only the final answer.** Without the retrieved/prompted sets and the dropped candidates, a wrong answer is undebuggable. Log the intermediate sets from day one.
11. **Building the ANN index before the bulk load.** Slower build and a worse graph; build after ingestion (Topic 25).
12. **No freshness canary.** Stale indexes are invisible until a user asks about a document that "should be there". A known-answer probe run on a schedule turns that into an alert.

---

## 15. Exercises

1. **Add a loader stage.** Write `load_documents(path)` for a folder of `.md` files: stable IDs from the relative path, normalised text, metadata (`title`, `mtime` as a string for determinism). Ingest twice and assert zero embedding calls.
2. **Content-addressed chunk IDs.** Change `chunk_document` to use `doc_id#sha1(text)[:12]`. Re-run the edit test: how many chunks change when you insert a paragraph at the top? Which trade-off did you just make?
3. **Batch-size sweep.** Generate a 200-chunk document and measure `embedder.calls` for `batch_size` in `{1, 4, 16, 64}`. Plot calls against batch size. Where does the curve flatten?
4. **Partial-failure drill.** Add an embedder that raises on the second batch. Ensure the ingest leaves the document in a consistent state (transaction-shaped) and that a retry completes without duplicating rows.
5. **Stale-index alarm.** Write a `freshness_probe(pipeline, doc, question)` that ingests a canary document, waits for a mutation that is *not* re-ingested, and asserts the probe fails. Then wire the same probe into a test that catches a missing `reindex` call.
6. **Profile migration.** Add a second embedder with 1,024 dimensions and implement a blue/green rebuild: write new rows to a separate store, compare top-1 accuracy on a labelled set, then swap. Keep the old store queryable until the swap.
7. **Morphology lab.** Add simple suffix stripping (`-ies → -y`, `-es`, `-s`) to the embedder's tokeniser. Re-run the warranty query. Does the gold chunk return? What new false matches appear?
8. **Trace your own corpus.** Ingest five real documents, trace one question end to end, and annotate each stage with the *one* thing most likely to fail silently for that corpus.

---

## 16. Done-When Checklist

- [x] I can name all eight stages, their inputs/outputs, and the contract each one must keep.
- [x] I can explain batch embedding, including request-vs-text counts and the retry/resumability implications.
- [x] I can write an idempotent upsert (key + content hash + `ON CONFLICT … WHERE`) and prune removed chunks.
- [x] I can list the re-index triggers (content, chunker, model, dimensions, prefixes) and say whether each is incremental or full.
- [x] I can trace one document through ingest → answer with real counts, and point at the stage that would fail silently.
- [x] I can demonstrate that re-ingesting an unchanged document costs zero embedding calls, and that editing one paragraph re-embeds exactly one chunk.
- [x] I can explain why a wrong answer with a valid citation is still a pipeline failure, using the morphology miss as the example.

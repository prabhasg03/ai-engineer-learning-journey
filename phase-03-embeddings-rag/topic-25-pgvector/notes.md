# Topic 25 — pgvector

## 1. Purpose of This Topic

Store vectors **next to the rest of your relational data** in Postgres, run approximate-nearest-neighbour (ANN) queries through an index, understand exactly **how IVFFlat and HNSW trade recall for speed and memory**, combine vector search with ordinary **SQL WHERE filters**, and be able to argue **Postgres-first vs specialist vector DB** for a given corpus size.

Because no Postgres server is required for the offline tests, `implementation/pgvector_sim.py` is a hand-written miniature that mirrors pgvector's semantics — same operator behaviours, same failure modes, same index knobs — so the reasoning transfers to real SQL unchanged.

```text
Topic 23: cosine/L2/dot math in Python      Topic 24: chunks to store
                 ↓                                        ↓
Topic 25: the SAME math as SQL operators + an index + WHERE filters
                 ↓
Topic 26+: the retrieval pipeline end to end
```

**Done when:** an indexed vector table answers ANN queries, and you can reason IVFFlat-vs-HNSW for a given corpus size.

---

## 2. Prerequisites

**Before: Topic 23**

- Cosine vs L2 vs negative inner product, and the ordering details
- Comfort with `ORDER BY` / `LIMIT` thinking
- Topic 24: you know what a chunk is, because chunks are the rows here

---

## 3. Vector Columns

Ship the wheel with what you have: a Postgres table can hold a vector column alongside every ordinary column — joins, permissions, backups, transactions included.

```sql
CREATE EXTENSION vector;                       -- once per database

CREATE TABLE documents (
    id bigserial PRIMARY KEY,
    content text NOT NULL,                     -- the chunk text (Topic 24)
    header_path text,                          -- metadata for WHERE filters
    embedding vector(1536)                     -- OpenAI 3-small, say
);

INSERT INTO documents (content, header_path, embedding)
VALUES ('Return window is 30 days.', 'Return Policy',
        '[0.013, -0.217, 0.417, ...]');       -- textual vector literal
```

Type facts from the pgvector README, worth memorising:

- a `vector` takes **4 × dimensions + 8 bytes** (single-precision floats; the +8 is a header) — 1M rows at 1536-d ≈ **6.15 GB**, before indexes,
- **16,000 dimensions** max for the column type (`vector`, `halfvec`, `sparsevec`), **64,000 for `bit`**,
- dimension is part of the type: `vector(1536)` is NOT `vector(768)`; mismatched inserts error out (never silent coercion) — mirrored by `test_dimension_mismatch_raises_like_an_insert`,
- element values must be finite (no NaN/Infinity); zero vectors are legal but *skipped by cosine indexes* and return NaN cosine distance,
- v0.7+ siblings: **`halfvec`** (2 bytes/element — halve storage; indexable to 4,000 dims), **`bit`** (binary quantization — Hamming `<~>` / Jaccard `<%>`), **`sparsevec`** (sparse vectors for BM25-style sparse embeddings),
- use **`COPY ... FORMAT BINARY`** for bulk loads (much faster than row-by-row INSERTs).

---

## 4. Distance Operators

| operator | computes | lowest value | module mirror |
|---|---|---|---|
| `<->` | **L2 / Euclidean distance** | 0 (identical) | `l2_distance` |
| `<=>` | **cosine distance** = 1 − cos sim | 0 (identical) | `cosine_distance` |
| `<#>` | **negative inner product** | −∞ (most similar) | `negative_inner_product` |
| `<+>` | L1 / taxicab distance | 0 | — (added pgvector 0.7) |
| `<~>` / `<%>` | Hamming / Jaccard (bit) | 0 | — |

Why `<#>` is negative: Postgres index scans walk operator results in **ASC** order, so "most similar" must be the *smallest* value, like a distance. Negation flips a big dot product (similar) into a very negative one (scanned first). Recover the inner product with `(a <#> b) * -1`; recover cosine similarity with `1 - (a <=> b)`.

The query shape that makes everything work:

```sql
-- k nearest chunks by cosine distance
SELECT id, content, 1 - (embedding <=> $query) AS similarity
FROM documents
ORDER BY embedding <=> $query
LIMIT 5;
```

Choose the operator that matches your vectors and stay consistent per index (never mix two metrics in one index):

- **OpenAI/text-embedding-3 style (unit-norm outputs):** cosine `<=>` classically; the docs also note that with normal-length vectors inner product `<#>` gives the same *ranking* with best raw performance,
- **models whose magnitude carries information (rare in text RAG):** L2 `<->`,
- rule of thumb from the docs: *"if vectors are normalized to length 1, use inner product for best performance"*.

Distance *filtering* exists too — `WHERE embedding <=> q < 0.3` — but note the README's warning: combine it with `ORDER BY` + `LIMIT` or the index won't serve it.

---

## 5. Exact vs ANN

### 5.1 Exact (no index) — where you start

Without an index, every query scans the whole table and computes the distance row-by-row:

```text
plan: Seq Scan on documents   (what EXPLAIN prints before the index exists)
```

Perfect **recall**, O(n) per query. Perfectly fine — preferable, even — up to roughly **100k rows** with 1,000-dim vectors on decent hardware, or with a selective `WHERE` filter that prunes rows first (see §6 for highly selective filters that bypass ANN entirely). Notice the planner's two requirements:

- queries need `ORDER BY <operator> ... LIMIT k` *exactly* — an expression like `ORDER BY 1 - (embedding <=> q) DESC` disables the index (rewrite as ASC `<=>` with `LIMIT`),
- small tables may stay on a seq scan anyway ("if the table is small, a table scan may be faster").

### 5.2 IVFFlat — inverted file, cluster-partitioned

Idea: run **k-means** on your vectors at build time; keep one inverted list per cluster; at query time compute distances to the *centroids*, probe the `probes` nearest lists only.

```sql
CREATE INDEX ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

SET ivfflat.probes = 4;               -- default 1 ...
SET LOCAL ivfflat.probes = 4;         -- ... or per-transaction
```

The README's three keys to good recall, straight from the source:

1. **Create the index AFTER the table has data.** Trained on too little data, lists land badly and the index is worse than useless — the module refuses to build one (`test_ivfflat_built_on_empty_table_raises` mirrors the "drop the index and wait" advice),
2. **`lists = rows / 1000`** for under 1M rows; **`sqrt(rows)`** beyond that. (100 lists for 100k rows; ~1,000–10,000 lists for millions),
3. **`probes = sqrt(lists)`** to start; raise for recall, lower for speed. Set `probes = lists` (or skip the index) and you get exact search back.

Behavioural notes the module demonstrates:

- recall **monotonically increases** with probes: fixture numbers with lists=15 — probes 1 → recall 0.64, probes 2 → 0.96, probes 4 → 1.00 (`test_ivfflat_recall_monotonic_in_probes`),
- probes=1 with default settings is a recall hole; many "pgvector is inaccurate!" bug reports are just default probes on real data,
- build is quick, memory-light (centroid coordinates + list members),
- the k-means means the index is a **model of your distribution**: re-build or re-probe when the corpus drifts heavily.

### 5.3 HNSW — hierarchical navigable small world graphs

A **multilayer graph**: each point connects to `m` neighbours; a few points also live on sparser upper layers (probability sampling), a denser middle, and everything lives at layer 0. Search = greedy descent through the sparse layers, then beam search in the dense bottom layer keeping an `ef_search`-sized candidate list. Crunchy Data walks this as exactly three illustrations stacked ("of course it's 3 algorithms in a trench coat").

```sql
CREATE INDEX ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

SET hnsw.ef_search = 100;             -- default 40
```

Knobs (build: `m` links per point per layer, `ef_construction` candidate size; query: `ef_search`) and their meaning, per Crunchy Data's measurements — which are worth quoting because they cut through the folklore:

- the original paper's sweet spot: **M in 5..48**; smaller M = fine for lower recall or low-dim data, bigger M for high recall or high-dim data,
- **`ef_construction`: "further increase leads to little extra performance but significantly longer construction time"** — keep the defaults unless your recall measurably sags; also note it must be ≥ 2 × M (the build list truncates to M),
- **`ef_search` is the real runtime lever**: it is also a *ceiling on rows returned* — you cannot return more rows than ef_search. Want LIMIT 100? set ef_search ≥ 100,
- build costs: HNSW **slower to build** (1M rows can redline CPU for ~6 minutes) and **uses more memory** (1M × 1536-d AI embeddings ≈ **8 GB index** you want resident in RAM),
- but HNSW has **no training step** (can be built on an empty table, unlike IVFFlat) and better speed-recall in general; the module's health check shows it exactly this way.

One gotcha Crunchy Data found in the wild: the planner prefers HNSW with **simple queries** — CTEs/joins can dislodge it. `EXPLAIN` until the plan shows `Index Scan using ..._hnsw_idx`, then add complexity back.

### 5.4 IVFFlat vs HNSW — the decision table

| | **IVFFlat** | **HNSW** |
|---|---|---|
| build speed | fast | slow |
| build memory | small (needs training data ≥ 10 × lists rows) | large; no training data needed |
| query speed-recall | good | **better** |
| recall robustness | sensitive to probes + distribution shift | stable given decent ef_search |
| knob safety | list count / probe count misconfig = silent bad recall | ef_search default is decent |
| updates | distribution drift → rebuild advisory | inserts integrate (slower per insert) |
| caps | vector ≤ 2,000 dims (halfvec 4,000) | same |

How the syllabus asks you to *reason* it: for a **small corpus** (< ~100k), skip ANN entirely and exact-scan; for **100k–10M** mostly-static docs where you want cheap indexes and fast rebuilds, IVFFlat with `lists = rows/1000, probes = sqrt(lists)` is great; for **latency-critical** or **incrementally growing** corpora at scale HNSW wins despite the RAM; **if distribution drifts monthly**, HNSW's no-training build or a scheduled IVFFlat reindex both handle it — the thing to actually monitor is the **recall drift** (§5.5).

### 5.5 Monitoring recall

pgvector docs' own recipe, mirrored by `index_health_check()`:

```sql
BEGIN;
SET LOCAL enable_indexscan = off;   -- exact search
SELECT ...;
COMMIT;
```

Compare ANN results against exact on real queries (recall@k); schedule it — it is the equivalent of `CHECK (last_known_good)` for your index. The module's `index_health_check` does exactly this dance offline, returning `{ivfflat_probes_1: 0.64, ... ivfflat_probes_5: 1.0, hnsw_ef_search_40: ...}`.

---

## 6. Combining Vector Search with SQL `WHERE` Filters

RAG queries are almost never pure vector searches — "return warranty chunks **for products in EN region**". pgvector's semantics on this are subtle and important:

### 6.1 The naive pitfall (Supabase's docs headline it)

```sql
SELECT * FROM documents
WHERE header_path = 'Return Policy'
ORDER BY embedding <=> $query
LIMIT 5;
```

With an ANN index, **filtering happens after the index scan**: the index already returned its ef_search (default 40) candidates, and your WHERE filters them. If the filter matches 10% of rows, 40 × 10% → **~4 rows**, far fewer than 5. The module reproduces exactly this in `test_hnsw_where_filter_applied_after_scan`.

### 6.2 The fixes, in order of increasing effort

1. **Iterative index scans** (pgvector 0.8+): keep scanning the index until enough rows match (bounded by `hnsw.max_scan_tuples` / `ivfflat.max_probes`); `strict_order` keeps exact ordering, `relaxed_order` trades slight disorder for recall (use a materialized CTE to re-sort). Mirrored by `iterative=True` in both index classes.
2. **Raise ef_search / probes** (and LIMIT) — cheap band-aid, more work per query.
3. **Partial index** for a few distinct filtered values:
   `CREATE INDEX ... USING hnsw (...) WHERE (header_path = 'Return Policy');` — the module's `VectorTable.search(where=...)` is the mental model for what stays inside,
4. **Partitioning** (`PARTITION BY LIST (header_path)`) for per-tenant/per-category isolation — also the multi-tenancy answer (indexes shared across tenants let one tenant's vectors affect another's recall),
5. **A B-tree on the filter column** (`CREATE INDEX ON documents (header_path)`) — for highly selective filters, Postgres can do a fast *exact* search over just the matching rows; often the best answer of all.

### 6.3 Hybrid search — two retrieval signals in one DB

Postgres full-text search sits natively alongside your vector column (the README shows `plainto_tsquery` + RRF fusion examples; Crunchy Data has a whole "hybrid search patterns" follow-up). This is one of the strongest Postgres-first arguments: keyword AND semantics in one query plan, no second system.

---

## 7. Postgres-first vs Specialist Vector DBs

### 7.1 Choose Postgres + pgvector first when…

- **Your data already has relations.** Documents have owners, tenants, ACLs, timestamps, joins. Vector-native stores must bolt this on; Postgres starts with it.
- **Operational surface area matters.** One backup story, one replication story (WAL, point-in-time recovery), one permission model, dashboards you already run (`pg_stat_statements`, PgHero).
- **Corpus size is post-doc, pre-hyperscale.** pgvector comfortably handles tables of a few million vectors; hybrid SQL+vector and filtering are first-class. Don't adopt a specialized database until pgvector measurably hurts — quantize, index, or shard first.
- **You want ACID + transactions around index maintenance** (upserts that reindex on conflict, keep chunk text + vectors in lockstep — the Topic 26 ingest story falls out naturally).

### 7.2 Consider specialist stores when…

- scale is genuinely outside pgvector's comfort zone (billions of vectors, sub-10 ms p99 without massive RAM),
- multi-tenant isolation at scale with per-tenant QoS is the core requirement,
- advanced native capabilities you'd otherwise build: hybrid sparse+dense with learned fusion, GPU brute-force scans,
- you lean on per-collection dashboards/observability (Qdrant/Weaviate/Marqo/Milvus/Pinecone have vector-tuned tooling).

### 7.3 The framing to internalise

> Vector search is a *feature*, not generally an *architecture*. Postgres keeps it as a feature until scale or specialised semantics force architecture-level change. That's the same discipline as "plain fetch before a request-library" (Phase 2 aptitude) — stay on the simple path until evidence says not.

---

## 8. Implementation Walkthrough — `pgvector_sim.py`

One module, five layers, all deterministic (seeded(s)):

- **Operators:** `l2_distance` (`<->`), `cosine_distance` (`<=>`), `negative_inner_product` (`<#>`), each raising on dimension mismatch like an insert into `vector(n)`; NaN parity for zero-vector cosine (pgvector skips these from cosine indexes).
- **`VectorTable`:** the typed vector column — insertion validation, upsert (ON CONFLICT), delete, and exact `search(query, op, k, where=dict | predicate)` with ASC ordering; `plan()` reports `Seq Scan on items` (exact) vs `Index Scan` (with an index).
- **`build_corpus`:** 5 seeded clusters × 10 L2-normalised 3-d vectors, plus a held-out query per cluster — the fixture the whole module's tests live on (`test_build_corpus_fixture_shape_and_ids`).
- **`kmeans` / `IVFFlatIndex`:** seeded k-means++ + Lloyd iterations (pgvector's own build phase is literally k-means); `search(..., probes, iterative)` with probe-clamping, list caps, and the iterative widen loop in v0.8 style, plus `plan()` = `Index Scan using items_ivfflat_idx`.
- **`HNSWIndex`:** seeded exponential layer sampling; insert = greedy descent + diversity-aware `_select_neighbors`; search = greedy descent, then beam search with `ef_search`; optional `iterative` widening for filters; `plan()` = `Index Scan using items_hnsw_idx`.
- **`recall` / `index_health_check`:** the pgvector docs' exact-search-vs-ANN comparison, offline.

38 pytest tests. Two builds with the same seed produce identical structures (`test_ivfflat_deterministic_rebuilds`, `test_hnsw_deterministic_rebuilds_same_graph`), and ANN distances for shared rows match exact to float precision.

---

## 9. Pitfalls

1. **Forgetting `ORDER BY` + `LIMIT`** — the search silently degrades to a bitmap-less scan; `EXPLAIN` before blaming the index. `SET LOCAL enable_seqscan = off;` to prove it to yourself in a transaction.
2. **IVFFlat built too early** (or `lists` >> data) — the README says drop the index until the table has scale; the module raises instead (`build` on empty table is an error — the honest mirror).
3. **Default `probes`/`ef_search` in production** — probes defaults to 1 and ef_search to 40; both can silently destroy recall. Measure recall first, then tune, then encode the values as configuration, not as luck.
4. **Assuming ANN results set-stable** — the docs warn plainly: "unlike typical indexes, you will see different results after adding an approximate index." Anything that diffs snapshots of nearest neighbours must tolerate ANN-grade wobble or pin to exact for that job.
5. **Post-filtering distortion** — §6.2's 10% example: check result counts after WHERE; if short, use iterative scans / partial indexes / partitioning.
6. **Half the index in RAM?** — neither `halfvec` nor binary quantization is free: halfvec degrades resolution (recall@1 dips at long tail); binary re-rank keeps recall but adds a fetch step. Plan the memory budget before choosing the type — and remember HNSW indexes want to be memory-resident for speed.
7. **Mixing operators between tables** — one op per index, one metric per table; a `<#>`-indexed table queried with `<->` silently seq-scans.

---

## 10. Exercises

1. `CREATE TABLE` by hand for your own chunk store (choose table columns for `header_path`, custom metadata) with pgvector; then write the three nearest-neighbour SQL queries: `<->`, `<=>`, `<#>` — with the same query vector shape; check in your notes which ranks equal when vectors are unit length.
2. In a scratch branch of the module, add `probes=2, 4, all` IVFFlat probes against `recall` measure on your own toy corpus (from `build_corpus`, varied projections) and confirm the monotonicity; Where does HNSW at ef-like `16` sit relative to IVFFlat probes=1? Anything surprising?
3. Post-filtering lab: in `build_corpus(20 per cluster, dim=3)` create a filter that matches only 15% of rows; measure: (a) naive post-filter hits count with ef_search=12, (b) iterative=True hits count, (c) a `probes`-sized override. Briefly justify what production would have chosen here from pgvector 0.8+ docs.
4. Write the real SQL for hybrid search over your Postgres store: full-text `plainto_tsquery` for keyword filter + `ORDER BY embedding <=> q LIMIT 5` for semantic. Sketch how RRF would fuse them, in 5 sentences.
5. Compute the memory math (from §3) for your real project numbers: chunk count × chosen dims × storage of `vector`/`halfvec`, then heap the currently projected Postgres-first vs specialist decision against it.

---

## 11. Done-When Checklist

- [x] I can `CREATE TABLE` with a `vector(1536)` column, insert, and run the ASC-operator nearest-neighbour query from memory.
- [x] I know when a query plan does a Seq Scan vs Index Scan, and the two syntax ingredients (ORDER BY distance op + LIMIT) that make indexes usable.
- [x] I can argue IVFFlat-vs-HNSW against a concrete corpus size using the two names' knobs (probes / ef_search) and the recall-vs-speed-vs-memory axes.
- [x] I can explain the post-filtering footnote (why a WHERE filter returns fewer rows with ANN and what pgvector 0.8's iterative scans / partial indexes do about it).
- [x] I can defend Postgres-first vs a specialist vector DB with concrete triggers for switching.

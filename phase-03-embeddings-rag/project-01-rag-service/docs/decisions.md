# Architecture Decisions — Sourceline

Format: context → decision → consequences → alternatives → revisit trigger. Status is **Accepted
(blueprint)** unless noted. These are the decisions a reviewer should challenge; changing one requires
updating the affected docs and tests.

---

## ADR-001 — PostgreSQL + pgvector over a dedicated vector database

**Status:** Accepted · 2026-10-26

**Context.** The corpus is 38 Markdown notes, ~300 chunks, ~2 MB of vectors. The project needs
metadata filters, transactional ingestion, audit tables, and a reviewer-friendly setup. A dedicated
vector database adds a service, a backup, and a failure domain.

**Decision.** Use PostgreSQL 16 + pgvector ≥ 0.8 as the only datastore. Dense retrieval uses HNSW with
`vector_cosine_ops`; metadata lives in relational tables; a GIN FTS index exists only for the
embedding-outage fallback.

**Consequences.**

- Positive: one backup/restore, one pool, transactional upserts, SQL filters, easy Docker Compose.
- Positive: the corpus/audit/queries all live together; evaluation can query the same rows.
- Negative: ANN tuning (`ef_search`, `m`, `ef_construction`) is ours; filtered ANN can under-fill
  without iterative scans.
- Negative: vector dimension changes need a migration/table rebuild; no built-in multi-vector search.
- Negative: at very large scale, a dedicated store may win; we have not measured that.

**Alternatives.** Pinecone/Weaviate/Qdrant (operational overhead, another account/key for a reviewer);
SQLite + FAISS (no transactional filters, awkward concurrency); in-memory NumPy (not a real
persistence story).

**Revisit trigger.** > 1M chunks, p95 retrieval > 300 ms after tuning, or filtered recall that cannot
meet the eval gate with iterative scans.

---

## ADR-002 — Raw SQL + psycopg over an ORM

**Status:** Accepted · 2026-10-26

**Context.** The schema is six tables; the critical query is a pgvector ANN query with filters. An ORM
would hide the SQL plan and add a dependency that is not the subject being demonstrated.

**Decision.** Hand-written SQL in `persistence/sql.py` and repositories, parameterized only. psycopg 3
with a connection pool. Migrations are plain `.sql` files with a checksummed runner.

**Consequences.**

- Positive: explicit plans, easy `EXPLAIN`, no N+1 surprises, no ORM session lifecycle.
- Positive: the pgvector operator/index usage is visible and testable.
- Negative: row mapping is manual; schema changes touch SQL and dataclasses.
- Negative: no automatic migration generation; we write forward-only migrations.
- Negative: more boilerplate for simple CRUD (acceptable at this size).

**Alternatives.** SQLAlchemy Core/ORM (competent, but hides the ANN plan and adds a learning-surface
detour); asyncpg (fast, but psycopg sync is simpler with FastAPI's threadpool and TestClient);
Django ORM (wrong stack).

**Revisit trigger.** The schema grows beyond ~15 tables or team velocity demands an ORM; even then,
keep the ANN query raw.

---

## ADR-003 — Dense-only retrieval in v1; hybrid deferred

**Status:** Accepted · 2026-10-26

**Context.** Technical notes contain exact identifiers (`ef_search`, `Retry-After`, `HNSW`) that dense
embeddings can miss. Hybrid BM25+dense and reranking are Phase 4 topics (30–31). Project 1's syllabus
requires ingestion, query+citations, failure handling, and hand-written code — not hybrid.

**Decision.** v1 uses dense retrieval only. A lexical FTS path exists **only** as a labelled fallback
when query embedding is unavailable. No RRF, no learned reranker, no query expansion. The repository
interface and eval harness leave room for them.

**Consequences.**

- Positive: a measured baseline; one ranking path; simpler prompt budgeting.
- Positive: the fallback demonstrates graceful degradation without pretending to be hybrid search.
- Negative: exact-term and code-heavy questions will underperform; documented and measured.
- Negative: some comparison questions need both chunks; dense retrieval may pick only one.
- Negative: the next quality step is clear but out of scope; the README says so.

**Alternatives.** Add BM25+RRF now (untested, scope creep); cross-encoder rerank (latency/cost, needs
labels); query expansion (extra model call/failure mode).

**Revisit trigger.** Recall@10 < 0.90 on the golden set, or exact-term failures dominate the
attribution report. Then implement hybrid + RRF, evaluate, and only then consider a reranker.

---

## ADR-004 — JSON query endpoint first; SSE reserved

**Status:** Accepted · 2026-10-26

**Context.** Streaming improves perceived latency but complicates error handling, citation validation,
and the contract. The product claim is grounded answers with citations, not token-by-token UX.

**Decision.** v1 returns one JSON response. `POST /v1/query/stream` is reserved and returns `501`; it
is not in the v1 OpenAPI contract. The UI shows a loading state.

**Consequences.**

- Positive: validation happens before any bytes are sent; errors are clean; tests are simple.
- Positive: citations are complete when the answer arrives.
- Negative: a 4-second answer feels slower than a streamed one.
- Negative: a future stream needs a `retrieval` event, `token` events, a final `citations` event, and
  an error event; partial unvalidated text must be labelled.

**Alternatives.** Stream raw tokens (cannot validate before display); stream only after validation
(no perceived benefit); skip streaming (current).

**Revisit trigger.** Demo feedback shows perceived latency is the main complaint, or a UX requirement
demands it. Then design the SSE contract with validation semantics first.

---

## ADR-005 — Content-addressed chunk IDs + per-document transactions

**Status:** Accepted · 2026-10-26

**Context.** Re-ingesting the corpus must not duplicate rows or re-embed unchanged text. Editing an
early section must not shift IDs for every later chunk. A failed document must not leave a
half-updated version.

**Decision.** `chunk_id = sha256(doc_id, heading_path, content, occurrence)[:24]`; `ordinal` and line
numbers are metadata, not identity. Diff new vs existing IDs: insert missing, update metadata for
existing, delete absent. One transaction per document; embeddings happen before the transaction.

**Consequences.**

- Positive: unchanged corpus = zero embedding calls; earlier edits do not invalidate later chunks.
- Positive: line shifts update metadata without re-embedding; failed docs keep the old version.
- Positive: citations remain stable while content is unchanged.
- Negative: an edit inside a chunk creates a new ID; the old row is deleted, so an old citation 404s
  (correct audit behaviour, but the UI must handle it).
- Negative: duplicate identical text needs an occurrence counter; a naive hash would collide.
- Negative: renames are delete+new in v1 (content-hash rename detection deferred).

**Alternatives.** Ordinal-based IDs (fragile to insertions); random UUIDs (no idempotency); hash of
whole document only (cannot diff chunks); upsert by `(doc_id, ordinal)` (tail rewrite).

**Revisit trigger.** Rename detection becomes a measured cost problem, or chunk identity needs to
survive heading renames (then include a stable section key).

---

## ADR-006 — One active embedding profile; full reindex on change

**Status:** Accepted · 2026-10-26

**Context.** Vectors from different models/dimensions are not comparable. Mixing them in one table
silently corrupts similarity scores. Postgres cannot alter `vector(1536)` to `vector(768)` in place.

**Decision.** A single profile key (`chunker|target|overlap|model|dimensions`) is stored on every row
and in `index_state`. Readiness compares the configured and active profiles. Any component change
requires a full rebuild; v1 uses a maintenance window (status `building`, readiness 503). No mixed
profiles, no silent model upgrade.

**Consequences.**

- Positive: correctness by construction; a wrong-profile query fails closed.
- Positive: the eval report always states the profile, so numbers are comparable.
- Negative: a model change is an outage/maintenance event in v1.
- Negative: a 768-dim local model needs a schema migration and rebuild.
- Negative: no zero-downtime blue/green in v1 (documented scaling path).

**Alternatives.** Store multiple embeddings per chunk (complexity, query routing); re-embed in place
(mixed rows during the run); trust the provider not to change (unsafe).

**Revisit trigger.** Model churn becomes frequent, or zero-downtime deploys are required. Then add a
`chunks_v2` table/view switch or a separate embedding table with an active-version pointer.

---

## ADR-007 — Structured output + deterministic citation validator

**Status:** Accepted · 2026-10-26

**Context.** Free-form prose is easy to display but hard to validate. Citations can be hallucinated,
misnumbered, or attached to unsupported claims.

**Decision.** The model returns JSON (`answer`, `abstained`, `abstention_reason`, `used_markers`).
The validator checks marker range, sentence coverage, and (as a diagnostic) weak support. One repair
attempt on schema/validation failure; then abstain. Citations are assembled from DB rows, never from
model-supplied metadata.

**Consequences.**

- Positive: deterministic checks; forged URLs/lines are impossible; the contract is testable.
- Positive: repair handles occasional JSON slips without a 5xx.
- Negative: structured-output support varies by provider; Ollama may need JSON mode + higher repair
  rate.
- Negative: sentence coverage is heuristic; semantic entailment is not proven.
- Negative: strict validation increases abstention; measured as over-abstention.

**Alternatives.** Parse free-form citations (brittle); trust the model's source strings (unsafe); use
an LLM judge at request time (latency/cost/nondeterminism); skip validation (not acceptable).

**Revisit trigger.** A provider with reliable native grounded citations changes the cost/benefit, or
claim-level NLI becomes cheap enough for the request path.

---

## ADR-008 — Fail closed on grounding

**Status:** Accepted · 2026-10-26

**Context.** A wrong answer with a plausible citation damages trust more than a refusal. The product
claim is "grounded answers with citations".

**Decision.** If no evidence clears the floor, the model reports insufficiency, the schema fails after
one repair, or citation validation fails after one repair, return `200 abstained=true` with a reason
(no answer) or a 503 for infrastructure failures. Never return an uncited answer as grounded.

**Consequences.**

- Positive: no unlabelled hallucination path; the UI can show a clear refusal.
- Positive: metrics separate false answers from over-abstention.
- Negative: some answerable questions are refused; the eval gates over-abstention at ≤ 5%.
- Negative: a strict validator can reject a good paraphrase; weak-support is diagnostic, not a hard
  fail, to limit this.
- Negative: users may perceive refusal as failure; closest sources help them rephrase.

**Alternatives.** Best-effort answer with a warning (violates the claim); always answer (unsafe);
human-in-the-loop (no users).

**Revisit trigger.** Over-abstention exceeds the gate after retrieval improvements; then tune the
validator/floor with evidence, not by removing the gate.

---

## ADR-009 — Labelled degraded modes, not silent fallbacks

**Status:** Accepted · 2026-10-26

**Context.** Providers fail. A 500 is unhelpful; a silent fallback can look like a normal answer and
mislead the reader. The demo must show failure behaviour.

**Decision.** Two explicit fallbacks:

1. **Extractive** when chat is unavailable: verbatim sentences from top evidence, cited, labelled
   `degraded.mode=extractive`.
2. **Lexical** when query embedding is unavailable: FTS retrieval with a separate floor, labelled
   `degraded.mode=lexical`.

Both reuse the citation validator; neither fabricates. DB/index failures fail closed with 503. Every
fallback is metered/logged.

**Consequences.**

- Positive: the service stays useful during a provider outage without lying about how.
- Positive: the label is testable and visible in the UI.
- Negative: two code paths to maintain/test; lexical quality is lower.
- Negative: extractive answers are less fluent and do not synthesise.
- Negative: a labelled degraded answer still costs retrieval/compute; acceptable.

**Alternatives.** Always 503 (simpler, less useful); silently use a smaller model (unlabelled,
confusing); cache last answers (stale, unsafe).

**Revisit trigger.** Fallback usage is nonzero outside drills (indicates a chronic dependency issue),
or a model-routing layer (topic 19c) can provide a labelled alternate model instead.

---

## ADR-010 — Corpus = this curriculum; adapter interface for future sources

**Status:** Accepted · 2026-10-26

**Context.** "Real document set" needs to be real, legally safe, reproducible, and verifiable. The
curriculum is authored here, versioned, 38 notes/83k words, and grows with the author. An external
corpus adds licensing, download, and freshness complexity.

**Decision.** v1 ingests the Phase 1–3 Markdown notes from this repository. Root `README.md`/
`SYLLABUS.md` are optional (`--include-meta`). The ingestion layer exposes a `CorpusAdapter` boundary
so a PDF/HTML/public-doc adapter can be added without changing the query path. No per-document ACLs in
v1 because the corpus is public.

**Consequences.**

- Positive: every citation is verifiable in the same checkout; no third-party redistribution.
- Positive: questions are relevant to the author's expertise and the demo story is coherent.
- Positive: no network at ingest; reproducible in CI.
- Negative: 38 docs is small; evaluation is tractable but not a scale proof.
- Negative: self-authored corpus may be less impressive than a well-known public dataset; the
  engineering, not the content, is the point.
- Negative: no ACL model; a private corpus would need one before retrieval.

**Alternatives.** FastAPI docs snapshot (public, larger, licensing/reproducibility work); a mix
(scope creep); synthetic fixtures (not "real").

**Revisit trigger.** A reviewer wants a scale demo, or the project needs multi-tenant/private corpora.
Then add an adapter + ACLs + a larger eval set, and keep the curriculum as the default demo.

---

## ADR-011 — In-memory rate limits and breakers for v1

**Status:** Accepted · 2026-10-26

**Context.** The demo is one API process. Redis adds a service and a failure mode. Shared state only
matters with multiple workers/replicas.

**Decision.** Token buckets, concurrency semaphores, and circuit breakers are in-process. The README
states the single-process assumption. At 10× traffic, move shared state to Redis and size pools.

**Consequences.**

- Positive: zero extra infrastructure; simple tests; deterministic.
- Positive: breakers still protect each worker from a dead dependency.
- Negative: with N workers, effective limits are ~N× the configured value; breaker state is per
  worker.
- Negative: a restart resets limits/breakers.
- Negative: not suitable for a multi-tenant hosted service without the upgrade.

**Alternatives.** Redis now (overkill for the demo); API-gateway limits only (no per-IP concurrency);
no limits (cost/DoS risk).

**Revisit trigger.** More than one API worker/replica, or a public demo with abuse. Then implement a
Redis-backed limiter/idempotency/breaker with the same interfaces.

---

## ADR-012 — Hand-written application code; infrastructure libraries only

**Status:** Accepted · 2026-10-26

**Context.** The syllabus requires "hand-written throughout". Frameworks hide the pipeline and make
the portfolio indistinguishable from a tutorial. Infrastructure libraries are still sensible.

**Decision.** No LangChain, LlamaIndex, RAG framework, ORM, scaffold generator, or copied end-to-end
project. Allowed: FastAPI, Pydantic, psycopg, provider SDK/HTTP client, uvicorn, pytest, ruff, mypy,
prometheus-client. Chunking, prompt assembly, citations, retries, breaker, SQL, and eval are written
and tested here. Adapted snippets carry a source comment.

**Consequences.**

- Positive: the engineering is visible and defensible; every stage is testable.
- Positive: fewer dependencies and less magic; easier to explain in an interview.
- Negative: more code and more bugs than a framework call; slower to build.
- Negative: some solved problems are re-solved (tokenization, retries) — deliberately, with tests.
- Negative: reviewer must trust the policy; `check_no_frameworks.py` + commit history + ADR help.

**Alternatives.** LangChain (fast, hides the point); a framework for ingestion only (still muddies the
claim); copy a tutorial (fails the syllabus and the interview).

**Revisit trigger.** Never for this project. A production team may choose frameworks; the portfolio
artifact keeps the hand-written path.

---

## ADR-013 — No response cache in v1

**Status:** Accepted · 2026-10-26

**Context.** A demo repeats the same questions; caching would cut latency/cost. But a cache hides
provider failures, complicates invalidation on re-ingest/profile change, and can serve stale
citations.

**Decision.** No response or query-embedding cache in v1. Every query exercises the real path.
Ingestion idempotency is separate and retained.

**Consequences.**

- Positive: demos show real latency/failure behaviour; no stale-citation class of bug.
- Positive: simpler correctness story; eval measures the actual path.
- Negative: repeated demo questions cost money and take the same time.
- Negative: no latency win at high repeat volume.

**Alternatives.** Exact-question cache (must key on profile+filters, invalidate on ingest); semantic
cache (unsafe/stale); provider prompt cache (model-side, may still apply).

**Revisit trigger.** A hosted demo with high repeat traffic and a measured cost/latency problem. Then
add a short-TTL exact cache keyed by normalized question + profile + filters, with explicit
invalidation and a `cached` flag.

# Interview Notes — Sourceline

**How to use this:** these are the answers you should be able to give without reading the docs, plus
the file to open when asked "show me". Replace every `<measured>` with the real number from the eval
report before an interview; never quote a target as a result.

---

## 1. "Walk me through a query."

> "FastAPI validates and rate-limits the request, then `QueryService` embeds the question with the
> same pinned profile used at ingest. It runs one SQL query over `chunks JOIN documents`: pre-filter
> by phase/topic/type, order by pgvector cosine distance, over-fetch 40 candidates. Then I dedupe
> exact and near-duplicates, order the evidence in a sandwich for attention, and pack it into a
> 6,000-token budget. A static prompt skeleton renders numbered evidence blocks and puts the question
> last. The model returns structured JSON; a deterministic validator checks every marker and every
> factual sentence. If anything fails, one repair, then abstain. The response includes citations built
> from the database rows, per-stage timings, and a request ID."

Open: `docs/retrieval-and-answering.md`, `docs/api-contract.md`.

---

## 2. "Why pgvector instead of Pinecone/Weaviate?"

> "At 38 documents and ~300 chunks, a dedicated vector database is operational overhead without a
> measured benefit. Postgres gives me transactions, metadata filters, full-text fallback, and the
> corpus/audit tables in one place. pgvector's HNSW is good enough; I measure recall against exact
> search. The migration path is documented: if scale or recall demands it, the retrieval interface is
> one repository method, and I would benchmark before moving."

Also mention: one backup, one connection pool, one failure domain; the trade-off is ANN tuning and
less specialized filtering than a vector DB.

Open: ADR-001, `docs/data-model.md`.

---

## 3. "How did you choose chunking?"

> "Structural, not fixed-size. I split on H2/H3, then paragraphs, keep fenced code and tables atomic,
> target 1,200 characters with 150 characters of overlap, and store exact line ranges. The heading
> breadcrumb goes into the embedding text but not the stored content, so citations stay verbatim. I
> tested boundary questions and compared sizes on the dev set; `<measured>` won on recall vs context
> precision."

Be honest: fixed-size is simpler; structural wins on technical notes because headings and code carry
meaning. The chunker has a version and a profile key; changing it forces a full reindex.

Open: `docs/ingestion.md`, chunker tests.

---

## 4. "How do you know retrieval works?"

> "Recall@10 and MRR on 80 labelled cases, split dev/test. I also log the four sets per query:
> retrieved, prompted, cited, and the answer. If the gold chunk is missing from `retrieved`, it is a
> retrieval miss; if it is retrieved but not prompted, it is a ranking/assembly miss. Those have
> different fixes. A single answer-quality number would hide that."

Numbers: recall@10 = `<measured>`, MRR = `<measured>`, candidate recall@40 = `<measured>`.

Open: `docs/evaluation.md`, `GET /v1/admin/queries/{id}`.

---

## 5. "How do you prevent hallucinations?"

> "Layered, and I state the limit. The prompt restricts the model to evidence and requires a citation
> per factual sentence. Output is structured JSON. The validator checks markers against the assembled
> map, rejects out-of-range markers, and requires sentence coverage of 1.0; otherwise one repair, then
> abstention. Citations are built from DB rows, so the model cannot forge a URL or line number.
> Semantic entailment is *measured* in eval with a calibrated judge and a human sample, not proven at
> runtime. That is the honest boundary."

If asked "what if the model cites a real chunk that doesn't support the claim?": "The weak-support
heuristic flags low overlap, but it is not entailment. Eval catches it; claim-level NLI is future
work. I would rather say that than overclaim."

Open: `docs/retrieval-and-answering.md` §7, validator tests.

---

## 6. "What happens when the provider is down?"

> "Every outbound call goes through a classifier, bounded retries with full jitter, `Retry-After`
> parsing, a deadline, and a circuit breaker. SDK retries are disabled so attempts don't multiply.
> If chat is down, the service returns a labelled extractive answer from the retrieved evidence, with
> citations, or a clean 503; never a 500 or an unlabelled guess. If embeddings are down at query time,
> lexical fallback is labelled; ingestion fails the affected document and leaves the old version
> intact. If Postgres is down, it fails closed."

Mention the chaos matrix and one drill result.

Open: `docs/failure-handling.md`.

---

## 7. "Why no LangChain / hybrid search / reranker?"

> "Because the point is to demonstrate the pipeline, not a framework call, and because hybrid/rerank
> need their own evaluation. Dense-only is the v1 baseline; the lexical path exists only as an outage
> fallback. The interfaces leave room for RRF and a cross-encoder, and the eval harness is the gate.
> I would rather ship a measured dense baseline than an unmeasured kitchen sink."

This also answers "why not agents?": no tools/writes, smaller blast radius, and the product is
grounded Q&A, not task automation.

Open: ADR-003, ADR-012, `docs/decisions.md`.

---

## 8. "Latency and cost?"

> "p95 end-to-end `<measured>` with real providers; retrieval p95 `<measured>`; the LLM dominates.
> Prompt is ~4–5k tokens, output ≤ 500, cost/query `<measured>`. Budgets are explicit; the hosted demo
> has a daily cap and per-IP limits. Ingest of the full corpus is `<measured>`; unchanged re-ingest is
> zero embeddings."

If the numbers are not measured yet, say "target ≤ 6 s / ≤ $0.01; the eval report has the actuals"
rather than inventing.

---

## 9. "How do you handle stale or conflicting documents?"

> "Freshness: every document and the index record the source commit; `/v1/ready` exposes age and a
> stale flag; deploy-time ingest is part of the release. A stale index is visible, not silent.
> Conflicts: the retriever may return both chunks; v1 surfaces both rather than pretending one is
> authoritative. A production system needs authority/recency metadata and a conflict policy; that is
> a documented limitation, not something I hand-wave."

Open: `docs/data-model.md` §9, `docs/retrieval-and-answering.md` §9.

---

## 10. "Security and prompt injection?"

> "The corpus is semi-trusted; evidence is escaped and confined to a data slot, and the model has no
> tools, browsing, or writes. Output is schema-validated and citations are checked. The admin surface
> is token-protected and not public; SQL is parameterized; corpus paths are allow-listed; rate limits
> and a budget cap bound abuse; secrets are env-only and redacted. Residual risk: a hostile document
> can still steer prose. I state that instead of claiming immunity."

Open: `docs/security-and-privacy.md`.

---

## 11. "What changes at 10× or 100×?"

> "10× traffic: Redis for shared rate limits/idempotency/breaker state, more API workers, pool tuning.
> 10× corpus: separate ingest worker/queue, bulk load then build HNSW, partitioning by phase/source.
> 100×: read replica or a dedicated vector store, but only after benchmarking; hybrid + rerank for
> quality. The current single-process in-memory state is a documented v1 trade-off, not an accident."

Open: `architecture.md` §11.

---

## 12. "What's the biggest weakness / what would you do differently?"

Pick one and be specific:

- "Dense-only retrieval misses exact API terms; the next quality step is hybrid + rerank, measured on
  the same set."
- "Citation validation is syntactic; semantic claim checking is the real hard problem."
- "The eval set is 80 cases; I report counts, not just percentages, and I would grow it from real
  failures."
- "I would build the eval harness earlier; prompt tuning without it is guesswork."

Avoid "nothing" and avoid blaming the model.

---

## 13. "Prove it's hand-written."

> "No LangChain/LlamaIndex/ORM; the chunker, prompt assembly, citation validator, retry wrapper,
> breaker, SQL, and eval runner are in `src/` with tests. The decisions doc records the policy and any
> adapted snippet has a source comment. The commit history shows the build order. You can run
> `scripts/check_no_frameworks.py`."

Open: ADR-012, `src/sourceline/domain/`, `resilience/`.

---

## 14. "What is not production-ready?"

Say it plainly:

- single process, in-memory limits/breakers;
- no per-user auth/ACLs;
- no claim-level entailment;
- no hybrid/rerank;
- forward-only migrations and a maintenance window for profile changes;
- no streaming;
- English-centric tokenizer/FTS;
- prompt injection mitigated, not solved;
- eval set small.

Then: "For a portfolio, the goal is to demonstrate the engineering and its boundaries, not to pretend
a single-node demo is a multi-tenant platform."

---

## 15. Quick reference

| Question | File |
|---|---|
| Requirements / acceptance | `project_requirements.md` |
| Components / flows | `architecture.md` |
| API shape / errors | `docs/api-contract.md`, `docs/openapi.yaml` |
| Schema / invariants | `docs/data-model.md` |
| Ingestion / idempotency | `docs/ingestion.md` |
| Retrieval / citations / abstention | `docs/retrieval-and-answering.md` |
| Retries / breakers / degraded | `docs/failure-handling.md` |
| Eval metrics / gates | `docs/evaluation.md` |
| Tests / chaos | `docs/testing.md` |
| Logs / metrics / alerts | `docs/observability.md` |
| Security / privacy | `docs/security-and-privacy.md` |
| Run / deploy / recover | `docs/deployment-and-runbook.md` |
| Trade-offs | `docs/decisions.md` |
| Demo | `docs/demo-script.md` |

---

## 16. Numbers sheet (fill after evaluation)

| Metric | Value | Date/commit/profile |
|---|---:|---|
| Documents / chunks | `<measured>` | |
| Recall@10 | `<measured>` | |
| MRR | `<measured>` | |
| Citation validity | `<measured>` | |
| Groundedness | `<measured>` | |
| False-answer rate | `<measured>` | |
| Over-abstention | `<measured>` | |
| p50 / p95 latency | `<measured>` | |
| Cost/query | `<measured>` | |
| Full ingest duration | `<measured>` | |
| Judge/human agreement | `<measured>` | |

If a number is missing, say "not measured yet"; do not fill it with a target.

# Project 1 — Sourceline

**A RAG service over a real document set: grounded answers with line-level citations.**

> **Status: design blueprint + empty scaffold.** The specification is complete, and the target
> folders plus every Python module listed in `project_folder_hierarchy.md` exist as zero-byte
> placeholders. No application logic, configs, SQL, static assets, or Docker files are implemented
> yet. The finished README (the one a hiring manager reads) must replace the status banner and the
> "target quickstart" section with recorded output.

Sourceline answers questions about the 28-topic AI-engineering curriculum in this repository.
It ingests the actual Markdown notes, chunks and embeds them into PostgreSQL + pgvector, retrieves
the passages that support an answer, assembles a budgeted prompt, and returns a concise answer
where **every factual sentence carries a citation** that resolves to a file, heading, and line
range. When the corpus does not contain the answer, it says so instead of guessing.

---

## Why this corpus

The corpus is not a toy fixture. It is the repository the project lives in:

| Property | Value (measured 2026-10-26) |
|---|---:|
| Markdown documents | 38 |
| Words | 83,348 |
| Raw size | ~594 KB |
| Structure | H1/H2/H3 headings, code fences, tables, cross-links |
| Licence | authored in this repository; no third-party corpus to redistribute |
| Reproducibility | clone the repo; the corpus arrives with it |

That gives a hiring manager a uniquely verifiable demo: every citation can be opened in the same
checkout, at the same commit. It also gives the project realistic retrieval problems — exact API
names, acronyms, code blocks, tables, near-duplicate explanations across topics, and questions that
span two notes files.

The ingestion layer is source-agnostic (`CorpusAdapter`), so an external public corpus (for example
a pinned FastAPI documentation snapshot) can be added later without changing the query path. That is
a stretch goal, not part of v1.

---

## What the finished service does

- **Ingests** the curriculum with a structural Markdown chunker, embeds batches, and upserts into
  pgvector **idempotently**: re-running on unchanged documents makes zero embedding calls; editing
  one section re-embeds only the affected chunks; deleting a section prunes its rows.
- **Answers** `POST /v1/query` with prose plus structured citations:

  ```json
  {
    "answer": "HNSW trades recall for latency by searching a hierarchical graph ... [1][2]",
    "citations": [
      {
        "marker": 1,
        "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
        "heading": "5.3 HNSW — hierarchical navigable small world graphs",
        "lines": [134, 158],
        "url": "https://github.com/<owner>/<repo>/blob/<commit>/phase-03-embeddings-rag/topic-25-pgvector/notes.md#L134-L158"
      }
    ],
    "abstained": false,
    "grounded": true
  }
  ```

  (Illustrative shape, not a recorded answer.)

- **Abstains** with a machine-readable reason when retrieval finds no evidence above the calibrated
  floor, when the model reports insufficient evidence, or when citation validation fails after one
  repair attempt.
- **Exposes diagnostics** behind `?debug=1` and an admin token: retrieved candidates and scores,
  what survived deduplication and budgeting, prompt token accounting, and per-stage latency.
- **Applies topic 19 failure handling** to every outbound call: error classification, bounded
  retries with exponential backoff + full jitter, `Retry-After` parsing (seconds and HTTP-date),
  per-attempt and overall deadlines, circuit breakers, idempotent ingestion, and explicit degraded
  modes. The LLM being down does not produce a 500; it produces a labelled extractive answer or a
  clean 503.
- **Proves itself** with a golden evaluation set, a smoke gate in CI, and a diagnostic suite that
  attributes failures to retrieval, ranking, or generation (topic 28).

---

## Architecture at a glance

```text
 Browser / curl
      │  HTTPS + JSON
      ▼
 ┌──────────────────────────────┐        ┌───────────────────────────────┐
 │ FastAPI                      │        │ Ingestion CLI / admin job     │
 │  middleware: request-id,     │        │  walk → parse → chunk →       │
 │  rate limit, error envelope  │        │  embed → upsert → prune       │
 │  /v1/query  /v1/documents    │        └───────────────┬───────────────┘
 │  /v1/ready  /metrics         │                        │
 └───────┬──────────────┬───────┘                        │
         │              │                                │
         ▼              ▼                                ▼
 ┌────────────────┐  ┌──────────────────────────────────────────────┐
 │ QueryService   │  │ PostgreSQL 16 + pgvector                     │
 │ embed → search │  │ documents · chunks · ingest_runs · query_logs│
 │ → assemble →   │  │ HNSW index · FTS fallback · migrations       │
 │ LLM → validate │  └──────────────────────────────────────────────┘
 └───┬────────┬───┘
     │        │
     ▼        ▼
 ┌─────────┐ ┌──────────┐
 │Embedding│ │ Chat LLM │   both behind one resilience layer:
 │ provider│ │ provider │   retry · backoff+jitter · Retry-After ·
 └─────────┘ └──────────┘   circuit breaker · deadline · bulkhead
```

Full component, sequence, data-model, and circuit-breaker diagrams live in
[`architecture.md`](architecture.md) and [`docs/diagrams/`](docs/diagrams/).

---

## Blueprint map

| Document | What it decides |
|---|---|
| [`project_requirements.md`](project_requirements.md) | Personas, user stories, numbered functional/non-functional requirements, acceptance criteria |
| [`architecture.md`](architecture.md) | Components, data flows, deployment topology, trust boundaries, scaling path |
| [`project_folder_hierarchy.md`](project_folder_hierarchy.md) | Exact target tree, layer rules, naming, generated-vs-hand-written policy |
| [`docs/api-contract.md`](docs/api-contract.md) | Endpoints, request/response schemas, errors, limits, auth, retries |
| [`docs/data-model.md`](docs/data-model.md) | Tables, constraints, indexes, lifecycle, retention |
| [`docs/ingestion.md`](docs/ingestion.md) | Corpus rules, chunking, embedding profile, idempotency, reindex triggers |
| [`docs/retrieval-and-answering.md`](docs/retrieval-and-answering.md) | Retrieval, dedupe, ordering, budget, prompt, citations, abstention |
| [`docs/failure-handling.md`](docs/failure-handling.md) | Topic 19 applied: taxonomy, retry matrix, breakers, degraded modes, chaos tests |
| [`docs/evaluation.md`](docs/evaluation.md) | Golden set, metrics, baselines, CI gates, human review |
| [`docs/testing.md`](docs/testing.md) | Unit/integration/contract/chaos/e2e matrix and fixtures |
| [`docs/observability.md`](docs/observability.md) | Logs, metrics, traces, dashboards, alerts |
| [`docs/security-and-privacy.md`](docs/security-and-privacy.md) | Threat model, controls, PII, prompt injection, cost abuse |
| [`docs/deployment-and-runbook.md`](docs/deployment-and-runbook.md) | Docker quickstart, migrations, backup/restore, incident runbook |
| [`docs/milestones.md`](docs/milestones.md) | Build order, exit criteria, effort shape |
| [`docs/demo-script.md`](docs/demo-script.md) | Three-minute portfolio demo and failure-mode demo |
| [`docs/risk-register.md`](docs/risk-register.md) | Risks, triggers, mitigations |
| [`docs/interview-notes.md`](docs/interview-notes.md) | Likely questions and the reasoning to defend |
| [`docs/decisions.md`](docs/decisions.md) | ADR-001 … ADR-013 with alternatives and consequences |
| [`docs/openapi.yaml`](docs/openapi.yaml) | Machine-readable API contract |
| [`corpus/`](corpus/) · [`evals/`](evals/) | Manifest schema, dataset schema, corpus/eval rules |

---

## Target quickstart (the finished README contract)

These are the commands the completed project **must** support on a fresh machine. They are written
now so the implementation is built against a concrete run experience, not retrofitted.

### Docker path (recommended for reviewers)

```bash
git clone <repo-url> && cd <repo>/phase-03-embeddings-rag/project-01-rag-service
cp .env.example .env          # add SOURCELINE_OPENAI_API_KEY + SOURCELINE_ADMIN_TOKEN (or use Ollama)
docker compose up -d db
docker compose run --rm api python -m sourceline.migrate
docker compose run --rm api python -m sourceline.ingest --root /corpus
docker compose up api
```

Open <http://127.0.0.1:8000/> for the demo UI, <http://127.0.0.1:8000/docs> for Swagger, and:

```bash
curl -s http://127.0.0.1:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"How does HNSW trade recall for speed?","top_k":6}'
```

### Local Python path

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:SOURCELINE_DATABASE_URL="postgresql://sourceline:sourceline@localhost:5432/sourceline"
python -m sourceline.migrate
python -m sourceline.ingest --root ..\..\
uvicorn sourceline.main:app --reload
```

The finished README must add: a 20-second GIF, a table of measured evaluation numbers, the
architecture image, the failure-mode demo, limitations, and a "what I would do next" section.
See [`docs/demo-script.md`](docs/demo-script.md) for the recording plan.

---

## Quality bar (targets, measured after implementation)

| Metric | Target | Where enforced |
|---|---:|---|
| Citation validity on answered responses | **100%** | deterministic validator + CI |
| Golden-set groundedness | **≥ 0.95** | eval gate |
| Retrieval recall@10 (any gold chunk) | **≥ 0.90** | eval gate |
| False-answer rate on unanswerable set | **≤ 5%** | eval gate |
| p95 end-to-end latency (real providers) | **≤ 6 s** | load test / dashboard |
| Ingest of the full 38-document corpus | **≤ 3 min** | ingest report |
| Idempotent re-ingest embedding calls | **0** | integration test |
| Unit + integration test suite | **green, no network** | CI |

These are commitments for the build. They are deliberately absent from the README until they are
actually measured; no invented numbers.

---

## Definition of done (syllabus mapping)

- [ ] **Real document set ingested (chunk → embed → pgvector).**
      Evidence: `ingest_runs` report, `documents`/`chunks` counts, zero-call re-ingest test, and a
      full `make ingest` transcript against the 38-file corpus.
- [ ] **Query endpoint returning grounded answers with citations.**
      Evidence: `POST /v1/query` with validated `1..n` markers, resolved citation objects, abstention
      path, citation-validity test, and the golden-set report.
- [ ] **Failure handling from topic 19 applied.**
      Evidence: retry wrapper with jitter + `Retry-After`, circuit breakers, deadlines, idempotent
      ingestion, degraded modes, and the fault-injection test matrix.
- [ ] **Hand-written throughout.**
      Evidence: no RAG framework, no ORM, no generated scaffolding; raw SQL; commit history;
      `docs/decisions.md` ADR-012 and the review checklist.
- [ ] **A hiring manager can run it from the README.**
      Evidence: fresh-machine Docker transcript, seeded corpus, no undocumented steps, hosted demo
      link (optional but recommended).

---

## Build order

`M0 design` (this folder) → `M1 skeleton + DB` → `M2 corpus + chunker` → `M3 embeddings + ingest`
→ `M4 retrieval` → `M5 answer + citations` → `M6 API + UI` → `M7 resilience` → `M8 evaluation`
→ `M9 docs + demo + deploy`. Exit criteria per milestone are in
[`docs/milestones.md`](docs/milestones.md). Do not start M5 before M3's idempotency tests pass;
do not start M8 before the answer path has a stable contract.

---

## Non-goals for v1

- Multi-tenant accounts, SSO, per-user document permissions.
- Hybrid BM25+dense fusion and a learned reranker (Phase 4 topics 30–31; interfaces left open).
- Agentic tools, web browsing, or write actions.
- Fine-tuning, custom embedding training, or a GPU stack.
- A distributed job queue or multi-region deployment.
- Perfect groundedness. The service measures and reports it; it does not claim to solve it.

---

## Hand-written policy

Application code is authored by hand: no LangChain, LlamaIndex, RAG frameworks, ORMs, scaffolding
generators, or copy-pasted tutorial projects. Infrastructure libraries are allowed where they are
not the subject being demonstrated: FastAPI, Pydantic, psycopg, the provider SDK/HTTP client,
uvicorn, pytest, ruff, mypy. SQL, chunking, prompt assembly, citation validation, retries, the
circuit breaker, and the evaluation runner are written and tested in this repository. Any adapted
snippet carries a source comment. See ADR-012.

---

## Licence and corpus

Application code: MIT (add `LICENSE` at implementation). The curriculum text under
`phase-*/**/*.md` remains the author's content and is included as the demo corpus; quoted
third-party material inside the notes remains under its original licence. The README must state
this explicitly so a reviewer is not misled about the corpus licence.

# Milestones — Sourceline

**Build order matters.** Each milestone has a demonstrable exit criterion and evidence. Do not start
the next milestone because the previous one "mostly works"; start it because the exit criterion is
met. Effort is an indication for part-time work, not a promise.

```text
M0 Design ─► M1 Skeleton/DB ─► M2 Corpus/Chunker ─► M3 Embed/Ingest
   ─► M4 Retrieval ─► M5 Answer/Citations ─► M6 API/UI
   ─► M7 Resilience ─► M8 Evaluation ─► M9 Portfolio polish
```

---

## M0 — Design blueprint (current)

**Deliverables**

- `README.md`, `project_requirements.md`, `architecture.md`, `project_folder_hierarchy.md`.
- `docs/` (API, data model, ingestion, retrieval/answering, failure handling, evaluation, testing,
  observability, security, deployment/runbook, milestones, demo, risks, interview notes, ADRs).
- Diagrams, OpenAPI, schemas, `.env.example`.

**Exit criteria**

- Every syllabus bullet for Project 1 maps to an acceptance criterion and a document.
- Architecture, folder tree, API, schema, and failure policy do not contradict each other.
- A reviewer can explain the system after reading the README + architecture.
- No application code is present.

**Evidence:** this folder. **Estimate:** done.

---

## M1 — Skeleton, configuration, database, migrations

**Deliverables**

- `pyproject.toml`, package skeleton, `config.py` with validation/profile derivation.
- `db/migrations/001_init.sql` … `003_seed_index_state.sql`.
- Migration runner + `python -m sourceline.migrate`.
- FastAPI `create_app`, `/v1/health`, `/v1/ready` (will report `index_not_ready` until M3).
- Structured logging + request ID middleware.
- Dockerfile + compose `db`/`api`.
- Unit tests for config; integration tests for migrations.

**Exit criteria**

- Fresh DB: migrations apply, re-apply is a no-op, checksum mismatch fails.
- `docker compose up -d db` + migrate works on Windows and Linux.
- `/v1/health` 200 with no DB; `/v1/ready` 503 with a machine reason.
- `ruff` and `mypy` pass; no secrets committed.

**Evidence:** migration transcript, health/ready curl output, test run.
**Depends on:** M0. **Estimate:** 1–2 days.
**Risk:** over-engineering the app factory. Keep it one process, one pool, no DI framework.

---

## M2 — Corpus discovery and chunking

**Deliverables**

- `domain/corpus.py`: include/exclude rules, normalisation, hashing, metadata, manifest.
- `domain/chunking.py`: structural Markdown chunker, line ranges, content-addressed IDs.
- `domain/tokens.py`: pinned tokenizer + budget helpers (budget used later).
- `corpus/manifest.schema.json` validation.
- `tests/unit/test_chunking.py`, `test_tokens_budget.py`, discovery tests.
- `scripts/build_corpus_snapshot.py`.

**Exit criteria**

- Discovering `../..` yields exactly the expected 38 documents, deterministic order.
- Every chunk's `[start_line, end_line]` slice equals `content` for the fixture corpus.
- No chunk splits a fence/table; oversize units are flagged.
- Manifest hash is stable across CRLF/LF checkouts.
- Chunker tests cover headings, overlap, code, tables, duplicates, occurrence IDs.

**Evidence:** corpus report (docs, words, chunks, p50/p95 tokens), chunk fixtures, test run.
**Depends on:** M1. **Estimate:** 2–3 days.
**Risk:** line mapping bugs. Write the slice-equality test before the chunker is "done".

---

## M3 — Embeddings and idempotent ingestion

**Deliverables**

- Provider protocol + OpenAI-compatible embedder + deterministic fake.
- Resilience primitives needed for ingest (classifier, retry, `Retry-After`, deadline).
- `services/ingest.py`: plan/diff/embed/upsert/prune, advisory lock, per-doc transaction, report.
- `ingest_runs` persistence; CLI `python -m sourceline.ingest`.
- Integration tests: idempotency, edit, prune, partial failure, profile change, lock.
- Corpus report and first full ingest.

**Exit criteria**

- Full corpus ingested into pgvector; counts match the manifest.
- Second run: `embedded=0`, `inserted=0`, `updated=0`, counts unchanged (counting fake/real calls).
- Edit one section: only affected IDs change; line shifts update metadata without embedding.
- Delete + `--prune`: rows removed.
- A failed document leaves its old rows intact; run status `partial`.
- Profile mismatch blocks readiness.
- Ingestion of 38 docs ≤ 3 min (real provider, excluding first model warm-up).

**Evidence:** ingest report, SQL counts, idempotency test output, cost/token numbers.
**Depends on:** M2. **Estimate:** 3–4 days.
**Risk:** the diff is subtler than it looks. Test metadata-only updates separately from text
changes. Do not proceed to M4 until the zero-call test passes against a real provider too (once,
manually).

---

## M4 — Retrieval

**Deliverables**

- `persistence/repositories.py`: candidate query, filters, citation resolution.
- HNSW index; `ef_search` handling; profile guard; deterministic tie-break.
- Query embedding path (no generation yet) + `QueryService` retrieval stage.
- Integration tests: filters, plan shape, profile, tie-break, recall fixture.
- A retrieval-only CLI or temporary endpoint for evaluation (not shipped) or a test harness.

**Exit criteria**

- Filters restrict results in SQL; no post-truncation underfill on the fixture.
- Unfiltered query uses the HNSW index (`EXPLAIN` assertion).
- Retrieval recall@10 measured on the dev set (baseline; target is M8).
- A known question returns its gold document in the top 10.
- Wrong-profile query fails closed.

**Evidence:** recall baseline, `EXPLAIN` output, filter tests.
**Depends on:** M3. **Estimate:** 2–3 days.
**Risk:** tuning `ef_search`/score floors before the eval exists. Record a baseline; do not guess.

---

## M5 — Prompt, generation, citations, abstention

**Deliverables**

- `domain/prompt.py`: static skeleton, slots, sanitisation, budget, ordering, markers.
- `domain/citations.py`: marker parsing, sentence coverage, truth table.
- `domain/abstention.py`: pre/post policy, reasons, closest sources.
- Chat provider + structured output + one repair.
- `QueryService` full path; fake chat for deterministic tests.
- Unit tests: prompt/injection/budget/dedupe/order/citations/abstention.
- First real cited answers; contract-level response shape.

**Exit criteria**

- Answered response has contiguous markers, valid citations, `grounded=true`, no unknown fields.
- Unanswerable (no evidence above floor) returns 200 abstained with no chat call.
- Invalid JSON/citation triggers exactly one repair, then abstention.
- Prompt injection fixture cannot add an allowed marker; output is escaped.
- Citation lines match the assembled chunk and the source slice.
- Budget sum never exceeds 6,000 tokens; debug reports components.

**Evidence:** sample answers with citations, unit test run, a deliberately unanswerable response.
**Depends on:** M4. **Estimate:** 3–4 days.
**Risk:** over-tuning the prompt before the eval. Build the validator and abstention truth table
first; then iterate with the dev set.

---

## M6 — API surface and demo UI

**Deliverables**

- Routers: query, documents, citations, stats, health/ready, admin (reindex/runs/query log).
- Error envelope, request ID, auth, rate limits, body limits, CORS config.
- Static UI: question box, answer, citation cards with source excerpt, unanswerable example,
  diagnostics panel (token-gated).
- OpenAPI runtime matches `docs/openapi.yaml`.
- Contract tests for every endpoint/error.
- `GET /v1/admin/queries/{id}` for diagnosis.

**Exit criteria**

- Contract tests pass; every error code has a test; `X-Request-ID` present.
- UI works from `http://127.0.0.1:8000/` with keyboard submit and readable citations.
- Citation click shows the exact source lines; pruned citation shows a "source changed" state.
- Admin reindex requires token + idempotency key; concurrent run 409.
- No prompt/secrets in debug; public debug disabled in hosted config.

**Evidence:** screenshots/GIF draft, contract test run, curl transcripts.
**Depends on:** M5. **Estimate:** 2–3 days.
**Risk:** UI scope creep. It is a thin proof of the API, not a design project. No build step, no
framework, no auth UI beyond a token field for diagnostics.

---

## M7 — Resilience and failure drills

**Deliverables**

- Full classifier table, retry wrapper with full jitter and `Retry-After` (seconds/date/cap).
- Deadlines propagated through all stages; breaker per dependency.
- SDK retry disabling + startup assertion.
- Degraded modes: extractive answer, lexical fallback; labels in response.
- Idempotent admin reindex; advisory lock; interrupted-run handling.
- Chaos test matrix; runbook; alerts/metrics.
- Manual failure drills recorded.

**Exit criteria**

- The entire chaos matrix passes with no real sleeps (fake clock).
- LLM down → 200 extractive labelled, citations valid; no 500.
- Embedding down → lexical labelled or 503; no silent empty answer.
- DB down → 503 + readiness fail; no fabricated answer.
- 429 with `Retry-After` honoured and capped; deadline not exceeded.
- Attempt counts prove SDK retries are off.
- A drill transcript exists for chat-down, DB-down, and 429.

**Evidence:** chaos test run, drill transcripts, breaker metrics screenshot.
**Depends on:** M6. **Estimate:** 3–4 days.
**Risk:** fallbacks become a second answer path with no validation. Reuse the same citation validator
and label every fallback.

---

## M8 — Evaluation and release gates

**Deliverables**

- 80+ golden cases (30/15/15/20), dev/test split, schema-valid JSONL.
- Eval runner (in-process fake, HTTP real, replay), metrics, attribution, report template.
- Judge prompt + calibration on 30 human labels (or documented as uncalibrated).
- Baselines/ablations (chunk size, top_k, ordering, floor, dedupe).
- CI smoke gate with fake providers; release report.
- Score-floor calibration on dev only.

**Exit criteria**

- Full report with commit/profile/dataset hash and per-category metrics.
- Targets met or misses documented with attribution and a decision:
  citation validity 100%, groundedness ≥ 0.95, recall@10 ≥ 0.90, false-answer ≤ 5%,
  over-abstention ≤ 5%, p95 ≤ 6 s, cost ≤ $0.01.
- Every failed case has an attribution; no "unknown" pile.
- CI smoke blocks citation/false-answer regressions offline.
- README metrics match the report exactly.

**Evidence:** `evals/reports/<date>-<commit>/summary.md`, `results.json`, CI run.
**Depends on:** M7 (stable contract), M5 (answer path). **Estimate:** 4–5 days.
**Risk:** dataset bias and judge drift. Write realistic questions, keep a test split, calibrate the
judge, and sample human review. Do not tune on test.

---

## M9 — Portfolio polish and reviewer experience

**Deliverables**

- Final README: pitch, 20s GIF, architecture image, quickstart, example queries, measured metrics,
  failure-mode demo, limitations, next steps, licence/privacy note.
- Hosted demo (optional but recommended) with rate limit + daily cap; or a recorded fallback.
- Fresh-machine run on a clean environment; fix every undocumented step.
- Demo script rehearsal; 3-minute video.
- Final security/privacy pass; dependency audit; secret scan.
- Tag/release; commit history clean; docs links valid.

**Exit criteria**

- A hiring manager can run it from the README in ≤ 10 minutes with one documented key.
- The demo shows: cited answer, source click, unanswerable refusal, debug diagnostics, re-ingest
  zero calls, one failure drill.
- README metrics are real and dated; limitations are explicit.
- No secrets, caches, or generated junk committed.
- The repository tells one coherent story: curriculum → corpus → pipeline → evidence → evaluation.

**Evidence:** fresh-machine transcript, GIF/video, hosted URL (if any), final eval report.
**Depends on:** M8. **Estimate:** 2–3 days.
**Risk:** polishing the README while the quickstart is broken. Do the fresh-machine run first; the
README is the last thing you edit, not the first.

---

## Cross-cutting definition of done

A milestone is done when:

1. The exit criterion is demonstrated, not asserted.
2. Tests cover the new failure modes (not just the happy path).
3. Docs are updated in the same commit set (schema, API, runbook).
4. No secrets, no debug leftovers, no dead code.
5. The change is committed with a message that explains the why, not just "add stuff".
6. The reviewer path still works end to end.

## What not to do

- Do not build the UI before the citation contract is stable.
- Do not tune thresholds before the eval split exists.
- Do not add hybrid search/reranking to rescue a flawed chunker; fix the foundation first.
- Do not claim "production-grade" without failure drills and an eval report.
- Do not skip the fresh-machine run because "it works on my machine".
- Do not let the corpus grow without re-checking the manifest, eval labels, and README counts.

## Suggested commit rhythm

| Milestone | Commit theme |
|---|---|
| M1 | `Add project skeleton, config, and database migrations` |
| M2 | `Add corpus discovery and structural Markdown chunking` |
| M3 | `Add idempotent embedding ingestion` |
| M4 | `Add pgvector retrieval with filters` |
| M5 | `Add grounded answer assembly with citations and abstention` |
| M6 | `Add query API and demo UI` |
| M7 | `Add retries, circuit breakers, and degraded modes` |
| M8 | `Add golden evaluation harness and report` |
| M9 | `Polish README, demo, and deployment` |

No push unless explicitly requested; keep the working tree clean between milestones.

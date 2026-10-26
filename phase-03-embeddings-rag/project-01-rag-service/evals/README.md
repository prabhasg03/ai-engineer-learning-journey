# Evaluation Notes — Sourceline

This folder holds the versioned golden set, its schema, and generated reports. The methodology is in
[`../docs/evaluation.md`](../docs/evaluation.md); this file is the practical contract.

---

## 1. Files

| Path | Committed? | Purpose |
|---|---|---|
| `dataset.schema.json` | yes | JSON Schema for one JSONL case |
| `datasets/smoke.jsonl` | yes | 12–15 fast CI cases (subset of golden) |
| `datasets/golden.jsonl` | yes | ≥ 80 labelled cases |
| `datasets/CHANGELOG.md` | yes | Additions/label changes with dates |
| `reports/<date>-<commit>/summary.md` | yes | Human-readable release report |
| `reports/<date>-<commit>/results.json` | yes (small) | Machine metrics/cases |
| `reports/.../raw/` | no | Large provider transcripts, if any |

Never commit API keys, raw prompts, provider bodies, or personal data in a report.

---

## 2. Composition

| Category | Cases | Answerable | Notes |
|---|---:|---|---|
| Factual | 30 | yes | one note/section |
| Comparison / synthesis | 15 | yes | two notes or two sections |
| Procedural / how-to | 15 | yes | commands, steps, code |
| Unanswerable | 20 | no | absent, false premise, future/private |
| **Total** | **80** | | dev/test split |

Smoke: 8 answerable + 4 unanswerable + 2 comparison, all drawn from the golden set. Do not create an
easier parallel set for CI; the gate must be meaningful.

---

## 3. Writing rules

- Start from a realistic question, then find the evidence. Do not generate a question from a heading.
- Paraphrase; include typos, acronyms, and indirect phrasing.
- Include exact-term cases (`ef_search`, `Retry-After`, `HNSW`) to expose dense-only weaknesses.
- Include boundary cases where a definition and caveat are in adjacent chunks.
- Unanswerable must be genuinely unanswerable: absent topic, false premise, current/latest info,
  private data, or a question the corpus does not address.
- `required_facts` are atomic and human-checkable; no vague "explains X".
- `forbidden_claims` catch common hallucinations.
- `gold_doc_ids` are durable; `gold_chunk_ids` optional (stale after re-chunk).
- No leakage: required facts/reference answers never enter prompts.
- No duplicate IDs; no test/dev leakage; no tuning on test.

Example (one JSONL line, formatted here for readability):

```json
{
  "id": "q-025-hnsw-recall",
  "question": "How does HNSW trade recall for speed?",
  "category": "factual",
  "answerable": true,
  "gold_doc_ids": ["phase-03-embeddings-rag/topic-25-pgvector/notes.md"],
  "gold_chunk_ids": [],
  "required_facts": [
    "HNSW searches a layered proximity graph",
    "ef_search controls the query-time candidate list",
    "higher ef_search improves recall at higher latency"
  ],
  "forbidden_claims": [
    "HNSW guarantees exact nearest neighbours",
    "ef_search changes the index structure"
  ],
  "reference_answer": "HNSW searches a multi-layer graph ...",
  "filters": {"phase": 3, "topic": 25},
  "difficulty": "medium",
  "split": "dev",
  "notes": "Definition and tuning advice are in adjacent sections."
}
```

---

## 4. Running

```bash
# Offline smoke (fake providers; CI)
python -m sourceline.eval --dataset evals/datasets/smoke.jsonl --split dev --mode in-process

# Full dev evaluation (real providers)
python -m sourceline.eval --dataset evals/datasets/golden.jsonl --split dev --mode http \
  --base-url http://127.0.0.1:8000 \
  --out evals/reports/$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)

# Release/test split
python -m sourceline.eval --dataset evals/datasets/golden.jsonl --split test --mode http \
  --judge calibrated --out evals/reports/<...>
```

Windows PowerShell uses `Get-Date -Format yyyy-MM-dd` and `git rev-parse --short HEAD` in variables.

The runner must use the same query path as production. `in-process` swaps providers, not retrieval or
assembly logic.

---

## 5. Report and gates

Each report includes:

- run metadata: dataset hash, split, commit, profile, models, judge version;
- headline metrics vs targets and previous run;
- per-category table (counts + rates);
- failure attribution: retrieval/ranking/generation/citation/over-abstention/false-answer/stale/conflict;
- latency and cost;
- human/judge calibration;
- decision (ship/hold/rollback) and limitations.

Release gates:

| Gate | Target |
|---|---:|
| Citation validity (answered) | 100% |
| Groundedness | ≥ 0.95 |
| Recall@10 | ≥ 0.90 |
| False-answer rate (unanswerable) | ≤ 5% |
| Over-abstention (answerable) | ≤ 5% |
| p95 latency | ≤ 6 s |
| Cost/query | ≤ $0.01 |

Report counts alongside percentages. At 80 cases, one case is 1.25 points; do not overclaim precision.

---

## 6. Attribution

For every failed case, assign one label:

| Label | Meaning |
|---|---|
| `retrieval_miss` | Gold chunk/doc absent from `retrieved` |
| `ranking_miss` | Gold retrieved, absent from `prompted` |
| `generation_miss` | Gold prompted, answer incomplete/unsupported |
| `citation_miss` | Cited chunk does not support the claim |
| `over_abstention` | Answerable but refused |
| `false_answer` | Unanswerable but answered |
| `stale_index` | Corpus newer than index |
| `corpus_conflict` | Sources disagree |
| `dataset_issue` | Ambiguous/incorrect label |

No "unknown" pile. If it cannot be attributed, add a probe.

---

## 7. Maintenance

- Add every production/user-reported failure as a case before fixing it.
- Re-validate gold docs after a corpus change; mark stale cases and fix.
- Keep `CHANGELOG.md` entries: added cases, label changes, split changes, threshold changes.
- Do not delete a failing case to make the report green.
- Do not tune the score floor or prompt on the test split.
- Recalibrate the judge when the model/prompt changes; record agreement.
- Grow toward 150+ cases only if the categories remain balanced; quantity is not quality.

---

## 8. Privacy

Questions and answers may contain user text. Reports should quote only what is necessary for
diagnosis, prefer excerpts from the public corpus, and never include secrets, personal data, or raw
provider responses. The dataset itself must contain no private information.

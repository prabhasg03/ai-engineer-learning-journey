# Evaluation Plan — Sourceline

**Purpose:** prove that retrieval finds the right evidence, answers stay grounded in it, refusals are
honest, and changes do not regress. A RAG demo without an eval is a prompt with a database.

The evaluation harness is part of the product: `python -m sourceline.eval` loads versioned JSONL
cases, runs the same query path as the API, scores each stage, attributes failures, and writes a
report with the commit and profile.

---

## 1. What "good" means

| Dimension | Question | Primary metric |
|---|---|---|
| Retrieval | Did the retriever find the gold evidence? | Recall@k, MRR |
| Ranking/assembly | Did the evidence survive into the prompt? | Prompt-inclusion rate, context precision |
| Generation | Is the answer correct and supported? | Groundedness, answer correctness |
| Citations | Does every claim point to a real source? | Citation validity, sentence coverage |
| Refusal | Does it refuse when the corpus cannot answer? | False-answer rate, abstention recall/precision |
| Operations | Is it fast and affordable? | p50/p95 latency, cost/query |
| Diagnosis | Can a failure be attributed? | Attribution coverage |

The release gates are in §8. Targets are commitments; measured numbers go in the README only after
the harness produces them.

---

## 2. Dataset

### 2.1 Size and composition

| Category | Cases | What it tests |
|---|---:|---|
| Factual lookup | 30 | one note, one concept, direct answer |
| Comparison / synthesis | 15 | two notes or two sections; requires selecting both |
| Procedural / how-to | 15 | steps, commands, code, ordering |
| Unanswerable | 20 | absent from corpus, false premise, future/private info |
| **Total** | **80** | |

Plus a **smoke subset** of 12–15 cases (8 answerable, 4 unanswerable, 2 comparison) used in CI. Smoke
cases are a subset of the golden set, not a separate easier set; the gate must be meaningful.

The corpus is 38 notes, so 80 cases is roughly two questions per document. Avoid 80 questions about
one favourite topic; the distribution follows the corpus's topic weights.

### 2.2 Case schema

JSONL, one object per line (schema: [`evals/dataset.schema.json`](../evals/dataset.schema.json)):

```json
{
  "id": "q-025-hnsw-recall",
  "question": "How does HNSW trade recall for speed?",
  "category": "factual",
  "answerable": true,
  "gold_doc_ids": ["phase-03-embeddings-rag/topic-25-pgvector/notes.md"],
  "gold_chunk_ids": [],
  "required_facts": [
    "HNSW searches a layered graph",
    "ef_search controls the query-time candidate list",
    "higher ef_search improves recall at higher latency"
  ],
  "forbidden_claims": [
    "HNSW guarantees exact nearest neighbours",
    "ef_search changes the index structure"
  ],
  "reference_answer": "HNSW searches a multi-layer proximity graph ...",
  "filters": {"phase": 3, "topic": 25},
  "difficulty": "medium",
  "notes": "Boundary-sensitive: the definition and tuning advice are in adjacent sections."
}
```

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Stable; never reuse for a different question |
| `question` | yes | Realistic user phrasing, not a heading |
| `category` | yes | `factual`, `comparison`, `procedural`, `unanswerable` |
| `answerable` | yes | Ground truth for refusal metrics |
| `gold_doc_ids` | yes (answerable) | At least one; used for document recall |
| `gold_chunk_ids` | no | Exact chunks if known; used for chunk recall when present |
| `required_facts` | answerable | Atomic facts the answer must contain; human-checkable |
| `forbidden_claims` | no | Claims that make the answer wrong |
| `reference_answer` | no | For human/judge comparison; not returned to the system |
| `filters` | no | If the question implies a scope; otherwise `{}` |
| `difficulty` | no | `easy`, `medium`, `hard` for reporting |
| `notes` | no | Why the case exists, known ambiguity |

`gold_chunk_ids` are optional because chunk IDs change when text changes; `gold_doc_ids` +
`required_facts` are the durable ground truth. When chunk IDs are present, the harness warns if they
no longer exist after a re-chunk rather than silently scoring zero.

### 2.3 How cases are written

- **From questions, not answers.** Start with a real question a reader would ask; then find the
  evidence. Do not generate a question from a chunk and call it realistic.
- **Paraphrase.** Avoid copying the heading; include typos, acronyms, and indirect phrasing.
- **Include exact-term cases.** `ef_search`, `Retry-After`, `HNSW`, `pgvector`, `RRF` — these expose
  dense-only weaknesses.
- **Include boundary cases.** A definition at the end of one chunk and its caveat at the start of the
  next.
- **Include unanswerable variants.** Absent topic, false premise, "latest version" (the corpus is a
  snapshot), personal/private info, and a question whose answer requires the open web.
- **No leakage.** `required_facts` and `reference_answer` never enter the prompt or retrieval.
- **Version the set.** Changing a case is a dataset change; record it in the report diff.

Unanswerable examples:

| Question | Why unanswerable |
|---|---|
| "What is the current price of GPT-4.1-mini?" | Pricing changes; not in the corpus |
| "How do I configure Kubernetes ingress?" | Topic absent |
| "What did the author decide in the 2024 meeting?" | Private/absent |
| "Why does pgvector use a B-tree for vectors?" | False premise (it does not) |
| "What is the warranty on the course?" | Not a product |

A good refusal is specific: "The corpus does not cover Kubernetes ingress" is better than a generic
"I don't know", but v1's fixed abstention string is acceptable if the reason field is correct. The UI
can show `closest_sources` to help the user rephrase.

### 2.4 Dev/test split

- 50 dev cases: threshold calibration, prompt iteration, chunk-size experiments.
- 30 test cases: touched only for final/release evaluation; no tuning against individual failures.
- The split is recorded in the dataset (`split` field) and the report. If a test case fails, you may
  diagnose it, but a fix must be justified by the dev set or a general principle, not by memorising
  the test answer.

At 80 cases, a single case is 1.25 percentage points. Report counts as well as rates; do not claim
"95% groundedness" on 20 cases without a confidence interval.

---

## 3. Metrics

### 3.1 Retrieval

For each answerable case with `gold_doc_ids`:

- **Doc recall@k** = 1 if any gold document appears in the top-k retrieved chunks, else 0.
- **Chunk recall@k** = 1 if any `gold_chunk_id` appears, when chunk IDs are supplied.
- **MRR** = 1 / rank of the first relevant chunk (document match), averaged.
- **nDCG@k** if graded relevance is added later; not required in v1.

Report `k = 10` (the retrieval candidate pool is 40, but recall@10 is the human-scale target) and
also recall@40 (the candidate ceiling). A gold chunk outside the candidate set can never be prompted;
that is a retrieval miss, not a ranking miss.

### 3.2 Context / assembly

- **Prompt inclusion** = gold doc/chunk present in `prompted`, given it was retrieved.
- **Context precision** = relevant prompted chunks / all prompted chunks (document-level; noisy, so
  report with the drop reasons).
- **Evidence recall** = required facts whose supporting chunk was prompted (manual or judge-assisted).
- **Budget utilization** = evidence tokens / evidence budget.

Prompt inclusion is the key ranking metric. If recall@40 is high but inclusion is low, the problem is
dedupe, budget, score floor, or ordering — not the embedding model.

### 3.3 Answer

- **Citation validity** (deterministic) = answered responses with every marker in `1..n` and no
  missing marker / answered responses. Gate: 100%.
- **Sentence coverage** = factual sentences with a valid marker / factual sentences. Gate: 100%
  for a response to be `grounded=true`.
- **Groundedness** (semantic) = claims supported by the cited evidence / claims. Scored by a
  calibrated judge and a human sample. Gate: ≥ 0.95.
- **Answer correctness** = 1 if all `required_facts` are present and no `forbidden_claims` appear;
  0 otherwise. Report per category and overall. This is stricter than groundedness: an answer can be
  grounded but incomplete.
- **Factual precision** = required facts present / required facts (partial credit), useful for
  diagnosis but not the gate.

### 3.4 Refusal

| Metric | Formula | Target |
|---|---|---:|
| False-answer rate | unanswerable cases with `abstained=false` / unanswerable cases | ≤ 5% |
| Abstention recall | unanswerable cases correctly abstained / unanswerable cases | ≥ 95% |
| Abstention precision | correctly abstained / all abstentions | report; low means over-abstention |
| Over-abstention rate | answerable cases abstained / answerable cases | ≤ 5% |
| Reason accuracy | abstention reason matches the expected class / abstentions | report |

False answers and over-abstention are both failures. A service that refuses everything has perfect
false-answer rate and is useless. Report both.

### 3.5 Operations

- **Latency**: p50/p95/p99 total and per stage (embed, retrieve, assemble, generate, validate). The
  harness records real provider timings; CI uses fakes and does not gate latency.
- **Cost**: tokens and estimated USD per query; p50/p95; total for the run.
- **Repair rate**: schema/citation repairs / generated answers. A rising rate signals prompt/model
  drift.
- **Degraded rate**: extractive/lexical responses / queries. Nonzero only during fault injection or
  a real outage.
- **Error rate**: non-2xx responses by code.

### 3.6 Diagnosis attribution

For every failed case, classify:

| Label | Evidence |
|---|---|
| `retrieval_miss` | No gold doc/chunk in `retrieved` |
| `ranking_miss` | Gold in `retrieved`, absent from `prompted` (dedupe/budget/floor) |
| `generation_miss` | Gold in `prompted`, answer missing facts or unsupported |
| `citation_miss` | Answer cites a different chunk than the supporting one |
| `over_abstention` | Answerable, but `abstained=true` |
| `false_answer` | Unanswerable, but `abstained=false` |
| `stale_index` | Gold exists in a newer source than the index |
| `corpus_conflict` | Two sources disagree; no single correct answer |
| `dataset_issue` | Ambiguous/incorrect gold label |

The report includes counts by label. A release cannot claim an improvement if it merely shifts
failures between categories without measuring both.

---

## 4. Scoring methods

### 4.1 Deterministic checks (always run)

- schema validation of every response;
- citation validity and sentence coverage;
- required-fact string/normalised matching (exact or alias list) for a first-pass correctness;
- forbidden-claim detection (substring/regex with human review for false positives);
- retrieval recall/MRR from gold IDs;
- latency/token/cost accounting.

These are cheap, reproducible, and run in CI with fake providers.

### 4.2 LLM judge (semantic groundedness)

A judge receives the question, the answer, and the **cited evidence only**, and returns per-claim
labels: `supported`, `partially_supported`, `unsupported`, `not_a_claim`. It does not see
`reference_answer` (to avoid answer-matching bias) and does not see the system prompt.

- Judge model is pinned and different from the answer model where practical.
- Temperature 0; JSON output; deterministic rubric.
- Calibrate against 30 human-labelled answers: agreement ≥ 0.80 (Cohen's κ reported). If calibration
  fails, fix the rubric, not the threshold.
- Judge version and prompt hash are recorded in the report.
- Judge results are advisory for release, but a **human review** of a 20% sample plus every
  disagreement is required before claiming groundedness.
- Do not use the judge to score retrieval; it cannot see what was not retrieved.

### 4.3 Human review

- 20% random sample of answered cases + all failures + all unanswerable false answers.
- Rubric: factual correctness, completeness, citation support, refusal quality, clarity.
- Two reviewers for the calibration set; adjudicate disagreements.
- Record reviewer initials/date in the report (no personal data beyond that).
- The human review is the ground truth for the README's quality claim; the judge is a scalable proxy.

---

## 5. Harness design

```text
python -m sourceline.eval \
  --dataset evals/datasets/golden.jsonl \
  --split test \
  --mode http \                 # or in-process
  --base-url http://127.0.0.1:8000 \
  --out evals/reports/2026-10-26-a01637a/
```

Modes:

| Mode | Providers | Use |
|---|---|---|
| `in-process` | fake embedding/chat | CI smoke, deterministic unit-level checks |
| `http` | configured real providers | Full/nightly evaluation |
| `replay` | recorded provider responses | Debug a past run without spending money |

The runner uses the **same** `QueryService`/HTTP contract as production. It must not import private
scoring shortcuts that change retrieval. It records:

```json
{
  "run": {
    "dataset": "golden.jsonl",
    "dataset_sha256": "...",
    "split": "test",
    "commit": "a01637a",
    "profile_key": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
    "models": {"embedding": "...", "chat": "...", "judge": "..."},
    "started_at": "...",
    "mode": "http"
  },
  "metrics": {"overall": {}, "by_category": {}},
  "cases": [
    {
      "id": "q-025-hnsw-recall",
      "retrieved": ["c_..."],
      "prompted": ["c_..."],
      "cited": ["c_..."],
      "abstained": false,
      "grounded": true,
      "correct": true,
      "attribution": null,
      "latency_ms": 2012,
      "cost_usd": 0.0018
    }
  ],
  "failures": [{"id": "...", "attribution": "ranking_miss", "detail": "..."}],
  "artifacts": {"report_md": "summary.md", "raw": "results.json"}
}
```

Reports are written to `evals/reports/<date>-<commit>/summary.md` and `results.json`. Commit the
summary and the small JSON; ignore large raw provider transcripts (they may contain text).

### 5.1 Report template

Use [`docs/templates/eval-report-template.md`](templates/eval-report-template.md). It includes:

- run metadata (commit, profile, models, dataset hash, split);
- headline metrics vs targets and vs the previous run;
- per-category table;
- failure attribution counts with one-line examples;
- calibration/agreement;
- cost and latency;
- decision: ship / hold / rollback, with reasons;
- known limitations.

No report, no release. "It looked good in the UI" is not evidence.

---

## 6. Baselines and ablations

Run these on the dev split before tuning the test split:

| Experiment | Values | Question |
|---|---|---|
| Chunk size | 800 / 1,200 / 1,600 chars | Recall vs context precision |
| Overlap | 0 / 150 / 300 chars | Boundary questions |
| `top_k` | 4 / 8 / 12 | Answer completeness vs cost |
| `candidate_k` | 20 / 40 / 80 | Recall ceiling |
| Ordering | descending / sandwich | Lost-in-the-middle |
| Dedupe | off / exact / exact+near | Context waste vs lost evidence |
| Score floor | 0.10 / 0.15 / 0.20 / 0.25 | False answers vs over-abstention |
| Breadcrumb in embedding | on / off | Section context |
| Repair | on / off | Invalid output recovery vs cost |

Record the winner and the effect size. A change that improves one metric while quietly worsening
false answers or cost is not a win. If sandwich ordering does not help on this corpus, say so in the
README; a negative result is engineering evidence.

---

## 7. CI integration

### 7.1 Pull request gate (offline)

- `ruff`, `mypy`, unit + contract + integration tests (Postgres service container).
- Eval smoke (12–15 cases) with **fake providers** and the fixture corpus:
  - response schema valid;
  - citation validity 100%;
  - no false answers on the 4 unanswerable smoke cases;
  - retrieval recall@10 on the smoke set ≥ 0.85 (small-N gate, reported as a count).
- No network, no real keys, deterministic.

The fake provider is scripted per case; it does not "know" the answer. The smoke gate checks the
pipeline and contract, not model quality.

### 7.2 Release gate (real providers)

- Full golden set, test split.
- Targets: recall@10 ≥ 0.90, groundedness ≥ 0.95, citation validity 100%, false-answer ≤ 5%,
  over-abstention ≤ 5%, p95 ≤ 6 s, cost/query ≤ $0.01.
- Human review of failures/20% sample.
- Report committed with the release tag.
- If a target misses, the release is held or the README reports the miss honestly; do not move the
  goalposts after seeing the result.

### 7.3 Regression policy

- A case that regresses from pass to fail blocks the release unless the report explains why the new
  behaviour is correct and the dataset label is updated (with a note).
- Track per-case history; a flapping case (pass/fail across runs) is a reliability bug (model
  nondeterminism, threshold too close, ambiguous label), not a rounding error.
- Adding cases: every production failure or user-reported miss becomes a case before the fix. This is
  the feedback loop.

---

## 8. Targets and decision rules

| Gate | Target | If missed |
|---|---:|---|
| Citation validity | 100% | Block release; fix validator/prompt |
| Groundedness | ≥ 0.95 | Hold; inspect generation misses; consider model/prompt |
| Recall@10 | ≥ 0.90 | Hold; fix retrieval/chunking/filters; consider hybrid |
| False-answer rate | ≤ 5% | Block; raise floor/strengthen abstention |
| Over-abstention | ≤ 5% | Hold; lower floor/improve recall; do not trade safety blindly |
| p95 latency | ≤ 6 s | Hold for hosted demo; optimize or document |
| Cost/query | ≤ $0.01 | Optimize budget/model or cap |
| Smoke (offline) | all pass | Block merge |

At 80 cases, 5% is 4 cases. Report counts; do not overstate precision. If the confidence interval is
wide, say so in the report.

---

## 9. Dataset maintenance

- Store JSONL in git; one case per line; stable IDs; no secrets or personal data.
- Validate every change with the schema and a duplicate-ID check.
- When the corpus changes (new topic, edited note), re-check gold doc IDs and required facts. A case
  whose gold disappeared is marked `stale` and fixed before the next release.
- Keep an `evals/datasets/CHANGELOG.md` (or a `version`/`notes` field) describing additions and label
  changes.
- Do not tune on the test split. Do not delete a failing case to make the report green.
- Unanswerable cases must remain genuinely unanswerable; if a new note answers one, move it to the
  answerable set with a new gold label (and note the change).

---

## 10. Anti-patterns

- A single "accuracy" number with no retrieval/citation breakdown.
- An LLM judge as the only metric, uncalibrated, with no human sample.
- Evaluating only questions whose answers are headings (easy mode).
- Tuning the score floor on the test set until the numbers look good.
- Reporting a percentage on 10 cases without counts.
- Ignoring over-abstention because "refusing is safe".
- Committing a report without the commit/profile/dataset hash.
- Treating a demo transcript as an evaluation.
- Adding a feature and not adding a case for its failure mode.

---

## 11. Definition of done for evaluation

- [ ] ≥ 80 golden cases with the category mix above and a dev/test split.
- [ ] Schema-valid dataset, no duplicate IDs, gold docs verified against the corpus.
- [ ] Runner works in `in-process` (fake) and `http` (real) modes.
- [ ] Report includes metadata, metrics, attribution, latency, cost, and a decision.
- [ ] Judge calibrated or explicitly marked uncalibrated; human sample reviewed.
- [ ] CI smoke gate runs offline and blocks on citation/false-answer regressions.
- [ ] Release report committed with measured numbers (or a documented miss).
- [ ] Threshold calibration recorded, not guessed.
- [ ] Every known failure has an attribution and an owner/next action.

# Evaluation Report — <YYYY-MM-DD> — <commit>

| Field | Value |
|---|---|
| Dataset | `evals/datasets/golden.jsonl` |
| Dataset SHA-256 | `<hash>` |
| Split | `dev` / `test` |
| Commit | `<sha>` |
| Profile | `markdown-h2-v1|1200|150|<model>|<dims>` |
| Embedding model | `<model>` |
| Chat model | `<model>` |
| Judge model / rubric | `<model>` / `<hash>` |
| Mode | `in-process` / `http` / `replay` |
| Started / finished | `<timestamps>` |
| Reviewer | `<initials>` |

---

## 1. Decision

**Ship / Hold / Rollback**

Reason (2–4 sentences). Link the blocking cases and the follow-up owner.

---

## 2. Headline metrics

| Metric | Target | This run | Previous | Δ | Pass? |
|---|---:|---:|---:|---:|---|
| Citation validity (answered) | 100% | `<n/N = %>` | `<...>` | `<...>` | |
| Groundedness | ≥ 0.95 | `<...>` | `<...>` | | |
| Recall@10 (any gold) | ≥ 0.90 | `<n/N = %>` | `<...>` | | |
| MRR | report | `<...>` | `<...>` | | |
| Answer correctness | report | `<...>` | `<...>` | | |
| False-answer rate | ≤ 5% | `<n/N = %>` | `<...>` | | |
| Over-abstention | ≤ 5% | `<n/N = %>` | `<...>` | | |
| p50 latency | report | `<ms>` | `<...>` | | |
| p95 latency | ≤ 6 s | `<ms>` | `<...>` | | |
| Cost / query | ≤ $0.01 | `<$>` | `<...>` | | |

Report **counts and rates**. At 80 cases, one case is 1.25 percentage points.

---

## 3. Per category

| Category | N | Recall@10 | Grounded | Correct | Abstained | False answers |
|---|---:|---:|---:|---:|---:|---:|
| Factual | 30 | | | | | |
| Comparison | 15 | | | | | |
| Procedural | 15 | | | | | |
| Unanswerable | 20 | n/a | n/a | n/a | | |

---

## 4. Failure attribution

| Label | Count | Example case | Suspected cause | Next action |
|---|---:|---|---|---|
| `retrieval_miss` | | | | |
| `ranking_miss` | | | | |
| `generation_miss` | | | | |
| `citation_miss` | | | | |
| `over_abstention` | | | | |
| `false_answer` | | | | |
| `stale_index` | | | | |
| `corpus_conflict` | | | | |
| `dataset_issue` | | | | |

Every failure has a label and an action. No unknown bucket.

---

## 5. Ablations / baselines

| Experiment | Value | Recall@10 | Grounded | False answers | Cost | Notes |
|---|---|---:|---:|---:|---:|---|
| Chunk size | 800 / 1200 / 1600 | | | | | |
| Overlap | 0 / 150 / 300 | | | | | |
| `top_k` | 4 / 8 / 12 | | | | | |
| Ordering | descending / sandwich | | | | | |
| Dedupe | off / exact / +near | | | | | |
| Score floor | 0.10–0.25 | | | | | |
| Repair | on / off | | | | | |

State the winner and the effect size. A negative result is valid.

---

## 6. Judge calibration / human review

| Item | Value |
|---|---|
| Human-labelled sample | `<n>` |
| Judge–human agreement | `<%>` |
| Cohen's κ | `<value>` |
| Disagreements reviewed | `<n>` |
| Rubric changes | `<yes/no + note>` |
| Human sample of answered cases | `<%>` |
| All failures reviewed? | yes/no |

---

## 7. Latency and cost

| Stage | p50 | p95 | Notes |
|---|---:|---:|---|
| Embed | | | |
| Retrieve | | | |
| Assemble | | | |
| Generate | | | |
| Validate | | | |
| **Total** | | | |

Tokens: prompt p50/p95 `<...>`; completion p50/p95 `<...>`.
Cost: total `<...>`; median `<...>`; max `<...>`.
Degraded/repair counts: `<...>`.

---

## 8. Known limitations / observations

- `<e.g. dense-only misses exact identifiers; 3 cases attributed to retrieval_miss>`
- `<e.g. over-abstention concentrated in comparison questions>`
- `<e.g. judge disagreement on partial support>`

Do not hide a miss; state it and the plan.

---

## 9. Artifacts

- `results.json` — machine-readable cases/metrics
- `summary.md` — this file
- `<raw logs, if not committed>`
- Query IDs / request IDs for failing cases: `<...>`

# Risk Register — Sourceline

Scoring: likelihood (L) and impact (I) are **1–5**; score = L × I. A score ≥ 15 needs a mitigation
before the milestone that exposes it; ≥ 20 needs an explicit go/no-go decision. Re-score at each
milestone. This is a portfolio project, so schedule and reviewer trust are risks alongside the
technical ones.

| ID | Risk | L | I | Score | Mitigation | Early warning | Contingency |
|---|---|---:|---:|---:|---|---|---|
| R-01 | Provider model deprecated or silently changed | 3 | 4 | 12 | Pin model IDs; record in eval report; re-run eval on change; provider abstraction | Eval regression without code change; 404 model | Switch model behind the interface; full re-embed if embedding model; document delta |
| R-02 | Embedding dimension/profile mismatch | 3 | 5 | 15 | Single active profile; readiness check; full-rebuild path; startup validation | `index_profile_mismatch`; dimension errors | Maintenance rebuild; migrate vector dimension; never mix vectors |
| R-03 | Chunk line mapping is wrong | 3 | 4 | 12 | Slice-equality tests; store exact source text; line-range invariant | Citation click shows wrong text | Re-chunk; add regression case; fix normalisation/line offset |
| R-04 | Dense-only retrieval misses exact terms | 4 | 3 | 12 | Eval exact-term cases; lexical fallback; document limitation; Phase 4 hybrid | Recall@10 low on API-name questions | Add hybrid/RRF (Phase 4) with eval; do not ship a hidden reranker |
| R-05 | Hallucinated citation or unsupported claim | 4 | 5 | 20 | Structured output; marker/sentence validation; one repair; abstain; eval judge/human | Citation-invalid counter; judge unsupported claims | Fail closed; tighten prompt; add claim checks; model change |
| R-06 | Over-abstention makes the demo look broken | 4 | 3 | 12 | Measure both abstention recall and over-abstention; calibrate floor on dev; closest sources | Answerable cases refused | Lower floor / improve recall / clarify question; do not trade false answers blindly |
| R-07 | False answers on unanswerable questions | 3 | 5 | 15 | Score floor; abstention prompt; unanswerable eval set; hosted guardrails | False-answer rate > 5% | Raise floor, strengthen prompt, add cases; hold release |
| R-08 | Score floor does not transfer to a new corpus/model | 4 | 3 | 12 | Calibrate per profile on dev; store floor in config/report; re-run eval | Sudden abstention/false-answer shift | Recalibrate; do not reuse a threshold blindly |
| R-09 | Stale index answers from old notes | 3 | 3 | 9 | `index_age_seconds`, expected commit, deploy-time ingest, alert | Commit mismatch/age alert | Re-ingest; show stale flag; block deploy if critical |
| R-10 | Cost spike from public demo/abuse | 3 | 4 | 12 | Per-IP limits, concurrency cap, daily budget, max tokens, alert at 80% | Cost alert; 429/503 spike | Revoke key, scale down, raise limit deliberately |
| R-11 | Prompt injection changes prose | 3 | 3 | 9 | Evidence escaping, no tools, output validation, injection eval case | Weird answer/instructions echoed | Add classifier/sanitisation; document residual risk |
| R-12 | Evaluation set is biased or too small | 4 | 4 | 16 | Realistic questions, category mix, dev/test split, counts not just rates, human sample | All cases pass suspiciously; failures cluster | Add cases; rebalance; report confidence limits |
| R-13 | LLM judge drifts/uncalibrated | 4 | 3 | 12 | Calibrate on 30 human labels; pin judge; report agreement; human review | Judge/human disagreement | Recalibrate or mark uncalibrated; rely on human sample |
| R-14 | Windows/Docker path issues block reviewer | 3 | 4 | 12 | Docker-first README; PowerShell + POSIX commands; fresh-machine test; compose healthchecks | Quickstart fails on a clean machine | Fix compose/mounts; provide local Python path; record video |
| R-15 | pgvector version/ANN recall surprise | 3 | 3 | 9 | Require ≥ 0.8; readiness reports version; recall vs exact test; document iterative scan | Under-filled filtered results; recall drop | Upgrade; exact search for narrow filters; tune ef_search |
| R-16 | Scope creep (agents, hybrid, streaming, UI) | 4 | 3 | 12 | Non-goals in requirements; milestone gates; ADRs; defer to Phase 4 | Milestone slipping; new feature before eval | Cut scope; ship v1; record deferral |
| R-17 | Secret/key leak | 2 | 5 | 10 | Env-only, redaction, secret scan, `.gitignore`, rotate procedure | Secret scanner alert; unexpected bill | Rotate immediately; incident note; audit logs; add test |
| R-18 | Hand-written policy violated by copied code | 2 | 4 | 8 | ADR-012; review checklist; commit history; source comments | Unexplained framework imports/style | Remove/replace; document borrowed snippets; review |
| R-19 | Corpus content is wrong/conflicting | 3 | 3 | 9 | Cite sources; eval conflict cases; surface both chunks; authority metadata future | Reviewer finds a contradiction | Correct the note; add case; decide recency/authority policy |
| R-20 | Schedule overrun (part-time build) | 4 | 3 | 12 | Milestones with exit criteria; cut P2; timebox M8; ship a smaller honest v1 | Two milestones behind | Reduce scope (no hosted demo/streaming), keep core + eval + failures |

---

## 1. Top risks (score ≥ 15)

### R-05 — Hallucinated citation / unsupported claim

This is the product risk. Mitigation is layered, not a single prompt:

1. Structured output + strict schema.
2. Markers validated against the assembled map; citations built from DB rows.
3. Every factual sentence must contain a marker; one repair; then abstain.
4. Semantic groundedness measured on the golden set with a calibrated judge + human sample.
5. The README states that validation is syntactic/heuristic, not entailment.

**Go/no-go:** if groundedness < 0.95 or citation validity < 100% after repair/abstain, the release is
held. Do not relabel the metric.

### R-06/R-07 — Refusal calibration

The service can fail in both directions. The eval report must show abstention recall, over-abstention,
and false answers together. A floor change requires both numbers. The README reports both.

### R-02 — Profile mismatch

The single biggest data-integrity risk. One vector column, one profile, readiness check, startup
validation, full-rebuild runbook. No "just re-embed some rows" shortcut.

### R-12 — Evaluation bias

80 cases is small. Mitigations: category mix, realistic phrasing, dev/test split, counts alongside
rates, human review, and adding every production failure as a case. The README says "80 cases" rather
than implying statistical certainty.

---

## 2. Risk process

- Review the register at the start of each milestone; update L/I with evidence.
- A risk with no mitigation and score ≥ 15 blocks the milestone exit until it is mitigated, accepted
  in writing, or removed by a scope decision.
- Every incident/failure gets a register row if it reveals a new risk, plus a regression test.
- Do not delete a risk because it is uncomfortable; move it to "accepted residual" with a reason.
- The risk register is not a compliance artifact; it is a decision log.

## 3. Accepted residual risks (v1)

| Risk | Why accepted | Revisit |
|---|---|---|
| Prompt injection can change prose | No tools/writes; corpus authored; output validated | If ingesting third-party/live corpora |
| Semantic entailment not proven per claim | Cost/complexity; eval + human sample instead | Phase 7 / claim-level checks |
| Single admin token, no rotation UI | Portfolio scope; TLS + non-public admin | Multi-user deployment |
| In-memory rate limits/breakers | Single process; documented | Multi-worker/10× traffic |
| No per-document ACLs | Public corpus; no accounts | Private corpus/multi-tenant |
| English-centric FTS/tokenizer | Corpus is English | Multilingual corpus |
| No streaming | JSON contract is enough for v1 | If UX demands it |
| No learned reranker | Dense baseline + eval; Phase 4 | After hybrid evaluation |

## 4. Kill criteria / stop rules

Stop and reassess if:

- The corpus cannot be ingested reproducibly (hash/count drift) after two attempts.
- Citation validity cannot reach 100% with repair/abstention.
- The service cannot distinguish an unanswerable question without refusing most answerable ones
  (false-answer and over-abstention both > 10%).
- The README quickstart cannot be made reliable on a fresh machine within the timebox.
- Cost per query cannot be bounded under the demo cap.
- The build is drifting into a framework integration rather than a hand-written pipeline.

Stopping is a valid engineering decision; shipping an unmeasured RAG demo is not.

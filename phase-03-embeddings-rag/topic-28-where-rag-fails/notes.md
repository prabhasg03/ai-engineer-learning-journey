# Topic 28 — Where RAG Fails

## 1. Purpose of This Topic

A wrong RAG answer is a **symptom**, not a diagnosis. The same visible failure — "the answer is wrong" — can come from four very different places:

1. the corpus never contained the answer (**unanswerable**),
2. the answer-bearing chunk was never retrieved (**retrieval miss**),
3. it was retrieved but did not reach the prompt (**ranking miss**),
4. it reached the prompt and the model still got it wrong (**generation miss**).

Each has a different fix and a different cost. Re-embedding the corpus when the real bug was a context-budget drop wastes days; rewriting the prompt when the real bug was a stale index changes nothing. This topic builds the diagnostic habit and the instrumentation that supports it.

The implementation is `implementation/diagnose.py`: a labelled-case harness that classifies failures by stage, detects stale indices and conflicting chunks, recognises unanswerable questions, and encodes a **failure boundary** for every pipeline stage.

**Done when:** given only symptoms, you can say whether the failure was retrieval, ranking, or generation — and name what you would change.

### Sources and what each contributes

- **Applied LLMs** — retrieval quality bounds everything downstream; hybrid/keyword search matters; long context does not replace retrieval; evaluate the pipeline, not the demo.
- **Eugene Yan — Patterns for LLM systems** — RAG as a system pattern, evaluation and guardrails as first-class components, and the habit of measuring each component rather than the end-to-end vibe.
- **Topics 26–27** — the pipeline stages and the assembly decisions that produce the observables this topic diagnoses.

---

## 2. Prerequisites

**Before: Topics 26 and 27**

- The eight stages and their contracts.
- The retrieved-vs-prompted distinction.
- Assembly reports (`dropped`, `truncated`, `citations`, `duplicates_removed`).
- Citation validation.
- Basic eval vocabulary: recall@k, precision, groundedness, abstention.

---

## 3. The Three Misses (and the Fourth Category)

### 3.1 Retrieval miss

**Definition:** a chunk that contains the answer exists in the corpus but is absent from the retrieved set.

Typical causes:

- chunking split the answer across boundaries, or buried it in boilerplate;
- the embedding model does not represent the query's vocabulary (exact names, IDs, morphology, rare terms);
- ANN under-recall (`ef_search`/`probes` too low) or a filter removed the row;
- the index is stale, so the document was never indexed;
- the query was rewritten into something else.

**Observable:** `gold ∉ retrieved`. The fix lives in ingest/chunk/embed/store/query/retrieve.

### 3.2 Ranking miss

**Definition:** the answer-bearing chunk is in the retrieved set but does not reach the final prompt.

This is the stage people forget to instrument. Causes:

- the top-k cutoff for the prompt is smaller than the retrieval set;
- a reranker scores the gold chunk below the cutoff;
- near-duplicate chunks crowd it out;
- the context budget drops or truncates it;
- the question/context assembly orders it where the model ignores it.

**Observable:** `gold ∈ retrieved` and `gold ∉ prompted`. The fix lives in reranking and assembly, not in the embedding model.

### 3.3 Generation miss

**Definition:** the answer-bearing chunk is in the prompt and the answer is still wrong (or refuses when it should answer).

Causes:

- the model ignores context and answers from parametric memory;
- the evidence is buried in the middle (Topic 27);
- two chunks conflict and the model picks the wrong one;
- instructions conflict with evidence ("always be helpful" vs "abstain if unsure");
- the answer cites a chunk that does not support it;
- the model over-abstains despite sufficient evidence;
- the answer is truncated by the output limit.

**Observable:** `gold ∈ prompted` and `answer_correct = False`. The fix lives in the prompt, the evidence set, or a verifier/guardrail.

### 3.4 Unanswerable by corpus

**Definition:** no chunk in the corpus contains the answer. This is not a "miss" to be fixed by retrieval — the correct behaviour is **abstention** (or routing to a human/another source).

Types:

- out of scope (the corpus is about refunds; the question is about careers);
- private/unauthorised data;
- too recent (the corpus predates the event);
- requires joining facts the corpus does not contain;
- ambiguous questions with no single answer.

**Observable:** `gold ∉ corpus`, or a human label of "not answerable". The metric is the **false-answer rate** on this set, not recall.

### 3.5 The decision tree

```text
Is the gold chunk in the corpus?
├─ No  → unanswerable        (correct behaviour: abstain)
└─ Yes
   └─ Is it in the retrieved set?
      ├─ No  → retrieval_miss
      └─ Yes
         └─ Is it in the final prompt?
            ├─ No  → ranking_miss
            └─ Yes
               └─ Is the answer correct?
                  ├─ No  → generation_miss
                  └─ Yes → ok
```

The **order of the checks is the method**. Check the corpus first, because no downstream fix can recover an answer that was never there. Check retrieval before ranking, because a chunk that was never retrieved cannot be "dropped by the prompt".

`locate_stage(gold_in_corpus, gold_retrieved, gold_in_prompt, answer_correct)` is this tree as a pure function. It has 16 possible input combinations; the expected outputs are exhaustively tested. The important asymmetries:

| in corpus | retrieved | prompted | correct | label |
|---|---|---|---|---|
| no | any | any | any | `unanswerable` |
| yes | no | any | any | `retrieval_miss` |
| yes | yes | no | any | `ranking_miss` |
| yes | yes | yes | no | `generation_miss` |
| yes | yes | yes | yes | `ok` |

---

## 4. Instrumentation: You Cannot Diagnose What You Did Not Log

The diagnosis needs **four sets per query**, not just the final answer:

| Set | Where it comes from | Why it matters |
|---|---|---|
| `corpus_ids` | the index at query time | separates unanswerable from retrieval miss |
| `retrieved_ids` | the retriever's ranked output | separates retrieval from ranking |
| `prompted_ids` | the assembler's included evidence | separates ranking from generation |
| `cited_ids` | the answer's resolved citations | detects citation mismatches |
| `answer_correct` | labels/judges | separates generation miss from ok |

The module's `Case` is exactly this record, plus operational metadata:

```python
Case(
    case_id="ranking-miss",
    question="What is the return window for international orders?",
    gold_ids=("returns#02",),
    corpus_ids=(...),
    retrieved_ids=("returns#00", "returns#02", "shipping#00"),
    prompted_ids=("returns#00", "shipping#00"),
    answer="Returns are accepted within 30 days. [1]",
    answer_correct=False,
    cited_ids=("returns#00",),
    expected="ranking_miss",
)
```

Practical logging rules:

- log **chunk IDs** and scores, not full text (privacy, cost, log volume);
- sample full prompts/answers separately with access control;
- include the profile key (model, dimensions, chunker version) and index age;
- include the assembly report (`dropped`, `truncated`, `duplicates_removed`);
- record whether the answer was an abstention;
- timestamp queries so a stale-index window is visible;
- make the record reproducible from the document version + query.

Without `retrieved_ids` and `prompted_ids`, every failure looks like "the model is bad".

---

## 5. Diagnosis: Symptoms to First Moves

The suite has labels, but humans arrive with symptoms. `SYMPTOM_GUIDE` maps the common ones to a stage and a first check:

| Symptom | First diagnosis | First move |
|---|---|---|
| Wrong answer, but cites a real chunk | `generation_miss` | check whether the cited chunk actually contains the claim; add groundedness |
| "I don't know" although the doc exists | `generation_miss` / over-abstention | confirm the gold chunk is in the prompt; loosen refusal or fix ordering |
| New documents never show up | stale index / ingest | freshness canary; compare source count to index count; reindex trigger |
| Two answers contradict each other | conflict | detect conflicting chunks; prefer recency/authority or show both |
| Similar chunks, never the exact one | `retrieval_miss` | inspect chunk boundaries, hybrid search, ef_search/probes |
| Cites a source that was not in the prompt | citation mismatch | validate markers against the assembly map |
| Plausible answer, no citation | hallucination | require citations; groundedness check; abstain when unsupported |
| Answers a question the corpus cannot answer | unanswerable | coverage check before generation; calibrate abstention |

The pattern is always the same: **locate the stage, then choose the fix**. Do not start with the fix.

---

## 6. Stale Indices

A stale index is a **cause**, not a symptom label. The symptom is usually a retrieval miss (the fresh document is absent) or a conflict (old and new chunks both present).

### 6.1 How indices go stale

- ingestion is a one-off script, not a scheduled/triggered job;
- the job fails silently (zero documents, auth error swallowed, partial batch);
- deletes do not propagate (soft-deleted docs remain searchable);
- the embedding model changed but the index was not rebuilt (profile drift);
- a cache/CDN layer serves old results;
- replication lag: the document is in the source DB but not yet in the vector table;
- a "temporary" backfill never finished.

### 6.2 Detection

- **age:** `now - max(updated_at)` for the index; the module treats `index_age_days > 30` as stale evidence (threshold configurable).
- **change tracking:** `doc_changed_since_ingest` — the source hash differs from the manifest hash.
- **freshness canary:** ingest a known document, mutate it, query for the new value, and assert the old value no longer wins. Run on a schedule.
- **counts/checksums:** source document count vs indexed distinct `doc_id`; per-document content hash reconciliation.
- **known-answer probes:** a small set of questions whose answers must change when a document changes.

### 6.3 Fixes

- reindex on content change (manifest diff) and on a schedule (belt and braces);
- expose an index-age metric and alert on it;
- make deletes first-class: a tombstone table or a `deleted_at` filter applied at query time;
- blue/green rebuild for model changes (Topic 26);
- a freshness SLO: "a changed document is queryable within N minutes".

In the fixture, `stale-index` has `index_age_days=45` and the gold chunk missing from retrieval. The diagnosis is:

```text
stale-index   retrieval_miss   causes: stale_index
```

The label says what you observe; the cause says why. That distinction is what stops you from "fixing" retrieval while the real problem is that the ingester stopped running three weeks ago.

---

## 7. Conflicting Chunks

### 7.1 How conflicts arise

- multiple document versions (old and new policy both indexed);
- region/product variants that share a title but differ in values;
- duplicated sources with different dates or authorities;
- a migration that wrote both old and new chunks;
- user-generated content contradicting official documentation.

Conflicts are especially dangerous because both chunks are *relevant*. Retrieval did its job; the corpus is inconsistent. The model then picks one — often the first, the longer, or the more confidently worded one.

### 7.2 Detection in the module

The module extracts simple numeric policy claims:

```text
"the <subject> is <number> <unit>"
```

Examples: "the return window is 30 days", "the warranty period is 12 months". Claims with the same subject but different values are a conflict:

```python
extract_claims({"policy#old": "The return window is 30 days.",
                "policy#new": "The return window is 14 days."})
# [Claim("policy#old", "return window", 30, "day"),
#  Claim("policy#new", "return window", 14, "day")]

find_conflicts(claims)
# [Conflict(subject="return window",
#           statements=(("policy#new", "14 days"), ("policy#old", "30 days")))]
```

Units are normalised (`day`/`days`) so a sloppy plural is not reported as a conflict. The fixture's conflicting case is labelled `generation_miss` — the gold chunk was in the prompt, but the model quoted the old value — and carries the cause `conflict`.

At production scale, replace the regex with:

- entity/attribute extraction (dates, prices, limits, eligibility);
- an NLI/contradiction model over pairs of retrieved chunks;
- an LLM judge restricted to "do these two statements disagree about the same fact?";
- metadata-aware checks (same canonical entity, different `effective_date`).

### 7.3 Resolution

There is no universal answer, but there are defensible policies:

1. **Authority:** an official policy document outranks a support macro or a user comment.
2. **Recency:** for time-varying facts, prefer the latest `effective_date`; keep the old version for historical questions.
3. **Scope:** "14 days for international orders" does not conflict with "30 days domestic" if the scope is explicit. Extract and respect the scope before declaring a conflict.
4. **Surface the conflict:** when unresolved, answer with both values and dates ("the policy changed from 30 to 14 days on…") or abstain.
5. **Never average or silently pick.** That produces a third, wrong answer.

---

## 8. Unanswerable-by-Corpus Questions

### 8.1 Why this category is separate

Retrieval metrics assume a relevant document exists. For unanswerable questions, a retriever will still return the *least irrelevant* chunks, and a helpful model will often answer from parametric memory. Recall@k is meaningless; the metric that matters is **false-answer rate**.

### 8.2 Building the set

Collect questions that are:

- out of scope for the corpus,
- about documents that were deleted or never ingested,
- too recent for the index,
- answerable only by combining facts that are not co-located,
- ambiguous or underspecified.

Label them "unanswerable" with a reference answer of "I don't know" (plus the reason). Keep them in the eval suite permanently; they are the regression test for helpfulness bias.

### 8.3 Correct behaviour and detection

The two fixture cases show both outcomes:

| Case | Gold in corpus? | Answer | Diagnosis |
|---|---|---|---|
| `unanswerable` | no | "I don't know…" | `unanswerable` (correct) |
| `answered-unanswerable` | no | "Yes, we price match within 5 days. [1]" | `unanswerable` + `answered_unanswerable` |

The second is the dangerous one: a fluent, cited answer to a question the corpus cannot answer. The citation may even be valid — the chunk exists, it just does not support the claim.

Defences:

- **coverage check before generation:** classify whether the retrieved evidence actually contains an answer (retrieval score threshold + LLM/NLI check);
- **calibrated abstention:** measure the refusal rate on answerable vs unanswerable sets and tune the instruction/threshold;
- **routing:** send low-coverage questions to a human or a different source instead of the generator;
- **citation + groundedness validation:** an unsupported claim should fail even when the marker is valid;
- **eval both directions:** over-abstention on answerable questions is also a failure (see §9).

---

## 9. Generation Misses

With the gold chunk in the prompt, the remaining failure surface is the model + prompt:

### 9.1 Ignored context

The model answers from parametric memory, especially when the context is long, noisy, or contradictory. Detection: compare the answer against the cited chunk (quote overlap, NLI); run a **counterfactual** — change the gold chunk's value in the prompt and see whether the answer changes. If the answer stays the same, the model is not using the context.

### 9.2 Lost in the middle

The gold chunk is present but in a weak position. Detection: measure accuracy by gold-chunk position in a controlled eval; apply sandwich ordering and repeat the question (Topic 27).

### 9.3 Conflicting evidence

Two chunks disagree; the model picks one. Detection: `find_conflicts` at assembly; resolution policies in §7. Conflicts are a corpus/assembly problem that surfaces as a generation miss.

### 9.4 Citation mismatch

The answer cites `[7]` when only five chunks were assembled, or cites a chunk that does not contain the claim. Detection: `validate_citations` for the first; quote/claim matching for the second. Fix: number after pruning, validate before returning, and instruct the model to quote the supporting sentence.

### 9.5 Over-abstention

The gold chunk is present, but the model refuses. Causes: an over-cautious instruction, a low-confidence retrieval score leaking into the prompt, or a conflict the model cannot resolve. Detection: refusal rate on answerable cases with gold-in-prompt; flag `over_abstention`. Fix: strengthen the evidence framing ("the answer is in the context; use it"), add few-shot grounded answers, or lower the refusal threshold.

### 9.6 Hallucinated support

A fluent answer with a valid-looking citation that does not support it. Detection: groundedness checks (NLI, quote matching, LLM judge with the cited chunk only). Fix: require verbatim quotes, verify each sentence, or replace the generator with a more constrained/extractive path for high-stakes answers.

### 9.7 Output truncation

The answer is cut off by `max_tokens` or the context window. Detection: finish-reason checks (`length`), answer completeness evals. Fix: reserve more output tokens (Topic 27), shorten the answer format, or stream/continue.

---

## 10. The Failure-Boundary Habit

A **failure boundary** is a written answer to three questions for each stage:

1. **What breaks?** (the failure mode)
2. **How would we notice?** (metric, log, probe, alert)
3. **What would we change?** (the remediation)

Write it *before* launch, keep it next to the code, and map every incident back to a row. If an incident does not fit a row, the table is incomplete — add it.

The module encodes one boundary per pipeline stage:

| Stage | What breaks | How you notice | What you change |
|---|---|---|---|
| **ingest** | a loader skips/truncates/corrupts a document; the index never has it | source vs indexed counts; checksums; zero-doc crawl | assert counts/checksums; fail on empty sources; volume alerts |
| **chunk** | the answer is split across a boundary, diluted by boilerplate, or trapped in a table/code fence | chunk-level recall on labelled questions; inspect gold boundaries | paragraph/semantic chunking; overlap; keep structured blocks intact |
| **embed** | query and document vectors are incomparable (model/prefix drift, truncation, zero vectors, OOV) | vector norms; model ID per row; retrieval evals after model changes | pin model + prefix; reject zero vectors; reindex on change |
| **store** | stale rows, partial writes, missing/never-built index | freshness canary; row counts per source; index build logs | idempotent upserts; prune removed chunks; reindex triggers; freshness SLO |
| **query** | the query is rewritten badly, empty, or embedded with the wrong model/prefix | log final query + norm; compare rewritten vs raw retrieval | guard rewriting; fall back to the raw question; one embedding contract |
| **retrieve** | ANN under-recall; filters remove the answer; k > index; post-filtering returns too few | recall@k vs exact; filter cardinality; returned count vs k | raise ef_search/probes; pre-filter; hybrid search; over-retrieve then rerank |
| **assemble** | the gold chunk is deduped away, budget-dropped, truncated, or buried in the middle | assert the gold chunk is cited; log drops/reasons; record prompt order | budget accounting; near-duplicate detection; sandwich ordering; citations at assembly |
| **answer** | the model ignores context, hallucinates, cites unsupported sources, or over-abstains | groundedness/citation checks; gold-in-context counterfactual; refusal rate by answerability | grounded instructions; citation validation; verifier pass; calibrated abstention |

Two disciplines make the table useful:

- **Every row needs a probe.** A failure mode with no detection is a story, not a boundary. The probe can be a unit test, a scheduled canary, a dashboard, or an alert.
- **Every incident gets a row and a regression test.** The fix is not done when the answer is patched; it is done when the same failure would be caught automatically.

---

## 11. Evaluation: Measuring Each Stage

End-to-end answer accuracy is necessary but too coarse to diagnose. Track at least:

### Retrieval

- **recall@k** — fraction of cases where the gold chunk is in the top k (report "any gold" and "all gold" separately);
- **MRR** — mean reciprocal rank of the first gold chunk;
- **nDCG@k** — graded relevance, if you have it;
- **exact-vs-ANN recall** — sample queries, compare ANN results to exact search (Topic 25).

### Ranking / assembly

- **context precision** — fraction of prompted chunks that are relevant;
- **context recall** — fraction of gold chunks present in the prompt;
- **drop reasons** — how often the gold chunk is dropped by dedupe vs budget vs top-k;
- **position of the gold chunk** in the prompt (lost-in-the-middle risk).

### Generation

- **answer correctness** — labels/rubric/exact match, per question type;
- **citation validity** — markers exist in the assembly map;
- **groundedness** — fraction of answer claims supported by the cited evidence (NLI/LLM judge with spot checks);
- **abstention rate** — split by answerable/unanswerable;
- **false-answer rate on unanswerable** — the headline safety metric.

### Diagnosis itself

- **stage-attribution accuracy** on the labelled failure suite — the module's `run_suite` scores this;
- **confusion matrix** of expected vs diagnosed labels; systematic confusion points to missing instrumentation.

LLM-as-judge is useful for scale but must be calibrated against human labels, with a fixed rubric, blind ordering, and periodic spot checks. A judge that agrees with itself is not evidence.

---

## 12. Implementation Walkthrough — `diagnose.py`

- **`Case`** — the observed query plus the four sets, answer correctness, citations, index age, and expected label; validates labels and ages.
- **`locate_stage`** — the four-question decision tree, exhaustively tested over 16 input combinations.
- **`diagnose`** — label + causes (`stale_index`, `prompt_pruned`, `conflict`, `citation_mismatch`, `over_abstention`, `answered_unanswerable`) + fixes + notes.
- **`extract_claims` / `find_conflicts`** — numeric policy claims, unit normalisation, conflict grouping.
- **`is_abstention`** — refusal detection (over-abstention is a failure, not success).
- **`BOUNDARIES` / `failure_boundary`** — the eight-stage failure-boundary table.
- **`SYMPTOM_GUIDE` / `guide`** — symptom → first diagnostic move, exact or substring match.
- **`run_suite`** — diagnoses a labelled list, scores accuracy, counts labels, reports mismatches.
- **`SAMPLE_CASES` / `SAMPLE_CHUNKS`** — ten fixtures covering every label and cause.

The suite result on the fixture:

```text
cases=10 scored=10 correct=10 accuracy=1.00
labels: generation_miss=4, ok=1, ranking_miss=1, retrieval_miss=2, unanswerable=2
```

```text
ok                       ok               causes: -
retrieval-miss           retrieval_miss   causes: -
ranking-miss             ranking_miss     causes: prompt_pruned
generation-miss          generation_miss  causes: -
unanswerable             unanswerable     causes: -
stale-index              retrieval_miss   causes: stale_index
conflicting-chunks       generation_miss  causes: conflict
citation-mismatch        generation_miss  causes: citation_mismatch
over-abstention          generation_miss  causes: over_abstention
answered-unanswerable    unanswerable     causes: answered_unanswerable
```

The conflicting chunks fixture:

```text
conflict: return window
  policy#new → 14 days
  policy#old → 30 days
```

Run it:

```bat
cd phase-03-embeddings-rag\topic-28-where-rag-fails\implementation
python -m pytest -q          :: 72 passed
python diagnose.py           :: demo: suite, diagnoses, conflicts, boundaries
```

The 72 tests cover: the 16-row decision table; every fixture label; stale age and doc-change causes; conflict extraction/normalisation/sorting; citation mismatch; over-abstention; answered-unanswerable; fixes per label/cause; symptom guide exact/substring/unknown; all eight boundaries; suite accuracy, counts, mismatches, empty and unscored cases; and frozen diagnosis records.

---

## 13. Pitfalls

1. **Blaming the model first.** Check the four sets before touching the prompt. Most "hallucinations" are missing evidence.
2. **Logging only the final answer.** Without retrieved/prompted IDs and drop reasons, diagnosis is guesswork.
3. **Evaluating with the same retriever that produced the failure.** You need gold chunk IDs (or human labels) to compute recall and to tell retrieval from ranking.
4. **Stopping at recall@k.** A chunk can be retrieved and still never reach the prompt. Measure context recall/precision and prompt inclusion.
5. **Treating a stale index as a symptom.** It is a cause; the label is usually `retrieval_miss`. Fix the freshness pipeline, not the retriever.
6. **Evaluating only answerable questions.** The model learns that every question has an answer; false answers on unanswerable questions go unmeasured.
7. **Deduplicating away conflicting evidence.** Conflicts are information, not noise. Surface or resolve them; do not let dedupe pick a winner silently.
8. **Using an LLM judge without calibration.** Judges have position, verbosity, and self-preference biases; anchor them to human labels and spot-check.
9. **Fixing generation when the evidence was never in the prompt.** You will "improve" the prompt while the retrieval bug remains.
10. **No regression set.** A fix that works for one question rotates the failure to another. Keep the labelled cases and add every incident.
11. **Logging full text and PII by default.** Log chunk IDs, scores, and hashes; gate full-text access.
12. **Assuming ANN is exact.** Recall below 1.0 is normal; a missing gold chunk can be an index-tuning problem, not a model problem.

---

## 14. Exercises

1. **Instrument your own pipeline.** Add the four sets (`corpus`, `retrieved`, `prompted`, `cited`) and the assembly report to one real query. Write them as a JSON record with chunk IDs and scores.
2. **Build a 20-case labelled suite.** Include at least: 5 ok, 3 retrieval misses, 2 ranking misses, 3 generation misses, 4 unanswerable, 1 stale-index case, 1 conflict, 1 citation mismatch. Run `run_suite`; where does your diagnosis disagree with your labels?
3. **Stale-index drill.** Stop the ingest job, change a source document, and query for the new value. Write the canary that would have caught it, then wire it into a test/alert.
4. **Conflict lab.** Take two real documents that disagree (or fabricate one). Add claim extraction, detect the conflict, and implement a recency/authority policy. What does the answer look like when the conflict is unresolved?
5. **False-answer rate.** Write 20 unanswerable questions for your corpus. Measure how many get answered, with and without a coverage check. Report the delta.
6. **Counterfactual test.** For 10 cases, change a number in the gold chunk inside the prompt and see whether the answer changes. What fraction of answers are actually grounded in the evidence?
7. **Citation audit.** Run citation validation on 50 answers, then manually check whether the cited chunk supports the claim. Estimate precision and recall of the validator against your judgement.
8. **Boundary review.** Fill in the eight-row failure-boundary table for your own system, with a concrete probe per row. Which row has no probe today?

---

## 15. Done-When Checklist

- [x] I can classify a failure as unanswerable, retrieval miss, ranking miss, or generation miss from the four sets.
- [x] I can explain why the checks must happen in that order, and what each label implies for the fix.
- [x] I can detect a stale index with age, content hashes, counts, and a freshness canary.
- [x] I can detect conflicting chunks and choose a defensible resolution policy.
- [x] I can distinguish an unanswerable question from a retrieval failure and measure the false-answer rate.
- [x] I can name the generation failure modes (ignored context, lost in the middle, conflict, citation mismatch, over-abstention, hallucination) and a detection for each.
- [x] I can write a failure-boundary row for all eight stages with a probe and a change.
- [x] I can score a labelled diagnostic suite and explain where my attribution is wrong.

# Topic 27 — Prompt Construction from Retrieved Context

## 1. Purpose of This Topic

Retrieval decides *what* the model may see. Prompt construction decides **what it actually sees, in what order, with how much room, and with which citation contract**.

A retriever can return the perfect chunk and the answer can still be wrong because:

- the chunk was placed in the middle of a long context and the model ignored it (**lost in the middle**),
- three near-duplicate chunks consumed the budget and pushed out the diverse evidence,
- the answer-bearing chunk was truncated at the budget boundary,
- the question was buried above 20k tokens of evidence,
- citation numbers were assigned before pruning, so `[4]` points at nothing,
- retrieved text closed the `<context>` tag and "became" instructions.

This topic builds an assembler that makes each of those decisions explicit and testable:

```text
candidates → dedupe → order → budget → cite → render → validate
```

The implementation is `implementation/prompting.py`, with 62 offline tests covering ordering, deduplication, budget accounting, citation integrity, question placement, and template/injection hygiene.

**Done when:** you can assemble a context window that neither exceeds the budget nor buries the question, with citation slots built into the assembly rather than reconstructed afterwards.

### Sources and what each contributes

- **Lost in the Middle (Liu et al., 2023)** — the empirical basis for ordering: performance is highest when relevant information sits at the beginning or end of the context and degrades when it is in the middle; the effect persists in long-context models.
- **DeepLearning.AI — RAG course** — context relevance, groundedness, and answer relevance as the evaluation frame; assembly choices are measured, not vibes.
- **Hugging Face cookbook** — the standard prompt shape for a small RAG recipe: instructions, retrieved context, question; a useful baseline to improve on.
- **Applied LLMs** — structure inputs and outputs, keep prompts focused, and craft context tokens deliberately rather than stuffing.

---

## 2. Prerequisites

**Before: Topic 26**

- The pipeline stages and the retrieved/prompted/answer distinction.
- Token estimation and chunk sizes (Topic 24).
- Citations as markers attached to chunks (Topic 26, §10).
- Basic prompt engineering: system vs user message, delimiters, output constraints.

---

## 3. The Prompt Is a Budgeted Artifact

A RAG prompt has five competing consumers of one finite window:

```text
┌──────────────────────────────────────────────┐
│ instructions (static, authored)              │  fixed cost
├──────────────────────────────────────────────┤
│ evidence blocks (dynamic, retrieved)         │  the variable budget
├──────────────────────────────────────────────┤
│ question (dynamic, short)                    │  fixed-ish cost
├──────────────────────────────────────────────┤
│ answer reserve (output tokens)               │  must be reserved
├──────────────────────────────────────────────┤
│ template overhead (tags, headers, separators)│  easy to forget
└──────────────────────────────────────────────┘
```

The total must satisfy:

```text
instructions + evidence + question + answer_reserve + overhead ≤ context_window
```

Two hard rules:

1. **The answer reserve is not optional.** If the context window is also the model's maximum input+output length, filling it with evidence leaves no room to answer. Reserve 15–25% for the response, more for long-form answers.
2. **Never target 100% utilisation.** Token estimators are approximate (especially for code, JSON, and non-English text), and providers count message framing/templates differently. Keep a 10–15% safety margin.

The module computes the plan explicitly and refuses to over-allocate:

```python
plan = plan_budget(
    total_tokens=900,
    instruction_tokens=76,
    question_tokens=7,
    answer_reserve=150,
    overhead_tokens=14,
)
# BudgetPlan(total=900, instructions=76, question=7,
#            answer_reserve=150, overhead=14, evidence=653)
```

The real assembled prompt from the fixture uses **165 tokens**: the evidence is far below its 653-token allowance. That is fine — a budget is a ceiling, not a target. Stuffing to the ceiling is how quality drops.

### 3.1 Sizing the split

Practical starting ratios for a support/RAG assistant:

| Component | Share | Notes |
|---|---:|---|
| instructions | 10–15% | static, authored, deduplicated; do not grow it with retrieved text |
| question | 1–5% | short; counts twice if repeated at both edges |
| evidence | 55–70% | the actual variable budget |
| answer reserve | 15–25% | raise for long answers or tool/JSON output |
| overhead | 2–5% | tags, headers, separators, message framing |

These are starting points, not laws. The right split is measured: if answers are truncated, raise the reserve; if answers ignore evidence, the problem is ordering/dedup, not a bigger context.

### 3.2 Estimation

`estimate_tokens(text) = ceil(len(text) / 4)` is the heuristic used here and in Topic 24. It is deliberately simple and **wrong in useful ways**: code and JSON can be 2–3× denser, CJK text is much denser, and markdown tables distort it. Production should use the model's tokenizer (`tiktoken`, the provider's count endpoint) and still keep a margin. The assembly algorithm is estimator-agnostic: swap the function, keep the budget logic.

---

## 4. Ordering Effects: Lost in the Middle

### 4.1 The finding

Liu et al. evaluated models on multi-document QA and key-value retrieval where the relevant passage was placed at different positions in a long context. Two robust results:

- accuracy is **highest when the relevant information is at the start or end** of the context and **lowest in the middle** — a U-shaped curve;
- the degradation is not fixed by longer context windows: models with extended context still under-use information in the middle, and the effect tends to worsen as the context grows.

The practical reading: **retrieval order is a prompt-engineering decision**. The common default — dump top-k in descending score order — puts the best chunk first (good) but the second-best chunk immediately after it, and the rest toward the middle. When the answer needs the 4th–8th chunk, it is in the worst position.

### 4.2 The simulator in this repo

No model is available offline, so `positional_weights(n)` models a U-shaped attention profile and normalises it to 1:

```text
n=5 → [0.267, 0.167, 0.133, 0.167, 0.267]
n=4 → [0.321, 0.179, 0.179, 0.321]
```

The middle position gets **half** the weight of an edge at `n=5` (`0.133` vs `0.267`). This is a simulation of the documented curve, not a measurement of a specific model — its job is to make ordering choices produce numbers in tests and demos instead of assertions of taste.

`position_sensitive_quote(question, ordered)` multiplies each chunk's query-term overlap by its positional weight and picks the maximum. With two equally relevant chunks:

```text
ordered: [gold-edge, noise, gold-mid, noise, noise]
weights: [0.267,     0.167,  0.133,   0.167, 0.267]
scores:  [0.533,     0,      0.267,   0,     0]
pick:    gold-edge
```

Same evidence, same relevance, half the expected attention because of position alone.

### 4.3 Ordering strategies

| Strategy | Result for scores `[.91, .72, .65, .44]` | When to use |
|---|---|---|
| `as_retrieved` | `.91, .72, .65, .44` | trust the retriever; baseline |
| `best_first` | `.91, .72, .65, .44` | most demos; best chunk at index 0 |
| `worst_first` | `.44, .65, .72, .91` | ablation only: strongest at the end |
| `sandwich` | `.91, .65, .44, .72` | default here: strongest first **and** second-strongest last |

`order_evidence(..., "sandwich")` places rank 1 at the start, rank 2 at the end, and the rest in the middle (descending). The point is not that this is universally best; it is that **you can state the policy, test it, and change it in one place**.

### 4.4 Question placement

The question can go:

- **after the context** (`end`) — the most common default; the question is the last thing the model reads before answering (recency).
- **before the context** (`start`) — useful when the context is short and the question frames what to look for.
- **both** (`both`) — repeat the question at the end of long contexts so it is not buried; costs the question's tokens twice.

The module makes the placement explicit and counts the duplicated question in the budget:

```python
assemble_prompt(..., question_position="end")   # default
assemble_prompt(..., question_position="start")
assemble_prompt(..., question_position="both")  # question counted twice
```

There is no universal winner. Measure on your own eval set, especially as context length grows.

---

## 5. Deduplication

### 5.1 Why duplicates are expensive

Chunk overlap (Topic 24) deliberately duplicates text at boundaries. Add repeated headers/footers, the same policy in three documents, and near-identical FAQ answers, and a top-10 retrieval set can contain four copies of one paragraph. Consequences:

- **budget waste:** duplicates consume evidence tokens that diverse chunks needed;
- **false consensus:** the model sees "the same fact" four times and treats it as more authoritative;
- **citation confusion:** four markers point at nearly identical text; the answer's `[3]` is arbitrary;
- **ranking distortion:** duplicates crowd out the one chunk that actually answers a different part of the question.

### 5.2 Exact vs near duplicates

**Exact:** normalise case and whitespace, then hash. Our `_normalise` lowercases and collapses whitespace, so `"  Same   TEXT. "` and `"same text."` collide. This catches repeated boilerplate and literal copies.

**Near:** token-set Jaccard similarity:

```python
jaccard(tokens_a, tokens_b) = |A ∩ B| / |A ∪ B|
```

The module drops a candidate when its Jaccard with an already-kept chunk is ≥ `near_threshold` (default 0.85). That catches punctuation/casing/stopword edits without needing embeddings. It is O(n²) over the candidate set — fine for 10–100 chunks.

At larger scale:

- **MinHash + LSH** for sub-linear near-duplicate detection;
- **SimHash** for fixed-width fingerprints;
- **embedding cosine** with a high threshold (e.g. 0.95) when paraphrases must collapse;
- **metadata-aware rules**: same `doc_id` + adjacent ordinals + high overlap = boundary duplication, which is expected; don't over-collapse.

Over-deduplication is a real failure: two chunks can share most tokens but differ in the one number that matters (`30 days` vs `14 days`). Keep the higher-scored/newer one, record what was removed, and evaluate on labelled cases before making the threshold aggressive.

### 5.3 What the module returns

```python
DedupReport(
  kept=[...],                                  # ranked by score
  removed=[("returns#01", "near_duplicate", "returns#00")],
)
```

The removal list is not decoration: it is the audit trail for "why did the prompt have only two chunks?" and feeds the ranking-miss diagnosis in Topic 28.

---

## 6. Citations Baked Into Assembly

### 6.1 Assign markers at assembly time

The citation contract should be established **when the prompt is built**, not reconstructed from the answer afterwards:

```text
[1] Return Policy
Returns are accepted within 30 days of delivery. Refunds are issued within 5 business days.

[2] Shipping Damages
Shipping damage claims must be filed within 48 hours of delivery. …
```

- the marker `[n]` is inserted into the evidence block,
- the same `n` is stored in `citations: {chunk_id: n}`,
- the instruction says: *cite every factual sentence with the marker of the evidence that supports it*,
- the validator checks every marker in the answer against the map.

Numbering **after** pruning is essential. If you number first and then drop chunks, the remaining markers have gaps (`[1]`, `[3]`, `[7]`) and the model may cite the missing numbers. The module numbers included chunks in prompt order: `1..m`, contiguous.

### 6.2 Why markers rather than source IDs?

- Short markers are cheap and unambiguous inside the answer.
- Source IDs (URLs, document IDs) are long and models reproduce them unreliably.
- The marker→chunk map lives in the application, where it can be validated and rendered as links.

Anthropic's prompt-engineering guidance recommends asking the model to **quote the supporting passage verbatim** before answering ("cite quotations from documents"). That combines well with markers: quote + `[n]` gives you a string the application can check against the cited chunk.

### 6.3 Validation

```python
validate_citations("Returns take 30 days [1]. See also [9].", assembled)
# → [9]   (no chunk 9 was assembled)
```

This catches:

- hallucinated markers,
- markers left over from a previous turn/context,
- renumbering bugs after pruning,
- answers that cite a source not in the prompt.

It does **not** catch a valid marker attached to an unsupported claim. For that you need groundedness checks: quote matching, NLI, or an LLM judge. Citation validity is necessary, not sufficient.

---

## 7. Template Hygiene: Static Skeleton vs Dynamic Slots

### 7.1 The separation

A prompt has two kinds of text with different trust levels:

- **static skeleton** — authored by you: instructions, tags, output contract. It may contain slots but never retrieved content.
- **dynamic slots** — question and evidence: untrusted input, inserted only at declared positions.

```text
<instructions>
{instructions}          ← static authored text
</instructions>

{opening_question}<context>
{context}               ← untrusted evidence, data only
</context>{closing_question}
```

`PromptTemplate` discovers slots (`{instructions}`, `{context}`, `{opening_question}`, `{closing_question}`), rejects missing/extra values, and renders in a **single pass** by splitting the skeleton and joining values. Retrieved text is never re-scanned for slots.

### 7.2 The failure this prevents

If you build a template by interpolating evidence and then call `.format()` again, braces in the evidence are interpreted:

```python
template = INSTRUCTIONS + "\n{context}\n{question}"
text = template.format(context=evidence, question=question)
# evidence = "see {question} for details" → still literal here (one pass),
# but any SECOND format pass would substitute it.
```

More importantly, concatenation order can put untrusted text inside the instruction region:

```python
prompt = f"{evidence}\n\n{SYSTEM_PROMPT}\n{question}"   # evidence can claim to be instructions
```

The static/dynamic split makes that structurally impossible: instructions are rendered from the authored slot; evidence can only appear inside `<context>`.

### 7.3 Injection hygiene

Retrieved documents are attacker-controlled in the general case (web pages, user uploads, support tickets). The module applies two cheap mitigations:

1. **Tag neutralisation** — `</context>` becomes `[/context]`, so evidence cannot close the data block and start a fake instruction block.
2. **Instruction-like line removal** — lines beginning with `ignore previous…`, `disregard…`, `system:`, `assistant:`, `you are now`, `new instructions:` are dropped and counted (`injection_lines_removed`).

Neither is a complete defence. Prompt injection is not solved by string filtering; models can be persuaded by paraphrases, encodings, or content that looks like data. The serious defences are layered:

- state clearly that `<context>` is data, never instructions (in the static skeleton);
- keep the model's tools/permissions minimal; retrieved text must not be able to trigger side effects;
- validate outputs (citations, schemas, allow-lists);
- evaluate injection attempts as a test suite, not as a one-off review;
- log `injection_lines_removed` so you can see attacks rather than silently swallowing them.

### 7.4 Output contract

The skeleton should also pin the output shape:

- cite with `[n]`;
- answer in the requested language/format;
- abstain with a fixed phrase when the context lacks the answer;
- no markdown if the UI renders plain text (or vice versa).

A stable output contract is what makes downstream validation and citation parsing possible.

---

## 8. The Assembly Algorithm, Step by Step

`assemble_prompt(question, candidates, ...)`:

1. **Validate the template and question position.** Unsupported positions fail loudly; unexpected slots fail loudly.
2. **Plan the budget.** Measure instructions, question (×2 if `both`), template overhead, reserve the answer, and compute the evidence allowance.
3. **Dedupe** (optional) — exact + near-duplicate removal, ranked by score, with an audit trail.
4. **Order** — `sandwich` by default: strongest at the edges, weaker in the middle.
5. **Sanitise** each candidate — strip instruction-like lines, neutralise tags.
6. **Fit into the evidence budget**, in order:
   - if the whole block fits, include it and assign the next citation number;
   - if not, and truncation is allowed and at least `min_chunk_tokens` remain, truncate the body and include it (mark `truncated`);
   - otherwise drop it (record `(chunk_id, "budget")`).
7. **Render** the static skeleton with instructions, context, and question blocks.
8. **Verify** the final token count against the total budget; raise if it exceeds.

The result is an `AssembledPrompt` carrying everything needed to audit the decision:

```python
AssembledPrompt(
    text=...,
    evidence=[...],                       # in prompt order
    citations={"gold-edge": 1, "n1": 2, ...},
    budget=BudgetPlan(...),
    used_tokens=165,
    dropped=[("big#02", "budget")],
    truncated=[],
    duplicates_removed=[...],
    injection_lines_removed=1,
    question_position="end",
)
```

### 8.1 Worked example

Candidates: five chunks, scores `0.90, 0.80, 0.70, 0.60, 0.50`; budget 900 tokens; answer reserve 150.

```text
BudgetPlan(total=900, instructions=76, question=7,
           answer_reserve=150, overhead=14, evidence=653)

order (sandwich): gold-edge(.90), n1(.70), n2(.60), n3(.50), gold-mid(.80)
used: 165 tokens
citations: gold-edge=1, n1=2, n2=3, n3=4, gold-mid=5
```

Note what the ordering did: the second-best chunk (`gold-mid`, .80) moved to the **end**, where the positional weight is highest, instead of sitting at index 1. The prompt order and the citation numbers are both consequences of the assembly policy.

### 8.2 Truncation vs dropping

When a chunk does not fit:

- **Truncate** if there is enough room to keep a meaningful prefix (`allow_truncation=True`). Mark it: a truncated chunk can lose the sentence that answers the question.
- **Drop** if what remains is below `min_chunk_tokens`; a fragment is worse than no fragment because it looks like evidence and cannot support an answer.
- **Never** silently cut without recording it. `truncated` and `dropped` are the audit trail that Topic 28 uses to distinguish a ranking miss from a generation miss.

---

## 9. Implementation Walkthrough — `prompting.py`

- **`PromptTemplate`** — slot discovery, strict rendering, `static_segments()` for hygiene tests, custom skeletons.
- **`Evidence`** — `chunk_id`, `text`, `score`, `source`, metadata.
- **`dedupe_evidence`** — exact normalised duplicates + token-set Jaccard near-duplicates; returns kept + removed with reasons.
- **`order_evidence`** — `as_retrieved`, `best_first`, `worst_first`, `sandwich`.
- **`positional_weights` / `expected_attention` / `position_sensitive_quote`** — the offline U-shape simulator.
- **`plan_budget` / `BudgetPlan`** — explicit split with validation; over-allocation and zero evidence room raise.
- **`sanitize_evidence`** — tag neutralisation + instruction-like line removal with a count.
- **`assemble_prompt`** — dedupe → order → fit → cite → render → verify.
- **`validate_citations`** — hallucinated marker detection.

Run it:

```bat
cd phase-03-embeddings-rag\topic-27-prompt-construction\implementation
python -m pytest -q          :: 62 passed
python prompting.py          :: demo: ordering, weights, dedupe, assembly, validation
```

The 62 tests cover: slot discovery/rendering; missing/extra slots; single-pass rendering; unmatched braces; static-vs-dynamic separation; injection stripping and tag neutralisation; exact/near dedupe; every ordering; positional normalisation and edge bias; budget arithmetic and validation; contiguous citations; drops vs truncation; question placement; disabled dedupe; empty candidate lists; and citation validation.

---

## 10. Pitfalls

1. **Dumping top-k in score order and calling it a prompt.** This puts the second-best chunk in position 2 and the answer-bearing 6th chunk in the middle. Order deliberately.
2. **Confusing "more context" with "better context".** Extra chunks add noise, duplicates, and distractor conflicts; they also dilute attention. Retrieve more than you show, show less than you retrieve.
3. **Forgetting the answer reserve.** Filling the window with evidence leaves the model no room to answer; the response is cut off or the request is rejected.
4. **Using characters as tokens without a margin.** Chars/4 underestimates code, JSON, and CJK. Reserve 10–15% headroom or use the real tokenizer.
5. **Deduplicating on exact text only.** Overlapping chunks from Topic 24 are near-duplicates by construction; exact hashing misses almost all of them.
6. **Over-deduplicating.** Collapsing chunks that differ only in a critical number (`30` vs `14`) destroys the answer. Keep the audit trail and validate on labelled cases.
7. **Numbering citations before pruning.** Gaps and mismatches follow. Number after the evidence set is final.
8. **Assuming a citation marker proves grounding.** A valid `[2]` can support a false claim. Validate markers *and* check that the quoted/supported text is actually in the cited chunk.
9. **Putting the question only at the top of a long context.** By the time the model reaches the evidence, the question is far away. Repeat it at the end for long contexts.
10. **Building the prompt by string concatenation with untrusted evidence in the instruction region.** Evidence must be data in a declared slot, never adjacent to instructions without delimiters.
11. **Treating injection filtering as solved.** Strip the cheap attacks, log them, and still assume a determined document can influence the model. Limit what the model can *do* with that influence.
12. **Not logging the dropped/truncated lists.** When the answer is wrong, the first question is "was the evidence even in the prompt?" Without the assembly report, you cannot answer it.

---

## 11. Exercises

1. **Measure the U-shape on your own eval set.** Take 20 questions with known gold chunks, assemble each with the gold at positions 0, middle, and last (fixed context length), and compare answer accuracy. Does your model show the documented curve?
2. **Ordering bake-off.** Run the same 50 cases through `best_first`, `worst_first`, and `sandwich`; report answer accuracy and citation validity. Which wins for your corpus, and by how much?
3. **Dedup threshold sweep.** Vary `near_threshold` from 0.6 to 1.0 on a fixture with boundary-overlap chunks and one near-duplicate containing a changed number. Plot chunks kept vs answer accuracy; find the point where over-dedup hurts.
4. **Budget stress test.** Fix the evidence at 10 chunks and vary `answer_reserve` from 50 to 400 tokens. Find where answers start getting truncated and where evidence gets dropped. What is the safe split for your model?
5. **Citation audit.** Generate 20 answers with the real LLM you use, and run `validate_citations`. Then manually check the valid ones: how many cite a chunk that does not support the sentence? Build a small groundedness rubric.
6. **Injection suite.** Write 10 injection strings (tag closing, "ignore previous", fake system messages, base64/paraphrase). Measure how many the sanitiser removes and how many still change the model's answer. Add the failures as regression tests.
7. **Question placement.** Compare `start`, `end`, and `both` at 1k, 8k, and 32k context. Report accuracy and cost (the `both` variant pays for the question twice).
8. **Template refactor.** Take a prompt you have written with f-strings and move it to `PromptTemplate`. List every place where retrieved text could previously have landed in the instruction region.

---

## 12. Done-When Checklist

- [x] I can explain the lost-in-the-middle curve and why retrieval order is a prompt-engineering decision.
- [x] I can implement and justify `sandwich` ordering, and say when `best_first` is enough.
- [x] I can place the question at the start, end, or both, and account for its token cost.
- [x] I can dedupe exact and near-duplicate chunks with an audit trail, and explain the over-dedup risk.
- [x] I can split a context window into instructions, evidence, question, answer reserve, and overhead with arithmetic.
- [x] I can bake citation markers into assembly, renumber after pruning, and validate the answer's markers.
- [x] I can separate a static prompt skeleton from dynamic slots and explain why retrieved text must never enter the instruction region.
- [x] I can demonstrate an injection attempt being neutralised and state why the defence is still incomplete.

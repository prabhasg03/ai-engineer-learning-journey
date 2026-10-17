# Topic 21 — Decision: when NOT to use an LLM

**Before:** 20 (and most of Phase 2) · **Sources:** [When Code Beats the Model](https://tianpan.co/blog/2026-04-18-when-code-beats-the-model) · [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

**Done when:** for a given feature you argue a justified choice — possibly "no LLM" — plus the condition that would flip it.

## Learning checklist

- [ ] Constraints → candidates → trade-offs → justified choice + sensitivity ("what flips it")
- [ ] Deterministic-first rule; verifiability as an axis
- [ ] Cost/latency budgets deciding as often as capability
- [ ] Classic flips: regex beats LLM extraction; a classifier beats generation

---

## 1. Purpose of this topic

Every feature eventually asks the same question, and the honest answer is often
**"no LLM"**: *should this be a model at all?*

This topic is the closing decision of Phase 2. Topics 11–20 taught you how to build
with an LLM; this one teaches you when not to — and makes the resulting argument
**falsifiable**, because a choice without a flip condition is an opinion, not an
engineering decision.

The framework, in order:

```text
1. CONSTRAINTS   hard requirements, pass/fail: latency budget, cost ceiling,
                 offline/privacy, exactness, scale
2. CANDIDATES    deterministic code, regex/parser, SQL/lookup, classical ML
                 classifier, embedding + nearest neighbour, small LLM,
                 large/reasoning LLM
3. TRADE-OFFS    weighted criteria: capability/quality, verifiability, cost,
                 latency, determinism, maintainability
4. CHOICE        the justified winner
   + SENSITIVITY the single change that would flip it
```

---

## 2. Prerequisites

**Before: Topic 20 (and most of Phase 2)**

You need:

- Cost/latency arithmetic per request (Topics 10, 20) — you will compare
  `$0.00002` and `25ms` against `$0.008` and `2500ms`
- Structured output and schema validation as *verification* (Topic 12)
- Classification/regression intuition from the ML track (regularisation, held-out
  eval) when comparing a classifier to generation
- Agents/workflows thinking (Topic 39 comes later, but the same axes are used)
- The failure-handling mindset: what breaks, how you'd notice, what you'd change

---

## 3. Core concepts

### 3.1 Deterministic-first

If a deterministic method meets the requirement, prefer it. It is:

- **cheaper** — often exactly $0 per request
- **faster** — milliseconds, not hundreds of milliseconds
- **exactly testable** — a unit test is a proof, not a sample
- **incapable of hallucinating** — there is no distribution to sample from
- **free of prompt-injection surface** — there is no prompt

Reach for an LLM only for genuinely **open-ended language or ambiguity**: text
whose acceptable answers are many, whose structure is unknown, or whose rules you
cannot write down. Everything else is a coding task.

### 3.2 Verifiability is an axis

Ask: *can the output be checked cheaply and exactly?*

| Verifiability | What it means |
| --- | --- |
| Regex match, schema validation, unit test, ground truth | High — a verifier catches errors, so LLM **generation becomes safe**, and best-of-N / self-consistency (topic 20) is viable |
| Human review only | Medium — the cost of the error path is now a human's minute |
| Nobody can tell without doing the work | Low — errors ship silently |

**Low verifiability + high stakes** is the dangerous corner: it argues for
deterministic code, heavy guardrails, or human review — never for "trust the model
more". This is the `verifiability_gate` in the code, and it is why an unverifiable
RAG answer at high stakes is a **block**, not a warning.

### 3.3 Budgets decide as often as capability

- A **3s p99** and a **$0.0001/request** ceiling kill an LLM even when it is the
  most capable option on the table.
- Conversely a **$0.02 reasoning call** is trivial next to a human's minute.

Capability rarely wins alone; if a cheaper candidate is within your quality bar,
it wins by definition. Hard constraints (latency, cost, offline, exactness)
eliminate candidates *before* any scoring happens — that order is the whole point.

### 3.4 The classic flips

| Feature | Naive choice | Flip | Why |
| --- | --- | --- | --- |
| Field extraction from a **known** format | LLM extraction | **regex/parser** | deterministic, exact, free, testable |
| The **same** extraction when the format drifts weekly | regex/parser | **LLM + schema validation** | the parser's accuracy collapses; the schema *is* the verifier |
| Routing/labeling into a **fixed** set | generation | **small classifier** | 5ms vs 900ms, $0 vs $0.0004, ~5% less quality |
| A **fixed** FAQ | RAG | **lookup table** | exact match beats embedding + generation |
| A **known** report | text-to-SQL | **hand-written SQL** | no ambiguity to resolve |
| Multi-document synthesis questions | retrieval alone | **RAG generation** | retrieval returns a shelf of chunks, not an answer |

The flip condition is what makes each of those an argument instead of a preference:
*"if the schema drifts past ~2%/week, the parser becomes unmaintainable → LLM
extraction"* is testable; *"LLMs are the future"* is not.

### 3.5 The never-LLM list

Do not use an LLM for:

- **exact arithmetic** (totals, tax, reconciliation) — compute in code
- **deterministic transforms** (unit conversion, date math, formatting)
- **authorization decisions** — policy code, auditable and exact
- **cryptographic exactness** — exact, constant-time, never a sampler
- **exact legal wording** — do not paraphrase what must be verbatim
- anything **unverifiable where errors are unacceptable**

Each of those is in the module as `NEVER_LLM` with its reason, so the "no LLM"
answer has a citation rather than a vibe.

---

## 4. Design

```python
# candidates and their machine-checkable properties --------------------------
@dataclass(frozen=True)
class Candidate:
    name: str; kind: str
    scores: dict[str, float]        # criterion -> 0..1 (higher = better)
    latency_ms: float; cost_usd: float
    requires_network: bool; exact: bool; verifiable: bool

# 1. hard constraints -------------------------------------------------------
@dataclass(frozen=True)
class Constraint: name; predicate: Callable[[Candidate], bool]; detail
latency_constraint(ms) / cost_constraint(usd) / offline_constraint() / exactness_constraint()
apply_hard_constraints(candidates, constraints) -> ConstraintResult(survivors, eliminated)
deterministic_first(candidates) -> list[Candidate]

# 2. weighted trade-offs ----------------------------------------------------
@dataclass(frozen=True)
class Criterion: name; weight; direction="higher"|"lower"
score_candidates(candidates, criteria) -> Ranked(scores, criteria, weight_total)

# 3. verifiability gate -----------------------------------------------------
verifiability_gate(candidate, *, stakes, requires_exactness) -> GateVerdict(allowed, warnings)
never_llm_reason(feature_kind) -> str | None

# 4. the decision and its sensitivity ---------------------------------------
decide(candidates, criteria, constraints, *, stakes, requires_exactness) -> Decision
flip_thresholds(ranked) -> Sensitivity          # analytic: how far the winner must fall
sensitivity(decision, deltas) -> list[SensitivityCheck]   # what-if re-ranking

# worked-example helpers ----------------------------------------------------
choose_extraction(sample, known_format, *, format_stability, stakes)
choose_task_type(task) -> Decision              # classifier vs generation
choose_faq(corpus_size, *, question_variety, answers_span_documents)
```

Three deliberate design decisions:

1. **Constraints are predicates, not scores.** A 3s p99 is not "a low latency
   score"; it is a requirement, and failing it removes the candidate. Modelling it
   as a score is how teams end up shipping an LLM that misses p99 "on average".
2. **`direction="lower"`** exists for value-like axes (error rate, normalised
   cost): the candidate stores the raw value and the ranking inverts it, so the
   same axis can be read either way without hand-negating numbers in the table.
3. **Sensitivity is analytic first.** `flip_thresholds` solves
   `d* = (winner_total - runner_total) * W / w_i` per criterion — the exact drop
   that hands the win over — and `sensitivity` then re-runs the ranking for
   what-if deltas that are *not* a single-axis move (e.g. a weight change).

---

## 5. Implementation walkthrough (`decide.py`)

### The decision loop

`decide(...)` runs the four steps and refuses to guess:

```text
decide(candidates, criteria, constraints=[latency <= 50ms, cost <= $0/request])
  -> eliminate the failures FIRST (with the reason recorded)
  -> rank the survivors on weighted criteria (normalised weights)
  -> gate the winner on verifiability + exactness
  -> produce justification + flip_condition
  -> raise ValueError if every candidate was eliminated
```

### Worked example 1 — invoice field extraction

Candidates: `regex-parser` (2ms, $0, exact), `small-llm-structured` (900ms,
$0.0004, schema-validated), `large-llm-structured` (2500ms, $0.008). Criteria:
accuracy 0.35, robustness 0.25, verifiability 0.20, maintainability 0.20.

```text
known format, stable        regex-parser 0.890 | small-llm 0.846 | large-llm 0.829
  -> regex-parser wins; deterministic-first applies
  -> flip: parser accuracy falling by >= 0.127 (a drifting schema) lets small-llm win

known format, drifting      small-llm 0.846 | large-llm 0.829 | regex-parser 0.465
  -> small-llm-structured wins (schema validation is the verifier)
  -> flip: freeze the layout, reach 100% validated regex coverage -> the parser wins

no known format             large-llm 0.845 | small-llm 0.775 | regex-parser 0.310
  -> large-llm wins; flip: narrow to one template with a published schema
```

The `-0.127` comes straight from `flip_thresholds`: the margin between the parser
and the small LLM is about 0.044, and accuracy carries a weight of 0.35, so a
drop of roughly `0.044 / 0.35` in the parser's accuracy score hands the win over.
That is a *number you can go and measure*: what does parser accuracy actually do
when a vendor changes the layout?

### Worked example 2 — support-ticket routing

```text
"Route this support ticket to the right team"
  classifier 0.960 | generation 0.600      -> classifier (closed-set signals: ['route'])
  flip: the label set stops being fixed (new categories weekly, or labels need rationales)

with latency <= 50ms and cost <= $0/request:
  generation fails 'latency <= 50ms' first (900ms), classifier survives at 5ms
  -> the budget did the deciding; the soft scores never got a vote
```

### Worked example 3 — FAQ answering

```text
40 fixed entries            lookup-table 0.938 | embedding-retrieval 0.770 | rag 0.633
  flip: questions get paraphrased -> exact lookup misses -> embedding-retrieval

questions paraphrased       embedding-retrieval wins
  flip: answers start spanning documents (retrieval returns a shelf of chunks)

multi-document synthesis    rag-generation 0.653 | embedding-retrieval 0.610 | lookup 0.578
  flip: every answer fits one retrievable chunk -> retrieval alone, generation is pure cost
  [gate: stakes=low, so an unverifiable generation step is a warning, not a block]
```

Note how thin that last margin is (0.653 vs 0.610). That is the honest shape of the
problem: the answer depends on weights, and the sensitivity report is what tells
you so. At high stakes the gate flips the recommendation entirely: an unverifiable
generation step is **blocked**, and you go back to curated retrieval plus review.

### Sensitivity output

```text
Delta("parser accuracy fails on a new vendor layout (-0.20)", "accuracy", "regex-parser", -0.20)
  -> winner becomes small-llm-structured
Delta("accuracy weight x1.5", "accuracy", "regex-parser", weight_multiplier=1.5)
  -> still regex-parser (no flip)
```

Run it: `python -m pytest -q` (27 tests) from `implementation/`, or open
`decision_demo.ipynb`.

---

## 6. Pitfalls

- **Scoring a hard constraint.** A latency budget modelled as "a low latency
  score" lets a capable LLM average its way past p99. Constraints eliminate.
- **Choosing on capability alone.** Capability is one criterion; cost, latency and
  verifiability are usually the deciding ones at scale.
- **A decision with no flip condition.** "We picked the LLM" is unfalsifiable.
  Always name the measurement that would overturn it ("if the schema drifts past
  X%/week…").
- **Assuming an LLM is needed because the input is text.** Text input, structured
  output, known format = a parser. Text input, closed label set = a classifier.
- **Ignoring verifiability.** An unverifiable output at high stakes is a block, not
  a tuning problem. Add the verifier or change the candidate.
- **Thresholds carved in stone.** Quality bars, weights and frequencies are
  estimates; put them in one place, version them, and re-run the matrix when your
  traffic or your price list changes.
- **Cost-per-request blindness at scale.** $0.0004 × 5M requests/month is $2,000
  for a router that a 5ms classifier does for free.
- **Treating the matrix as a decision-maker.** It structures the argument; the
  numbers still come from your evals, your p99, and your error budget.
- **Enumerating candidates too narrowly.** If "write a parser" is not in the list,
  deterministic-first can never win. Include the boring options.
- **Letting an LLM into the never-list corners.** Arithmetic, authorization,
  crypto and legal exactness are not judgement calls.

---

## 7. Exercises

1. Take one feature you actually want to build. Fill in the four steps by hand:
   constraints (numbers, not adjectives), candidates (including at least two
   non-LLM), criteria + weights, then run `decide` and compare with your gut.
2. Break your own decision: find the weight change or score drop that flips it with
   `sensitivity`, then go measure whether that change is plausible in your traffic.
3. Add an "escalation" candidate type: classifier first, LLM on low-confidence
   cases, and re-score it. Where does the cascade beat both ends?
4. Implement `choose_report`: SQL template vs text-to-SQL, with a schema-drift flip
   condition. Prove that a known report shape picks SQL.
5. Write the flip conditions for three features in your current project as
   *measurable triggers* (metric, threshold, window) rather than prose.
6. Argue the opposite case for the FAQ matrix at high stakes: show the
   verifiability gate blocking `rag-generation`, and design the cheapest thing that
   would unblock it (span-level citations + an answer-grounding check).

---

## 8. Sources

- When Code Beats the Model — deterministic-first, the classic flips, and why the
  simpler path keeps winning: <https://tianpan.co/blog/2026-04-18-when-code-beats-the-model>
- Anthropic — Building Effective Agents (workflows vs agents, routing, the
  "simplest thing that works" principle this decision framework operationalises):
  <https://www.anthropic.com/engineering/building-effective-agents>
- Related: topic 12 (schema validation as the verifier), topic 19c (routing tiers),
  topic 20 (best-of-N needs a verifier), topic 39 (workflow vs agent — the same
  argument applied to control flow).

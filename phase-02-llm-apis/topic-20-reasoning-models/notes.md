# Topic 20 — Reasoning models and test-time compute ★

**Before:** 7 (temperature and sampling), 10 (token cost and counting) · **Sources:** [OpenAI — reasoning models](https://developers.openai.com/api/docs/guides/reasoning) · [Anthropic — extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) · [Anthropic — visible extended thinking](https://www.anthropic.com/research/visible-extended-thinking)

**Done when:** given a task profile you pick model + effort/budget with a justified cost-latency trade-off, and explain how thinking tokens get billed.

## Learning checklist

- [ ] Reasoning/thinking tokens: generated before (and between) visible output, billed as output
- [ ] Control knobs across providers: `reasoning.effort`, thinking budgets → adaptive effort
- [ ] Serial vs parallel test-time compute (best-of-N chains, verifiers)
- [ ] Latency/cost trade-offs: when extra thinking earns its keep
- [ ] Prompting differences: give goals + constraints; skip "think step by step"
- [ ] Planner/worker routing: reasoning model plans, fast model executes

---

## 1. Purpose of this topic

A reasoning model spends tokens **thinking before it answers**. That single extra
step changes three things an engineer has to budget for:

1. **Billing** — thinking tokens are output tokens, and they usually dwarf the
   visible answer. On the worked example below, hidden thinking is **89.1% of the
   bill**, the visible answer 6.5%, and the input 4.4%.
2. **Latency** — first visible token gets further away as effort rises: 5.4s at
   `none` → 39.5s at `medium` → 551.5s at `max` on the same 300-token answer.
3. **Architecture** — thinking is the raw material of *test-time compute* (TTC):
   you can buy quality by thinking longer (serial) or by drawing more samples and
   verifying (parallel).

Done: you can look at a task, pick model + effort, and defend the cost/latency
trade with numbers instead of vibes — and you can state exactly what you are
billed for when the model thinks.

**Scope:** this topic is about *choosing the knobs*. The engineering of a
reasoning turn inside an agent loop (interleaved thinking between tool calls)
shows up again in Phase 6; the routing half pairs with topic 19c's auto-tiers.

---

## 2. Prerequisites

**Before: Topic 7, Topic 10**

You need:

- Output pricing asymmetry and `$/request` arithmetic (Topic 10)
- Sampling: temperature, top-p, and why best-of-N wants a non-zero temperature
  (Topic 7)
- The cost/latency mindset from retries, timeouts and fallbacks (Topics 19, 19a,
  19c) — thinking is a budget the same way timeouts are

---

## 3. Core concepts

### 3.1 What thinking tokens are

- Generated **internally before** the visible output. With **interleaved
  thinking** the model also thinks *between* visible blocks and tool calls.
- **Not returned as text.** The API gives you the answer; the reasoning itself is
  hidden. What you can get is an optional *summary* (OpenAI
  `reasoning.summary = auto | concise | detailed`; Anthropic can stream
  `thinking` blocks). A summary is a readable artefact, **not** the raw trace.
- They **occupy the context window**. Thinking plus visible output plus input all
  consume the same budget.
- They are **billed as OUTPUT tokens**, never as input.
- The count is exposed in usage:

| Provider | Field |
| --- | --- |
| OpenAI | `usage.output_tokens_details.reasoning_tokens` |
| Anthropic | `usage.output_tokens_details.thinking_tokens` — only on the **final `message_delta`** when streaming |

### 3.2 The knobs

**OpenAI** — an effort ladder plus three modes:

```python
reasoning={"effort": "medium"}     # none < minimal < low < medium < high < xhigh < max
reasoning={"mode": "standard"}     # standard | pro  (pro does more model work, billed at token rates)
reasoning={"summary": "auto"}      # auto | concise | detailed
reasoning={"context": "current_turn"}  # current_turn | all_turns (carry earlier reasoning forward)
```

- Which rungs exist is **model-dependent** (e.g. gpt-5.5 defaults to `medium`;
  some models reject `none`).
- `max_output_tokens` caps **thinking + output together**.
- OpenAI advises reserving roughly **25,000 tokens** for reasoning + output while
  experimenting — otherwise you discover the cap the expensive way (§3.3).
- Persisted reasoning can be reused only **within a model family**; a provider
  fallback (topic 19a) drops encrypted reasoning the target cannot decrypt and
  re-reasons on that turn.

**Anthropic** — either a manual budget or adaptive effort:

```python
# manual extended thinking: you pick the ceiling of the thinking phase
thinking={"type": "enabled", "budget_tokens": 8192}   # min 1024, and less than max_tokens
# adaptive thinking: the model decides whether and how much to think
thinking={"type": "adaptive"}
output_config={"effort": "medium"}                    # low | medium | high | xhigh | max
```

- The manual budget must be **≥ 1024** and **strictly less than `max_tokens`**.
  The exception is **interleaved thinking**, whose budget spans every thinking
  block in one turn and may therefore exceed `max_tokens`.
- The budget is a **target, not a hard cap**: bigger budgets help complex tasks
  with **diminishing returns and more latency**. Budgets above ~32k are a signal
  to use batch processing rather than synchronous calls.
- Interleaved thinking (think between tool calls) is a beta header on older
  models and automatic under adaptive thinking.
- Changing the budget/mode **between turns invalidates the prompt cache** — the
  config is rendered into the prompt, so the prefix changes.
- Adaptive `low` **may skip thinking entirely** on easy input. That is the whole
  point of adaptive: pay nothing when there is nothing to think about.

### 3.3 Billing, and the `max_output_tokens` trap

```text
billed_output = visible_output_tokens + reasoning_tokens      # both at the OUTPUT rate
cost          = input_tokens * input_price + billed_output * output_price
```

Because thinking is spent **first**, a call can burn its whole output budget
thinking and return **no visible text at all**:

```text
status            = incomplete
incomplete_reason = max_output_tokens      (possibly before any visible token)
billed            = input + reasoning      (you pay and get nothing)
```

### 3.4 Serial vs parallel test-time compute

| | Parallel (best-of-N, self-consistency) | Serial (one longer chain) |
| --- | --- | --- |
| Shape | draw **N independent samples**, then pick | one chain: bigger thinking budget, or refine → refine → refine |
| Latency | ≈ **one** sample | grows with every step |
| Cost | ≈ **N ×** | grows with the chain |
| Needs | a **verifier/scorer** to pick a winner | nothing extra |
| Ceiling | raised by a good verifier — **verifier quality is the real limit** | raised by the model's own long-horizon ability |

Two ways to pick a winner in the parallel case:

- **Outcome reward** — score the final answer (rubric, exact-match, unit test).
- **Process reward** — score each step; a `min` aggregate is a checklist, so one
  bad step sinks the sample.

Self-consistency is the same draw-N idea with a *voting* verifier: majority vote
over N samples. It needs no scorer at all, but it only works when the answer is
a discrete thing you can count (a label, a number, a short string) — and it fails
silently when the majority is confidently wrong.

Note the asymmetry in the numbers: best-of-8 at `medium` effort scores **0.9999**
against **0.9627** for a single `high`-effort sample at similar cost. That is the
real lesson — *eight cheap samples plus a verifier* can beat *one expensive
sample*, when you can verify.

### 3.5 When extra thinking earns its keep

- **Earns it:** hard multi-step work that is *checkable* — math, code, deep
  planning, debugging, multi-constraint decisions.
- **Rarely earns it:** classification, simple lookup/retrieval, extraction from a
  known schema, latency-critical chat.
- **Shape of the curve:** costs scale roughly linearly with thinking tokens, TTFT
  grows with them, quality shows **diminishing returns** — the last rung of the
  ladder buys a fraction of the first.
- **The decision procedure:** run evals on **your** traffic. Not the leaderboard,
  not vibes: your prompt set, your quality bar, your p99.

### 3.6 Prompting differences

Reasoning models already think; the prompt's job is to define the *problem*, not
the *process*.

Do:

- Give the **goal**, the **constraints**, and the **success criteria**.
- Provide **context and tools**.
- Ask for a **short preamble** ("open with one sentence on what you are about to
  do") so the first *visible* token lands early while thinking streams behind it.
- Keep using **structured output** contracts — nothing about thinking changes
  Topic 12.

Don't:

- `think step by step` / step-by-step scripts — the model already plans its own
  process; over-scripting can *hurt*.
- Filler incantations like `take a deep breath`.
- Narrating the reasoning you asked for by hand — you would be paying twice
  (thinking and output) for the same tokens.

### 3.7 Planner/worker routing

A reasoning model **plans, decomposes and audits**; a fast cheap model
**executes** the sub-tasks it was handed.

- Route by **turn difficulty and value**: hard or high-value turns → reasoning;
  easy execution → fast.
- The split is serial TTC at the *system* level: one expensive planning turn,
  N cheap execution turns.
- This is the same idea as topic 19c's auto-tiers (`SIMPLE / MEDIUM / COMPLEX /
  REASONING` pools), applied to a single agent loop: the plan turn is a
  `REASONING` call, the execution turns are `SIMPLE` calls.

---

## 4. Design

```python
# knobs + billing ---------------------------------------------------------
class Effort(str, Enum): ...                # none < minimal < low < medium < high < xhigh < max
ADAPTIVE_THINKING_TARGETS: dict[Effort, dict[Difficulty, int]]   # effort x difficulty -> thinking
planned_thinking_tokens(effort, difficulty) -> int               # 0 is a real answer
validate_thinking_budget(budget_tokens, max_tokens, *, interleaved=False) -> None

@dataclass(frozen=True)
class Price: input_per_mtok; output_per_mtok; cached_input_per_mtok

@dataclass(frozen=True)
class Usage: input_tokens; visible_output_tokens; reasoning_tokens
    billed_output_tokens = visible + reasoning
    to_usage_payload(provider, *, streaming, final_delta) -> dict

estimate_cost(usage, price) -> CostBreakdown   # input / visible / reasoning / total

@dataclass(frozen=True)
class CompletionResult: status; visible_text; usage; cost; thought_summary; incomplete_reason
run_completion(...) -> CompletionResult         # thinking first, then visible, capped by max_output_tokens

# test-time compute -------------------------------------------------------
best_of_n(samples, verifier, tie_break=None) -> Selection
majority_vote(samples) -> Selection
parallel_cost(usage, price, n, *, cached_input=True) -> float
serial_cost(usage, price, extra_thinking_tokens) -> float
refine(prompt, steps, *, verifier, improver=None) -> RefineTrace
OutcomeVerifier(rubric) / ProcessVerifier(step_scores, aggregate="min")

# decision support --------------------------------------------------------
@dataclass(frozen=True)
class TaskProfile: name; difficulty; input_tokens; visible_output_tokens; verifiable; latency_sensitive; stakes
estimate(profile, effort, *, model, price, samples=1) -> Estimate(effort, thinking, cost, latency, quality)
choose_effort(profile, *, quality_bar, budget_usd, latency_budget_s, ...) -> EffortChoice

# prompting + routing -----------------------------------------------------
build_reasoning_prompt(goal, constraints, success_criteria, *, context, output_contract, ask_for_preamble)
detect_step_by_step(prompt) / detect_and_strip_step_by_step(prompt)
planner_worker_split(plan_model, worker_model, subtasks, ...) -> RoutingPlan
route_turn(subtask, fast_model, reasoning_model, ...) -> RouteAssignment
```

Two modelling choices worth stating out loud:

1. **Quality is a saturating curve, not a step.** `q = base + (1-base)(1 - e^(-thinking/k))`
   with `base` the no-thinking floor and `k` growing with difficulty. It is a
   *teaching model*: it reproduces the two facts that matter (diminishing returns;
   hard tasks need far more thinking for the same quality) so `choose_effort` has
   something honest to reason over. Real numbers come from evals on your traffic.
2. **Parallel TTC changes quality only when a verifier exists.** `estimate(...,
   samples=N)` raises quality toward 1 only if `profile.verifiable`; without a
   verifier you pay N × for the same quality.

---

## 5. Implementation walkthrough (`reasoning.py`)

- **Effort → thinking.** `ADAPTIVE_THINKING_TARGETS[effort][difficulty]` encodes
  the adaptive semantics: `low` on an easy prompt targets **0** thinking tokens,
  while `max` on a hard prompt targets 131,072. `EFFORT_TO_THINKING_BUDGET` is the
  one-number summary of that table (the medium row) that a config file would use.
- **Manual budget validation.** `validate_thinking_budget(2048, 2048)` raises
  ("budget_tokens < max_tokens"); `validate_thinking_budget(4096, 2048,
  interleaved=True)` passes, because interleaved thinking spans the whole turn.
  The 1024 floor applies to *manual* budgets only — adaptive effort levels may
  target fewer tokens, or none.
- **Billing.** `Usage.billed_output_tokens` is `visible + reasoning`, and
  `estimate_cost` splits the output cost into where it went:

  ```text
  Usage(input=800, visible=300, reasoning=4096), reasoning-small ($0.55 / $2.20 per Mtok)
    billed output = 4396 tokens
    input cost    = 0.00044      output cost = 0.009671
    reasoning     = 0.009011   (89.1% of the 0.010111 total)
    same answer with thinking off = 0.0011   -> thinking is 9.2x the rest of the call
  ```

- **The `max_output_tokens` trap.** `run_completion` spends thinking first and
  returns `status="incomplete"`, `incomplete_reason="max_output_tokens"`,
  `visible_text=""` when 20,000 output tokens are consumed by 30,000 planned
  thinking tokens — and still costs `$0.04455`. `will_fit(...)` and
  `recommended_reserve_warnings(...)` are the cheap pre-flight checks that stop
  you buying empty completions.
- **Usage shapes.** `Usage.to_usage_payload("openai")` nests
  `output_tokens_details.reasoning_tokens`;
  `to_usage_payload("anthropic", streaming=True, final_delta=False)` shows the
  subtlety that the thinking count only lands on the final `message_delta`.
- **Parallel TTC.** `best_of_n(samples, verifier)` picks the highest score and
  falls back to an optional `tie_break` verifier on ties (otherwise the earliest
  sample wins, so the result is reproducible). `majority_vote(samples)` is
  self-consistency with a deterministic tie-break.
  `parallel_cost(usage, price, n)` prices the N samples: the prompt prefix is
  billed once and then read from the cache (`cached_input=True`), while every
  sample pays full output price including its thinking.
- **Serial TTC.** `refine(prompt, steps, verifier=...)` walks one chain and scores
  every version, which is how you *see* diminishing returns:
  `[0.30, 0.70, 0.80, 0.85]` — gains of `+0.40, +0.10, +0.05` from three steps.
  `serial_cost(usage, price, extra_thinking)` prices the other serial option
  (one call, more thinking).
- **Estimator.** For a medium task (in=800, visible=300, `reasoning-small`):

  | effort | thinking | cost | latency | quality |
  | --- | --- | --- | --- | --- |
  | none | 0 | $0.0011 | 5.4s | 0.600 |
  | minimal | 128 | $0.0014 | 6.5s | 0.607 |
  | low | 1,024 | $0.0034 | 13.9s | 0.654 |
  | medium | 4,096 | $0.0101 | 39.5s | 0.777 |
  | high | 16,384 | $0.0371 | 141.9s | 0.961 |
  | xhigh | 32,768 | $0.0732 | 278.5s | 0.996 |
  | max | 65,536 | $0.1453 | 551.5s | 1.000 |

  Read the curve, not the endpoint: `medium → high` buys **+0.18 quality for
  +$0.027**, while `xhigh → max` buys **+0.004 for +$0.072**.

- **Choosing.** `choose_effort(profile, quality_bar=..., budget_usd=...)` walks the
  ladder and returns the **cheapest** effort that clears the bar inside budget and
  latency, with every rung it considered attached for auditing:

  ```text
  classify a ticket, difficulty 0.1, bar 0.80  -> none     (0 thinking)
  debug a race condition, 0.9,     bar 0.90    -> high     32,768 thinking, q 0.963
  extract fields, 0.1, bar 0.87, budget $0.0015 -> max (escalated, met_budget=False)
  ```

  The third line is the honest failure mode: when a budget forbids every rung that
  could clear the bar, you get the highest allowed effort **plus a reason** —
  relax a constraint, move to parallel TTC, or route to a stronger model.

- **Prompting.** `build_reasoning_prompt(goal, constraints, success_criteria)`
  emits `# Goal / # Constraints / # Success criteria / # Output`, asserts its own
  output contains no process-scripting phrase, and asks for a one-sentence
  preamble. `detect_and_strip_step_by_step` shows the repair:

  ```text
  in : "Summarise this invoice. Think step by step. Return JSON."
  out: ("Summarise this invoice. Return JSON.", ["Think step by step."])
  ```

- **Routing.** `planner_worker_split(reasoning_large, fast_small, subtasks)` yields
  plan → (easy → fast, hard → reasoning, high-value → reasoning) → audit, and
  reports `{"plan_model_calls": 4, "worker_model_calls": 1, "total_calls": 5}`.

Run it: `python -m pytest -q` (30 tests) from `implementation/`, or open
`reasoning_demo.ipynb`.

---

## 6. Pitfalls

- **Forgetting thinking is output.** Sizing `max_tokens` off the answer length
  guarantees `status=incomplete` on a thinking model. Budget thinking + answer, or
  reserve ~25k while experimenting.
- **Paying for nothing.** A call that exhausts `max_output_tokens` while thinking
  returns no visible text and still bills input + reasoning. Always check
  `status`/`incomplete_reason` before you use the text.
- **Reading the summary as the reasoning.** Summaries are generated artefacts;
  you cannot rely on them as a faithful trace, and you may be billed for the
  summary tokens too.
- **Assuming the budget is a cap.** Anthropic's `budget_tokens` is a *target*;
  the model may think less. Reasoning about it as a hard limit leads to wrong
  latency estimates.
- **Changing effort between turns.** The config is rendered into the prompt, so
  changing the budget/mode invalidates the prompt cache and re-prices your prefix.
- **Expecting reasoning to survive a fallback.** Encrypted reasoning is not
  portable across providers/families; the fallback re-reasons from scratch.
- **Best-of-N without a verifier.** You pay N × and get one sample's quality back.
  The verifier is the ceiling: a weak scorer makes parallel TTC a cost multiplier.
- **Voting on the wrong thing.** Majority vote needs a countable answer; on
  free-form output it degenerates into "whatever the first sample said".
- **Still saying "think step by step".** On a reasoning model it is at best dead
  weight and can degrade the output; delete the process scripting and state the
  goal, constraints and success criteria instead.
- **Escalating effort to answer a budget question.** If the bar is unreachable
  inside the budget, the fix is a cheaper model, a narrower task, or parallel TTC
  with a verifier — not `max`.

---

## 7. Exercises

1. Add `reasoning.context = all_turns` to `run_completion` and price a three-turn
   conversation where turn 2 and 3 carry turn 1's reasoning forward. Compare with
   re-thinking each turn (cost and latency both).
2. Implement a `RegexVerifier` alongside `OutcomeVerifier` and show best-of-N with
   a *weak* verifier choosing a worse answer than a strong one on the same samples.
3. Extend `estimate` so `samples` costs a *reduced* output price per sample when
   the samples share a cached prefix — then find the N where best-of-N stops being
   cheaper than one higher-effort call.
4. Add `route_turn` confidence: let the fast model attempt a hard turn and escalate
   to the reasoning model when a verifier scores it below a bar (cascade). Compare
   total cost against "reasoning-first".
5. Work through one real prompt of yours: profile it (difficulty, verifiability,
   latency sensitivity), run `choose_effort`, then check the prediction against a
   real call's `usage.output_tokens_details`.

---

## 8. Sources

- OpenAI — reasoning models guide (effort ladder, `mode`, `summary`, `context`,
  `max_output_tokens`, the ~25k experimenting reserve, usage field):
  <https://developers.openai.com/api/docs/guides/reasoning>
- Anthropic — extended thinking (manual `budget_tokens` ≥ 1024 and < `max_tokens`,
  interleaved exception, adaptive `output_config.effort`, cache invalidation,
  >32k → batch): <https://platform.claude.com/docs/en/build-with-claude/extended-thinking>
- Anthropic — visible extended thinking (summaries vs raw reasoning, interleaved
  thinking between tool calls): <https://www.anthropic.com/research/visible-extended-thinking>
- Related: topic 7 (sampling for best-of-N), topic 10 (token cost), topic 12
  (structured output still applies), topic 19a (fallbacks drop reasoning),
  topic 19c (auto-tiers).

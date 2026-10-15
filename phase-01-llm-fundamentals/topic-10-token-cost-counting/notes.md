# Topic 10 — Token Cost and Counting

**Before:** Topic 1 (Tokens), Topic 6 (Your first LLM API call)

## Done When

You **estimate a feature's $/request — including the input/output split — before writing its code.**

That means: given a prompt shape, a conversation length, and a model, you produce a number and a
sentence that defends it.

---

# 1. Why Cost Is an Engineering Topic, Not an Accounting One

Cost is a design constraint that arrives **before** you write the code, exactly like latency or
memory. If you cannot estimate it, you cannot choose between:

* one long prompt vs. two short calls
* a chat model vs. a small model
* sending full history vs. sending a summary
* retrieving 5 chunks vs. 20 chunks

Every one of those decisions is a **price decision dressed up as an architecture decision**.

```text
Design choice  →  token count  →  price  →  feasibility
```

The cost estimate is what turns "this feels expensive" into "this costs $0.004 per request, so
$4 per 1,000 users per day, so we need budgets or a cheaper tier."

---

# 2. The Two-Price Model

Every major provider charges **separately for input and output**, and the two prices are not equal.

```text
cost_per_request = (input_tokens  / 1_000_000) × input_price
                 + (output_tokens / 1_000_000) × output_price
```

Two facts follow immediately:

1. **You must know the split.** "1,000 tokens" is not a price. "900 input, 100 output" is.
2. **Output is usually the expensive side.** Generation is sequential and memory-bound; reading a
   prompt is parallel and cheaper. Output prices are commonly ~3–5× input prices on the same model.

### Illustrative relative structure

| Tier | Relative input price | Relative output price | Typical use |
|------|---------------------|----------------------|-------------|
| Small / mini | 1× | ~4× input | classification, routing, extraction |
| Mid | ~10× | ~40× input | general chat, RAG answers |
| Frontier / reasoning | ~50–150× | ~200–600× input | hard reasoning, agent planning |

Treat the numbers as a *shape*, not a quote. The shape is stable across providers and across time:
**small models are roughly 10–30× cheaper than frontier models, and output costs several times
input within every tier.** That shape is what you memorise and reason with.

> Always read the provider's current pricing page before committing. Prices change; the asymmetry
> between input/output and between tiers does not.

---

# 3. Input Tokens Are Not Just the User's Message

This is the mistake that makes estimates wrong by 3–10×.

```text
input_tokens =
      system prompt
    + tool / function schemas
    + few-shot examples
    + retrieved context (RAG chunks)
    + full conversation history
    + the actual user message      ← usually the SMALLEST part
```

A "one-line question" against a RAG endpoint can easily be:

```text
system prompt         250 tokens
tool schemas          400 tokens
retrieved chunks    3,200 tokens
history               900 tokens
user question          15 tokens
                    ------------
input               4,765 tokens
```

The user typed 15 tokens. You paid for 4,765. **Everything you add to the context is billed on
every single turn.**

---

# 4. Counting Before You Call

Three ways to count, in order of preference for estimation:

1. **`tiktoken` locally** — fast, free, offline. Exact for OpenAI models; a close approximation for
   others (tokenizers differ, but counts are usually within a few percent for English prose).
2. **A provider counting endpoint** — e.g. Anthropic's `messages/count_tokens`, which is exact for
   that provider's model including images and tools.
3. **Character heuristics** — "~4 characters per token" for English. Use only when nothing else is
   available, and never for a number you will defend in an interview.

```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
len(enc.encode("Your prompt text here"))
```

### What the API reports back

Every response carries a usage block you can reconcile against your estimate:

```json
{
  "usage": {
    "prompt_tokens": 4765,
    "completion_tokens": 180,
    "total_tokens": 4945
  }
}
```

Some providers add fields you must not ignore:

* reasoning/thinking tokens — billed as output even though you never see them (Topic 20)
* cached-read tokens — usually ~10% of input price
* cache-write tokens — sometimes **more** than input price
* image/audio tokens, counted in their own modality units

**Rule: log the returned usage per request. Your estimate is only trustworthy once it has been
reconciled against real usage at least once per feature.**

---

# 5. The Estimation Recipe

Do this on paper before writing the feature.

```text
1. Pick the model tier.                        (small / mid / frontier)
2. Write the prompt skeleton.                  (system + examples + tool schemas)
3. Write a REALISTIC request.                  (not the shortest one)
4. Count input tokens.                         (tiktoken or counter endpoint)
5. Estimate output tokens.                     (see below)
6. Apply the two-price formula.
7. Multiply by expected requests/day.          ($/day, $/month)
8. State the sensitivity: what changes the number most?
```

### Estimating output tokens when you don't know yet

| Task shape | Reasonable first guess |
|-----------|------------------------|
| Classification / label | 1–10 tokens |
| Field extraction (JSON) | 30–120 tokens |
| Short answer | 100–250 tokens |
| RAG answer with citations | 200–600 tokens |
| Long-form draft | 800–2,000 tokens |
| Reasoning model on a hard task | add 500–5,000 thinking tokens |

Then **measure once** and replace the guess permanently. Guesses are for the first estimate;
measured medians are for the budget.

---

# 6. Worked Example — RAG Answer Feature

Assume illustrative prices (fill in real ones from the provider page):

```text
input  price: $3.00 / 1M tokens
output price: $15.00 / 1M tokens
```

Feature: "answer a question over our docs."

```text
system prompt + instructions            300
retrieved chunks (8 × ~400)           3,200
conversation history (5 turns)          800
user question                            20
------------------------------------------
input                                 4,320 tokens

expected output (answer + citations)    350 tokens
------------------------------------------
```

```text
input  : 4,320 / 1e6 × $3.00  = $0.012960
output :   350 / 1e6 × $15.00 = $0.005250
                                 ---------
per request                     = $0.018210
```

At 5,000 requests/day:

```text
$0.01821 × 5,000 = $91.05 / day  ≈  $2,730 / month
```

Now the interesting part — **what moves the number?**

| Change | Effect on per-request cost |
|--------|----------------------------|
| Retrieval 8 chunks → 4 chunks | input −1,600 → −$0.0048 → −26% |
| History off (stateless single-turn) | input −800 → −$0.0024 → −13% |
| Output 350 → 150 (tighter instruction) | output −200 → −$0.0030 → −16% |
| Cache the static system prompt (read @10%) | input cost on 300 tokens ×0.9 → −$0.00081 → −4% |
| Move the *answer* to a small tier | total ≈ −91% |

Notice: **the user's 20-token question is irrelevant.** All the money is in context you chose to
send, and in the output length you allowed.

Note the caching row: only the **leading, byte-identical** part of the prompt is cacheable. Here
that is the 300-token system prompt, so the saving is small. Big cache wins need a *large* stable
prefix (a long fixed system prompt plus tool schemas and few-shot examples) sitting in front of
the variable parts — retrieving fresh chunks *before* the stable block destroys the cache.

That is the interview-grade answer: *"about two cents a request, dominated by retrieved context,
barely moved by caching because our cacheable prefix is small, and sensitive to the
output-length ceiling."*

---

# 7. Cost Regressions From Prompt Bloat

Cost does not fail loudly. It drifts.

| Regression | Why it happens | How to catch it |
|-----------|----------------|-----------------|
| System prompt growth | "just one more rule" per sprint | version the prompt; diff token count in CI |
| Few-shot creep | 3 examples → 12 examples | per-example value test, not per-example vibes |
| Tool schema bloat | many unused tools always attached | attach tools per route, not globally |
| History never compacted | full transcript resent every turn | track input tokens vs turn number |
| Retrieval top-k raised | "more context must be better" | measure quality AND cost together |
| Verbose model default | model changes, output doubles | alert on median output tokens |
| Retry storms | 429/5xx handled without caps | bound retries; count retried tokens as cost |

```text
cost_trend = f(median input tokens, median output tokens, requests/day, price)
```

Track those four series. A cost spike is almost never the provider raising prices — it is one of
the rows above.

---

# 8. Thinking in $/Request at Scale

Do the multiplication out loud; it is what separates an engineering answer from a demo answer.

```text
per request     $0.0182
per user/day    × 3 requests      = $0.0546
per 1,000 users × $0.0546         = $54.60 / day
per month (30d)                    ≈ $1,638
```

Then ask the questions that follow automatically:

* What is the **unit economics**? If a user pays $5/month and costs $1.64/month in tokens, the
  margin is workable — but only before retries, evals, and grading calls (which also cost tokens).
* What is the **cap**? A per-key budget or `max_tokens` ceiling turns an unbounded risk into a
  bounded one.
* What is the **cheap path**? Classify the easy 80% with a small model, escalate the hard 20%.
* What is the **hidden** cost? Evals, LLM-as-judge, embeddings, and trace storage are all real
  spend and are usually forgotten in the estimate.

### Caching changes the arithmetic, not the shape

Prompt caching makes a repeated prefix ~10% of input price (read) — sometimes with a write
penalty of ~125% the first time. It only helps the **leading bytes that repeat unchanged**, so
the size of the win equals the size of your stable prefix, and it costs nothing in quality. Put
the fixed block first (system prompt, tool schemas, few-shot examples) and the variable block
last (retrieved chunks, history, question); a service that injects fresh chunks *before* the
stable block has almost nothing cacheable.

---

# 9. Token Counting Is Not the Same Everywhere

| Provider reality | Consequence for your estimate |
|------------------|-------------------------------|
| Different tokenizers | `tiktoken` is an approximation for non-OpenAI models |
| Reasoning tokens billed as output | output estimates double or triple on hard prompts |
| Cache read/write pricing | prefix-heavy workloads price differently from the naive formula |
| Image/audio tokenisation | a "short" multimodal prompt can be thousands of tokens |
| Streaming | output tokens are still counted the same; only latency changes |
| Long-context price tiers | some models charge more above a context threshold |

**Never carry a per-token price from one model to another, or one month to the next.** Carry the
*structure* (input vs output, tier ratio, cache discounts) and look the numbers up.

---

# 10. Cost Hygiene Checklist for a New Feature

```text
[ ] Model tier chosen deliberately, with a stated reason
[ ] Prompt skeleton counted (system + examples + tools)
[ ] Realistic request counted, not a best-case one
[ ] Output ceiling set (max_tokens) and its cost computed
[ ] $/request written down before the first line of code
[ ] × requests/day and × users converted to a daily and monthly figure
[ ] Sensitivity named: which single change moves the number most
[ ] Retry and eval costs included in the budget
[ ] Returned usage logged per request and reconciled against the estimate once
[ ] Alert threshold on median input tokens, median output tokens, and daily spend
```

---

# 11. Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Short question = cheap request" | Context (system, RAG, history, tools) dominates; the question is noise |
| "Input and output cost the same" | Output is typically several times more expensive per token |
| "Caching makes it free" | Cached read ≈ 10% of input price, and writes can exceed normal input price |
| "Reasoning tokens are hidden, so they're free" | They are billed as output |
| "We can optimise cost later" | Model tier and context shape are architectural; retrofitting is expensive |
| "The model was upgraded, so cost is the same" | A newer model can be cheaper *per token* and more expensive *per task* if it's more verbose |
| "tiktoken gives the provider's exact count" | Only for that provider's models; elsewhere it's an estimate |

---

# 12. Interview-Ready Answer

> **Q: "How would you estimate and control the cost of an LLM feature?"**
>
> **A:** "I'd estimate before coding. The cost formula is input tokens at the input price plus output
> tokens at the output price. I count the *whole* input — system prompt, tool schemas, retrieved
> chunks, history — not just the user's message, because context is what dominates. I'd take a
> realistic request, count it with tiktoken or the provider's counting endpoint, estimate the output
> ceiling, and produce a $/request number, then multiply it out to daily and monthly at expected
> volume. I'd name the sensitivity — usually retrieved-context size or the output ceiling. Then I'd
> control it with: a deliberate model tier, prompt caching for the static prefix, fewer/smaller
> retrieved chunks, history compaction, bounded retries, and budgets or per-request caps so a bug
> can't become a bill. Finally I'd log returned usage per request and alert on medians, so prompt
> bloat shows up as a regression instead of a surprise invoice."

---

# 13. What You Should Be Able to Explain Without Notes

1. The **two-price formula** and why the input/output split matters
2. Why **output is usually the expensive side**
3. Why the **user's message is the smallest part** of the input
4. How to count **before** calling (`tiktoken`, counting endpoints, and why heuristics are last resort)
5. How to convert **$/request → $/day → $/month** and state the unit economics
6. Why **prompt caching** changes the arithmetic for repeated prefixes
7. Which **regressions** quietly inflate cost, and which signals catch them

---

# 14. Connection to Other Topics

| Topic | Connection |
|-------|------------|
| 1. Tokens | Counting mechanism; why rare text costs more |
| 3. Context window | Input + output share one budget; output ceiling trade-off |
| 4. Statelessness | History resent each turn = paid each turn |
| 7. Temperature/sampling | `max_tokens` bounds the output side of the bill |
| 9. Prompt engineering | Few-shot examples are a recurring cost, not a one-off |
| 20. Reasoning models | Thinking tokens are billed as output |
| 24/27. Chunking & prompt assembly | Chunk count and size are the biggest input lever |
| 60. Cost monitoring | Per-feature attribution and alert thresholds |
| 60a/60b. Cost optimisation | Cost per completed task, caching, tiering, caps |

---

# 15. Final Mental Model

```text
                    DESIGN
                       │
                       ▼
              count the INPUT
      (system + tools + RAG + history + question)
                       │
                       ▼
             bound the OUTPUT
                  (max_tokens)
                       │
                       ▼
        input×in_price + output×out_price
                       │
                       ▼
                 $/request
                       │
        ┌──────────────┼───────────────┐
        ▼              ▼               ▼
   $/day at       sensitivity     control levers
   real volume    (what moves it) (tier, cache,
                                   top-k, caps)
```

**One sentence to remember:**

> **Cost is a design property you can compute on paper: the money is in the context you send and
> the output you allow, not in the question the user typed.**
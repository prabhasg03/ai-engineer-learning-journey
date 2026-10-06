# Topic 7 — Temperature and Sampling

## 1. The generation decision

An LLM generates text **one token at a time**.

At every generation step, the model receives the tokens generated so far and produces a score for every possible next token.

These scores are called **logits**.

For example, imagine the model is completing:

> "The cat sat on the"

The model might internally produce something conceptually like:

| Candidate token | Logit |
| --------------- | ----: |
| `mat`           |   5.2 |
| `floor`         |   4.1 |
| `chair`         |   2.8 |
| `roof`          |   1.2 |
| `car`           |  -0.5 |

The model has not yet selected a token.

The logits are simply **scores indicating the model's preference among possible next tokens**.

A probability distribution is then created from those scores, normally using **softmax**.

Finally, a decoding/sampling strategy selects the next token.

The simplified pipeline is:

```text
Input/context
      ↓
Transformer
      ↓
Logits
      ↓
Temperature / sampling controls
      ↓
Probability distribution
      ↓
Token selection
      ↓
Next token
      ↓
Add token to context
      ↓
Repeat
```

This process continues until the model reaches a stopping condition.

### Important distinction

Sampling controls do **not** give the model new knowledge.

They change **how the next token is selected from the model's existing probability distribution**.

So:

```text
Temperature ≠ intelligence
Temperature ≠ knowledge
Temperature ≠ correctness
```

Instead:

```text
Temperature = control over the concentration of the next-token distribution
```

---

# 2. Logits

Before understanding temperature, you need to understand logits.

A model's final layer produces one score for every possible token.

Suppose the vocabulary contains 50,000 tokens.

At one generation step, the model produces approximately:

```text
logit(token 1)     = 1.42
logit(token 2)     = 5.71
logit(token 3)     = -0.92
...
logit(token 50000) = 0.37
```

These are **not probabilities**.

They can be:

* positive
* negative
* greater than 1
* less than 0

The important property is their **relative magnitude**.

A higher logit means the model considers that token more likely relative to other candidates.

---

# 3. From logits to probabilities

Softmax converts logits into probabilities.

The formula is:

$$
p_i =
\frac{e^{z_i}}
{\sum_j e^{z_j}}
$$

where:

* \(z_i\) = logit of token \(i\)
* \(e\) = Euler's number
* \(p_i\) = probability assigned to token \(i\)

The probabilities have these properties:

```text
0 ≤ p_i ≤ 1
```

and:

$$
\sum_i p_i = 1
$$

For example:

```text
Token       Probability
------------------------
mat            0.65
floor          0.20
chair          0.10
roof           0.04
car            0.01
```

Now the model can select a token from this distribution.

---

# 4. What is sampling?

**Sampling** means selecting a token from the model's probability distribution.

Suppose:

```text
mat      → 0.65
floor    → 0.20
chair    → 0.10
roof     → 0.04
car      → 0.01
```

If sampling is allowed, the model could select:

```text
mat
```

most of the time, but occasionally:

```text
floor
chair
roof
```

could also be selected.

This is what introduces **variation**.

The important idea is:

> The model does not simply ask "What is the highest-probability token?" in every decoding mode.

Instead, depending on the decoding configuration, it can sample from a modified probability distribution.

---

# 5. Temperature

Temperature modifies the logits **before softmax**.

The formula becomes:

$$
p_i =
\frac{e^{z_i/T}}
{\sum_j e^{z_j/T}}
$$

where:

$$
T > 0
$$

is the temperature.

The key idea:

> Temperature controls how concentrated or flat the probability distribution becomes.

---

# 6. Low temperature

Suppose the logits are:

```text
A = 5
B = 4
C = 2
D = 1
```

At a relatively low temperature, the difference between high and low logits becomes more significant.

The resulting distribution becomes **sharper**.

Conceptually:

```text
A → very high probability
B → moderate probability
C → low probability
D → very low probability
```

Therefore:

> Low temperature makes high-probability tokens dominate more strongly.

This generally produces:

* less variation
* more predictable output
* more conventional responses
* less random sampling

But remember:

```text
Low temperature ≠ correct answer
```

A model can confidently produce a wrong answer.

---

# 7. High temperature

With higher temperature, the differences between logits become less pronounced.

The probability distribution becomes **flatter**.

Conceptually:

```text
A → 0.40
B → 0.30
C → 0.20
D → 0.10
```

instead of something much more concentrated like:

```text
A → 0.90
B → 0.07
C → 0.02
D → 0.01
```

Lower-probability alternatives become more likely.

Therefore:

> Higher temperature increases the possibility of selecting less-probable alternatives.

This can be useful for:

* brainstorming
* creative writing
* alternative ideas
* varied drafts
* ideation

---

# 8. Temperature does not reorder logits

This is an important interview concept.

Suppose:

```text
A = 5
B = 4
C = 2
```

Temperature changes:

```text
5 → 5/T
4 → 4/T
2 → 2/T
```

For positive \(T\), the ordering remains:

```text
A > B > C
```

Therefore:

> Temperature changes the relative probabilities but does not normally change the ranking of the logits.

The highest-logit token remains the highest-logit token.

What changes is **how strongly the distribution favors it**.

---

# 9. Temperature example

Take:

```text
logits = [3, 2, 1, 0]
```

At:

```text
T = 1
```

the logits remain:

```text
[3, 2, 1, 0]
```

At:

```text
T = 0.5
```

they become:

```text
[6, 4, 2, 0]
```

The differences become larger.

Therefore the distribution becomes sharper.

At:

```text
T = 2
```

they become:

```text
[1.5, 1, 0.5, 0]
```

The differences become smaller.

Therefore the distribution becomes flatter.

This gives you the simplest mental model:

```text
Temperature ↓
       ↓
Distribution sharper
       ↓
Top candidates dominate

Temperature ↑
       ↓
Distribution flatter
       ↓
More alternatives become viable
```

---

# 10. Temperature = 0

The formula:

$$
\frac{z_i}{T}
$$

cannot literally use:

```text
T = 0
```

because that would involve division by zero.

Therefore implementations commonly interpret:

```text
temperature = 0
```

as **greedy/argmax decoding**.

That means:

> Select the highest-scoring token instead of performing ordinary temperature-based sampling.

Conceptually:

```text
A → 0.70
B → 0.20
C → 0.08
D → 0.02
```

Greedy decoding chooses:

```text
A
```

because:

```text
argmax(probability) = A
```

---

# 11. Temperature 0 does not guarantee determinism

This is one of the most important points in Topic 7.

A common beginner statement is:

> "Temperature 0 means the output will always be exactly identical."

That is too strong.

A better statement is:

> Temperature 0 is generally greedy and near-deterministic under a fixed serving setup, but it is not a universal reproducibility guarantee.

Why?

### Reason 1 — Hardware/software nondeterminism

Different hardware kernels or numerical operations can sometimes produce tiny differences.

If two candidate tokens have extremely close scores, a tiny numerical difference can potentially affect the selected token.

### Reason 2 — Serving infrastructure

Cloud providers may:

* route requests differently
* update model versions
* change infrastructure
* modify serving configurations
* change kernels or optimizations

Therefore:

```text
temperature = 0
```

does not mean:

```text
permanent identical output across all environments
```

---

# 12. Fixed serving setup

For learning, a more useful statement is:

```text
Temperature 0
        ↓
Greedy decoding
        ↓
Near-deterministic
        ↓
under a fixed model + fixed serving setup
```

If you want reproducibility, you should consider the entire environment:

```text
Model version
+
Prompt
+
Sampling configuration
+
Serving implementation
+
Hardware/software
+
Seed/deterministic settings where supported
```

Even then, guarantees depend on what the provider actually documents.

---

# 13. Why nonzero temperature creates different answers

Suppose:

```text
Token A = 60%
Token B = 30%
Token C = 10%
```

At nonzero temperature, the model can sample:

```text
A
```

but it could also select:

```text
B
```

If the first generated token changes, the context changes.

For example:

### Generation 1

```text
Prompt
 ↓
Token A
 ↓
New context
 ↓
Next distribution
```

### Generation 2

```text
Prompt
 ↓
Token B
 ↓
Different context
 ↓
Different next distribution
```

Therefore the variation can compound.

This is why a small difference early in generation can produce a substantially different final response.

---

# 14. Top-k sampling

Temperature changes probabilities.

Top-k does something different.

> Top-k removes candidates outside the top `k` highest-scoring tokens.

Suppose the model has:

```text
A → 0.40
B → 0.25
C → 0.15
D → 0.10
E → 0.06
F → 0.04
```

If:

```text
top_k = 3
```

we retain:

```text
A
B
C
```

and remove:

```text
D
E
F
```

The remaining probabilities are then conceptually renormalized.

So:

```text
Top-k = candidate-set restriction
```

---

# 15. Top-k's key characteristic

Top-k has a **fixed maximum candidate count**.

For example:

```text
top_k = 10
```

means:

```text
at most 10 candidates
```

are retained.

It does not care directly about cumulative probability mass.

That's what makes it different from top-p.

---

# 16. Top-p / nucleus sampling

Top-p works using cumulative probability.

Suppose the distribution is:

```text
A → 0.50
B → 0.25
C → 0.12
D → 0.08
E → 0.03
F → 0.02
```

Set:

```text
top_p = 0.80
```

Start from the highest-probability tokens:

```text
A = 0.50
A+B = 0.75
A+B+C = 0.87
```

The smallest set reaching the target probability mass contains:

```text
A
B
C
```

So the candidate set becomes:

```text
[A, B, C]
```

The exact boundary behavior depends on implementation details, but the core idea is:

> Top-p keeps the smallest high-probability candidate set whose cumulative probability reaches the chosen probability mass.

---

# 17. Top-k vs top-p

This distinction is extremely important.

| Property                      | Top-k                | Top-p                                    |
| ----------------------------- | -------------------- | ---------------------------------------- |
| Basis                         | Number of candidates | Probability mass                         |
| Candidate count               | Fixed maximum        | Variable                                 |
| Example                       | Keep top 10          | Keep candidates covering 95% probability |
| Adapts to distribution shape? | Less                 | More                                     |
| Main purpose                  | Crop candidate set   | Crop candidate set                       |

Mental model:

```text
TOP-K
"What are the K best candidates?"

TOP-P
"How many candidates do I need to cover P probability mass?"
```

---

# 18. Temperature vs top-k/top-p

These controls should not be treated as interchangeable.

### Temperature

Changes:

```text
relative probability
```

It does not directly remove candidates.

### Top-k

Changes:

```text
candidate set
```

by keeping the top `k`.

### Top-p

Changes:

```text
candidate set
```

based on cumulative probability.

Therefore:

```text
Temperature
    ↓
reshape distribution

Top-k / Top-p
    ↓
crop distribution
```

---

# 19. Example of the difference

Imagine:

```text
A  0.50
B  0.25
C  0.12
D  0.08
E  0.03
F  0.02
```

### Temperature

Temperature might transform this into something like:

```text
A  0.65
B  0.20
C  0.08
D  0.04
E  0.02
F  0.01
```

All candidates still exist.

### Top-k = 3

```text
A
B
C
```

D/E/F are removed.

### Top-p = 0.80

Potentially:

```text
A + B = 0.75
A + B + C = 0.87
```

so A/B/C become the retained set.

The exact probabilities are renormalized after filtering.

---

# 20. Don't stack sampling controls blindly

A common beginner mistake is:

```json
{
  "temperature": 0.9,
  "top_k": 10,
  "top_p": 0.7
}
```

and then asking:

> "Why did this configuration behave differently?"

You may not understand which control caused which effect.

Your learning strategy should therefore be:

```text
First:
temperature alone

Then:
top-k alone

Then:
top-p alone

Then:
combined controls
```

Only combine parameters once you understand each one independently.

---

# 21. Sampling settings by task

The settings in your syllabus are **starting points**, not universal rules.

## Ideation

Starting point:

```text
temperature ≈ 0.7–1.0
```

Optionally:

```text
top-p
```

Why?

Because multiple plausible answers are useful.

Example:

> Give 10 names for an AI startup.

You don't necessarily want the same obvious answer every time.

---

# 22. Extraction and classification

Starting point:

```text
temperature ≈ 0–0.2
```

Why?

Because extraction/classification generally benefits from:

* consistency
* predictable formatting
* fewer unnecessary alternatives

Example:

```text
Invoice:
INV-2026-1042
```

You don't want the model randomly inventing alternative formats.

But remember:

```text
low temperature ≠ guaranteed correctness
```

You still need:

```text
schema validation
+
business validation
+
possibly deterministic post-processing
```

---

# 23. Code generation

Starting point:

```text
temperature ≈ 0–0.3
```

Why?

You generally want:

* conventional implementations
* consistency
* fewer unnecessary variations

But sampling settings are not a substitute for testing.

The actual engineering pipeline should be:

```text
LLM generates code
        ↓
Compile
        ↓
Run tests
        ↓
Check static analysis
        ↓
Review
```

not:

```text
temperature = 0
        ↓
Trust code
```

---

# 24. Unique-answer tasks

Suppose the question is:

> What is the capital of France?

You generally don't need much randomness.

A high-temperature response could potentially introduce unnecessary variation or mistakes.

Therefore:

```text
Unique / constrained answer
        ↓
lower randomness
        ↓
validate result
```

---

# 25. Creative tasks

Suppose:

> Give me 20 unusual sci-fi planet names.

Now diversity is useful.

You may intentionally allow:

```text
higher temperature
```

because:

```text
variation = useful
```

The key principle is:

> Sampling settings should be selected based on the objective of the task.

---

# 26. Temperature is not a "truth setting"

This deserves special emphasis.

A common misconception is:

```text
temperature = 0
        ↓
correct answer
```

This is false.

Temperature controls **selection variability**.

It does not verify facts.

For example, if the model's probability distribution strongly favors a hallucinated answer:

```text
Hallucination = highest-probability token sequence
```

then:

```text
temperature = 0
```

can consistently produce the hallucination.

Therefore:

```text
Temperature
≠ factuality
```

---

# 27. Sampling does not change model knowledge

Suppose the model learned:

```text
A = likely continuation
B = alternative continuation
```

Changing temperature doesn't teach it something new.

Instead:

```text
Model knowledge
       ↓
Logits
       ↓
Sampling configuration
       ↓
Selected token
```

Therefore:

> Sampling controls affect decoding, not the underlying learned knowledge.

---

# 28. API parameters

Sampling settings belong in the **request JSON body**.

They are not HTTP headers.

Conceptually:

```http
POST /v1/chat/completions

Content-Type: application/json
```

Body:

```json
{
  "model": "<model>",
  "messages": [
    {
      "role": "user",
      "content": "Suggest names for a plant shop."
    }
  ],
  "temperature": 0.8,
  "top_p": 0.95
}
```

Notice:

```text
Content-Type
```

is an HTTP header.

While:

```text
temperature
top_p
top_k
```

are request-body parameters.

---

# 29. OpenAI parameter mapping

According to your supplied Topic 7 material:

OpenAI Chat Completions exposes:

```text
temperature
top_p
```

as top-level JSON body fields.

Your material states:

```text
top_k is not a standard Chat Completions sampling field
```

Therefore you should not blindly copy:

```json
"top_k": 20
```

from another provider into an OpenAI Chat Completions request.

Always check the endpoint/model documentation.

---

# 30. Anthropic parameter mapping

According to your supplied material, Anthropic Messages exposes:

```text
temperature
top_p
top_k
```

as top-level JSON body fields.

Your notes also specifically warn that Anthropic documents constraints on combining sampling controls.

Therefore:

> Don't assume that parameters from one provider can be copied unchanged into another provider.

---

# 31. Provider APIs are contracts

This is an important connection to Topic 6.

In Topic 6, you learned:

```text
endpoint
headers
authentication
JSON body
response
errors
```

Topic 7 adds:

```text
sampling parameters
```

These are part of the API contract.

For every provider, verify:

```text
What parameters exist?
What are their types?
What values are allowed?
Can they be combined?
Does this model support them?
What endpoint supports them?
```

Don't rely on memory.

---

# 32. Your local Qwen setup

Your current learning environment is:

```text
Python
   ↓
raw HTTP
   ↓
127.0.0.1:8080
   ↓
llama-server
   ↓
Qwen3-4B Q4_K_M
```

Therefore your Topic 7 request looks conceptually like:

```json
{
  "model": "Qwen/Qwen3-4B-GGUF:Q4_K_M",
  "messages": [
    {
      "role": "user",
      "content": "Give three different names for a plant shop."
    }
  ],
  "temperature": 0.8,
  "max_tokens": 150
}
```

This is particularly useful because you can experiment repeatedly without paying for API calls.

---

# 33. What you should observe experimentally

Don't just run the notebook.

Record observations.

For example:

| Temperature | Output diversity | Consistency | Observation       |
| ----------: | ---------------- | ----------- | ----------------- |
|         0.0 | Low              | High        | Greedy-like       |
|         0.2 | Low              | High        | Conservative      |
|         0.7 | Moderate         | Moderate    | More variation    |
|         1.0 | Higher           | Lower       | More alternatives |

These are **observations**, not guaranteed universal behavior.

Your actual Qwen setup is what you should report.

---

# 34. A better experiment

Use exactly the same prompt:

```text
Give one unusual name for a plant shop.
```

Run:

```text
T = 0.0
T = 0.2
T = 0.7
T = 1.0
```

Then repeat each five times.

Record:

```text
temperature
run number
output
```

For example:

```text
0.0
Run 1 → ...
Run 2 → ...
Run 3 → ...
Run 4 → ...
Run 5 → ...

0.7
Run 1 → ...
Run 2 → ...
Run 3 → ...
Run 4 → ...
Run 5 → ...
```

Then count:

```text
number of unique outputs
```

That gives you an actual empirical understanding of temperature.

---

# 35. Experiment: top-k

Keep:

```text
temperature = 0.8
```

constant.

Change:

```text
top_k = 5
top_k = 20
top_k = 50
```

Observe:

```text
output diversity
```

The important question isn't:

> "Which number is best?"

Instead ask:

> "What changed when I restricted the candidate set?"

---

# 36. Experiment: top-p

Keep:

```text
temperature = 0.8
```

constant.

Try:

```text
top_p = 0.5
top_p = 0.8
top_p = 0.95
top_p = 1.0
```

Observe how output behavior changes.

Again, the goal is not to memorize:

```text
0.95 = best
```

The goal is understanding:

```text
top_p = probability-mass-based candidate filtering
```

---

# 37. Three controls in one mental model

Think of generation as a funnel.

### Without filtering

```text
10,000 possible tokens
        ↓
Probability distribution
        ↓
Sampling
```

### Temperature

```text
10,000 candidates
        ↓
Reshape probability concentration
        ↓
Sampling
```

### Top-k

```text
10,000 candidates
        ↓
Keep top K
        ↓
Renormalize
        ↓
Sampling
```

### Top-p

```text
10,000 candidates
        ↓
Keep candidates covering P probability mass
        ↓
Renormalize
        ↓
Sampling
```

This is probably the most useful mental model for interviews.

---

# 38. Common misconceptions

### Misconception 1

> Higher temperature makes the model smarter.

False.

It changes sampling behavior.

---

### Misconception 2

> Temperature 0 guarantees identical answers forever.

False.

It is generally greedy/near-deterministic under a fixed serving setup.

---

### Misconception 3

> Temperature controls hallucinations directly.

Not reliably.

Lower temperature can reduce variation, but it doesn't guarantee factuality.

---

### Misconception 4

> Top-k and top-p are the same thing.

No.

```text
Top-k → number of candidates
Top-p → probability mass
```

---

### Misconception 5

> Temperature removes tokens.

No.

Temperature primarily reshapes probabilities.

Top-k/top-p are the candidate-cropping mechanisms.

---

### Misconception 6

> Temperature 0 means "the model thinks harder."

No.

It is a decoding strategy, not an intelligence setting.

---

### Misconception 7

> Lower temperature means better answers.

Not universally.

It means less sampling variability.

---

# 39. Practical decision framework

When choosing sampling settings, ask:

### Question 1

Does the task need multiple valid alternatives?

If yes:

```text
more sampling diversity
```

may help.

### Question 2

Does the task have a unique or highly constrained answer?

If yes:

```text
lower variability
```

is often preferable.

### Question 3

Can the output be automatically validated?

If yes:

```text
sampling + validation
```

is stronger than relying on sampling alone.

---

# 40. Engineering perspective

In a real AI application, you shouldn't simply write:

```python
temperature = 0.7
```

and forget about it.

You should evaluate:

```text
Prompt
+
Model
+
Sampling configuration
+
Output constraints
+
Validation
+
Evaluation dataset
```

For example:

```text
100 representative prompts
        ↓
Run temperature 0.1
        ↓
Evaluate
        ↓
Run temperature 0.7
        ↓
Evaluate
        ↓
Compare
```

Metrics might include:

```text
accuracy
format validity
task success
latency
token usage
cost
failure rate
```

Therefore sampling is an **engineering parameter**, not merely a creative-writing knob.

---

# 41. Interview-ready answer

If an interviewer asks:

> What is temperature in an LLM?

Answer:

> **Temperature rescales the model's logits before softmax. A lower temperature makes the probability distribution sharper, so high-probability tokens dominate more strongly, while a higher temperature flattens the distribution and increases the chance of lower-probability alternatives. Temperature changes the selection behavior rather than the model's underlying knowledge, and temperature zero is generally implemented as greedy decoding rather than literal division by zero.**

If asked about top-k:

> **Top-k sampling restricts generation to the k highest-scoring candidate tokens and samples from that reduced set.**

If asked about top-p:

> **Top-p, or nucleus sampling, keeps the smallest high-probability candidate set whose cumulative probability reaches a specified probability mass, so the number of candidates can vary with the distribution.**

If asked about the difference:

> **Temperature reshapes the probability distribution, while top-k and top-p crop the candidate set. Top-k uses a candidate-count limit, whereas top-p uses a cumulative-probability threshold.**

---

# 42. The four things you absolutely need to remember

If you forget everything else from Topic 7, remember these:

### 1. Temperature

```text
Temperature ↓
→ sharper distribution
→ less variation

Temperature ↑
→ flatter distribution
→ more variation
```

### 2. Top-k

```text
Keep K candidates.
```

### 3. Top-p

```text
Keep candidates covering P probability mass.
```

### 4. Temperature 0

```text
Usually greedy/argmax
≠ universal determinism guarantee
```

---

# 43. Topic 7 final mental model

Put the whole topic together:

```text
                    LLM
                     │
                     ▼
                   Logits
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
     Temperature          Candidate filtering
          │                ┌──────┴──────┐
          │                │             │
          │              Top-k         Top-p
          │                │             │
          └────────────────┴─────────────┘
                           │
                           ▼
                 Modified distribution
                           │
                           ▼
                        Sampling
                           │
                           ▼
                    Selected token
                           │
                           ▼
                    Add to context
                           │
                           ▼
                     Repeat
```

The central distinction is:

> **Temperature changes how probability mass is distributed; top-k and top-p determine which candidates remain available for sampling.**

And the engineering principle is:

> **Choose sampling settings according to the task, then validate the output independently.**
# Topic 2 — Next-Token Prediction

## 1. What this topic is really about

The central idea is extremely simple:

> **An autoregressive language model repeatedly predicts what token should come next, appends that token to the sequence, and predicts again.**

That's the mechanism you need to understand before studying:

```text
Tokens
  ↓
Next-token prediction
  ↓
Context window
  ↓
Temperature / sampling
  ↓
Hallucination
  ↓
Prompt engineering
```

Your syllabus's four required boxes are:

1. The single mechanism: distribution → sample → append → repeat
2. Autoregression
3. Why confident wrongness, verbosity, and losing the thread follow from the loop
4. Training objective vs inference behavior — **one line only** for now. 

---

# 2. The fundamental problem

Suppose the model receives:

```text
The capital of France is
```

What should it output?

Intuitively:

```text
Paris
```

But mechanically, the model isn't directly thinking:

> "I know the answer is Paris."

Instead, its job during generation is to produce a **probability distribution over possible next tokens**.

Conceptually:

```text
The capital of France is
             ↓
        model
             ↓
┌──────────────────────────┐
│ Paris       0.92         │
│ London      0.01         │
│ Berlin      0.01         │
│ located     0.003        │
│ ...                      │
└──────────────────────────┘
```

The exact probabilities are illustrative, not actual model probabilities.

The important idea is:

> **At each generation step, the model assigns probabilities to possible next tokens.**

---

# 3. Token, not word

Topic 1 established that the model works with tokens.

So don't think:

```text
"The capital of France is Paris"
```

as:

```text
word → word → word → word → word
```

Think:

```text
token₁ → token₂ → token₃ → token₄ → token₅ → ...
```

Depending on the tokenizer, a word may consist of multiple tokens.

Therefore:

> **Next-token prediction means next-token prediction, not next-word prediction.**

This distinction matters throughout the rest of the curriculum.

---

# 4. The entire generation loop

This is the most important thing to memorize.

Suppose the initial prompt is:

```text
The cat sat on the
```

The model predicts the next token.

Maybe:

```text
mat → 0.70
floor → 0.10
chair → 0.05
...
```

Suppose `mat` is selected.

Now the sequence becomes:

```text
The cat sat on the mat
```

The model runs again.

It predicts the next token:

```text
because → ...
and → ...
. → ...
...
```

Suppose:

```text
.
```

is selected.

Now:

```text
The cat sat on the mat.
```

Again:

```text
The cat sat on the mat.
 ↓
model
 ↓
It → ...
The → ...
This → ...
...
```

And so on.

So the complete loop is:

```text
                ┌──────────────────────┐
                │                      │
                ▼                      │
             Context                  │
                │                      │
                ▼                      │
             Model                    │
                │                      │
                ▼                      │
     Probability distribution         │
                │                      │
                ▼                      │
        Select next token              │
                │                      │
                ▼                      │
       Append token to context ────────┘
```

This is **autoregressive generation**.

---

# 5. What does "distribution" mean?

Suppose the vocabulary contains 50,000 possible tokens.

The model produces a score for each possible next token.

Conceptually:

```text
token       probability
-----------------------
"The"          0.12
"Paris"        0.08
"cat"          0.04
"because"      0.03
"."            0.02
...
```

All possible next tokens have some associated probability after normalization.

The probabilities approximately satisfy:

```text
P(token₁) + P(token₂) + ... + P(token_N) = 1
```

where `N` is the vocabulary size.

The model isn't choosing from:

```text
true / false
```

It is producing a distribution over many possible continuations.

---

# 6. The next-token prediction equation

You don't need advanced mathematics here.

Just understand this notation:

$$
P(x_{t+1}\mid x_1,x_2,\dots,x_t)
$$

It means:

> Probability of the next token given all previous tokens.

For example:

$$
P(\text{Paris} \mid \text{The capital of France is})
$$

The model is estimating this conditional distribution.

Then:

$$
x_{t+1} \sim P(x_{t+1}\mid x_1,\dots,x_t)
$$

means the next token is selected according to that distribution.

You don't need to derive how the neural network produces this distribution yet.

That belongs much later.

---

# 7. Autoregression

## Definition

**Autoregressive generation** means that generated output becomes part of the input for the next prediction.

Example:

```text
Initial context:

I went to the

        ↓

predict

        ↓

store

        ↓

I went to the store

        ↓

predict

        ↓

yesterday

        ↓

I went to the store yesterday

        ↓

predict

        ↓

...
```

The model continuously feeds its own generated tokens back into the sequence.

---

# 8. Why this is called "autoregressive"

Break down the word:

```text
auto
=
itself

regressive
=
depends on previous values
```

In practical LLM terms:

> The model generates a value and then uses that generated value as part of the context for generating the next value.

So:

```text
x₁ → x₂ → x₃ → x₄ → x₅
```

becomes:

```text
x₁
 ↓
predict x₂
 ↓
x₁ x₂
 ↓
predict x₃
 ↓
x₁ x₂ x₃
 ↓
predict x₄
```

---

# 9. Why generation happens one token at a time

This is a subtle but important point.

Suppose you ask:

> Write a sentence about a dog.

The model doesn't inherently produce the entire sentence as one atomic prediction.

Conceptually:

```text
Write a sentence about a dog
             ↓
            "The"
             ↓
"The"
             ↓
           "dog"
             ↓
"The dog"
             ↓
          "ran"
             ↓
"The dog ran"
             ↓
          "quickly"
             ↓
"The dog ran quickly"
```

Every new token is conditioned on the sequence available at that point.

---

# 10. The model doesn't "see the future"

Suppose the final output is:

```text
The dog ran quickly across the field.
```

When predicting:

```text
The dog ran
```

the model doesn't get to condition that prediction on:

```text
quickly across the field
```

The future tokens haven't been generated yet.

Generation proceeds left-to-right:

```text
The
 ↓
dog
 ↓
ran
 ↓
quickly
 ↓
across
 ↓
the
 ↓
field
```

This is fundamental to autoregressive generation.

---

# 11. A useful mental model

Don't imagine:

```text
LLM
 ↓
thinks
 ↓
writes answer
```

For this topic, use:

```text
context
   ↓
probability distribution
   ↓
next token
   ↓
new context
   ↓
probability distribution
   ↓
next token
   ↓
...
```

That's the mental model your syllabus wants you to internalize.

---

# 12. Where does "knowledge" appear?

This is where people often misunderstand LLMs.

Suppose:

```text
The capital of France is
```

produces a very high probability for:

```text
Paris
```

You can say:

> The model has learned statistical patterns that make `Paris` highly probable in this context.

But be careful with the wording.

At this stage, don't turn that into:

> "The model searches its database and retrieves Paris."

That's not the mechanism you're learning here.

The model produces a probability distribution conditioned on the current token sequence.

---

# 13. Why the model can continue a sentence

Consider:

```text
I poured the coffee into the
```

Possible continuations include:

```text
cup
machine
sink
...
```

The context strongly influences the distribution.

Compare:

```text
I poured the coffee into the
```

with:

```text
I parked the car in the
```

The likely next-token distributions are different because the contexts are different.

So:

```text
same model
+
different context
=
different next-token distribution
```

---

# 14. Context determines the prediction

Consider:

```text
The bank approved my
```

Possible continuation:

```text
loan
```

Now:

```text
I sat beside the
```

Possible continuation:

```text
bank
```

The token `bank` can have very different probabilities depending on its surrounding context.

This is why you should think:

> **The model predicts the next token conditioned on the preceding context.**

Not:

> "The model assigns one fixed meaning to every word."

---

# 15. One token can change everything

Suppose the context is:

```text
The trophy doesn't fit in the suitcase because it is
```

The next-token distribution depends heavily on the preceding sequence.

Now change:

```text
The trophy doesn't fit in the suitcase because the suitcase is
```

The likely continuation changes.

This demonstrates:

```text
small context change
       ↓
different probability distribution
       ↓
different continuation
```

---

# 16. The probability distribution changes every step

This is important.

You don't get one probability distribution for the whole answer.

You get a new distribution at every generation step.

Example:

```text
Prompt:
"The dog"

Step 1:
P(next token | "The dog")

        ↓ selected "ran"

Step 2:
P(next token | "The dog ran")

        ↓ selected "across"

Step 3:
P(next token | "The dog ran across")

        ↓ selected "the"

Step 4:
P(next token | "The dog ran across the")
```

So:

$$
P(x_3|x_1,x_2)
$$

is different from:

$$
P(x_4|x_1,x_2,x_3)
$$

because the context has changed.

---

# 17. Why confident wrong answers are possible

This is one of your syllabus's explicit requirements.

Your syllabus says you should explain **confident wrongness purely from next-token mechanics**, without relying on the words "bug" or "bad model." 

The key is:

> **A language model's generation mechanism selects plausible continuations; plausibility and factual truth are not identical.**

Consider:

```text
The inventor of the fictional technology X was
```

If the model has encountered many textual patterns around something similar, it may produce a highly plausible continuation.

But:

```text
high probability
≠
guaranteed truth
```

The model can therefore generate:

```text
fluent
coherent
specific
confident
```

text that isn't factually correct.

---

# 18. Why confidence can be misleading

Imagine the distribution is:

```text
Candidate A    0.80
Candidate B    0.10
Candidate C    0.05
Others         0.05
```

The model strongly prefers A.

That tells you:

> A is highly probable according to the model under this context.

It does **not** logically prove:

> A is true in the external world.

This distinction becomes the foundation for Topic 8 — hallucination.

For Topic 2, don't go too deeply into mitigation yet.

---

# 19. Why the model can be confidently wrong

Consider a fictional prompt:

```text
The Nobel Prize in Quantum Sandwich Engineering was awarded to
```

The model may still continue the sentence.

Why?

Because the generation mechanism doesn't first perform:

```text
Does this entity actually exist?
```

and only then generate.

Instead, it generates a continuation based on the learned distribution.

So:

```text
linguistic plausibility
        ↓
next-token probability
```

can produce a fluent continuation even when the premise is false.

---

# 20. Why models can be verbose

Your syllabus specifically asks you to explain verbosity from the next-token mechanism. 

Suppose the model has generated:

```text
Here is the answer:
```

Several continuation patterns may have high probability:

```text
First, ...
Another important point is ...
Additionally, ...
It is worth noting that ...
Finally, ...
```

Once one such continuation is generated, it becomes part of the context.

Then that new context can make another explanatory continuation likely.

So you can get:

```text
answer
 ↓
explanation
 ↓
additional explanation
 ↓
example
 ↓
another example
 ↓
summary
 ↓
conclusion
```

The model doesn't necessarily have a separate internal instruction:

> "I should waste 800 words."

Rather, the autoregressive process can keep finding plausible continuation tokens that extend the response.

---

# 21. Why one generated sentence can lead to another

Suppose:

```text
Artificial intelligence is changing software development.
```

The next likely tokens may produce:

```text
One important area is...
```

Then:

```text
One important area is developer productivity.
```

Now the newly generated phrase itself influences what comes next:

```text
This includes...
```

Then:

```text
This includes code generation...
```

And so on.

The model is continuously conditioning on its own output.

That creates a feedback-like chain:

```text
previous context
      ↓
generated token
      ↓
new context
      ↓
new prediction
      ↓
generated token
      ↓
new context
      ↓
...
```

---

# 22. Why losing the thread can happen

Again, stay within the syllabus.

Suppose the conversation contains:

```text
A
B
C
D
E
F
G
H
```

The model predicts the next token based on the context available to it.

If an important detail becomes less useful relative to the enormous amount of surrounding context, the resulting probability distribution may not strongly preserve that earlier detail.

More importantly, once generation begins, **the model's own generated tokens become part of the sequence**.

If the generation drifts:

```text
original topic
      ↓
related topic
      ↓
another related topic
      ↓
new framing
      ↓
further continuation
```

the subsequent predictions are now conditioned on the new trajectory.

So an early deviation can influence later output.

---

# 23. Error propagation

This is one of the most important consequences of autoregression.

Suppose:

```text
Step 1 → correct
Step 2 → correct
Step 3 → slightly wrong
Step 4 → based on Step 3
Step 5 → based on Step 4
Step 6 → based on previous output
```

The model isn't automatically returning to Step 3 and correcting it.

Instead:

```text
wrong generated token
        ↓
becomes context
        ↓
influences next prediction
        ↓
may create further divergence
```

This is one reason generation can drift.

---

# 24. The difference between generation and search

Don't confuse:

```text
next-token generation
```

with:

```text
search through all possible answers
```

The model is generating sequentially.

Conceptually:

```text
A
├── B
│   ├── C
│   └── D
└── E
    ├── F
    └── G
```

There could be an enormous number of possible sequences.

A normal generation process doesn't exhaustively enumerate all possible complete answers.

It repeatedly selects tokens according to the configured decoding strategy.

Sampling details are the subject of **Topic 7 — Temperature and sampling**.

For Topic 2, just understand that a next-token probability distribution exists and a token is selected from it.

---

# 25. Greedy selection

A simple conceptual strategy is:

> Always choose the highest-probability next token.

Suppose:

```text
A → 0.60
B → 0.25
C → 0.10
D → 0.05
```

Greedy decoding chooses:

```text
A
```

Then the context changes and a new distribution is produced.

Again:

```text
distribution 1
→ choose A

new context
→ distribution 2

choose next token

new context
→ distribution 3
```

Don't confuse this with the general generation mechanism.

**Greedy decoding is one possible way of selecting the token.**

---

# 26. Sampling

Another approach is to sample according to the distribution.

For example:

```text
A → 0.60
B → 0.25
C → 0.10
D → 0.05
```

A sampling process can select:

```text
A
```

but it can also select:

```text
B
```

or:

```text
C
```

with corresponding probabilities.

This creates variation between generations.

**Detailed temperature/top-p/top-k behavior belongs to Topic 7.**

---

# 27. Why the same prompt can produce different answers

Suppose:

```text
Prompt:
Write a short story about a robot.
```

At some step:

```text
robot → 0.45
machine → 0.30
android → 0.15
system → 0.10
```

A sampling-based decoder could select different tokens on different runs.

Once the first token changes:

```text
Prompt + token A
```

and:

```text
Prompt + token B
```

are different contexts.

Therefore the next probability distributions can also differ.

This produces a cascading effect:

```text
different token
      ↓
different context
      ↓
different distribution
      ↓
different token
      ↓
different context
      ↓
increasingly different generation
```

---

# 28. The autoregressive feedback loop

This deserves to be memorized visually:

```text
               ┌─────────────────────────────┐
               │                             │
               ▼                             │
          Current context                   │
               │                             │
               ▼                             │
       Next-token distribution               │
               │                             │
               ▼                             │
       Token selection                       │
               │                             │
               ▼                             │
       Append selected token ────────────────┘
```

In one sentence:

> **Predict → select → append → repeat.**

That is the core of Topic 2.

---

# 29. What happens at the end?

Generation continues until some stopping condition is reached.

Conceptually, this could be:

```text
stop token
```

or a configured output limit / other generation constraint.

So:

```text
prompt
 ↓
token
 ↓
token
 ↓
token
 ↓
...
 ↓
stop
```

You don't need API-specific stopping details yet.

---

# 30. Training objective vs inference

Your syllabus explicitly says:

> Training objective vs inference behaviour — one line only; depth lands in topic 65. 

So memorize only this:

> **During training, the model learns to predict the next token from preceding tokens; during inference, it uses those learned patterns to generate tokens sequentially.**

That's enough for Topic 2.

Do **not** dive into:

* backpropagation
* gradients
* cross-entropy derivation
* Transformer architecture
* attention
* optimizer mechanics
* parameter updates

Those belong later.

---

# 31. Training vs inference — simple example

Imagine training text:

```text
The cat sat on the mat.
```

Training exposes the model to relationships like:

```text
The
↓
cat

The cat
↓
sat

The cat sat
↓
on

The cat sat on
↓
the

The cat sat on the
↓
mat
```

The model learns patterns that help predict the next token.

At inference time, given:

```text
The cat sat on the
```

it generates a continuation.

That's the only level you need now.

---

# 32. What the model actually outputs internally

Eventually, you'll hear:

```text
logits
```

and:

```text
softmax
```

You should know the basic vocabulary, but **don't study the internals deeply in Topic 2**.

Conceptually:

```text
context
   ↓
model
   ↓
scores for vocabulary tokens
   ↓
probability distribution
   ↓
token selection
```

Later, Topic 66–67 will explain the Transformer and attention mechanisms underneath this process.

---

# 33. Tokens → probabilities → tokens

The entire process can therefore be represented as:

```text
Token IDs
   ↓
LLM
   ↓
scores/probabilities
   ↓
select token ID
   ↓
append token ID
   ↓
LLM again
```

Notice something important:

> The model operates on **token IDs**, not raw text.

Topic 1 taught you how text becomes tokens.

Topic 2 teaches you what happens **after the model has the token sequence**.

---

# 34. Connecting Topic 1 and Topic 2

You should be able to explain:

```text
Topic 1
Text
 ↓
Tokenizer
 ↓
Token IDs

Topic 2
Token IDs
 ↓
Next-token prediction
 ↓
New token ID
 ↓
Append
 ↓
Predict again
```

Together:

```text
                 ┌──────────────────┐
                 │                  │
Text → Tokenizer → Context → Model  │
                 │        ↑         │
                 │        │         │
                 └── new token ────┘
```

This is the beginning of the complete LLM pipeline.

---

# 35. Example: generating a sentence

Prompt:

```text
The weather today is
```

Suppose the model produces:

```text
beautiful
```

Now:

```text
The weather today is beautiful
```

Next:

```text
and
```

Now:

```text
The weather today is beautiful and
```

Next:

```text
sunny
```

Now:

```text
The weather today is beautiful and sunny
```

Next:

```text
.
```

Now:

```text
The weather today is beautiful and sunny.
```

Conceptually:

```text
Step 0:
The weather today is

Step 1:
The weather today is beautiful

Step 2:
The weather today is beautiful and

Step 3:
The weather today is beautiful and sunny

Step 4:
The weather today is beautiful and sunny.
```

Every step is a new next-token prediction.

---

# 36. Why tokenization matters to prediction

Topic 1 and Topic 2 are connected.

Suppose:

```text
"playing"
```

is represented by several tokens in some tokenizer.

The model predicts **those token units**, not the entire English word as one indivisible object.

So:

```text
text
 ↓
tokens
 ↓
next-token prediction
```

The tokenizer determines the units that the model predicts.

---

# 37. Why "next-token prediction" sounds deceptively simple

The algorithm is simple:

```text
predict
append
repeat
```

But the model's learned probability distribution can be extremely complex.

That distinction is important:

```text
generation algorithm
=
simple loop

prediction function
=
complex learned model
```

You should not conclude:

> "LLMs are simple because generation is just next-token prediction."

The **loop** is simple.

The model generating the distribution is enormously more complex.

---

# 38. A crucial distinction: mechanism vs capability

This is a good interview concept.

You can say:

> **Next-token prediction describes the mechanism of generation, not the full explanation of the capabilities that emerge from the learned model.**

The generation loop is:

```text
distribution → token → append → repeat
```

The distribution itself contains the learned behavior.

Later topics explain where that behavior comes from.

---

# 39. Why next-token prediction can produce reasoning-like text

You may observe:

```text
Let's calculate this step by step.

First...

Therefore...

So the answer is...
```

At the mechanism level, the model is still generating tokens sequentially.

The generated sequence can contain structures that **look like reasoning**.

For Topic 2, the important point is:

> Even sophisticated-looking output is generated through the same next-token mechanism.

Don't jump yet into whether this constitutes genuine reasoning. That's outside this topic.

---

# 40. Why a model can continue a pattern

Suppose:

```text
1, 2, 3, 4,
```

The likely continuation may be:

```text
5
```

Or:

```text
Monday, Tuesday, Wednesday,
```

may continue with:

```text
Thursday
```

The model has learned patterns in text.

The mechanism remains:

```text
context
 ↓
next-token distribution
 ↓
selected token
```

---

# 41. Why prompts matter

At this point, you can already see why prompt wording matters.

Compare:

```text
Explain Java.
```

with:

```text
Explain Java to a beginner using a simple analogy.
```

These create different contexts.

Different context:

```text
↓
different conditional distribution
↓
different likely continuations
```

You don't need prompt-engineering techniques yet.

You're just understanding the mechanical foundation for Topic 9.

---

# 42. Why adding one sentence can alter the response

Suppose:

```text
Explain machine learning.
```

versus:

```text
Explain machine learning to a 10-year-old.
```

The second context changes the probability distribution toward tokens associated with:

```text
simple explanations
analogies
basic vocabulary
```

Again:

```text
context
→ probability distribution
→ generated tokens
```

---

# 43. Why generated text can become self-reinforcing

Suppose the model starts with:

```text
There are three important reasons...
```

That phrase establishes an expectation of:

```text
First...
Second...
Third...
```

Once `First` is generated, the resulting context makes a structured enumeration more likely.

So the model can establish a pattern and then continue that pattern.

This helps explain both:

* coherent structure
* excessive continuation

using the same mechanism.

---

# 44. The key idea behind "losing the thread"

Don't explain it as:

> "The model forgot."

Instead, at this stage say:

> The model's next-token distribution is determined by the context available to it, and its own generated tokens become part of that context. If generation moves onto a different trajectory, subsequent predictions are conditioned on that new trajectory.

That's a much more mechanically accurate explanation.

---

# 45. Three behaviors, one mechanism

Your syllabus intentionally asks you to connect three observations to the same mechanism. 

### Confident wrongness

```text
plausible continuation
        ↓
high probability
        ↓
fluent but potentially false statement
```

### Verbosity

```text
one plausible continuation
        ↓
another plausible continuation
        ↓
another
        ↓
long response
```

### Losing the thread

```text
generated continuation
        ↓
new context
        ↓
new distribution
        ↓
trajectory shifts
```

All three occur within:

```text
context
 ↓
distribution
 ↓
token
 ↓
append
 ↓
repeat
```

That's the insight your syllabus is looking for.

---

# 46. What not to say in an interview

Avoid:

> "The LLM thinks of the answer and then writes it."

Better:

> "An autoregressive LLM generates a probability distribution over the next token conditioned on the current context, selects a token according to the decoding strategy, appends it to the context, and repeats."

That answer demonstrates actual understanding.

---

# 47. The one-sentence interview answer

Memorize this:

> **An autoregressive LLM generates a probability distribution over the next token given the current context, selects a token from that distribution, appends it to the sequence, and repeats until generation stops.**

If you can explain that naturally without memorizing the sentence, you've understood Topic 2.

---

# 48. Topic 2 mental model

Keep this diagram in your notes:

```text
             CURRENT CONTEXT
                    │
                    ▼
              ┌───────────┐
              │    LLM    │
              └─────┬─────┘
                    │
                    ▼
        Probability distribution
        over vocabulary tokens
                    │
                    ▼
             Token selection
                    │
                    ▼
             New token ID
                    │
                    ▼
         Append to context
                    │
                    └──────────────┐
                                   │
                                   ▼
                              Repeat
```

Everything else in Topic 2 is an explanation of this diagram.

---

# 49. Hands-on exercises for your notebook

Because your learning rules say **you write the exercise code yourself**, I won't give you the implementation.

Your Topic 2 notebook should contain these experiments.

### Experiment 1 — Next-token probabilities

Use a real language model/API to inspect the next-token behavior conceptually.

Goal:

```text
prompt
→ possible continuations
→ observe probability differences
```

---

### Experiment 2 — Context changes prediction

Compare:

```text
The doctor treated the
```

with:

```text
The mechanic repaired the
```

Ask yourself:

> How should the likely continuation distribution differ?

Then verify experimentally where your chosen model/API exposes suitable information.

---

### Experiment 3 — Autoregressive generation

Build a very small generation loop conceptually:

```text
prompt
→ predict
→ append
→ predict
→ append
→ ...
```

Don't use a high-level `generate()` abstraction for the learning version if you can avoid it.

The point is to see the loop yourself.

---

### Experiment 4 — One-token-at-a-time logging

For every generation step, record:

```text
step
current context
selected token
new context
```

Example:

```text
Step 1
Context: "The cat"
Token: " sat"

Step 2
Context: "The cat sat"
Token: " on"

Step 3
Context: "The cat sat on"
Token: " the"
```

---

### Experiment 5 — Greedy vs sampling

Use a tiny model or API where appropriate.

Compare:

```text
greedy
```

against:

```text
sampling
```

Don't study temperature mathematically yet.

Just observe:

```text
same context
→ different selection behavior
```

---

### Experiment 6 — Confident wrongness

Construct prompts containing a false or fictional premise.

Record:

```text
Prompt
Model response
Why the continuation is plausible
Why plausibility does not establish truth
```

Do not try to solve hallucination yet.

---

### Experiment 7 — Verbosity

Give the model a simple question.

Observe how one continuation can lead to:

```text
answer
→ explanation
→ example
→ additional explanation
→ summary
```

Then explain it using the autoregressive loop.

---

### Experiment 8 — Trajectory drift

Start with a prompt where several continuations are plausible.

Run multiple generations.

Compare:

```text
Run 1
Run 2
Run 3
```

Then explain:

```text
different selected token
→ different context
→ different next distribution
→ increasingly different trajectory
```

---

# 50. Quiz yourself

Before marking Topic 2 complete, you should be able to answer these **without notes**.

### Basic

1. What exactly is being predicted?
2. Is it a word or a token?
3. What is a probability distribution?
4. What does autoregressive mean?
5. What happens after a token is selected?

### Mechanical

6. Why does every generated token change the next prediction?
7. Why does the model need to run the prediction process repeatedly?
8. What is the role of the context?
9. Why does the model not generate the entire response in one next-token prediction?
10. What is the difference between the generation loop and the model that produces the distribution?

### Behavioral

11. Why can a model produce a fluent false statement?
12. Why can the response become unnecessarily long?
13. Why can a generated response drift away from the original direction?
14. How can an early generated token influence many later tokens?
15. Why can two generations from the same prompt differ?

### Interview

16. Explain next-token prediction in 30 seconds.
17. Explain autoregression in one example.
18. Explain why "next-word prediction" is technically inaccurate.
19. Explain confident wrongness without using "bug" or "bad model."
20. Explain verbosity using only the next-token mechanism.

---
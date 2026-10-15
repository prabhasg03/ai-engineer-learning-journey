# Topic 8 — Hallucination

**Before:** Topic 2 (Next-token prediction), Topic 7 (Temperature and sampling)

## Done When

You can present hallucination as **expected behaviour of the training objective** and name **three concrete mitigation levers**.

You should be able to explain:

> **Why "plausible next token" is not "true token", why post-training doesn't remove hallucination, and how grounding / "I don't know" / verification passes mitigate it.**

---

# 1. What Is Hallucination?

Hallucination is when a model generates text that is **fluent, confident, and plausible — but factually incorrect or entirely fabricated**.

It is not a rare edge case. It is a structural property of how LLMs work.

```text
Hallucination
= fluent output
+ confident tone
+ no grounding in reality
```

---

# 2. The Core Mechanism: Plausible ≠ True

From Topic 2, the model's only mechanism is:

```text
Predict next token
   ↓
Sample from distribution
   ↓
Append to context
   ↓
Repeat
```

The training objective (next-token prediction on massive text corpora) optimizes for:

> **Statistical plausibility** — what token sequence looks like human language.

It does **not** optimize for:

> **Truth** — whether the statement corresponds to reality.

These are different targets.

### Example

Prompt:
```
Who won the 2023 Nobel Prize in Physics for work on quantum entanglement?
```

Model might generate:
```
The 2023 Nobel Prize in Physics was awarded to Dr. Sarah Chen and Dr. Michael Roberts for their groundbreaking work on quantum entanglement in topological materials.
```

This sounds perfectly plausible — it has the right structure, names, and terminology. But it's entirely fabricated. The actual 2023 winners were Pierre Agostini, Ferenc Krausz, and Anne L'Huillier for attosecond physics.

The model produced a **plausible continuation**, not a **true statement**.

---

# 3. Why the Training Objective Produces Hallucination

## 3.1 Next-Token Prediction Rewards Fluency

The loss function (cross-entropy) penalizes the model when it assigns low probability to the actual next token in the training data.

The model learns:
- Grammar
- Factual patterns that appear frequently in training
- Style and tone
- Reasoning-like patterns

It does **not** learn:
- A concept of "truth" vs "falsehood"
- A mechanism to verify claims against reality
- When it "doesn't know"

## 3.2 The Model Has No Access to Ground Truth at Inference Time

At inference, the model only has:
- The prompt (context)
- Its weights (compressed training patterns)

It cannot:
- Query a database
- Check Wikipedia
- Run code to verify math
- Distinguish "I learned this" from "this pattern looks familiar"

## 3.3 Fluency Is the Failure Mode

The more fluent the model, the more convincing the hallucination.

A less capable model might say:
```
I don't know who won.
```

A more capable model says:
```
Dr. Sarah Chen won for quantum entanglement research.
```

The second answer **looks better** by the training objective's metric (next-token likelihood), but it's **worse** by the truth metric.

---

# 4. Why Post-Training Doesn't Remove Hallucination

## 4.1 What Post-Training Does

Post-training (SFT, RLHF, RLAIF, DPO, etc.) shapes the model's behavior by:
- Teaching it to follow instructions
- Teaching it to refuse harmful requests
- Teaching it to format output in certain ways
- Teaching it to say "I don't know" in some contexts
- Smoothing the probability distribution toward preferred responses

## 4.2 What Post-Training Cannot Do

Post-training operates on the **same weights** and **same architecture**.

It cannot:
- Add a "truth verification" module
- Give the model access to external knowledge at inference
- Change the fundamental objective (next-token prediction)
- Distinguish between "memorized fact" and "plausible fabrication" internally

## 4.3 The "Confident Error" Problem

RLHF often rewards confident, helpful-sounding answers.

A model that says:
```
I'm not certain, but I think...
```

may be penalized compared to:
```
The answer is X.
```

This can **increase** confident hallucination in some regimes — the model learns that confident wrongness scores higher than hedged correctness.

> **Post-training polishes the surface; it doesn't change the engine.**

---

# 5. Three Concrete Mitigation Levers

These are engineering approaches, not model fixes. They work **around** the model's limitations.

---

## Lever 1 — Grounding (Retrieval-Augmented Generation)

**Principle:** Don't ask the model to recall facts. Give it the facts.

```text
Without grounding:
Prompt → Model → "Dr. Sarah Chen won..."

With grounding:
Prompt → Retrieve relevant docs → Prompt + docs → Model → "According to the Nobel committee, the 2023 winners were..."
```

### How It Works

1. **Retrieve** relevant documents from a trusted source (your database, web search, knowledge base)
2. **Insert** those documents into the context window
3. **Instruct** the model to answer only from the provided context
4. **Cite** sources in the answer

### Why It Works

The model is good at:
- Reading provided text
- Synthesizing answers from given context
- Following "only use the provided information" instructions

The model is bad at:
- Retrieving facts from its weights
- Knowing what it doesn't know

### Practical Pattern

```python
# Pseudocode
context = retrieve_documents(query, top_k=5)
prompt = f"""Answer using ONLY the provided context. If the context doesn't contain the answer, say "I don't know."

Context:
{context}

Question: {query}

Answer:"""
```

### Limitations

- Retrieval can fail (wrong documents retrieved)
- Context window limits how much you can provide
- Model can still hallucinate *within* the provided context (though less often)
- Doesn't help with reasoning tasks that require no external facts

---

## Lever 2 — Allow "I Don't Know" (Abstention)

**Principle:** Train/prompt the model to refuse when uncertain, rather than guess.

### Why Models Don't Naturally Say "I Don't Know"

The training data contains very few examples of "I don't know" — humans writing text usually write answers, not refusals. The model learns that completing the pattern means producing an answer.

### How to Enable Abstention

#### Via Prompting

```text
If you are not certain of the answer, respond with "I don't have enough information to answer this question." Do not guess.
```

#### Via System Prompt

```text
You are a careful assistant. When you don't know something, explicitly say so. It is better to refuse than to hallucinate.
```

#### Via Fine-Tuning (if you control the model)

Include refusal examples in SFT data:
```
Q: Who won the 2023 Nobel Prize in Physics for quantum entanglement?
A: I don't have that information in my training data. The 2023 Nobel Prize in Physics was awarded for attosecond physics.
```

#### Via Sampling Settings

Low temperature + top-p can reduce random fabrication, but **does not guarantee abstention**.

### Calibrated Abstention (Advanced)

Research shows models can be calibrated to express uncertainty verbally:
- "I'm confident that..." (high probability)
- "I think..." (moderate)
- "I'm not sure, but..." (low)
- "I don't know." (very low / no evidence)

This requires careful evaluation on your specific use case.

---

## Lever 3 — Verification Passes

**Principle:** Generate, then verify. Don't trust the first pass.

### Pattern 1 — Self-Consistency / Best-of-N

```python
# Generate multiple answers at temperature > 0
answers = [generate(prompt, temperature=0.7) for _ in range(5)]

# Check for consensus
if all_same(answers):
    return answers[0]  # High confidence
else:
    return "Multiple possible answers; needs review"
```

### Pattern 2 — Critic / Verifier Model

```python
# Generate candidate answer
candidate = generate(prompt, temperature=0.2)

# Verify with a separate prompt/model
verification_prompt = f"""Does the following answer accurately address the question? Check for hallucinations.

Question: {prompt}
Proposed Answer: {candidate}

Respond with: VALID / INVALID / UNCERTAIN
Reason:"""

verification = generate(verification_prompt, temperature=0)

if "INVALID" in verification:
    return "Verification failed: " + verification
else:
    return candidate
```

### Pattern 3 — Structured Verification (Code / Schema)

For extractable facts (numbers, dates, entities):

```python
answer = generate(prompt, temperature=0.1)
extracted_facts = parse_entities(answer)

# Verify each against ground truth
for fact in extracted_facts:
    if not verify_against_source(fact):
        return f"Unverified claim: {fact}"

return answer
```

### Pattern 4 — Chain-of-Verification (CoVe)

1. Generate initial answer
2. Generate verification questions from the answer
3. Answer those questions independently
4. Revise original answer based on verification

```text
Initial: "Sarah Chen won 2023 Nobel Physics for quantum entanglement"
   ↓
Verification Qs: "Who won 2023 Nobel Physics?" "What was the citation?"
   ↓
Independent answers: "Agostini, Krausz, L'Huillier for attosecond pulses"
   ↓
Revised: "The 2023 Nobel Physics winners were Agostini, Krausz, L'Huillier. The claim about Sarah Chen was incorrect."
```

---

# 6. Interview Framing: Expected Behaviour, Not a Bug

This is a critical interview distinction.

##  Weak Answer

> "Hallucination is a bug where the model makes things up. We're working on fixing it."

This suggests you don't understand the architecture.

##  Strong Answer

> "Hallucination is expected behaviour of next-token prediction trained for plausibility, not truth. The model generates statistically likely continuations; it has no internal truth-verification mechanism. Post-training (RLHF) smoothes outputs but doesn't add a truth check — it can even increase confident errors. We mitigate it with three levers: (1) grounding via RAG so the model reads facts rather than recalling them, (2) explicit abstention prompts so the model says 'I don't know' instead of guessing, and (3) verification passes — self-consistency, critic models, or structured fact-checking against trusted sources."

---

# 7. Common Misconceptions

| Misconception | Reality |
|---------------|---------|
| "Hallucination is a bug that will be fixed" | It's a structural property of the training objective |
| "Temperature 0 eliminates hallucination" | Low temperature reduces variation, not fabrication. A confident hallucination at T=0 is still a hallucination. |
| "Bigger models hallucinate less" | They hallucinate *more fluently*. Frequency may decrease for memorized facts, but novel fabrication persists. |
| "RLHF removes hallucination" | RLHF teaches style/refusal; it doesn't add truth verification. Can increase confident errors. |
| "The model 'knows' it's hallucinating" | The model has no introspective access to its own knowledge boundaries. |
| "Citations in the output prove grounding" | Models can fabricate citations that look perfectly real (fake DOIs, fake URLs, fake page numbers). |

---

# 8. What You Should Be Able to Explain Without Notes

1. **Define hallucination in terms of the training objective** — plausible next token ≠ true token
2. **Explain why post-training doesn't remove it** — same weights, same architecture, no truth module added
3. **Name and describe three mitigation levers** — grounding, abstention, verification
4. **Give a concrete example of each lever** — RAG prompt pattern, "I don't know" instruction, self-consistency loop
5. **Frame it correctly in an interview** — expected behaviour, not a bug; engineering mitigations, not model fixes

---

# 9. Connection to Other Topics

| Topic | Connection |
|-------|------------|
| 2. Next-token prediction | Root cause: the only mechanism is statistical continuation |
| 7. Temperature & sampling | Low T reduces variation but not fabrication |
| 9. Prompt engineering | "I don't know" prompts, citation requirements |
| 22-28. RAG | Grounding lever implemented via retrieval |
| 34. Citations and grounding | Verifying citations, abstention on weak evidence |
| 55. Faithfulness metrics | Automated hallucination detection (RAGAS, etc.) |
| 57. Evaluating agents | Trajectory evaluation catches hallucinated tool calls |

---

# 10. Final Mental Model

```text
TRAINING OBJECTIVE
       │
       ▼
Next-token prediction on internet-scale text
       │
       ▼
Optimizes for: statistical plausibility / fluency
       │
       ▼
Does NOT optimize for: truth / factuality / knowledge boundaries
       │
       ▼
HALLUCINATION IS EXPECTED
       │
       ├──▶ Grounding (RAG) ─────▶ "Read, don't recall"
       ├──▶ Abstention ──────────▶ "Say 'I don't know' instead of guessing"
       └──▶ Verification ────────▶ "Generate, then check"
```

**One sentence to remember:**

> **Hallucination is not a bug — it's the model doing exactly what it was trained to do: produce plausible continuations. The engineering task is to build systems that detect, mitigate, or route around it.**
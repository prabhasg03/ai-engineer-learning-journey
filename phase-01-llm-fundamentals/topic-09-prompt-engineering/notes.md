# Topic 9 — Prompt Engineering That Survives Contact

**Before:** Topic 6 (Your first LLM API call)

## Done When

You take a **failing prompt**, rewrite it using **roles / few-shot / delimiters**, and **defend every change**.

Layer one of the stack: **prompt → context → harness → loop**.

---

# 1. What Is Prompt Engineering?

Prompt engineering is the disciplined practice of designing inputs to an LLM to produce reliable, correct, useful outputs.

It is **not**:
- "Prompt whispering" (magic phrases)
- Trial-and-error without a method
- One perfect prompt that works forever

It **is**:
- Systematic iteration: change one thing, measure, keep or revert
- Understanding how the model reads your input
- Building prompts that degrade gracefully under distribution shift

---

# 2. The Mental Model: How the Model Reads Your Prompt

The model sees a **sequence of tokens**. It doesn't "understand" your intent — it predicts what token sequence plausibly follows.

Your prompt is **context**. Everything in it biases the next-token distribution.

```text
Your prompt
    ↓
Tokenized
    ↓
Fed to transformer
    ↓
Biases logits for next token
    ↓
Generation begins
```

**Key insight**: The model has no hidden state from your prompt except what's in the token sequence. If it's not in the tokens, it doesn't exist.

---

# 3. Roles: System vs User vs Assistant

## 3.1 The Three Roles

| Role | Purpose | Typical Content |
|------|---------|-----------------|
| `system` | Persistent instructions, persona, rules, constraints | "You are a precise JSON extractor. Never add commentary." |
| `user` | The actual query/task from the human (or application) | "Extract the invoice number from: [text]" |
| `assistant` | Model's previous responses (for few-shot, conversation history) | Prior examples, previous turns |

## 3.2 What Belongs in System Prompts

```text
✓ Task definition and constraints
✓ Output format requirements (JSON schema, no markdown, etc.)
✓ Persona / tone / style rules
✓ Negative constraints ("Never do X")
✓ Tool/function descriptions (if not using native tool calling)
✓ Few-shot examples (alternatively: in user messages)
```

```text
✗ The actual task input (that's user)
✗ Conversation history (that's user/assistant pairs)
✗ Dynamic data that changes per request
```

## 3.3 System Prompt Example

```json
{
  "role": "system",
  "content": "You are an invoice extraction engine. Output ONLY valid JSON matching this schema:\n{\"invoice_number\": \"string\", \"date\": \"YYYY-MM-DD\", \"total\": \"number\", \"vendor\": \"string\"}\n\nRules:\n- If a field is not present, use null\n- Never add commentary, explanations, or markdown\n- If the text is not an invoice, return {\"error\": \"not_an_invoice\"}"
}
```

---

# 4. Few-Shot Examples

## 4.1 Why Few-Shot Works

The model learns the **pattern** from examples:
- Input format → Output format
- Style, verbosity, edge-case handling
- Implicit rules not stated explicitly

## 4.2 Few-Shot Structure

```text
System: [instructions]

User: Example 1 input
Assistant: Example 1 output

User: Example 2 input
Assistant: Example 2 output

...

User: Actual task input
Assistant: [model generates]
```

## 4.3 Choosing Examples

| Principle | Why |
|-----------|-----|
| **Diverse** | Cover edge cases, not just happy path |
| **Representative** | Match the distribution of real inputs |
| **Minimal** | 3-5 examples usually sufficient; more = cost/latency |
| **Correct** | Wrong examples teach wrong patterns |

## 4.4 Example: Invoice Extraction

```json
[
  {"role": "system", "content": "Extract invoice fields as JSON. Schema: {\"invoice_number\": \"str\", \"date\": \"YYYY-MM-DD\", \"total\": \"float\", \"vendor\": \"str\"}. Missing → null. Non-invoice → {\"error\": \"not_an_invoice\"}."},
  {"role": "user", "content": "Invoice #INV-2024-001\nDate: 2024-01-15\nVendor: Acme Corp\nTotal: $1,234.56"},
  {"role": "assistant", "content": "{\"invoice_number\": \"INV-2024-001\", \"date\": \"2024-01-15\", \"total\": 1234.56, \"vendor\": \"Acme Corp\"}"},
  {"role": "user", "content": "Receipt from Bob's Cafe\nCoffee: $4.50\nTotal: $4.50"},
  {"role": "assistant", "content": "{\"error\": \"not_an_invoice\"}"},
  {"role": "user", "content": "Invoice 42\nVendor: Widgets Inc\nTotal: 99.00"},
  {"role": "assistant", "content": "{\"invoice_number\": \"42\", \"date\": null, \"total\": 99.0, \"vendor\": \"Widgets Inc\"}"},
  {"role": "user", "content": "[YOUR ACTUAL INPUT HERE]"}
]
```

---

# 5. Delimiters

## 5.1 Why Delimiters Matter

The model needs to know **where one thing ends and another begins**.

Without delimiters:
```
Analyze this text for sentiment: The movie was great but the ending ruined it. Is it positive?
```
Ambiguous: Is "Is it positive?" part of the text or the instruction?

With delimiters:
```
Analyze the following text for sentiment:

<<<TEXT>>>
The movie was great but the ending ruined it.
<<</TEXT>>>

Question: Is the sentiment positive?
```

## 5.2 Common Delimiter Patterns

| Pattern | Use Case |
|---------|----------|
| `<<<TAG>>> ... <<</TAG>>>` | Named sections, nestable |
| `---` / `===` | Simple separation |
| `""" ... """` | Code blocks, long text |
| `<tag> ... </tag>` | XML-style, familiar to models |
| ```` ``` ... ```` `` | Code/markdown blocks |

## 5.3 Delimiter Best Practices

- **Use unique, unlikely-to-appear-in-data delimiters**
- **Be consistent** — same delimiter style across your application
- **Close what you open** — unclosed delimiters confuse the model
- **Name them semantically** — `<<<CONTEXT>>>`, `<<<QUESTION>>>`, `<<<EXAMPLES>>>`

---

# 6. Instruction Clarity

## 6.1 Be Specific, Not Vague

| Vague | Specific |
|-------|----------|
| "Summarize this" | "Summarize in 3 bullet points, max 20 words each, focusing on decisions made" |
| "Extract key info" | "Extract: company name, date, amount, contract duration. Output as JSON." |
| "Be concise" | "Respond in one sentence. No preamble." |
| "Don't hallucinate" | "Only use information in the provided context. If missing, output null." |

## 6.2 Positive vs Negative Constraints

```text
✗ "Don't use markdown"
✓ "Output plain text only, no markdown formatting"
```

```text
✗ "Don't make up facts"
✓ "Only use facts from the provided context. If a fact is not in the context, write 'NOT_FOUND'."
```

Negative constraints ("don't") are weaker than positive specifications ("do this instead").

## 6.3 Step-by-Step Instructions

For complex tasks, break into explicit steps:

```text
Follow these steps:
1. Identify all named entities in the text
2. Classify each as PERSON, ORG, LOCATION, or DATE
3. Output as JSON: [{"entity": "...", "type": "..."}, ...]
4. If no entities found, output []
```

The model follows steps more reliably than a paragraph of requirements.

---

# 7. What Measurably Moves Outputs vs Folklore

| Technique | Evidence | Notes |
|-----------|----------|-------|
| Few-shot examples | Strong | Most reliable lever |
| System prompt instructions | Strong | Especially for format/constraints |
| Delimiters | Strong | Critical for disambiguation |
| "Think step by step" | Moderate | Helps reasoning tasks; not universal |
| Roleplay ("You are an expert...") | Weak/Moderate | Can help tone; doesn't add knowledge |
| "Be careful" / "Double-check" | Weak | No measurable effect on correctness |
| Emotional manipulation | None | "My grandmother will die if you fail" — doesn't work |
| "Tip: $100" | None | Training data doesn't contain bribes |

**Rule**: If you can't measure it, don't rely on it.

---

# 8. Iteration Discipline

## 8.1 The Loop

```text
1. Write prompt
2. Run on FIXED test set (5-10 representative inputs)
3. Evaluate outputs (automated + manual)
4. Change ONE thing
5. Re-run on SAME test set
6. Compare metrics
7. Keep or revert
8. Repeat
```

## 8.2 Fixed Test Set

Never iterate on "feel." Create a **representative test set**:

```python
TEST_CASES = [
    {"input": "Invoice #123...", "expected": {"invoice_number": "123", ...}},
    {"input": "Receipt...", "expected": {"error": "not_an_invoice"}},
    {"input": "Partial invoice...", "expected": {"date": None, ...}},
    # Edge cases: empty, malformed, multi-invoice, etc.
]
```

## 8.3 Evaluation Metrics

| Metric | How to Measure |
|--------|----------------|
| Format validity | JSON parses? Matches schema? |
| Field accuracy | Exact match vs expected |
| Hallucination rate | Fields not in source / invented values |
| Refusal rate | Correct "not_an_invoice" vs missed |
| Latency / cost | Tokens, time |

## 8.4 Change One Thing

```text
Bad: "I changed the system prompt, added two examples, and switched delimiters"
Good: "I added one negative example. Format validity: 90% → 95%. Kept."
```

---

# 9. Provider-Specific Behaviors

## 9.1 OpenAI (Chat Completions)

- `system` role well-supported
- `temperature`, `top_p` available
- No native `top_k`
- Structured outputs via `response_format: {type: "json_schema", ...}`

## 9.2 Anthropic (Messages)

- `system` is a **top-level parameter**, not a message
- `temperature`, `top_p`, `top_k` all available
- Prefill via `assistant` message with partial content
- Strong at following complex instructions

## 9.3 Local (llama.cpp / vLLM / TGI)

- Varies by server
- Usually OpenAI-compatible API
- May not support all parameters
- Test your specific deployment

---

# 10. Common Failure Modes & Fixes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Output has markdown despite "no markdown" | Instruction not in system prompt | Move to system; add few-shot |
| Fields missing from JSON | Schema not explicit enough | Add schema to system; few-shot with all fields |
| Model explains instead of outputting | "Assistant" tone in system prompt | System: "Output ONLY JSON. No commentary." |
| Inconsistent date formats | No format specified | Specify `YYYY-MM-DD` in schema + examples |
| Hallucinated values | No grounding / no "null" instruction | Add "use null if missing" + few-shot with nulls |
| Verbose output | No length constraint | "Max 3 bullets", "One sentence", token limit |

---

# 11. Advanced: Prompt Templates as Code

Treat prompts as **versioned, tested code**:

```python
# prompts/invoice_extraction.py
from string import Template

SYSTEM_PROMPT = """You are an invoice extraction engine. Output ONLY valid JSON matching this schema:
{"invoice_number": "string", "date": "YYYY-MM-DD", "total": "number", "vendor": "string"}

Rules:
- If a field is not present, use null
- Never add commentary, explanations, or markdown
- If the text is not an invoice, return {"error": "not_an_invoice"}"""

FEW_SHOT = [
    {"role": "user", "content": "Invoice #INV-2024-001\nDate: 2024-01-15\nVendor: Acme Corp\nTotal: $1,234.56"},
    {"role": "assistant", "content": '{"invoice_number": "INV-2024-001", "date": "2024-01-15", "total": 1234.56, "vendor": "Acme Corp"}'},
    {"role": "user", "content": "Receipt from Bob's Cafe\nCoffee: $4.50\nTotal: $4.50"},
    {"role": "assistant", "content": '{"error": "not_an_invoice"}'},
]

def build_messages(text: str) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(FEW_SHOT)
    messages.append({"role": "user", "content": f"<<<INVOICE_TEXT>>>\n{text}\n<<</INVOICE_TEXT>>>"})
    return messages
```

Version control this. Test it. Review changes like code.

---

# 12. Interview-Ready Answer

> **Q: "How do you design a prompt that reliably extracts structured data?"**
>
> **A:** "I start with a system prompt that defines the task, output schema, and hard constraints (e.g., 'output ONLY JSON, missing fields = null'). I add 3-5 diverse few-shot examples covering happy path and edge cases. I use named delimiters (`<<<INPUT>>>...<<</INPUT>>>`) to separate the variable input from instructions. I evaluate on a fixed test set with automated metrics (schema validity, field accuracy). I iterate by changing one thing at a time — adding an example, tightening a constraint — and measure the delta. I don't rely on folklore like 'think step by step' or roleplay unless the test set shows it helps."

---

# 13. What You Should Be Able to Explain Without Notes

1. **Three roles** — system/user/assistant, what belongs in each
2. **Few-shot** — why it works, how to choose examples, where to place them
3. **Delimiters** — why needed, common patterns, best practices
4. **Instruction clarity** — specific vs vague, positive vs negative, step-by-step
5. **Iteration discipline** — fixed test set, change one thing, measure
6. **What's folklore** — emotional manipulation, tips, "be careful" don't work
7. **Provider differences** — system prompt location, available parameters

---

# 14. Connection to Other Topics

| Topic | Connection |
|-------|------------|
| 6. First API call | Prompt is the JSON body's `messages` |
| 7. Temperature/sampling | Low T for extraction; prompt must work at that T |
| 8. Hallucination | "Only use context" + abstention are prompt techniques |
| 12. Structured output | Schema in system prompt + few-shot = parse-and-retry loop |
| 27. Prompt from retrieval | Delimiters critical when injecting retrieved docs |
| 35. Context engineering | Prompt is the static skeleton; context is dynamic slots |
| 48. Harness engineering | Prompts become packaged skills (SKILL.md) |

---

# 15. Final Mental Model

```text
PROMPT ENGINEERING
       │
       ├──▶ Static skeleton (system prompt, few-shot, delimiters)
       │         │
       │         ▼
       │    Versioned, tested, reviewed like code
       │
       ├──▶ Dynamic slots (user input, retrieved context, tool results)
       │         │
       │         ▼
       │    Injected at runtime, validated, truncated
       │
       └──▶ Evaluation loop
                 │
                 ▼
           Fixed test set + metrics
                 │
                 ▼
           Change one thing → measure → keep/revert
```

**One sentence to remember:**

> **Prompt engineering is not writing clever sentences — it's building a tested, versioned interface between your application and the model's probability distribution.**
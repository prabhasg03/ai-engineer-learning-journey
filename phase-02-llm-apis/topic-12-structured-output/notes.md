# Topic 12 — Structured Output

## 1. Purpose of This Topic

You have learned to make raw HTTP calls (Topic 6) and model data with Pydantic (Topic 11). Now you apply both to the central engineering problem: **getting JSON you can actually parse from an LLM**.

This topic teaches you why `"please reply in JSON"` fails, and how to build a reliable parse-and-retry loop that works in production.

---

## 2. Prerequisites

**Before: Topic 11 — Python unassisted #2: type hints and Pydantic models**

You need Pydantic models to define the output schema and validate responses.

---

## 3. The Problem: "Please Reply in JSON"

Asking an LLM to output JSON is unreliable:

```text
User: Extract the invoice as JSON.
Model: Here is the invoice:
{
  "invoice_number": "INV-001",
  "total": 1234.56
}
```

Problems:
1. **Prose wrapper** — model adds explanation before/after JSON
2. **Markdown fences** — wraps in ```json ... ```
3. **Invalid JSON** — trailing commas, missing quotes, wrong types
4. **Schema drift** — keys missing, wrong types, extra fields

In production, this breaks downstream systems.

---

## 4. Three Approaches Compared

| Approach | How It Works | Reliability | When to Use |
|----------|--------------|-------------|-------------|
| **Prompt-only** | "Reply only with valid JSON matching this schema" | ~60-80% | Prototyping only |
| **JSON mode** | Provider enforces JSON syntax (not schema) | ~90% syntax, schema not guaranteed | When provider supports it |
| **Schema-constrained decoding** | Provider restricts tokens to valid schema | ~99%+ | Production (OpenAI Structured Outputs) |
| **Parse-and-retry** | You parse, validate, retry with error feedback | ~95%+ with 2-3 retries | Any provider, any schema |

---

## 5. JSON Mode vs Schema-Constrained Decoding

### 5.1 JSON Mode (syntax only)

```python
# Request
{
    "model": "gpt-4o-mini",
    "messages": [...],
    "response_format": {"type": "json_object"}
}
```

Guarantees: valid JSON syntax
Does NOT guarantee: required fields, correct types, no extra fields

### 5.2 Structured Outputs (OpenAI) / Tool-Use Schema (Anthropic)

```python
# Request with schema
{
    "model": "gpt-4o-2024-08-06",
    "messages": [...],
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "invoice",
            "schema": {...},  # JSON Schema
            "strict": true
        }
    }
}
```

Guarantees: valid JSON **matching the exact schema**

---

## 6. The Parse-and-Retry Loop (Universal)

Since not all providers support schema-constrained decoding, and you need to understand the mechanism, you will build a **parse-and-retry loop** by hand.

```text
┌─────────────────────────────────────┐
│         ATTEMPT N                   │
│  1. Send request with schema in     │
│     system prompt                   │
│  2. Get response                    │
│  3. Extract JSON from response      │
│  4. Parse JSON                      │
│  5. Validate against Pydantic model │
│         │                           │
│    ┌────┴────┐                      │
│    ↓         ↓                      │
│ Success   Failure                   │
│    │         │                      │
│    ↓         ↓                      │
│  Return   Retry with error          │
│           feedback (max N times)    │
└─────────────────────────────────────┘
```

### 6.1 Retry Feedback

On validation failure, feed the error back to the model:

```text
Your previous response failed validation:

Error: Field 'total' - Input should be a valid number
Received: "total": "1234.56"

Please fix and return only valid JSON matching the schema.
```

---

## 7. Extracting JSON from Model Output

Models often wrap JSON in prose or markdown. Extract robustly:

```python
import re
import json

def extract_json(text: str) -> dict | None:
    """Extract first JSON object from text."""
    # Remove markdown fences
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    
    # Find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    
    try:
        return json.loads(text[start:end+1])
    except json.JSONDecodeError:
        return None
```

---

## 8. The Validation Loop Implementation

```python
from pydantic import BaseModel, ValidationError
from typing import TypeVar

T = TypeVar("T", bound=BaseModel)

def structured_call(
    model_class: type[T],
    messages: list[dict],
    max_retries: int = 3,
    **api_kwargs
) -> T:
    """
    Call LLM API, parse response, validate against model_class.
    Retry with error feedback on validation failure.
    """
    schema_json = model_class.model_json_schema()
    
    system_prompt = f"""You are a structured data extraction engine.
Output ONLY valid JSON matching this exact schema:
{json.dumps(schema_json, indent=2)}

Rules:
- No prose, no markdown, no commentary
- All required fields must be present
- Types must match exactly
"""

    for attempt in range(max_retries):
        # Build messages with schema reminder
        current_messages = [
            {"role": "system", "content": system_prompt},
            *messages
        ]
        
        if attempt > 0:
            # Add error feedback from previous attempt
            current_messages.append({
                "role": "user",
                "content": f"Previous response failed validation:\n{last_error}\n\nReturn corrected JSON only."
            })
        
        response = call_api(current_messages, **api_kwargs)
        raw = extract_content(response)
        parsed = extract_json(raw)
        
        if parsed is None:
            last_error = "No valid JSON found in response"
            continue
        
        try:
            return model_class.model_validate(parsed)
        except ValidationError as e:
            last_error = format_validation_errors(e)
            continue
    
    raise RuntimeError(f"Failed after {max_retries} retries")
```

---

## 9. Why "Please Reply in JSON" Fails

| Failure Mode | Example | Root Cause |
|--------------|---------|------------|
| Prose wrapper | "Here is your JSON: {...}" | Model trained to be helpful, not silent |
| Markdown fences | ```json {...}``` | Common in training data |
| Type coercion | `"total": "1234.56"` (string) | JSON doesn't distinguish int/float in text |
| Missing fields | omits optional `vendor: null` | Model doesn't know null is required |
| Extra fields | adds `"confidence": 0.95` | No constraint against extra keys |

---

## 10. Tool Schemas as Output Contracts

The same JSON Schema used for **tool declarations** (Topic 17) doubles as your **output contract**.

```python
# Tool schema = output schema
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_invoice",
        "description": "Extract invoice fields",
        "parameters": Invoice.model_json_schema()
    }
}

# When model calls tool, arguments ARE the structured output
```

This is why Topic 12 comes **before** Topic 17 — you understand the schema first.

---

## 11. Done-When Checklist

From the syllabus:

- [ ] "Please reply in JSON" and why it breaks
- [ ] JSON mode vs schema-constrained decoding vs parse-and-retry
- [ ] Tool schemas reused as output contracts
- [ ] Retry-with-error-feedback loops on validation failure
- [ ] Instructor-style libraries — only after hand-rolling once

---

## 12. Sources

- [OpenAI — structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Instructor](https://python.useinstructor.com/) (only after hand-rolling once)
- [Anthropic — tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
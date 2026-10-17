# Topic 17 — Tool Calling / Function Calling

## 1. Purpose of This Topic

Build the complete tool-calling loop **by hand**. No frameworks. No SDK agent helpers.

You will learn the single most important fact about tool calling:

> **The model never executes anything itself.** It returns a call *request*. Your code executes the function, feeds the result back, and loops until the model produces a final answer.

This is the #1 interview misconception — candidates say "the model calls the tool" when actually the model only *requests* a call.

---

## 2. Prerequisites

**Before: Topic 12 — Structured output**

You need:
- Pydantic models for JSON schemas (Topic 12)
- JSON extraction + parse-and-retry (Topic 12)
- Raw HTTP API calls (Topic 6)

---

## 3. The Tool-Calling Mental Model

### What actually happens

```text
Your code                  Model                  Your code
    │                          │                        │
    │ 1. request + tool schema │                        │
    │ ───────────────────────> │                        │
    │                          │ 2. returns tool call   │
    │                          │    REQUEST (not exec)  │
    │ <─────────────────────── │                        │
    │                          │                        │
    │ 3. execute function      │                        │
    │ ───────────────────────> │                        │
    │                          │                        │
    │ 4. feed result back      │                        │
    │ ───────────────────────> │                        │
    │                          │ 5. final answer        │
    │ <─────────────────────── │                        │
    │                          │                        │
```

The model is a **text predictor**. It sees your tool schemas in the system prompt, decides which tool to call and what arguments to pass, but it cannot run code.

### One sentence interview correction

> "The model doesn't execute the tool — it emits a structured request. Your code executes the function and feeds the result back."

---

## 4. The Tool-Calling Loop

```text
┌─────────────────────────────────────────────────┐
│  Loop iteration N                               │
│  ┌─────────────┐      ┌──────────────────┐      │
│  │ Send request│─────▶│ Model decides    │      │
│  │  + tools    │      │  which tool to   │      │
│  └─────────────┘      │  call (+args)    │      │
│         │             └──────────────────┘      │
│         │                                       │
│         ▼                                       │
│  ┌─────────────┐                                │
│  │ If tool call│─────▶│ Execute function   │      │
│  │   requested │      │  locally           │      │
│  └─────────────┘      └──────────────────┘      │
│         │                                       │
│         ▼                                       │
│  ┌─────────────┐                                │
│  │ Feed result │─────▶│ Model generates      │      │
│  │   back      │      │  final answer        │      │
│  └─────────────┘      └──────────────────┘      │
│         │                                       │
│         └─────── (repeat until final answer) ──┘
└─────────────────────────────────────────────────┘
```

### Message roles in tool calling

| Role | Purpose |
|------|---------|
| `system` | Instructions + tool schemas |
| `user` | The user's question |
| `assistant` | Model's response (text OR tool call request) |
| `tool` | Function result fed back to model |

---

## 5. Declaring Tools as JSON Schemas

Tools are declared with JSON Schema, just like Topic 12's structured output:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "units": {"type": "string", "enum": ["c", "f"]}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Do math",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"}
                },
                "required": ["expression"]
            }
        }
    }
]
```

The model receives these in the system prompt (or via the provider's `tools` parameter) and returns a `tool_calls` array in its response instead of plain text.

---

## 6. The Model Returns a Call Request

When the model decides to use a tool, its response looks like:

```json
{
    "choices": [{
        "message": {
            "role": "assistant",
            "content": null,
            "tool_calls": [{
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": "{\"city\": \"Seattle\", \"units\": \"c\"}"
                }
            }]
        }
    }]
}
```

Note:
- `content` is `null` (no text)
- `tool_calls` contains the requested call(s)
- `arguments` is a **JSON string** — you must parse it
- Each call has a unique `id` you must echo back in the `tool` response

---

## 7. You Execute; You Feed the Result Back

```python
# Your code executes the function
result = get_weather(city="Seattle", units="c")

# Feed back as a tool message
{
    "role": "tool",
    "tool_call_id": "call_abc123",
    "content": '{"temperature": 15, "condition": "cloudy"}'
}
```

The `tool_call_id` must match the `id` from the model's request — this is how the model knows which result corresponds to which call.

---

## 8. Loop Until Final Answer

The model may:
1. Return text → done
2. Return a tool call → execute, feed back, repeat
3. Return multiple tool calls → execute all, feed all back, repeat

```python
messages = [system, user]
for _ in range(max_iterations):
    response = call_llm(messages, tools=TOOLS)
    msg = response["choices"][0]["message"]

    if msg.get("tool_calls"):
        # The assistant message WITH tool_calls must go into history
        # BEFORE the matching tool messages.
        messages.append(msg)

        # Execute each tool call
        for tool_call in msg["tool_calls"]:
            name = tool_call["function"]["name"]
            args = json.loads(tool_call["function"]["arguments"])
            result = TOOL_FUNCTIONS[name](**args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(result)
            })

        continue

    if msg.get("content"):
        return msg["content"]  # Final answer
```

---

## 9. Argument Hallucination

The model may pass arguments that are:
- Wrong type (string instead of number)
- Missing required fields
- Extra fields not in schema
- Values not in enum

**Always validate** tool arguments before executing:

```python
from pydantic import BaseModel, ValidationError

class GetWeatherArgs(BaseModel):
    city: str
    units: str = "c"

args = json.loads(tool_call["function"]["arguments"])
try:
    validated = GetWeatherArgs(**args)
except ValidationError as e:
    # Feed error back to model
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps({"error": str(e)})
    })
    continue
```

---

## 10. Multiple / Parallel Tool Calls

The model can request multiple tools in one response:

```json
"tool_calls": [
    {"id": "call_1", "function": {"name": "get_weather", "arguments": "{\"city\": \"Seattle\"}"}},
    {"id": "call_2", "function": {"name": "get_weather", "arguments": "{\"city\": \"Portland\"}"}}
]
```

Execute all, feed all back as separate `tool` messages with matching `tool_call_id`s, then let the model synthesize.

---

## 11. Provider Differences

| Aspect | OpenAI | Anthropic |
|--------|--------|-----------|
| Declaration | `tools` parameter | `tools` parameter |
| Schema | JSON Schema | `input_schema` |
| Response field | `tool_calls` | `tool_use` |
| Result role | `tool` | `user` (with `tool_result`) |
| Multiple calls | Supported | Supported |

The **mechanism is identical**: model requests, you execute, you feed back.

---

## 12. Done-When Checklist

From the syllabus:

- [ ] Declaring tools as JSON schemas; the model returns a call *request*
- [ ] You execute; you feed the result back; loop until final answer
- [ ] The model never executes anything itself — the #1 interview misconception
- [ ] Argument hallucination; multiple/parallel tool calls

---

## 13. Sources

- [OpenAI — function calling](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api)
- [Anthropic — tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [anthropic-sdk `tool_runner`](https://github.com/anthropics/anthropic-sdk-python) (reference implementation — read after hand-rolling)
# Topic 14 — Streaming

## 1. Purpose of This Topic

You have made raw HTTP calls (Topic 6) and learned async (Topic 13). Now you learn **streaming** — receiving the response token-by-token instead of waiting for the full completion.

Streaming transforms perceived latency and enables real-time UX, but it complicates error handling, parsing, and retries.

---

## 2. Prerequisites

**Before: Topic 6, Topic 13**

You need:
- Raw HTTP request/response understanding
- Async/await and `aiohttp` patterns

---

## 3. Why Streaming Matters

| Non-streaming | Streaming |
|---------------|-----------|
| Wait 5s for full response | First token in 200ms |
| User sees nothing | User sees progressive output |
| All-or-nothing failure | Partial result on failure |
| Simple parsing | Incremental parsing needed |

---

## 4. Server-Sent Events (SSE)

LLM streaming uses **Server-Sent Events** — a simple HTTP-based protocol.

```text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"choices":[{"delta":{"content":"Hello"}}]}

data: {"choices":[{"delta":{"content":" world"}}]}

data: {"choices":[{"delta":{"content":"!"}}]}

data: [DONE]
```

Each chunk:
- Starts with `data: `
- Contains JSON with `delta` (not `message`)
- Ends with `\n\n`
- Final chunk: `data: [DONE]`

---

## 5. Streaming Request (OpenAI-compatible)

```python
payload = {
    "model": "gpt-4o-mini",
    "messages": [...],
    "stream": True,  # Key difference
    "max_tokens": 256
}
```

---

## 6. Consuming the Stream (async)

```python
import aiohttp
import json

async def stream_completion(session, url, payload):
    async with session.post(url, json=payload) as response:
        response.raise_for_status()
        
        async for line in response.content:
            line = line.decode('utf-8').strip()
            if not line or line == "data: [DONE]":
                continue
            
            if line.startswith("data: "):
                data = line[6:]  # Remove "data: "
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"]
                    if "content" in delta:
                        yield delta["content"]
                except json.JSONDecodeError:
                    continue

# Usage
async for token in stream_completion(session, url, payload):
    print(token, end="", flush=True)
```

---

## 7. Key Differences: Streaming vs Non-Streaming Response

| Aspect | Non-streaming | Streaming |
|--------|---------------|-----------|
| Response field | `message.content` | `choices[0].delta.content` |
| Stop reason | In final response | In final chunk (`finish_reason`) |
| Usage | In final response | In final chunk (or separate) |
| Errors | HTTP status | May appear mid-stream |

---

## 8. Mid-Stream Errors

Streaming can fail **after** some tokens are delivered:

```text
data: {"choices":[{"delta":{"content":"The answer is 42"}}]}
data: {"choices":[{"delta":{"content":" because"}}]}
data: {"error":{"type":"rate_limit_error","message":"Rate limit exceeded"}}
```

Your code must:
- Handle errors after yielding partial content
- Not assume the stream completes cleanly
- Decide: show partial result? retry? abort?

---

## 9. No Clean Retry After Flush

Once you've sent tokens to the user (printed, sent via WebSocket, written to HTTP response), **you cannot cleanly retry**.

Options:
1. **Buffer first, then send** — defeats streaming latency benefit
2. **Accept partial failure** — show what you have, offer retry button
3. **Idempotent retry design** — only for non-user-facing background jobs

---

## 10. Streaming + Tool Calls

Tool calls can appear **mid-stream**:

```text
data: {"choices":[{"delta":{"content":"Let me check..."}}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"get_weather","arguments":"{\""}}]}}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"location\":\"NYC\"}"}}]}}]}
data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"}"}}]}}]}
```

You must:
- Buffer tool call chunks until complete
- Parse accumulated arguments as JSON
- Execute tool, then resume streaming

---

## 11. Incremental Parsing

For structured output with streaming, parse incrementally:

```python
import json

class IncrementalParser:
    def __init__(self, model_class):
        self.model_class = model_class
        self.buffer = ""
    
    def feed(self, chunk: str) -> list[BaseModel]:
        self.buffer += chunk
        results = []
        
        # Try to extract complete JSON objects
        while True:
            start = self.buffer.find("{")
            end = self.buffer.rfind("}")
            if start == -1 or end == -1:
                break
            candidate = self.buffer[start:end+1]
            try:
                parsed = json.loads(candidate)
                validated = self.model_class.model_validate(parsed)
                results.append(validated)
                self.buffer = self.buffer[end+1:]
            except (json.JSONDecodeError, ValidationError):
                break
        
        return results
```

---

## 12. When to Use Streaming

| Use Streaming | Don't Need Streaming |
|---------------|---------------------|
| Chat interfaces | Background batch jobs |
| Real-time dashboards | Structured extraction (Topic 12) |
| Long-form generation | When you need atomic all-or-nothing |
| User-facing latency matters | When retry must be clean |

---

## 13. Done-When Checklist

From the syllabus:

- [ ] Server-sent events mechanics; assembling chunks/deltas
- [ ] Why streaming transforms perceived latency and UX
- [ ] Mid-stream error handling: partial answers, no clean retry after flush
- [ ] Complication preview: streaming + tool calls together

---

## 14. Sources

- [OpenAI — streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Anthropic — streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [SSE specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
# SYLLABUS


### Progress map

| Phase | Topics | Milestone | Done |
|---|---|---|---|
| 1 — What an LLM is | 1–10 | Project A | ☐ 1–3 , 4–6  (self-taught) |
| 2 — LLM APIs as a backend engineer | 11–21 | Project B | ☐ |
| 3 — Embeddings & RAG | 22–28 | Project 1 | ☐ |
| 4 — RAG that survives production | 29–34h | — | ☐ |
| 5 — Context engineering | 35–37 | — | ☐ |
| 6 — Agents | 38–49 | Project 2 | ☐ |
| 7 — Evaluation | 50–57 | — | ☐ |
| 8 — LLMOps & production | 58–64 | Project 3 | ☐ |
| 9 — Theory underneath & the job | 65–70 | interviews/portfolio | ☐ |
| B — ML foundations *(interleaved)* | 71–90 + 78a | Mini-project B + both interview doors | ☐ |

The stack worth memorising for interviews — it's also the shape of the course:

```text
prompt engineering   →  what one message says              (topic 9)
context engineering  →  what the window contains            (topics 35–37)
harness engineering  →  what runs around the model          (topic 48)
loop engineering     →  what drives the loop unsupervised   (topic 49)
```

---

## Phase 1 — What an LLM actually is

### 1. Tokens  *(taught — [lessons/0001-tokens.html](lessons/0001-tokens.html), reference: [reference/llm-fundamentals.html](reference/llm-fundamentals.html))*

**Done when:** you predict which strings cost more tokens and why, then verify with a tokenizer.

- [x] Why models don't consume words or characters
- [x] Bytes → BPE merges → vocabulary IDs; frequent text cheap, rare text expensive
- [x] Consequences: cost, limits, weird behaviours (r-counting, trailing whitespace, non-English inflation)
- [x] Counting tokens programmatically with `tiktoken`
- [x] Exercise: predicted counts verified in OpenAI/tiktokenizer playgrounds

Sources: [Karpathy — Let's build the GPT Tokenizer](https://www.youtube.com/watch?v=zduSFxRajkE) ·
[karpathy/minbpe](https://github.com/karpathy/minbpe)

### 2. Next-token prediction  *(self-taught via [chats/2.next_token.md](chats/2.next_token.md) — teaching, graded final challenge and drift answer appended to that file; no lesson HTML)*

**Before:** 1 · **Sources:** [Karpathy — Intro to LLMs (1h)](https://www.youtube.com/watch?v=zjkBMFhNj_g) · [State of GPT](https://www.youtube.com/watch?v=bZQun8Y4L2A)
**Done when:** you explain why Copilot is sometimes confidently wrong or overly verbose purely from next-token mechanics — "bug" and "bad model" are banned words in the answer.

- [x] The single mechanism: output a distribution over the next token, sample, append, repeat
- [x] Autoregression — generated text becomes input text
- [x] Why observed Copilot behaviours (confident wrongness, verbosity, losing the thread) fall out of this one loop — all three demonstrated (chat 2 probe; EOS bonus; drift answer 2026-09-01)
- [x] Verbosity mechanically: generation runs until a stop token / EOS or a token cap — nothing in the objective prefers brevity *(taught at the end of `chats/2.next_token.md`; applied in the pizza challenge's EOS bonus)*
- [x] "Losing the thread" tied explicitly to drift: each generated token conditions the next, so one early wrong turn compounds *(answered in own words at the end of `chats/2.next_token.md`)*
- [x] Training objective vs inference behaviour — one line only; depth lands in topic 65

*Status 2026-09-01: DONE. The pizza three-step challenge was answered correctly (full trace, correct re-feeding, EOS named as the terminator unprompted; one refinement: per-step distributions must sum to 1), and the drift box was answered in own words. Verbosity's explain-state is partial — EOS was applied but never narrated in own words; re-check it as an opening retrieval question next session.*

### 3. The context window, precisely  *(self-taught via [chats/3.Context Window Topic.md](chats/3.Context Window Topic.md) — teaching, graded final challenge and quadratic answer appended to that file; no lesson HTML)*

**Before:** 2 · **Sources:** [Karpathy — Deep Dive into LLMs](https://www.youtube.com/watch?v=7xTGNNLPyMI) · [OpenAI — tokens & counting](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)
**Done when:** you predict what happens (error vs truncation vs cost growth) when a conversation grows past the limit, and can explain truncation vs compaction mechanically.

- [x] Input + output share one budget per request
- [x] What happens at overflow: hard error vs silent truncation, depending on API
- [x] Named anchors for overflow — OpenAI: 400 `context_length_exceeded`; Anthropic: 400 `invalid_request_error` ("prompt is too long"); 413 for byte-size limits; silent truncation is self-hosted/legacy behaviour *(taught and applied at the end of `chats/3.Context Window Topic.md`)*
- [x] Why finite: attention cost grows with length — crisp interview version: self-attention compares every token with every other, so cost grows roughly with the *square* of sequence length *(fact recalled in own answer 2026-09-01; the n×n mechanism phrasing gets one re-check at the next session's opening retrieval)*
- [x] Truncation vs compaction — formalising what you already know informally
- [x] "The model forgot" is mechanical: never saw it, or attention degraded

*Status 2026-09-01: DONE. The four-question final challenge was answered correctly (no-fit arithmetic; truncation; compaction; lossy summarisation — refinement given: Q4 should name both lossy paths), both overflow anchors were named exactly, and the quadratic fact was recalled. Its mechanism phrasing gets one re-check next session.*

### 4. Statelessness  *(self-taught via [chats/4.Statelessness.md](chats/4.Statelessness.md) — teaching, the missing cached-prefixes box, and the graded challenge were appended to that file; no lesson HTML)*

**Before:** 3 · **Sources:** [Chip Huyen — Notes on LLM Engineering](https://huyenchip.com/2023/04/11/llm-engineering.html) · [Anthropic — prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) *(source added 2026-09-24 for the fake-memory box)*
**Done when:** you narrate where conversation state actually lives and why cost grows on every turn even when nothing new is asked.

- [x] The API has no memory between calls; conversation is a list *you* resend each turn
- [x] History growth = cost growth, paid on every turn *(2,000-token re-send trace computed solo in chat 4)*
- [x] Things that look like memory but aren't: chat products, cached prefixes, stored threads *(the one box the chat skipped — taught at the end of `chats/4.Statelessness.md` 2026-09-24: provider-side threads/`previous_response_id` reassemble the same prefix server-side; prompt caching discounts re-computation of the re-sent prefix — 1.25× write / 0.1× read on Anthropic, up to 90% off cached input on OpenAI, minutes-scale TTL refreshed on use; challenge answered correctly same day)*
- [x] Implication chain: statelessness → client-side history → compaction need → cost curve

*Status 2026-09-24: DONE. The chat earned four ideas on 2026-09-09 (statelessness definition, cost-growth arithmetic, client-side state assembly incl. system prompt/RAG context, compaction-need chain); the review added the fake-memory box the chat never taught, plus a graded challenge. One medium-severity check rolls into opening retrieval: never cite "70–80% accuracy loss" as a universal threshold (LR-0010).*

### 5. Python unassisted #1: functions, dicts, JSON  *(self-taught via [chats/5.functions,dicts,json.md](chats/5.functions,dicts,json.md) — no lesson HTML)*

**Before:** none · **Sources:** [pytest — Get Started](https://docs.pytest.org/en/stable/getting-started.html) · [Composing Programs](https://www.composingprograms.com/) (selective) · [Fluent Python 2e](https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/) (Paid)
**Done when:** dict/JSON-munging functions pass your own pytest suite, written with zero autocomplete.

- [x] Writing without Copilot: functions, dict/list manipulation, `json.load`/`json.dump` *(dict/JSON functions hand-written in `practise/5_dictionary_json.py`; mutation-aliasing and nested-access paths explained — one slip: `choices` is a list, index before key)*
- [x] pytest basics: plain asserts, running tests, reading failure output *(own suite in `practise/5_test.py`; diagnosed `E assert 130 == 120` as a wrong test expectation, not a wrong function)*
- [x] venv + pip hygiene *(venv create/activate demonstrated; `python -m pip install pytest` into the active env)*
- [x] Policy: no autocomplete; tests prove correctness, not vibes

*Status 2026-09-24: DONE (chat 2026-09-09). Done-when met — own pytest suite passing, written unassisted. Closing six-question retrieval all correct (`load`/`loads`, key-vs-index, aliasing, `assert`, reading `E` lines, venv purpose); answer keys live at the end of the chat; items roll into the opening-retrieval rotation (LR-0011). One refinement to keep: say "`items` and `x` refer to the same mutable list object", not "passing the reference".*

### 6. Your first LLM API call  *(self-taught via [chats/6.llm_api_call.md](chats/6.llm_api_call.md) — no lesson HTML)*

**Before:** 4, 5 · **Sources:** [OpenAI API docs](https://developers.openai.com/api/docs) · [Anthropic API docs](https://platform.claude.com/docs)
**Done when:** you make a raw HTTP call (no SDK), read every field of the response, and triage a 401 vs 400 vs 429 on sight.

- [x] Raw HTTP anatomy: endpoint, headers, auth key, JSON body — no SDK yet *(hand-written `requests.post()` against Gemini in `practise/6_llm.py`: `x-goog-api-key` + `Content-Type` headers, key from env var, payload separate from headers)*
- [x] The `messages` array and roles; reading the response object (`content`, `usage`, stop reason) *(parsed content, `finishReason: STOP`, and the full usage block — caught that `total ≠ prompt + completion` because of `thoughtsTokenCount`, unprompted)*
- [x] Reading provider docs as an engineer *(read Gemini's REST schema; noted OpenAI Responses API uses `input`/`previous_response_id` rather than `messages`)*
- [x] First contact with errors: 401 vs 400 vs 429 *(triaged on sight in the probe)*

*Status 2026-09-24: DONE (chat 2026-09-18). Done-when met — raw HTTP, no SDK, full response read, errors triaged; final explain-back ("Python → POST → endpoint + headers + JSON payload → JSON response → extract fields") closed it (LR-0012). One refinement: the API key lives in a header, provider-specific (`x-goog-api-key` vs `Authorization: Bearer`). Production-hygiene debt parked on topic 11: check status code before `.json()`, and never assume token schemas match across providers.*

### 7. Temperature and sampling

**Before:** 6 · **Sources:** [State of GPT](https://www.youtube.com/watch?v=bZQun8Y4L2A) · [Chip Huyen — Notes](https://huyenchip.com/2023/04/11/llm-engineering.html)
**Done when:** you choose sampling settings for three different tasks and justify each; and explain why temperature 0 isn't a determinism guarantee.

- [ ] Temperature reshapes the distribution; top-p / top-k crop it
- [ ] Same prompt ≠ same answer; temperature 0 is near-deterministic, not guaranteed
- [ ] When randomness helps (ideation) vs hurts (extraction, code)
- [ ] Where sampling params live in both major APIs

### 8. Hallucination

**Before:** 2, 7 · **Sources:** [Why language models hallucinate](https://openai.com/index/why-language-models-hallucinate/) · [Anthropic — reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations)
**Done when:** you present hallucination as expected behaviour of the training objective and name three concrete mitigation levers.

- [ ] Plausible-next-token ≠ true; fluency is the failure mode
- [ ] Why post-training polish doesn't remove it (and smooths confident errors)
- [ ] Mitigation levers: grounding, allowing "I don't know", verification passes
- [ ] Interview framing: expected behaviour, not a bug

### 9. Prompt engineering that survives contact

**Before:** 6 · **Sources:** [Anthropic — prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview) · [Anthropic interactive tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial) · [Lilian Weng — Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/)
**Done when:** you take a failing prompt, rewrite it using roles/few-shot/delimiters, and defend every change. Layer one of the stack: prompt → context → harness → loop.

- [ ] System vs user vs assistant roles; what belongs in system prompts
- [ ] Few-shot examples; delimiters; instruction clarity
- [ ] What measurably moves outputs vs folklore
- [ ] Iteration discipline: change one thing, test against fixed examples

### 10. Token cost and counting

**Before:** 1, 6 · **Sources:** [tiktoken](https://github.com/openai/tiktoken) · [Anthropic — token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)
**Done when:** you estimate a feature's $/request including input/output split before writing its code.

- [ ] Input/output pricing asymmetry; model tiers
- [ ] Estimating cost before shipping; counting endpoints and `tiktoken`
- [ ] Cost regressions from prompt bloat
- [ ] Thinking in $/request at scale

### Mini-project A — CLI summariser

**Before:** 1–10 · **Done when:** it runs on a fresh machine from your README alone.
**Rules:** hand-written throughout. No frameworks, no Copilot.

- [ ] File reader + API call, streaming-free output
- [ ] Token/cost report per run
- [ ] pytest suite passing
- [ ] Written without autocomplete/AI generation

---

## Phase 2 — LLM APIs as a backend engineer

### 11. Python unassisted #2: type hints and Pydantic models

**Before:** 5 · **Sources:** [Pydantic v2 docs](https://docs.pydantic.dev/latest/) · [Real Python — dataclasses](https://realpython.com/python-data-classes/) · [Adam Johnson — type hints](https://adamj.eu/tech/2021/05/11/python-type-hints-args-and-kwargs/)
**Done when:** you model a real API payload with validators and narrate exactly what happens when bad data hits it.

- [ ] Annotations for primitives, `Optional`/`Union`, containers
- [ ] Pydantic `BaseModel`: field types, validators, `.model_validate()` / `.model_dump()`
- [ ] Validation errors as contracts failing loudly at the boundary
- [ ] Why typed I/O is non-negotiable once another system consumes your output

### 12. Structured output

**Before:** 11 · **Sources:** [OpenAI — structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) · [Instructor](https://python.useinstructor.com/) (only after hand-rolling once)
**Done when:** a schema-constrained call plus retry-on-validation loop runs end-to-end, and you can say precisely why "please reply in JSON" fails.

- [ ] "Please reply in JSON" and why it breaks
- [ ] JSON mode vs schema-constrained decoding vs parse-and-retry
- [ ] Tool schemas reused as output contracts
- [ ] Retry-with-error-feedback loops on validation failure
- [ ] Instructor-style libraries — only after hand-rolling once

### 13. Python unassisted #3: async and await

**Before:** 5 · **Sources:** [Real Python — async IO walkthrough](https://realpython.com/async-io-python/) · [Python.org — conceptual overview of asyncio](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html)
**Done when:** concurrent API calls via `asyncio.gather` work, and you spot a blocking-the-loop bug in code you're shown.

- [ ] Event-loop mental model; coroutine functions vs coroutines vs tasks
- [ ] What `await` suspends and resumes; `asyncio.gather` for concurrency
- [ ] Why IO-bound LLM calls are the ideal async workload
- [ ] Blocking-the-loop pitfalls (sync calls inside async routes)

### 14. Streaming

**Before:** 6, 13 · **Sources:** [OpenAI — streaming](https://developers.openai.com/api/docs/guides/streaming-responses) · [Anthropic — streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming)
**Done when:** a streamed completion renders end-to-end, deltas assembled correctly, and you can describe what breaks mid-stream.

- [ ] Server-sent events mechanics; assembling chunks/deltas
- [ ] Why streaming transforms perceived latency and UX
- [ ] Mid-stream error handling: partial answers, no clean retry after flush
- [ ] Complication preview: streaming + tool calls together

### 15. Python unassisted #4: decorators

**Before:** 5 · **Sources:** [Real Python — decorators primer](https://realpython.com/primer-on-python-decorators/) · [Trey Hunner — decorators track](https://www.pythonmorsels.com/screencasts/decorators/)
**Done when:** you hand-write a decorator that takes arguments and narrate the closure chain that makes it work.

- [ ] Closures → wrapper functions → `@` syntax
- [ ] `functools.wraps`; decorators that take arguments; stacking order
- [ ] Goal: FastAPI's route decorators stop being magic

### 16. FastAPI essentials

**Before:** 11, 15 · **Sources:** [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) · [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
**Done when:** a small service runs with typed routes, one dependency, and a passing TestClient test.

- [ ] Path/query parameters; request bodies as Pydantic models
- [ ] Response models, status codes, dependency injection
- [ ] Async routes; automatic docs
- [ ] TestClient basics — extending the topic 5 testing habit

### 17. Tool calling / function calling

**Before:** 12 · **Sources:** [OpenAI — function calling](https://help.openai.com/en/articles/8555517-function-calling-in-the-openai-api) · [Anthropic — tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) · [anthropic-sdk `tool_runner`](https://github.com/anthropics/anthropic-sdk-python)
**Done when:** the complete tool-call loop works hand-written, and you can correct "the model executes the function" in one sentence.

- [ ] Declaring tools as JSON schemas; the model returns a call *request*
- [ ] You execute; you feed the result back; loop until final answer
- [ ] The model never executes anything itself — the #1 interview misconception
- [ ] Argument hallucination; multiple/parallel tool calls

### 18. MCP — Model Context Protocol ★

**Before:** 17 · **Sources:** [What is MCP?](https://modelcontextprotocol.io/docs/getting-started/intro) · [Architecture](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture) · [Authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
**Done when:** a tiny MCP server you wrote is connected to by a real client, you can name who does what between host/client/server, and you can trace the OAuth flow plus the main prompt-injection risk.

- [ ] The N×M integration problem MCP solves; "USB-C for AI applications"
- [ ] Hosts, clients, servers — who does what
- [ ] Primitives: tools, resources, prompts; discovery and dynamic capability lists
- [ ] Tools vs resources vs prompts: model-controlled actions vs app-controlled context vs reusable templates; when each fits
- [ ] MCP client: connect, list capabilities, call a tool, read a resource, get a prompt, handle errors
- [ ] Transports: stdio vs HTTP; writing a tiny MCP server and connecting a real client to it
- [ ] Authorization (OAuth 2.1): Protected Resource Metadata discovery via `WWW-Authenticate`, AS metadata, PKCE code flow, resource indicators + audience validation, scopes and step-up; stdio uses env creds, not OAuth
- [ ] Security surface: tool-description injection, untrusted servers, token passthrough

### 19. Failure handling

**Before:** 6, 17 · **Sources:** [Claude API errors](https://platform.claude.com/docs/en/api/errors) · [openai-python README](https://github.com/openai/openai-python)
**Done when:** a retry wrapper with exponential backoff + jitter that honours `Retry-After` is running around your calls, and you classify any API error on sight.

- [ ] Taxonomy: rate limits (429), overload (5xx/529), timeouts
- [ ] Exponential backoff with jitter; honouring `Retry-After`
- [ ] Idempotency so retries are safe; circuit-breaker intuition
- [ ] What SDKs retry by default vs what remains your problem

### 19a. Fallbacks / failover

**Before:** 19 · **Sources:** [LiteLLM — Fallbacks](https://docs.litellm.ai/docs/proxy/reliability) · [Cloudflare — Dynamic routing](https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/)
**Done when:** a failing primary model fails over to a backup in order, you name which fallback type fired, and spend logs distinguish fallback-served from direct requests.

- [ ] Ordered failover after `num_retries`: `fallbacks=[{"gpt-4o-mini": ["gpt-4o"]}]`; in-order semantics
- [ ] Three types: general `fallbacks` (rate-limit/5xx) vs `context_window_fallbacks` (needs `enable_pre_call_checks` + `max_input_tokens`) vs `content_policy_fallbacks` (policy violation)
- [ ] Combo: `num_retries` + `request_timeout` + `allowed_fails`/`cooldown_time`; default vs per-request fallbacks; `disable_fallbacks`
- [ ] Attribution: spend logs carry `attempted_fallbacks` + `original_model_group`; key-access and budget enforcement on fallback targets

### 19b. LLM gateways

**Before:** 19a · **Sources:** [LiteLLM AI Gateway](https://docs.litellm.ai/docs/simple_proxy) · [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/) · [Cloudflare — Dynamic routing](https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/)
**Done when:** you route two providers through one OpenAI-compatible endpoint with per-key budgets, and defend gateway-vs-SDK for a given team size.

- [ ] One endpoint for 100+ models: OpenAI-shaped requests, gateway fans out to the model own­ing provider
- [ ] Virtual keys: per user/team/project models + budgets + rate limits; spend tracking per key/team/tag
- [ ] Central controls: logging (Langfuse/Datadog/OTel), guardrails (filters, PII masking), Admin UI
- [ ] Dynamic routes: conditional / percentage (A/B) / rate-limit / budget-limit nodes with fallback; version + rollback without code change
- [ ] Gateway vs SDK decision: gateway past one app/person or when keys/spend/central-logs/guardrails matter

### 19c. Model routing for production

**Before:** 19a · **Sources:** [LiteLLM — Router](https://docs.litellm.ai/docs/routing) · [LiteLLM — Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) · [OpenRouter — Auto Router](https://openrouter.ai/docs/features/model-routing)
**Done when:** you configure two routing strategies plus one auto-router tier, and explain when session affinity is worth its cost.

- [ ] Strategies: simple-shuffle (rpm/tpm-weighted, production default) vs latency-based (TTL + buffer) vs least-busy vs cost-based (price map + custom pricing) vs usage-based; custom plugin
- [ ] Routing groups: per-group strategy; group callable as a model name; group-scoped access + spend rows
- [ ] Auto tiers: SIMPLE / MEDIUM / COMPLEX / REASONING pools; heuristic scorer (7 dims, sub-ms) vs LLM/JEV classifier vs keyword short-circuit; `cause=` marker; adaptive Thompson sampling
- [ ] Hosted contrast: market-based routing (task-type → spend-share → cost_tier low→max → primary + fallbacks); allowed/excluded wildcards; session stickiness with graceful degrade
- [ ] Session affinity: pin by `session_id` so provider prompt caches stay warm; idle TTL; falls through on cooldown; whole session inherits first-turn tier as the trade-off

### 20. Reasoning models and test-time compute ★

**Before:** 7, 10 · **Sources:** [OpenAI — reasoning models](https://developers.openai.com/api/docs/guides/reasoning) · [Anthropic — extended thinking](https://platform.claude.com/docs/en/build-with-claude/extended-thinking) · [Visible extended thinking](https://www.anthropic.com/research/visible-extended-thinking)
**Done when:** given a task profile you pick model + effort/budget with a justified cost-latency trade-off, and explain how thinking tokens get billed.

- [ ] Reasoning/thinking tokens: generated before (and between) visible output, billed as output
- [ ] Control knobs across providers: `reasoning.effort`, thinking budgets → adaptive effort
- [ ] Serial vs parallel test-time compute (best-of-N chains, verifiers)
- [ ] Latency/cost trade-offs: when extra thinking earns its keep
- [ ] Prompting differences: give goals + constraints; skip "think step by step"
- [ ] Planner/worker routing: reasoning model plans, fast model executes

### 21. Decision: when NOT to use an LLM

**Before:** 20 (and most of Phase 2) · **Sources:** [When Code Beats the Model](https://tianpan.co/blog/2026-04-18-when-code-beats-the-model) · [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
**Done when:** for a given feature you argue a justified choice — possibly "no LLM" — plus the condition that would flip it.

- [ ] Constraints → candidates → trade-offs → justified choice + sensitivity ("what flips it")
- [ ] Deterministic-first rule; verifiability as an axis
- [ ] Cost/latency budgets deciding as often as capability
- [ ] Classic flips: regex beats LLM extraction; a classifier beats generation

### Mini-project B — AI Shopping Assistant

**Before:** 11–21 · **Done when:** runs on a fresh machine from your README alone.
**Rules:** FastAPI + structured output + tool calling over product search / inventory / order status. Hand-written throughout.

- [ ] Typed FastAPI service with structured outputs
- [ ] Tool calling over product search / inventory / order status
- [ ] Retries and backoff around every outbound call
- [ ] Streaming responses
- [ ] Written without autocomplete/AI generation

---

## Phase 3 — Embeddings and RAG

### 22. Embeddings

**Before:** 2 · **Sources:** [Alammar — Illustrated Word2Vec](https://jalammar.github.io/illustrated-word2vec/) · [Weaviate — vector embeddings explained](https://weaviate.io/blog/vector-embeddings-explained)
**Done when:** you explain meaning-as-geometry in your own words and choose an embedding model + dimensions knowingly.

- [ ] Text → dense vector; semantics as geometry
- [ ] Similar meaning lands nearby regardless of wording
- [ ] Models, dimensions, normalisation
- [ ] Caveat: benchmark leaders ≠ your domain

### 23. Cosine similarity

**Before:** 22 · **Sources:** [Marqo — intro to vector embeddings](https://www.marqo.ai/courses/introduction-to-vector-embeddings) · [Weaviate — vector search explained](https://weaviate.io/blog/vector-search-explained)
**Done when:** you compute cosine similarity by hand on two tiny vectors and justify cosine over Euclidean distance.

- [ ] Dot products and angles computed by hand on tiny vectors
- [ ] Why cosine and not Euclidean distance (magnitude invariance)
- [ ] In code: numpy, then pgvector operators
- [ ] Threshold picking — no universal number; tune per corpus

### 24. Chunking

**Before:** 22 · **Sources:** [Pinecone — chunking strategies](https://www.pinecone.io/learn/chunking-strategies/) · [NVIDIA — finding the best chunking strategy](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/)
**Done when:** you chunk a sample document three different ways and articulate the granularity trade-off of each.

- [ ] Why split: window limits + retrieval granularity
- [ ] Fixed-size pitfalls: mid-sentence and mid-table cuts
- [ ] Overlap; structure-aware splitting
- [ ] Size trade-off: precision vs context completeness
- [ ] The single highest-leverage quality decision in RAG

### 25. pgvector

**Before:** 23 · **Sources:** [pgvector repo](https://github.com/pgvector/pgvector) · [Crunchy Data — HNSW with pgvector](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector) · [Supabase — vector columns](https://supabase.com/docs/guides/ai/vector-columns)
**Done when:** an indexed vector table answers ANN queries, and you can reason IVFFlat-vs-HNSW for a given corpus size.

- [ ] Vector columns; distance operators (`<->`, `<=>`, `<#>`)
- [ ] Exact vs ANN indexes (IVFFlat, HNSW); recall/speed/memory trade-offs
- [ ] Combining vector search with SQL `WHERE` filters
- [ ] Decision framing: Postgres-first vs specialist vector DBs

### 26. The retrieval pipeline end to end

**Before:** 24, 25 · **Sources:** [Learn RAG From Scratch](https://www.youtube.com/watch?v=sVcwVQRHIc8) · [DeepLearning.AI — RAG course](https://www.deeplearning.ai/courses/retrieval-augmented-generation) · [HF cookbook](https://huggingface.co/learn/cookbook/en/index)
**Done when:** you trace one document through ingest→answer naming where each stage fails silently, with idempotent upserts working.

- [ ] ingest → chunk → embed → store → query → retrieve → assemble → answer
- [ ] Batch embedding; idempotent upserts; re-index triggers
- [ ] Where each stage fails silently
- [ ] Trace one document through the entire path

### 27. Prompt construction from retrieved context

**Before:** 26 · **Sources:** [DeepLearning.AI — RAG course](https://www.deeplearning.ai/courses/retrieval-augmented-generation) · [HF cookbook](https://huggingface.co/learn/cookbook/en/index)
**Done when:** you assemble a context window that neither blows the budget nor buries the question, with citation slots built in.

- [ ] Ordering effects (lost-in-the-middle); question placement
- [ ] Deduplication; budget split between instructions and evidence
- [ ] Citation markers baked into assembly
- [ ] Template hygiene: static skeleton vs dynamic slots

### 28. Where RAG fails

**Before:** 26, 27 · **Sources:** [Applied LLMs](https://applied-llms.org/) · [Eugene Yan — patterns](https://eugeneyan.com/writing/llm-patterns/)
**Done when:** given only symptoms you diagnose which stage failed — retrieval miss, ranking miss, or generation miss.

- [ ] Diagnose: retrieval miss vs ranking miss vs generation miss
- [ ] Stale indices; conflicting chunks; unanswerable-by-corpus questions
- [ ] Failure boundary habit: what breaks, how you'd notice, what you'd change

### Project 1 — RAG service over a real document set

**Before:** 22–28 · **Done when:** a hiring manager can run it from the README. First portfolio piece.

- [ ] Real document set ingested (chunk → embed → pgvector)
- [ ] Query endpoint returning grounded answers with citations
- [ ] Failure handling from topic 19 applied
- [ ] Hand-written throughout

---

## Phase 4 — RAG that survives production

### 29. Chunking strategies compared

**Before:** 24, 28 · **Sources:** [Pinecone — chunking strategies](https://www.pinecone.io/learn/chunking-strategies/) · [NVIDIA study](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/)
**Done when:** you compare strategies empirically on your own corpus and defend a choice plus its flip conditions.

- [ ] Fixed vs recursive vs semantic vs structural — mechanics of each
- [ ] Justified choice for a given corpus, plus sensitivity analysis
- [ ] Measuring: retrieval hit-rate deltas between strategies
- [ ] When the choice flips (corpus changes, query mix changes)

### 30. Hybrid search

**Before:** 25 · **Sources:** [ParadeDB — hybrid search in PostgreSQL](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual) · [Elastic — hybrid search](https://www.elastic.co/search-labs/blog/hybrid-search-elasticsearch)
**Done when:** BM25 + dense fusion runs in your stack, and you name query types where pure vector loses.

- [ ] BM25 refresher (TF-IDF lineage, no deep math)
- [ ] Pure-vector blind spots: names, codes, acronyms, exact phrases
- [ ] Reciprocal rank fusion / score fusion
- [ ] Sparse + dense in a Postgres-era stack

### 31. Reranking

**Before:** 30 · **Sources:** [Cohere — rerank](https://docs.cohere.com/docs/rerank-overview) · [Mixedbread — mxbai-rerank-v2](https://www.mixedbread.com/blog/mxbai-rerank-v2)
**Done when:** a retrieve-wide-rerank-narrow funnel is running and you can do its latency math.

- [ ] Bi-encoder retrieval vs cross-encoder reranking — why cross-encoders score better
- [ ] The top-k funnel: retrieve wide, rerank narrow
- [ ] Latency cost; when reranking earns it
- [ ] Hosted vs self-hosted rerankers

### 32. Query rewriting and expansion

**Before:** 30 · **Sources:** [HyDE paper](https://arxiv.org/abs/2212.10496) · [freeCodeCamp — HyDE explainer](https://www.freecodecamp.org/news/what-is-hyde-how-to-improve-rag-with-hypothetical-documents/)
**Done when:** conversational queries get standalone-ified, HyDE is tried on your corpus, and you know when rewriting hurts.

- [ ] Standalone-ifying conversational queries (coreference resolution)
- [ ] Multi-query expansion; HyDE (hypothetical document embeddings)
- [ ] When rewriting hurts: drift from user intent

### 33. Metadata filtering

**Before:** 25 · **Sources:** [ParadeDB — hybrid manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual) · [pgvectorscale — label-filtered search](https://github.com/timescale/pgvectorscale)
**Done when:** filtered vector search returns correctly scoped results and you can explain pre-filter vs post-filter semantics.

- [ ] Pre-filter vs post-filter semantics in ANN search
- [ ] date / source / tenant / permission scoping
- [ ] The cheapest accuracy win teams reach for last
- [ ] Filter × index interaction gotchas

### 34. Citations and grounding

**Before:** 27 · **Sources:** [Anthropic — citations](https://platform.claude.com/docs/en/build-with-claude/citations) · [Why Your RAG Citations Are Lying](https://tianpan.co/blog/2026-04-23-rag-citations-post-hoc-rationalization)
**Done when:** answers carry span-level citations you've verified against sources, and weak evidence produces abstention instead of invention.

- [ ] Span-level attribution back to source chunks
- [ ] Fake-citation failure modes; verifying cited spans exist
- [ ] Answer abstention when evidence is weak
- [ ] Groundedness as a product requirement, not a nice-to-have

### 34a. Document parsing

**Before:** 24, 26 · **Sources:** [Pinecone — chunking strategies](https://www.pinecone.io/learn/chunking-strategies/) · [Anthropic — contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) · [Unstructured docs](https://docs.unstructured.io/) · [PyMuPDF docs](https://pymupdf.readthedocs.io/) · [LangChain — document loaders](https://docs.langchain.com/oss/python/integrations/document_loaders) *(last three verified 2026-10-13)*
**Done when:** you parse a real PDF with headings and a table into clean text plus structure, and name exactly what was lost in the conversion.

- [ ] Text extraction vs structure preservation: headings, tables, lists, reading order
- [ ] Native-text PDFs vs what needs OCR (see 34b) — never assume every PDF needs OCR
- [ ] Table and header handling: why naive extraction destroys retrieval
- [ ] Exercise: parse one PDF two ways and compare chunk-ready output

### 34b. OCR

**Before:** 34a · **Sources:** [Tesseract user manual](https://tesseract-ocr.github.io/tessdoc/) · [PyMuPDF — OCR guide](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html) *(both verified 2026-10-13)*
**Done when:** you state when OCR is needed vs not, run OCR on one scanned page, and show what its errors do to retrieval.

- [ ] When OCR applies: scanned/image-only PDFs and images; machine-readable text needs none (per LR-0007)
- [ ] OCR error modes: character confusion, layout loss, fake reading order
- [ ] Cost/latency of OCR in the ingest path; caching parsed output
- [ ] Exercise: OCR one scanned page, diff against clean text, predict retrieval impact

### 34c. Metadata enrichment at ingest

**Before:** 26, 33 · **Sources:** [Anthropic — contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) · [ParadeDB — hybrid manual](https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual)
**Done when:** your chunks carry tenant/source/date/section metadata and filtered search returns correctly scoped results because of it.

- [ ] What to attach: source, date, tenant/permissions, section/headings, doc type
- [ ] Contextual prefixes: LLM-generated chunk context before embedding (Anthropic pattern)
- [ ] Enrichment feeds filtering (33) and citations (34) — ingest decides what retrieval can use
- [ ] Exercise: enrich one document set and prove a filtered query respects the new fields

### 34d. Parent-child retrieval

**Before:** 24, 29 · **Sources:** [LangChain — retrievers](https://docs.langchain.com/oss/python/integrations/retrievers/) *(verified 2026-10-13; parent-document pattern now lives under custom retrievers, no standalone page)* · [Anthropic — contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval) (contrast: prefixing vs hierarchy)
**Done when:** small-child matching returns large-parent answers on your corpus and you defend both size choices.

- [ ] Small chunks for matching precision, large parents for answer completeness
- [ ] Child→parent ID mapping; store layout and lookup cost
- [ ] When hierarchy wins vs flat chunks or contextual prefixes
- [ ] Exercise: build the two-level index and show a query flat chunks truncate but parents answer

### 34e. Corrective RAG

**Before:** 28, 32 · **Sources:** [CRAG paper — Corrective Retrieval Augmented Generation](https://arxiv.org/abs/2401.15884) *(Yan et al., verified 2026-10-13)*
**Done when:** you trace grade → rewrite-or-web-search on a weak-retrieval query and say when the fallback earns its cost.

- [ ] Relevance grading of retrieved chunks before generation
- [ ] Corrective actions: rewrite the query, re-retrieve, fall back to web search
- [ ] Versus plain pipeline (26): the grade gate is the difference
- [ ] Exercise: force a retrieval miss and walk the corrective path by hand

### 34f. Self-RAG

**Before:** 28, 34 · **Sources:** [Self-RAG paper](https://arxiv.org/abs/2310.11511) *(Asai et al., verified 2026-10-13)*
**Done when:** you explain retrieve-need and critique tokens in your own words and show when self-critique flips an answer to abstention.

- [ ] Decide-to-retrieve: not every query needs retrieval
- [ ] Reflection tokens: relevance, support, utility critiques inside generation
- [ ] Abstention as a designed outcome, not a failure
- [ ] Versus corrective RAG (34e): self-critique vs external grade gate

### 34g. Graph RAG

**Before:** 26, 30 · **Sources:** [microsoft/graphrag repo](https://github.com/microsoft/graphrag) · [From Local to Global paper](https://arxiv.org/abs/2404.16130) *(both verified 2026-10-13; repo notes it is largely in maintenance mode — read for patterns, build small)*
**Done when:** you build a tiny entity-relation graph and answer one multi-hop question pure vectors miss.

- [ ] Entities + relations extracted at ingest; community summaries for global questions
- [ ] Local vs global search: fact lookup vs synthesis over the graph
- [ ] When graphs win: multi-hop, ownership, hierarchy questions; when they lose: cost and build complexity
- [ ] Exercise: extract a 10-node graph from sample docs and run one multi-hop query

### 34h. Multimodal RAG

**Before:** 26, 34 · **Sources:** [ColPali paper](https://arxiv.org/abs/2407.01449) *(Faysse et al., verified 2026-10-13)*
**Done when:** you retrieve across text plus one non-text modality (image or table) and ground the answer in that source.

- [ ] Text + image/table embeddings in one index; late vs early fusion at intuition level
- [ ] Table/image parsing linkage back to 34a–34b
- [ ] Grounding non-text evidence with citations (34) intact
- [ ] Exercise: ingest one doc with a chart/table and answer a question whose evidence lives outside the prose

---

## Phase 5 — Context engineering ★

*Sits between RAG and agents deliberately: retrieved documents and tool results are what arrive IN
the window, and everything in the agents phase depends on curating it well.*

### 35. From prompt engineering to context engineering ★

**Before:** 9, 14, 17, 26 · **Sources:** [Anthropic — effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
**Done when:** you define the discipline in interview form and explain attention budget and context rot without notes.

- [ ] Definition shift: curating the optimal set of tokens at **every** inference, not writing one perfect prompt
- [ ] Everything landing in the window besides your prompt: system prompt, tool/MCP schemas, retrieved documents, message history, tool results
- [ ] Attention budget and context rot: recall degrades as the window fills even below the limit
- [ ] Guiding principle: smallest possible set of high-signal tokens
- [ ] The layer-stack map: prompt → context → harness → loop

### 36. Compaction, tool-result clearing, and context resets ★

**Before:** 3, 35 · **Sources:** [Context engineering cookbook](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools) · [compaction docs](https://platform.claude.com/docs/en/build-with-claude/compaction)
**Done when:** you can match each context symptom to its primitive and simulate/sketch compaction with a summary prompt tuned recall-first.

- [ ] Compaction: summarise-and-restart; lossy by design; tuning the summary prompt (maximise recall first, then precision); what survives a summary
- [ ] Tool-result clearing: surgically replacing stale, re-fetchable results while keeping the record that the call happened
- [ ] Structured note-taking / agentic memory: notes written OUTSIDE the window, pulled back in later
- [ ] Context resets vs compaction: clean slate + structured handoff artifact vs preserved continuity; "context anxiety" as a real failure
- [ ] Choosing per symptom: whole-window growth → compaction · bulky re-fetchable results → clearing · cross-session persistence → memory

### 37. Just-in-time retrieval and progressive disclosure ★

**Before:** 35, 36 · **Sources:** [context engineering post](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) · [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
**Done when:** you redesign a stuff-everything app sketch into progressive disclosure and argue when stuffing still wins.

- [ ] Stuff-everything vs fetch-on-demand trade-off
- [ ] Progressive disclosure: metadata first (names, sizes, timestamps), details only when relevant
- [ ] Filesystem/environment exploration as the canonical pattern
- [ ] Token-efficient tool outputs: return pointers and summaries, not payloads
- [ ] When one-shot stuffing still wins: small stable corpora, latency-critical paths
- [ ] Bridge: implemented as agentic RAG in topic 43

---

## Phase 6 — Agents

### 38. The agent loop

**Before:** 17 · **Sources:** [smolagents guided tour](https://huggingface.co/docs/smolagents/en/guided_tour) · [Lilian Weng — autonomous agents](https://lilianweng.github.io/posts/2023-06-23-agent/)
**Done when:** a minimal agent loop you wrote by hand terminates cleanly on both success and budget.

- [ ] think → act → observe → repeat, stripped to the smallest honest version
- [ ] Hand-rolled while-loop: messages array + tool dispatch + termination condition
- [ ] Stop conditions: final answer, max iterations, budget exhaustion
- [ ] Frameworks hide exactly this — which is why it's built by hand first

### 39. Decision: workflow vs agent

**Before:** 38 · **Sources:** [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) · [LangGraph — workflows & agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) · [When Code Beats the Model](https://tianpan.co/blog/2026-04-18-when-code-beats-the-model)
**Done when:** given scenarios you classify workflow-vs-agent(-vs-hybrid) and defend each call.

- [ ] Fixed pipeline vs autonomous loop; the hybrid patterns (prompt chaining, routing, orchestrator-worker, evaluator-optimiser)
- [ ] Workflow primitives by name: sequential chain, parallel fan-out/fan-in, conditional branch, loop with stop condition, event-driven trigger — and which hybrid pattern each maps to
- [ ] Routing static vs dynamic: rules/classifier/LLM-judge route conditions; what the router reads and what it returns (next agent, next tool, next model)
- [ ] Predictability / auditability / cost axes
- [ ] The most over-reached-for tool in the field; when the workflow wins decisively
- [ ] Flip condition: task variability

### 40. State and memory

**Before:** 36, 38 · **Sources:** [Letta — agent memory](https://www.letta.com/blog/agent-memory/) · [Mem0 — how it works](https://docs.mem0.ai/core-concepts/how-it-works)
**Done when:** you design a memory-tier scheme for an agent, state a policy for what deserves persisting, and classify any memory as episodic/semantic/user-scoped on sight.

- [ ] Short-term (the window) vs long-term (external stores)
- [ ] State object: what the agent carries between steps (messages, tool results, plan, scratchpad) vs what stays in the window
- [ ] Persistence mechanics: save/load the state object across turns and restarts; what survives a context reset and what must be re-fetched
- [ ] Checkpoints: versioned state snapshots that allow resume, rewind and HITL approval; checkpoint vs memory (resume-point vs retrievable knowledge)
- [ ] Context assembly: which state + memory + retrieval pieces get composed into the window at each inference, and what gets left out
- [ ] Memory tiers: buffer, self-edited core memory, recall/archival stores
- [ ] Episodic vs semantic vs procedural: events you experienced, facts you know, skills you run — mapped to recall vs archival vs core
- [ ] User memory: preferences, decisions, durable facts scoped by `user_id`; extraction → dedup → embed → retrieve (Mem0 add/search flow)
- [ ] Relation to Phase 5 primitives (compaction / clearing / note-taking)
- [ ] Write policies: what deserves persisting at all; never persist secrets or raw credentials

### 41. Planning and decomposition

**Before:** 38 · **Sources:** [Lilian Weng — planning sections](https://lilianweng.github.io/posts/2023-06-23-agent/) · [ReAct paper](https://arxiv.org/abs/2210.03629) · [Reflexion](https://arxiv.org/abs/2303.11366)
**Done when:** you decompose a real task into an agent plan, trace a ReAct Thought/Action/Observation loop by hand, and identify decomposition failure modes in a given trace.

- [ ] Task decomposition into steps; plan representations (lists, graphs, plan files)
- [ ] ReAct: Thought → Action → Observation loop; reasoning traces as actions in language space; when the Thought step earns its keep
- [ ] Reflection / Reflexion: self-critique over past actions, binary reward + heuristic stop, reflections as working memory for the next trial
- [ ] Replanning triggers when observations contradict the plan
- [ ] Reliable failure modes: over-decomposition, lost global goal, plan rot
- [ ] Planner/executor separation previewed (full treatment in topic 48)

### 42. Multi-step tool use

**Before:** 38 · **Sources:** [Berkeley function-calling leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) · [Anthropic — tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
**Done when:** chained tool calls recover from a mid-chain failure, runaway behaviour is capped, and you can name the six tool classes and their failure modes.

- [ ] The six tool classes: API calls, DB/SQL, search/retrieval, browser/web, code execution, file I/O — what each returns and what each breaks
- [ ] Tool selection: how the agent picks 1 of N tools (schema + description quality, argument fit); single vs parallel tool calls and when each wins
- [ ] Chaining where step N+1 needs step N's result
- [ ] Tool-error propagation; partial-progress recovery
- [ ] Runaway detection: iteration caps, repeated-action detectors
- [ ] Parallel vs sequential calls

### 43. Agentic RAG ★

**Before:** 26, 32, 38, 42 · **Sources:** [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) · [effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
**Done when:** your pipeline RAG becomes retrieval-as-a-tool and you can argue the flexibility-vs-determinism trade both ways.

- [ ] Retrieval as a callable tool instead of a fixed pre-retrieval step
- [ ] The agent decides whether / what / how to retrieve; multi-hop retrieval loops
- [ ] Self-correction: retrieve again on weak evidence, decompose the query
- [ ] Versus the hard-coded pipeline of topic 26 — flexibility vs determinism, a decision
- [ ] Cost honesty: agentic retrieval spends tokens deciding to retrieve

### 44. LangGraph

**Before:** 38 · **Sources:** [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) · [workflows & agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
**Done when:** your hand-rolled loop from 38 is rebuilt as a graph, with checkpointing demonstrated.

- [ ] Graphs / nodes / edges / state as explicit control flow over the hand-rolled loop
- [ ] Conditional edges (routing) and loops with stop conditions built as graph constructs; parallel fan-out/fan-in as graph branches
- [ ] Checkpointing and persistence; interrupts as HITL hooks
- [ ] Map every LangGraph concept back to topic 38's loop
- [ ] When the framework earns itself vs gets in the way

### 45. Human-in-the-loop

**Before:** 44 · **Sources:** [Mastra — where to put approval](https://mastra.ai/blog/hitl-where-to-put-approval-in-agents-and-workflows) · [LangGraph interruptions](https://docs.langchain.com/oss/python/langgraph/interrupts) · [OpenAI Agents SDK — human in the loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) · [Pydantic AI — deferred tools](https://ai.pydantic.dev/deferred-tools/)
**Done when:** approval gates sit in defensible places and suspend/resume round-trips work.

- [ ] Gate placement: pre-tool-call approval vs mid-workflow suspend/resume
- [ ] Interrupt/resume mechanics (state snapshots)
- [ ] Which actions must never be autonomous: spending, deleting, sending, merging
- [ ] Approval → review → escalation → intervention chain: approve/reject a paused tool, review the trace before resuming, escalate to a human as a first-class outcome (vs retry/abort), intervene mid-run and resume with `Command(resume=)` / `RunState`
- [ ] Cross-framework shape: OpenAI `needs_approval → interruptions → approve/reject → Runner.run(state)` (serializable `RunState`); Pydantic `requires_approval → DeferredToolRequests/Results`; LangGraph `interrupt()` bubbling to outer graph with outer-only checkpointer + `thread_id`

### 46. Multi-agent orchestration ★

**Before:** 38, 44 · **Sources:** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) · [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) · [OpenAI Agents SDK — orchestration](https://openai.github.io/openai-agents-python/multi_agent/) · [OpenAI Agents SDK — handoffs](https://openai.github.io/openai-agents-python/handoffs/) · [langgraph-supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) · [langgraph-swarm](https://github.com/langchain-ai/langgraph-swarm-py)
**Done when:** an orchestrator-worker run completes with condensed worker reports, and you cite its ~15× cost multiplier unprompted.

- [ ] Subagent pattern: fresh context windows per focused task; condensed returns (~1–2k tokens)
- [ ] Supervisor variants by name: planner → worker (reasoning model plans, cheap model executes), manager → specialists (triage routes, specialist owns remainder), supervisor router vs peer-to-peer swarm (`active_agent` state for resume)
- [ ] Agent selection and dynamic routing: orchestrator picks the next worker by task type and observation; static assignment vs per-step routing
- [ ] Model routing: reasoning model plans, fast/cheap model executes; what flips the route (complexity, cost, latency)
- [ ] Context firewalls: workers don't inherit the orchestrator's transcript
- [ ] Handoffs — task transfer: `transfer_to_X` (OpenAI) vs `Command(goto=)` / `create_handoff_tool` (LangGraph) vs `transfer_to_agent` (ADK); one handoff per destination; handoff as LLM-callable tool
- [ ] Handoffs — context sharing and seamless transitions: full-history default vs condensed return vs filesystem-reference bypass; `input_filter` / `output_mode` / `output_key` / `nest_handoff_history` (not redaction — sanitize before nesting); explicit transfer contract (objective + output format + boundaries)
- [ ] Collaboration — shared goals, shared memory, collective problem solving, team of agents: shared `messages` key vs isolated per-agent keys + shared plan in external Memory / `RunContext`; when shared context hurts (tight dependencies, coding) and isolation wins
- [ ] Agent → agent vs agent → human: `handoff` transfers ownership vs `as_tool()` keeps manager ownership; both surface HITL identically (pause → approve/reject → resume); escalate vs retry vs abort
- [ ] Maker/checker separation; parallel fan-out with isolation (worktrees)
- [ ] Economics: orchestrator-worker runs cost ~15× a chat call — when that's justified
- [ ] When a single agent with better tools suffices (most of the time)

### 46a. OpenAI Agents SDK — handoffs, guardrails, sessions

**Before:** 44, 45, 46 · **Sources:** [Agents](https://openai.github.io/openai-agents-python/agents/) · [Handoffs](https://openai.github.io/openai-agents-python/handoffs/) · [Guardrails](https://openai.github.io/openai-agents-python/guardrails/) · [Sessions](https://openai.github.io/openai-agents-python/sessions/) · [Tracing](https://openai.github.io/openai-agents-python/tracing/) · [Running agents](https://openai.github.io/openai-agents-python/running_agents/)
**Done when:** a triage → specialist handoff with an input guardrail and a needs_approval resume runs end to end, and you can place every guardrail type without notes.

- [ ] `Agent` + `Runner` loop: minimal primitives (`Agent`, `Runner`, tools, handoffs, guardrails, sessions, tracing); `Runner.run/run_streamed` owns turns, handoffs, guardrails; `RunResult` (`final_output`, `interruptions`, `to_state()`)
- [ ] Handoffs vs agents-as-tools: handoff transfers ownership for the remainder of the turn; `as_tool()` keeps manager control to synthesize; combine (triage → handoff → specialist calls others as tools)
- [ ] Guardrail placement: `input_*` on first agent only, `output_*` on final agent only, `tool_*` on every guarded `FunctionTool` call (not on handoffs/hosted tools); `tripwire_triggered` halts the run
- [ ] Sessions as auto-history (not vector memory): `SQLiteSession`/Redis/Mongo/encrypted; same session instance on resume; `to_state()`/`to_input_list()` for inspection
- [ ] SDK vs LangGraph decision: convention-over-graph (LLM routes via handoffs) vs explicit `StateGraph` (cycles, custom schema, `interrupt()`, time-travel)

### 46b. Google ADK — workflows, handoffs, deployment

**Before:** 44, 46 · **Sources:** [Agents](https://adk.dev/agents/) · [LLM agents](https://adk.dev/agents/llm-agents/) · [Workflows](https://adk.dev/workflows/) · [Sessions/State/Memory](https://adk.dev/sessions/) · [Runtime event loop](https://adk.dev/runtime/event-loop/) · [Tool confirmation](https://adk.dev/tools-custom/confirmation/) · [A2A](https://adk.dev/a2a/intro/)
**Done when:** a Sequential → specialist run with `output_key` chaining plus one approval-gated tool deploys via `adk web`, and you can state when ADK beats LangGraph.

- [ ] Core loop: `LlmAgent(name, description, instruction, tools, model)` → `Runner` → `Event` (text / FunctionCall / FunctionResponse / state-delta) → `SessionService`; `description` drives routing, `instruction` templates `{state_var}`
- [ ] Template workflows vs 2.0 graphs: `SequentialAgent` / `ParallelAgent` (distinct `output_key`s) / `LoopAgent` (until `escalate` or `maxIterations`); ADK 2.0+ prefers Graph + Dynamic + Collaborative workflows
- [ ] Handoff and context: `transfer_to_agent` (LLM-driven) vs `AgentTool` delegation vs shared `Session.state` / `output_key` / `temp:` scope vs cross-service `RemoteA2aAgent` (Events  A2A Messages)
- [ ] HITL: `FunctionTool(require_confirmation)` / `request_confirmation` for single tools vs `yield RequestInput` graph node for workflow gates (`rerun_on_resume=True`)
- [ ] ADK vs LangGraph decision: GCP/Gemini-native path (`adk web` → API server → Cloud Run / Agent Engine), built-in Session/Memory/Artifacts + eval harness, A2A + MCP interop vs explicit provider-neutral `StateGraph` control

### 46c. Pydantic AI — typed agents and deferred tools

**Before:** 11, 44, 45 · **Sources:** [Agents](https://ai.pydantic.dev/agents/) · [Multi-agent applications](https://ai.pydantic.dev/multi-agent-applications/) · [Dependencies](https://ai.pydantic.dev/dependencies/) · [Output](https://ai.pydantic.dev/output/) · [Deferred tools](https://ai.pydantic.dev/deferred-tools/) · [Logfire](https://ai.pydantic.dev/logfire/)
**Done when:** a typed `Agent[Deps, Output]` with DI, validated structured output, one delegation and one approval-gated tool runs with Logfire tracing, and you can place it against LangGraph/OpenAI SDK.

- [ ] `Agent[DepsT, OutputT]` container: instructions, typed tools/toolsets, `output_type`, `deps_type`, model string swap (`openai:…` → `google:…`); `run/run_sync/run_stream/iter()`
- [ ] DI via `deps_type` + `RunContext[Deps]`: `ctx.deps` in tools/validators; `agent.override(deps=…)` for tests; async tools for I/O
- [ ] Structured output as validation + retry: `output_type` (models, unions, `Literal`/`Enum`); Tool vs Native vs Prompted output; failure fed back; `result.output` typed
- [ ] Delegation ladder: tool-call delegation (`usage=ctx.usage`, `UsageLimits`) vs `SubAgents` capability (`delegate_task`) vs programmatic handoff in app code vs `pydantic-graph`
- [ ] HITL as deferred tools: `requires_approval` / `raise ApprovalRequired` / `raise CallDeferred`; resume with `DeferredToolResults`; `conversation=` persistence
- [ ] Pydantic AI vs LangGraph vs OpenAI SDK: validated output + FastAPI-like testing + Logfire/OTel vs explicit cyclic graphs vs single-provider convention-over-graph

### 47. Agent failure boundary

**Before:** 38–46 · **Sources:** [τ²-bench](https://github.com/sierra-research/tau2-bench) · [Cloudflare — Project Think](https://blog.cloudflare.com/project-think/)
**Done when:** you post-mortem a failing agent trace and name the observability signal that catches each failure class early.

- [ ] The taxonomy: infinite loops, cost blowups, cascading tool errors
- [ ] Observability signals that catch each early
- [ ] Graceful degradation: escalate vs retry vs abort
- [ ] Post-mortem habit on trace logs

### 48. Harness engineering ★

**Before:** 47 (and the whole phase) · **Sources:** [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) · [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) · [Osmani — Agent Harness Engineering](https://www.oreilly.com/radar/agent-harness-engineering/)
**Done when:** you dissect a real harness (Claude Code-class) component by component and design a separation pattern for a given workload.

- [ ] Definition: agent = model + harness; harness = prompts, tools, skills, context policies, hooks, sandboxes, subagents, session persistence, permissions
- [ ] Anatomy: loop engine · tool/skill registry (SKILL.md-style packaged skills — anchored in skills you've already authored) · session persistence · lifecycle hooks · permission gate
- [ ] Separation patterns: initializer/coder, writer/reviewer, planner/executor — externalised state that survives context resets
- [ ] Harness vs framework: pre-wired runtime vs assemblable kit; harness-as-a-service (Agent SDKs)
- [ ] Model-harness co-training: same model scores differently across harnesses; moving harnesses unlocks capability the default left behind

### 49. Loop engineering ★

**Before:** 48 · **Sources:** [Osmani — Loop Engineering](https://www.oreilly.com/radar/loop-engineering/) · [IBM — what is loop engineering?](https://www.ibm.com/think/topics/loop-engineering) · [Stop Hand-Holding Your Coding Agent (arXiv)](https://arxiv.org/html/2607.00038v1)
**Done when:** you author a complete loop specification and can name the anti-pattern in a described system.

- [ ] One floor above the harness: systems that drive agents without you prompting each step
- [ ] The loop specification's five parts: trigger · goal · verification gate · stopping rule · memory/ledger
- [ ] Verification ladder: deterministic checks → schema/lint rules → delayed field truth → LLM-as-judge → human checkpoint
- [ ] Named terminal states: success / no-op / blocked / stalled / exhausted — never mistake exhaustion for success
- [ ] Bounded budgets: iteration caps, wall-clock, token ceilings; escalation as a first-class outcome
- [ ] Maker/checker: an external gate that can say no; anti-patterns (self-grading loop, unbounded loop, soft gate, mega-prompt)
- [ ] Guardrail instincts: never let a loop merge; forbidden shortcuts spelled out explicitly

### Project 2 — AI Data Analyst

**Before:** 38–49 · **Done when:** runs from README; second pass inside an agent-harness SDK completed.
**Rules:** agent with SQL, Python-analysis, RAG and charting tools.

- [ ] Agent loop with SQL + analysis + RAG + chart tools
- [ ] HITL gates on anything destructive (from topic 45)
- [ ] Second pass rebuilt inside Claude Agent SDK or OpenAI Agents SDK — note what the harness gave you and what it cost
- [ ] Trace logs kept for every run

---

## Phase 7 — Evaluation

### 50. Why evals are the job

**Before:** 28 (and shipping something) · **Source:** [Hamel Husain — Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
**Done when:** you articulate the CI-for-prompts mindset and start an error-analysis log for one real system.

- [ ] From "looks right" to "measurably works"
- [ ] CI-for-prompts mindset
- [ ] Error analysis as the core daily habit

### 51. Precision and recall

**Before:** 50 · **Source:** [Weaviate — retrieval evaluation metrics](https://weaviate.io/blog/retrieval-evaluation-metrics)
**Done when:** you compute precision/recall on retrieval results and explain the threshold tension.

- [ ] Confusion matrix; why RAG retrieval needs both
- [ ] F1 briefly; precision/recall tension in threshold choices

### 52. Retrieval metrics

**Before:** 51 · **Source:** [Weaviate — retrieval evaluation metrics](https://weaviate.io/blog/retrieval-evaluation-metrics)
**Done when:** hit@k, MRR and NDCG are computed by you on a labelled set, and you say what each punishes.

- [ ] Hit-rate@k, MRR, NDCG — what each punishes
- [ ] Computing them on a small labelled set

### 53. Building an evaluation dataset

**Before:** 52 · **Sources:** [openai/evals build-eval guide](https://github.com/openai/evals) · [Hamel — evals](https://hamel.dev/blog/posts/evals/)
**Done when:** an eval dataset with golden answers exists for your Project 1 corpus, built from realistic queries.

- [ ] Sourcing real queries; golden answers; labelling discipline
- [ ] Coverage vs size; drift over time

### 54. LLM-as-a-judge

**Before:** 53 · **Sources:** [Hamel — LLM-as-a-judge that drives business results](https://hamel.dev/blog/posts/llm-judge/) · [MT-Bench paper](https://arxiv.org/abs/2306.05685) · [Braintrust — what is an LLM-as-a-judge?](https://www.braintrust.dev/articles/what-is-llm-as-a-judge)
**Done when:** a judge is calibrated against your own labels and you can name its biases with examples.

- [ ] Rubric scoring vs pairwise comparison
- [ ] Biases: position, verbosity, self-enhancement
- [ ] Calibrating against human labels; when not to trust it

### 55. Faithfulness, relevance and hallucination metrics

**Before:** 54 · **Source:** [RAGAS docs](https://docs.ragas.io/en/stable/)
**Done when:** claim-level groundedness checks run against your Project 1 answers.

- [ ] Groundedness via claim extraction and verification
- [ ] RAGAS-style automated metrics; what they catch and miss

### 56. Regression testing prompts

**Before:** 53 · **Source:** [promptfoo docs](https://www.promptfoo.dev/docs/intro/)
**Done when:** a prompt change is blocked in CI until the eval suite passes.

- [ ] Prompts as code: versioning, review, snapshot tests
- [ ] Eval suites in CI; blocking merges on regressions

### 57. Evaluating agents — trajectories and outcomes ★

**Before:** 47, 53 · **Sources:** [BFCL](https://gorilla.cs.berkeley.edu/leaderboard.html) · [τ²-bench](https://github.com/sierra-research/tau2-bench)
**Done when:** you design outcome AND trajectory evals for your Project 2 agent and reason about pass^k.

- [ ] Outcome evals (did it finish?) vs trajectory evals (did it get there sanely?)
- [ ] pass^k reliability: why single-run demos lie about agent quality
- [ ] Step-level credit assignment; judging tool-use efficiency
- [ ] Benchmarks (BFCL, τ²-bench) vs building your own task suite
- [ ] Cost-of-eval trade-offs for long-running agents

### 57a. Toxicity and safety metrics

**Before:** 54, 55 · **Sources:** [Perspective API](https://www.perspectiveapi.com/) · [OpenAI — moderation](https://platform.openai.com/docs/guides/moderation) · [DeepEval — toxicity](https://deepeval.com/docs/metrics-toxicity) + [bias](https://deepeval.com/docs/metrics-bias) · [RAGAS — AspectCritic](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/aspect_critic/) · [MT-Bench paper](https://arxiv.org/abs/2306.05685)
**Done when:** DeepEval Toxicity + Bias run at threshold 0.5 on your outputs and you can name why the judge disagrees with Moderation.

- [ ] Perspective attributes (TOXICITY → THREAT), 0–1 scores, sunsetting Dec 2026 — legacy only
- [ ] OpenAI Moderation 13 categories, flagged + category_scores, signals-not-blocking
- [ ] DeepEval opinion-ratio scoring (non-toxic/total); quoted-text and judge-bias limits
- [ ] RAGAS AspectCritic custom safe/unsafe; MT-Bench position/verbosity/self-enhancement biases

### 57b. Offline evals — the CI gate

**Before:** 53 · **Sources:** [Hamel — CI vs production](https://hamel.dev/blog/posts/evals-faq/how-are-evaluations-used-differently-in-cicd-vs-monitoring-production.html) · [Braintrust — evaluate](https://www.braintrust.dev/docs/evaluate) · [Langfuse — core concepts](https://langfuse.com/docs/evaluation/core-concepts) · [OpenAI — evals](https://developers.openai.com/api/docs/guides/evals?api-mode=responses)
**Done when:** a 100+ golden set gates your deploys and a prompt change is blocked until it passes.

- [ ] Dataset (input + expected) + Task + Evaluators → immutable Experiment
- [ ] Deterministic checks first (exact/regex/tool-call), judge only where needed
- [ ] Small curated set (100+, past-bug regressions + edges); reproducibility over coverage

### 57c. Online evals — production monitoring

**Before:** 57b · **Sources:** [Hamel — how often](https://hamel.dev/blog/posts/evals-faq/how-often-should-i-run-my-evals.html) · [Braintrust — score online](https://www.braintrust.dev/docs/evaluate/score-online) · [Langfuse — core concepts](https://langfuse.com/docs/evaluation/core-concepts) · [Anthropic — demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
**Done when:** live traces are sampled + async-scored and one prod failure is promoted into the offline set.

- [ ] No ground truth → reference-free judges + heuristics + human spot-checks
- [ ] Sampling rules (filter + rate + idle timeout); cheap checks 100%, judge nightly sample; CIs on prod metrics
- [ ] Feedback loop: low/high-scoring traces → new offline tests; thumbs up/down as signal

### 57d. A/B testing prompts and models

**Before:** 57b, 78a · **Sources:** [Anthropic — statistical approach](https://www.anthropic.com/research/statistical-approach-to-model-evals) (paper https://arxiv.org/abs/2411.00640) · [Hamel — field guide](https://hamel.dev/blog/posts/field-guide/index.html) · [Eugene Yan — product evals](https://eugeneyan.com/writing/product-evals) · [Braintrust — compare](https://www.braintrust.dev/docs/evaluate/compare-experiments)
**Done when:** two prompts run on the same items with a paired mean-diff + 95% CI and a ship/hold call.

- [ ] Paired design (same items both arms); mean diff + SE + CI; clustered SEs when grouped
- [ ] One evaluator per failure dimension, binary pass/fail; pairwise needs tie label; swap order
- [ ] Sizing: 100 traces floor, 100–200 labelled per mode; Anthropic power analysis over rules-of-thumb

### 57e. Human evaluation and judge calibration

**Before:** 54 · **Sources:** [Hamel — LLM-as-judge guide](https://hamel.dev/blog/posts/llm-judge) · [MT-Bench paper](https://arxiv.org/abs/2306.05685) · [RAGAS — answer correctness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_correctness/) · [Braintrust — human review](https://braintrust.dev/docs/core/human-review) · [openai/evals build-eval](https://github.com/openai/evals/blob/main/docs/build-eval.md)
**Done when:** a judge hits TPR+TNR >0.90 on a held-out test set and you report κ with the confusion matrix.

- [ ] Rubric + binary pass/fail + written critique; expert defines good; critiques seed the judge (+15–20% agreement)
- [ ] Agreement: Cohen κ / Fleiss κ / Krippendorff α; raw agreement lies under imbalance; 0.4–0.6 substantial, ≥0.8 deploy
- [ ] Accuracy (vs reference) vs correctness (F1 + semantic vs ground truth) vs faithfulness (supported/total vs context); BLEU/ROUGE insufficient for open-ended

---

## Phase 8 — LLMOps and production

### 58. Tracing an LLM system

**Before:** 47 · **Sources:** [Langfuse docs](https://langfuse.com/docs) · [OpenLLMetry](https://www.traceloop.com/docs/openllmetry/introduction) · [OTel traces primer](https://opentelemetry.io/docs/concepts/signals/traces/) · [OTel GenAI walkthrough 2026](https://opentelemetry.io/blog/2026/genai-observability/)
**Done when:** spans cover an LLM + tool call path end-to-end and traces answer "where did this run go wrong".

- [ ] Spans across a non-deterministic system; OpenTelemetry carry-over from backend work
- [ ] Token/model attributes on traces; sampling traces for review

### 58a. Agent-trace taxonomy and OTel GenAI semconv

**Before:** 58 · **Sources:** [GenAI spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) · [Agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) · [Client inference span](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/client-inference.md) · [OpenInference semconv](https://raw.githubusercontent.com/Arize-ai/openinference/main/spec/semantic_conventions.md) · [OpenAI Agents tracing](https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md)
**Done when:** you draw an `invoke_agent` root with `chat` + `execute_tool` + `retrieval` children, name what each span carries, and state which `gen_ai.*` names are Development (may break).

- [ ] Trace vs span vs event; `invoke_agent → chat → execute_tool → retrieval` shape; CLIENT vs INTERNAL span kinds
- [ ] Span kinds by name: LLM / TOOL / RETRIEVER (+EMBEDDING/RERANKER) / AGENT / handoff (`from_agent`, `to_agent`); OpenInference `openinference.span.kind`
- [ ] Required vs opt-in attributes: `operation.name`, `provider.name`, `request/response.model`, `usage.input/output_tokens`, `finish_reasons` always on; prompts/completions/tool definitions opt-in (PII off by default)
- [ ] Semconv status: all `gen_ai.*` Development — pin the version; only `server.address/port`, `error.type` Stable
- [ ] Exercise: read one real trace (Langfuse or Phoenix) and map every span to its kind + parent

### 58b. Logs for AI systems

**Before:** 58 · **Sources:** [OTel GenAI 2024 signals](https://opentelemetry.io/blog/2024/otel-generative-ai/) · [Microsoft SFI observability](https://learn.microsoft.com/en-us/security/zero-trust/sfi/observability-ai-systems) · [Langfuse audit logs](https://langfuse.com/docs/administration/audit-logs.md) · [Langfuse data retention](https://langfuse.com/docs/administration/data-retention)
**Done when:** you classify any log line as request / tool / audit, state its retention, and show where PII is redacted.

- [ ] Request logs: identity, timestamp, conversation/run IDs, inputs + responses; content events are opt-in and redactable
- [ ] Tool logs: tool name, args, permissions, outputs + retrieval provenance; exceptions with type/message/stacktrace
- [ ] Audit logs (compliance): immutable who/what/when + before/after JSON for org/project actions; RBAC + export; exempt from trace retention
- [ ] PII boundaries: what never leaves the window unredacted; retention vs forensics trade-off; `flush()` in short-lived jobs

### 58c. Observability platforms hands-on

**Before:** 58, 58a, 58b · **Sources:** [Langfuse docs](https://langfuse.com/docs) · [Phoenix docs](https://arize.com/docs/phoenix) · [LangSmith observability](https://docs.langchain.com/langsmith/observability) · [CloudWatch GenAI](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GenAI-observability.html) · [Azure monitor OpenAI](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/monitor-openai) · [OpenLLMetry supported](https://www.traceloop.com/docs/openllmetry/tracing/supported)
**Done when:** one app you instrumented shows its traces in two backends (e.g. Langfuse + Phoenix or cloud), and you defend which backend fits which constraint.

- [ ] LangSmith: traces/evals/prompts + deploy; closed-source, SDK-native, LangGraph depth; seat + trace pricing
- [ ] Langfuse: MIT self-host parity; OTel-native SDKs; unit = trace/observation/score (no seat fee); prompt versioning + online judges
- [ ] Phoenix (+AX): ELv2 self-host; most OTel-native via OpenInference; eval-first (judge + code + human, span-replay, Datasets & Experiments)
- [ ] Cloud-native: CloudWatch / GCP / Azure for metrics/logs/traces + alarms (not judges); OTLP export; per-client usage + audit via gateway pattern
- [ ] Exercise: instrument one agent loop with OpenLLMetry, export OTLP to Langfuse and Phoenix, compare the same trace in both

### 59. Prompt and model versioning

**Before:** 56 · **Sources:** [PromptLayer docs](https://docs.promptlayer.com/) · Langfuse prompt management
**Done when:** models and prompts are pinned in config and an upgrade runbook exists.

- [ ] Pinning models; silent upgrades as outages
- [ ] Prompt changelogs; config-as-code

### 60. Cost, token and latency monitoring

**Before:** 58 · **Sources:** [Langfuse docs](https://langfuse.com/docs) · [OpenAI — latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)
**Done when:** a dashboard tracks cost/tokens/latency per feature with alert thresholds set.

- [ ] Dashboards that keep an AI product alive
- [ ] Per-feature attribution; alert thresholds

### 60a. Success, failure and TTFT

**Before:** 60, 58a · **Sources:** [GenAI metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md) · [Token metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-token-metrics.md) · [Langfuse cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking.md) · [Phoenix metrics](https://arize.com/docs/phoenix/tracing/llm-traces/metrics) · [Anthropic commerce agents](https://claude.com/blog/the-anatomy-of-effective-commerce-agents)
**Done when:** a dashboard shows latency percentiles + TTFT + cost + error rate per feature, and one alert fires on a real threshold breach.

- [ ] TTFT / first-chunk vs total duration; server `time_to_first_token` / `time_per_output_token`; latency breakdown = Σ over turns (time-to-last-token + tool time)
- [ ] Token counters by input/output and modality; cost = usage × price table (cache_read ~1/10th, cache-write ~1.25×); cost per completed task, not per call
- [ ] Success vs failure: span `status` OK/ERROR + `error.type`; LLM/tool error counts over time; baseline + alert deviations
- [ ] Exercise: cut one prompt's output tokens ~50% and show the latency + cost delta on the dashboard

### 60b. Cost optimization as discipline

**Before:** 60, 60a, 19c · **Sources:** [LiteLLM — Auto Routing](https://docs.litellm.ai/docs/proxy/auto_routing) · [LiteLLM AI Gateway](https://docs.litellm.ai/docs/simple_proxy) · [OpenRouter — Auto Router](https://openrouter.ai/docs/features/model-routing) · [Langfuse cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking.md)
**Done when:** you take one feature's dashboard and cut its cost per completed task with a before/after number, naming what you traded away.

- [ ] Measure: spend per key/team/model; cost per completed task (not per call); cache-hit rate as a cost lever
- [ ] Cut unit cost: tier down (SIMPLE→REASONING), cost-based routing, halve output tokens (≈ halve latency), prompt compression; cache_read ~1/10th, best deployments 90–99% hit
- [ ] Cap spend: virtual-key budgets, per-user quotas, `max_price` / provider budgets, rate + budget-limit fallback nodes
- [ ] Prove: dashboard delta on cost + latency + error rate; classifier cost deducted from auto-router savings

### 61. Caching

**Before:** 27, 59 · **Sources:** [Alephant — caching comparison](https://blog.alephant.io/prompt-caching-vs-semantic-caching-vs-exact-match/) · [Anthropic — prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) · [Redis — semantic caching](https://redis.io/blog/what-is-semantic-caching/)
**Done when:** a cache stack is chosen with each layer's breakage modes written down.

- [ ] Exact, prefix/prompt and semantic caching
- [ ] What each saves; what each breaks (staleness, personalisation leaks)

### 62. Prompt injection and the OWASP LLM Top 10

**Before:** 45 · **Sources:** [OWASP GenAI Top 10 (2026)](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) · [OWASP — sensitive information disclosure](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/) · [Willison — prompt injection explained](https://simonwillison.net/2023/May/2/prompt-injection-explained/) · [lethal trifecta](https://simonwillison.net/2025/jun/16/the-lethal-trifecta/) · [Gandalf CTF](https://gandalf.lakera.ai/)
**Done when:** you win a few Gandalf rounds, apply the lethal-trifecta risk model to Project 2, and identify where its sensitive data could leak.

- [ ] Direct vs indirect injection; exfiltration paths through tools
- [ ] Treat model output as untrusted input — always
- [ ] Sensitive-data boundaries: PII in prompts, retrieval and traces; user-scoped document access; provider retention and deletion policy

### 63. Guardrails beyond injection ★

**Before:** 62 · **Sources:** [NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/) · [NeMo — rail types](https://docs.nvidia.com/nemo/guardrails/latest/about-nemo-guardrails-library/rail-types) · [OpenAI Agents — guardrails](https://openai.github.io/openai-agents-python/guardrails/) · [OpenAI — guardrails & approvals](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals) · [Willison — dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/)
**Done when:** a guardrail pipeline (input filter → schema gate → policy check) is designed with false-positive costs argued.

- [ ] Input filtering, output schema gates, policy checks as pipeline stages
- [ ] Moderation layers; where guardrails sit in the request lifecycle
- [ ] False-positive economics: over-blocking kills utility too
- [ ] Composing guardrails with the harness permission gate (topic 48)
- [ ] NeMo Guardrails rail types: input, dialog, output, retrieval, execution — where each fires
- [ ] OpenAI Agents SDK guardrail placement: input guardrails first, output guardrails last, plus tool-level guardrails around each call

### 62a. Jailbreaking

**Before:** 62 · **Sources:** [OWASP LLM01 — prompt injection](https://owasp.org/www-project-top-10-for-large-language-model-applications/2_0_vulns/LLM01_PromptInjection.html) · [Anthropic — constitutional classifiers](https://www.anthropic.com/news/constitutional-classifiers) · [Jailbreaking survey](https://arxiv.org/abs/2501.18837)
**Done when:** you classify a jailbreak attempt by family, explain why a classifier layer catches what a prompt filter misses, and name the residual risk.

- [ ] Jailbreak vs prompt injection: same surface, different goal (bypass policy vs hijack behaviour)
- [ ] Attack families: role-play/persona, encoding/obfuscation, many-shot, crescendo, refusal suppression
- [ ] Defence layers: input classifiers, constitutional classifiers, output moderation; why no single layer holds
- [ ] Why jailbreaks are never "solved" — refusal is learned behaviour on the same weights as capability

### 62b. AI red teaming

**Before:** 62, 62a · **Sources:** [OWASP GenAI red teaming guide](https://genai.owasp.org/resource/genai-red-teaming-guide/) · [Microsoft AI red team](https://learn.microsoft.com/en-us/security/ai-red-team/) · [PyRIT](https://microsoft.github.io/PyRIT/) · [lethal trifecta](https://simonwillison.net/2025/jun/16/the-lethal-trifecta/) · [Gandalf CTF](https://gandalf.lakera.ai/) · [Red-teaming LMs paper](https://arxiv.org/abs/2302.12173)
**Done when:** you run a structured red-team pass over Project 2, log findings by severity, and turn each into a regression test.

- [ ] Red teaming vs traditional pentesting: probabilistic, non-deterministic, no single "fixed" state
- [ ] Scope: model, system prompt, tools, retrieval, agent loop; the lethal trifecta as a scoping lens
- [ ] PyRIT orchestration: attack objectives, converters, scorers; automating the loop
- [ ] Findings → severity → regression test; red-team output feeds the eval suite (56)
- [ ] Exercise: run Gandalf to its hardest level, then red-team your own Project 2 prompt

### 62c. Data leakage and PII detection

**Before:** 62 · **Sources:** [OWASP LLM02 — sensitive information disclosure](https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure/) · [Presidio](https://presidio.dataprivacystack.org/) · [Presidio analyzer](https://data-privacy-stack.github.io/presidio/analyzer/) · [Presidio supported entities](https://microsoft.github.io/presidio/supported_entities/) · [OpenAI — your data](https://platform.openai.com/docs/guides/your-data) · [Microsoft SFI — observability](https://learn.microsoft.com/en-us/security/zero-trust/sfi/observability-ai-systems)
**Done when:** PII is detected and redacted at ingress and egress of Project 2, and the provider retention/deletion posture is written down.

- [ ] Leakage paths: training data, system prompt, retrieval corpus, traces/logs, tool outputs
- [ ] PII detection with Presidio: analyzer (entities, recognizers, confidence) + anonymizer (redact/mask/replace)
- [ ] Where to redact: pre-prompt, pre-log, pre-trace; why post-hoc redaction is too late
- [ ] Provider data policy: retention windows, training opt-out, zero-data-retention tiers; deletion on request
- [ ] Exercise: run Presidio over a sample of your own logs and measure false positives/negatives

### 62d. Secrets management

**Before:** 16, 62 · **Sources:** [OWASP secrets management cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) · [OWASP FastAPI security cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/FastAPI_Security_Cheat_Sheet.html) · [OWASP logging cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
**Done when:** no secret lives in code or logs, keys rotate without a redeploy, and a leaked key has a documented blast radius.

- [ ] Secret vs config vs credential; never in git, never in prompts, never in traces
- [ ] Storage: env injection, secret managers (Vault/cloud KMS), sealed secrets; per-environment separation
- [ ] Rotation and revocation: short-lived tokens, key IDs, the runbook for a leaked key
- [ ] Log hygiene: scrub API keys/tokens from request, tool and error logs (58b)
- [ ] Exercise: grep your repo and logs for key patterns; wire a pre-commit secret scanner

### 62e. Tool permissions and least privilege

**Before:** 45, 48 · **Sources:** [Claude Code — permissions](https://code.claude.com/docs/en/permissions)
**Done when:** every tool in Project 2 declares its permission scope, and the default is deny with explicit allow.

- [ ] Least privilege for tools: read vs write vs execute; per-tool allow/deny/ask
- [ ] Permission scopes: filesystem paths, network egress, shell commands; allowlists over blocklists
- [ ] Human-in-the-loop approval for destructive/irreversible actions; the harness gate (48)
- [ ] Prompt injection turns a permitted tool into an attack primitive — scope limits blast radius

### 62f. Agent sandboxing

**Before:** 42, 48 · **Sources:** [Claude Code — sandboxing](https://code.claude.com/docs/en/sandboxing) · [Claude Code — sandbox environments](https://code.claude.com/docs/en/sandbox-environments) · [OpenAI — agent sandboxes](https://developers.openai.com/api/docs/guides/agents/sandboxes)
**Done when:** an agent executes untrusted code in an isolated environment with no host or network escape, and you can state the isolation boundary.

- [ ] Why sandbox: code execution, untrusted tool output, blast-radius containment
- [ ] Isolation levels: process, container, microVM, gVisor; filesystem + network egress controls
- [ ] Ephemeral vs persistent sandboxes; state, secrets and credentials inside the boundary
- [ ] Escape modes: network exfiltration, resource exhaustion, host mounts; how each is closed
- [ ] Exercise: run a code-executing agent in a container with egress denied and prove the boundary holds

### 62g. MCP security

**Before:** 18 · **Sources:** [MCP — authorization spec](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) · [MCP — security best practices](https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices)
**Done when:** an MCP server you build enforces OAuth 2.1, validates tokens, and resists the documented attack classes.

- [ ] OAuth 2.1 authorization: resource server, protected resource metadata, token audience binding
- [ ] Token handling: no token passthrough, validate audience/issuer, short-lived + refresh
- [ ] Attack classes: confused deputy, token theft, session hijacking, malicious server, tool poisoning
- [ ] Trust boundary: a third-party MCP server is untrusted code with tool access — scope it (62e)

### 62h. Rate limiting for production

**Before:** 19 · **Sources:** [OpenAI — rate limits](https://developers.openai.com/api/docs/guides/rate-limits) · [Anthropic — rate limits](https://docs.anthropic.com/en/api/rate-limits)
**Done when:** Project 2 enforces per-user and per-key limits, backs off on 429s, and degrades gracefully under load.

- [ ] Provider limits: RPM/TPM, tokens-per-day, concurrency; headers and 429 semantics
- [ ] Client-side limiting: token buckets, per-user quotas, queueing; retry with exponential backoff + jitter
- [ ] Cost as a limit: budget caps, per-request token ceilings, abuse detection
- [ ] Graceful degradation: queue vs shed vs fallback model; what the user sees at the limit

### 64. Deployment

**Before:** 16, 19 · **Sources:** [FastAPI in containers](https://fastapi.tiangolo.com/deployment/docker/) · [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)
**Done when:** your containerised service is deployed with health checks green.

- [ ] Containerising the FastAPI service; env/secrets handling
- [ ] Scaling async workers; health checks
- [ ] Blue-green notes for model swaps

### Project 3 — Production hardening

**Before:** 50–64 · **Done when:** Project 1 or 2 survives the checklist below.

- [ ] Auth + rate limiting
- [ ] Tracing wired (58)
- [ ] Evals gating deploys in CI (56)
- [ ] Injection threat model documented (62)
- [ ] Test that one user cannot retrieve another user's documents; redact sensitive trace fields and document data-retention choices (62)

---

## Phase 9 — The theory underneath, and the job

### 65. Neural networks and gradient descent

**Before:** everything above · **Sources:** [3Blue1Brown — but what is a neural network?](https://www.youtube.com/watch?v=aircAruvnKk) · [Karpathy — building micrograd](https://www.youtube.com/watch?v=VMj-3S1tku0)
**Done when:** you explain training at interview depth without hand-waving loss or descent.

- [ ] Neurons, weights, activations; loss; descent intuition
- [ ] Enough to make fine-tuning talk honest, no more

### 66. The Transformer

**Before:** 65 · **Sources:** [3Blue1Brown — transformers](https://www.youtube.com/watch?v=wjZofJX0v4M) · [Alammar — illustrated transformer](https://jalammar.github.io/illustrated-transformer/)
**Done when:** you walk tokens→logits and argue why recurrence lost.

- [ ] Tokens → embeddings → blocks → logits
- [ ] Residual-stream intuition; why it replaced recurrence (parallelism, long-range paths)

### 67. Attention

**Before:** 66 · **Sources:** [3Blue1Brown — attention step-by-step](https://www.youtube.com/watch?v=eMlx5fFNoYc) · [Annotated Transformer](https://nlp.seas.harvard.edu/annotated-transformer/)
**Done when:** attention scores computed by hand on a toy example, matching code output.

- [ ] Q/K/V computed by hand on a tiny example
- [ ] Softmax weighting; causal masks; multi-head

### 68. Fine-tuning vs RAG vs prompting

**Before:** everything · **Sources:** [Applied LLMs](https://applied-llms.org/) · Chip Huyen, *AI Engineering* (Paid)
**Done when:** the three-way decision is defended with data-readiness and maintenance-burden axes, plus flips.

- [ ] Knowledge vs behaviour vs cost axes; data readiness; maintenance burden
- [ ] A decision answerable only now that everything else exists

### 68a. Pretrain vs SFT vs RAG + decoding/KV-cache (decision depth)

**Before:** 7, 66, 68 · **Sources:** [HF LLM course ch1/4](https://huggingface.co/learn/llm-course/chapter1/4) · [Karpathy — Intro to LLMs](https://www.youtube.com/watch?v=zjkBMFhNj_g) · [HF LLM course ch11/3 SFT](https://huggingface.co/learn/llm-course/chapter11/3) · [HF — advanced RAG](https://huggingface.co/learn/cookbook/advanced_rag) · [HF — how to generate](https://huggingface.co/blog/how-to-generate) · [HF — generation strategies](https://huggingface.co/docs/transformers/en/generation_strategies) · [HF — KV-cache](https://huggingface.co/docs/transformers/en/kv_cache)
**Done when:** you defend pretrain vs fine-tune vs RAG per scenario and predict temperature/top-p effects + `do_sample` requirement in one sentence. Decision depth only — no pretraining labs per mission scope.

- [ ] Pretraining: self-supervised LM (causal vs masked) on huge corpus over weeks; shared weights save compute/carbon — why not to pretrain
- [ ] Anchor: base "dreams" documents; finetune directs into assistant dreams, does not fix hallucinations; retrieval working-memory > memory
- [ ] SFT only if: prompting insufficient, precise schema/format, domain jargon, or smaller-tuned beats large-general; else RAG for dynamic/proprietary/cited (tune chunk/top_k/rerank; lost-in-middle); hybrid legit
- [ ] Decoding: greedy default vs sampling; temperature `<0.4` factual / `>0.8` creative (needs `do_sample=True`); top-k fixed vs top-p adaptive; beam for MT/summary not chat
- [ ] KV-cache 5-min: memoize past K/V — per-step quadratic → linear, memory linear; `use_cache=True`; inference-only

### 69. AI system design interviews

**Before:** 68 · **Sources:** [ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide) · [Eugene Yan — how to interview](https://eugeneyan.com/writing/how-to-interview/)
**Done when:** you deliver a full RAG-or-agent design out loud under time constraints.

- [ ] Designing RAG/agent systems out loud under constraints
- [ ] Cost/latency budgets; failure talk; defending trade-offs

### 70. Portfolio and interview prep

**Before:** Projects 1–3, 69 · **Sources:** [Applied LLMs](https://applied-llms.org/) · [Latent Space](https://www.latent.space/about)
**Done when:** a stranger can run all three projects from their READMEs, and your stories are rehearsed.

- [ ] Packaging the three projects so a hiring manager can run them
- [ ] Demo scripts; project stories; mock interview loops

---

## Track B — ML foundations (interleaved) *(added 2026-08-25)*

Serves the service-company interview door directly. Interleaving rule and dependencies are at the
top of CURRICULUM.md; every Done-when below is an interview answer given out loud.

### 71. NumPy arrays

**Before:** none · **Sources:** [NumPy — the absolute basics for beginners](https://numpy.org/doc/stable/user/absolute_beginners.html)
**Done when:** you rewrite a loop as a vectorized expression and explain where the speedup comes from.

- [x] `ndarray` vs Python list: homogeneous dtype, fixed size, rectangular shape *(distinction explained in own words — `chats/71.numpy.md` Q5)*
- [x] Creating arrays (`array`, `zeros`, `arange`, `linspace`); shape/ndim/size/dtype attributes *(arange/linspace predictions Q6 all correct; rows-vs-ndim slip corrected — LR-0008)*
- [x] Indexing, slicing, boolean masks; views vs copies (and why a view mutation bites) *(Q7–Q11; mask-result-shape confusion corrected in chat; view mutation demonstrated twice — Q11 and mini-challenge Q19)*
- [x] Vectorized elementwise ops replacing loops; aggregation with and without `axis` *(axis sums Q13–15 correct; speedup explanation refined to "the loop moved into compiled code"; done-when met in mini-challenge Q17–Q20, 2026-09-07)*
- [x] Exercise: vectorize a loop-based function from your own code, by hand *(mini-challenge Q17–18: `prices * 1.18`, values predicted correctly)*

### 72. Matrix operations and broadcasting

**Before:** 71 · **Sources:** [NumPy absolute basics](https://numpy.org/doc/stable/user/absolute_beginners.html) (broadcasting + transpose sections)
**Done when:** you predict output shapes of a chain of operations on paper, then verify in code.

- [x] Broadcasting rules: dimensions must match or be 1; the classic `ValueError` *(Q5–Q7 incl. right-to-left conflict identification; "broadcasting never changes the result shape" slip corrected — recheck owed, LR-0009)*
- [x] Elementwise `*` vs matrix multiplication `@`; dot product by hand *(final no-Copilot exercise: `A*B` and `A@B` both computed correctly by hand, 2026-09-07)*
- [x] Transpose (`.T`), reshape, newaxis for row/column vectors *(Q4 and Q11 correct; 1-D `.T` no-op caveat taught at the end of the chat)*
- [x] Why this matters downstream: an embedding is a row vector; attention is matmuls all the way down *(motivated via `Q @ K.T` in chat 72; the applied use is verified at lessons 22–23)*

### 73. Pandas I: selection and filtering

**Before:** 71 · **Sources:** [10 minutes to pandas](https://pandas.pydata.org/docs/user_guide/10min.html) (object creation → boolean indexing)
**Done when:** you answer three data questions from a raw CSV without looking anything up.

- [ ] Series vs DataFrame; one dtype per column; reading CSVs with `read_csv`
- [ ] Column selection; `loc` (label) vs `iloc` (position)
- [ ] Boolean filtering: masks, multiple conditions with `&`/`|`, `isin`
- [ ] Adding/modifying columns; `describe`, `head`, `value_counts`

### 74. Pandas II: groupby, merge/join, missing data

**Before:** 73 · **Sources:** [10 minutes to pandas](https://pandas.pydata.org/docs/user_guide/10min.html) (merge, grouping, missing data sections)
**Done when:** you write a rolling average AND explain LEFT vs INNER join out loud — both are real TCS/Wipro interview questions.

- [ ] Split-apply-combine: `groupby` + aggregation, grouping by multiple columns
- [ ] `concat` vs `merge`; inner/left/right/outer joins and what each keeps
- [ ] Missing data: `isna`, `dropna`, `fillna`; why "20% missing in a key column" has no single right answer
- [ ] Rolling windows: `.rolling(n).mean()` and edge behaviour at series start

### 75. Basic visualization and EDA

**Before:** 73 · **Sources:** [10 minutes to pandas](https://pandas.pydata.org/docs/user_guide/10min.html) (plotting section)
**Done when:** every plot you make answers a stated question about the data.

- [ ] Histograms for distributions; scatter for relationships; bar for categories
- [ ] pandas `.plot()` over matplotlib plumbing; labelling axes honestly
- [ ] The EDA habit: look before you model — outliers, skew, missingness patterns

### 76. Descriptive statistics

**Before:** none · **Sources:** [StatQuest](https://www.statquest.org/) (statistics videos index)
**Done when:** you choose mean or median for a skewed dataset and defend the choice out loud.

- [ ] Mean vs median vs mode; when the mean lies
- [ ] Variance and standard deviation — what "spread" means mechanically
- [ ] Common distributions at intuition level: normal, skewed, uniform
- [ ] Sampling: sample vs population, why bigger samples help

### 77. Probability, conditional probability, Bayes theorem

**Before:** 76 · **Sources:** [StatQuest](https://www.statquest.org/)
**Done when:** you solve a base-rate problem out loud without notes.

- [ ] Probability as long-run frequency; independent ≠ mutually exclusive
- [ ] Conditional probability from a contingency table
- [ ] Bayes theorem derived from the definition of conditional probability — not memorized
- [ ] Why base rates dominate: the medical-test question interviews love

### 78. Correlation and covariance

**Before:** 76 · **Sources:** [MLU-Explain](https://mlu-explain.github.io/) visual essays · [scikit-learn user guide §2.6](https://scikit-learn.org/stable/modules/covariance.html)
**Done when:** you explain covariance → correlation normalization and name something correlation cannot tell you.

- [ ] Covariance: sign gives direction, magnitude compares nothing
- [ ] Pearson r: normalized covariance, range −1..1
- [ ] Correlation ≠ causation; linear-only sensitivity; Anscombe's-quartet intuition

### 78a. Statistical inference and uncertainty

**Before:** 76, 77 · **Sources:** [NIST — hypothesis tests](https://www.itl.nist.gov/div898/handbook/prc/section2/prc24.htm) · [NIST — confidence intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) · [SciPy — bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
**Done when:** you compare two model or product results from a sample, report an uncertainty interval, and explain what a p-value does and does not say.

- [ ] Sample estimates vary: distinguish an observed score from the unknown population value
- [ ] Null hypothesis and p-value: probability of data at least this extreme *assuming the null*, not probability the null is true
- [ ] Confidence intervals: repeated-sampling coverage, not a probability assigned to a fixed parameter; practical vs statistical significance
- [ ] Exercise: bootstrap an interval for a score difference on held-out examples; state what the data cannot establish

### 79. Linear regression, loss functions, gradient descent

**Before:** 72, 76 · **Sources:** [MLU-Explain — Linear Regression](https://mlu-explain.github.io/) · [StatQuest](https://www.statquest.org/)
**Done when:** you hand-run 3 gradient-descent steps on paper and say what too-large/too-small learning rates do.

- [ ] The line, residuals, MSE as loss; why squaring
- [ ] Gradient descent mechanics: gradient → step opposite → repeat
- [ ] Learning rate: divergence vs crawl — the interview's favourite hyperparameter question
- [ ] Train/test split: fitting ≠ generalizing (first contact with topic 85's ideas)

### 79a. Features pipeline: scaling, encoding, leakage-safe assembly

**Before:** 73, 74 · **Sources:** [scikit-learn — preprocessing](https://scikit-learn.org/stable/modules/preprocessing.html) · [scikit-learn — compose](https://scikit-learn.org/stable/modules/compose.html) · [scikit-learn — common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) · [MLU-Explain — train/test/validation](https://mlu-explain.github.io/train-test-validation/) · [scikit-learn — feature selection](https://scikit-learn.org/stable/modules/feature_selection.html)
**Done when:** you build a `ColumnTransformer + Pipeline` on a mixed-type DataFrame that splits first, fits train-only, handles unseen categories, includes `SelectKBest`, and scores on untouched test.

- [ ] Scaling: `StandardScaler` vs `MinMax/MaxAbs` vs `Normalizer` (per-feature vs per-sample) vs `RobustScaler`; fit-train / transform-test
- [ ] Encoding: ordinal (ordered only) vs one-hot (nominals); `drop` for collinearity; `handle_unknown='ignore'` for unseen categories
- [ ] Assembly: `ColumnTransformer` per-column transforms inside a leakage-safe `Pipeline`; joint grid-search
- [ ] Leakage rules: never `fit` on test; `SelectKBest`-in-pipeline; `Pipeline` inside `cross_val_score` (bridges to 85)

### 80. Logistic regression and classification

**Before:** 79 · **Sources:** [MLU-Explain — Logistic Regression](https://mlu-explain.github.io/) · [scikit-learn user guide §1.1.11](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression)
**Done when:** you explain why accuracy is already the wrong metric here — before metrics are formally taught.

- [ ] Sigmoid squashes scores to probabilities; decision boundary at a threshold
- [ ] Log-loss vs MSE for classification; maximum-likelihood at intuition level
- [ ] Classification vs regression as problem shapes
- [ ] Multiclass in one line: one-vs-rest idea only

### 81. Regularization and the bias-variance tradeoff

**Before:** 80 · **Sources:** [scikit-learn user guide — Ridge/Lasso](https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification) · [MLU-Explain — bias-variance essay](https://mlu-explain.github.io/)
**Done when:** you give the L1-vs-L2 answer out loud — a real Infosys interview question.

- [ ] Overfitting vs underfitting; training vs test error curves
- [ ] L2 (Ridge) shrinks smoothly; L1 (Lasso) drives coefficients to exactly zero
- [ ] Sparsity as feature selection; when each wins
- [ ] Hyperparameters as knobs that set this tradeoff

### 82. Decision trees

**Before:** 80 · **Sources:** [MLU-Explain — Decision Trees](https://mlu-explain.github.io/) · [scikit-learn user guide §1.10](https://scikit-learn.org/stable/modules/tree.html)
**Done when:** you trace a tree's splits on a toy table and explain why depth causes overfitting.

- [ ] Splits chosen by entropy/information gain (or Gini) — computed by hand once
- [ ] Depth, leaves, purity; unpruned trees memorize
- [ ] Trees handle mixed types, need no scaling — their practical appeal

### 83. Random forests, gradient boosting, XGBoost

**Before:** 82 · **Sources:** [MLU-Explain — Random Forests](https://mlu-explain.github.io/) · [scikit-learn user guide §1.11](https://scikit-learn.org/stable/modules/ensemble.html)
**Done when:** you contrast bagging and boosting out loud in under a minute.

- [ ] Bagging: bootstrap + vote; forests decorrelate trees via feature subsampling
- [ ] Boosting: sequential error-fixing; gradient-boosting framing; XGBoost as the tuned industrial version
- [ ] Feature importance: impurity-based vs permutation — and how misleading the first can be
- [ ] When a forest beats boosting and vice versa

### 83a. Unsupervised ML: clustering + PCA

**Before:** 72, 76 · **Sources:** [StatQuest video index](https://statquest.org/video_index.html) · [StatQuest — K-means](https://youtu.be/4b5d3muPQmA) · [scikit-learn §2.3 clustering](https://scikit-learn.org/stable/modules/clustering.html) · [sklearn — cluster comparison](https://scikit-learn.org/stable/auto_examples/cluster/plot_cluster_comparison.html) · [sklearn §2.5.1 PCA](https://scikit-learn.org/stable/modules/decomposition.html) · [sklearn §1.13 feature selection](https://scikit-learn.org/stable/modules/feature_selection.html)
**Done when:** you recite Lloyd steps + inertia + 2 failure modes by hand, state hierarchical linkage in one sentence, and contrast PCA vs feature selection out loud.

- [ ] K-means: pick k → assign-to-nearest-centroid → recompute means → repeat; inertia criterion; elbow/silhouette for choosing k
- [ ] Failure modes: non-spherical/elongated clusters; Euclidean inflation in high-D (run PCA first); cluster-comparison visual
- [ ] Hierarchical: bottom-up agglomerative, Ward/complete/average/single linkage, dendrogram read
- [ ] PCA vs selection: new orthogonal variance-max axes (center-not-scale, `whiten` for downstream) vs subset of originals (`SelectKBest`/`SelectFromModel`)

### 83b. Model serving: versioned artifact → FastAPI online vs batch

**Before:** 16, 64, 83 · **Sources:** [sklearn — model persistence](https://scikit-learn.org/stable/model_persistence.html) · [PyTorch — saving/loading](https://docs.pytorch.org/tutorials/beginner/saving_loading_models) · [ONNX intro](https://onnx.ai/onnx/intro/) · [FastAPI — Docker](https://fastapi.tiangolo.com/deployment/docker/)
**Done when:** a versioned `models/iris-v1.joblib` serves at `POST /predict` with `model_version` in the response, and you defend batch vs online.

- [ ] sklearn: `joblib dump/load`, `protocol=5`, same-version envs, versioned filename (`-v1`); `skops.io` secure alt
- [ ] PyTorch contrast: `state_dict` + re-instantiate + `load_state_dict(weights_only=True)` + `model.eval()`; whole-model pickle brittle
- [ ] ONNX bridge: train anywhere → `.onnx` → Runtime without Python; version identically for both paths
- [ ] Lab: load once at startup, Pydantic validate, `POST /predict`; batch = scheduled bulk scores (throughput), online = per-request (latency)

### Mini-project B — end-to-end classical ML project

**Before:** 71–83 · **Done when:** a stranger can rerun your notebook top-to-bottom and you deliver its story STAR-format without notes.

- [ ] Pick a tabular dataset with real messiness (missing values, mixed types)
- [ ] pandas EDA → one simple model → one ensemble → honest comparison with proper metrics
- [ ] A README + walkthrough that answers "describe a complex project end to end" — the universal interview question

### 84. Evaluation I: confusion matrix, precision/recall/F1, ROC-AUC

**Before:** 80, 83 · **Sources:** [scikit-learn user guide §3.4](https://scikit-learn.org/stable/modules/model_evaluation.html) · [MLU-Explain — ROC & AUC, Precision & Recall essays](https://mlu-explain.github.io/)
**Done when:** given a scenario, you pick precision or recall and defend it.

- [ ] Confusion matrix: TP/FP/TN/FN as the atom of every classification metric
- [ ] Accuracy's failure on imbalance; precision vs recall tension; F1 as their compromise
- [ ] ROC curve and AUC: ranking quality, threshold-free view
- [ ] Threshold choice as a business decision, not a default

### 85. Evaluation II: MAE/MSE/RMSE, cross-validation, leakage, class imbalance

**Before:** 79, 84 · **Sources:** [scikit-learn user guide §3.1](https://scikit-learn.org/stable/modules/cross_validation.html) · [§12.2 data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) · [MLU-Explain — Cross-Validation, Train/Test essays](https://mlu-explain.github.io/)
**Done when:** you diagnose a leaked-feature setup on sight and say what SMOTE trades away.

- [ ] Regression metrics: MAE vs MSE vs RMSE — outlier sensitivity and units
- [ ] K-fold cross-validation: why one split lies; stratification
- [ ] Data leakage: scaling/imputation before splitting, target leakage; the silent killer
- [ ] Class imbalance: SMOTE vs class weights — trade-offs out loud (a real Infosys question)

### 86. Neural networks

**Before:** 79 · **Sources:** [3Blue1Brown — neural networks series](https://www.3blue1brown.com/topics/neural-networks) · [scikit-learn user guide §1.17 MLP](https://scikit-learn.org/stable/modules/neural_networks_supervised.html)
**Done when:** you explain backpropagation mechanically at interview depth, no hand-waving.

- [ ] Neurons, weights, layers, activation functions and why non-linearity is load-bearing
- [ ] Forward propagation as nested matrix multiplications (topic 72 pays off)
- [ ] Loss; backpropagation as chain rule through the graph; gradient descent revisited from topic 79
- [ ] *(Subsumes Track-A lesson 65 — consolidation there, not re-teaching.)*

### 87. PyTorch

**Before:** 86 · **Sources:** [PyTorch — Learn the Basics](https://pytorch.org/tutorials/beginner/basics/intro.html)
**Done when:** you write the full training loop from memory, no tutorial open.

- [ ] Tensors: NumPy intuition carries over; `.requires_grad` and autograd by example
- [ ] `Dataset`/`DataLoader`: batching, shuffling, why both matter
- [ ] `nn.Module`: defining a model; optimizers; loss functions
- [ ] Training loop + validation loop; overfit-one-batch debugging trick
- [ ] Checkpoints: save/load model state; resuming training

### 87a. GPU Basics for PyTorch

**Before:** 86 · **Sources:** [NVIDIA — CUDA intro](https://docs.nvidia.com/cuda/cuda-programming-guide/01-introduction/introduction.html) · [PyTorch — CUDA semantics](https://docs.pytorch.org/docs/2.14/notes/cuda.html) · [PyTorch — AMP](https://docs.pytorch.org/docs/2.14/amp.html) · [PyTorch — AMP recipe](https://docs.pytorch.org/tutorials/recipes/recipes/amp_recipe.html)
**Done when:** you explain the batch-size VRAM limit and its OOM fixes out loud, with `memory_allocated()` evidence.

- [ ] CUDA vs CPU: thousands of parallel threads + bandwidth for matmuls/convs
- [ ] Pattern: `is_available()` + `device('cuda')` + `.to(device)`; async exec; `memory_allocated()/max_memory_allocated()/empty_cache()`
- [ ] VRAM: weights + activations + grads + optimizer state scale with batch; caching allocator vs `nvidia-smi` reserved
- [ ] AMP: `autocast(device_type="cuda")` around forward+loss only, fast ops fp16/bf16 + reductions fp32; `GradScaler` vs underflow; dims ×8 for Tensor Cores

### 88. CNNs conceptually

**Before:** 86 · **Sources:** pending verification at lesson-authoring time (candidate: CS231n notes)
**Done when:** you explain what a convolution computes and why pooling exists, in interview depth.

- [ ] Convolution: local receptive fields, weight sharing, feature maps
- [ ] Pooling: downsampling, translation tolerance
- [ ] Feature hierarchies: edges → textures → parts → objects
- [ ] Conceptual only per mission scope — no training CNNs required

### 89. Sequence models conceptually

**Before:** 86 · **Sources:** pending verification at lesson-authoring time (candidate: Colah — Understanding LSTM Networks)
**Done when:** you explain what problem RNNs solve and which two problems LSTM gates fix.

- [ ] Sequences need state: the RNN loop, unrolled
- [ ] Vanishing gradients over long sequences — the failure boundary
- [ ] LSTM gates: forget/input/output as learned information control
- [ ] Why recurrence lost to attention (parallelism, long-range paths) — sets up topic 90

### 90. Transformer architecture bridge

**Before:** 72, 87, 89 · **Sources:** [3Blue1Brown — transformers](https://www.youtube.com/watch?v=wjZofJX0v4M) · [Alammar — Illustrated Transformer](https://jalammar.github.io/illustrated-transformer/) *(already verified for topics 66–67)*
**Done when:** you draw the whole architecture from tokens to logits and narrate it.

- [ ] Tokenization (lesson 1) → embeddings (topics 22, 72) → positional encoding: why order must be injected
- [ ] Self-attention: Q/K/V computed by hand on a tiny example
- [ ] Encoder vs decoder roles; masking; stacked blocks with residuals
- [ ] The bridge answer: this architecture serves *both* your interview doors at once

---

## Revision log

- **2026-10-13 (AI/ML-foundation gap-fill)** — added topics 79a (features pipeline: scaling/encoding/ColumnTransformer/leakage-safe, prereq to 79/85), 83a (unsupervised: k-means/hierarchical + PCA vs selection), 83b (model serving: joblib/state_dict + FastAPI online vs batch), 87a (GPU basics: CUDA/VRAM/AMP, prereq to 87), 68a (pretrain-vs-SFT-vs-RAG + decoding/KV-cache decision depth, extends 68 within mission scope). All sources fetched and verified same day (see raw/ai-ml-foundation-gaps-research.md). No renumbering.
- **2026-10-13 (LLM-application-engineering gap-fill)** — added topics 19a (fallbacks/failover, three types + attribution), 19b (LLM gateways, virtual keys + dynamic routes), 19c (production model routing, strategies + auto tiers + session affinity), 60b (cost optimization, measure→cut→cap→prove). All sources fetched and verified same day (see raw/llm-app-eng-gaps-research.md). No renumbering.
- **2026-10-13 (security gap-fill)** — added topics 62a–62h: jailbreaking, AI red teaming, data leakage + PII detection, secrets management, tool permissions + least privilege, agent sandboxing, MCP security, rate limiting for production. Expanded 63 with NeMo rail types and OpenAI Agents SDK guardrail placement. No renumbering.
- **2026-10-13 (observability gap-fill)** — added topics 58a (agent-trace taxonomy + OTel semconv), 58b (request/tool/audit logs), 58c (platforms hands-on), 60a (success/failure + TTFT). Fixed 58's `OpenLLetry` typo → OpenLLMetry; replaced moved OTel URL with repo + traces primer. No renumbering.
- **2026-10-13 (workflow/state/routing gap-fill)** — expanded 39 (five workflow primitives, static-vs-dynamic routing), 40 (state object, persistence, checkpoints vs memory, context assembly), 42 (tool selection), 44 (conditional edges, loops, fan-out as graph constructs), 46 (agent selection, dynamic + model routing). No renumbering.
- **2026-10-13 (agent/MCP gap-fill)** — expanded 18 (tools-vs-resources-vs-prompts, client build, OAuth 2.1 auth), 40 (episodic/semantic/user memory), 41 (ReAct + Reflexion), 42 (six tool classes). Done-whens tightened to test the new boxes; no renumbering.
- **2026-10-13 (RAG gap-fill)** — added topics 34a–34h: ingestion parsing, OCR, ingest-time metadata enrichment, parent-child retrieval, corrective RAG, self-RAG, graph RAG, multimodal RAG. All 34a–34h sources fetched and verified same day (see RESOURCES.md); 34c reused already-verified links.
- **2026-08-25 (Track B added)** — topics 71–90 (ML foundations) appended for the mission expansion
  to service-company interviews; progress map row and learner-profile blurb updated. All cited
  sources machine-verified 2026-08-25 except two marked "pending verification" (88, 89). Topics
  84–86 partially subsume Track-A lessons 51 and 65–67 — see CURRICULUM.md revision history.
- **2026-08-22 (checklist edition)** — converted to checkbox format; added learner-profile handoff
  so any teaching agent can pick up a single topic cold; added Done-when gates and the completion
  protocol. Finishing this file == finishing the curriculum.
- **2026-08-22 (initial)** — created alongside the curriculum expansion (59 → 70 lessons). Added:
  MCP (18), reasoning models & test-time compute (20), Context engineering phase (35–37), Agentic
  RAG (43), Multi-agent orchestration (46), Harness engineering (48), Loop engineering (49),
  Evaluating agents (57), Guardrails beyond injection (63). All ★ topics verified against primary
  sources the same day.

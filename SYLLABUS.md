# SYLLABUS
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

### 2. Next-token prediction

**Before:** 1 · **Sources:** [Karpathy — Intro to LLMs (1h)](https://www.youtube.com/watch?v=zjkBMFhNj_g) · [State of GPT](https://www.youtube.com/watch?v=bZQun8Y4L2A)
**Done when:** you explain why Copilot is sometimes confidently wrong or overly verbose purely from next-token mechanics — "bug" and "bad model" are banned words in the answer.

- [ ] The single mechanism: output a distribution over the next token, sample, append, repeat
- [ ] Autoregression — generated text becomes input text
- [ ] Why observed Copilot behaviours (confident wrongness, verbosity, losing the thread) fall out of this one loop
- [ ] Training objective vs inference behaviour — one line only; depth lands in topic 65

### 3. The context window, precisely

**Before:** 2 · **Sources:** [Karpathy — Deep Dive into LLMs](https://www.youtube.com/watch?v=7xTGNNLPyMI) · [OpenAI — tokens & counting](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)
**Done when:** you predict what happens (error vs truncation vs cost growth) when a conversation grows past the limit, and can explain truncation vs compaction mechanically.

- [ ] Input + output share one budget per request
- [ ] What happens at overflow: hard error vs silent truncation, depending on API
- [ ] Why finite: attention cost grows with length
- [ ] Truncation vs compaction — formalising what you already know informally
- [ ] "The model forgot" is mechanical: never saw it, or attention degraded

### 4. Statelessness

**Before:** 3 · **Sources:** [Chip Huyen — Notes on LLM Engineering](https://huyenchip.com/2023/04/11/llm-engineering.html)
**Done when:** you narrate where conversation state actually lives and why cost grows on every turn even when nothing new is asked.

- [ ] The API has no memory between calls; conversation is a list *you* resend each turn
- [ ] History growth = cost growth, paid on every turn
- [ ] Things that look like memory but aren't: chat products, cached prefixes, stored threads
- [ ] Implication chain: statelessness → client-side history → compaction need → cost curve

### 5. Python unassisted #1: functions, dicts, JSON

**Before:** none · **Sources:** [pytest — Get Started](https://docs.pytest.org/en/stable/getting-started.html) · [Composing Programs](https://www.composingprograms.com/) (selective) · [Fluent Python 2e](https://www.oreilly.com/library/view/fluent-python-2nd/9781492056348/) (Paid)
**Done when:** dict/JSON-munging functions pass your own pytest suite, written with zero autocomplete.

- [ ] Writing without Copilot: functions, dict/list manipulation, `json.load`/`json.dump`
- [ ] pytest basics: plain asserts, running tests, reading failure output
- [ ] venv + pip hygiene
- [ ] Policy: no autocomplete; tests prove correctness, not vibes

### 6. Your first LLM API call

**Before:** 4, 5 · **Sources:** [OpenAI API docs](https://developers.openai.com/api/docs) · [Anthropic API docs](https://platform.claude.com/docs)
**Done when:** you make a raw HTTP call (no SDK), read every field of the response, and triage a 401 vs 400 vs 429 on sight.

- [ ] Raw HTTP anatomy: endpoint, headers, auth key, JSON body — no SDK yet
- [ ] The `messages` array and roles; reading the response object (`content`, `usage`, stop reason)
- [ ] Reading provider docs as an engineer
- [ ] First contact with errors: 401 vs 400 vs 429

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

**Before:** 17 · **Sources:** [What is MCP?](https://modelcontextprotocol.io/docs/getting-started/intro) (then Architecture from the docs index)
**Done when:** a tiny MCP server you wrote is connected to by a real client, and you can name who does what between host/client/server plus the main security risk.

- [ ] The N×M integration problem MCP solves; "USB-C for AI applications"
- [ ] Hosts, clients, servers — who does what
- [ ] Primitives: tools, resources, prompts; discovery and dynamic capability lists
- [ ] Transports: stdio vs HTTP; writing a tiny MCP server and connecting a real client to it
- [ ] Security surface: tool-description injection, untrusted servers

### 19. Failure handling

**Before:** 6, 17 · **Sources:** [Claude API errors](https://platform.claude.com/docs/en/api/errors) · [openai-python README](https://github.com/openai/openai-python)
**Done when:** a retry wrapper with exponential backoff + jitter that honours `Retry-After` is running around your calls, and you classify any API error on sight.

- [ ] Taxonomy: rate limits (429), overload (5xx/529), timeouts
- [ ] Exponential backoff with jitter; honouring `Retry-After`
- [ ] Idempotency so retries are safe; circuit-breaker intuition
- [ ] What SDKs retry by default vs what remains your problem

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
- [ ] Predictability / auditability / cost axes
- [ ] The most over-reached-for tool in the field; when the workflow wins decisively
- [ ] Flip condition: task variability

### 40. State and memory

**Before:** 36, 38 · **Sources:** [Letta — agent memory](https://www.letta.com/blog/agent-memory/) · [Mem0 — how it works](https://docs.mem0.ai/core-concepts/how-it-works)
**Done when:** you design a memory-tier scheme for an agent and state a policy for what deserves persisting.

- [ ] Short-term (the window) vs long-term (external stores)
- [ ] Memory tiers: buffer, self-edited core memory, recall/archival stores
- [ ] Relation to Phase 5 primitives (compaction / clearing / note-taking)
- [ ] Write policies: what deserves persisting at all

### 41. Planning and decomposition

**Before:** 38 · **Source:** [Lilian Weng — planning sections](https://lilianweng.github.io/posts/2023-06-23-agent/)
**Done when:** you decompose a real task into an agent plan and identify decomposition failure modes in a given trace.

- [ ] Task decomposition into steps; plan representations (lists, graphs, plan files)
- [ ] Replanning triggers when observations contradict the plan
- [ ] Reliable failure modes: over-decomposition, lost global goal, plan rot
- [ ] Planner/executor separation previewed (full treatment in topic 48)

### 42. Multi-step tool use

**Before:** 38 · **Sources:** [Berkeley function-calling leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html) · [Anthropic — tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
**Done when:** chained tool calls recover from a mid-chain failure and runaway behaviour is capped.

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
- [ ] Checkpointing and persistence; interrupts as HITL hooks
- [ ] Map every LangGraph concept back to topic 38's loop
- [ ] When the framework earns itself vs gets in the way

### 45. Human-in-the-loop

**Before:** 44 · **Sources:** [Mastra — where to put approval](https://mastra.ai/blog/hitl-where-to-put-approval-in-agents-and-workflows) · LangGraph interrupt docs
**Done when:** approval gates sit in defensible places and suspend/resume round-trips work.

- [ ] Gate placement: pre-tool-call approval vs mid-workflow suspend/resume
- [ ] Interrupt/resume mechanics (state snapshots)
- [ ] Which actions must never be autonomous: spending, deleting, sending, merging

### 46. Multi-agent orchestration ★

**Before:** 38, 44 · **Sources:** [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) · [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
**Done when:** an orchestrator-worker run completes with condensed worker reports, and you cite its ~15× cost multiplier unprompted.

- [ ] Subagent pattern: fresh context windows per focused task; condensed returns (~1–2k tokens)
- [ ] Context firewalls: workers don't inherit the orchestrator's transcript
- [ ] Maker/checker separation; parallel fan-out with isolation (worktrees)
- [ ] Economics: orchestrator-worker runs cost ~15× a chat call — when that's justified
- [ ] When a single agent with better tools suffices (most of the time)

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

---

## Phase 8 — LLMOps and production

### 58. Tracing an LLM system

**Before:** 47 · **Sources:** [Langfuse docs](https://langfuse.com/docs) · [OpenLLetry](https://www.traceloop.com/docs/openllmetry/introduction) · [OTel GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
**Done when:** spans cover an LLM + tool call path end-to-end and traces answer "where did this run go wrong".

- [ ] Spans across a non-deterministic system; OpenTelemetry carry-over from backend work
- [ ] Token/model attributes on traces; sampling traces for review

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

### 61. Caching

**Before:** 27, 59 · **Sources:** [Alephant — caching comparison](https://blog.alephant.io/prompt-caching-vs-semantic-caching-vs-exact-match/) · [Anthropic — prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) · [Redis — semantic caching](https://redis.io/blog/what-is-semantic-caching/)
**Done when:** a cache stack is chosen with each layer's breakage modes written down.

- [ ] Exact, prefix/prompt and semantic caching
- [ ] What each saves; what each breaks (staleness, personalisation leaks)

### 62. Prompt injection and the OWASP LLM Top 10

**Before:** 45 · **Sources:** [OWASP GenAI Top 10 (2026)](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) · [Willison — prompt injection explained](https://simonwillison.net/2023/May/2/prompt-injection-explained/) · [lethal trifecta](https://simonwillison.net/2025/jun/16/the-lethal-trifecta/) · [Gandalf CTF](https://gandalf.lakera.ai/)
**Done when:** you win a few Gandalf rounds and apply the lethal-trifecta risk model to Project 2 explicitly.

- [ ] Direct vs indirect injection; exfiltration paths through tools
- [ ] Treat model output as untrusted input — always

### 63. Guardrails beyond injection ★

**Before:** 62 · **Sources:** [NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/) · [Willison — dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/)
**Done when:** a guardrail pipeline (input filter → schema gate → policy check) is designed with false-positive costs argued.

- [ ] Input filtering, output schema gates, policy checks as pipeline stages
- [ ] Moderation layers; where guardrails sit in the request lifecycle
- [ ] False-positive economics: over-blocking kills utility too
- [ ] Composing guardrails with the harness permission gate (topic 48)

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

- [ ] `ndarray` vs Python list: homogeneous dtype, fixed size, rectangular shape
- [ ] Creating arrays (`array`, `zeros`, `arange`, `linspace`); shape/ndim/size/dtype attributes
- [ ] Indexing, slicing, boolean masks; views vs copies (and why a view mutation bites)
- [ ] Vectorized elementwise ops replacing loops; aggregation with and without `axis`
- [ ] Exercise: vectorize a loop-based function from your own code, by hand

### 72. Matrix operations and broadcasting

**Before:** 71 · **Sources:** [NumPy absolute basics](https://numpy.org/doc/stable/user/absolute_beginners.html) (broadcasting + transpose sections)
**Done when:** you predict output shapes of a chain of operations on paper, then verify in code.

- [ ] Broadcasting rules: dimensions must match or be 1; the classic `ValueError`
- [ ] Elementwise `*` vs matrix multiplication `@`; dot product computed by hand
- [ ] Transpose (`.T`), reshape, newaxis for row/column vectors
- [ ] Why this matters downstream: an embedding is a row vector; attention is matmuls all the way down

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

### 79. Linear regression, loss functions, gradient descent

**Before:** 72, 76 · **Sources:** [MLU-Explain — Linear Regression](https://mlu-explain.github.io/) · [StatQuest](https://www.statquest.org/)
**Done when:** you hand-run 3 gradient-descent steps on paper and say what too-large/too-small learning rates do.

- [ ] The line, residuals, MSE as loss; why squaring
- [ ] Gradient descent mechanics: gradient → step opposite → repeat
- [ ] Learning rate: divergence vs crawl — the interview's favourite hyperparameter question
- [ ] Train/test split: fitting ≠ generalizing (first contact with topic 85's ideas)

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

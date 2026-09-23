# Topic 3 — The context window, precisely

## Core idea

A context window is the maximum number of tokens a model can process in one request. It is the model's working input, not a permanent memory store. The request typically contains some combination of:

- system instructions;
- conversation history;
- retrieved documents or tool results;
- the current user message; and
- space reserved for the model's output.

The model can only generate from the tokens included in the current request. Information outside that request is unavailable unless the application summarizes, retrieves, or otherwise re-inserts it.

## 1. Input and output share one budget

For a request, the practical constraint is:

```text
input tokens + maximum output tokens <= model context limit
```

For example, with a 16,000-token context limit and 12,000 input tokens, at most about 4,000 output tokens can fit if the API uses the same limit for both. The exact API parameters and accounting rules vary, so the model documentation is authoritative.

Important consequences:

- A large prompt leaves less room for the answer.
- `max_tokens` or its equivalent is a ceiling, not a promise that the model will use all of it.
- The request can fail before generation if the input plus requested output exceeds the limit.
- Input and output token usage can both affect cost, but pricing rules are separate from the context-limit rule.
- Tool calls and tool results usually consume context too; a long result can reduce room for the final response.

Do not confuse these concepts:

| Concept | Meaning |
|---|---|
| Context window | Maximum tokens visible in one request/generation context |
| Maximum output | Maximum tokens the model may generate for that request |
| Conversation memory | Application-managed storage that may be added to later requests |
| Model parameters | Learned weights; not the same as temporary conversation context |

## 2. What happens at overflow

Overflow means the assembled request is larger than the permitted context. The result depends on the API, SDK, model, and application logic.

### Hard error

Many APIs reject the request with a context-length or invalid-request error. No completion is generated. This is the safest behaviour because it makes loss of information explicit.

### Silent or automatic truncation

Some clients, frameworks, or APIs remove tokens to make the request fit. Possible policies include:

- remove the oldest messages first;
- preserve the system message and remove older conversation turns;
- truncate the beginning or end of a text field;
- keep the newest content and discard earlier context; or
- reduce the requested output allowance.

The policy matters. Truncating the beginning can remove goals and definitions; truncating the end can remove the latest question or constraints. “The model forgot” may actually mean that the relevant tokens were discarded before inference.

Never assume truncation behaviour. Check the API documentation and inspect the final serialized request where possible.

### Application-managed prevention

Production applications commonly count or estimate tokens before sending a request, reserve output capacity, and then choose a policy such as summarization, retrieval, or dropping low-priority history.

## 3. Why the window is finite

The transformer processes relationships between tokens using attention. In a straightforward full-attention implementation, each token can interact with many other tokens. If sequence length is `n`, the number of pairwise token relationships is approximately proportional to:

```text
n × n = O(n²)
```

Doubling the sequence length can therefore require roughly four times as many attention-score interactions, with additional memory and latency costs. Real systems use optimizations, specialized attention patterns, caching, and hardware techniques, so the exact cost is implementation-dependent. The key point remains: longer contexts are computationally expensive, and models impose a finite maximum.

During autoregressive generation, the model normally reuses cached key/value states for earlier tokens. This avoids recomputing all earlier work for every new token, but the stored cache still grows with the context length and consumes memory.

A larger advertised context window does not guarantee equal quality everywhere in the window. Long prompts can increase latency and cost, and the model may use distant details less reliably than nearby, salient details.

## 4. Truncation versus compaction

Both techniques reduce context size, but they preserve information differently.

### Truncation

Truncation removes tokens or messages without replacing them with a semantic representation.

```text
conversation: A B C D E F G
truncate:     --------- E F G
```

The removed information is no longer available to the model unless it exists elsewhere in the request.

Advantages:

- simple and fast;
- deterministic when the policy is explicit;
- no extra model call or summarization cost.

Risks:

- silently loses requirements, decisions, or definitions;
- can break references such as “the second option”; and
- may preserve recent chatter while deleting the original objective.

### Compaction

Compaction transforms older context into a shorter representation, usually a summary or structured state, and inserts that representation into a later request.

```text
conversation: A B C D E F G
compact:      [summary of A–D] E F G
```

The model receives fewer tokens, but some information can survive in compressed form.

Advantages:

- preserves goals, decisions, constraints, and unresolved work when designed well;
- supports long-running conversations and agents; and
- can use structured fields instead of prose.

Risks:

- summaries can omit or distort details;
- repeated compaction can lose information progressively;
- summarization consumes tokens, latency, and possibly money; and
- a summary is not equivalent to the original evidence.

A robust compaction record should separate stable facts, user preferences, decisions, constraints, open questions, completed work, and exact artifacts or identifiers that must not be paraphrased. Keep authoritative source data outside the summary and retrieve it when exact wording matters.

## 5. “The model forgot” is mechanical

When a model appears to forget, investigate the request rather than assuming a mysterious memory failure. Common explanations are:

1. **The information was never sent.** The application stored it in a database or an earlier process, but did not include or retrieve it for this request.
2. **The information was truncated.** A context-management policy removed it to fit the limit.
3. **The information was compacted imperfectly.** The summary omitted, altered, or generalized the important detail.
4. **The information was present but hard to use.** It was buried in a huge prompt, contradicted by later text, poorly formatted, or far from the current task.
5. **Attention and retrieval were imperfect.** A finite context does not mean every token receives equal effective use; long-context performance can degrade, especially for details surrounded by irrelevant material.
6. **The output budget was too small.** The model may have identified the answer but lacked room to complete it.

Useful debugging questions:

- What exact messages and documents were in the final request?
- How many tokens did each section consume?
- Which truncation or compaction policy ran?
- Was the relevant fact preserved verbatim or only summarized?
- Was it contradicted later in the prompt?
- Did the model have enough output capacity?

## Context-management pattern

A practical request pipeline is:

```text
collect state
→ classify content by importance
→ count/estimate input tokens
→ reserve output capacity
→ retrieve only relevant evidence
→ compact or truncate by an explicit policy
→ validate the final request
→ send and log token usage
```

Prioritize system rules, the current task, safety constraints, active decisions, and directly relevant evidence. Remove redundant greetings, stale tool output, repeated instructions, and irrelevant history first. Keep a stable external record for anything that must be exact.

## Worked example

Suppose a model has a 10,000-token context limit. The application assembles:

```text
system instructions:     1,000 tokens
conversation history:    6,500 tokens
retrieved documents:     2,000 tokens
current user message:      500 tokens
requested output:        2,000 tokens
total:                  12,000 tokens
```

The request exceeds the limit by 2,000 tokens. Valid remedies include:

- remove low-value history;
- compact older turns from 6,500 to 4,500 tokens;
- retrieve fewer or shorter documents;
- reduce the output ceiling; or
- reject the request clearly and ask the caller to narrow it.

Blindly sending it may produce an error. Automatically removing the first 2,000 tokens may delete the original requirements. A deliberate policy is therefore part of application correctness.

## Self-check

- Given an input size and output allowance, can you determine whether a request fits?
- Can you distinguish an API hard error from client-side truncation?
- Can you explain why compaction is not the same as memory?
- Can you identify what was lost when a conversation “forgot” a requirement?
- Can you describe how context limits affect latency, cost, and reliability?

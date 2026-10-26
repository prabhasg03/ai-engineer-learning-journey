# Demo Script — Sourceline

**Goal:** in three minutes, show that this is an engineered retrieval system, not a chatbot wrapper:
real corpus, real citations, honest refusal, visible diagnostics, idempotent ingestion, and a failure
mode that behaves.

Record a 20-second GIF for the README and a 3-minute video for the portfolio. Rehearse on the same
machine/network you will record on.

---

## 1. Pre-flight (10 minutes before)

- [ ] `docker compose up -d db` healthy; `api` up; `/v1/ready` is `ready`.
- [ ] Index contains the expected 38 documents/chunk count.
- [ ] `.env` has a valid key; admin token available but **not visible on screen**.
- [ ] Test the three questions below; note the citation doc IDs (do not memorise fake answers).
- [ ] Run `python -m sourceline.ingest --root ../..` once to confirm the no-op report (`embedded=0`).
- [ ] Open the UI, `/docs`, and a terminal at readable font size.
- [ ] Notifications off; browser bookmarks/bar clean; no keys/tokens in history or terminal prompt.
- [ ] Record a backup video/GIF in case the provider is down. Label any fake-provider footage as such.

---

## 2. The 3-minute flow

### 0:00–0:25 — Problem and claim

> "My curriculum is 38 Markdown notes, about 83,000 words. Finding and verifying an explanation means
> remembering which topic covered it. This is Sourceline: it ingests those notes into Postgres +
> pgvector, answers from the retrieved passages, and cites the file, heading, and line range. If the
> corpus doesn't support an answer, it refuses."

Show the repo tree briefly (38 notes) and the architecture diagram (one slide/README section).

### 0:25–0:50 — Architecture in one breath

> "Ingestion is a CLI: discover, hash, structural Markdown chunking, batch embeddings, idempotent
> upsert into pgvector, prune stale chunks. Query is FastAPI: embed the question, HNSW retrieval with
> metadata filters, dedupe and budget the evidence, a static prompt, structured output, then a
> deterministic citation validator. Retries, `Retry-After`, deadlines, and circuit breakers wrap
> every outbound call."

Point at the diagram; do not read every box.

### 0:50–1:35 — Live cited answer

Ask:

> **"How does HNSW trade recall for speed?"**

Show:

- the answer with `[1][2]` markers;
- the citation cards (doc ID + heading + lines);
- click a citation → the exact source excerpt/lines;
- one sentence about why this is not just "the model said so": the citations are built from the
  retrieved chunk rows, and the validator rejects markers that do not map.

Optional second question if time:

> **"What is the difference between a retrieval miss and a ranking miss?"**

Expected: citations to topic 28; answer distinguishes the stages. This demonstrates cross-note
retrieval and topic 28 vocabulary.

### 1:35–2:00 — Honest refusal

Ask something deliberately outside the corpus:

> **"How do I configure Kubernetes ingress?"**

Show:

- `abstained=true`, `abstention_reason="no_relevant_evidence"`;
- no citations; `closest_sources` (if any) clearly labelled as not evidence;
- the point: "A false answer costs more trust than a refusal."

If the question accidentally retrieves something above the floor, use the pre-tested unanswerable
case from the eval set instead; do not improvise a refusal that looks like a failure.

### 2:00–2:25 — Diagnostics

Open the diagnostics panel (admin token) or:

```bash
curl -s 'http://127.0.0.1:8000/v1/query?debug=1' \
  -H "Authorization: Bearer $SOURCELINE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does HNSW trade recall for speed?","top_k":6}'
```

Show:

- candidate count and top score;
- dedupe/drop reasons;
- evidence tokens vs budget;
- per-stage timings (embed/retrieve/generate);
- prompt hash, not the prompt itself.

> "This is how I diagnose a bad answer: was the gold chunk retrieved, did it survive budgeting, did
> the model cite it? Retrieval miss, ranking miss, generation miss — different fixes."

### 2:25–2:45 — Idempotent ingestion

Run:

```bash
python -m sourceline.ingest --root ../..
```

Show the report:

```text
plan: new=0 changed=0 unchanged=38 deleted=0
chunks: inserted=0 updated=0 deleted=0 reused=<n> embedded=0
status: success
```

> "Re-running on an unchanged corpus makes zero embedding calls. Edit one section and only the
> affected chunks are re-embedded; delete one and its rows are pruned. That is the difference between
> a demo and a pipeline."

### 2:45–3:00 — Failure mode + close

If you have a safe failure drill (fake provider flag or a recorded clip), show:

- chat provider down → `degraded.mode="extractive"`, labelled, citations still valid; or a clean
  `503 upstream_unavailable` with `Retry-After`;
- no 500, no fake answer.

Close:

> "The evaluation report is in the repo: recall@10, citation validity, groundedness, false-answer
> rate, latency, and cost, with the commit and model profile. Limitations are stated in the README —
> dense-only retrieval, no reranker, heuristic grounding. The next step is hybrid search and a
> cross-encoder, measured against the same set."

Do not end on "it's basically production-ready". End on what is measured and what is next.

---

## 3. Failure-mode demo (separate 60-second clip)

Do not break the live demo environment. Use a scripted drill:

```bash
# Fake provider configured to fail chat calls, service already running
SOURCELINE_FAKE_CHAT=down python -m sourceline.eval --case demo-failure
```

Or record the chaos test output:

```text
test_llm_down ... ok
  response.status = 200
  response.degraded.mode = "extractive"
  response.citations = [...]
  response.grounded = true
```

Voice-over:

> "When chat is unavailable, the service does not 500 and does not invent prose. It extracts the most
> relevant sentences from the retrieved evidence, cites them, and labels the response as degraded. If
> there is no usable evidence, it returns a clean 503 with a `Retry-After`."

Also show the 429 drill briefly if time: provider `Retry-After` honoured, retries bounded, breaker
opens rather than hammering.

---

## 4. Recording checklist

- 1280×720 or 1920×1080; terminal font ≥ 16 px; light or dark theme with contrast.
- Cursor visible; no rapid scrolling; pause on citations.
- No API keys, tokens, `.env` contents, browser profiles, or personal notifications.
- The GIF is ≤ 20 s and ≤ 10 MB; it shows the question → answer → citation click.
- Captions or a one-line subtitle for the key claim ("answers cite the exact lines").
- Host the video (YouTube unlisted/Loom) and link it in the README; keep a local copy.
- If the provider is down during recording, use the recorded backup and say so; never present fake
  output as a live run.

---

## 5. README asset list

| Asset | Where | Content |
|---|---|---|
| Hero GIF | top | question → cited answer → source click |
| Architecture image | after intro | the component diagram (export from Mermaid) |
| Eval table | quality section | measured metrics + date/commit/profile |
| Failure screenshot | reliability section | degraded/extractive or 503 with `Retry-After` |
| Debug screenshot | engineering section | candidates/drops/timings (no secrets) |
| Hosted link | top | optional; rate-limited demo |

---

## 6. Questions to avoid in the live demo

- Anything about the current date, prices, or "latest" versions (the corpus is a snapshot).
- Questions that require three-hop synthesis; v1 has no planner; use the eval set's comparison case
  if you want to show multi-chunk retrieval.
- Questions containing personal/secret data; the demo sends questions to a provider.
- A question you have not tested five minutes earlier.

---

## 7. Post-demo follow-up

Have ready:

- the eval report path;
- the failure-handling doc and one chaos test;
- the data model and the idempotency test;
- one honest limitation and the Phase 4 plan (hybrid + rerank);
- the repository URL and the exact commit used in the recording.

If asked "how do you know it's grounded?", show the validator + the human-reviewed sample, and say
plainly that semantic entailment is measured, not proven, in v1.

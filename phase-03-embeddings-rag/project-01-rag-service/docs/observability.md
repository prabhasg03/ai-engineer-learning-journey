# Observability — Sourceline

**Goal:** answer three questions quickly — *Is the service healthy? Where did this answer lose
evidence? What changed?* — without storing secrets, prompts, or personal data.

Three signals, three jobs:

| Signal | Job | Retention |
|---|---|---|
| Structured logs | Per-request narrative and errors | 7–30 days (platform) |
| Metrics | Rates, latency, saturation, RAG health | 15–90 days (Prometheus) |
| Traces (optional) | Cross-stage timing for one request | 7 days |
| `query_logs` (DB) | Durable diagnostic record for evaluation/attribution | 30 days |

---

## 1. Structured logs

JSON lines to stdout; the platform collects them. One event per meaningful step, not one line per
function call.

Required fields on every request event:

```json
{
  "ts": "2026-10-26T10:20:11.412Z",
  "level": "info",
  "event": "query_completed",
  "service": "sourceline",
  "version": "1.0.0",
  "request_id": "req_4f8c...",
  "route": "POST /v1/query",
  "status": 200,
  "latency_ms": 2012,
  "profile_key": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
  "retrieved_count": 31,
  "prompted_count": 6,
  "cited_count": 2,
  "abstained": false,
  "grounded": true,
  "degraded": null,
  "prompt_tokens": 4120,
  "completion_tokens": 154,
  "cost_usd": 0.0018,
  "index_age_seconds": 3600
}
```

Stage events (debug level or sampled at info):

```json
{"event":"stage_completed","request_id":"req_...","stage":"embed","elapsed_ms":143,"attempts":1,"breaker_state":"closed"}
{"event":"stage_completed","request_id":"req_...","stage":"retrieve","elapsed_ms":21,"candidates":31,"ef_search":80}
{"event":"stage_completed","request_id":"req_...","stage":"generate","elapsed_ms":1840,"model":"gpt-4.1-mini","attempts":1}
{"event":"validation_failed","request_id":"req_...","reason":"invalid_marker","markers":[9],"allowed":6,"repair":true}
```

Ingest events:

```json
{"event":"ingest_plan","run_id":"run_...","new":0,"changed":1,"unchanged":37,"deleted":0,"profile_changed":0}
{"event":"ingest_document","run_id":"run_...","doc_id":"...","chunks":8,"inserted":2,"deleted":1,"embedded":2}
{"event":"ingest_completed","run_id":"run_...","status":"success","duration_ms":2400,"embedded":2,"embedding_calls":1}
```

### 1.1 Redaction rules

Never log:

- API keys, authorization headers, admin tokens, database URLs with passwords;
- system prompts, full rendered prompts, full document text;
- question/answer text by default (`SOURCELINE_LOG_QUESTIONS=false` stores only hashes);
- raw provider response bodies (they may echo prompts or contain unsafe text);
- client IPs in per-request logs (aggregate only, if needed);
- stack traces to clients (server logs may include a sanitised stack with the request ID).

A redaction filter runs on every log record as a last line of defence. Tests feed a fake key/URL into
an error and assert it does not appear in captured logs.

### 1.2 Levels and sampling

| Level | Use |
|---|---|
| `error` | Unhandled/5xx, invariant failure, auth misconfiguration |
| `warning` | Retry exhaustion, breaker open, degraded mode, validation repair, stale index |
| `info` | Request completed, ingest completed, startup/readiness transition |
| `debug` | Stage timings, candidate IDs, assembly drops (never enabled in hosted production) |

High-volume stage logs are sampled (e.g. 10%) at info; the per-request completion event is always
logged. Diagnostics for a specific request come from `query_logs`/debug, not from turning on debug
globally.

---

## 2. Metrics

Prometheus text format at `/metrics`, bound to the app but blocked at the reverse proxy in hosted
deployments. Use a registry with a `service="sourceline"` default label.

### 2.1 HTTP / golden signals

| Metric | Type | Labels |
|---|---|---|
| `sourceline_http_requests_total` | counter | `route`, `method`, `status` |
| `sourceline_http_request_duration_seconds` | histogram | `route`, `method` |
| `sourceline_http_in_flight` | gauge | `route` |
| `sourceline_rate_limited_total` | counter | `scope` |
| `sourceline_request_body_rejected_total` | counter | `reason` |

Histogram buckets: 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 6, 10, 30 s.

### 2.2 RAG pipeline

| Metric | Type | Labels | Why |
|---|---|---|---|
| `sourceline_stage_duration_seconds` | histogram | `stage` (embed/retrieve/assemble/generate/validate) | Find the slow stage |
| `sourceline_retrieved_candidates` | histogram | — | Retrieval health |
| `sourceline_prompted_chunks` | histogram | — | Budget/assembly |
| `sourceline_evidence_tokens` | histogram | — | Budget utilization |
| `sourceline_abstentions_total` | counter | `reason` | Refusal behaviour |
| `sourceline_grounded_total` | counter | `grounded` | Grounding rate |
| `sourceline_citation_invalid_total` | counter | `reason` | Validator/regression alarm |
| `sourceline_repair_total` | counter | `kind` (schema/citation) | Prompt/model drift |
| `sourceline_degraded_total` | counter | `mode` (extractive/lexical) | Fallback usage |
| `sourceline_query_cost_usd` | histogram | — | Spend |
| `sourceline_tokens_total` | counter | `kind` (prompt/completion) | Cost/latency |

### 2.3 Dependencies

| Metric | Type | Labels |
|---|---|---|
| `sourceline_dependency_attempts_total` | counter | `dependency`, `kind`, `outcome` |
| `sourceline_dependency_duration_seconds` | histogram | `dependency`, `operation` |
| `sourceline_retry_total` | counter | `dependency`, `kind` |
| `sourceline_circuit_state` | gauge | `dependency` (0 closed, 1 half-open, 2 open) |
| `sourceline_circuit_open_total` | counter | `dependency` |
| `sourceline_deadline_exceeded_total` | counter | `stage` |
| `sourceline_db_pool_in_use` | gauge | — |
| `sourceline_db_pool_waiting` | gauge | — |

### 2.4 Index / ingest

| Metric | Type | Labels |
|---|---|---|
| `sourceline_index_documents` | gauge | — |
| `sourceline_index_chunks` | gauge | — |
| `sourceline_index_age_seconds` | gauge | — |
| `sourceline_index_ready` | gauge | — |
| `sourceline_ingest_duration_seconds` | histogram | `mode` |
| `sourceline_ingest_documents_total` | counter | `status` |
| `sourceline_ingest_chunks_embedded_total` | counter | — |
| `sourceline_ingest_failures_total` | counter | `code` |

### 2.5 Label discipline

Do **not** use unbounded values as labels: question text, request ID, document ID, chunk ID, user IP,
error message. Those belong in logs/DB. `route` is the templated path (`/v1/documents/{doc_key}`), not
the raw path. If per-document metrics are needed, use a bounded `phase`/`topic` label, not `doc_id`.

---

## 3. Traces (optional)

If OpenTelemetry is enabled, one trace per request with spans:

```text
POST /v1/query
├── validate
├── readiness/profile
├── embed.query
│   └── provider.request (attempt=1)
├── retrieve
├── assemble
├── generate
│   ├── provider.request (attempt=1)
│   └── repair (optional)
├── validate.citations
└── respond
```

Attributes: `request_id`, `profile_key`, `stage`, `attempt`, `breaker_state`, `model`, token counts.
No prompt/document text. Trace ID is returned as `X-Trace-ID` when enabled. OTel is optional for the
portfolio; structured logs + metrics are sufficient for v1, and the code should not depend on a
collector being present.

---

## 4. Dashboards

### 4.1 Service health

- Request rate, error rate (4xx/5xx), p50/p95/p99 latency.
- In-flight requests, rate-limited count, DB pool in use/waiting.
- Readiness state and index age.
- Breaker states for embedding/chat/DB.

### 4.2 RAG quality

- Abstention rate by reason (trend).
- Grounded vs ungrounded count.
- Citation-invalid count (should be zero after repair/abstain).
- Repair rate (schema/citation).
- Degraded mode count (should be zero outside drills).
- Retrieved candidates / prompted chunks / evidence tokens distributions.
- Cost per query and daily spend.

### 4.3 Ingest

- Last run status/duration; documents/chunks embedded; failures by code.
- Index counts vs expected corpus count.
- Index age with a 7-day threshold.

---

## 5. Alerts

| Alert | Condition | Severity | Runbook |
|---|---|---|---|
| Readiness failing | `/v1/ready` != ready for 2 min | page | DB/index |
| Error rate | 5xx > 5% for 5 min | page | provider/DB |
| Latency | p95 > 8 s for 10 min | page | provider/budget |
| Circuit open | any dependency open > 1 min | page | dependency |
| Citation invalid | counter increases (unrepaired) | ticket | validator/prompt |
| Ingest failed/partial | last run failed/partial | ticket | ingest |
| Index stale | age > 7 days or commit mismatch | ticket | reindex |
| Cost | daily spend > 80% of cap | ticket | budget/model |
| Rate limiting | > 20% of requests 429 for 10 min | ticket | capacity/abuse |
| DB pool saturation | waiting > 0 for 5 min | ticket | pool/DB |

Alert fatigue is a failure: every alert must have an action. A "citation invalid" alert is meaningful
because the target is zero; a "groundedness dropped" alert requires an eval run, not a single request.

---

## 6. SLOs and error budgets

For the hosted demo (best effort, not a commercial SLA):

| SLI | Target | Window |
|---|---:|---|
| Availability (non-5xx / all) | 99.0% | 30 days |
| p95 query latency | ≤ 6 s | 30 days |
| Citation validity | 100% (answered) | per run/release |
| Groundedness | ≥ 0.95 | per release eval |
| Index freshness | ≤ 7 days | continuous |

A 99% availability target allows ~7.2 h/month of 5xx. Provider outages count against the SLI because
the service owns its dependency choice and fallback. A labelled degraded 200 is available, not an
error; an unlabelled wrong answer is worse than a 503.

---

## 7. Query diagnostics (`query_logs`)

For each query, store the four sets and timings (see [`data-model.md`](data-model.md)):

| Field | Diagnostic use |
|---|---|
| `retrieved` | Was the gold chunk found? (retrieval miss) |
| `prompted` | Did it survive dedupe/budget? (ranking miss) |
| `cited` | Did the model use it? (generation miss) |
| `abstained`/`reason` | Refusal behaviour |
| `grounded` | Validator outcome |
| `degraded` | Fallback usage |
| `timings`/tokens | Performance/cost |
| `error_code` | Failure class |

Access is admin-only (`GET /v1/admin/queries/{id}`). Questions are hashed by default; redacted text is
opt-in only for local development. The table is not a analytics warehouse; it is a debugging and
eval-attribution record with 30-day retention.

---

## 8. Debugging a single bad answer (procedure)

1. Get the `request_id` from the response or UI.
2. `GET /v1/admin/queries/{request_id}` → check `retrieved` for the gold doc/chunk.
3. If absent: retrieval miss. Inspect query text (if logged), embedding profile, filters, `ef_search`,
   chunk boundaries.
4. If present but not `prompted`: ranking/assembly. Pull the debug drop reasons (or re-run with
   `?debug=1`): duplicate, budget, score floor, order.
5. If prompted but not cited/wrong: generation. Inspect the prompt hash/model, repair attempts, and
   eval judge for the same case.
6. If the index is stale: compare `source_commit`/`age_seconds`; re-ingest.
7. If the corpus conflicts: record both chunks, decide the authority/recency policy, add an eval case.
8. Add a regression case before fixing. The fix is not done until the case passes.

---

## 9. Privacy and security of telemetry

- Logs/metrics/traces must not contain secrets, prompts, document text, or raw questions by default.
- IP addresses are used in memory for rate limiting; if logged, truncate/anonymise and document the
  retention.
- `query_logs` stores hashes by default; opt-in redacted text is local-only or explicitly consented.
- Metrics labels are bounded; no user/doc identifiers.
- `/metrics` is not publicly routed in the hosted demo.
- Access to admin diagnostics requires the admin token; the token is never logged.
- Backups inherit the retention/privacy rules of the data they contain.

---

## 10. Operational acceptance

- [ ] Every request has a request ID in the response and logs.
- [ ] Request completion, error, retry, breaker, degraded, ingest, and readiness events are logged.
- [ ] Metrics cover HTTP, stages, dependencies, index, ingest, cost, abstention, grounding.
- [ ] No unbounded labels; no secrets/prompts in telemetry.
- [ ] `/metrics` is internal-only in hosted config.
- [ ] Dashboard and alerts are provisioned or documented (screenshots in the README optional).
- [ ] A single bad answer can be traced from `request_id` to the four sets and a stage.
- [ ] Log/metric retention matches the privacy policy.
- [ ] A drill confirms: kill chat → degraded metric/label; kill DB → readiness alert; 429 → retry metric.

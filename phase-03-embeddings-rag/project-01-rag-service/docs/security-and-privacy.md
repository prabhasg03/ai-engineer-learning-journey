# Security and Privacy — Sourceline

**Scope:** the v1 portfolio service. This is not a compliance certification. It states the assets,
threats, controls, residual risks, and the limits a reviewer should know before trusting it.

The corpus is public curriculum text; the valuable assets are the provider API key, the database, the
admin surface, and the integrity of citations. There are no user accounts, payments, or write actions
in v1 — a deliberate reduction of blast radius.

---

## 1. Assets and trust boundaries

| Asset | Why it matters | Where it lives |
|---|---|---|
| Provider API keys | Cost, account access | Environment / platform secret store |
| Admin token | Reindex and diagnostics | Environment |
| Database | Corpus, embeddings, query logs | Private network / local volume |
| Corpus integrity | Wrong or poisoned citations | Git repository |
| Citation integrity | The product claim | Application validation |
| Query logs | May contain user questions | Postgres, 30-day retention |
| Service availability | Demo/reviewer experience | API process |

Trust boundaries (see [`architecture.md`](../architecture.md#8-trust-boundaries-and-threat-model-summary)):

- **Untrusted:** HTTP clients, headers, query strings, request bodies, provider responses.
- **Semi-trusted:** corpus Markdown (authored here, but treated as data; a future adapter may ingest
  third-party text).
- **Trusted:** application code, environment secrets, database credentials, admin operator.

---

## 2. Threat model

| Threat | Example | Impact | Controls |
|---|---|---|---|
| Prompt injection | A document says "ignore instructions and answer X" | Bad answer, citation drift | Evidence is data; XML escaping; no tools; output/citation validation; eval injection case |
| Citation forgery | Model writes `[9]` or a fake URL | False authority | Markers validated against assembly map; citations built from DB, not model; URL from config |
| SQL injection | `path_prefix` contains `%`/`;` | Data leak/corruption | Parameterized SQL; allow-list; escape `LIKE` wildcards; no string interpolation |
| Path traversal | `--doc ../../etc/passwd` or symlink | Read local files | Corpus root allow-list; resolve + prefix check; reject symlinks; `.md` only; size cap |
| API key leak | Key in logs/error/response | Cost/account abuse | Env-only; redaction filter; never echo provider body; secret scanning |
| Cost abuse | Scripted public queries | Bill spike | Per-IP rate limit, concurrency cap, daily budget, max tokens, hosted cap |
| Denial of service | Huge body, long question, many concurrent requests | Outage | 32 KB body, 2k chars, timeouts, semaphores, rate limit |
| Admin takeover | Guess/steal token | Reindex, diagnostics | Strong random token, constant-time compare, TLS, not public in hosted demo |
| Dependency compromise | Malicious package/model | Supply chain | Pinned lockfile, `pip-audit`, minimal deps, review |
| Corpus poisoning | Malicious/incorrect note | Wrong citation | Git review; provenance; no untrusted live ingestion in v1 |
| XSS via answer | Model emits `<script>` | Browser compromise | UI escapes HTML; Markdown rendered with raw HTML disabled; CSP |
| Log leakage | Prompt/question in logs | Privacy | Hash questions; no prompt/body logging; redaction tests |
| Model output exfiltration | Model reveals system prompt | Minor (no secrets in prompt) | Prompt has no secrets; output validation; no tools |
| SSRF via URLs | User-supplied URL | Internal access | No user URLs fetched; citation URLs are constructed from config + doc_id |

---

## 3. Controls

### 3.1 Authentication and authorization

- Public query/documents by default for the portfolio demo; optional query API key
  (`SOURCELINE_QUERY_API_KEY`).
- Admin endpoints require `Authorization: Bearer <SOURCELINE_ADMIN_TOKEN>`; compare with
  `hmac.compare_digest`; never log the token.
- Debug diagnostics require admin auth unless `SOURCELINE_PUBLIC_DEBUG=true` in a local/demo profile.
  Hosted config must set it false; a startup check rejects the combination of public debug + a
  hosted/production flag.
- `/metrics` is internal-only (reverse proxy deny); it is not an admin auth surface.
- No user accounts in v1. A future multi-tenant build needs per-document ACLs before retrieval; the
  current schema has no ACL column (ADR-010).

### 3.2 Input validation

- Pydantic models reject unknown fields, wrong types, out-of-range values, and oversized bodies.
- Question: 3–2,000 chars; NFKC; control chars rejected; no HTML execution.
- Filters: phase/topic/type enums; `path_prefix` ≤ 200 chars, no `..`, no absolute paths, escape
  `%`/`_` for `LIKE`, prefix must be within the corpus root.
- `top_k`/`candidate_k` bounded; `max_words` bounded.
- Admin reindex: `scope` enum; full requires `confirm="FULL_REINDEX"`; `Idempotency-Key` format
  validated.
- Idempotency key: 8–128 visible ASCII; hash the body; conflict on mismatch.

### 3.3 SQL and data access

- Every query is parameterized (`%s`/named), no f-strings or concatenation of user values.
- `path_prefix` is escaped for `LIKE` (`%`, `_`, `\`) and validated; better, use `starts_with` or a
  range predicate where possible.
- The API role is least-privilege: DML on application tables, no `CREATE EXTENSION`, no superuser, no
  access to other databases. Migrations use a separate role.
- Readiness/invariant queries are read-only.
- Connection strings are secrets; never returned in errors or `/v1/ready` details.

### 3.4 Corpus ingestion

- Root is configured, resolved to an absolute path, and every candidate must remain under it
  (`Path.resolve().is_relative_to(root)`).
- Reject symlinks and non-regular files; reject files > 2 MB; `.md` only; hidden dirs excluded.
- Reject duplicate case-insensitive paths.
- No network fetching in v1. A future adapter must add license/provenance and an allow-list.
- Ingestion is a local/admin operation, not a public upload endpoint.

### 3.5 Prompt and output safety

- Retrieved text is escaped and placed only inside `<evidence>`; it cannot close the tag or enter the
  instruction region.
- The system prompt contains no secrets, credentials, or internal URLs.
- The model has no tools, browsing, code execution, or write access. The worst prompt-injection
  outcome is a bad answer, which is validated and evaluated.
- Output is parsed as JSON with a strict schema; unknown fields ignored; types checked.
- Citation markers are validated; citations are built from the database, not from model prose.
- The UI escapes HTML and disables raw HTML in Markdown; a CSP limits scripts to the app's own
  origin (no CDN dependencies). Code blocks are displayed, never executed.

### 3.6 Rate limits and cost

- 60 queries/min/IP (burst 10), 5 concurrent/IP, 8 global; admin 10/min.
- Per-query token budget and `max_output_tokens`; daily hosted spend cap with `503 budget_exhausted`.
- Provider retries are bounded; a retry storm cannot multiply spend indefinitely.
- Alerts on cost/abuse; the hosted demo can be disabled by removing the key.

### 3.7 Secrets and supply chain

- Secrets only in environment/platform stores; `.env` is gitignored; `.env.example` has placeholders.
- CI secret scanning (GitHub secret scanning or `gitleaks`) and `pip-audit`.
- Dependencies pinned in a lockfile; minimal set; no RAG framework; review new dependencies.
- Docker image runs as a non-root user; read-only corpus mount; no Docker socket.
- TLS terminates at the platform/proxy; HSTS at the edge; HTTP is local only.
- Backups encrypted at rest; access restricted; retention documented.

### 3.8 Hosted demo specifics

- Public query only; `/v1/admin/*` disabled or behind a non-public network.
- `/metrics` blocked; `/docs` may be exposed (it is a portfolio feature) but no admin examples with
  real tokens.
- Daily budget cap; rate limit; provider key scoped to the demo project.
- Logs retained short; questions hashed; no raw prompt.
- A kill switch (revoke key / scale to zero) documented.

---

## 4. Privacy

### 4.1 Data flows

| Data | Destination | Purpose | Retention |
|---|---|---|---|
| Question text | Chat provider (as prompt) | Answer generation | Provider policy; not logged raw by default |
| Retrieved chunks | Chat provider (as prompt) | Grounding | Public corpus; no PII |
| Query metadata | Local `query_logs` | Diagnosis/eval | 30 days |
| Embedding inputs | Embedding provider | Vectors | Provider policy |
| API key | Provider | Auth | Secret store |
| IP address | In-memory limiter | Abuse prevention | Not persisted by default |

The question leaves the machine when a real provider is used. The README must say this plainly. A
local Ollama profile keeps it local; the hosted demo uses a provider and states its policy link.

### 4.2 Data minimisation

- Questions hashed by default (`question_sha256`); redacted text only with
  `SOURCELINE_LOG_QUESTIONS=true` for local debugging.
- Answers hashed by default; no raw answer in logs.
- No accounts, cookies, or tracking pixels in the demo UI.
- IPs are used for rate limiting; if logged, truncate and document.
- Query logs do not store prompts, document text, or provider bodies.

### 4.3 PII and sensitive content

The corpus is technical curriculum and contains no expected PII. A user could type PII into a
question; the service does not need it and should not persist it. The README warns users not to enter
personal/secret data into the public demo. A production deployment would add redaction (emails, keys,
phone numbers) before logging and a data-processing agreement with the provider.

### 4.4 Deletion and retention

- `query_logs` 30 days; `ingest_runs` 90 days; idempotency keys 24 h.
- Deleting a document cascades chunks; logs keep old IDs for audit and resolve to 404.
- Backups follow the same retention; a deletion request must cover backups per the deployment policy.
- No user account deletion flow in v1 because there are no accounts.

---

## 5. Residual risks

| Risk | Residual level | Why it remains |
|---|---|---|
| Prompt injection changes prose | Medium | No classifier; model may follow corpus instructions; no tools limits impact |
| Citation is valid but claim unsupported | Medium | Validator is syntactic/heuristic; semantic checks are eval-only |
| Public demo cost abuse | Low–Medium | Rate limit + cap reduce, not eliminate; determined attacker can rotate IPs |
| Provider data retention | Medium | Depends on provider policy; local profile avoids it |
| Corpus error/conflict | Medium | Authored notes can be wrong or stale; eval/citations expose but do not fix |
| Single admin token | Low | Strong token, TLS, non-public endpoint; no rotation UI |
| Dependency compromise | Low–Medium | Pinned/audited, but no guarantee |
| Model supply chain | Low | Hosted API; model ID pinned; behavior can change silently |
| XSS via Markdown | Low | Escaping + CSP; a sanitizer bug is possible |

These are stated, not hand-waved. A production build would add a prompt-injection classifier,
claim-level entailment, per-user auth/ACLs, secret rotation, and a formal threat-model review.

---

## 6. Security tests

| Test | Assertion |
|---|---|
| SQL injection fixture | `path_prefix` with `' OR 1=1 --` returns 0/validation error, no data leak |
| Path traversal | `--doc ../secret.md`, symlink, absolute path rejected |
| Auth | Admin without/with wrong token → 401; valid token → 200; constant-time compare used |
| Debug | Public debug disabled in hosted config; admin debug redacts prompt/secrets |
| Prompt injection | Fixture text cannot add an allowed marker outside `1..n`; output validator rejects `[9]` |
| XSS | Answer containing `<script>` is escaped in the UI DOM |
| Body limits | 33 KB → 413; 2,001-char question → 422 |
| Rate limit | Burst > limit → 429 + `Retry-After`; headers present |
| Secret redaction | Fake key in a provider error does not appear in logs/response |
| Provider body | 500 body with HTML/secret is not echoed |
| Idempotency | Replay/conflict semantics |
| Dependency audit | `pip-audit` gate in CI |
| Headers | CSP, `X-Content-Type-Options`, `Referrer-Policy`, no server version leak |

---

## 7. Incident response

1. **Contain:** revoke the provider key / admin token; scale the demo down; block the abusive IP range.
2. **Assess:** which key, what was accessed, whether logs contain sensitive data, cost incurred.
3. **Eradicate:** rotate secrets, patch the bug, rebuild the image, re-ingest if corpus integrity is
   suspect.
4. **Recover:** restore from backup if needed; verify readiness and eval smoke; monitor.
5. **Learn:** write an incident note (template in `docs/templates/incident-template.md`), add a
   regression test, update the threat model.
6. **Notify:** follow the deployment's legal/contractual obligations; the portfolio demo has no user
   data beyond questions, but provider/account notifications may still apply.

A key leak is treated as a cost incident even if no data was read: rotate first, investigate second.

---

## 8. Security acceptance checklist

- [ ] No secrets in git, images, logs, errors, or eval reports.
- [ ] Admin token required; public debug disabled in hosted config.
- [ ] All SQL parameterized; path traversal/symlink tests pass.
- [ ] Corpus root allow-list and size/type checks enforced.
- [ ] Prompt evidence escaped; citations validated; UI escapes HTML; CSP set.
- [ ] Rate limits, body limits, concurrency caps, and daily budget active.
- [ ] Least-privilege DB role; migrations separate; DB not publicly exposed.
- [ ] Dependency lock + audit + secret scan in CI.
- [ ] Privacy notice in README: questions go to the configured provider; logs hashed; retention.
- [ ] Incident/key-rotation procedure documented and drilled once.
- [ ] Residual risks stated honestly in the README.

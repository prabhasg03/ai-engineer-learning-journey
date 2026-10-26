# Deployment and Runbook — Sourceline

**Primary deployment:** Docker Compose on a reviewer's machine. **Optional:** a small hosted demo.
**Non-goal:** a multi-tenant production platform.

The README's quickstart is a contract. This document is the operator's version: prerequisites, env
vars, migrations, ingest, backup/restore, failure runbooks, and rollback.

---

## 1. Prerequisites

| Path | Requirements |
|---|---|
| Docker (recommended) | Docker Desktop / Engine with Compose v2; ~1 GB free disk |
| Local Python | Python 3.12; PostgreSQL 16 with pgvector ≥ 0.8; a C build toolchain only if psycopg binary is unavailable |
| Provider | An OpenAI-compatible embeddings + chat endpoint and key, **or** a local Ollama server with compatible models |
| Corpus | The repository checkout (38 phase Markdown files) |

The Docker path is the reviewer path. The local path exists for development and for environments
where Docker is unavailable.

---

## 2. Configuration

Copy `.env.example` to `.env`. Never commit `.env`. The app validates settings at startup and fails
with a readable error rather than a traceback.

### 2.1 Core

| Variable | Default | Notes |
|---|---|---|
| `SOURCELINE_ENV` | `local` | `local`, `test`, `hosted`; affects safety checks |
| `SOURCELINE_DATABASE_URL` | `postgresql://sourceline:sourceline@127.0.0.1:5432/sourceline` | Compose overrides host to `db` |
| `SOURCELINE_ADMIN_TOKEN` | empty | Required for admin/debug; generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SOURCELINE_QUERY_API_KEY` | empty | Optional public-query bearer key |
| `SOURCELINE_PUBLIC_DEBUG` | `false` | Must be false when `ENV=hosted` |
| `SOURCELINE_LOG_QUESTIONS` | `false` | Redacted question/answer text; local only |
| `SOURCELINE_LOG_LEVEL` | `INFO` | |
| `SOURCELINE_LOG_FORMAT` | `json` | `json` or `console` |

### 2.2 Providers

| Variable | Default | Notes |
|---|---|---|
| `SOURCELINE_OPENAI_API_KEY` | empty | Required unless the test fake profile is explicit |
| `SOURCELINE_OPENAI_BASE_URL` | `https://api.openai.com/v1` | Point at Azure/Ollama-compatible endpoint if needed |
| `SOURCELINE_EMBEDDING_MODEL` | `text-embedding-3-small` | Pinned; changing requires full reindex |
| `SOURCELINE_EMBEDDING_DIMENSIONS` | `1536` | Must match the schema; 768 needs a migration |
| `SOURCELINE_CHAT_MODEL` | `gpt-4.1-mini` | Pinned; verify availability at build time |
| `SOURCELINE_CHAT_TEMPERATURE` | `0` | |
| `SOURCELINE_CHAT_MAX_OUTPUT_TOKENS` | `500` | |
| `SOURCELINE_EMBED_TIMEOUT_SECONDS` | `3` | Per attempt |
| `SOURCELINE_CHAT_TIMEOUT_SECONDS` | `20` | Per attempt |
| `SOURCELINE_PROVIDER_MAX_RETRIES` | `0` | SDK retries disabled; must stay 0 |

### 2.3 Retrieval and budget

| Variable | Default | Notes |
|---|---|---|
| `SOURCELINE_TOP_K` | `8` | Final evidence count |
| `SOURCELINE_CANDIDATE_K` | `40` | Retrieval over-fetch |
| `SOURCELINE_EF_SEARCH` | `80` | HNSW query-time candidate list |
| `SOURCELINE_SCORE_FLOOR` | `0.20` | Calibrate on the dev split |
| `SOURCELINE_CONTEXT_BUDGET_TOKENS` | `6000` | Total |
| `SOURCELINE_ANSWER_RESERVE_TOKENS` | `700` | Output + safety |
| `SOURCELINE_MAX_WORDS` | `200` | Answer length |
| `SOURCELINE_LEXICAL_FALLBACK` | `true` | Only for embedding outages |
| `SOURCELINE_LEXICAL_SCORE_FLOOR` | `0.05` | `ts_rank_cd` scale; calibrate |
| `SOURCELINE_REQUEST_DEADLINE_SECONDS` | `30` | Overall |
| `SOURCELINE_TOKENIZER_ENCODING` | `o200k_base` | Must match the chat model family |

### 2.4 Corpus and chunking

| Variable | Default | Notes |
|---|---|---|
| `SOURCELINE_CORPUS_ROOT` | `../..` (local) / `/corpus` (compose) | Absolute or project-relative |
| `SOURCELINE_SOURCE_BASE_URL` | empty | e.g. `https://github.com/<owner>/<repo>/blob` |
| `SOURCELINE_EXPECTED_COMMIT` | empty | If set, readiness warns on mismatch |
| `SOURCELINE_MAX_INDEX_AGE_SECONDS` | empty | If set, readiness warns when older |
| `SOURCELINE_CHUNKER_VERSION` | `markdown-h2-v1` | Change only with a full reindex |
| `SOURCELINE_CHUNK_TARGET_CHARS` | `1200` | |
| `SOURCELINE_CHUNK_OVERLAP_CHARS` | `150` | |
| `SOURCELINE_CHUNK_MAX_CHARS` | `1800` | |
| `SOURCELINE_EMBED_BATCH_SIZE` | `64` | |

The **profile key** is derived:
`{chunker}|{target}|{overlap}|{embedding_model}|{dimensions}`. Do not set it by hand.

### 2.5 Ops and safety

| Variable | Default | Notes |
|---|---|---|
| `SOURCELINE_RATE_LIMIT_PER_MIN` | `60` | Query |
| `SOURCELINE_RATE_LIMIT_BURST` | `10` | |
| `SOURCELINE_QUERY_CONCURRENCY_PER_IP` | `5` | |
| `SOURCELINE_QUERY_CONCURRENCY_GLOBAL` | `8` | |
| `SOURCELINE_ADMIN_RATE_LIMIT_PER_MIN` | `10` | |
| `SOURCELINE_MAX_BODY_BYTES` | `32768` | |
| `SOURCELINE_DAILY_BUDGET_USD` | `0` | 0 = disabled; hosted should set |
| `SOURCELINE_TRUST_PROXY` | `false` | Only true behind a trusted proxy |
| `SOURCELINE_CORS_ORIGINS` | empty | Comma-separated; UI is same-origin |
| `SOURCELINE_DB_POOL_MIN` | `2` | |
| `SOURCELINE_DB_POOL_MAX` | `10` | |
| `SOURCELINE_RETRY_AFTER_CAP_SECONDS` | `30` | Ingestion cap; query paths clamp to 10 s |
| `SOURCELINE_CIRCUIT_FAILURE_THRESHOLD` | `5` | |
| `SOURCELINE_CIRCUIT_OPEN_SECONDS` | `30` | |
| `SOURCELINE_METRICS_ENABLED` | `true` | |
| `SOURCELINE_OTEL_ENABLED` | `false` | Optional |

### 2.6 Startup validation

The app refuses to start when:

- `SOURCELINE_ENV=hosted` and `SOURCELINE_PUBLIC_DEBUG=true`;
- `SOURCELINE_ENV=hosted` and `SOURCELINE_DAILY_BUDGET_USD=0`;
- `PROVIDER_MAX_RETRIES != 0`;
- the embedding dimensions do not match the schema/profile;
- required provider settings are missing for the selected provider;
- `top_k > candidate_k` or budgets are impossible;
- the admin token is missing while admin routes are enabled.

---

## 3. Docker quickstart (reviewer path)

```bash
git clone <repo-url>
cd <repo>/phase-03-embeddings-rag/project-01-rag-service
cp .env.example .env
# edit .env: set SOURCELINE_OPENAI_API_KEY and SOURCELINE_ADMIN_TOKEN

docker compose up -d db
docker compose run --rm api python -m sourceline.migrate
docker compose run --rm api python -m sourceline.ingest --root /corpus
docker compose up api
```

Then:

```bash
curl -s http://127.0.0.1:8000/v1/ready
curl -s http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"How does HNSW trade recall for speed?","top_k":6}'
```

Open <http://127.0.0.1:8000/> for the UI.

### 3.1 Compose shape

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: sourceline
      POSTGRES_PASSWORD: sourceline
      POSTGRES_DB: sourceline
    volumes:
      - sourceline_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sourceline -d sourceline"]
      interval: 5s
      timeout: 3s
      retries: 20
    ports:
      - "127.0.0.1:5432:5432"   # local only; remove in hosted

  api:
    build: .
    env_file: .env
    environment:
      SOURCELINE_DATABASE_URL: postgresql://sourceline:sourceline@db:5432/sourceline
      SOURCELINE_CORPUS_ROOT: /corpus
    volumes:
      - ../..:/corpus:ro
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/v1/health"]
      interval: 10s
      timeout: 3s
      retries: 10

volumes:
  sourceline_pgdata:
```

The corpus mount is `../..` because the project lives two levels below the repository root. It is
read-only; ingestion writes only to Postgres.

### 3.2 Dockerfile requirements

- Multi-stage: builder installs locked dependencies; runtime has only the app + production deps.
- Run as a non-root user.
- No compiler/toolchain in the runtime image.
- `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`.
- Healthcheck uses `/v1/health` (liveness), not `/v1/ready`.
- Pinned base image digest at release.
- The image must not contain `.env`, tests, eval reports, or the corpus snapshot unless built for
  hosted mode.

---

## 4. Local Python quickstart (development)

```powershell
cd phase-03-embeddings-rag/project-01-rag-service
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

$env:SOURCELINE_DATABASE_URL="postgresql://sourceline:sourceline@127.0.0.1:5432/sourceline"
$env:SOURCELINE_CORPUS_ROOT="..\.."
$env:SOURCELINE_OPENAI_API_KEY="..."
$env:SOURCELINE_ADMIN_TOKEN="..."

python -m sourceline.migrate
python -m sourceline.ingest --root ..\..
uvicorn sourceline.main:app --reload
```

On macOS/Linux, use `source .venv/bin/activate` and POSIX paths. Start Postgres via Docker
(`docker compose up -d db`) even if the app runs locally; that avoids a system PostgreSQL install.

---

## 5. Migrations

```bash
python -m sourceline.migrate            # apply pending
python -m sourceline.migrate --status   # show applied/pending
python -m sourceline.migrate --check    # exit 1 if pending (CI/release)
```

- Files are ordered lexically; each runs in a transaction.
- The runner takes an advisory lock; concurrent migrations cannot interleave.
- Checksums are verified; an edited applied migration is a hard failure.
- Forward-only. Destructive changes require a backup and a new migration.
- `CREATE EXTENSION vector` requires privileges; run it once as an operator if the app role cannot.
- Readiness fails if the database has fewer migrations than the image expects.

---

## 6. Ingest and reindex

### 6.1 Normal corpus edit

```bash
python -m sourceline.ingest --root ../..
```

- Changed-only by default; unchanged documents cost zero embeddings.
- `--dry-run` prints the plan without writes.
- `--prune` removes documents deleted from the corpus.
- Review the report; exit code 3/4/5 means investigate before deploying.

### 6.2 Full rebuild

```bash
# Profile/chunker/model change or corruption
python -m sourceline.ingest --root ../.. --scope full --confirm-full
```

This is a maintenance operation: readiness returns 503 while `index_state.status='building'`. Run it
before starting the new API version, or accept a short outage. A future blue/green profile rebuild is
described in [`data-model.md`](data-model.md#62-full-rebuild-maintenance).

### 6.3 Admin endpoint

```bash
curl -X POST http://127.0.0.1:8000/v1/admin/reindex \
  -H "Authorization: Bearer $SOURCELINE_ADMIN_TOKEN" \
  -H "Idempotency-Key: reindex-$(date +%Y%m%d-%H%M)" \
  -H "Content-Type: application/json" \
  -d '{"scope":"changed","prune":true}'
```

The CLI is canonical for long runs. The endpoint runs a background thread in v1 and is convenient for
the demo; do not expose it publicly.

---

## 7. Hosted demo (optional)

### 7.1 Topology

- One API container on Fly.io / Render / a small VM.
- Managed Postgres with pgvector ≥ 0.8 (or a sidecar Postgres with a persistent volume).
- Corpus snapshot baked into the image at build time; no runtime mount.
- Secrets in the platform store; no `.env` in the image.
- TLS at the edge; `/metrics` and admin routes blocked.
- Public query rate limit + daily budget; hosted env checks enforced.

### 7.2 Build with a corpus snapshot

The Docker build context is the project folder, so `../..` is not available. Before building:

```bash
python scripts/build_corpus_snapshot.py --root ../.. --out corpus/snapshot
docker build -t sourceline .
```

The snapshot is generated, ignored by default, and includes a manifest with hashes/commit. The image
sets `SOURCELINE_CORPUS_ROOT=/corpus` and copies the snapshot there. The release records the snapshot
hash; rebuilding with a different snapshot is a deliberate reindex.

### 7.3 Release sequence

```text
1. backup database
2. build image with corpus snapshot
3. run migrations (one-off release command)
4. run ingest --scope changed (or full for profile changes)
5. start/roll the API
6. check /v1/ready, /v1/health, a smoke query
7. run eval smoke against the deployed URL (admin disabled; use public query)
```

If step 4 changes rows while the old API serves, the old API remains compatible because the schema is
additive and the profile is unchanged. For a profile change, use the maintenance path.

### 7.4 Cost controls

- Set `SOURCELINE_DAILY_BUDGET_USD` (e.g. 5).
- Per-IP rate and concurrency limits at the app and edge.
- Cap `max_output_tokens` and `top_k`.
- Revoke the key or scale to zero to stop spend.
- Alert at 80% of the cap.

---

## 8. Backup and restore

### 8.1 Backup

```bash
docker compose exec -T db pg_dump -U sourceline -Fc sourceline > backups/sourceline-$(date +%Y%m%d).dump
```

- Encrypt at rest; store outside the host.
- Back up before destructive migrations and before a full rebuild.
- Verify the dump is non-empty and restorable (a backup you never restore is a hope).

### 8.2 Restore drill (quarterly)

```bash
docker compose up -d db
docker compose exec -T db dropdb -U sourceline --if-exists sourceline_restore
docker compose exec -T db createdb -U sourceline sourceline_restore
docker compose exec -T db pg_restore -U sourceline -d sourceline_restore < backups/<file>.dump
# point a temporary SOURCELINE_DATABASE_URL at sourceline_restore, run migrate --check and /v1/ready
```

Record the drill date/result. The restore is not complete until readiness and a smoke query pass.

---

## 9. Runbook

| Symptom | Check | Action |
|---|---|---|
| `/v1/health` fails | process, port, logs | Restart container; check OOM; inspect startup error |
| `/v1/ready` 503 `database_unavailable` | DB container, credentials, pool | Start/restore DB; verify URL; restart pool; check disk |
| `/v1/ready` 503 `index_not_ready` | `index_state`, counts | Run migrate/ingest; check failed run |
| `/v1/ready` 503 `index_profile_mismatch` | active vs configured profile | Reindex with the configured profile; do not mix |
| `/v1/ready` `stale=true` | `age_seconds`, commit | Re-ingest; update `SOURCELINE_EXPECTED_COMMIT` |
| Query 503 `upstream_unavailable` | provider status, retry/breaker metrics | Wait for cooldown; verify key/model/quota; check status page |
| Query 503 `upstream_rate_limited` | provider quota, `Retry-After` logs | Back off; raise quota; reduce concurrency |
| Query 503 `circuit_open` | breaker gauge | Fix dependency; wait for half-open; do not restart-loop |
| Query 504 | stage timings | Reduce `top_k`/output; inspect provider latency; raise deadline only with evidence |
| Query 429 | rate-limit headers | Client is over limit; wait or raise limit deliberately |
| Extractive spike | chat breaker | Restore chat provider; verify labels; check key/quota |
| Lexical spike | embedding breaker | Restore embeddings; verify FTS quality |
| Ingest partial | `ingest_runs.error_code`, failed doc | Fix file/provider; re-run; unchanged docs skip |
| Ingest locked | another run | Wait; check for a hung process; advisory lock clears on session end |
| High cost | tokens/query, repair rate | Lower budget/top_k; check retries/repairs; cap |
| Bad citations | sample `query_logs`/debug | Validate marker map; check stale chunk/line drift; re-ingest |
| Disk full | `df`, DB size | Free space; prune logs; expand volume; re-run failed writes |
| Container can't read corpus | mount path/permissions | Verify `../..:/corpus:ro`; check file ownership |
| `vector` extension missing | `\dx` | `CREATE EXTENSION vector` as an operator; rerun migrations |
| Dimension mismatch | pgvector error | Confirm profile; rebuild with the correct dimension/migration |

Every runbook action that changes state gets a log line or a note in the incident template.

---

## 10. Rollback

| Change | Rollback |
|---|---|
| API image | Redeploy the previous image tag; schema is additive/backward-compatible |
| Migration | Forward-only: write a compensating migration; restore backup if destructive |
| Embedding profile | Keep the old table/backup; full rebuild back; readiness blocks mixed profiles |
| Corpus content | `git revert` the note, re-ingest; old chunks are replaced only after commit |
| Bad prompt/config | Revert config/image; re-run eval smoke; no data change |
| Secret leak | Rotate key/token immediately; redeploy; invalidate old credentials |

Never "roll back" by deleting rows without a backup. The index is reproducible from the corpus +
profile, which is the real recovery asset.

---

## 11. CI/CD

- PR: lint, types, tests, offline eval smoke, Docker build.
- Release: build/push image with a corpus snapshot; run migrations; ingest; deploy; smoke query;
  attach eval report.
- No automatic ingest of arbitrary URLs; no automatic key rotation in v1.
- Migrations run before the new API starts; readiness gates traffic.
- A failed readiness keeps the old version serving (platform-dependent); otherwise roll back.

---

## 12. Fresh-machine acceptance checklist

- [ ] Docker Desktop/Engine and Compose are installed.
- [ ] Clone + `cd` to the project; `.env` created from the example.
- [ ] `docker compose up -d db` is healthy.
- [ ] Migrate applies with no manual SQL.
- [ ] Ingest completes with the expected document count and no failures.
- [ ] `docker compose up api` reaches `ready`.
- [ ] UI loads; three demo questions return cited answers.
- [ ] One unanswerable question abstains.
- [ ] `pytest -q` passes (if running the dev path).
- [ ] No undocumented step, no secret committed, no port conflict.
- [ ] Total time from clone to first answer ≤ 10 minutes (excluding model download/provider latency).

If any box fails, the README is not done. The project's definition of done is the reviewer's
experience, not the author's machine.

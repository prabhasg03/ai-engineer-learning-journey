# Incident — <YYYY-MM-DD> — <short title>

| Field | Value |
|---|---|
| Incident ID | `INC-<YYYYMMDD>-<n>` |
| Severity | SEV-1 / SEV-2 / SEV-3 |
| Status | Investigating / Mitigated / Resolved |
| Detected by | Alert / user report / drill |
| Start / detected / resolved | `<timestamps>` |
| Owner | `<name/role>` |
| Affected surface | Query / ingest / admin / demo |
| Request IDs / run IDs | `<...>` |

---

## 1. Summary

Two or three sentences: what happened, who was affected, how it was fixed.

## 2. Impact

- Queries failed: `<n>` / `<%>`
- Degraded responses: `<n>`
- False answers suspected: `<n>`
- Data loss/corruption: `<none / describe>`
- Cost impact: `<$>`
- Duration: `<...>`

## 3. Timeline

| Time (UTC) | Event |
|---|---|
| | Deploy/change |
| | First symptom |
| | Alert fired |
| | Investigation started |
| | Mitigation applied |
| | Resolved |

## 4. Detection

- Which signal fired (metric/alert/log/user)?
- How long between cause and detection?
- What made it visible or invisible?
- If a drill found it, link the drill.

## 5. Root cause

State the technical cause, not "human error". Include the failing stage (retrieval, assembly,
generation, dependency, database, deploy) and the evidence (request ID, logs, metrics).

## 6. Contributing factors

- Configuration:
- Missing test/alert:
- Dependency behaviour:
- Documentation gap:
- Time pressure/scope:

## 7. Response and recovery

- Immediate mitigation:
- Data restored/reingested:
- Rollback:
- Verification (readiness, smoke query, eval):
- Communication:

## 8. What went well

- `<e.g. breaker prevented a retry storm>`
- `<e.g. degraded mode stayed labelled>`

## 9. What went poorly

- `<e.g. no alert on index age>`
- `<e.g. runbook step missing>`

## 10. Follow-ups

| Action | Owner | Due | Status |
|---|---|---|---|
| Add regression test | | | |
| Add/adjust alert | | | |
| Update runbook | | | |
| Fix root cause | | | |
| Update risk register | | | |

## 11. Lessons

One paragraph a future operator can learn from. No blame; focus on system conditions.

## 12. Links

- Dashboard / query:
- Logs / request IDs:
- Commit / deploy:
- Related eval case/issue:

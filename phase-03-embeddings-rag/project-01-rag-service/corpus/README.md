# Corpus Notes — Sourceline

This folder is **not** the corpus. The corpus is the curriculum Markdown already in the repository:

```text
phase-01-llm-fundamentals/**/*.md
phase-02-llm-apis/**/*.md
phase-03-embeddings-rag/**/*.md
```

`corpus/` holds the manifest contract, corpus-specific documentation, and an optional generated
snapshot for container builds.

---

## 1. Inventory (2026-10-26)

| Property | Value |
|---|---:|
| Markdown documents | 38 |
| Words | 83,348 |
| Raw size | ~594 KB |
| Approx. tokens | ~105k–115k |
| Expected chunks | ~300–380 (after chunking) |
| Language | English (technical) |
| Encoding | UTF-8 |

The ingester's report is authoritative. If a note is added or removed, update this table, the README,
and the evaluation labels after re-ingest. Do not let the docs claim a stale count.

---

## 2. Include / exclude rules

| Rule | Value |
|---|---|
| Include | `phase-01-llm-fundamentals/**/*.md`, `phase-02-llm-apis/**/*.md`, `phase-03-embeddings-rag/**/*.md` |
| Exclude dirs | `**/implementation/**`, `**/__pycache__/**`, `**/.pytest_cache/**`, `**/.venv/**`, `**/.git/**`, `**/node_modules/**`, `**/project-01-rag-service/**` |
| Exclude files | hidden files, non-`.md`, > 2 MB, symlinks |
| Phase READMEs | Included if present |
| Root `README.md` / `SYLLABUS.md` | Excluded by default; `--include-meta` opts in |
| Ordering | POSIX path ascending (byte order) |
| Duplicate case-insensitive paths | Rejected |

Why exclude the project folder? To avoid indexing the service's own design docs and answering about
itself instead of the curriculum. The README/docs remain for a human reviewer.

---

## 3. Normalisation and provenance

Before hashing/chunking:

1. UTF-8 strict decode; reject invalid bytes.
2. Strip BOM.
3. CRLF/CR → LF.
4. Strip trailing spaces/tabs; preserve leading indentation.
5. Ensure one trailing newline.
6. Do not reflow text, strip HTML comments, or rewrite links.

Line numbers refer to the normalised file and match GitHub's line view. `doc_id` is the POSIX relative
path. `source_commit` is the git commit at ingest. Citations are built as:

```text
{SOURCELINE_SOURCE_BASE_URL}/{commit}/{doc_id}#L{start}-L{end}
```

If `SOURCELINE_SOURCE_BASE_URL` is unset, citations carry the path and lines only; the UI shows a local path.
This is the correct fallback for a private checkout.

---

## 4. Manifest

The ingester can write a deterministic manifest:

```bash
python -m sourceline.ingest --root ../.. --dry-run --write-manifest corpus/manifest.json
```

Shape (schema: [`manifest.schema.json`](manifest.schema.json)):

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-26T10:10:00Z",
  "source_commit": "a01637a",
  "profile_key": "markdown-h2-v1|1200|150|text-embedding-3-small|1536",
  "root": ".",
  "documents": [
    {
      "doc_id": "phase-03-embeddings-rag/topic-25-pgvector/notes.md",
      "title": "Topic 25 — pgvector",
      "phase": 3,
      "topic": 25,
      "doc_type": "notes",
      "content_hash": "5e2c...",
      "byte_size": 18234,
      "word_count": 3180,
      "line_count": 412
    }
  ]
}
```

The manifest is a diff input, not a second source of truth for chunk text. Do not hand-edit hashes.
A committed manifest is optional; commit it for release provenance if useful, and regenerate it when
the corpus changes.

---

## 5. Snapshot

The Docker build context is this project folder, so `../..` is not available to `docker build`. For a
hosted image, generate a snapshot:

```bash
python scripts/build_corpus_snapshot.py --root ../.. --out corpus/snapshot
```

- `corpus/snapshot/` is generated and ignored by default.
- It contains only the included Markdown plus a manifest.
- The image copies it to `/corpus` and sets `SOURCELINE_CORPUS_ROOT=/corpus`.
- Record the snapshot hash/commit in the release notes.
- Local Compose uses a read-only mount of the repository root instead; no snapshot needed.

Do not commit a stale snapshot that silently diverges from the notes. Either regenerate it in the
release pipeline or omit it.

---

## 6. Licence and privacy

- The curriculum text is authored in this repository; the project code is MIT (see root `LICENSE` at
  implementation). The corpus is included as the demo document set; quoted third-party material in
  the notes remains under its original licence.
- Do not add private notes, credentials, customer data, or personal information to the corpus. The
  corpus is sent to the configured embedding/chat provider when the service runs.
- A future third-party corpus requires a licence review and an adapter with provenance metadata.

---

## 7. Corpus change checklist

When adding/editing/deleting a note:

- [ ] Re-run discovery; confirm the document count and hashes.
- [ ] Re-ingest changed-only; review inserted/updated/deleted chunks.
- [ ] Confirm `embedded=0` on a second run.
- [ ] Check citations for a known question still resolve to the right lines.
- [ ] Update the README/corpus inventory if counts changed.
- [ ] Re-check eval gold doc IDs/facts for the changed note.
- [ ] If the change affects a topic, add a question to the eval set (especially for a fixed failure).
- [ ] Commit the note and the doc updates together; do not commit a generated snapshot unless intended.

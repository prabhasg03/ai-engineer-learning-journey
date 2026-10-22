"""Topic 26 - the retrieval pipeline, end to end.

One offline, deterministic implementation of the whole path:

    ingest -> chunk -> embed -> store -> query -> retrieve -> assemble -> answer

Everything that would normally be a network dependency is a hand-written,
seeded stand-in:

- the *embedder* is signed feature hashing over word uni/bi-grams (same
  mechanics as a real model: fixed dimensions, unit-length outputs, silent
  zero vectors for empty input - but no semantics beyond shared words);
- the *store* is a dict of rows with the same contract as a vector table
  (idempotent upsert by chunk id, stale-row deletion, cosine search);
- the *answerer* is extractive: it quotes the best-matching sentence and
  attaches a citation. That is the deterministic stand-in for the LLM call
  at the end of a real pipeline.

The point of the topic is not the stand-ins: it is the *contracts between
stages* and the places each stage fails **silently** - wrong output, no
error. Those are modelled explicitly:

- ``ingest`` diffs chunk content hashes, so re-ingesting an unchanged
  document costs zero embedding calls; changed chunks are re-embedded and
  removed chunks are deleted (no orphans);
- ``reindex_reason`` surfaces the three real re-index triggers: new
  document, content change, and profile change (model / dimensions /
  chunker version);
- ``SILENT_FAILURES`` names what each stage can swallow, and
  ``Pipeline.diagnose`` detects the conditions in a live pipeline;
- ``Pipeline.trace_document`` is the done-when artifact: one document walked
  through all eight stages with the numbers each stage produced.

Everything is deterministic (SHA-256 hashing, no ``hash()``, no clock, no
network).
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Stages, tokenisation, hashing
# ---------------------------------------------------------------------------

STAGES = (
    "ingest",
    "chunk",
    "embed",
    "store",
    "query",
    "retrieve",
    "assemble",
    "answer",
)

# A real embedding endpoint truncates anything past its input window. We
# model that window in characters (the pipeline itself never truncates; it
# only WARNs, because the provider's silent truncation is the failure).
MAX_EMBED_INPUT_CHARS = 8_000

_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]*")
_PARAGRAPH_RE = re.compile(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Same tokenisation everywhere in the pipeline."""
    return _TOKEN_RE.findall(text.lower())


STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on",
        "at", "by", "for", "with", "from", "as", "is", "are", "was", "were", "be",
        "been", "being", "do", "does", "did", "have", "has", "had", "i", "you", "it",
        "we", "they", "he", "she", "my", "our", "your", "their", "this", "that",
        "these", "those", "what", "which", "who", "how", "many", "much", "can",
        "could", "should", "would", "will", "not", "no", "there", "here",
    }
)


def content_terms(text: str) -> list[str]:
    """Tokens minus stopwords - the overlap that actually carries meaning."""
    return [token for token in tokenize(text) if token not in STOPWORDS]


def content_hash(text: str) -> str:
    """Stable content identity (SHA-256, not Python's salted hash())."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The stand-in embedder
# ---------------------------------------------------------------------------


def _stable_int(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


class HashingEmbedder:
    """Deterministic signed feature hashing over words and word bigrams.

    A real embedding model maps text to a fixed-width, L2-normalised vector
    learned from data. This one maps text to a fixed-width, L2-normalised
    vector derived from SHA-256 - so the *mechanics* (dimensions, batching,
    unit sphere, silent zero vectors) are real even though the semantics are
    only "shared words".
    """

    def __init__(self, dimensions: int = 8192, model_name: str = "hashing-8192-v1") -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.model_name = model_name
        self.calls = 0  # batch calls made (the cost unit we track)
        self.texts_embedded = 0

    def embed_one(self, text: str) -> list[float]:
        """One text -> unit vector. Empty / token-less text -> zero vector.

        The zero vector is deliberate: real providers reject empty strings,
        but an upstream bug that hands the embedder "" or whitespace produces
        a zero vector whose cosine is NaN - it is silently unretrievable.
        """
        vector = [0.0] * self.dimensions
        tokens = content_terms(text)  # glue words carry no retrieval signal here
        features = list(tokens)
        features += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for feature in features:
            idx = _stable_int("f:" + feature) % self.dimensions
            sign = 1.0 if _stable_int("s:" + feature) % 2 == 0 else -1.0
            vector[idx] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]

    def embed_batch(self, texts: list[str], batch_size: int = 4) -> list[list[float]]:
        """Embed a list in fixed-size batches, returning vectors in order.

        Batching is the difference between one API call per chunk and one per
        few hundred chunks. ``self.calls`` counts requests, not texts, so
        tests can prove batching happened (and that idempotent re-ingest made
        zero calls).
        """
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            self.calls += 1
            for text in texts[start : start + batch_size]:
                vectors.append(self.embed_one(text))
                self.texts_embedded += 1
        return vectors


# ---------------------------------------------------------------------------
# Documents and chunks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str

    @property
    def content_hash(self) -> str:
        return content_hash(self.text)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    start: int
    end: int
    content_hash: str
    chunker_version: str
    hard_split: bool = False


def split_sentences(text: str) -> list[str]:
    """Sentence-ish split used only for over-long paragraphs."""
    return [part.strip() for part in _SENTENCE_RE.findall(text) if part.strip()]


def chunk_document(
    document: Document,
    max_chars: int = 300,
    chunker_version: str = "paragraph-v1",
) -> list[Chunk]:
    """Split a document into stable, paragraph-aware chunks.

    Contract:
    - paragraphs (blank-line separated) are the preferred boundary;
    - an over-long paragraph is split on sentence ends, then hard-split if a
      single sentence is still over budget (and flagged);
    - chunk ids are ``<doc_id>#<ordinal>`` so re-ingesting the same document
      produces the same ids, which is what makes upserts idempotent.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    units: list[tuple[int, str, bool]] = []  # (start offset, text, hard_split)
    for paragraph_match in _PARAGRAPH_RE.finditer(document.text):
        paragraph = paragraph_match.group(0)
        if not paragraph.strip():
            continue
        paragraph_start = paragraph_match.start()
        if len(paragraph) <= max_chars:
            units.append((paragraph_start, paragraph.strip(), False))
            continue
        for sentence_match in _SENTENCE_RE.finditer(paragraph):
            sentence = sentence_match.group(0).strip()
            if not sentence:
                continue
            sentence_start = paragraph_start + sentence_match.start()
            if len(sentence) <= max_chars:
                units.append((sentence_start, sentence, False))
            else:
                for offset in range(0, len(sentence), max_chars):
                    units.append((sentence_start + offset, sentence[offset : offset + max_chars], True))

    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_start: int | None = None
    buffer_end = 0

    def flush() -> None:
        nonlocal buffer, buffer_start, buffer_end
        if not buffer:
            return
        text = "\n\n".join(buffer)
        ordinal = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}#{ordinal:02d}",
                doc_id=document.doc_id,
                ordinal=ordinal,
                text=text,
                start=buffer_start if buffer_start is not None else 0,
                end=buffer_end,
                content_hash=content_hash(text),
                chunker_version=chunker_version,
                hard_split=hard_split_seen,
            )
        )
        buffer, buffer_start = [], None

    for start, unit, was_split in units:
        candidate_length = sum(len(part) for part in buffer) + len(unit) + (2 * len(buffer))
        if buffer and candidate_length > max_chars:
            flush()
        if buffer_start is None:
            buffer_start = start
            hard_split_seen = False
        buffer.append(unit)
        buffer_end = start + len(unit)
        hard_split_seen = hard_split_seen or was_split
    flush()
    return chunks


# ---------------------------------------------------------------------------
# The vector store
# ---------------------------------------------------------------------------


@dataclass
class StoredChunk:
    chunk_id: str
    doc_id: str
    text: str
    vector: list[float]
    content_hash: str
    model_name: str
    dimensions: int
    chunker_version: str


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"different vector dimensions {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return dot / (na * nb)


class VectorStore:
    """A dict-backed stand-in for a vector table.

    The contract that matters: ``upsert`` is keyed by ``chunk_id``, so
    replaying the same chunk is a no-op; ``delete_document_except`` removes
    rows the new version no longer contains (the classic stale-chunk bug is
    *not* deleting them).
    """

    def __init__(self) -> None:
        self.rows: dict[str, StoredChunk] = {}

    def upsert(self, row: StoredChunk) -> str:
        existing = self.rows.get(row.chunk_id)
        if existing is None:
            self.rows[row.chunk_id] = row
            return "inserted"
        if existing.content_hash == row.content_hash and existing.model_name == row.model_name:
            return "unchanged"
        self.rows[row.chunk_id] = row
        return "updated"

    def delete_document_except(self, doc_id: str, keep: set[str]) -> int:
        stale = [cid for cid, row in self.rows.items() if row.doc_id == doc_id and cid not in keep]
        for chunk_id in sorted(stale):
            del self.rows[chunk_id]
        return len(stale)

    def delete_document(self, doc_id: str) -> int:
        stale = [cid for cid, row in self.rows.items() if row.doc_id == doc_id]
        for chunk_id in stale:
            del self.rows[chunk_id]
        return len(stale)

    def rows_for_document(self, doc_id: str) -> list[StoredChunk]:
        return [row for row in self.rows.values() if row.doc_id == doc_id]

    def search(
        self,
        query_vector: list[float],
        k: int = 3,
        where: dict | None = None,
    ) -> list[tuple[StoredChunk, float]]:
        """Cosine search; NaN scores (zero vectors) sort last, never crash."""
        hits: list[tuple[StoredChunk, float]] = []
        for row in self.rows.values():
            if where is not None and any(getattr(row, key, None) != value for key, value in where.items()):
                continue
            hits.append((row, cosine_similarity(query_vector, row.vector)))
        hits.sort(key=lambda pair: (math.isnan(pair[1]), -pair[1] if not math.isnan(pair[1]) else 0.0, pair[0].chunk_id))
        return hits[: max(0, int(k))]

    def __len__(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Reports and traces
# ---------------------------------------------------------------------------


@dataclass
class IngestReport:
    doc_id: str
    reason: str
    chunks_total: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    embedded: int = 0
    embed_batches: int = 0
    zero_vectors: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Citation:
    number: int
    chunk_id: str
    doc_id: str
    title: str


@dataclass
class Retrieval:
    query: str
    hits: list[tuple[StoredChunk, float]]
    zero_query: bool
    k: int

    @property
    def missing(self) -> int:
        return max(0, self.k - len(self.hits))


@dataclass
class AssembledContext:
    text: str
    citations: list[Citation]
    used_chars: int
    budget_chars: int
    dropped: list[str] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)

    def citation_map(self) -> dict[str, int]:
        return {citation.chunk_id: citation.number for citation in self.citations}


@dataclass
class Answer:
    text: str
    citations: list[int]
    evidence_chunk_ids: list[str]
    abstained: bool


@dataclass(frozen=True)
class StageTrace:
    stage: str
    summary: str
    details: dict


@dataclass
class DocumentTrace:
    """The done-when artifact: one document, all eight stages, no gaps."""

    document: Document
    question: str
    stages: list[StageTrace]
    answer: Answer

    def format(self) -> str:
        lines = [f"trace: {self.document.doc_id} -> {self.question!r}"]
        for stage in self.stages:
            lines.append(f"  {stage.stage:<9} {stage.summary}")
            for key, value in stage.details.items():
                lines.append(f"            {key}: {value}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Silent-failure catalogue (the topic's second deliverable)
# ---------------------------------------------------------------------------

SILENT_FAILURES: dict[str, tuple[str, ...]] = {
    "ingest": (
        "an unsupported/corrupt file yields zero documents and the job still reports success",
        "a duplicate doc_id overwrites (or is skipped by) the previous version without a diff",
        "an HTML/PDF loader returns navigation chrome as if it were content",
    ),
    "chunk": (
        "a document shorter than the chunker window produces one giant chunk that the embedder truncates",
        "the last chunk is a 30-character stub whose embedding matches everything weakly",
        "tables and code fences are sliced mid-structure - retrieval still returns something",
    ),
    "embed": (
        "input beyond the model window is truncated by the provider without an error",
        "empty/OOV text becomes a zero vector: stored fine, cosine=NaN, never retrieved",
        "a retried batch silently drops the rows that failed instead of failing the job",
    ),
    "store": (
        "stale chunks from the previous document version remain and can outrank fresh ones",
        "batched writes partially succeed and the ingest counter still says 'done'",
        "a dimension mismatch is coerced by an adapter instead of rejected",
    ),
    "query": (
        "the query is empty or all stopwords -> zero vector -> zero results, not an error",
        "query and documents are embedded with different models/prefixes (scores are meaningless)",
        "the wrong distance operator ranks a normalized store but returns plausible-looking rows",
    ),
    "retrieve": (
        "k is larger than the number of stored chunks, so fewer rows silently reach the prompt",
        "post-filtering (WHERE after ANN) returns fewer than k rows for narrow filters",
        "ANN recall is below 1.0 and the missing row is the one that held the answer",
    ),
    "assemble": (
        "the context budget silently truncates the chunk that contained the answer",
        "duplicate near-identical chunks eat the budget and push out the diverse evidence",
        "the question is buried mid-context; models attend to the edges (lost in the middle)",
    ),
    "answer": (
        "the model answers from parametric memory and cites nothing (or the wrong source)",
        "an abstention arrives as a confident-sounding answer with no support",
        "citation numbers are renumbered after pruning and no longer match the prompt",
    ),
}


def silent_failure_notes(stage: str) -> tuple[str, ...]:
    if stage not in SILENT_FAILURES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {list(STAGES)}")
    return SILENT_FAILURES[stage]


@dataclass(frozen=True)
class Issue:
    stage: str
    code: str
    message: str
    severity: str = "warning"


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """The whole path, with the contracts that make it idempotent."""

    def __init__(
        self,
        embedder: HashingEmbedder | None = None,
        chunker_version: str = "paragraph-v1",
        max_chars: int = 300,
        batch_size: int = 4,
    ) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.chunker_version = chunker_version
        self.max_chars = max_chars
        self.batch_size = batch_size
        self.store = VectorStore()
        self.manifests: dict[str, dict] = {}
        self.last_ingest: dict[str, IngestReport] = {}

    # -- profile / re-index triggers ---------------------------------------

    @property
    def profile_key(self) -> str:
        """Everything that makes stored vectors incompatible if it changes."""
        return (
            f"{self.embedder.model_name}|{self.embedder.dimensions}|"
            f"{self.chunker_version}|{self.max_chars}"
        )

    def reindex_reason(self, document: Document) -> str | None:
        """None = up to date; otherwise the trigger that forces a rebuild.

        The three production triggers: a new document; changed content; a
        changed embedding/chunking profile. The profile change is the one
        teams forget - a new model makes every stored vector incomparable.
        """
        manifest = self.manifests.get(document.doc_id)
        if manifest is None:
            return "new_document"
        if manifest["profile_key"] != self.profile_key:
            return "profile_changed"
        if manifest["content_hash"] != document.content_hash:
            return "content_changed"
        return None

    # -- stage 1 + 2: ingest and chunk -------------------------------------

    def ingest(self, document: Document) -> IngestReport:
        """Load, chunk, embed (only what changed), store, prune, record.

        Idempotency contract:
        - same document + same profile -> zero chunks embedded;
        - changed chunk -> that chunk re-embedded and upserted;
        - removed chunk -> deleted (no orphans);
        - profile change -> all of the document's chunks rebuilt.
        """
        reason = self.reindex_reason(document)
        report = IngestReport(document.doc_id, reason or "unchanged")
        if reason is None:
            report.chunks_total = self.manifests[document.doc_id]["chunks"]
            report.unchanged = report.chunks_total
            report.warnings.append("unchanged: 0 embedding calls (idempotent)")
            self.last_ingest[document.doc_id] = report
            return report

        chunks = chunk_document(document, self.max_chars, self.chunker_version)
        report.chunks_total = len(chunks)
        if not chunks:
            report.warnings.append(
                "no chunks produced: the document is invisible to retrieval (empty/whitespace-only input)"
            )
            self.store.delete_document(document.doc_id)
            self.manifests[document.doc_id] = {
                "content_hash": document.content_hash,
                "profile_key": self.profile_key,
                "chunk_hashes": {},
                "chunks": 0,
            }
            self.last_ingest[document.doc_id] = report
            return report

        if reason == "profile_changed":
            report.deleted += self.store.delete_document(document.doc_id)

        new_ids = {chunk.chunk_id for chunk in chunks}
        report.deleted += self.store.delete_document_except(document.doc_id, new_ids)

        to_embed: list[Chunk] = []
        for chunk in chunks:
            existing = self.store.rows.get(chunk.chunk_id)
            if (
                existing is not None
                and existing.content_hash == chunk.content_hash
                and existing.model_name == self.embedder.model_name
                and existing.dimensions == self.embedder.dimensions
                and existing.chunker_version == self.chunker_version
            ):
                report.unchanged += 1
            else:
                to_embed.append(chunk)

        calls_before = self.embedder.calls
        vectors = (
            self.embedder.embed_batch([chunk.text for chunk in to_embed], self.batch_size)
            if to_embed
            else []
        )
        report.embed_batches = self.embedder.calls - calls_before
        report.embedded = len(to_embed)
        if to_embed and report.embed_batches == 0:
            report.warnings.append("embedding requested but no batch call was made")

        for chunk, vector in zip(to_embed, vectors):
            if len(vector) != self.embedder.dimensions:
                raise ValueError("embedder returned a vector of the wrong dimension")
            if all(value == 0.0 for value in vector):
                report.zero_vectors += 1
                report.warnings.append(
                    f"chunk {chunk.chunk_id} embedded to a zero vector (NaN cosine; silently unretrievable)"
                )
            status = self.store.upsert(
                StoredChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    text=chunk.text,
                    vector=vector,
                    content_hash=chunk.content_hash,
                    model_name=self.embedder.model_name,
                    dimensions=self.embedder.dimensions,
                    chunker_version=chunk.chunker_version,
                )
            )
            if status == "inserted":
                report.inserted += 1
            else:
                report.updated += 1

        for chunk in chunks:
            if len(chunk.text) > MAX_EMBED_INPUT_CHARS:
                report.warnings.append(
                    f"chunk {chunk.chunk_id} exceeds the {MAX_EMBED_INPUT_CHARS}-char input window; "
                    "a real provider truncates it silently"
                )

        self.manifests[document.doc_id] = {
            "content_hash": document.content_hash,
            "profile_key": self.profile_key,
            "chunk_hashes": {chunk.chunk_id: chunk.content_hash for chunk in chunks},
            "chunks": len(chunks),
        }
        self.last_ingest[document.doc_id] = report
        return report

    def reindex(self, documents: list[Document]) -> list[IngestReport]:
        """Force a full rebuild (the 'we changed the model' button)."""
        reports = []
        for document in documents:
            self.store.delete_document(document.doc_id)
            self.manifests.pop(document.doc_id, None)
            reports.append(self.ingest(document))
        return reports

    def remove_document(self, doc_id: str) -> int:
        deleted = self.store.delete_document(doc_id)
        self.manifests.pop(doc_id, None)
        self.last_ingest.pop(doc_id, None)
        return deleted

    # -- stage 5 + 6: query and retrieve -----------------------------------

    def retrieve(self, query: str, k: int = 3, where: dict | None = None) -> Retrieval:
        query_vector = self.embedder.embed_one(query)
        zero_query = all(value == 0.0 for value in query_vector)
        hits = self.store.search(query_vector, k=k, where=where)
        return Retrieval(query=query, hits=hits, zero_query=zero_query, k=k)

    # -- stage 7: assemble --------------------------------------------------

    def assemble(
        self,
        retrieval: Retrieval,
        budget_chars: int = 700,
        citation_titles: dict[str, str] | None = None,
    ) -> AssembledContext:
        """Naive context assembly (Topic 27 rebuilds this properly).

        Kept deliberately simple so the failure modes are visible: first-come
        order, whole chunks only, no dedupe, no positioning strategy.
        """
        if budget_chars <= 0:
            raise ValueError("budget_chars must be positive")
        titles = citation_titles or {}
        lines: list[str] = []
        citations: list[Citation] = []
        used = 0
        dropped: list[str] = []
        for row, _score in retrieval.hits:
            number = len(citations) + 1
            title = titles.get(row.doc_id, row.doc_id)
            block = f"[{number}] {title}\n{row.text}"
            cost = len(block) + (1 if lines else 0)
            if used + cost > budget_chars:
                dropped.append(row.chunk_id)
                continue
            lines.append(block)
            citations.append(Citation(number, row.chunk_id, row.doc_id, title))
            used += cost
        return AssembledContext(
            text="\n\n".join(lines),
            citations=citations,
            used_chars=used,
            budget_chars=budget_chars,
            dropped=dropped,
        )

    # -- stage 8: answer ----------------------------------------------------

    def answer(self, query: str, assembled: AssembledContext) -> Answer:
        """Extractive answerer: quote the best sentence, attach a citation.

        This is where a real system calls an LLM. The extractive version is
        deterministic and lets us test the *grounding contract*: every answer
        sentence comes from a cited chunk, or the system abstains.
        """
        if not assembled.citations:
            return Answer(
                text="I don't know based on the available context.",
                citations=[],
                evidence_chunk_ids=[],
                abstained=True,
            )
        query_terms = set(content_terms(query))
        by_number = {citation.number: citation for citation in assembled.citations}
        best: tuple[int, int, str, Citation] | None = None  # (overlap, order, sentence, citation)
        for order, block in enumerate(assembled.text.split("\n\n")):
            header, _, body = block.partition("\n")
            number_text = header.split("]", 1)[0].lstrip("[")
            if not number_text.isdigit():
                continue
            citation = by_number.get(int(number_text))
            if citation is None:
                continue
            for sentence in split_sentences(body):
                overlap = len(query_terms & set(content_terms(sentence)))
                if best is None or (overlap, -order) > (best[0], best[1]):
                    best = (overlap, -order, sentence, citation)
        if best is None or best[0] == 0:
            return Answer(
                text="I don't know based on the available context.",
                citations=[],
                evidence_chunk_ids=[citation.chunk_id for citation in assembled.citations],
                abstained=True,
            )
        overlap, _, sentence, citation = best
        return Answer(
            text=f"{sentence} [{citation.number}]",
            citations=[citation.number],
            evidence_chunk_ids=[citation.chunk_id],
            abstained=False,
        )

    # -- convenience --------------------------------------------------------

    def query(self, question: str, k: int = 3, budget_chars: int = 700) -> tuple[Retrieval, AssembledContext, Answer]:
        retrieval = self.retrieve(question, k=k)
        assembled = self.assemble(retrieval, budget_chars=budget_chars)
        return retrieval, assembled, self.answer(question, assembled)

    # -- the done-when trace ------------------------------------------------

    def trace_document(self, document: Document, question: str, k: int = 3, budget_chars: int = 700) -> DocumentTrace:
        """Walk ONE document through ingest -> answer, recording every stage."""
        report = self.ingest(document)
        chunks = chunk_document(document, self.max_chars, self.chunker_version)
        rows = self.store.rows_for_document(document.doc_id)
        zero_vectors = sum(1 for row in rows if all(v == 0.0 for v in row.vector))
        retrieval = self.retrieve(question, k=k)
        assembled = self.assemble(retrieval, budget_chars=budget_chars, citation_titles={document.doc_id: document.title})
        answer = self.answer(question, assembled)
        query_norm = math.sqrt(sum(v * v for v in self.embedder.embed_one(question)))

        stages = [
            StageTrace(
                "ingest",
                f"{report.reason}: {report.embedded} embedded, {report.unchanged} unchanged, "
                f"{report.deleted} pruned",
                {"warnings": report.warnings or ["none"]},
            ),
            StageTrace(
                "chunk",
                f"{len(chunks)} chunks, max {max((len(c.text) for c in chunks), default=0)} chars",
                {"chunk_ids": [chunk.chunk_id for chunk in chunks]},
            ),
            StageTrace(
                "embed",
                f"{len(rows)} rows x {self.embedder.dimensions} dims, {zero_vectors} zero vectors",
                {"batches": report.embed_batches, "model": self.embedder.model_name},
            ),
            StageTrace(
                "store",
                f"{len(self.store)} rows total; profile {self.profile_key}",
                {"chunks_for_document": len(rows)},
            ),
            StageTrace(
                "query",
                f"query vector norm {query_norm:.3f}",
                {"zero_query": retrieval.zero_query},
            ),
            StageTrace(
                "retrieve",
                f"{len(retrieval.hits)} hits for k={k} (missing {retrieval.missing})",
                {"hits": [(row.chunk_id, round(score, 4)) for row, score in retrieval.hits]},
            ),
            StageTrace(
                "assemble",
                f"{assembled.used_chars}/{assembled.budget_chars} chars, {len(assembled.citations)} citations",
                {"dropped": assembled.dropped or ["none"]},
            ),
            StageTrace(
                "answer",
                "abstained" if answer.abstained else f"quoted {len(answer.citations)} citation(s)",
                {"text": answer.text, "citations": answer.citations},
            ),
        ]
        return DocumentTrace(document=document, question=question, stages=stages, answer=answer)

    # -- diagnosis ----------------------------------------------------------

    def diagnose(self, document: Document | None = None, query: str | None = None, k: int = 3, budget_chars: int = 700) -> list[Issue]:
        """Turn the silent failures into explicit warnings, per stage."""
        issues: list[Issue] = []
        if document is not None:
            chunks = chunk_document(document, self.max_chars, self.chunker_version)
            if not chunks:
                issues.append(Issue("chunk", "no_chunks", "document produced zero chunks and is invisible to retrieval"))
            oversized = [chunk.chunk_id for chunk in chunks if len(chunk.text) > MAX_EMBED_INPUT_CHARS]
            if oversized:
                issues.append(Issue("embed", "oversized_chunks", f"{len(oversized)} chunk(s) exceed the embedding window: {oversized}"))
            report = self.last_ingest.get(document.doc_id)
            if report is None or self.reindex_reason(document) is not None:
                reason = self.reindex_reason(document) or "never_ingested"
                issues.append(Issue("store", "index_stale", f"document is not current in the store ({reason})"))
            elif report.zero_vectors:
                issues.append(Issue("embed", "zero_vectors", f"{report.zero_vectors} stored chunk(s) are zero vectors and can never match"))
            stored_ids = {row.chunk_id for row in self.store.rows_for_document(document.doc_id)}
            current_ids = {chunk.chunk_id for chunk in chunks}
            orphans = stored_ids - current_ids
            if orphans:
                issues.append(Issue("store", "stale_rows", f"{len(orphans)} stale chunk row(s) remain: {sorted(orphans)}"))
        if query is not None:
            retrieval = self.retrieve(query, k=k)
            if retrieval.zero_query:
                issues.append(Issue("query", "zero_query", "query embedded to a zero vector: no result can match"))
            if not retrieval.hits:
                issues.append(Issue("retrieve", "no_hits", "retrieval returned zero rows"))
            elif retrieval.missing:
                issues.append(Issue("retrieve", "short_k", f"retrieved {len(retrieval.hits)} rows for k={k}"))
            assembled = self.assemble(retrieval, budget_chars=budget_chars)
            if assembled.dropped:
                issues.append(Issue("assemble", "budget_drop", f"{len(assembled.dropped)} chunk(s) dropped by the context budget"))
            answer = self.answer(query, assembled)
            if answer.abstained:
                issues.append(Issue("answer", "abstained", "answerer found no supporting sentence (abstained)"))
        return issues


# ---------------------------------------------------------------------------
# Sample corpus (one policy document per topic; reused by the notebook)
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENTS = [
    Document(
        doc_id="returns",
        title="Return Policy",
        text=(
            "We accept returns within 30 days of delivery. Refunds are issued to the "
            "original payment method within 5 business days after inspection."
            "\n\n"
            "Sale items are final sale and cannot be returned. Gift cards are also "
            "excluded from returns."
            "\n\n"
            "To start a return, open the order page and choose Start Return. Print the "
            "prepaid label and drop the parcel at any carrier location."
        ),
    ),
    Document(
        doc_id="shipping",
        title="Shipping Damages",
        text=(
            "If a package arrives damaged, photograph the box and the item before opening "
            "it fully. Claims must be filed within 48 hours of delivery."
            "\n\n"
            "Carriers deny claims that arrive without photos. Attach at least two images "
            "showing the shipping label and the damaged contents."
        ),
    ),
    Document(
        doc_id="warranty",
        title="Warranty",
        text=(
            "Manufacturer warranties cover defects for 12 months from the purchase date. "
            "Normal wear and tear is not covered."
            "\n\n"
            "Warranty claims require the original receipt and the serial number printed "
            "on the device."
        ),
    ),
]


if __name__ == "__main__":
    print("topic 26 - the retrieval pipeline end to end (offline demo)")

    pipeline = Pipeline(max_chars=200, batch_size=4)
    print("\n1. first ingest")
    for document in SAMPLE_DOCUMENTS:
        report = pipeline.ingest(document)
        print(
            f"  {document.doc_id:<9} {report.reason:<13} chunks={report.chunks_total} "
            f"inserted={report.inserted} embedded={report.embedded} batches={report.embed_batches}"
        )

    print("\n2. re-ingest the same document: idempotent")
    calls_before = pipeline.embedder.calls
    report = pipeline.ingest(SAMPLE_DOCUMENTS[0])
    print(
        f"  {report.reason}: embedded={report.embedded} unchanged={report.unchanged} "
        f"new_batch_calls={pipeline.embedder.calls - calls_before}"
    )

    print("\n3. edit one paragraph: only one chunk re-embedded")
    edited = Document(
        "returns",
        "Return Policy",
        SAMPLE_DOCUMENTS[0].text.replace("30 days", "45 days"),
    )
    report = pipeline.ingest(edited)
    print(
        f"  {report.reason}: updated={report.updated} unchanged={report.unchanged} "
        f"embedded={report.embedded}"
    )

    print("\n4. shrink the document: stale chunks pruned")
    shorter = Document("returns", "Return Policy", edited.text.split("\n\n")[0])
    report = pipeline.ingest(shorter)
    print(
        f"  {report.reason}: deleted={report.deleted} "
        f"rows_left={len(pipeline.store.rows_for_document('returns'))}"
    )

    print("\n5. batch embedding: requests, not texts")
    long_document = Document(
        "batch",
        "Batch demo",
        "\n".join(
            f"Paragraph {index} about returns and refunds within 30 days of delivery."
            for index in range(9)
        ),
    )
    batch_pipeline = Pipeline(max_chars=80, batch_size=4)
    report = batch_pipeline.ingest(long_document)
    print(
        f"  {report.chunks_total} chunks -> {report.embed_batches} batch requests "
        f"(batch_size=4), {report.embedded} texts embedded"
    )

    print("\n6. reindex trigger: profile change")
    profile_pipeline = Pipeline(max_chars=200)
    profile_pipeline.ingest(SAMPLE_DOCUMENTS[0])
    profile_pipeline.chunker_version = "paragraph-v2"
    print(f"  chunker change -> {profile_pipeline.reindex_reason(SAMPLE_DOCUMENTS[0])}")
    report = profile_pipeline.ingest(SAMPLE_DOCUMENTS[0])
    print(f"  rebuild: embedded={report.embedded} deleted={report.deleted}")

    print("\n7. trace one document through all eight stages")
    trace_pipeline = Pipeline(max_chars=200, batch_size=4)
    trace = trace_pipeline.trace_document(
        SAMPLE_DOCUMENTS[2], "How long do manufacturer warranties cover defects?"
    )
    print(trace.format())

    print("\n8. a silent failure: morphology")
    morphology_pipeline = Pipeline(max_chars=200, batch_size=4)
    for document in SAMPLE_DOCUMENTS:
        morphology_pipeline.ingest(document)
    retrieval, assembled, answer = morphology_pipeline.query("How long is the warranty?")
    print("  hits:", [(row.chunk_id, round(score, 4)) for row, score in retrieval.hits])
    print("  answer:", answer.text)
    print("  (the chunk with the real answer, warranty#00, was never retrieved)")

    print("\n9. diagnostics")
    issues = morphology_pipeline.diagnose(
        document=SAMPLE_DOCUMENTS[0], query="", k=50, budget_chars=10
    )
    for issue in issues:
        print(f"  {issue.stage:<9} {issue.code:<14} {issue.message}")

"""Tests for the Topic 26 pipeline: contracts, idempotency, silent failures.

Run:  python -m pytest -v
"""

import math

import pytest

from pipeline import (
    MAX_EMBED_INPUT_CHARS,
    SAMPLE_DOCUMENTS,
    SILENT_FAILURES,
    STAGES,
    Document,
    HashingEmbedder,
    Pipeline,
    chunk_document,
    content_hash,
    cosine_similarity,
    silent_failure_notes,
    tokenize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sample(doc_id: str) -> Document:
    return next(doc for doc in SAMPLE_DOCUMENTS if doc.doc_id == doc_id)


def build_pipeline(**kwargs) -> Pipeline:
    kwargs.setdefault("max_chars", 200)
    kwargs.setdefault("batch_size", 2)
    return Pipeline(**kwargs)


def ingest_all(pipeline: Pipeline) -> None:
    for document in SAMPLE_DOCUMENTS:
        pipeline.ingest(document)


class ZeroEmbedder(HashingEmbedder):
    """A broken embedder: every text becomes a zero vector (silent failure)."""

    def embed_one(self, text: str) -> list[float]:
        return [0.0] * self.dimensions


# ---------------------------------------------------------------------------
# Tokenisation, hashing, embeddings
# ---------------------------------------------------------------------------


def test_tokenize_splits_and_lowercases():
    assert tokenize("Return DAYS, 30!") == ["return", "days", "30"]


def test_content_hash_is_stable_and_content_sensitive():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 64


def test_embedding_is_unit_length():
    vector = HashingEmbedder(dimensions=64).embed_one("return policy")
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-12)


def test_empty_text_embeds_to_zero_vector():
    assert HashingEmbedder(dimensions=32).embed_one("   ") == [0.0] * 32


def test_batch_requests_are_ceilings_not_texts():
    embedder = HashingEmbedder(dimensions=32)
    vectors = embedder.embed_batch([f"text {i}" for i in range(5)], batch_size=2)
    assert len(vectors) == 5
    assert embedder.calls == 3  # 2 + 2 + 1
    assert embedder.texts_embedded == 5


def test_batch_rejects_zero_batch_size():
    with pytest.raises(ValueError):
        HashingEmbedder().embed_batch(["x"], batch_size=0)


def test_embedding_dimension_mismatch_cannot_be_silently_compared():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Chunking: stable ids, budgets, hard splits
# ---------------------------------------------------------------------------


def test_chunk_ids_are_stable_across_runs():
    first = chunk_document(sample("returns"), max_chars=200)
    second = chunk_document(sample("returns"), max_chars=200)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert [c.content_hash for c in first] == [c.content_hash for c in second]


def test_chunk_ids_contain_doc_and_ordinal():
    chunks = chunk_document(sample("returns"), max_chars=200)
    assert chunks[0].chunk_id == "returns#00"
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunks_respect_max_chars():
    for document in SAMPLE_DOCUMENTS:
        chunks = chunk_document(document, max_chars=200)
        assert chunks
        assert all(len(chunk.text) <= 200 for chunk in chunks)


def test_chunk_text_is_verbatim_document_text():
    for document in SAMPLE_DOCUMENTS:
        for chunk in chunk_document(document, max_chars=200):
            assert chunk.text in document.text


def test_long_sentence_is_hard_split_and_flagged():
    document = Document("long", "Long", "word " * 120)  # 600 chars, no terminators
    chunks = chunk_document(document, max_chars=100)
    assert len(chunks) >= 6
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.hard_split for chunk in chunks)


def test_chunking_requires_positive_budget():
    with pytest.raises(ValueError):
        chunk_document(sample("returns"), max_chars=0)


# ---------------------------------------------------------------------------
# Ingest: the idempotency contract
# ---------------------------------------------------------------------------


def test_first_ingest_is_new_document():
    pipeline = build_pipeline()
    report = pipeline.ingest(sample("returns"))
    assert report.reason == "new_document"
    assert report.inserted == report.chunks_total
    assert report.embedded == report.chunks_total
    assert report.deleted == 0


def test_second_ingest_is_free_and_identical():
    pipeline = build_pipeline()
    pipeline.ingest(sample("returns"))
    calls = pipeline.embedder.calls
    report = pipeline.ingest(sample("returns"))
    assert report.reason == "unchanged"
    assert report.embedded == 0
    assert report.unchanged == report.chunks_total
    assert pipeline.embedder.calls == calls
    assert len(pipeline.store.rows_for_document("returns")) == report.chunks_total


def test_editing_one_paragraph_reembeds_only_that_chunk():
    pipeline = build_pipeline()
    original = sample("returns")
    pipeline.ingest(original)
    calls_before = pipeline.embedder.calls

    edited = Document(
        "returns",
        original.title,
        original.text.replace("within 30 days", "within 45 days"),
    )
    report = pipeline.ingest(edited)

    assert report.reason == "content_changed"
    assert report.updated == 1
    assert report.inserted == 0
    assert report.embedded == 1
    assert report.unchanged == report.chunks_total - 1
    assert pipeline.embedder.calls == calls_before + 1
    stored = {row.chunk_id: row for row in pipeline.store.rows_for_document("returns")}
    assert "within 45 days" in stored["returns#00"].text


def test_shrinking_a_document_prunes_stale_chunks():
    pipeline = build_pipeline()
    original = sample("returns")
    chunks_before = len(chunk_document(original, max_chars=200))
    pipeline.ingest(original)

    shorter = Document("returns", original.title, original.text.split("\n\n")[0])
    report = pipeline.ingest(shorter)

    assert report.reason == "content_changed"
    assert report.deleted >= 1
    assert len(pipeline.store.rows_for_document("returns")) == 1
    assert len(pipeline.store.rows_for_document("returns")) < chunks_before
    assert "returns#02" not in pipeline.store.rows


def test_profile_change_is_a_reindex_trigger():
    pipeline = build_pipeline()
    pipeline.ingest(sample("returns"))
    pipeline.chunker_version = "paragraph-v2"
    assert pipeline.reindex_reason(sample("returns")) == "profile_changed"


def test_embedding_model_change_is_a_reindex_trigger():
    pipeline = build_pipeline()
    pipeline.ingest(sample("returns"))
    pipeline.embedder = HashingEmbedder(dimensions=128, model_name="other-128")
    assert pipeline.reindex_reason(sample("returns")) == "profile_changed"


def test_profile_change_rebuilds_rows_with_the_new_dimensions():
    pipeline = build_pipeline()
    pipeline.ingest(sample("returns"))
    pipeline.embedder = HashingEmbedder(dimensions=128, model_name="other-128")
    report = pipeline.ingest(sample("returns"))
    assert report.reason == "profile_changed"
    assert report.deleted > 0
    rows = pipeline.store.rows_for_document("returns")
    assert rows and all(row.dimensions == 128 for row in rows)


def test_force_reindex_reembeds_everything():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    calls_before = pipeline.embedder.calls
    reports = pipeline.reindex(SAMPLE_DOCUMENTS)
    assert pipeline.embedder.calls > calls_before
    assert all(report.reason == "new_document" for report in reports)
    assert sum(report.embedded for report in reports) == len(pipeline.store)


def test_remove_document_clears_rows_and_manifest():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    removed = pipeline.remove_document("shipping")
    assert removed > 0
    assert pipeline.store.rows_for_document("shipping") == []
    assert "shipping" not in pipeline.manifests


def test_document_hash_changes_when_text_changes():
    original = sample("returns")
    edited = Document("returns", original.title, original.text + " Extra line.")
    assert original.content_hash != edited.content_hash


# ---------------------------------------------------------------------------
# Search, retrieve, assemble
# ---------------------------------------------------------------------------


def test_search_sorts_best_first():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    hits = pipeline.store.search(pipeline.embedder.embed_one("return refund days"), k=5)
    scores = [score for _, score in hits]
    assert all(not math.isnan(score) for score in scores)
    assert scores == sorted(scores, reverse=True)


def test_search_k_is_a_cap_not_a_promise():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval = pipeline.retrieve("return", k=100)
    assert len(retrieval.hits) == len(pipeline.store)
    assert retrieval.missing == 100 - len(pipeline.store)


@pytest.mark.parametrize(
    "question,expected_doc",
    [
        ("How many days do I have to return an item?", "returns"),
        ("What do I need for a shipping damage claim?", "shipping"),
        ("How long does the warranty cover defects?", "warranty"),
    ],
)
def test_retrieval_finds_the_right_document(question, expected_doc):
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval = pipeline.retrieve(question, k=3)
    assert retrieval.hits
    assert retrieval.hits[0][0].doc_id == expected_doc


def test_zero_query_is_flagged_not_hidden():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval = pipeline.retrieve("", k=3)
    assert retrieval.zero_query is True


def test_assembly_numbers_citations_from_one():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval = pipeline.retrieve("return policy", k=3)
    assembled = pipeline.assemble(retrieval, budget_chars=1_000)
    assert [citation.number for citation in assembled.citations] == list(range(1, len(assembled.citations) + 1))
    assert all(f"[{citation.number}]" in assembled.text for citation in assembled.citations)
    assert assembled.used_chars <= assembled.budget_chars


def test_assembly_drops_chunks_that_do_not_fit():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval = pipeline.retrieve("return policy", k=3)
    assembled = pipeline.assemble(retrieval, budget_chars=120)
    assert assembled.dropped
    assert assembled.used_chars <= 120
    assert len(assembled.citations) < len(retrieval.hits)


def test_assembly_with_empty_retrieval_is_empty():
    pipeline = build_pipeline()
    retrieval = pipeline.retrieve("anything", k=3)
    assembled = pipeline.assemble(retrieval)
    assert assembled.text == ""
    assert assembled.citations == []


# ---------------------------------------------------------------------------
# Answer: grounded or abstain
# ---------------------------------------------------------------------------


def test_answer_quotes_a_sentence_and_cites_it():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval, assembled, answer = pipeline.query("How many days do I have to return an item?")
    assert not answer.abstained
    assert answer.citations
    number = answer.citations[0]
    assert f"[{number}]" in answer.text
    sentence = answer.text.rsplit(" [", 1)[0]
    assert sentence in assembled.text
    assert any(citation.number == number for citation in assembled.citations)


def test_answer_abstains_when_context_is_empty():
    pipeline = build_pipeline()
    retrieval = pipeline.retrieve("return policy", k=3)
    assembled = pipeline.assemble(retrieval)
    answer = pipeline.answer("return policy", assembled)
    assert answer.abstained is True
    assert answer.citations == []


def test_answer_abstains_for_questions_outside_the_corpus():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    retrieval, assembled, answer = pipeline.query("What is the capital of France?")
    assert answer.abstained is True
    assert answer.text.startswith("I don't know")


# ---------------------------------------------------------------------------
# The done-when trace
# ---------------------------------------------------------------------------


def test_trace_document_covers_all_eight_stages_in_order():
    pipeline = build_pipeline()
    trace = pipeline.trace_document(sample("warranty"), "How long is the warranty?")
    assert [stage.stage for stage in trace.stages] == list(STAGES)


def test_trace_document_records_ingest_and_embed_numbers():
    pipeline = build_pipeline()
    trace = pipeline.trace_document(sample("warranty"), "How long is the warranty?")
    by_stage = {stage.stage: stage for stage in trace.stages}
    assert by_stage["ingest"].details["warnings"] == ["none"]
    assert by_stage["embed"].details["batches"] >= 1
    assert by_stage["chunk"].details["chunk_ids"]
    assert "hits" in by_stage["retrieve"].details


def test_trace_answer_is_grounded_or_abstained():
    pipeline = build_pipeline()
    trace = pipeline.trace_document(sample("warranty"), "How long is the warranty?")
    if trace.answer.abstained:
        assert trace.answer.citations == []
    else:
        assert trace.answer.citations
        assert trace.answer.evidence_chunk_ids


def test_trace_format_lists_every_stage():
    pipeline = build_pipeline()
    text = pipeline.trace_document(sample("returns"), "return window").format()
    for stage in STAGES:
        assert f"{stage:<9}" in text


# ---------------------------------------------------------------------------
# Diagnosis: the silent failures made explicit
# ---------------------------------------------------------------------------


def test_diagnose_flags_a_document_that_was_never_ingested():
    pipeline = build_pipeline()
    issues = pipeline.diagnose(document=sample("returns"))
    assert any(issue.code == "index_stale" and issue.stage == "store" for issue in issues)


def test_diagnose_flags_zero_vector_embeddings():
    pipeline = Pipeline(embedder=ZeroEmbedder(dimensions=32), max_chars=200)
    report = pipeline.ingest(sample("returns"))
    assert report.zero_vectors == report.chunks_total
    issues = pipeline.diagnose(document=sample("returns"))
    assert any(issue.code == "zero_vectors" and issue.stage == "embed" for issue in issues)


def test_diagnose_flags_empty_document_as_zero_chunks():
    pipeline = build_pipeline()
    empty = Document("empty", "Empty", "   \n\n  ")
    report = pipeline.ingest(empty)
    assert report.chunks_total == 0
    assert report.warnings
    issues = pipeline.diagnose(document=empty)
    assert any(issue.code == "no_chunks" for issue in issues)


def test_diagnose_flags_oversized_chunks():
    pipeline = Pipeline(max_chars=10_000)
    long_document = Document("long", "Long", "x " * (MAX_EMBED_INPUT_CHARS // 2 + 100))
    report = pipeline.ingest(long_document)
    assert any("input window" in warning for warning in report.warnings)
    issues = pipeline.diagnose(document=long_document)
    assert any(issue.code == "oversized_chunks" for issue in issues)


def test_diagnose_flags_zero_query():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    issues = pipeline.diagnose(document=sample("returns"), query="")
    assert any(issue.code == "zero_query" and issue.stage == "query" for issue in issues)


def test_diagnose_flags_short_k():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    issues = pipeline.diagnose(query="return policy", k=1_000)
    assert any(issue.code == "short_k" and issue.stage == "retrieve" for issue in issues)


def test_diagnose_flags_budget_drops_and_abstention():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    issues = pipeline.diagnose(query="return policy", k=3, budget_chars=10)
    codes = {issue.code for issue in issues}
    assert "budget_drop" in codes
    assert "abstained" in codes


def test_diagnose_flags_stale_rows_left_by_hand():
    pipeline = build_pipeline()
    ingest_all(pipeline)
    row = pipeline.store.rows["returns#00"]
    pipeline.store.rows["returns#99"] = type(row)(
        chunk_id="returns#99",
        doc_id="returns",
        text="orphan",
        vector=row.vector,
        content_hash="deadbeef",
        model_name=row.model_name,
        dimensions=row.dimensions,
        chunker_version=row.chunker_version,
    )
    # The manifest still says the document is current, so only the orphan is flagged.
    issues = pipeline.diagnose(document=sample("returns"))
    assert any(issue.code == "stale_rows" for issue in issues)


def test_silent_failure_catalogue_covers_every_stage():
    assert set(SILENT_FAILURES) == set(STAGES)
    for stage in STAGES:
        assert len(silent_failure_notes(stage)) >= 2


def test_silent_failure_lookup_rejects_unknown_stage():
    with pytest.raises(ValueError):
        silent_failure_notes("deploy")

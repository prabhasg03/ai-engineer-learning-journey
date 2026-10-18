"""Tests for Topic 24 - chunking strategies and their failures.

The syllabus done-when: "chunk a sample document three different ways and
articulate the granularity trade-off of each." These tests chunk
SAMPLE_DOCUMENT with every strategy and assert the quality differences:
lossless coverage, boundary guarantees, table/code integrity, and the
precision-vs-completeness trade.
"""
from __future__ import annotations

from chunking import (
    SAMPLE_DOCUMENT,
    Chunk,
    ChunkReport,
    balanced_fences,
    estimate_token_count,
    fixed_size_chunks,
    is_sentence_end,
    markdown_chunks,
    mid_sentence_cut_count,
    mid_table_cut_count,
    overlap_text,
    paragraph_chunks,
    report,
    sentence_chunks,
    split_sentences,
    token_budget_chunks,
)

# -- split_sentences ---------------------------------------------------------


def test_split_sentences_cover_every_character_exactly_once():
    pieces = split_sentences(SAMPLE_DOCUMENT)
    assert "".join(p[2] for p in pieces) == SAMPLE_DOCUMENT


def test_split_sentences_respects_abbreviations():
    doc = "Dr. Smith arrived early. He spoke for an hour."
    sentences = [s[2] for s in split_sentences(doc)]
    assert len(sentences) == 2  # NOT split after "Dr."
    assert "Dr. Smith arrived early." in sentences[0]


def test_split_sentences_treats_exclamation_runs_as_one_boundary():
    doc = "Wow!!! Really? Yes."
    assert len(split_sentences(doc)) == 3


def test_is_sentence_end_contract():
    text = "First. Second"
    assert is_sentence_end(text, 6)  # after "First."
    assert not is_sentence_end(text, 4)  # mid word
    assert is_sentence_end(text, len(text))  # document end


# -- fixed size chunks -------------------------------------------------------


def test_fixed_size_sizes_and_count():
    chunks = fixed_size_chunks("a" * 525, size=100)
    sizes = [len(c.text) for c in chunks]
    assert all(s == 100 for s in sizes[:-1])
    assert sizes[-1] == 25
    assert all(s <= 100 for s in sizes)


def test_fixed_no_overlap_tiles_exactly():
    text = "x" * 450
    chunks = fixed_size_chunks(text, size=200, overlap=0)
    assert "".join(c.text for c in chunks) == text


def test_fixed_overlap_shares_the_tail():
    text = SAMPLE_DOCUMENT
    chunks = fixed_size_chunks(text, size=180, overlap=40)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt.start == prev.start + 140  # step = size - overlap
        assert overlap_text(prev, nxt) == prev.text[-40:]


def test_fixed_rejects_bad_overlap():
    try:
        fixed_size_chunks("abc", size=10, overlap=10)
        raise AssertionError("must reject overlap == size")
    except ValueError as exc:
        assert "overlap" in str(exc)
    try:
        fixed_size_chunks("abc", size=0)
        raise AssertionError("must reject zero size")
    except ValueError:
        pass


def test_fixed_size_mid_sentence_cuts_versus_sentence_strategy():
    fixed = fixed_size_chunks(SAMPLE_DOCUMENT, size=200)
    packed = sentence_chunks(SAMPLE_DOCUMENT, max_chars=400)
    fixed_cuts = mid_sentence_cut_count(fixed, SAMPLE_DOCUMENT)
    packed_cuts = mid_sentence_cut_count(packed, SAMPLE_DOCUMENT)
    assert fixed_cuts >= 5  # windowing a real doc makes multiple bad cuts
    assert packed_cuts == 0  # sentence chunks never cut inside a sentence


def test_fixed_size_cuts_the_markdown_table():
    fixed = fixed_size_chunks(SAMPLE_DOCUMENT, size=200)
    assert mid_table_cut_count(fixed) > 0  # window slices straight through
    tactic = markdown_chunks(SAMPLE_DOCUMENT)
    structured = [c for c in tactic if "Hygiene seal intact" in c.text]
    assert structured, "the table should live whole inside one chunk"
    assert all("|" in c.text for c in structured)


# -- sentence chunks ---------------------------------------------------------


def test_sentence_chunk_boundaries_are_sentence_ends():
    doc = SAMPLE_DOCUMENT
    chunks = sentence_chunks(doc, max_chars=300)
    for c in chunks:
        assert c.end == len(doc) or is_sentence_end(doc, c.end) or c.metadata.get("hard_split")


def test_sentence_chunks_zero_mid_sentence_cuts():
    chunks = sentence_chunks(SAMPLE_DOCUMENT, max_chars=400)
    hard_splits = sum(1 for c in chunks if c.metadata.get("hard_split"))
    assert hard_splits == 0  # longest sentence is under 400 chars
    assert mid_sentence_cut_count(chunks, SAMPLE_DOCUMENT) == 0


def test_sentence_chunks_shorter_chunks_when_budget_shrinks():
    big = sentence_chunks(SAMPLE_DOCUMENT, max_chars=2000)
    small = sentence_chunks(SAMPLE_DOCUMENT, max_chars=250)
    assert len(small) >= len(big)


def test_sentence_chunks_partition_text():
    chunks = sentence_chunks(SAMPLE_DOCUMENT, max_chars=300)
    for c in chunks:
        assert c.start < c.end
    # consecutive chunk starts increase monotonically (no overlaps)
    starts = [c.start for c in chunks]
    assert starts == sorted(starts)


# -- paragraph chunks --------------------------------------------------------


def test_paragraph_chunks_match_blank_line_structure():
    chunks = paragraph_chunks(SAMPLE_DOCUMENT)
    assert len(chunks) >= 10
    for c in chunks:
        assert c.text and c.text.strip()[0] != "# paragraph-marker"


def test_paragraph_chunks_map_one_to_one_when_small():
    text = "One short paragraph.\n\nAnother short paragraph.\n"
    chunks = paragraph_chunks(text)
    assert [c.text.strip() for c in chunks] == [
        "One short paragraph.",
        "Another short paragraph.",
    ]


def test_paragraph_chunks_hard_split_huge_paragraph():
    text = ("word " * 400).strip() + "\n"  # ~1996 chars
    chunks = paragraph_chunks(text, max_chars=600)
    assert all(c.metadata.get("hard_split") for c in chunks)
    assert all(len(c.text) <= 600 for c in chunks)


# -- markdown chunks ---------------------------------------------------------


def test_markdown_chunks_carry_header_path():
    chunks = markdown_chunks(SAMPLE_DOCUMENT)
    by_header = {}
    for c in chunks:
        by_header.setdefault(c.metadata["header_path"], []).append(c)
    assert "Return Policy > Exclusions" in by_header
    assert "Return Policy > Shipping Damages" in by_header
    assert any(
        "Hygiene seal intact" in c.text for c in by_header["Return Policy > Exclusions"]
    )


def test_markdown_keeps_the_table_whole():
    chunks = markdown_chunks(SAMPLE_DOCUMENT)
    table_chunks = [c for c in chunks if "| Headphones |" in c.text]
    assert table_chunks, "table rows must survive inside one chunk"
    for c in table_chunks:
        assert "| Product |" in c.text  # the header row is neighbours, not severed
        assert c.metadata["header_path"] == "Return Policy > Exclusions"


def test_markdown_never_cuts_a_code_fence():
    chunks = markdown_chunks(SAMPLE_DOCUMENT, max_chars=50)  # tiny, to force pressure
    assert any("```" in c.text for c in chunks)
    for c in chunks:
        assert balanced_fences(c.text), f"unbalanced fence in {c.id}"


def test_markdown_chunks_ids_and_offset_valid():
    chunks = markdown_chunks(SAMPLE_DOCUMENT)
    assert [c.id for c in chunks] == [f"md-{i}" for i in range(1, len(chunks) + 1)]
    for c in chunks:
        assert SAMPLE_DOCUMENT[c.start : c.start + 1] == c.text[:1]


def test_markdown_inside_fence_hashes_are_not_headings():
    doc = "# Real Heading\n\n```python\n# not a heading\nx = 1\n```\n\nTail text here.\n"
    chunks = markdown_chunks(doc)
    paths = {c.metadata["header_path"] for c in chunks}
    assert all("not a heading" not in p for p in paths)
    assert "Real Heading" in paths


# -- token budget chunks -----------------------------------------------------


def test_token_budget_respected():
    chunks = token_budget_chunks(SAMPLE_DOCUMENT, budget_tokens=100)
    assert all(c.metadata["tokens"] <= 100 for c in chunks if not c.metadata.get("hard_split"))


def test_token_budget_hard_splits_huge_sentences():
    sentence = "verylongword " * 100  # ~1300 chars -> ~325 tokens
    doc = f"Intro sentence here. {sentence} Tail sentence.\n"
    chunks = token_budget_chunks(doc, budget_tokens=80)
    hard = [c for c in chunks if c.metadata.get("hard_split")]
    assert hard, "the oversize sentence must be hard-split"
    assert estimate_token_count(sentence) > 80


def test_token_budget_chunk_count_grows_as_budget_shrinks():
    counts = [
        len(token_budget_chunks(SAMPLE_DOCUMENT, budget_tokens=b))
        for b in (400, 200, 100, 50)
    ]
    assert counts == sorted(counts)  # fewer tokens per chunk -> more chunks


def test_token_budget_custom_estimator_is_used():
    def word_counter(text: str) -> int:
        return len(text.split())

    chunks = token_budget_chunks(
        SAMPLE_DOCUMENT, budget_tokens=5, tokenizer_estimate=word_counter
    )
    assert all(c.metadata["tokens"] <= 5 for c in chunks if not c.metadata.get("hard_split"))
    assert len(chunks) > 10  # 5 words per chunk is very fine-grained


def test_estimate_token_count_chars_per_four():
    assert estimate_token_count("") == 0
    assert estimate_token_count("abcd") == 1
    assert estimate_token_count("abcde") == 2  # ceil


# -- reports -----------------------------------------------------------------


def test_report_shape():
    chunks = fixed_size_chunks(SAMPLE_DOCUMENT, size=200)
    rep = report(chunks, SAMPLE_DOCUMENT)
    assert isinstance(rep, ChunkReport)
    assert rep.strategy == "fixed"
    assert rep.chunk_count == len(chunks)
    assert rep.max_chars <= 200
    assert rep.avg_chars > 0
    assert rep.mid_sentence_cuts == mid_sentence_cut_count(chunks, SAMPLE_DOCUMENT)


def test_granularity_tradeoff_table():
    # The articulation the done-when asks for, encoded:
    strategies = [
        (
            "fixed",
            fixed_size_chunks(SAMPLE_DOCUMENT, size=200),
        ),
        (
            "sentence",
            sentence_chunks(SAMPLE_DOCUMENT, max_chars=300),
        ),
        (
            "markdown",
            markdown_chunks(SAMPLE_DOCUMENT),
        ),
    ]
    reports = {name: report(chunks, SAMPLE_DOCUMENT) for name, chunks in strategies}
    # Fine granularity: fixed has the most chunks...
    assert reports["fixed"].chunk_count >= reports["sentence"].chunk_count
    # ...but pays for it with broken sentences and broken tables:
    assert reports["fixed"].mid_sentence_cuts > reports["sentence"].mid_sentence_cuts
    # Structure-aware has the small count and the clean cuts:
    assert reports["markdown"].mid_sentence_cuts == reports["sentence"].mid_sentence_cuts == 0
    # And completeness table:
    assert reports["markdown"].chunk_count < reports["fixed"].chunk_count


def test_overlap_is_the_completeness_band_aid():
    with_overlap = fixed_size_chunks(SAMPLE_DOCUMENT, size=200, overlap=50)
    without = fixed_size_chunks(SAMPLE_DOCUMENT, size=200, overlap=0)
    assert len(with_overlap) > len(without)  # overlap costs more chunks
    # ...and the repeated 50 chars per boundary are the "deduplication tax":
    shared_chars = sum(len(overlap_text(p, n)) for p, n in zip(with_overlap, with_overlap[1:]))
    assert shared_chars == 50 * (len(with_overlap) - 1)

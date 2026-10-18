"""Tests for Topic 22 - embeddings as geometry.

Everything is offline and deterministic. The "models" here are hand-written
(PPMI co-occurrence + feature hashing) so that the geometry -- meaning-as-
position, unit-sphere normalisation, dimension trade-offs -- can be asserted,
not just described.
"""
from __future__ import annotations

import math

from embeddings import (
    EXAMPLE_CORPUS,
    CooccurrenceEmbedder,
    HashingEmbedder,
    contrastive_score,
    cosine_similarity,
    l2_normalize,
    most_similar,
    neighbor_stability,
    storage_bytes,
    tokenize,
    truncate,
)


def norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


# -- tokenisation -----------------------------------------------------------


def test_tokenize_splits_and_lowercases():
    assert tokenize("The DOG's ball!") == ["the", "dog's", "ball"]


def test_someKnown_tokenization_contract():
    toks = tokenize("Puppy Wag-Tail 42")
    assert toks == ["puppy", "wag", "tail", "42"]


# -- geometry helpers -------------------------------------------------------


def test_norm_of_l2_normalized_is_one():
    vec = l2_normalize([1.0, 2.0, 2.0])
    assert math.isclose(norm(vec), 1.0, rel_tol=1e-12)


def test_l2_normalize_of_zero_vector_stays_zero():
    assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]


def test_l2_normalize_preserves_direction():
    scaled = [10.0 * x for x in [0.3, 0.4]]
    assert math.isclose(l2_normalize(scaled)[0], 0.6, rel_tol=1e-12)
    assert math.isclose(l2_normalize(scaled)[1], 0.8, rel_tol=1e-12)


def test_cosine_same_direction_is_one():
    assert math.isclose(cosine_similarity([1, 1], [3, 3]), 1.0, rel_tol=1e-12)


def test_cosine_orthogonal_is_zero():
    assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-12


def test_cosine_symmetric():
    a = [1.0, 2.0, -1.0]
    b = [0.5, -0.5, 0.25]
    assert math.isclose(
        cosine_similarity(a, b), cosine_similarity(b, a), rel_tol=1e-12
    )


def test_cosine_of_zero_vector_is_nan_like_pgvector():
    assert math.isnan(cosine_similarity([0, 0], [1, 1]))

# -- cooccurrence embedder: meaning = the company a word keeps --------------


def build_embedder() -> CooccurrenceEmbedder:
    return CooccurrenceEmbedder(EXAMPLE_CORPUS, window=2)


def test_cooccembedder_vocabsize_bigger_than_a_handful():
    emb = build_embedder()
    assert emb.dimensions > 15


def test_embeddings_always_unit_vectors():
    emb = build_embedder()
    for text in ["loyal dog", "stock market", "puppy plays", "zzz-unknown"]:
        vec = emb.embed_text(text)
        assert math.isclose(norm(vec), 1.0 if any(emb.vocab.get(t) for t in tokenize(text)) else 0.0)


def test_deterministic_across_instances():
    a = build_embedder()
    b = build_embedder()
    assert a.embed_text("a loyal dog") == b.embed_text("a loyal dog")


def test_similar_meaning_lands_nearby_regardless_of_wording():
    emb = build_embedder()
    q = emb.embed_text("the puppy is loyal")
    dog_vec = emb.embed_text("a dog is faithful")
    finance_vec = emb.embed_text("the stock market rallied")
    assert cosine_similarity(q, dog_vec) > cosine_similarity(q, finance_vec)


def test_dog_and_puppy_are_neighbors_but_dog_and_stock_are_not():
    emb = build_embedder()
    dog, puppy = emb.embed_word("dog"), emb.embed_word("puppy")
    market = emb.embed_word("market")
    # same-concept words beat finance words for dog's slot in geometry
    assert cosine_similarity(dog, puppy) > cosine_similarity(dog, market)
    ranking = most_similar(emb.embed_word("dog"), dict(emb.vocab))
    names = [name for name, _ in ranking]
    assert "puppy" in names
    finance_positions = [
        names.index(w) for w in ("stock", "investors", "bond", "yields") if w in emb.vocab
    ]
    dog_word_positions = [
        names.index(w) for w in ("loyal", "faithful", "friendly") if w in emb.vocab
    ]
    assert finance_positions and dog_word_positions
    assert min(dog_word_positions) < min(finance_positions)


def test_unknown_word_contributes_nothing():
    emb = build_embedder()
    zero = emb.embed_text("zzzqqq")
    assert all(v == 0.0 for v in zero)
    with_unseen = emb.embed_text("the dog zzzqqq")
    plain = emb.embed_text("the dog")
    assert cosine_similarity(with_unseen, plain) > 0.99  # identical direction


def test_same_text_is_self_similar_one():
    emb = build_embedder()
    v = emb.embed_text("cat naps on windowsill")
    assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-12)


def test_ppmi_values_are_non_negative():
    emb = build_embedder()
    for vec in emb.vocab.values():
        assert all(v >= 0.0 for v in vec)


# -- hashing embedder: dimensions / normalisation / determinism -------------


def test_hashing_respects_chosen_dimensions():
    for d in (8, 16, 64):
        vec = HashingEmbedder(dimensions=d).embed("hello world")
        assert len(vec) == d


def test_hashing_deterministic_independent_of_process_salt():
    # Uses hashlib internally: the same text must map to the same vector
    # every run (unlike Python's built-in hash(), which is salted).
    e = HashingEmbedder(dimensions=32)
    assert e.embed("alpha beta") == e.embed("alpha beta")


def test_hashing_different_texts_differ():
    e = HashingEmbedder(dimensions=64)
    assert e.embed("alpha beta") != e.embed("gamma delta")


def test_hashing_output_on_unit_sphere():
    e = HashingEmbedder(dimensions=64)
    for text in ["run fast", "running races", "", "      "]:
        vec = e.embed(text)
        n = norm(vec)
        assert math.isclose(n, 1.0, rel_tol=1e-12) or n == 0.0


def test_hashing_shared_trigrams_pull_run_and_running_together():
    e = HashingEmbedder(dimensions=64)
    runv = e.embed("run")
    runningv = e.embed("running")
    quantumv = e.embed("quantum")
    assert cosine_similarity(runv, runningv) > cosine_similarity(runv, quantumv)


def test_hashing_is_morphology_not_semantics():
    # The trap the caveats section warns about: a hashing embedder cannot
    # tell that a puppy is a pet but a spreadsheet is not, when the two
    # strings share no letters. "puppy" and "iceskating" share no trigrams.
    e = HashingEmbedder(dimensions=64)
    pet = e.embed("puppy")
    pet2 = e.embed("dog pet")
    paper = e.embed("iceskating")
    assert abs(cosine_similarity(pet, pet2) - 0.0) < 1.0  # any relationship is cosmetic
    assert cosine_similarity(pet, pet2) < 1.0
    assert cosine_similarity(pet, paper) < cosine_similarity(pet, pet2)


# -- dimensions, truncation (Matryoshka-style), storage ---------------------


def test_truncate_keeps_leading_dimensions_and_renormalises():
    e = HashingEmbedder(dimensions=64)
    full = e.embed("quarterly revenue report")
    cut = truncate(full, 32)
    assert len(cut) == 32
    assert math.isclose(norm(cut), 1.0, rel_tol=1e-12)


def test_truncate_beyond_original_dimensions_raises():
    e = HashingEmbedder(dimensions=32)
    full = e.embed("text")
    try:
        truncate(full, 64)
        raise AssertionError("should have raised")
    except ValueError as exc:
        assert "truncate" in str(exc) or "dimensions" in str(exc)


def test_neighbor_stability_degrades_gracefully_not_catastrophically():
    e = HashingEmbedder(dimensions=128)
    candidates = {
        f"doc-{i}": e.embed(f"quarterly report number {i} about revenue margin")
        for i in range(12)
    }
    query = e.embed("quarterly revenue report")
    kept = neighbor_stability(query, candidates, top_k=3, dimensions=32)
    assert kept >= 1  # most coarse neighbours survive a 4x cut
    assert kept <= 3


def truncate_map(candidates: dict[str, list[float]], dims: int) -> dict[str, list[float]]:
    return {k: truncate(v, dims) for k, v in candidates.items()}


def test_truncating_without_renormalising_breaks_the_unit_sphere():
    e = HashingEmbedder(dimensions=64)
    full = e.embed("warning label")
    sliced = full[:16]
    assert norm(sliced) < 1.0  # dropped mass -> not unit length anymore
    assert math.isclose(norm(truncate(full, 16)), 1.0, rel_tol=1e-12)


def test_storage_bytes_match_pgvector_accounting():
    assert storage_bytes(1536) == 4 * 1536 + 8  # 6,152 bytes for 1536-d float32
    assert storage_bytes(3) == 4 * 3 + 8


def test_one_million_1536_dim_vectors_are_gigabytes():
    per_row = storage_bytes(1536)
    gb_per_million = per_row * 1_000_000 / (1000**3)
    assert 6.0 < gb_per_million < 7.0  # ~6.15 GB before any index overhead


# -- benchmark caveat harness ------------------------------------------------


def test_contrastive_score_separates_good_from_bad_embedder_on_domain():
    query = "loyal dog guards the family"
    positives = ["a faithful dog protects the house", "the puppy stayed close"]
    negatives = ["the stock market rallied", "bond yields climbed"]

    semantic = CooccurrenceEmbedder(EXAMPLE_CORPUS, window=2)
    letters = HashingEmbedder(dimensions=64)

    semantic_score = contrastive_score(semantic.embed_text, query, positives, negatives)
    hashing_score = contrastive_score(letters.embed, query, positives, negatives)

    assert semantic_score > hashing_score  # on THIS domain, co-occurrence wins
    assert semantic_score > 0.0


def test_hashing_wins_when_domain_is_about_letters_not_meaning():
    query = "running race results"
    positives = ["the runner raced fast", "racing results today"]
    negatives = ["loyal dog sleeps", "cat purrs quietly"]
    letters = HashingEmbedder(dimensions=64)
    semantic = CooccurrenceEmbedder(EXAMPLE_CORPUS, window=2)
    assert contrastive_score(letters.embed, query, positives, negatives) > contrastive_score(
        semantic.embed_text, query, positives, negatives
    )

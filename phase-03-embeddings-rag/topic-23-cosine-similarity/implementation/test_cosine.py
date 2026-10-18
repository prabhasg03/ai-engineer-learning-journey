"""Tests for Topic 23 - cosine similarity, magnitude invariance, thresholds.

Hand-computed numbers come first (the syllabus done-when: "compute cosine
similarity by hand on two tiny vectors"), then the invariances, then the
numpy + pgvector-operator layers, then threshold calibration.
"""
from __future__ import annotations

import math

from cosine import (
    HAND_COMPUTATION,
    ThresholdRow,
    angle_degrees,
    best_f1_threshold,
    calibration_report,
    cosine_distance,
    cosine_similarity,
    dot_product,
    euclidean_distance,
    l2_distance,
    magnitude,
    negative_inner_product,
    np_cosine_similarity_matrix,
    np_rank_by_similarity,
    sweep_thresholds,
)

# -- the hand computation ---------------------------------------------------


def test_hand_computation_dot_product():
    assert dot_product((1, 2), (2, 1)) == 4


def test_hand_computation_magnitudes():
    assert math.isclose(magnitude((1, 2)), math.sqrt(5), rel_tol=1e-12)
    assert math.isclose(magnitude((2, 1)), math.sqrt(5), rel_tol=1e-12)


def test_hand_computation_cosine_is_four_fifths():
    assert math.isclose(cosine_similarity((1, 2), (2, 1)), 0.8, rel_tol=1e-12)


def test_hand_computation_angle_matches_arccos():
    assert math.isclose(angle_degrees((1, 2), (2, 1)), 36.86989764584402, rel_tol=1e-9)


def test_hand_computation_cosine_distance_is_point_two():
    assert math.isclose(cosine_distance((1, 2), (2, 1)), 0.2, rel_tol=1e-12)


def test_hand_computation_record_matches_lived_computations():
    # The reference table and the functions agree: notes and code stay in sync.
    assert HAND_COMPUTATION["dot"] == dot_product(HAND_COMPUTATION["a"], HAND_COMPUTATION["b"])
    assert math.isclose(
        HAND_COMPUTATION["cosine"],
        cosine_similarity(HAND_COMPUTATION["a"], HAND_COMPUTATION["b"]),
        rel_tol=1e-12,
    )
    assert math.isclose(
        HAND_COMPUTATION["angle_degrees"],
        angle_degrees(HAND_COMPUTATION["a"], HAND_COMPUTATION["b"]),
        rel_tol=1e-9,
    )


# -- boundary angles --------------------------------------------------------


def test_same_vector_similarity_is_one():
    assert math.isclose(cosine_similarity([3, 4], [3, 4]), 1.0, rel_tol=1e-12)


def test_opposite_vector_similarity_is_minus_one():
    assert math.isclose(cosine_similarity([1, 0], [-1, 0]), -1.0, rel_tol=1e-12)


def test_orthogonal_similarity_is_zero():
    assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-12


def test_45_and_90_and_180_degree_angles():
    a = [1, 0]
    assert math.isclose(angle_degrees(a, [1, 1]), 45.0, rel_tol=1e-9)
    assert math.isclose(angle_degrees(a, [0, 1]), 90.0, rel_tol=1e-9)
    assert math.isclose(angle_degrees(a, [-2, 0]), 180.0, rel_tol=1e-9)


def test_higher_dimensions_hand_example():
    # (1,2,2) vs (2,4,1): dot=2+8+2=12, mag_a=sqrt(9)=3, mag_b=sqrt(21)
    assert math.isclose(
        cosine_similarity((1, 2, 2), (2, 4, 1)), 12 / (3 * math.sqrt(21)), rel_tol=1e-12
    )


# -- invariances ------------------------------------------------------------


def test_magnitude_invariance_scaling_one_side():
    a = [1.0, 2.0]
    b = [3.0, -1.0]
    base = cosine_similarity(a, b)
    for k in (0.1, 2.0, 1_000.0):
        assert math.isclose(cosine_similarity([k * x for x in a], b), base, rel_tol=1e-12)
        assert math.isclose(cosine_similarity(a, [k * y for y in b]), base, rel_tol=1e-12)


def test_magnitude_invariance_scaling_both_sides():
    a = [2.0, -1.0, 0.5]
    b = [-0.5, 0.25, 1.0]
    assert math.isclose(
        cosine_similarity([100 * x for x in a], [0.01 * y for y in b]),
        cosine_similarity(a, b),
        rel_tol=1e-12,
    )


def test_euclidean_distance_is_NOT_magnitude_invariant():
    # The contrast the done-when asks you to justify.
    a = [1.0, 2.0]
    b = [2.0, 1.0]
    assert math.isclose(euclidean_distance(a, b), 2**0.5, rel_tol=1e-12)  # sqrt( (1-2)^2 + (2-1)^2 )
    assert euclidean_distance([10 * x for x in a], [10 * y for y in b]) > 10.0
    # ...while cosine did not move at all:
    assert abs(cosine_similarity(a, b) - 0.8) < 1e-12


def test_cosine_bounded_between_minus_one_and_one():
    samples = [
        ((1, 5, -3), (7, -2, 4)),
        ((0.3, -0.9), (-4, 1)),
        ((-5, 5), (5, -5)),
    ]
    for a, b in samples:
        sim = cosine_similarity(a, b)
        assert -1.0 <= sim <= 1.0


def test_symmetry():
    pairs = [((1, 2), (2, 1)), ((0.5, -1, 3), (4, 2, -0.25))]
    for a, b in pairs:
        assert math.isclose(cosine_similarity(a, b), cosine_similarity(b, a), rel_tol=1e-12)


def test_bad_lengths_raise():
    for fn in (
        cosine_similarity,
        cosine_distance,
        dot_product,
        euclidean_distance,
        negative_inner_product,
    ):
        try:
            fn([1, 2], [1, 2, 3])
        except ValueError as exc:
            assert "length" in str(exc) or "dimensions" in str(exc)
        else:
            raise AssertionError(f"{fn.__name__} should raise on length mismatch")


def test_zero_vector_is_nan_like_pgvector():
    # pgvector: zero vectors get NaN cosine distance (and are skipped by
    # cosine indexes entirely).
    assert math.isnan(cosine_similarity([0, 0], [1, 1]))
    assert math.isnan(cosine_distance([0, 0], [1, 1]))
    assert math.isnan(angle_degrees([0, 0], [1, 1]))


# -- the pgvector operator triple --------------------------------------------


def test_l2_distance_matches_pythagoras():
    assert math.isclose(euclidean_distance((0, 0), (3, 4)), 5.0, rel_tol=1e-12)
    assert l2_distance((0, 0), (3, 4)) == euclidean_distance((0, 0), (3, 4))


def test_cosine_distance_identity_one_minus_similarity():
    a, b = (0.5, -1.0, 2.0), (1.5, 0.25, -0.75)
    assert math.isclose(
        cosine_distance(a, b), 1.0 - cosine_similarity(a, b), rel_tol=1e-12
    )


def test_negative_inner_product_equals_minus_dot():
    a, b = (1, 2, 3), (4, -5, 6)
    assert negative_inner_product(a, b) == -dot_product(a, b)
    # ...which is why it orders ascending like a distance in Postgres:
    # bigger inner product (more similar) -> more negative -> earlier in ASC.


def test_negative_inner_product_extremes():
    unit = [0.6, 0.8]
    assert math.isclose(negative_inner_product(unit, unit), -1.0, rel_tol=1e-12)
    assert math.isclose(negative_inner_product(unit, [-x for x in unit]), 1.0, rel_tol=1e-12)


def test_unit_vectors_euclidean_vs_chord_identity():
    # For unit vectors: ||a-b||^2 = 2 - 2*cos(a,b)  (chord length on sphere).
    # Handy interview fact: cosine and euclidean give the SAME RANKING.
    examples = [((1, 0), (0, 1)), ((0.6, 0.8), (-0.8, 0.6)), ((1, 1) and [1 / 2**0.5, 1 / 2**0.5], (-1 / 2**0.5, -1 / 2**0.5))]
    for a, b in examples:
        assert math.isclose(
            euclidean_distance(a, b) ** 2, 2 - 2 * cosine_similarity(a, b), rel_tol=1e-12
        )


def test_ranking_by_euclidean_matches_cosine_on_unit_vectors():
    vectors = [
        (1.0, 0.0),
        (math.sqrt(0.5), math.sqrt(0.5)),
        (0.0, 1.0),
        (-math.sqrt(0.5), math.sqrt(0.5)),
    ]
    query = (1.0, 0.0)
    by_cos = sorted(range(4), key=lambda i: cosine_distance(query, vectors[i]))
    by_l2 = sorted(range(4), key=lambda i: euclidean_distance(query, vectors[i]))
    assert by_cos == by_l2


# -- numpy layer -------------------------------------------------------------


def test_numpy_matches_pure_python():
    import numpy as np

    rng = np.random.default_rng(7)  # deterministic
    matrix = np.round(rng.normal(size=(6, 4)), 3)
    query = np.round(rng.normal(size=4), 3)
    pure = cosine_similarity(list(query), list(matrix[3]))
    got = float(np_cosine_similarity_matrix(matrix, query)[3])
    assert math.isclose(got, pure, rel_tol=1e-12)


def test_numpy_query_length_mismatch_raises():
    import numpy as np

    matrix = np.ones((2, 3))
    try:
        np_cosine_similarity_matrix(matrix, np.ones(4))
        raise AssertionError("should raise")
    except ValueError as exc:
        assert "dimensions" in str(exc)


def test_numpy_rank_by_similarity_best_first_and_skips_nan():
    matrix = [[1, 0], [0, 1], [0.9, 0.1], [0, 0]]  # last row is zero -> NaN
    order = np_rank_by_similarity(matrix, [0.95, 0.05], k=2)
    assert order == [0, 2]  # [1,0] scores 0.95; [0.9,0.1] scores ~0.87; NaN row excluded


def test_numpy_ranking_matches_a_normalized_pure_python_ranking():
    import numpy as np

    rng = np.random.default_rng(11)
    matrix = np.round(rng.normal(size=(8, 3)), 3)
    query = np.round(rng.normal(size=3), 3)
    units = [list(map(float, np.asarray(row) / np.linalg.norm(row))) for row in matrix]
    by_cos = sorted(range(8), key=lambda i: cosine_distance(query, units[i]))
    assert np_rank_by_similarity(matrix, list(query), k=8) == by_cos


# -- threshold calibration ---------------------------------------------------

PAIRS = [
    (0.91, True),
    (0.87, True),
    (0.84, True),
    (0.62, False),
    (0.55, False),
    (0.71, False),
    (0.66, False),
]


def test_sweep_extremes():
    rows = {r.threshold: r for r in sweep_thresholds(PAIRS, [0.0, 1.0])}
    # threshold 0 takes everything: perfect recall, diluted precision
    assert rows[0.0].recall == 1.0
    assert rows[0.0].precision == 3 / 7
    # threshold 1 takes nothing: recall 0, precision 0 (no retrieved pairs)
    assert rows[1.0].recall == 0.0
    assert rows[1.0].precision == 0.0


def test_precision_recall_in_bounds_and_f1_is_harmonic_mean():
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    for row in sweep_thresholds(PAIRS, thresholds):
        assert 0.0 <= row.precision <= 1.0
        assert 0.0 <= row.recall <= 1.0
        if row.precision + row.recall > 0:
            expected = 2 * row.precision * row.recall / (row.precision + row.recall)
            assert math.isclose(row.f1, expected, rel_tol=1e-12)
        assert isinstance(row, ThresholdRow)


def test_higher_threshold_raises_precision_lowers_recall():
    rows = {r.threshold: r for r in sweep_thresholds(PAIRS, [0.5, 0.9])}
    assert rows[0.9].precision > rows[0.5].precision
    assert rows[0.9].recall < rows[0.5].recall


def test_best_f1_threshold_lands_in_the_gap():
    best = best_f1_threshold(PAIRS, [0.0, 0.1, 0.3, 0.5, 0.62, 0.63, 0.68, 0.75, 0.8, 0.86, 0.9])
    assert 0.6 <= best.threshold <= 0.9  # it cuts between the two clusters
    assert best.f1 == max(r.f1 for r in sweep_thresholds(PAIRS, [0.0, 0.1, 0.3, 0.5, 0.62, 0.63, 0.68, 0.75, 0.8, 0.86, 0.9]))


def test_calibration_report_is_printable_and_sorted():
    report = calibration_report(PAIRS, [0.9, 0.5, 0.7])
    lines = report.splitlines()
    assert lines[0].startswith("threshold")
    values = [float(line.split()[0]) for line in lines[2:]]
    assert values == sorted(values)  # sweep sorts thresholds despite input order


def test_thresholds_are_per_corpus_not_universal():
    # Two corpora, one threshold. The signals in each corpus live on
    # different similarity ranges, so the "perfect" threshold in one is
    # dead weight in the other - exactly why thresholds get tuned per corpus.
    noisy_corpus = [(0.93, True), (0.92, True), (0.89, False), (0.88, False)]
    clean_corpus = [(0.71, True), (0.72, True), (0.30, False), (0.25, False)]
    strict, loose = 0.915, 0.5

    noisy_at_strict = sweep_thresholds(noisy_corpus, [strict])[0]
    clean_at_loose = sweep_thresholds(clean_corpus, [loose])[0]
    # Each corpus has a threshold that separates relevant from noise:
    assert noisy_at_strict.f1 == 1.0  # 0.905 keeps the two relevant pairs only
    assert clean_at_loose.f1 == 1.0  # 0.5 keeps the two relevant pairs only

    # ...but the two thresholds do not transfer:
    assert sweep_thresholds(clean_corpus, [strict])[0].recall == 0.0  # cut too low for this corpus
    assert sweep_thresholds(noisy_corpus, [loose])[0].precision < 0.6  # noise crosses this cutoff

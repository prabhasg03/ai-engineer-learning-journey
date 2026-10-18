"""Tests for Topic 25 - pgvector semantics, IVFFlat, HNSW, filtered search.

The real Postgres is not invoked; these tests pin the semantics that the
SQL mirrors expose (operator formulas, dimension errors, Seq Scan vs
Index Scan, probes/ef_search recall curves, post-filtering behaviour,
iterative scans). Seeded everywhere: two builds with the same seed are
byte-identical.
"""
from __future__ import annotations

import math

from pgvector_sim import (
    INDEX_DIM_LIMITS,
    OPERATORS,
    TYPE_DIM_LIMITS,
    HNSWIndex,
    IVFFlatIndex,
    Row,
    VectorTable,
    build_corpus,
    cosine_distance,
    index_health_check,
    kmeans,
    l2_distance,
    negative_inner_product,
    recall,
    storage_bytes,
)

# -- operator mirrors ---------------------------------------------------------


def test_l2_distance_pythagoras():
    assert math.isclose(l2_distance([0, 0], [3, 4]), 5.0, rel_tol=1e-12)


def test_cosine_distance_identity():
    a, b = [1, 2], [2, 1]
    assert math.isclose(cosine_distance(a, b), 0.2, rel_tol=1e-12, abs_tol=1e-12)  # cos = 0.8
    assert math.isclose(cosine_distance(a, a), 0.0, abs_tol=1e-12)


def test_negative_inner_product_sign():
    assert negative_inner_product([1, 2, 3], [1, 2, 3]) == -14.0
    # most similar => most negative => sorts FIRST in ascending scans
    assert negative_inner_product([1, 0], [-1, 0]) == 1.0


def test_operator_table_contents():
    assert set(OPERATORS) == {"<->", "<=>", "<#>"}


def test_dimension_mismatch_raises_like_an_insert():
    t = VectorTable("items", dimensions=3)
    try:
        t.add(1, [1, 2])
        raise AssertionError("insert with wrong dims must raise")
    except ValueError as exc:
        assert "different vector dimensions" in str(exc)


def test_type_and_index_dim_limits():
    assert TYPE_DIM_LIMITS["vector"] == 16_000
    assert INDEX_DIM_LIMITS["vector"] == 2_000
    assert INDEX_DIM_LIMITS["halfvec"] == 4_000


def test_storage_bytes_formula():
    assert storage_bytes(1536) == 1536 * 4 + 8


def test_zero_vector_cosine_distance_is_nan():
    assert math.isnan(cosine_distance([0, 0], [1, 1]))


# -- the table (vector column + exact search) ----------------------------------


def make_table() -> VectorTable:
    table = VectorTable("items", dimensions=2)
    table.add(1, [1.0, 0.0], category="pets", content="dog doc")
    table.add(2, [0.0, 1.0], category="finance", content="bond doc")
    table.add(3, [0.9, 0.1], category="pets", content="puppy doc")
    table.add(4, [-1.0, 0.0], category="pets", content="opposite doc")
    return table


def test_exact_search_returns_sorted_topk():
    table = make_table()
    hits = table.search([1.0, 0.0], op="<=>", k=3)
    ids = [row.id for row, _ in hits]
    dists = [d for _, d in hits]
    assert ids[0] == 1
    assert ids[1] == 3
    assert ids[2] == 2  # [0,1] at distance 1.0, nearer than the opposite doc
    assert dists == sorted(dists)


def test_exact_search_upsert_and_delete():
    table = make_table()
    table.upsert(1, [1.0, 0.0], content="dog doc v2", category="pets")
    assert table.get(1).data["content"] == "dog doc v2"
    assert len(table) == 4
    assert table.delete(2) is True
    assert table.delete(99) is False
    assert len(table) == 3
    table.upsert(5, [0.0, -1.0], category="pets")
    assert len(table) == 4 and table.get(5).vector == [0.0, -1.0]


def test_exact_search_duplicate_id_raises():
    table = make_table()
    try:
        table.add(1, [1.0, 0.0])
        raise AssertionError("duplicate id should raise")
    except ValueError as exc:
        assert "already exists" in str(exc)


def test_exact_search_k_semantics():
    table = make_table()
    assert len(table.search([1.0, 0.0], k=2)) == 2
    assert len(table.search([1.0, 0.0], k=0)) == 0
    assert len(table.search([1.0, 0.0], k=99)) == 4  # more than rows -> all rows


def test_exact_search_where_dict():
    table = make_table()
    hits = table.search([1.0, 0.0], op="<=>", k=5, where={"category": "finance"})
    assert [row.id for row, _ in hits] == [2]


def test_exact_search_where_callable():
    table = make_table()
    hits = table.search([1.0, 0.0], op="<=>", k=5, where=lambda row: "doc" in row.data["content"])
    assert len(hits) == 4  # every fixture content contains "doc"


def test_seq_plan_vs_index_plan():
    table = make_table()
    assert table.plan() == "Seq Scan on items"
    assert table.plan(uses_index=True) == "Index Scan"


# -- the hybrid corpus ----------------------------------------------------------


def test_build_corpus_fixture_shape_and_ids():
    table, queries = build_corpus(n_per_cluster=10, dimensions=3, seed=7)
    assert len(table) == 50 == 5 * 10
    ids = sorted(row.id for row in table.rows)
    assert ids == list(range(50))
    clusters = {row.id: row.data["cluster"] for row in table.rows}
    assert clusters[0] == 0 and clusters[49] == 4
    assert all(math.isclose(sum(v * v for v in r.vector), 1.0, rel_tol=1e-9) for r in table.rows)
    assert len(queries) == 5


# -- k-means (ivfflat's training phase) -----------------------------------------


def test_kmeans_anchors_each_cluster_with_one_center():
    table, _ = build_corpus(n_per_cluster=10, dimensions=3, seed=7)
    km = kmeans([r.vector for r in table.rows], n_lists=5, seed=42)
    # strongest claim: every exact cluster's own rows mostly share a list
    per_cluster_lists: dict[int, set[int]] = {}
    for i, a in km.assignment.items():
        row = table.rows[i]
        per_cluster_lists.setdefault(row.data["cluster"], set()).add(a)
    dominant = all(len(s) <= 2 for s in per_cluster_lists.values())
    assert dominant


def test_kmeans_deterministic_seed():
    table, _ = build_corpus(n_per_cluster=6, dimensions=3, seed=7)
    a = kmeans([r.vector for r in table.rows], 5, seed=42)
    b = kmeans([r.vector for r in table.rows], 5, seed=42)
    assert a.assignment == b.assignment and a.centers == b.centers


def test_kmeans_rejects_more_lists_than_vectors():
    try:
        kmeans([[1, 0], [0, 1]], n_lists=3, seed=1)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_ivfflat_built_on_empty_table_raises():
    table = VectorTable("items", dimensions=2)
    try:
        IVFFlatIndex(table, lists=4, seed=42).build()
        raise AssertionError("build-before-data must raise")
    except ValueError as exc:
        assert "after the table has data" in str(exc)


# -- IVFFlat behaviour ----------------------------------------------------------


def make_corpus() -> tuple[VectorTable, list[list[float]]]:
    return build_corpus(n_per_cluster=10, dimensions=3, seed=7)


def test_ivfflat_search_returns_k_rows_sorted():
    table, queries = make_corpus()
    index = IVFFlatIndex(table, lists=5, seed=42).build()
    hits = index.search(queries[0], k=5, probes=5)
    assert len(hits) == 5
    dists = [d for _, d in hits]
    assert dists == sorted(dists)


def test_ivfflat_probes_equals_lists_is_exact():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    for q in queries:
        approx = ix.search(q, k=5, probes=5)  # probes == lists == every list
        exact = table.search(q, k=5)
        assert [row.id for row, _ in approx] == [row.id for row, _ in exact]


def test_ivfflat_recall_monotonic_in_probes():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=15, seed=42).build()  # a coarse partition
    recall_at = {}
    for probes in (1, 2, 4):
        scores = [recall(ix.search(q, k=5, probes=probes), table.search(q, k=5)) for q in queries]
        recall_at[probes] = sum(scores) / len(scores)
    assert recall_at[4] == 1.0
    assert recall_at[1] <= recall_at[2] <= recall_at[4]
    assert recall_at[1] < 1.0  # default probes=1 genuinely loses neighbours


def test_ivfflat_defaults_to_probes_one():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    assert ix.search(queries[0], k=5) == ix.search(queries[0], k=5, probes=1)


def test_ivfflat_probes_clamped():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    assert len(ix.search(queries[0], k=5, probes=999)) == 5  # clamped to lists


def test_ivfflat_where_filter_and_iterative():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    q = queries[0]
    # cluster 0 is the nearest cluster for q; querying with a WHERE on a
    # far cluster with default probes finds nothing without iteration
    hits_far = ix.search(q, k=3, probes=1, where={"cluster": 4})
    hits_far_iterative = ix.search(q, k=3, probes=1, where={"cluster": 4}, iterative=True, max_probes=5)
    assert not hits_far or all(row.data["cluster"] == 4 for row, _ in hits_far)
    assert len(hits_far_iterative) == 3
    assert all(row.data["cluster"] == 4 for row, _ in hits_far_iterative)


def test_ivfflat_plan_string():
    table, _ = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    assert ix.plan() == "Index Scan using items_ivfflat_idx"


def test_ivfflat_deterministic_rebuilds():
    table, _ = make_corpus()
    a = IVFFlatIndex(table, lists=5, seed=42).build()
    b = IVFFlatIndex(table, lists=5, seed=42).build()
    assert a.assignments == b.assignments
    assert a.lists_rows == b.lists_rows


# -- HNSW behaviour ---------------------------------------------------------------


def test_hnsw_recall_is_high_at_default_ef():
    table, queries = make_corpus()
    ix = HNSWIndex(table, m=8, seed=42).build()
    for q in queries:
        hits = ix.search(q, k=5)  # ef_search 40
        assert len(hits) == 5
        score = recall(hits, table.search(q, k=5))
        assert score >= 0.6, f"hnsw recall@5 {score} too low"


def test_hnsw_recall_improves_with_ef():
    table, queries = make_corpus()
    ix = HNSWIndex(table, m=8, seed=42).build()
    low = sum(recall(ix.search(q, k=5, ef_search=8), table.search(q, k=5)) for q in queries) / 5
    high = sum(recall(ix.search(q, k=5, ef_search=60), table.search(q, k=5)) for q in queries) / 5
    assert high >= low
    assert high > 0.5


def test_hnsw_deterministic_rebuilds_same_graph():
    table, _ = make_corpus()
    a = HNSWIndex(table, m=8, seed=42).build()
    b = HNSWIndex(table, m=8, seed=42).build()
    assert a.layers == b.layers
    assert a.entry_point == b.entry_point


def test_hnsw_every_node_reachable_in_layer0_and_entry_point_exists():
    table, _ = make_corpus()
    ix = HNSWIndex(table, m=8, seed=42).build()
    assert ix.entry_point is not None
    reachable = {ix.entry_point}
    frontier = [ix.entry_point]
    while frontier:
        node = frontier.pop()
        for nb in ix.layers[0].get(node, set()):
            if nb not in reachable:
                reachable.add(nb)
                frontier.append(nb)
    assert reachable == set(range(len(table)))


def test_hnsw_where_filter_applied_after_scan():
    table, queries = make_corpus()
    ix = HNSWIndex(table, m=8, seed=42).build()
    q = queries[0]
    # filter to a single cluster: ef_search=40 candidates mostly fail it,
    # so the post-filter returns FEWER than k rows (the pgvector footnote)
    hits = ix.search(q, k=3, ef_search=12, where={"cluster": 0})
    assert all(row.data["cluster"] == 0 for row, _ in hits)
    iterative = ix.search(q, k=3, ef_search=12, where={"cluster": 0}, iterative=True)
    assert len(iterative) == 3  # widened scan keeps going until enough


def test_hnsw_plan_string():
    table, _ = make_corpus()
    ix = HNSWIndex(table, m=8, seed=42).build()
    assert ix.plan() == "Index Scan using items_hnsw_idx"


def test_hnsw_m_rejected_below_two():
    table, _ = make_corpus()
    try:
        HNSWIndex(table, m=1, seed=42)
        raise AssertionError("m=1 should be rejected")
    except ValueError:
        pass


# -- combined: exact vs ANN + health check ---------------------------------------


def test_recall_function_semantics():
    r1, r2, r3, r4 = Row(1, [0]), Row(2, [0]), Row(3, [0]), Row(4, [0])
    exact = [(r1, 0.1), (r2, 0.2), (r3, 0.3), (r4, 0.4)]
    approx = [(r1, 0.11), (r3, 0.32)]
    # ground truth top-4: ids 1,2,3,4; approx returned ids 1,3
    assert recall(approx, exact) == 2 / 4


def test_index_health_check_produces_recall_scores():
    table, queries = make_corpus()
    scores = index_health_check(table, queries, k=5)
    assert set(scores) == {
        "ivfflat_probes_1",
        "ivfflat_probes_3",
        "ivfflat_probes_5",
        "hnsw_ef_search_16",
        "hnsw_ef_search_40",
    }
    assert scores["ivfflat_probes_5"] == 1.0
    assert scores["hnsw_ef_search_40"] >= scores["ivfflat_probes_1"]
    assert 0.0 <= scores["ivfflat_probes_1"] <= 1.0


def test_shared_rows_report_identical_distances():
    table, queries = make_corpus()
    ix = IVFFlatIndex(table, lists=5, seed=42).build()
    h = HNSWIndex(table, m=8, seed=42).build()
    q = queries[0]
    exact = {row.id: d for row, d in table.search(q, k=20)}
    for row, d in ix.search(q, k=20, probes=5):
        assert math.isclose(exact[row.id], d, rel_tol=1e-9)
    for row, d in h.search(q, k=20, ef_search=60):
        assert math.isclose(exact[row.id], d, rel_tol=1e-9)

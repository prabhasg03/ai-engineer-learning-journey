"""Topic 23 - Cosine similarity: angles, magnitude invariance, thresholds.

Three layers live here:

1. Pure-Python vector math, mirroring the pgvector operators exactly:
   - `<->`  L2 (Euclidean) distance            -> l2_distance
   - `<=>`  cosine DISTANCE = 1 - cosine sim  -> cosine_distance
   - `<#>`  NEGATIVE inner product            -> negative_inner_product
   (pgvector README: "<#> returns the negative inner product since Postgres
   only supports ASC order index scans on operators.")

2. numpy versions of the same functions, so "in code: numpy, then pgvector
   operators" is literally in the module.

3. Threshold calibration: `sweep_thresholds` and `best_f1_threshold`, the
   offline version of "there is no universal cosine threshold - tune per
   corpus".

Also: the worked hand computation for (1,2) x (2,1) that the syllabus' done-
when asks for is spelled out in `HAND_COMPUTATION` and asserted in the tests.

Zero-vector behaviour intentionally mirrors pgvector: cosine distance of a
zero vector yields NaN (pgvector returns NaN; zero vectors are simply not
indexed for cosine distance).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# 1. Pure python - the hand computations
# ---------------------------------------------------------------------------

# Worked by hand: a = (1, 2), b = (2, 1)
#   dot(a, b)        = 1*2 + 2*1            = 4
#   |a| = sqrt(1+4)  = sqrt(5)              |b| = sqrt(5)
#   cos(a, b)        = 4 / (sqrt(5)*sqrt(5)) = 4/5 = 0.8
#   angle            = arccos(0.8)          = 36.8698976... degrees
#   cosine distance  = 1 - 0.8              = 0.2
HAND_COMPUTATION = {
    "a": (1, 2),
    "b": (2, 1),
    "dot": 4,
    "mag_a": math.sqrt(5),
    "mag_b": math.sqrt(5),
    "cosine": 0.8,
    "angle_degrees": 36.86989764584402,
    "cosine_distance": 0.2,
}


def dot_product(a, b) -> float:
    """Sum of element-wise products. Order of the two args does not matter."""
    if len(a) != len(b):
        raise ValueError(f"vectors must have the same length, got {len(a)} and {len(b)}")
    return sum(x * y for x, y in zip(a, b))


def magnitude(v) -> float:
    """Euclidean length sqrt(sum(v_i^2))."""
    return math.sqrt(dot_product(v, v))


def cosine_similarity(a, b) -> float:
    """cos(angle between a and b) = dot / (|a| * |b|).

    Magnitude invariance: scaling either vector by a POSITIVE constant
    cannot change the result, because the scale factors cancel. This is the
    reason embeddings are compared by angle, not by Euclidean distance
    (see notes section 5).
    """
    if len(a) != len(b):
        raise ValueError(f"vectors must have the same length, got {len(a)} and {len(b)}")
    na, nb = magnitude(a), magnitude(b)
    if na == 0.0 or nb == 0.0:
        return float("nan")  # pgvector parity: zero vectors -> NaN
    return dot_product(a, b) / (na * nb)


def cosine_distance(a, b) -> float:
    """pgvector's `<=>`: cosine DISTANCE = 1 - cosine similarity.

    Low distance = similar. Not a metric in the triangle-inequality sense,
    but a perfectly good ordering.
    """
    sim = cosine_similarity(a, b)
    if math.isnan(sim):
        return float("nan")
    return 1.0 - sim


def angle_degrees(a, b) -> float:
    """Angle in degrees between two vectors, computed through cosine."""
    sim = cosine_similarity(a, b)
    if math.isnan(sim):
        return float("nan")
    clipped = max(-1.0, min(1.0, sim))  # guard float error before acos
    return math.degrees(math.acos(clipped))


def euclidean_distance(a, b) -> float:
    """sqrt of sum of squared differences — what `<->` computes."""
    if len(a) != len(b):
        raise ValueError(f"vectors must have the same length, got {len(a)} and {len(b)}")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def negative_inner_product(a, b) -> float:
    """pgvector's `<#>`: the inner product, negated.

    Exists because Postgres index scans walk operators in ASCending order:
    "most similar" must be the SMALLEST value, like a distance.
    """
    if len(a) != len(b):
        raise ValueError(f"vectors must have the same length, got {len(a)} and {len(b)}")
    return -dot_product(a, b)


def l2_distance(a, b) -> float:
    """Alias keeping the pgvector operator name visible (`<->`)."""
    return euclidean_distance(a, b)


# ---------------------------------------------------------------------------
# 2. numpy layer ("in code: numpy, then pgvector operators")
# ---------------------------------------------------------------------------


def np_cosine_similarity_matrix(matrix, query):
    """Cosine similarity of every row of `matrix` against a query vector.

    One dot product against a stacked matrix instead of a loop - this is
    the shape real vector search takes (a table of embeddings vs a query).
    """
    import numpy as np

    m = np.asarray(matrix, dtype=float)
    q = np.asarray(query, dtype=float)
    if m.ndim != 2 or q.ndim != 1:
        raise ValueError("expected matrix shape (n, d) and query shape (d,)")
    if m.shape[1] != q.shape[0]:
        raise ValueError(f"different vector dimensions {m.shape[1]} and {q.shape[0]}")
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    denom = m_norms * q_norm
    with np.errstate(invalid="ignore", divide="ignore"):
        sims = m @ q / denom
    return sims  # NaN where a row or query is zero (pgvector parity)


def np_rank_by_similarity(matrix, query, k):
    """Row indices of the k most similar rows (best first, NaN excluded)."""
    sims = np_cosine_similarity_matrix(matrix, query)
    order = [i for i in range(len(sims)) if not math.isnan(float(sims[i]))]
    order.sort(key=lambda i: (-float(sims[i]), i))
    return order[:k]


# ---------------------------------------------------------------------------
# 3. Threshold calibration - "no universal number; tune per corpus"
# ---------------------------------------------------------------------------


@dataclass
class ThresholdRow:
    """One row of a threshold sweep: candidate cut-off + resulting P/R/F1."""

    threshold: float
    precision: float
    recall: float
    f1: float


def sweep_thresholds(pairs, thresholds) -> list[ThresholdRow]:
    """Precision/recall/F1 for each candidate cosine-similarity cutoff.

    `pairs` is a list of (similarity, is_relevant) tuples - in a real system
    these come from scoring your golden set (Topic 22 section 6) against
    labels. For every threshold t:
        a pair counts as retrieved when similarity >= t
    then:
        precision = relevant-retrieved / retrieved
        recall    = relevant-retrieved / total-relevant
        f1        = harmonic mean.
    """
    rows = []
    total_relevant = sum(1 for _, rel in pairs if rel)
    for t in sorted(thresholds):
        retrieved = [rel for sim, rel in pairs if sim >= t]
        retrieved_relevant = sum(1 for rel in retrieved if rel)
        retrieved_count = len(retrieved)
        precision = retrieved_relevant / retrieved_count if retrieved_count else 0.0
        recall = retrieved_relevant / total_relevant if total_relevant else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        rows.append(ThresholdRow(threshold=t, precision=precision, recall=recall, f1=f1))
    return rows


def best_f1_threshold(pairs, thresholds) -> ThresholdRow:
    """The cutoff with the best F1 - deterministic, ties broken by the
    earlier (lower) threshold in the scan. Best-F1 is a starting point, not
    a law: also look at the precision/recall trade the product needs.
    """
    rows = sweep_thresholds(pairs, thresholds)
    return min(rows, key=lambda r: (-r.f1, r.threshold))


def calibration_report(pairs, thresholds) -> str:
    """Printable table for the notebook: threshold -> precision/recall/F1."""
    rows = sweep_thresholds(pairs, thresholds)
    lines = ["threshold | precision | recall | f1", "----------+-----------+--------+----"]
    for r in rows:
        lines.append(f"{r.threshold:8.2f} | {r.precision:9.2f} | {r.recall:6.2f} | {r.f1:.2f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Offline demo: `python cosine.py`
# ---------------------------------------------------------------------------


def _demo() -> None:
    a, b = HAND_COMPUTATION["a"], HAND_COMPUTATION["b"]
    print("topic 23 - cosine similarity by hand (offline demo)")
    print("the worked example: a = (1, 2), b = (2, 1)")
    print(f"  dot={dot_product(a, b)} |a|={magnitude(a):.4f} |b|={magnitude(b):.4f}"
          f" cos={cosine_similarity(a, b):.4f} angle={angle_degrees(a, b):.4f} deg"
          f" cosine_distance={cosine_distance(a, b):.4f}")
    scaled = [1000.0 * x for x in a]
    print(f"magnitude invariance: cosine({scaled}, {b}) = {cosine_similarity(scaled, b):.4f}"
          f" but euclidean = {euclidean_distance(scaled, b):.1f}")
    print("pgvector operator mirrors on the same vectors:")
    print(f"  <-> {l2_distance(a, b):.4f}   <=> {cosine_distance(a, b):.4f}"
          f"   <#> {negative_inner_product(a, b):.4f}")
    import numpy

    matrix = numpy.array([[1.0, 2.0], [2.0, 1.0], [-1.0, 0.5], [0.0, 1.0]])
    order = np_rank_by_similarity(matrix, [1, 2], k=3)
    print(f"numpy batch ranking against (1, 2): rows {order}")
    pairs = [(0.93, True), (0.90, True), (0.88, True), (0.61, False),
             (0.55, True), (0.40, False), (0.35, False), (0.21, False)]
    print("threshold sweep on a labelled golden set:")
    print(calibration_report(pairs, [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]))


if __name__ == "__main__":
    _demo()

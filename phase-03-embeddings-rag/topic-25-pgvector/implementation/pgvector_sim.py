"""Topic 25 - pgvector: a hand-written mini vector database.

No Postgres server is required for these tests, so this module mirrors
pgvector's *semantics* in pure Python: the same operators, the same index
behaviours, the same failure modes - so the reasoning you build here
transfers to the real SQL unchanged.

What lives here:

- ``VectorTable``   - a vector column: typed, fixed dimensions, insert
  validation (pgvector errors on dimension mismatch), exact scan search.
- distance operator mirrors: ``l2_distance`` (`<->`), ``cosine_distance``
  (`<=>`), ``negative_inner_product`` (`<#>`).
- ``IVFFlatIndex``  - inverted-file index: k-means into ``lists`` clusters,
  scan the ``probes`` nearest clusters. Fast to build, small, needs
  training data, recall depends on probe count (pgvector default: 1).
- ``HNSWIndex``     - layered "small world" graph: greedy descent through
  sparse layers, beam search (``ef_search``) in the dense bottom layer.
  No training step, better speed-recall than IVFFlat, more memory,
  slower to build (Crunchy Data: "cutting edge for all vector indexing").
- ``where``         - SQL-style filter predicate; pgvector applies filters
  AFTER the index scan (see `test_hnsw_where_filter_applied_after_scan`), which can return fewer
  rows than asked; the ``iterative`` flag mirrors pgvector 0.8+
  "iterative index scans" that keep scanning until enough rows match.
- ``plan``          - "Seq Scan" (exact) vs "Index Scan using ..." (ANN),
  mirroring what EXPLAIN prints and why ORDER BY + LIMIT matters.
- ``recall``        - score of an approximate index against exact results

Determinism: every index takes an explicit seed; k-means uses seeded
k-means++ init; HNSW uses seeded exponential layer sampling. Two builds
with the same seed produce identical structures (asserted in tests).
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Operator mirrors (identical formulas in Topic 23's pure-python layer)
# ---------------------------------------------------------------------------


def dot_product(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def magnitude(v: list[float]) -> float:
    return math.sqrt(dot_product(v, v))


def l2_distance(a: list[float], b: list[float]) -> float:
    """`<->`  - Euclidean (L2) distance."""
    if len(a) != len(b):
        raise _dimension_mismatch(len(a), len(b))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def cosine_distance(a: list[float], b: list[float]) -> float:
    """`<=>`  - cosine DISTANCE = 1 - cosine similarity.

    pgvector parity: zero vectors produce NaN (and are skipped by cosine
    indexes).
    """
    if len(a) != len(b):
        raise _dimension_mismatch(len(a), len(b))
    na, nb = magnitude(a), magnitude(b)
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return 1.0 - dot_product(a, b) / (na * nb)


def negative_inner_product(a: list[float], b: list[float]) -> float:
    """`<#>` - the inner product, NEGATED.

    pgvector README: "<#> returns the negative inner product since Postgres
    only supports ASC order index scans on operators."
    """
    if len(a) != len(b):
        raise _dimension_mismatch(len(a), len(b))
    return -dot_product(a, b)


OPERATORS: dict[str, Callable[[list[float], list[float]], float]] = {
    "<->": l2_distance,
    "<=>": cosine_distance,
    "<#>": negative_inner_product,
}


def _dimension_mismatch(a: int, b: int) -> ValueError:
    return ValueError(f"different vector dimensions {a} and {b}")


def _distance(op: str, a: list[float], b: list[float]) -> float:
    if op not in OPERATORS:
        raise ValueError(f"unsupported operator {op!r}; expected one of {sorted(OPERATORS)}")
    return OPERATORS[op](a, b)


# ---------------------------------------------------------------------------
# The vector column ("embedding vector(3)"). Validation mirrors pgvector:
# STORED ONLY tables hold any number of dims (type cap 16,000) but an
# INDEX caps at 2,000 dims (halfvec 4,000, bit 64,000).
# ---------------------------------------------------------------------------


TYPE_DIM_LIMITS = {"vector": 16_000, "halfvec": 16_000, "bit": 64_000, "sparsevec": 16_000}
# NOTE from the README's index section: vector indexes cap at 2,000 dims
# (halfvec 4,000, bit 64,000); a `sparsevec` index caps at 1,000 NON-ZERO
# elements (the type itself still holds 16,000 - see TYPE_DIM_LIMITS).
INDEX_DIM_LIMITS = {"vector": 2_000, "halfvec": 4_000, "bit": 64_000, "sparsevec": 1_000}


def storage_bytes(dimensions: int) -> int:
    """pgvector README: 'Each vector takes 4 * dimensions + 8 bytes'."""
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    return 4 * dimensions + 8


@dataclass
class Row:
    id: str | int
    vector: list[float]
    data: dict = field(default_factory=dict)  # the other SQL columns


class VectorTable:
    """A table with a typed vector column and exact (sequential) search.

    Mirrors:

        CREATE TABLE items (id bigserial PRIMARY KEY,
                            content text, embedding vector(dims));
        SELECT * FROM items ORDER BY embedding <=> query LIMIT k;

    No index => the planner does a SEQ SCAN over every row: perfect
    recall, O(n) work per query. Good enough for small tables (docs-scale).
    """

    def __init__(self, name: str = "items", dimensions: int = 3) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if dimensions > TYPE_DIM_LIMITS["vector"]:
            raise ValueError("vector columns hold up to 16,000 dimensions")
        self.name = name
        self.dimensions = dimensions
        self.rows: list[Row] = []

    # -- writes ------------------------------------------------------------

    def add(self, id_, vector: list[float], **data) -> Row:
        vector = [float(v) for v in vector]
        if len(vector) != self.dimensions:
            raise _dimension_mismatch(len(vector), self.dimensions)
        if self.get(id_) is not None:
            raise ValueError(f"row with id {id_!r} already exists (use upsert)")
        row = Row(id_, vector, dict(data))
        self.rows.append(row)
        return row

    def upsert(self, id_, vector: list[float], **data) -> Row:
        """INSERT ... ON CONFLICT (id) DO UPDATE SET embedding = ..."""
        existing = self.get(id_)
        vector = [float(v) for v in vector]
        if existing is not None:
            if len(vector) != self.dimensions:
                raise _dimension_mismatch(len(vector), self.dimensions)
            existing.vector = vector
            existing.data = dict(data)
            return existing
        return self.add(id_, vector, **data)

    # -- reads -------------------------------------------------------------

    def get(self, id_) -> Row | None:
        for row in self.rows:
            if row.id == id_:
                return row
        return None

    def delete(self, id_) -> bool:
        for i, row in enumerate(self.rows):
            if row.id == id_:
                del self.rows[i]
                return True
        return False

    def __len__(self) -> int:
        return len(self.rows)

    # -- exact search --------------------------------------------------------

    def search(
        self,
        query: list[float],
        op: str = "<=>",
        k: int = 5,
        where: dict | Callable[[Row], bool] | None = None,
    ) -> list[tuple[Row, float]]:
        """Exact nearest neighbours: scan every row, sort by distance ASC.

        `where` mirrors a SQL WHERE clause: either a dict of equality
        predicates or a callable(Row) -> bool.
        """
        query = [float(v) for v in query]
        if len(query) != self.dimensions:
            raise _dimension_mismatch(len(query), self.dimensions)
        predicate = _as_predicate(where)
        hits = []
        for row in self.rows:
            if predicate is None or predicate(row):
                hits.append((row, _distance(op, query, row.vector)))
        # NaN distances (zero vectors under <=>) sort last, like pgvector's
        # behaviour of excluding them from the index.
        hits.sort(key=lambda pair: (math.isnan(pair[1]), pair[1], str(pair[0].id)))
        k = max(0, int(k))
        return hits[:k]

    def plan(self, uses_index: bool = False) -> str:
        """The EXPLAIN line, abbreviated."""
        return "Seq Scan on " + self.name if not uses_index else "Index Scan"

    # NOTE on hand-written style comments: the notes.md companion shows the
    # real SQL for each mirrored behaviour.


def _as_predicate(where) -> Callable[[Row], bool] | None:
    if where is None:
        return None
    if callable(where):
        return where
    if isinstance(where, dict):

        def predicate(row: Row) -> bool:
            return all(row.data.get(key) == value for key, value in where.items())

        return predicate
    raise ValueError("where must be a callable or a dict of equality predicates")


# ---------------------------------------------------------------------------
# Seeded vector corpus for the index demos/tests
# ---------------------------------------------------------------------------

CLUSTER_CENTERS = [
    (2.0, 2.0, 0.5),
    (-2.0, -2.5, 0.5),
    (-2.0, 2.5, 2.0),
    (2.0, -2.5, -2.0),
    (0.0, 0.0, -3.0),
]


def build_corpus(
    n_per_cluster: int = 10,
    dimensions: int = 3,
    seed: int = 7,
    jitter: float = 0.4,
) -> tuple[VectorTable, list[list[float]]]:
    """Fixture: clusters with deterministic jitter + held-out queries.

    Returns (table, queries). Every vector is L2-normalised to unit length
    (the OpenAI-style shape, where cosine and dot ranking coincide).
    """
    import random as _random

    rng = _random.Random(seed)
    table = VectorTable("items", dimensions)
    queries: list[list[float]] = []
    idx = 0
    for c, center in enumerate(CLUSTER_CENTERS):
        for j in range(n_per_cluster):
            vec = [center[k] + rng.uniform(-jitter, jitter) for k in range(dimensions)] if dimensions == len(center) else None
            if vec is None:
                vec = [(center[k % len(center)] if k < dimensions else 0.5) + rng.uniform(-jitter, jitter) for k in range(dimensions)]
            vec = [v / magnitude(vec) for v in vec]
            table.add(idx, vec, cluster=c, text=f"doc {idx} of cluster {c}")
            idx += 1
        # one held-out query per cluster, slightly off-center
        q = [center[k] + rng.uniform(-0.2, 0.2) for k in range(min(dimensions, len(center)))]
        while len(q) < dimensions:
            q.append(0.25)
        q = [v / magnitude(q) for v in q]
        queries.append(q)
    return table, queries


# ---------------------------------------------------------------------------
# 1. IVFFlat: inverted file index
# ---------------------------------------------------------------------------


@dataclass
class KMeansResult:
    centers: list[list[float]]
    assignment: dict[int, int]  # row position in table -> list/cluster id
    iterations: int


def kmeans(
    vectors: list[list[float]],
    n_lists: int,
    seed: int = 42,
    max_iterations: int = 25,
) -> KMeansResult:
    """Lloyd's algorithm, seeded k-means++ init (pgvector trains its lists
    with k-means too - IVFFlat's build phase is 'performing k-means')."""
    if n_lists < 1:
        raise ValueError("lists must be >= 1")
    if len(vectors) < n_lists:
        raise ValueError("need at least one training vector per list")
    rng = random.Random(seed)
    dim = len(vectors[0])

    # --- k-means++ seeding -------------------------------------------------
    centers = [list(vectors[rng.randrange(len(vectors))])]
    while len(centers) < n_lists:
        # weight each vector by its squared distance to the nearest center
        def d2(v: list[float]) -> float:
            return min(l2_distance(v, c) ** 2 for c in centers)

        weights = [d2(v) for v in vectors]
        total = sum(weights)
        pick, acc = rng.random() * total, 0.0
        for v, w in zip(vectors, weights):
            acc += w
            if acc >= pick:
                centers.append(list(v))
                break
        else:
            centers.append(list(vectors[-1]))

    # --- Lloyd iterations --------------------------------------------------
    assignment: dict[int, int] = {}
    iterations = 0
    for _ in range(max_iterations):
        iterations += 1
        new_assign = {}
        for i, v in enumerate(vectors):
            best, best_d = 0, float("inf")
            for c, center in enumerate(centers):
                d = l2_distance(v, center)
                if d < best_d:
                    best, best_d = c, d
            new_assign[i] = best
        moved = 0.0
        for c in range(n_lists):
            members = [vectors[i] for i, a in new_assign.items() if a == c]
            if members:
                new_center = [
                    sum(v[d] for v in members) / len(members) for d in range(dim)
                ]
                moved += l2_distance(centers[c], new_center)
                centers[c] = new_center
            else:
                # empty cluster: grab a random unassigned-ish point
                centers[c] = list(vectors[rng.randrange(len(vectors))])
        assignment = new_assign
        if moved < 1e-9:
            break
    return KMeansResult(centers=centers, assignment=assignment, iterations=iterations)


class IVFFlatIndex:
    """Inverted-file index: cluster into `lists`, scan the `probes` nearest.

    Mirrors:

        CREATE INDEX ON items USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        SET ivfflat.probes = 4;      -- default 1!

    Keys to good recall (from the pgvector README):
      1. create the index AFTER the table has data,
      2. lists = rows/1000 (up to 1M rows) or sqrt(rows) beyond that,
      3. probes = sqrt(lists) is a good starting point.
    Small tables (our toy corpus) would skip this index entirely - the
    planner prefers a Seq Scan.
    """

    def __init__(self, table: VectorTable, lists: int, op: str = "<=>", seed: int = 42) -> None:
        self.table = table
        if lists < 1:
            raise ValueError("lists must be >= 1")
        if table.dimensions > INDEX_DIM_LIMITS["vector"]:
            raise ValueError("ivfflat indexes cap vector at 2,000 dimensions")
        self.lists = lists
        self.op = op
        self.seed = seed
        self.km: KMeansResult | None = None
        self.assignments: dict[int, int] = {}  # row position -> list id
        self.lists_rows: dict[int, list[int]] = {}

    def build(self) -> "IVFFlatIndex":
        """'Create the index after the table has some data' - we enforce it."""
        if len(self.table) == 0:
            raise ValueError("create the index after the table has data")
        self.km = kmeans([r.vector for r in self.table.rows], self.lists, seed=self.seed)
        self.assignments = {i: a for i, a in self.km.assignment.items()}
        self.lists_rows = {c: [] for c in range(self.lists)}
        for i, a in self.assignments.items():
            self.lists_rows[a].append(i)
        return self

    def _candidate_positions(self, query: list[float], probes: int) -> list[int]:
        assert self.km is not None
        probe = max(1, min(probes, self.lists))
        order = sorted(
            range(self.lists), key=lambda c: (l2_distance(query, self.km.centers[c]), c)
        )
        candidates: list[int] = []
        for c in order[:probe]:
            candidates.extend(self.lists_rows[c])
        return candidates

    def search(
        self,
        query: list[float],
        k: int = 5,
        where=None,
        probes: int = 1,
        iterative: bool = False,
        max_probes: int = 100,
    ) -> list[tuple[Row, float]]:
        """Approximate search; `iterative=True` mirrors pgvector 0.8+
        iterative scans: widen probes until k rows pass the filter or the
        probe cap is reached."""
        query = [float(v) for v in query]
        if len(query) != self.table.dimensions:
            raise _dimension_mismatch(len(query), self.table.dimensions)
        predicate = _as_predicate(where)
        used_probes = min(max(1, probes), self.lists)
        cap = max_probes if iterative else used_probes
        while True:
            positions = self._candidate_positions(query, used_probes)
            hits = [
                (self.table.rows[i], _distance(self.op, query, self.table.rows[i].vector))
                for i in positions
                if predicate is None or predicate(self.table.rows[i])
            ]
            if hits or not iterative:
                break
            if used_probes >= cap:
                break
            used_probes = min(used_probes + max(1, (cap - used_probes) // 2), cap)
        # NaN distances sort last (zero vectors are skipped by cosine indexes)
        hits.sort(key=lambda pair: (math.isnan(pair[1]), pair[1], str(pair[0].id)))
        return hits[: max(0, int(k))]

    def plan(self) -> str:
        return f"Index Scan using {self.table.name}_ivfflat_idx"


# ---------------------------------------------------------------------------
# 2. HNSW: hierarchical navigable small world graph
# ---------------------------------------------------------------------------


class HNSWIndex:
    """Layered graph index, hand-written: M links per node, ef candidates.

    Mirrors:

        CREATE INDEX ON items USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        SET hnsw.ef_search = 40;     -- default 40

    Build: insert rows one at a time. New points get a top layer by
    exponential sampling (P(layer) = 1/M, seeded); they connect greedily.
    Search: descend layers with ef=1, beam search ef_search in layer 0.
    Crunchy Data's advice holds in code: bigger m / ef_construction means
    slower builds for little extra quality; ef_search is your recall knob.
    """

    def __init__(
        self,
        table: VectorTable,
        m: int = 8,
        ef_construction: int = 64,
        op: str = "<=>",
        seed: int = 42,
    ) -> None:
        self.table = table
        if table.dimensions > INDEX_DIM_LIMITS["vector"]:
            raise ValueError("hnsw indexes cap vector at 2,000 dimensions")
        if m < 2:
            raise ValueError("m must be >= 2 (paper's useful range: 5..48)")
        self.m = m
        self.m_max0 = m * 2  # paper: 2M links at layer 0
        self.ef_construction = ef_construction
        self.op = op
        self.rng = random.Random(seed)
        self.layers: dict[int, dict[int, set[int]]] = {0: {}}
        self.entry_point: int | None = None
        self.max_layer = 0
        self._insertion_order: list[int] = []

    # -- internals ----------------------------------------------------------

    def _dist(self, a: list[float], b: list[float]) -> float:
        return _distance(self.op, a, b)

    def _random_level(self) -> int:
        # P(layer >= l) = (1/M)^l  (seeded exponential sampling)
        u = self.rng.random() or 1e-12
        return int(-math.log(u) * (1.0 / math.log(self.m)))

    def _search_layer(
        self,
        query: list[float],
        entry_points: list[int],
        layer: int,
        ef: int,
        allowed: set[int] | None = None,
    ) -> list[int]:
        """Beam search one layer, return the ef closest visited nodes."""
        vectors = self.table.rows
        visited = set(entry_points)
        candidates: list[tuple[float, int]] = []
        results: list[tuple[float, int]] = []
        for ep in entry_points:
            d = self._dist(query, vectors[ep].vector)
            heapq.heappush(candidates, (d, ep))
            heapq.heappush(results, (-d, ep))
        while len(results) > ef:
            heapq.heappop(results)
        while candidates:
            d, node = heapq.heappop(candidates)
            farthest = -results[0][0]
            if d > farthest and len(results) >= ef:
                break
            neighbours = self.layers[layer].get(node, set())
            for nb in neighbours:
                if allowed is not None and nb not in allowed:
                    continue
                if nb in visited:
                    continue
                visited.add(nb)
                nd = self._dist(query, vectors[nb].vector)
                farthest = -results[0][0]
                if len(results) < ef or nd < farthest:
                    heapq.heappush(candidates, (nd, nb))
                    heapq.heappush(results, (-nd, nb))
                    if len(results) > ef:
                        heapq.heappop(results)
        gathered = [(-neg_d, node) for neg_d, node in results]
        gathered.sort()
        return [node for _, node in gathered]

    def _select_neighbors(
        self, base: list[float], candidates: list[int], m: int
    ) -> list[int]:
        """Heuristic selection (diversity-aware, as in the paper): keep a
        candidate only if it is closer to the new point than to any
        already-selected neighbour."""
        vectors = self.table.rows
        scored = sorted(
            ((self._dist(base, vectors[i].vector), i) for i in candidates),
            key=lambda pair: (pair[0], pair[1]),
        )
        selected: list[int] = []
        for _, idx in scored:
            if len(selected) >= m:
                break
            v = vectors[idx].vector
            ok = True
            for s in selected:
                if self._dist(v, vectors[s].vector) < self._dist(base, v):
                    ok = False
                    break
            if ok:
                selected.append(idx)
        # backfill with plain closest if the heuristic pruned everything
        if len(selected) < m:
            for _, idx in scored:
                if idx not in selected:
                    selected.append(idx)
                if len(selected) >= m:
                    break
        return selected

    # -- build ---------------------------------------------------------------

    def build(self) -> "HNSWIndex":
        if len(self.table) == 0:
            raise ValueError("build the index after loading data")
        for position in range(len(self.table)):
            self._insert(position)
        return self

    def _insert(self, position: int) -> None:
        vectors = self.table.rows
        vec = vectors[position].vector
        level = self._random_level()
        self._insertion_order.append(position)
        for l in range(max(self.max_layer, level) + 1):
            self.layers.setdefault(l, {})
        for l in range(level + 1):
            self.layers[l][position] = set()
        if self.entry_point is None:
            self.entry_point = position
            self.max_layer = level
            return
        # descend from the top layer to level+1 with greedy ef=1
        node = self.entry_point
        for l in range(self.max_layer, level, -1):
            path = self._search_layer(vec, [node], l, 1)
            node = path[0]
        # insert at each layer between min(level, max_layer) and 0
        for l in range(min(level, self.max_layer), -1, -1):
            entry_layer = self.layers[l]
            if not entry_layer:
                self.layers[l][position] = set()
                continue
            candidates = self._search_layer(vec, [node], l, max(self.ef_construction, 1))
            selected = self._select_neighbors(vec, candidates, self.m)
            self.layers[l][position] = set(selected)
            m_limit = self.m_max0 if l == 0 else self.m
            for s in selected:
                links = self.layers[l][s]
                links.add(position)
                if len(links) > m_limit:
                    # prune the overfull neighbour by its own distances
                    sv = vectors[s].vector
                    best = sorted(
                        links,
                        key=lambda n2: (self._dist(sv, vectors[n2].vector), n2),
                    )[:m_limit]
                    self.layers[l][s] = set(best)
            node = selected[0] if selected else node
        if level > self.max_layer:
            self.max_layer = level
            self.entry_point = position

    # -- search ----------------------------------------------------------------

    def search(
        self,
        query: list[float],
        k: int = 5,
        where=None,
        ef_search: int = 40,
        iterative: bool = False,
    ) -> list[tuple[Row, float]]:
        query = [float(v) for v in query]
        if len(query) != self.table.dimensions:
            raise _dimension_mismatch(len(query), self.table.dimensions)
        predicate = _as_predicate(where)
        ef = max(ef_search, k)
        node = self.entry_point
        if node is None:
            return []
        for l in range(self.max_layer, 0, -1):
            node = self._search_layer(query, [node], l, 1)[0]
        best = self._search_layer(query, [node], 0, ef)
        rows = [(self.table.rows[i], self._dist(query, self.table.rows[i].vector)) for i in best]
        if predicate is not None:
            # pgvector: filtering is applied AFTER the index scan
            rows = [pair for pair in rows if predicate(pair[0])]
            if iterative:
                # widen ef (up to hard cap) until enough rows match
                widened = ef
                trend = rows
                while len(trend) < k and widened < 512:
                    widened *= 2
                    best = self._search_layer(query, [self.entry_point or node], 0, widened)
                    trend = [
                        (self.table.rows[i], self._dist(query, self.table.rows[i].vector))
                        for i in best
                        if predicate(self.table.rows[i])
                    ]
                rows = trend
        rows.sort(key=lambda pair: (math.isnan(pair[1]), pair[1], str(pair[0].id)))
        return rows[: max(0, int(k))]

    def plan(self) -> str:
        return f"Index Scan using {self.table.name}_hnsw_idx"


# ---------------------------------------------------------------------------
# Recall measurement + the ANN health-check pgvector docs recommend
# ---------------------------------------------------------------------------


def recall(approximate: list[tuple[Row, float]], exact: list[tuple[Row, float]]) -> float:
    """Fraction of the exact top-k that the approximate search returned."""
    exact_ids = [row.id for row, _ in exact]
    approx_ids = [row.id for row, _ in approximate]
    if not exact_ids:
        return 0.0
    overlap = len(set(exact_ids) & set(approx_ids))
    return overlap / len(exact_ids)


def index_health_check(
    table: VectorTable,
    queries: list[list[float]],
    k: int = 5,
) -> dict[str, float]:
    """Monitor recall like the pgvector docs suggest: compare each index
    against exact search on the same queries (exact = SET LOCAL
    enable_indexscan = off)."""
    ivf = IVFFlatIndex(table, lists=max(1, len(table) // 5), seed=42).build()
    hnsw = HNSWIndex(table, m=8, ef_construction=64, seed=42).build()
    out = {}
    for nprobe in (1, 3, 5):
        scores = [
            recall(
                ivf.search(q, k=k, probes=nprobe),
                table.search(q, k=k),
            )
            for q in queries
        ]
        out[f"ivfflat_probes_{nprobe}"] = sum(scores) / len(scores)
    for ef in (16, 40):
        scores = [
            recall(hnsw.search(q, k=k, ef_search=ef), table.search(q, k=k)) for q in queries
        ]
        out[f"hnsw_ef_search_{ef}"] = sum(scores) / len(scores)
    return out


# ---------------------------------------------------------------------------
# Offline demo: `python pgvector_sim.py`
# ---------------------------------------------------------------------------


def _demo() -> None:
    a, b = [1.0, 2.0, 2.0], [2.0, 4.0, 1.0]
    print("topic 25 - pgvector semantics, miniaturised (offline demo)")
    print(f"operators on {a} vs {b}:")
    print(f"  <-> {l2_distance(a, b):.4f}   <=> {cosine_distance(a, b):.4f}"
          f"   <#> {negative_inner_product(a, b):.4f}")

    table, queries = build_corpus(seed=7)
    print(f"corpus: {len(table)} unit vectors, {table.dimensions} dims, 5 seeded clusters")
    print("no index yet ->", table.plan())
    q = queries[0]
    exact = table.search(q, k=5)
    ivf = IVFFlatIndex(table, lists=10, seed=42).build()
    hnsw = HNSWIndex(table, m=8, ef_construction=64, seed=42).build()
    print("with an index ->", ivf.plan())
    for label, got in [
        ("exact", exact),
        ("ivf probes=1", ivf.search(q, k=5, probes=1)),
        ("ivf probes=5", ivf.search(q, k=5, probes=5)),
        ("hnsw ef=40", hnsw.search(q, k=5, ef_search=40)),
    ]:
        ids = [row.id for row, _ in got]
        print(f"  {label:14} top-5 ids = {ids}")
    health = index_health_check(table, queries)
    print("recall vs exact (the docs' health check):")
    for key in sorted(health):
        print(f"    {key:<22} {health[key]:.3f}")
    filtered = hnsw.search(q, k=5, where={"cluster": 0}, ef_search=40)
    iterative = hnsw.search(q, k=5, where={"cluster": 0}, ef_search=40, iterative=True)
    print(f"WHERE cluster = 0 with ef_search=40: naive scan returns {len(filtered)},"
          f" iterative scan returns {len(iterative)}")
    print("plans - exact:", table.plan(), "| ivfflat:", ivf.plan(), "| hnsw:", hnsw.plan())


if __name__ == "__main__":
    _demo()

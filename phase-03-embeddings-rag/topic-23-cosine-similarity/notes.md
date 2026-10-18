# Topic 23 — Cosine similarity

## 1. Purpose of This Topic

Compute cosine similarity **by hand on two tiny vectors**, be able to say exactly **why cosine beats Euclidean distance** for comparing embeddings, translate that into code (pure Python, then numpy, then pgvector's operators), and calibrate a **threshold per corpus** instead of copy-pasting "0.8" from a blog post.

```text
Topic 22: embeddings are vectors (dense, direction-encoding)
                 ↓
Topic 23: geometry of comparing them — dot, angle, magnitude invariance
                 ↓
Topic 25: the SAME math becomes SQL operators  `<->`  `<=>`  `<#>`
```

**Done when:** you compute cosine similarity by hand on two tiny vectors and justify cosine over Euclidean distance.

---

## 2. Prerequisites

**Before: Topic 22**

- Embeddings as direction (unit sphere, normalisation), not as numbers-you-read
- Square roots and a pocket calculator's worth of arithmetic

---

## 3. The Three Formulas (on paper, tiny vectors)

For vectors **a** = (1, 2) and **b** = (2, 1):

```text
step 1  dot product      dot(a,b) = 1·2 + 2·1             = 4
step 2  lengths          |a| = sqrt(1+4) = sqrt(5)   |b| = sqrt(5)
step 3  cosine           cos(a,b) = 4 / (sqrt(5) · sqrt(5)) = 4/5 = 0.8
step 4  angle            θ = arccos(0.8) ≈ 36.87°
step 5  cosine DISTANCE  1 - 0.8 = 0.2        (what pgvector's <=> returns)
```

That reference computation is literally `HAND_COMPUTATION` in `cosine.py`, and the test `test_hand_computation_record_matches_lived_computations` proves the functions reproduce it — notes and code cannot drift apart.

Definitions you must carry:

```text
cosine similarity(a, b) = dot(a, b) / (||a|| · ||b||)      in [-1, 1]
cosine distance(a, b)   = 1 - cosine similarity            in [0, 2]
angle(a, b)             = arccos(similarity)               in [0, 180°]
L2 distance(a, b)       = sqrt(Σ (aᵢ - bᵢ)²)               (pythagoras)
inner product           = dot(a, b)  (unbounded)
```

Interpretation cheat-line: **1 = same direction, 0 = right angle (unrelated), -1 = opposite.** In text-search practice similarities cluster in [0, 1]; negatives come from models that emit signed embeddings.

Another hand example for 3-D (do it yourself once): a = (1,2,2), b = (2,4,1) → dot = 12, |a| = 3, |b| = √21, cos = 12/(3√21) ≈ 0.873. `test_higher_dimensions_hand_example` asserts exactly that arithmetic.

---

## 4. Why Cosine and Not Euclidean Distance (magnitude invariance)

### 4.1 The demo

Scale **a** = (1,2) by 1000 → (1000, 2000). The **direction** is unchanged; **only the magnitude moved**:

```text
cosine((1000,2000), (2,1))  = 0.8      — same as before  ✓ invariant
euclidean((1000,2000),(2,1)) ≈ 999.7   — huge           ✗ not invariant
```

Can a text written twice as *much* be "twice as far away" from its paraphrase? No — repetition and verbosity are not meaning. That is the entire argument.

### 4.2 Why magnitudes vary at all (and what they encode)

For embedding-model vectors, the norm often encodes **information-frequency effects**, not topic: shorter/rarer/token-heavy phrases, sentence length, and anisotropy of the model's output space all bias the length. Two known traps that magnitude invariance neutralises:

- a chunk padded with boilerplate gets stretched away from its topic,
- a very short query is usually shorter (smaller norm) than a chunk — Euclidean systematically favours long chunks as "far".

OpenAI's own guidance (embeddings docs): for their models, compare with **cosine**; if vectors are already unit length, dot and cosine are equal, which is why `pgvector` docs say: "If vectors are normalized to length 1 (like OpenAI embeddings), use inner product for best performance."

### 4.3 The elegant special case

For **unit** vectors:

```text
||a - b||² = ||a||² + ||b||² - 2·dot(a,b) = 1 + 1 - 2·cos(a,b) = 2 - 2·cos(a,b)
```

So the Euclidean distance between normalised vectors is a **monotonic function of cosine similarity** — the two produce the *same ranking* (asserted twice in the tests: `test_unit_vectors_euclidean_vs_chord_identity`, `test_ranking_by_euclidean_matches_cosine_on_unit_vectors`). This is worth saying out loud in an interview: "cosine vs Euclidean is not a quality debate; it is a magnitude debate, and on the unit sphere they rank identically."

Euclidean *has* legitimate non-embedding uses (raw feature spaces where scale is meaningful: image RGB histograms, coordinates in 2-D plots). The RAG default stays cosine because that is what embedding models train for.

### 4.4 One caution

Cosine "distance" is not a metric in the triangle-inequality sense — don't build geometry-dependent algorithms (certain clustering proofs) on it. For ordering results it is perfectly well-behaved, which is all retrieval needs.

---

## 5. In Code: numpy first, then pgvector operators

### 5.1 numpy (the workstation layer)

`np_cosine_similarity_matrix(matrix, query)` does the whole corpus-vs-query comparison in one matrix product — one dot per row vs a Python loop. NaN rows = zero vectors, kept deliberately (next section). `np_rank_by_similarity` returns the best-k row indices, NaN excluded. Deterministic seed used in tests (`default_rng(7)`) because reproducibility beats randomness for learning fixtures.

### 5.2 pgvector — the same math as SQL operators

| pgvector | meaning | module mirror | notes |
|---|---|---|---|
| `<->` | **L2 (Euclidean) distance** | `l2_distance` / `euclidean_distance` | classic pythagoras |
| `<=>` | **cosine distance** = 1 − cosine sim | `cosine_distance` | the RAG default |
| `<#>` | **negative inner product** | `negative_inner_product` | see below |
| `<+>` | L1 (taxicab) distance | — (added pgvector 0.7) | |

Why is `<#>` **negative**? Because Postgres index scans walk operator results in **ASC** order: "most similar" must be the *smallest* value like a distance. Negating flips big-dot-product (similar) into very-negative (scans first). To recover the inner product: `(a <#> b) * -1`.

Corresponditions to commit to memory:

```text
OpenAI-style pipeline                     pgvector
------------------------------------------------------------
cosine similarity  0.91      ⇔           1 - (embedding <=> query) = 0.91
best rows by ASC distance                ORDER BY embedding <=> query LIMIT 5
normalized vectors, dot ranking          ORDER BY embedding <#> query LIMIT 5
```

Zero vectors: pgvector's cosine distance of a zero vector is **NaN**, and zero vectors are skipped by cosine indexes entirely. `cosine.py` mirrors that (`float("nan")`) and `test_zero_vector_is_nan_like_pgvector` pins the behaviour — don't "fix" it into a 0.0; parity with the real database keeps your local reasoning honest.

Failed-length arguments raise `ValueError`, which is what a real `vector(768)` column does when you insert a 512-d vector: dimension mismatches are errors, never silent coercion (Topic 25's table enforces the same).

---

## 6. Threshold Picking — No Universal Number; Tune Per Corpus

The question every RAG team asks in week 2: "what cosine score is 'good enough' to send to the LLM?" Wrong question, right instinct. The facts:

1. **Scores are model-relative, not absolute.** The same English pair can score 0.55 on one model and 0.8 on another; similarity *ranges* differ per model (document it when you switch). Folk numbers like "0.75+" are folklore, not physics. A baseline to know about: some legacy models scored ~0.7 for *unrelated* sentence pairs, so a fixed 0.5 threshold would admit pure noise.
2. **Scores shift with corpus shape**, not only with the model — mix in headings, tables, code, or a non-English spillover and the whole distribution moves. `test_thresholds_are_per_corpus_not_universal` shows two corpora where each has a *perfect* threshold (F1 = 1.0) and each other's threshold is blind (recall 0 / precision collapse).
3. **Precision and recall trade through the same knob.** Raise the threshold → what you keep is trustworthy but you drop the gold; lower it → you catch gold plus junk (the "empty answer" vs "wrong answer" failure families). `test_higher_threshold_raises_precision_lowers_recall` pins the direction.

### 6.1 The offline calibration procedure (implemented as `sweep_thresholds`)

1. Label a batch: pairs `(similarity, is_relevant)` from your golden set — real queries against known-good and known-irrelevant chunks (Topic 22 §6).
2. Sweep candidate thresholds; for each compute precision / recall / F1 (`ThresholdRow`).
3. Pick on the trade you need: F1's argmax (`best_f1_threshold`) as the starting point, then slide toward precision if wrong answers cost more than empty ones (support), toward recall if the user should see *something* (agent retrieval), and confirm with the LLM-side eval later.
4. Re-check after: model switch, chunk-size change, big corpus growth. The threshold is **configuration for a point in time**, not a constant.

`calibration_report()` prints the sweep table; the demo notebook renders it.

---

## 7. Implementation Walkthrough — `cosine.py`

Layer by layer, all pure-math, offline, deterministic:

- `HAND_COMPUTATION` — the worked (1,2)×(2,1) example as data, so tests assert *your notes*.
- Pure Python: `dot_product`, `magnitude`, `cosine_similarity`, `cosine_distance`, `angle_degrees` (with the pre-`acos` clip that guards floating-point overshoot), `euclidean_distance`, `negative_inner_product`, `l2_distance` alias.
- numpy: `np_cosine_similarity_matrix` (full-batch), `np_rank_by_similarity` (top-k, NaN-free).
- Thresholds: `ThresholdRow`, `sweep_thresholds` (sorted, deterministic), `best_f1_threshold` (ties → lower threshold), `calibration_report`.

34 pytest tests, both hand-arithmetic and property-based.

---

## 8. Pitfalls

1. **Comparing unnormalised vs normalised vectors** — mixed batches break every identity of §4.3; normalise per store.
2. **Zero-vector crash instead of NaN parity** — guard like pgvector does (or exclude zero vectors at ingestion, like pgvector's cosine index does).
3. **Copy-pasting a threshold from another codebase** — recalibrate on your corpus (§6), and re-check on every model/chunking change.
4. **Using `<=>` values as "confidence"** — they order candidates; they do not certify the answer is right. Reranking/eval (later topics) cover trust.
5. **Expecting cosine < 0 on all-dissimilar document pairs** — with several embedding families, unrelated text still scores mildly positive (the vector spaces are not isotropic); let your own §6 sweep reveal the baseline.
6. **Forgetting `1 - sim` direction in SQL** — remember `<=>` returns the *distance* (lower = closer); subtract from 1 only for display.

---

## 9. Exercises

1. By hand (no calculator beyond squares/roots): a=(3,4), b=(4,3). Compute dot, magnitudes, cos, angle, cosine distance. Check with `python -c` from this folder.
2. Show (paper) that for unit vectors cosine distance and L2 ordering coincide, then verify with `test_ranking_by_euclidean_matches_cosine_on_unit_vectors`-style code of your own on five random unit vectors (`default_rng(seed)`).
3. Build a labelled mini-dataset: 6 relevant + 6 irrelevant (q, text) pairs about *your day job's domain*; sweep 20 thresholds; report best F1. What threshold did you get, and where did it surprise you?
4. Compute `euclidean((5,12),(9,15))` mentally — then check that scaling both by 4 multiplies it by 4 while cosine doesn't move.
5. Explain in one paragraph why `<#>` is negated in Postgres. (Answer pattern: ASC index scans; similar ⇒ bigger dot ⇒ *more* negative ⇒ scanned first.)

---

## 10. Done-When Checklist

- [x] I computed cos((1,2),(2,1)) = 0.8, angle ≈ 36.87°, distance 0.2 by hand.
- [x] I can justify cosine over Euclidean with the scaling argument and the unit-sphere equivalence.
- [x] My code has the pure-Python, numpy, and pgvector-operator layers, each tested.
- [x] I know thresholds are per-corpus (and per-model), and I can run a sweep to pick one.

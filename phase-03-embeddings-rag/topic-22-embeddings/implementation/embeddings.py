"""Topic 22 - Embeddings: text -> dense vectors, meaning as geometry.

This module is a *toy* embedding laboratory. It does not call any real
embedding API (those need network keys); instead it hand-writes two kinds of
embedders so you can watch the geometry behave:

1. ``CooccurrenceEmbedder`` - meaning from "the company a word keeps".
   Words that appear next to similar words get similar vectors. This is the
   count-based idea behind the modern embedding models described in
   Jay Alammar's "The Illustrated Word2vec" and Weaviate's
   "Vector Embeddings Explained" (both are the syllabus sources).

2. ``HashingEmbedder`` - a deterministic feature-hashing embedder over word
   tokens and character 3-grams. It reacts to *letters* (so "run" and
   "running" land near each other through shared trigrams) but it has NO
   semantics: it only knows what the strings look like. It exists to expose
   dimensions/normalisation/truncation mechanics.

Geometry helpers live here too (``cosine_similarity``, ``l2_normalize``).
Topic 23 studies cosine similarity in its own right; this module needs just
enough of it to prove that "similar meaning lands nearby".

Everything is offline and deterministic: the only "hashing" is via hashlib
(NOT Python's built-in ``hash()``, whose value is salted per process and
would make runs non-reproducible).
"""

from __future__ import annotations

import hashlib
import math
import re
import statistics
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tokenisation + geometry helpers
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


def tokenize(text: str) -> list[str]:
    """Lowercase and split on anything that is not a letter/digit/apostrophe."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t]


def l2_normalize(values: list[float]) -> list[float]:
    """Scale a vector to length 1 (all model outputs sit on the unit sphere)."""
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0.0:
        return list(values)  # zero vector stays zero; nothing to scale
    return [v / norm for v in values]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """cos(theta) between two vectors; 1.0 = same direction, 0 = orthogonal.

    Defined here as a private helper; Topic 23 is the deep dive.
    """
    if len(a) != len(b):
        raise ValueError(f"different vector dimensions {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return float("nan")  # pgvector parity: zero vectors -> NaN cosine
    return dot / (na * nb)


def most_similar(
    query: list[float],
    candidates: dict[str, list[float]],
) -> list[tuple[str, float]]:
    """Rank candidates by cosine similarity to ``query`` (best first)."""
    scored = [(name, cosine_similarity(query, vec)) for name, vec in candidates.items()]
    nan_free = [s for s in scored if not math.isnan(s[1])]
    return sorted(nan_free, key=lambda s: (-s[1], s[0]))


def storage_bytes(dimensions: int) -> int:
    """Bytes for one float32 embedding, pgvector-style accounting.

    pgvector README: a ``vector`` takes ``4 * dimensions + 8`` bytes; each
    element is a single-precision float and vectors may hold up to 16,000
    dimensions. The +8 is the type header.
    """
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    return 4 * dimensions + 8


# ---------------------------------------------------------------------------
# 1. Cooccurrence embedder: meaning from "the company a word keeps"
# ---------------------------------------------------------------------------


@dataclass
class CooccurrenceEmbedder:
    """Count-based embeddings with PPMI weighting over a window of words.

    Give it a small corpus of sentences. For every word pair that occurs
    within ``window`` tokens of each other in a sentence, we count the pair.
    We then replace raw counts with PPMI (positive pointwise mutual
    information) so that "explains away" pairs that co-occur just because
    both words are frequent. Each word's vector is its PPMI profile over
    the other words, L2-normalised.

    Phrase embedding = mean of known word vectors, re-normalised. Words
    outside the vocabulary contribute nothing (documented limitation: real
    models generalise to unseen words via subwords).
    """

    corpus: list[str]
    window: int = 2
    vocab: dict[str, list[float]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.window < 1:
            raise ValueError("window must be >= 1")
        sentences = [tokenize(s) for s in self.corpus]
        sentences = [s for s in sentences if s]
        vocab = sorted({t for s in sentences for t in s})
        index = {w: i for i, w in enumerate(vocab)}
        counts: dict[tuple[int, int], float] = {}

        for s in sentences:
            for i, w in enumerate(s):
                for j in range(max(0, i - self.window), min(len(s), i + self.window + 1)):
                    if j == i:
                        continue
                    key = (index[w], index[s[j]])
                    counts[key] = counts.get(key, 0.0) + 1.0

        total = sum(counts.values())
        unigram = [0.0] * len(vocab)
        for (i, _), c in counts.items():
            unigram[i] += c
        grand = sum(unigram) or 1.0

        rows = [[0.0] * len(vocab) for _ in vocab]
        for (i, j), c in counts.items():
            pmi = math.log2((c / total) / ((unigram[i] / grand) * (unigram[j] / grand)))
            rows[i][j] = max(0.0, pmi)
        for i in range(len(vocab)):
            self.vocab[vocab[i]] = l2_normalize(rows[i])

    def embed_word(self, word: str) -> list[float]:
        """Vector for a single known word; unknown words -> zero vector."""
        return self.vocab.get(word.lower(), [0.0] * self.dimensions)

    def embed_text(self, text: str) -> list[float]:
        """Mean of known word vectors, L2-normalised (like mean pooling)."""
        known = [self.vocab[w] for w in tokenize(text) if w in self.vocab]
        if not known:
            return l2_normalize([0.0] * self.dimensions)
        dims = self.dimensions
        mean_vec = [sum(vec[d] for vec in known) / len(known) for d in range(dims)]
        return l2_normalize(mean_vec)

    @property
    def dimensions(self) -> int:
        """Vocabulary size: one axis per known word (fully interpretable)."""
        return len(self.vocab)


# A tiny workshop corpus. Dogs cluster with loyalty/playfulness actions,
# cats with naps, finance with markets. Nothing here "knows" that a puppy is
# a young dog - the co-occurrence statistics make them neighbours.
EXAMPLE_CORPUS = [
    "the dog is loyal and friendly",
    "a loyal dog protects the family",
    "a faithful dog guards the house",
    "the playful puppy wags its tail",
    "the puppy chased the ball happily",
    "puppies love to play and run",
    "dogs bark at strangers loudly",
    "a good dog sits on command",
    "the cat naps on the warm windowsill",
    "a sleepy cat purrs softly",
    " cats quietly watch the birds outside",
    "the kitten played with a ball of yarn",
    "cats and dogs are common family pets",
    "the farmer feeds the cow every morning",
    "sheep graze in the green field",
    "the horse runs across the paddock",
    "the stock market rallied on strong earnings",
    "investors bought shares before the rise",
    "interest rates rose and lending slowed",
    "the bank lent money to small businesses",
    "bond yields climbed after the report",
    "the fund bought bonds and shares",
    "markets fell as inflation climbed",
    "traders watched the market closely",
    "every puppy grows into a young dog",
    "the puppy is a loyal young dog",
    "a playful puppy becomes a loyal family dog",
    "the big dog watches over the little puppy",
]


# ---------------------------------------------------------------------------
# 2. Hashing embedder: dimensions + normalisation + truncation mechanics
# ---------------------------------------------------------------------------


def _stable_int(s: str) -> int:
    """Deterministic integer from a string (process-independent)."""
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


@dataclass
class HashingEmbedder:
    """Signed feature hashing over word tokens and character 3-grams.

    Every feature is hashed to an index and a sign; raw counts are summed,
    then the result is L2-normalised.

    This embedder is honest about what it is NOT: it has no idea what words
    MEAN. Two texts are near each other only when they share letters and
    tokens. We still use it because it makes the *mechanics* of embedding
    APIs concrete and testable offline:

    - you choose ``dimensions`` up front (a real API does this for you)
    - output is always on the unit sphere after normalisation
    - you can slice off trailing dimensions (in the style of Matryoshka
      embedding models, e.g. OpenAI text-embedding-3, which support
      ``dimensions=256/1024/3072``) and watch recall blur
    - collisions are the price of a fixed-width space
    """

    dimensions: int = 64

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")

    def _bump(self, vec: list[float], feature: str, weight: float = 1.0) -> None:
        idx = _stable_int(feature) % self.dimensions
        sign = 1.0 if _stable_int("sign:" + feature) % 2 == 0 else -1.0
        vec[idx] += sign * weight

    def embed(self, text: str) -> list[float]:
        """Text -> dense signed-hashed vector (unit length)."""
        vec = [0.0] * self.dimensions
        tokens = tokenize(text)
        for tok in tokens:
            self._bump(vec, "w:" + tok)
            padded = f"^{tok}$"
            for i in range(len(padded) - 2):
                self._bump(vec, "g:" + padded[i : i + 3], weight=0.5)
        return l2_normalize(vec)


def truncate(vector: list[float], dimensions: int) -> list[float]:
    """Keep the first ``dimensions`` coordinates, then re-normalise.

    Matryoshka-style truncation: the leading coordinates of models trained
    this way carry the coarsest ("most useful") information, so recall
    degrades gracefully rather than collapsing. After slicing you MUST
    re-normalise - a sliced vector is no longer on the unit sphere.
    """
    if dimensions <= 0:
        raise ValueError("dimensions must be positive")
    if dimensions > len(vector):
        raise ValueError(
            f"cannot truncate to {dimensions} dimensions from {len(vector)}"
        )
    return l2_normalize(vector[:dimensions])


def neighbor_stability(query: list[float], candidates: dict[str, list[float]], top_k: int, dimensions: int) -> int:
    """How many of the top-k neighbours survive a Matryoshka-style cut?

    ``query`` and every candidate get truncated to ``dimensions`` floats
    (re-normalised), then re-ranked; we count how many of the original
    top-k names are still in the reduced top-k. This is exactly the
    "recall blurs gracefully" behaviour that models such as OpenAI's
    text-embedding-3 family rely on when you pass a smaller ``dimensions``.
    """
    full = {name for name, _ in most_similar(query, candidates)[:top_k]}
    reduced_query = truncate(query, dimensions)
    reduced_candidates = {name: truncate(vec, dimensions) for name, vec in candidates.items()}
    reduced = {name for name, _ in most_similar(reduced_query, reduced_candidates)[:top_k]}
    return len(full & reduced)


# ---------------------------------------------------------------------------
# 3. "Benchmark leaders != your domain": an offline golden-set harness
# ---------------------------------------------------------------------------


def contrastive_score(
    embed_fn,
    query: str,
    positives: list[str],
    negatives: list[str],
) -> float:
    """Mean similarity to positives MINUS mean similarity to negatives.

    A stand-in for the small golden evaluation set you should build before
    trusting any embedding model:

        50-200 (query, known-good chunk) pairs FROM YOUR DATA
        + the same number of known-bad distractors.

    A leaderboard winner (MTEB style) means nothing unless this number,
    measured on your domain, beats the alternative you already run.
    """
    q_vec = embed_fn(query)
    pos_scores = [cosine_similarity(q_vec, embed_fn(text)) for text in positives]
    neg_scores = [cosine_similarity(q_vec, embed_fn(text)) for text in negatives]
    pos_scores = [s for s in pos_scores if not math.isnan(s)]
    neg_scores = [s for s in neg_scores if not math.isnan(s)]
    pos_mean = statistics.mean(pos_scores) if pos_scores else 0.0
    neg_mean = statistics.mean(neg_scores) if neg_scores else 0.0
    return pos_mean - neg_mean


# ---------------------------------------------------------------------------
# Offline demo: `python embeddings.py`
# ---------------------------------------------------------------------------


def _demo() -> None:
    emb = CooccurrenceEmbedder(EXAMPLE_CORPUS, window=2)
    print("topic 22 - embeddings: meaning as geometry (offline demo)")
    print(f"cooccurrence embedder over EXAMPLE_CORPUS: {emb.dimensions}-d vectors")
    print("(one axis per vocab word; similar words keep similar company)")
    for phrase in ["a loyal young dog", "the playful puppy", "bond yields climb"]:
        q = emb.embed_text(phrase)
        best = most_similar(q, emb.vocab)[:3]
        print(f"embed({phrase!r}) nearest vocab words: "
              + ", ".join(f"{name}={score:.3f}" for name, score in best))
    meta = {"dog": emb.embed_word("dog"), "loyal": emb.embed_word("loyal"),
            "bank": emb.embed_word("bank"), "yields": emb.embed_word("yields")}
    print(f"cos(dog, loyal) = {cosine_similarity(meta['dog'], meta['loyal']):.3f}"
          f"   cos(dog, yields) = {cosine_similarity(meta['dog'], meta['yields']):.3f}")

    hashing = HashingEmbedder(dimensions=64)
    full = hashing.embed("quarterly revenue report")
    unit = math.isclose(math.sqrt(sum(v * v for v in full)), 1.0)
    print(f"hashing embedder: 64-d by construction, unit length = {unit}")
    for dims in (16, 32, 64):
        cut = truncate(full, dims)
        print(f"  slice to {dims:>2}-d and re-normalise, still unit: "
              f"{math.isclose(math.sqrt(sum(v * v for v in cut)), 1.0)}")

    query = emb.embed_text("a loyal dog")
    kept = neighbor_stability(query, emb.vocab, top_k=5, dimensions=8)
    print(f"matryoshka cut to 8 dims: {kept}/5 of the top-5 word neighbours survive")
    print(f"storage_bytes(1536) = {storage_bytes(1536)} bytes/row (pgvector accounting)")


if __name__ == "__main__":
    _demo()

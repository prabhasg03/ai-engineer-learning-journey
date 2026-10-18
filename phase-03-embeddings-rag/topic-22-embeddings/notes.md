# Topic 22 — Embeddings

## 1. Purpose of This Topic

Turn text into a **dense vector** — a fixed list of floats — so that *meaning becomes geometry*: similar meanings sit near each other in the vector space, regardless of the exact wording. When you can explain that in your own words and pick a model + dimension count **knowingly** (knowing the trade-offs), this topic is done.

This topic opens Phase 3, the RAG phase:

```text
Topic 2: text -> tokens -> vectors
                 ↓
Topic 22: text -> EMBEDDINGS (dense vectors where geometry = meaning)
                 ↓
Topic 23: measuring similarity (cosine)   Topic 24: what we embed (chunks)
                     ↓                          ↓
                 Topic 25: where we keep them (pgvector)
                     ↓
Everything downstream in Phase 3 (retrieval pipelines) rests on these four.
```

**Done when:** you explain meaning-as-geometry in your own words and choose an embedding model + dimensions knowingly.

---

## 2. Prerequisites

**Before: Topic 2**

You need:
- Words to token IDs to vectors (the pipeline from Topic 2)
- Basic vector math: dot product, vector length (Topic 23 sharpens this)
- Nothing about neural networks in detail — the *behaviour* of embeddings matters here, not their training internals

---

## 3. What an Embedding Is

An embedding is a function `text -> list[float]` of fixed length (the **dimensions**), e.g. 1536 numbers. The list is not interpretable digit-by-digit; what matters is the **arrangement**: two texts that mean similar things get vectors that point in similar directions.

Two eras of how those vectors came to be (both syllabus sources tell this story):

1. **Count-based classics.** Distribute a word by "the company it keeps." Count which words appear around it, build a huge sparse vector per word, optionally weight with PPMI ("positive pointwise mutual information" — so common-but-boring words like *the* stop dominating), then compress (SVD) — Firth's "you shall know a word by the company it keeps", made computational. The `CooccurrenceEmbedder` in `implementation/embeddings.py` hand-writes exactly this for a tiny corpus.

2. **Learned dense embeddings.** Word2Vec (skip-gram/CBOW) trains a small network on the *prediction task itself*: "given a word, predict its neighbours" (or reverse). No one inspects the hidden layer; that hidden layer **is** the embedding. Because the same idea can be expressed with different words, training forces synonyms into nearby positions — geometry encodes the regularities of usage. Famous consequence: `vector("king") - vector("man") + vector("woman") ≈ vector("queen")` — relationships become directions. GloVe converts global co-occurrence statistics into vectors directly; fastText adds sub-word parts so *unseen* strings still get vectors; and modern transformer-based models (BERT family, then every embedding API: OpenAI, Cohere, Google, open-weights BGE/E5/GTE/nomic) produce **contextual** embeddings, where a text's vector depends on all of it, not just isolated tokens.

One distinction Alammar draws that you must carry into RAG: **contextual vs static.** In Word2Vec, "bank" has one vector whether you wrote about finance or rivers. Transformer models give each occurrence a different representation shaped by its surroundings. Embedding models usually embed whole sentences/passages at once, so the "same word, different sense" problem is softened — but it re-appears as "same sentence, different document topic," which is why **chunking** (Topic 24) matters.

### The mental model to make your own

> A good embedding function is a map from a huge discrete space (all texts) into a small continuous one (a unit sphere), drawn so that *semantic* closeness becomes *geometric* closeness, and *irrelevant* differences (synonyms, punctuation, ordering) are smoothed away.

That single sentence is the bullet "text → dense vector; semantics as geometry". Everything else in this topic is about knowing **what you traded** to get that map.

---

## 4. Similar Meaning Lands Nearby — Regardless of Wording

The property you are buying is **paraphrase invariance**:

- "How do I reset my password?" and "I can't log in, my password doesn't work" share almost no surface words, yet an embedding model should place them a few degrees apart.
- Meanwhile "reset password" vs "reset billing address" share lots of surface words (:reset, :address) but must land further apart.

The `CooccurrenceEmbedder` demonstrates the mechanism offline. In `test_embeddings.py`:

- `'the puppy is loyal'` sits closer to `'a dog is faithful'` than to `'the stock market rallied'` — *no* words in common with the first pair except glue words; the geometry comes from co-occurrence statistics.
- `test_hashing_shared_trigrams_pull_run_and_running_together` shows the *other* pull: shared character trigrams make `run`/`running` neighbours even with zero training. Useful, but it is **morphology, not semantics** — `test_hashing_is_morphology_not_semantics` proves a hashing embedder cannot relate "puppy" and "pet" if the letters differ.

That pair of tests is the topic's honesty check: a real embedding model is doing (1) — usage-derived meaning — at model scale, and you cannot get it from string tricks.

Worked example using our tiny corpus (real numbers, from the demo notebook):

```text
embed("the puppy is loyal")       ~ direction of {puppy, loyal, young, dog…}
embed("a dog is faithful")        ~ direction of {dog, faithful, guards, house…}
embed("the stock market rallied") ~ direction of {stock, market, rallied, earnings…}

cos(query, dog-faithful)  ≈ 0.83   (high: same topic, different words)
cos(query, finance-rally) ≈ 0.1x   (low: unrelated)
```

(Your numbers depend on corpus and window; run the notebook and read the printed table.)

---

## 5. Models, Dimensions, Normalisation

### 5.1 Models you will actually encounter

| Model | Default dims | Know it as |
|---|---|---|
| OpenAI `text-embedding-3-small` | 1536 | cheap default; supports `dimensions` parameter (Matryoshka) |
| OpenAI `text-embedding-3-large` | 3072 | higher recall ceiling; dims 256/1024/3072 supported |
| OpenAI `text-embedding-ada-002` | 1536 | legacy; no `dimensions` parameter |
| Cohere embed v3/v4 (english/multi) | 1024 (v3) | `input_type` (search_document vs search_query) matters |
| sentence-transformers `all-MiniLM-L6-v2` | 384 | local, tiny, fast; the "hello world" of embeddings |
| BAAI `bge-*`, intfloat `e5-*` | 768 / 1024 | strong open-weights; prefixes ("query: ", "passage: ") matter |
| Nomic embed text v1.5 | 768 | Matryoshka-style dims 64..768 |
| Google `text-embedding-004` | 768 | dims parameter |

Check the provider's docs — this table ages, the *categories* do not: **dimensions, cost, context window (max input length), Matryoshka support, prefixes, language coverage.**

Day-1 practicalities of calling a real embedding API, worth knowing before the first integration:

- **Batch your inputs.** Every embedding API takes a *list* of texts per request (100s–1000s at a time, each provider different); one-text-per-request burns latency and money for nothing.
- **Cost is per input token and cheap in absolute terms** — roughly two orders of magnitude below generation pricing; corpus re-embedding is billed once per model switch, which is why the golden-set decision (§6) happens *before* the bulk job.
- **Cache aggressively**: key results by (model, dimensions, content hash) so unchanged chunks are never re-embedded — the same key the Topic 26 upsert story uses.
- **Store provenance with every vector** — `model_name`, `dimensions`, and a text hash column. When you switch models (§6 caveat 4), you need to know exactly which rows are stale.
- **Respect the input window**: chunk to your biggest model's limit minus margin; texts that overflow are silently truncated, not rejected (Topic 24's window-limits reason).

The syllabus point is not the table; it is that all these knobs are *knowable* and each one has a reason:

### 5.2 Dimensions — what they cost and what they buy

- Storage: pgvector accounting says a float32 `vector` takes `4 * dimensions + 8` bytes. One million 1536-d vectors ≈ **6.15 GB** of pure vector before any index overhead; a 384-d MiniLM row is 1.5 KB. `storage_bytes`/`test_one_million_1536_dim_vectors_are_gigabytes` code exactly this arithmetic.
- Recall: more dimensions = finer distinctions ("higher resolution"), diminishing returns after model-dependent sweet spots.
- Latency: distance computations are O(dims); ANN index memory grows with dims too.
- **Matryoshka / truncation:** several modern models are trained so the first N coordinates carry the coarsest, most useful information. OpenAI `dimensions=256` and Nomic's 64..768 range rely on this: a 1536-d store can be cut to 256 (2 KB/row) and still rank quite well — slightly blurrier. `truncate()` in the module reproduces the mechanism, and `neighbor_stability()` measures how many top-k neighbours survive a cut. Rule from the tests: after slicing you MUST re-normalise (`test_truncating_without_renormalising_breaks_the_unit_sphere`).
- Chunk count dominates: total memory = rows × (per-row vector + per-row index overhead). Fewer, bigger chunks = cheaper but coarser (this is exactly Topic 24's trade-off).

### 5.3 Normalisation — the unit sphere

Embedding APIs output vectors that are **already L2-normalised** (length exactly 1) — verify this on day 1 of any integration; several models historically didn't and downstream behaviour silently changed. On the unit sphere:

```text
cosine(a, b) = dot(a, b)          # the convenient special case
```

so providers can rank by plain dot products and One distance function family serves everyone. Consequences:

- Similarity is bounded [-1, 1]; distance in [0, 2].
- For unit vectors, ranking by cosine and ranking by Euclidean distance agree (prove in Topic 23) — so if your vector DB offers either, orderings match.
- If you compute anything yourself, you must normalise *every* vector the same way; mixing normalised and raw vectors produces scores that are not comparable.
- `l2_normalize()` + the "always unit length" tests encode this invariant.

---

## 6. Caveat: Benchmark Leaders ≠ Your Domain

The MTEB-style leaderboards rank embedding models on a big pot of average scores across tasks and datasets. Four reasons a leaderboard number does not transfer:

1. **Averages hide your slice.** A model averaging 62 might be mediocre on your kind of text (advisory documents, rare domain jargon, short support tickets, non-English) while a less-famous model is excellent on it.
2. **Metrics are proxies.** Leaderboards score retrieval benchmarks with labelled pairs from *their* corpora; your queries are different shapes (they may be questions, error messages, part numbers).
3. **Static snapshots.** Leaderboards churn; the ranking you memorised is last quarter's.
4. **Score ⇏ produce.** The winning model may cost 10×, be 5× slower, need 4 GB of positional GPU memory, or have licensing constraints.

What to do instead — do this before every model choice, and it is the same offline procedure `contrastive_score()` implements:

1. Collect a **small golden set from your data**: 50–200 (query, known-relevant text) pairs plus known-irrelevant distractors.
2. For each candidate model measure: mean similarity to positives **minus** mean similarity to negatives (contrastive score), plus recall@k on realistic query shapes.
3. Compare models *and* your current solution on that score. Only then look at cost/latency/dimensions.
4. Remember **switching models invalidates old vectors** — embeddings from different models live in incompatible spaces; a migration means re-embedding the whole corpus and re-building indexes. Store `model_name + dimensions` alongside every vector (Topic 25 rows, Topic 26 upserts).

The two `test_contrastive_score…` tests show the punchline on a toy scale: on the *pets/finance* domain the PPMI embedder beats the letter-machine; on *string-overlap* queries the letter-machine wins. Ranked "better overall" is meaningless; *stronger on your corpus* is the number.

---

## 7. Implementation Walkthrough — `topic-22-embeddings/implementation/embeddings.py`

One module, four honest parts:

- `tokenize`, `l2_normalize`, `cosine_similarity`, `most_similar` — minimal geometry (Cosine's deep dive is Topic 23).
- `CooccurrenceEmbedder` — PPMI-weighted co-occurrence vectors over `EXAMPLE_CORPUS` (~28 sentences about dogs/cats/farm/finance). Its `vocab`-sized rows are interpretable: each column of a word's vector is "how strongly that word co-occurs with this partner", so `embed_text` = mean pooling of known words (like the mean-pooling of sentence embeddings).
- `HashingEmbedder` — deterministic signed feature hashing (via `hashlib.sha256`, **not** built-in `hash()`, which is process-salted and would break reproducibility) over word tokens + char 3-grams. Settings: `dimensions` (your knob), weight 1.0 for words, 0.5 for trigrams.
- `truncate` / `neighbor_stability` / `contrastive_score` / `storage_bytes` — the Matryoshka and benchmark-caveat harnesses.

Run the demo notebook for the currently printed story; run `click-to-run.bat` (pytest, 31 tests) offline. You never need a network: this module exists so you can *watch* the properties that real models give you for free.

---

## 8. Pitfalls

1. **Judging a model from one lucky query** — no; use the golden set.
2. **Switching models without re-embedding** — old and new vectors are incompatible geometries; distances between models are numerical noise.
3. **Truncating without renormalising** — sliced vectors have norm < 1, so cosine-vs-cosine comparisons break; always `truncate` + re-normalise (tested).
4. **Assuming cos-similarity = intended relevance** — high similarity only means "distributionally similar"; the *relevance* of a chunk to a question involves intent, novelty; Topic 24 (chunking) + rerankers address part of the gap.
5. **Comparing words with a subword-free model in uppercase/typo form** — case/typo normalisation varies per model; know your tokenizer's normalisation.
6. **Assuming hashing/char-trigram similarity = semantic similarity** — the module is built for you to run into this (`test_hashing_is_morphology_not_semantics`): hashing "puppy" relates only to strings that share letters.
7. **Ignoring dimension cost in planning** — dims × rows is your memory bill; 1536-d floats cost ~6.1 KB/row, 384-d just 1.5 KB; Matryoshka truncation and quantization (Topic 25's `halfvec`) are the escape hatches.

---

## 9. Exercises

1. Add 5 sentences to `EXAMPLE_CORPUS` (e.g. pets + 'grooming') and re-run the two similarity tests by hand? Verify: do they still hold? What does it mean for your golden-set confidence?
2. Change `HashingEmbedder`'s `dimensions` to 8 and note which tests now fail. Explain the collision-vs-compression trade-off.
3. Write a golden set of 10 pairs relevant to *your* domain/work and run `contrastive_score` by plugging in a real API offline (or imagine the replaced embedder). What hurts most — positives not scoring high, or negatives scoring equally high?
4. Truncate a 128-d fake-embedding to 6, 12, 32 dims and tabulate `neighbor_stability` — when does the cut become unacceptable?
5. Explain to your notes (2 paragraphs): "words/sentences as geometry," and one sentence every time you'd double-check dimensions before embedding 1M docs.

---

## 10. Done-When Checklist

- [x] I can draw "text → dense vector" and explain *semantics as geometry* without notes.
- [x] I have run a paraphrase-invariance demo (no shared words, high score; shared surface, low score).
- [x] I know the model table's categories (dimensions, cost, context window, Matryoshka support, prefixes, languages) and can choose one for a concrete project.
- [x] I know why a leaderboard winner can fail on my domain and what the 50-200-pair golden set checks instead.

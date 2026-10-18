# Topic 24 — Chunking

## 1. Purpose of This Topic

Chunk a real document **three different ways** and be able to articulate the granularity trade-off of each. When embeddings meet simple chunkers, the most common quality catastrophe is not choosing the wrong strategy, but treating whatever slicing strategy emerged as above question. This topic gives you the families, their failure modes, and the measuring stick to compare them honestly.

```text
Topic 22-23: embeddings + cosine  (how you FIND things)
                     ↓
Topic 24: chunking                (what the finder works with)
                     ↓
retrieval quality = chunking × embedding × search
   (fix one downstream stage in isolation and the ceiling stays at the chunk)
```

**Done when:** you chunk a sample document three different ways and articulate the granularity trade-off of each.

---

## 2. Prerequisites

**Before: Topic 22**

- Embedding a *piece* of text vs embedding a *document*
- Cosine comparison of query vs chunk (Topic 23)

---

## 3. What Chunking Is and Why You Split

**Chunking** = partitioning a document into the pieces you will embed and retrieve. Retrieval does not index a 200-page PDF; it indexes chunks. You split for two reasons, and both matter:

1. **Window limits.** An embedding model has a max input length (e.g. 512 or 8,192 tokens). Everything past it is silently truncated — that is "silent failure": your tail-anchored content (tables in appendices, closing clauses of policies) vanishes without raising an error.
2. **Retrieval granularity.** Even with a giant window, one vector per document makes queries mushy: ten topics average into one point. Smaller units = sharper matches = better precision. Sharper matches also help the LLM: short relevant context beats long diluted context (Topic 27's ordering problems start here).

Chunking is, in Pinecone's phrase, "the single highest-leverage quality decision in RAG": it's the preprocessing that decides what the vector database *contains*, and no downstream fix reconstitutes information you sliced away at the seams.

---

## 4. Fixed-size Pitfalls: Mid-sentence and Mid-table Cuts

The default approach — chunk every 200 characters — fails in exactly the joints the sources call out:

- **Mid-sentence cuts.** A chunk boundary inside a sentence halves its context; whatever snippet is retrieved arrives as an orphan fragment. In `SAMPLE_DOCUMENT`, a 200-char sliding window makes **6 mid-sentence cuts** (`mid_sentence_cut_count`); sentence-aware chunking makes **zero**.
- **Mid-table cuts.** A markdown table whose rows straddle the boundary becomes two half-tables. The half with `| Phones | 7 days |` cannot tell the model whether it is legal to return a phone (that row's meaning depends on the `| Product | Window | Notes |` header in the chunk above, now severed). Count with `mid_table_cut_count`.
- **Mid-cut sections, for the same tombstone reasons: mid-code, mid-list, mid-quote.** A fenced code block cut in half stops parsing, and both halves stop answering "what does this function do".
- **The final-chunk stub.** Capping at fixed size leaves a remaining stub of ~30 characters; embedding a stub wastes a row and invites low-information matches.

The **overlap band-aid**: windows of 200 with 50-char overlap raise retrieval *recall* (the true sentence appears *somewhere* intact more often), at a concrete price:

- chunk count grows: step = size − overlap: 400 chars → 2.67 chunks instead of 2 (23% cost increase over a 1 MB corpus repeated on every query),
- the duplicated text appears in k results as multiple near-identical rows, diluting the top-k with near-duplicates,
- and it does nothing for mid-table or mid-code cuts (sameness is not structure).

`test_overlap_is_the_completeness_band_aid` pins both effects. Use overlap when you cannot detect structure — cheapest fix for cheap chunkers — not as a permanent architecture.

---

## 5. Structure-aware Splitting

Structure you can identify avoids cutting the units that carry meaning:

- **Sentences** (`sentence_chunks`) — pack whole sentences until full; the longest sentence alone over budget is hard-split then flagged (`hard_split=True`), never silently merged. A minimum-viable boundary detector must survive: `Dr.` / `e.g.` / `U.S.` abbreviations, `!!!` runs, and closing quotation marks. `split_sentences` in the module passes a test that every character is covered exactly once (`test_split_sentences_cover_every_character_exactly_once`).
- **Paragraphs** (`paragraph_chunks`) — blank-line breaks skip sentence machinery: the author already marked the unit boundary. Cheapest and often the best quality-per-line-of-code.
- **Markdown structure** (`markdown_chunks`) — the tree:
  - heading *hierarchy* rides in every chunk's metadata (`header_path`: `"Return Policy > Exclusions"`), so a retrieved snippet arrives with its context — vital for hybrid search (Topic 25 covers pgvector "WHERE" filters; header_path is a filterable column),
  - fenced code blocks never split (tracked with ` _FenceState` regardless of length),
  - tables naturally stay whole because a heading closes the section and table rows lack blank-line boundaries — plus the soft flush (at max_chars) only happens OUTSIDE a fence, keeping the fence pair intact.
- **Where real systems stop:** tables as row groups with the header echoed into each one (`[Product | \n | Laptops | …]`), question-response pairs (support tickets), YAML/JSON-keys, emails (quoted thread per segment), rows of logs.

Semantic-aware splitters (recursive character, then "embed sentence clusters and merge adjacent on cosine similarity, then embed clusters") sit *between* paragraph and markdown; they cost more compute but are the natural next step after this topic's hand-written strategies.

---

## 6. Size Trade-off: Precision vs Context Completeness

There is no universally right chunk size; there is a trade you are making, whether or not you've named it:

| Chunk size | Retrieval precision | Context completeness |
|---|---|---|
| **Small** (sentence/2-paragraph) | Embedding is on-topic: cosine hits the *span* that answers the query | Too little context: LLM gets the fact but not the clause that caveats it; you need top-k stress and neighbors-fetch |
| **Large** (page/section) | Embedding averages 5 sub-topics: the "near-miss" chunk matches everywhere and nowhere | Enough surrounding text: the LLM sees the claim + its qualifiers + the table it references |
| **Overlapped midsize** | Middle ground | Middle ground + a dedup tax in the k results |

The correct size depends on the *use*:

- question-answering over policy text → smaller + structure-aware (chunks carry `header_path`),
- summarization-context or "wide knowledge" retrieval → larger sections,
- code Q&A → chunk per function/class with the fence intact — the function is the natural unit.

Share the difference where it helps: retrieve coarse (parent sections for context), rank fine (child passages for precision). The "small-to-big" pattern is a *hybrid*, and it is why chunking remains a knob you tune with measurement rather than a one-time choice.

LLM-side budget math (request the number before writing the chunker):

```text
chunks_per_query ≈ (ctx_window - reserved_answer - system_prompt) / chunk_tokens
100k window: (100k - 4k answer - 2k instructions) / 400-token chunks ≈ 235 visible chunks
```

`token_budget_chunks` implements the sizing from the LLM backward; `estimate_token_count` = chars/4 as the budget proxy.

---

## 7. The Single Highest-leverage Claim (worth a re-read)

Pinecone's phrase: *"chunking your data before/after applying the embeddings... is the single highest-leverage preprocessing decision because it determines the quality of embeddings."* Restated operationally:

> If your chunking shreds meaning, no embedding model, no index, no reranker can un-shred it. If your chunking preserves meaning, even a modest embedding model scores visibly higher.

Concretely: when your golden-set eval (Topic 22 §6) stalls, change chunk size before changing models — it is 10× cheaper and orders of magnitude faster to measure.

---

## 8. Implementation Walkthrough — `chunking.py` + the Trade-off Table

Module survey:

- `Chunk` dataclass — id, text, start/end (character offsets into the ORIGINAL text), strategy, metadata (`header_path`, `hard_split`, `tokens`, `sentences`).
- `fixed_size_chunks` (size + overlap, rejects overlap ≥ size), `split_sentences` (abbreviation/exclam-safe), `sentence_chunks`, `paragraph_chunks`, `markdown_chunks` (heading path + fences), `token_budget_chunks` (chars/4 estimator or yours).
- `estimates_token_count` / `.token_estimate` (chars/4 heuristic; swap `tokenizer_estimate` for a real counter).
- Diagnostics: `is_sentence_end`, `mid_sentence_cut_count`, `mid_table_cut_count`, `balanced_fences`, `report`/`ChunkReport`.
- `SAMPLE_DOCUMENT` — policy text with headings, a long paragraph, an abbreviation + `!!!`, a markdown table, and a fenced code block: exactly the joints that punish naive windowing.

The notebook builds the full trade-off table on it:

```text
strategy   chunk count  avg/max chars   mid-sentence cuts  fences intact?
fixed      7            ~197/200        6                  cut
sentence    7           ~196/275        0                  all
markdown    3           ~460/508        0                  all
```

(run the notebook for your numbers; the *pattern* — fine-grained windows buy broken sentences; the structure-aware version has the fewest cuts and the cleanest chunks — is the point.)

---

## 9. Pitfalls

1. **Fixed windows as default** without measuring how many cuts you bought (run `mid_sentence_cut_count` before/after any chunk-size change).
2. **Overlap as a permanent architecture** — it hides tables/code from being cleanly bounded; it does not produce semantic boundaries; it taxes recall by injecting near-duplicates into top-k.
3. **Using whitespace split for markdown** rather than per-line walks — header paths, fences, and table states break invisibly.
4. **Sizing by characters** instead of token budget (or em-in accurate token counter if available):
   a chunk that "fits" 500 characters may be 800 tokens in CJK languages or dense code. Swapping in the char→4-token heuristic is only a first-order approximation — recheck with a real tokenizer for production settings.
5. **Chunking the whole corpus, then changing models/sizes** without a re-chunk + re-embed + re-index plan (each chunk row is stale). Treat new chunk strategy as a schema migration (Topic 26: idempotent upserts with `content_hash`).
6. **Chunking semantic units too finely** — decontextualized single sentences retrieve but stay un-usable ("the warranty does not apply" without the "if" clause above it). Preserve structure with metadata instead of hoping the model infers it.

---

## 10. Exercises

1. Grab a real doc you wrote this week (README, PR comment). Compute the fixed/sentence/markdown table by hand and count mid-sentence cuts for one of them in a terminal. Do the counts surprise you?
2. Break-abstraction exercise: change `sentence_chunks` to *merge* chunks that are < 60% of max_chars with the following one — does the returned chunk set stay "0 cuts"? What boundary does this give up?
3. Markdown: add a per-table mode that echoes the header row into each chunk (instead of keeping the whole table). Store the header row in `metadata`. When would you prefer this over keeping the table whole?
4. Chunk the same doc with `budget_tokens=100` where each chunk still gets its *own* `header_path`; filter by header_path and compute the latency savings over searching the whole corpus (Topic 25's "WHERE + nprobe" hybrid intuition).
5. Explain in one paragraph why chunking is "highest leverage" despite costing zero model calls.

---

## 11. Done-When Checklist

- [x] I chunked `SAMPLE_DOCUMENT` three ways and can state each one's granularity trade-off from the printed table.
- [x] I can show, with counts, why fixed-size windows cut sentences and tables and what overlap does and does not fix.
- [x] Sentence/paragraph/markdown strategies are implemented and tested, including abbreviation and fence edge cases.
- [x] I can restate Pinecone's "highest-leverage decision" claim operationally: where to spend eval time first, and why.

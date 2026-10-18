"""Topic 24 - Chunking: how you cut text decides what retrieval can find.

Chunking is the "single highest-leverage quality decision in RAG" (Pinecone's
phrasing): an embedding of a bad chunk cannot be found by a good query, and
a retrieved bad chunk poisons the answer. This module hand-writes the four
chunking families the sources describe:

- `fixed_size_chunks` - size + overlap windows (the pitfalls are visible)
- `sentence_chunks`   - sentence-aware splitting (zero mid-sentence cuts)
- `paragraph_chunks`  - blank-line structural splitting
- `markdown_chunks`   - structure-aware for Markdown: heading hierarchy
  travels in every chunk's metadata and fenced code blocks are never cut
- `token_budget_chunks` - packs sentences into a token budget (the LLM-side
  sizing decision, using the chars/4 estimate)

Plus diagnostics:
- `mid_sentence_cut_count` - how many boundaries fall inside a sentence
- `ChunkReport` / `report` - sizes/counts for the notebook comparisons

Every chunk is a `Chunk` dataclass: `id`, `text`, `start`/`end` (character
offsets into the ORIGINAL document), `strategy`, and `metadata`.

Everything is deterministic and offline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable

# Estimated tokens per character: the "chars/4" heuristic for English
# prose. It is a size ESTIMATE (byte-budget safety margin), not a tokenizer.
_CHARS_PER_TOKEN = 4

_TERMINATORS = {"!", "?", "."}
_ABBREV = re.compile(
    r"\b(?:Dr|Mr|Mrs|Ms|St|Sr|Jr|vs|etc|e\.g|i\.e|U\.S|prof)\.$", re.IGNORECASE
)


def estimate_token_count(text: str) -> int:
    """chars/4 token estimate; empty text -> 0."""
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


@dataclass
class Chunk:
    """One slice of a document, located inside the original text."""

    id: str
    text: str
    start: int  # character offset into the source document
    end: int
    strategy: str
    metadata: dict = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        return estimate_token_count(self.text)


# ---------------------------------------------------------------------------
# Sentence segmentation (the engine behind structure-aware chunking)
# ---------------------------------------------------------------------------


def is_sentence_end(text: str, end: int) -> bool:
    """True when `text[:end]` ends on a real sentence boundary.

    A real boundary: last terminator is . ! or ? (possibly a run like !!!),
    NOT preceded by an abbreviation (Dr., e.g., U.S.), and followed by
    whitespace or end-of-text.
    """
    if end >= len(text):
        return True  # the document end is always a boundary
    window = text[:end].rstrip()
    if not window or window[-1] not in _TERMINATORS:
        return False
    if _ABBREV.search(window):
        return False
    return True


def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) triples covering the text exactly once.

    Consecutive terminators count as one boundary ("items!!!" is one end);
    abbreviation dots never split ("Dr. Smith" stays whole).
    """
    sentences: list[tuple[int, int, str]] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch in _TERMINATORS:
            j = i + 1
            while j < n and text[j] in _TERMINATORS:
                j += 1
            followed_by_break = j >= n or text[j].isspace()
            if followed_by_break and not _ABBREV.search(text[start:j]):
                # consume trailing whitespace into THIS sentence so the
                # pieces concatenate back to the original text exactly
                k = j
                while k < n and text[k].isspace():
                    k += 1
                sentences.append((start, k, text[start:k]))
                start = k
                i = k
                continue
            i = j
            continue
        i += 1
    if start < n:
        sentences.append((start, n, text[start:]))
    return sentences


# ---------------------------------------------------------------------------
# 1. Fixed-size chunks with overlap
# ---------------------------------------------------------------------------


def fixed_size_chunks(text: str, size: int = 200, overlap: int = 0) -> list[Chunk]:
    """Sliding window of `size` characters, stepping `size - overlap`.

    The baseline everybody tries first, and the shape where the classic
    failures live: mid-sentence cuts, mid-table rows, mid-code. Use it as
    the comparison floor, not the final choice.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    chunks: list[Chunk] = []
    step = size - overlap
    index = 1
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(
            Chunk(
                id=f"fixed-{index}",
                text=text[start:end],
                start=start,
                end=end,
                strategy="fixed",
                metadata={"size": end - start, "overlap": overlap},
            )
        )
        index += 1
        if end == len(text):
            break
        start += step
    return chunks


def overlap_text(prev: Chunk, nxt: Chunk) -> str:
    """Whatever two consecutive chunks share (empty when no overlap)."""
    shared = min(prev.end, nxt.end) - nxt.start
    return nxt.text[: max(0, shared)] if shared > 0 else ""


# ---------------------------------------------------------------------------
# 2. Sentence-aware chunks
# ---------------------------------------------------------------------------


def sentence_chunks(text: str, max_chars: int = 300) -> list[Chunk]:
    """Pack whole sentences until `max_chars`; a single sentence longer
    than the budget is hard-split (flagged `hard_split=True` in metadata).
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_start: int | None = None
    index = 1

    def flush(end_char: int) -> None:
        nonlocal buffer, buffer_start, index
        if not buffer:
            return
        chunks.append(
            Chunk(
                id=f"sent-{index}",
                text=" ".join(s.strip() for s in buffer),
                start=buffer_start if buffer_start is not None else 0,
                end=end_char,
                strategy="sentence",
                metadata={"sentences": len(buffer)},
            )
        )
        buffer, buffer_start, index = [], None, index + 1

    for start, end, sentence in split_sentences(text):
        if len(sentence) > max_chars:
            flush(start)
            for piece_start in range(start, end, max_chars):
                piece_end = min(piece_start + max_chars, end)
                chunks.append(
                    Chunk(
                        id=f"sent-{index}",
                        text=text[piece_start:piece_end],
                        start=piece_start,
                        end=piece_end,
                        strategy="sentence",
                        metadata={"sentences": 0, "hard_split": True},
                    )
                )
                index += 1
            buffer, buffer_start = [], end
            continue
        if buffer_start is None:
            buffer_start = start
        tentative = sum(len(s) for s in buffer) + len(sentence) + len(buffer)
        if buffer and tentative > max_chars:
            flush(start)
            buffer_start = start
        buffer.append(sentence)
    flush(len(text))
    return chunks


# ---------------------------------------------------------------------------
# 3. Paragraph chunks
# ---------------------------------------------------------------------------


def paragraph_chunks(text: str, max_chars: int = 600) -> list[Chunk]:
    """One chunk per non-empty paragraph line (hard-split if oversize).

    Paragraph breaks are the smallest split the AUTHOR chose as "this
    belongs together" - stronger structural signal than any character
    window.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    paragraphs: list[tuple[int, int, str]] = []
    for line_match in re.finditer(r"[^\n]*(?:\n|$)", text):
        paragraph = line_match.group(0)
        if paragraph.strip():
            paragraphs.append((line_match.start(), line_match.start() + len(paragraph), paragraph))
    chunks: list[Chunk] = []
    index = 1
    for start, end, paragraph in paragraphs:
        if len(paragraph) > max_chars:
            for piece_start in range(start, end, max_chars):
                piece_end = min(piece_start + max_chars, end)
                chunks.append(
                    Chunk(
                        id=f"para-{index}",
                        text=text[piece_start:piece_end],
                        start=piece_start,
                        end=piece_end,
                        strategy="paragraph",
                        metadata={"hard_split": True},
                    )
                )
                index += 1
        else:
            chunks.append(
                Chunk(
                    id=f"para-{index}",
                    text=paragraph,
                    start=start,
                    end=end,
                    strategy="paragraph",
                    metadata={},
                )
            )
            index += 1
    return chunks


# ---------------------------------------------------------------------------
# 4. Markdown / structure-aware chunks
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^(```|~~~)")


class _FenceState:
    def __init__(self) -> None:
        self.inside = False
        self.marker = ""


def markdown_chunks(text: str, max_chars: int = 800) -> list[Chunk]:
    """Chunk a Markdown document with structure awareness:

    - the heading path ("# Return Policy > ## Exclusions") rides along in
      every chunk's metadata, so a retrieved snippet knows its section;
    - fenced code blocks are never cut mid-block;
    - headings close sections; long sections soft-pack at `max_chars`.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    lines = text.splitlines(keepends=True)
    chunks: list[Chunk] = []
    header_path: list[str] = []
    current: list[str] = []
    current_start = 0
    offset = 0
    fence = _FenceState()
    index = 1

    def flush(end_char: int) -> None:
        nonlocal current, index
        body = "".join(current)
        if body.strip():
            chunks.append(
                Chunk(
                    id=f"md-{index}",
                    text=body,
                    start=current_start,
                    end=end_char,
                    strategy="markdown",
                    metadata={
                        "header_path": " > ".join(header_path) if header_path else "(top)"
                    },
                )
            )
            index += 1

    for line in lines:
        start, end = offset, offset + len(line)
        offset = end
        marker = _FENCE_RE.match(line.strip())
        if marker:
            if not fence.inside:
                fence.inside, fence.marker = True, marker.group(1)
            elif marker.group(1) == fence.marker:
                fence.inside = False
        heading = _HEADING_RE.match(line.rstrip("\n"))
        if heading and not fence.inside:
            if current and any(l.strip() for l in current):
                flush(start)
            level, title = len(heading.group(1)), heading.group(2).strip()
            header_path = header_path[: level - 1] + [title]
            current_start = start
            current = [line]
            continue
        if not current:
            current_start = start
        current.append(line)
        if not fence.inside and len("".join(current)) >= max_chars:
            flush(end)
            current = []
    if current and any(l.strip() for l in current):
        flush(len(text))
    return chunks


# ---------------------------------------------------------------------------
# 5. Token-budget packing
# ---------------------------------------------------------------------------


def token_budget_chunks(
    text: str,
    budget_tokens: int = 120,
    tokenizer_estimate: Callable[[str], int] | None = None,
) -> list[Chunk]:
    """Greedy sentence packing into a token budget.

    Choose budget from the LLM side:
        (context window - answer reserve - instruction reserve) / n_chunks
    then stuff sentences until full. `tokenizer_estimate` defaults to the
    chars/4 heuristic; swap in a real counter when you have one.
    """
    if budget_tokens <= 0:
        raise ValueError("budget_tokens must be positive")
    estimate = tokenizer_estimate or estimate_token_count

    chunks: list[Chunk] = []
    current: list[str] = []
    current_start: int | None = None
    index = 1

    def flush(end_char: int) -> None:
        nonlocal current, current_start, index
        if not current:
            return
        packed = " ".join(s.strip() for s in current)
        chunks.append(
            Chunk(
                id=f"budget-{index}",
                text=packed,
                start=current_start if current_start is not None else 0,
                end=end_char,
                strategy="budget",
                metadata={"tokens": estimate(packed)},
            )
        )
        current, current_start, index = [], None, index + 1

    for start, end, sentence in split_sentences(text):
        if estimate(sentence) > budget_tokens:
            flush(start)
            max_chars = max(1, budget_tokens * _CHARS_PER_TOKEN)
            for piece_start in range(start, end, max_chars):
                piece_end = min(piece_start + max_chars, end)
                piece = text[piece_start:piece_end]
                chunks.append(
                    Chunk(
                        id=f"budget-{index}",
                        text=piece,
                        start=piece_start,
                        end=piece_end,
                        strategy="budget",
                        metadata={"tokens": estimate(piece), "hard_split": True},
                    )
                )
                index += 1
            current, current_start = [], end
            continue
        tentative = estimate(" ".join(current + [sentence]))
        if current and tentative > budget_tokens:
            flush(start)
            current_start = start
        if current_start is None:
            current_start = start
        current.append(sentence)
    flush(len(text))
    return chunks


# ---------------------------------------------------------------------------
# 6. Diagnostics
# ---------------------------------------------------------------------------


def mid_sentence_cut_count(chunks: list[Chunk], text: str) -> int:
    """How many chunk boundaries fall INSIDE a sentence?

    This is the number the fixed-size strategy showers on you and the
    sentence/structure strategies eliminate ( apart from flagged
    hard-splits, which land inside a very long sentence by definition).
    """
    boundaries = [c.end for c in chunks if c.end < len(text)]
    return sum(1 for end in boundaries if not is_sentence_end(text, end))


def mid_table_cut_count(chunks: list[Chunk]) -> int:
    """Chunks that open or close mid-table (first/last line starts with |).

    The fixed-size windows over `SAMPLE_DOCUMENT` produce several of these;
    structure-aware strategies should produce zero (the whole table is one
    chunk or is bounded by a heading).
    """
    count = 0
    for chunk in chunks:
        lines = [ln for ln in chunk.text.splitlines() if ln.strip()]
        if not lines or chunk.strategy != "fixed":
            continue
        starts_inside = lines[0].lstrip().startswith("|")
        ends_inside = lines[-1].lstrip().startswith("|")
        count += int(starts_inside or ends_inside)
    return count


def balanced_fences(chunk_text: str) -> bool:
    """True when ``` fences come in pairs (a code block was never cut)."""
    return chunk_text.count("```") % 2 == 0


@dataclass
class ChunkReport:
    strategy: str
    chunk_count: int
    avg_chars: float
    max_chars: int
    mid_sentence_cuts: int


def report(chunks: list[Chunk], text: str) -> ChunkReport:
    sizes = [len(c.text) for c in chunks]
    return ChunkReport(
        strategy=chunks[0].strategy if chunks else "",
        chunk_count=len(chunks),
        avg_chars=sum(sizes) / len(sizes) if sizes else 0.0,
        max_chars=max(sizes) if sizes else 0,
        mid_sentence_cuts=mid_sentence_cut_count(chunks, text),
    )


# A sample document with every pitfall the sources mention: one-line vs
# long-line paragraphs, a heading tree, a Markdown TABLE, a fenced CODE
# BLOCK, an abbreviation (Dr.) and a run of exclamation marks.
SAMPLE_DOCUMENT = """# Return Policy

We accept returns within 30 days. Refunds go back to the original payment method within 5 business days after inspection completes at our returns center. Items must be unused, in original packaging, and accompanied by the order number from the email confirmation you received at purchase time.

Sale items!!! Are final sale only. Dr. Smith recommends checking the manufacturer warranty first.

## Exclusions

Electronics are the exception - see the table below.

| Product | Window | Notes |
|---------|--------|-------|
| Laptops | 14 days | Must include charger |
| Phones | 7 days | Activation locks must be off |
| Headphones | 30 days | Hygiene seal intact |

Wireless headphones have a special note: hygiene seals matter enormously. Broken seals make the return void, and refunds will not be issued in that case. The warehouse team photographs every returned item as proof of arrival condition.

## Shipping Damages

```python
def is_returnable(item, days_since_purchase):
    if item.from_sale and days_since_purchase > 0:
        return False  # sale items are final
    return days_since_purchase <= item.return_window
```

Photograph the box before opening. Carriers deny claims without photos, and our support team needs those images to open a claim with the shipping partner within the first 48 hours after delivery is recorded in the tracking system.
"""

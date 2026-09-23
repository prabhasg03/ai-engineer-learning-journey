# Topic 1 — Tokens

This folder contains a learning-focused implementation notebook for the tokenization topic in the LLM fundamentals phase.

## Goal

The notebook explains how:

- text is converted into bytes and token IDs
- byte-pair encoding (BPE) reduces redundancy
- token counts differ from word counts
- hidden tokenizer behavior affects cost, context windows, and weird edge cases

## Files

- `implementation/codebook.ipynb` — main notebook with the full learning flow
- `notes.md` — summary notes from the syllabus

## Suggested flow

1. Read the learning objectives in the notebook.
2. Build the character-level tokenizer first.
3. Move to byte-level reasoning and BPE pair merges.
4. Compare your own implementation with `tiktoken`.
5. Finish with a prediction-vs-verification exercise.

## Core idea

```text
Text
  ↓
Bytes / characters
  ↓
BPE merges
  ↓
Vocabulary IDs
  ↓
LLM input
```

This notebook intentionally focuses on the mechanism and intuition rather than re-implementing every production detail of Karpathy's full `minbpe` repo.

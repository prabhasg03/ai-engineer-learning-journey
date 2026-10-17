# Mini-project A — CLI summariser

Reads a text file, asks an OpenAI-compatible endpoint for a summary, and prints a
token-and-cost report for the run.

**Rules for this project:** hand-written throughout. No frameworks, no streaming, no
autocomplete/AI code generation. This is the Phase 1 consolidation — it should use only
topics 1–10: tokens, context window, statelessness, plain Python, one raw API call,
temperature, cost counting.

---

## What it does

```
python summariser.py sample.txt
```

1. Reads the file (`read_text`).
2. Builds a system + user prompt with the document wrapped in `<<<DOCUMENT>>>` delimiters
   (`build_messages`).
3. Counts the input tokens (`count_tokens`).
4. Calls `POST {base_url}/chat/completions` **without streaming** (`call_api`).
5. Reads the `usage` block from the response (`parse_usage`).
6. Prints the summary and a per-run report: input tokens, output tokens, total, and the
   USD cost computed from the input/output split (`compute_cost`, `format_report`).

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`
- A running OpenAI-compatible endpoint. The defaults point at a local
  [llama-server](https://github.com/ggml-org/llama.cpp) on `http://127.0.0.1:8080/v1`.

`tiktoken` is optional: without it the tool falls back to a ~4-chars/token estimate and
says so in the count. `requests` is required only for the actual API call; the
`--estimate-only` path and the whole test suite run without it.

## Usage

```bash
# summarise a file against the local endpoint
python summariser.py sample.txt

# choose the summary shape
python summariser.py sample.txt --style bullets
python summariser.py sample.txt --style tldr

# point at a different endpoint/model
python summariser.py sample.txt \
    --base-url http://127.0.0.1:8080/v1 \
    --model Qwen/Qwen3-4B-GGUF:Q4_K_M

# estimate tokens and cost WITHOUT calling the API
python summariser.py sample.txt --estimate-only

# machine-readable report
python summariser.py sample.txt --json
```

### Reasoning models (Qwen3, DeepSeek-R1, …)

Hybrid-reasoning models emit a hidden "thinking" block before the answer. On a small
`--max-tokens` budget they can spend the whole budget thinking and return **empty visible
content** — the run then fails with a clear error. The fix is the llama.cpp switch
`chat_template_kwargs.enable_thinking=false`, which this tool adds automatically when the
model name contains `qwen3`. Override it either way:

```bash
python summariser.py sample.txt --no-think   # force thinking off
python summariser.py sample.txt --think      # force thinking on (e.g. non-Qwen3)
```

Environment variables (all optional, overridden by CLI flags):

| Variable             | Meaning                       | Default                          |
|----------------------|-------------------------------|----------------------------------|
| `LLM_BASE_URL`       | endpoint base URL             | `http://127.0.0.1:8080/v1`       |
| `LLM_MODEL`          | model name                    | `Qwen/Qwen3-4B-GGUF:Q4_K_M`      |
| `SUMMARISER_PRICE_IN`| USD per 1M input tokens       | `0.30`                           |
| `SUMMARISER_PRICE_OUT`| USD per 1M output tokens     | `1.20`                           |

### Example report

```
--- RUN REPORT ---
model            : Qwen/Qwen3-4B-GGUF:Q4_K_M
source tokens    :      145
input tokens     :      196
output tokens    :       74
total tokens     :      270
cost (USD)       : 0.000148
```

## Tests

```bash
python -m pytest -q
```

The suite covers the pure functions (token counting, cost formula, message building,
usage parsing, response extraction, report formatting) and the CLI paths
(`--estimate-only`, `--json`, missing file). It never touches the network: the API call is
replaced with a fake response via `monkeypatch`.

## Design notes (write these yourself as you go)

- **Statelessness (topic 4):** the tool re-sends the whole document every run; nothing is
  remembered between invocations.
- **Context window (topic 3):** a very large file will exceed the model's budget. The
  current version does not chunk — decide whether that is acceptable, and if not, add a
  chunk-and-merge step.
- **Temperature (topic 7):** summarisation is an extraction-flavoured task, so the default
  is low (`0.2`). Justify any change.
- **Cost (topic 10):** the report shows the input/output split because the two prices
  differ; the document dominates the input, not the instruction.
- **Reasoning models:** turning hidden thinking off is what makes the visible summary
  non-empty on Qwen3; the auto-detect keeps the tool usable on plain chat models too.

## Done-when checklist (from the syllabus)

- [ ] File reader + API call, streaming-free output
- [ ] Token/cost report per run
- [ ] pytest suite passing
- [ ] Written without autocomplete/AI generation

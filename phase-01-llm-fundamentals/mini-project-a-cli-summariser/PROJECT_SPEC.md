# Mini-Project A --- CLI Summariser

## Detailed Project Specification

**Phase:** 1 --- What an LLM Actually Is\
**Prerequisites:** Topics 1--10 complete\
**Project type:** Handwritten Python CLI application\
**Completion standard:** A hiring manager can clone the project and run
it on a fresh machine by following `README.md` alone.

------------------------------------------------------------------------

## 1. Project Goal

Build a command-line application that reads a UTF-8 text file, sends its
contents to a local LLM served by `llama-server` through a raw HTTP
request, prints a structured summary, and reports token usage and
estimated cost.

This project is intended to demonstrate understanding of Python CLI
design, HTTP requests, JSON parsing, prompt construction, token
counting, cost calculation, error handling, automated testing, type
checking, and reproducible setup.

### Mandatory implementation rules

-   Write every project file yourself, from scratch.
-   Do not use frameworks.
-   Do not use Copilot, AI code generation, or autocomplete.
-   Do not use the OpenAI or Anthropic SDKs.
-   Do not use LangChain.
-   Do not use asynchronous code or concurrency.
-   Do not stream the model response. Make one request and wait for the
    complete response.
-   Do not add retries. Fail fast and provide a useful error.
-   Keep configuration in function arguments or CLI options; do not use
    global mutable state.

Permitted tools/libraries: Python standard library modules such as
`argparse`, `json`, `pathlib`, `dataclasses`, and `os`; `requests`;
`pytest`; `mypy`; and optional `tiktoken`.

------------------------------------------------------------------------

## 2. Expected Repository Layout

Create this directory and file structure:

``` text
mini-project-a-cli-summariser/
├── summariser.py          # Application and CLI
├── test_summariser.py     # Automated tests
├── requirements.txt       # Runtime/test dependencies
├── sample.txt             # Small example input
├── README.md              # Setup, usage, design notes
└── PROJECT_SPEC.md        # This specification
```

The application is expected to be approximately 300 lines and the test
suite approximately 400 lines, but these are estimates rather than
line-count targets. Correctness and clarity matter more than matching a
line count.

------------------------------------------------------------------------

## 3. CLI Interface

The program must be runnable as:

``` bash
python summariser.py sample.txt
```

### Required command-line options

  -------------------------------------------------------------------------------------
  Argument            Type              Default                      Requirement
  ------------------- ----------------- ---------------------------- ------------------
  `path`              Required          None                         UTF-8 text file to
                      positional path                                summarise

  `--style`           Choice            `paragraph`                  Accept
                                                                     `paragraph`,
                                                                     `bullets`, or
                                                                     `tldr`

  `--base-url`        String            `http://127.0.0.1:8080/v1`   Base URL for the
                                                                     local llama-server
                                                                     API

  `--model`           String            Environment variable         Model identifier
                                        `LLM_MODEL`, otherwise the   sent in the API
                                        documented default           payload

  `--temperature`     Float             `0.2`                        Sampling
                                                                     temperature

  `--max-tokens`      Integer           `200`                        Maximum generated
                                                                     output tokens

  `--price-in`        Float             `0.30`                       USD price per one
                                                                     million input
                                                                     tokens

  `--price-out`       Float             `1.20`                       USD price per one
                                                                     million output
                                                                     tokens

  `--estimate-only`   Flag              Off                          Calculate an
                                                                     estimate without
                                                                     calling the API

  `--json`            Flag              Off                          Emit a
                                                                     machine-readable
                                                                     JSON report
  -------------------------------------------------------------------------------------

The model default should be defined and documented consistently in the
implementation and README. The original example uses
`Qwen/Qwen3-4B-GGUF:Q4_K_M`.

### Required invocation examples

``` bash
python summariser.py sample.txt
python summariser.py sample.txt --style bullets
python summariser.py sample.txt --style tldr

python summariser.py sample.txt \
  --base-url http://127.0.0.1:8080/v1 \
  --model Qwen/Qwen3-4B-GGUF:Q4_K_M

python summariser.py sample.txt --estimate-only
python summariser.py sample.txt --json
```

Use `argparse` to define and validate arguments. Invalid choices should
be rejected by the CLI parser. Do not silently ignore user-supplied
options.

------------------------------------------------------------------------

## 4. Required Summary Styles

The selected style must be represented in the **system message**, not
appended as an instruction in the user message.

  Style         Required instruction/output constraint
  ------------- -------------------------------------------------
  `paragraph`   One concise paragraph of no more than 120 words
  `bullets`     3--5 bullets, each no more than 20 words
  `tldr`        One sentence of no more than 30 words

The user message should contain the document to summarise, wrapped in
clear delimiters so the model can distinguish the document from the
surrounding instructions.

Do not assume the model will always obey the requested format perfectly.
The application's responsibility is to construct the right prompt and
return the model's response; the specification does not require a
separate output-rewriting system.

------------------------------------------------------------------------

## 5. Token Counting

Implement:

``` text
count_tokens(text) -> int
```

### Required behaviour

1.  **Primary method:** Use `tiktoken.get_encoding("cl100k_base")` when
    `tiktoken` is installed.
2.  **Fallback:** If `tiktoken` is unavailable, estimate tokens using:
    `max(1, round(len(text) / 4))`
3.  Return an integer count.
4.  Test both the tokenizer path and the fallback path.
5.  Do not describe the fallback as exact tokenization.

### Token categories

-   **Source tokens:** Count the original document text only, before
    prompt templating.
-   **Input/prompt tokens:** Count the complete request text represented
    by the system prompt plus the user prompt containing the document.
-   **Output/completion tokens:** Prefer the provider's
    `usage.completion_tokens`. For an estimate-only run, use
    `--max-tokens` as the output estimate.
-   **Total tokens:** Input tokens plus output tokens.

The local model's tokenizer may differ from `cl100k_base`, so locally
calculated prompt counts are estimates. When the API provides usage
values, use those values for the actual usage report as specified below.

------------------------------------------------------------------------

## 6. Cost Calculation

Implement:

``` text
compute_cost(in, out, price_in, price_out) -> float
```

Use this formula:

``` text
cost_usd = (input_tokens / 1_000_000 * price_in) \
         + (output_tokens / 1_000_000 * price_out)
```

The input and output rates are independently configurable through
`--price-in` and `--price-out`.

Requirements:

-   Correctly calculate input and output costs separately.
-   Return the combined cost as a float.
-   Handle zero input tokens and/or zero output tokens.
-   Do not multiply by the source-token count separately; source tokens
    are a diagnostic field, not an additional billable category.
-   Include the resulting cost in every report.
-   Explain in the README that input and output prices can differ.

The rates are configurable estimates supplied by the user. Do not imply
that these defaults necessarily represent the actual price of running a
local model.

------------------------------------------------------------------------

## 7. File Reading and Validation

Implement:

``` text
read_text(path) -> str
```

Requirements:

-   Read the supplied file as UTF-8.
-   Return the file contents as a string.
-   Detect a missing file and report the required error.
-   Detect an empty file and report the required error.
-   Use clear, predictable error handling rather than exposing an
    unnecessary traceback to a normal CLI user.
-   Do not silently substitute another file or input.

Required errors:

``` text
error: input file not found: <path>
error: input file is empty: <path>
```

Both errors must result in exit code `2`.

The specification explicitly requires an empty-file check. It does not
define whether whitespace-only content should count as empty; choose a
consistent interpretation and document it.

------------------------------------------------------------------------

## 8. HTTP API Integration

Implement:

``` text
call_api(base_url, model, messages, temp, max_tokens) -> dict
```

### Request requirements

-   Use `requests.post` directly; do not use an LLM provider SDK.
-   Send one request to the local server's chat-completions endpoint
    under the configured base URL.
-   Include the model identifier, constructed messages, temperature, and
    maximum output-token limit in the request payload.
-   Set a timeout of **300 seconds** (local reasoning models can exceed
    120 s on a single summarisation call).
-   Do not enable streaming.
-   Make only one request; do not retry.
-   Parse the JSON response and return it for subsequent processing.
-   Handle HTTP status errors and network/timeout failures using the
    required error behaviour.

The server is expected to expose an OpenAI-compatible chat-completions
API. The project does not require support for arbitrary API formats.

### Required API error behaviour

  -----------------------------------------------------------------------------------------------------------
  Failure                                  Exit code Required message format
  --------------------- ---------------------------- --------------------------------------------------------
  HTTP 401                                         1 `error: 401 Unauthorized — check API key`

  HTTP 400                                         1 `error: 400 Bad Request — <response body>`

  HTTP 429                                         1 `error: 429 Rate Limited — retry after <Retry-After>s`

  HTTP 5xx                                         1 `error: 5xx Server Error — <status>`

  Network/timeout                                  1 `error: ConnectionError — <detail>`

  Empty model response                             1 `error: model returned empty content`
  -----------------------------------------------------------------------------------------------------------

For a 429 response, use the server's `Retry-After` header when present.
If it is absent, choose a clear fallback representation and document it;
do not retry automatically. For HTTP 5xx, the message should include the
actual status code, such as `503`.

Other unexpected HTTP statuses should also fail clearly with a non-zero
exit rather than being treated as success.

------------------------------------------------------------------------

## 9. Response Parsing

Implement the following functions:

``` text
parse_usage(response) -> Usage
extract_content(response) -> str
```

### `Usage` data structure

Define `Usage` as a dataclass with these integer fields:

-   `prompt_tokens`
-   `completion_tokens`
-   `total_tokens`

### `parse_usage(response)` requirements

-   Read usage information from the provider response when it is present
    and valid.
-   Return a `Usage` instance.
-   Handle a missing usage block without crashing.
-   The caller must be able to distinguish missing provider usage from
    valid reported usage so it can apply the required fallback
    behaviour.
-   Do not assume the provider always reports usage.

### `extract_content(response)` requirements

-   Extract the assistant's message content from the expected
    chat-completions response structure.
-   Validate that the expected fields exist and have usable values.
-   Handle malformed responses and empty content.
-   An empty or unusable assistant response must ultimately produce:
    `error: model returned empty content` with exit code `1`.

The tests must cover both successful extraction and malformed response
data.

------------------------------------------------------------------------

## 10. Summary Orchestration

Implement:

``` text
summarise(...) -> dict
```

This function coordinates file input, prompt creation, token counts, API
use, response parsing, cost calculation, and report data.

### Required behaviour

1.  Read and validate the input document.
2.  Count source tokens.
3.  Build the system and user messages for the selected style.
4.  Calculate the locally estimated input-token count.
5.  If `estimate_only=True`:
    -   Do not call the API.
    -   Use the configured maximum output-token limit as the
        output-token estimate.
    -   Calculate the estimated total tokens and cost.
    -   Return report data sufficient for text or JSON output.
6.  Otherwise:
    -   Call the API once.
    -   Extract the summary.
    -   Parse provider usage if available.
    -   Prefer provider-reported prompt/completion/total usage for the
        actual report when valid.
    -   If provider usage is absent, use the application's own token
        estimates; use the configured maximum output tokens as the
        output fallback specified by the project.
    -   Calculate total tokens and cost consistently.
7.  Return structured data so the CLI can render either a human-readable
    result or JSON.

The exact keys in the returned dictionary should be selected
deliberately, documented, and used consistently by the report formatter
and CLI. Include at least the summary when a real request was made, the
model, source/input/output/total token counts, cost, and whether the
result is estimated.

Do not make an API request in estimate-only mode. This must be proven by
a test that fails if the API function is called.

------------------------------------------------------------------------

## 11. Report Formatting

Implement:

``` text
format_report(model, usage, cost, source_tokens, estimated) -> str
```

The human-readable report must include all of these fields:

``` text
--- RUN REPORT ---
model            : <model identifier>
source tokens    : <count>
input tokens     : <count>
output tokens    : <count>
total tokens     : <count>
cost (USD)       : <cost>
```

Requirements:

-   Include the model identifier.
-   Include source, input, output, and total token counts.
-   Include cost in USD.
-   Make it clear when the figures are estimates rather than
    provider-reported usage.
-   Format the cost to a consistent precision; the example uses six
    decimal places.
-   Keep the report readable in a terminal.

The project must also support JSON output through `--json`. JSON must be
valid machine-readable JSON, not a Python dictionary representation.
Include all report fields and an explicit estimated/actual indicator.
For a real summary run, include the summary in the JSON output as well.

------------------------------------------------------------------------

## 12. CLI Output and Exit Codes

### Normal mode

For a successful normal run:

1.  Print the summary.
2.  Print the token/cost report.

### Estimate-only mode

-   Print the estimate report.
-   Do not call the LLM.
-   Exit with code `0` if the input and arguments are valid.

### JSON mode

-   Emit valid JSON containing all report fields.
-   Include the summary for a real API run.
-   Ensure errors are reported to standard error, not mixed into
    successful JSON output.
-   Use a consistent JSON schema across runs; if a field does not apply
    in estimate-only mode, represent it consistently, for example with
    `null`, rather than changing the type unpredictably.

### Exit codes

  Situation                                                                         Exit code
  -------------------------------------------------- ----------------------------------------
  Successful run                                                                            0
  API, network, timeout, or empty-response failure                                          1
  Missing input file                                                                        2
  Empty input file                                                                          2
  Invalid CLI arguments                                `argparse` standard non-zero behaviour

Implement:

``` text
build_parser() -> ArgumentParser
main(argv) -> int
```

Keep `main(argv)` testable by allowing an argument list to be passed
directly rather than requiring tests to alter the real process command
line.

------------------------------------------------------------------------

## 13. Automated Test Suite

Create `test_summariser.py`. Tests must not require a running LLM server
and must not make real network calls.

Use `pytest`, temporary files where appropriate, and `monkeypatch` to
replace the API function with a fake implementation.

The specification targets **27 passing tests**. The following is the
required coverage checklist; organize individual test cases so the
complete suite covers every item.

### Required test coverage

-   [ ] `count_tokens`: expected count when `tiktoken` is available.
-   [ ] `count_tokens`: heuristic fallback when `tiktoken` is
    unavailable.
-   [ ] `compute_cost`: input/output cost split.
-   [ ] `compute_cost`: zero-token case.
-   [ ] `build_messages`: selected style is injected into the system
    prompt.
-   [ ] `build_messages`: document is wrapped in clear delimiters.
-   [ ] `parse_usage`: valid usage block.
-   [ ] `parse_usage`: missing usage block.
-   [ ] `extract_content`: valid response.
-   [ ] `extract_content`: malformed response.
-   [ ] `format_report`: estimate report.
-   [ ] `format_report`: actual-usage report.
-   [ ] `format_report`: all required fields are present.
-   [ ] `summarise`: estimate-only mode does not call the API.
-   [ ] `summarise`: fake API response uses provider-reported usage.
-   [ ] `summarise`: missing provider usage triggers fallback counts.
-   [ ] CLI: `--estimate-only` prints an estimate and exits `0`.
-   [ ] CLI: `--json` emits valid JSON with all required fields.
-   [ ] CLI: missing file exits `2` and writes the required message to
    stderr.
-   [ ] File reading: valid UTF-8 file.
-   [ ] File reading: empty file.
-   [ ] API: 401 error.
-   [ ] API: 400 error.
-   [ ] API: 429 error.
-   [ ] API: 5xx error.
-   [ ] API: network/timeout failure.
-   [ ] API/response: empty model content.

The list above names 27 coverage targets; some targets may require
multiple test functions to test both positive and negative paths. The
final suite must include meaningful assertions rather than tests that
merely execute functions.

Run:

``` bash
python -m pytest -q
```

Target output: **27 passed**, consistent with the supplied project
specification. If you split a target into multiple tests, the actual
test count may be greater than 27; do not weaken coverage merely to
force a particular count.

------------------------------------------------------------------------

## 14. Type Hints and Code Quality

The application must meet these requirements:

-   Add `from __future__ import annotations`.
-   Add type hints to all functions, including parameters and return
    values.
-   Add docstrings to all public functions.
-   Use `Usage` as a dataclass.
-   Avoid `Any` types.
-   Do not use `type: ignore` unless there is a necessary, explained
    reason.
-   Avoid global mutable state.
-   Keep functions focused and readable.
-   Use clear names and handle errors explicitly.

Run:

``` bash
mypy --strict summariser.py
```

The target is zero errors. If third-party typing information creates a
problem, investigate and resolve it deliberately rather than suppressing
errors broadly.

------------------------------------------------------------------------

## 15. Dependencies

Create `requirements.txt` with the dependencies required to install and
run the application and its tests.

The project specification names:

-   `requests` --- HTTP requests.
-   `pytest` --- automated tests.
-   `tiktoken` --- optional token-counting dependency; the application
    must still work when it is unavailable.
-   `mypy` --- strict type checking during development.

Document which dependencies are needed at runtime and which are only for
development/testing. The fallback token counter must remain usable if
`tiktoken` is not installed.

------------------------------------------------------------------------

## 16. Sample Input

Include a small `sample.txt` so a reviewer can run the CLI immediately.

The supplied example text is:

``` text
Before deploying the API, ensure database migrations are complete, the queue is drained,
and the cache is warmed. Deploy to one node first, monitor errors and latency for 10
minutes, then roll out to remaining nodes. If error rate exceeds 1% or p99 latency
exceeds 500ms, roll back immediately. Document the rollback reason in the incident log.
```

A larger sample of approximately 500--2,000 words is also acceptable,
but a small sample is sufficient to validate basic setup and execution.

------------------------------------------------------------------------

## 17. Local LLM Server Setup

The original project specification gives this example for starting
`llama-server`:

``` bash
llama-server -hf Qwen/Qwen3-4B-GGUF:Q4_K_M -ngl 0 -c 4096 \
  --host 127.0.0.1 --port 8080
```

Then, in another terminal:

``` bash
cd phase-01-llm-fundamentals/mini-project-a-cli-summariser
python summariser.py sample.txt
```

The server command assumes `llama-server` is installed and that the
selected model can be obtained and run on the machine. Document any
machine-specific prerequisites and the exact way to install or obtain
the server/model that you personally validate. Do not claim the example
works on every machine without testing it.

### Reasoning-model note

The source specification notes that reasoning models such as Qwen3 or
DeepSeek-R1 may emit reasoning tokens and gives this request option:

``` json
{
  "chat_template_kwargs": {
    "enable_thinking": false
  }
}
```

It also mentions a `--no-think` option as already implemented in its
original plan, but `--no-think` is **not listed in the required CLI
arguments table** above. Treat it as an optional extension unless you
deliberately add it, test it, and document it. Do not let an optional
extension replace any required feature.

------------------------------------------------------------------------

## 18. README.md Requirements

The README must be sufficient for a new reviewer to set up and run the
project without asking you for missing steps.

Include all of the following:

1.  A one-line project description.
2.  Requirements, including Python 3.10+, installation using
    `pip install -r requirements.txt`, and the need for a running
    `llama-server`.
3.  Setup instructions for a fresh environment.
4.  Instructions for starting the local server and model.
5.  Usage examples for all required CLI options and combinations.
6.  An environment-variable table, including `LLM_MODEL`.
7.  Example successful output and an example report.
8.  The test command: `python -m pytest -q`.
9.  The type-check command: `mypy --strict summariser.py`.
10. Design notes explaining:
    -   **Statelessness (Topic 4):** The document is sent again on every
        run; the CLI does not rely on conversation memory stored by a
        previous run.
    -   **Context window (Topic 3):** Very large files may exceed the
        model's context window. Explain the limitations of the current
        implementation and do not claim automatic chunking if you have
        not implemented it.
    -   **Temperature (Topic 7):** Explain why a low default such as
        `0.2` is suitable for a relatively consistent summarisation
        task.
    -   **Cost (Topic 10):** Explain why input and output tokens have
        separate rates and why the reported cost is an estimate when
        usage or prices are estimated.
11. The completion checklist from this specification.
12. Known limitations and any machine-specific setup assumptions.

Keep documentation consistent with actual behaviour. Do not document
flags, environment variables, server setup steps, or error behaviour
that the implementation does not support.

------------------------------------------------------------------------

## 19. Acceptance Checklist

Do not mark the project complete until every applicable item has been
checked.

### Functional behaviour

-   [ ] `python summariser.py sample.txt` prints a summary and report.
-   [ ] `python summariser.py sample.txt --style bullets` requests
    bullet-style output.
-   [ ] `python summariser.py sample.txt --style tldr` requests a
    one-sentence TL;DR.
-   [ ] `python summariser.py sample.txt --estimate-only` does not make
    an API call and prints an estimate.
-   [ ] `python summariser.py sample.txt --json` emits valid JSON with
    all required fields.
-   [ ] `python summariser.py missing.txt` exits with code `2` and
    prints a clear error to stderr.
-   [ ] Empty input exits with code `2`.
-   [ ] HTTP, network, timeout, malformed-response, and empty-content
    errors fail clearly with the required exit code.

### Quality and tests

-   [ ] `python -m pytest -q` passes the required coverage targets.
-   [ ] `mypy --strict summariser.py` finishes with no errors.
-   [ ] Every function has type hints.
-   [ ] Every public function has a docstring.
-   [ ] No unnecessary `Any` or unexplained `type: ignore` is used.
-   [ ] Tests do not call a real network or require a live model server.

### Constraints

-   [ ] No `import openai`.
-   [ ] No `import anthropic`.
-   [ ] No `from langchain import ...`.
-   [ ] No `async`.
-   [ ] No streaming request such as `stream=True`.
-   [ ] No `ThreadPoolExecutor`.
-   [ ] No automatic retry logic.
-   [ ] No global mutable configuration.

### Documentation and reproducibility

-   [ ] README renders correctly on GitHub.
-   [ ] A fresh clone can be installed using the README instructions.
-   [ ] The documented commands have been tested on the target
    environment.
-   [ ] `sample.txt` is included.
-   [ ] The report and JSON schema are documented.
-   [ ] The final implementation and tests are handwritten by you.

------------------------------------------------------------------------

## 20. Suggested Implementation Sequence

Complete one small stage at a time. Test each stage before moving on.

1.  Create the directory and files.
2.  Implement `read_text`.
3.  Implement `count_tokens`.
4.  Implement `compute_cost`.
5.  Implement `build_messages`.
6.  Define `Usage` and implement `parse_usage`.
7.  Implement `extract_content`.
8.  Implement `format_report`.
9.  Implement `call_api` and test its error handling using mocked HTTP
    responses.
10. Implement `summarise`, including the no-network estimate-only path.
11. Implement `build_parser` and `main`.
12. Write the complete pytest suite.
13. Run the tests and fix failures.
14. Run `mypy --strict summariser.py`.
15. Write and validate the README.
16. Test the project from a fresh virtual environment or fresh clone.
17. Review every acceptance-checklist item before declaring the project
    done.

**Definition of done:** A reviewer can follow the README on a fresh
machine, install the dependencies, start the documented local model
server, run the sample command, see a summary and token/cost report, run
the tests without network access, and understand the design decisions
from the documentation.

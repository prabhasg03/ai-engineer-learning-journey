"""CLI summariser - Mini-project A (Phase 1).

Hand-written. No frameworks, no streaming, no autocomplete.

Reads a text file, asks an OpenAI-compatible endpoint for a summary, then prints a
token-and-cost report for the run.

The pure functions (``count_tokens``, ``build_messages``, ``compute_cost``,
``parse_usage``, ``format_report``) have no network dependency and are covered by
``test_summariser.py``. ``main`` wires them to a real HTTP call.

Usage:
    python summariser.py notes.txt
    python summariser.py notes.txt --style bullets --max-tokens 200
    python summariser.py notes.txt --estimate-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - environment dependent
    requests = None  # type: ignore[assignment]

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - tiktoken is optional
    _ENCODING = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_MODEL = "Qwen/Qwen3-4B-GGUF:Q4_K_M"

# USD per 1,000,000 tokens. Override with environment variables or CLI flags.
DEFAULT_PRICE_IN = 0.30
DEFAULT_PRICE_OUT = 1.20

STYLES = {
    "paragraph": "Write a single tight paragraph of at most 120 words.",
    "bullets": "Write between three and five bullet points, each under 20 words.",
    "tldr": "Write one sentence, at most 30 words.",
}


def auto_no_think(model: str) -> bool:
    """Default thinking off for models that emit a hidden reasoning block.

    Qwen3 (and a few other hybrid-reasoning models) can spend the whole output
    budget on hidden reasoning and return empty visible content. The
    llama.cpp-compatible switch ``chat_template_kwargs.enable_thinking`` fixes
    that. Other providers ignore or reject the field, so it is only added
    automatically for models known to need it; ``--no-think``/``--think``
    override the choice.
    """
    return "qwen3" in model.lower()


# ---------------------------------------------------------------------------
# Token counting and cost
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Exact via tiktoken when available, otherwise a rough ~4 chars/token guess."""
    if _ENCODING is not None:
        return len(_ENCODING.encode(text))
    return max(1, round(len(text) / 4))


def compute_cost(
    input_tokens: int,
    output_tokens: int,
    price_in_per_million: float,
    price_out_per_million: float,
) -> float:
    """USD for one request, from the input/output split."""
    return (
        input_tokens / 1_000_000 * price_in_per_million
        + output_tokens / 1_000_000 * price_out_per_million
    )


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def read_text(path: str | Path) -> str:
    """Read a UTF-8 text file, with a clear error if it is missing or empty."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"input file not found: {p}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"input file is empty: {p}")
    return text


def build_messages(text: str, style: str = "paragraph") -> list[dict[str, str]]:
    """Build the chat messages for the summarisation call."""
    instruction = STYLES.get(style)
    if instruction is None:
        raise ValueError(f"unknown style {style!r}; choose from {sorted(STYLES)}")
    system = (
        "You are a precise summariser. Use only information from the provided text. "
        "Do not add commentary, opinions, or facts that are not in the text. "
        f"{instruction}"
    )
    user = f"<<<DOCUMENT>>>\n{text}\n<<</DOCUMENT>>>"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# API call and response parsing
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def parse_usage(response_json: dict) -> Usage:
    """Read the usage block, falling back to zeros if the provider omits it."""
    usage = response_json.get("usage") or {}
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    total = int(usage.get("total_tokens", prompt + completion))
    return Usage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def call_api(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: float = 300.0,
    no_think: bool = False,
) -> dict:
    """POST to an OpenAI-compatible /chat/completions and return the parsed JSON."""
    if requests is None:
        raise RuntimeError("the 'requests' package is required to call the API")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if no_think:
        # llama.cpp extension: stop Qwen3 burning the budget on hidden reasoning.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    url = base_url.rstrip("/") + "/chat/completions"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def extract_content(response_json: dict) -> str:
    """Pull the assistant message text out of a chat-completions response."""
    try:
        message = response_json["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"unexpected response shape: {response_json!r}") from exc
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        if message.get("reasoning_content"):
            raise ValueError(
                "the model spent the whole output budget on hidden reasoning and "
                "returned no visible content; re-run with --no-think or a larger "
                "--max-tokens"
            )
        raise ValueError(f"the model returned no visible content: {response_json!r}")
    return content.strip()


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_report(
    model: str,
    usage: Usage,
    cost: float,
    source_tokens: int,
    estimated: bool = False,
) -> str:
    """Human-readable per-run token and cost report."""
    label = "ESTIMATE (no API call)" if estimated else "RUN REPORT"
    lines = [
        f"--- {label} ---",
        f"model            : {model}",
        f"source tokens    : {source_tokens:>8}",
        f"input tokens     : {usage.prompt_tokens:>8}",
        f"output tokens    : {usage.completion_tokens:>8}",
        f"total tokens     : {usage.total_tokens:>8}",
        f"cost (USD)       : {cost:>8.6f}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def summarise(
    text: str,
    *,
    base_url: str,
    model: str,
    style: str,
    temperature: float,
    max_tokens: int,
    price_in: float,
    price_out: float,
    estimate_only: bool = False,
    no_think: bool | None = None,
) -> dict:
    """Run one summarisation (or estimate it) and return summary + report data."""
    messages = build_messages(text, style)
    input_tokens = sum(count_tokens(m["content"]) for m in messages)

    if estimate_only:
        estimated_output = max_tokens
        usage = Usage(input_tokens, estimated_output, input_tokens + estimated_output)
        return {
            "summary": None,
            "usage": usage,
            "cost": compute_cost(input_tokens, estimated_output, price_in, price_out),
            "estimated": True,
        }

    resolved_no_think = auto_no_think(model) if no_think is None else no_think
    response = call_api(
        base_url, model, messages, temperature, max_tokens, no_think=resolved_no_think
    )
    summary = extract_content(response)
    usage = parse_usage(response)
    if usage.prompt_tokens == 0:
        # Provider omitted usage; fall back to our own count for the input side.
        usage = Usage(input_tokens, count_tokens(summary), input_tokens + count_tokens(summary))
    cost = compute_cost(usage.prompt_tokens, usage.completion_tokens, price_in, price_out)
    return {"summary": summary, "usage": usage, "cost": cost, "estimated": False}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="summariser",
        description="Summarise a text file and print a token/cost report.",
    )
    parser.add_argument("path", help="path to a UTF-8 text file")
    parser.add_argument(
        "--style",
        choices=sorted(STYLES),
        default="paragraph",
        help="summary shape (default: paragraph)",
    )
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=200)
    parser.add_argument(
        "--price-in",
        type=float,
        default=float(os.getenv("SUMMARISER_PRICE_IN", DEFAULT_PRICE_IN)),
        help="USD per 1M input tokens",
    )
    parser.add_argument(
        "--price-out",
        type=float,
        default=float(os.getenv("SUMMARISER_PRICE_OUT", DEFAULT_PRICE_OUT)),
        help="USD per 1M output tokens",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="count tokens and estimate cost without calling the API",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the report as JSON instead of text",
    )
    thinking = parser.add_mutually_exclusive_group()
    thinking.add_argument(
        "--no-think",
        dest="no_think",
        action="store_true",
        default=None,
        help="disable hidden reasoning (llama.cpp chat_template_kwargs)",
    )
    thinking.add_argument(
        "--think",
        dest="no_think",
        action="store_false",
        help="force hidden reasoning even for models auto-detected as reasoning models",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        text = read_text(args.path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        result = summarise(
            text,
            base_url=args.base_url,
            model=args.model,
            style=args.style,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            price_in=args.price_in,
            price_out=args.price_out,
            estimate_only=args.estimate_only,
            no_think=args.no_think,
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure as a clean exit code
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    usage: Usage = result["usage"]
    report = format_report(
        args.model,
        usage,
        result["cost"],
        source_tokens=count_tokens(text),
        estimated=result["estimated"],
    )

    if args.json:
        print(
            json.dumps(
                {
                    "summary": result["summary"],
                    "model": args.model,
                    "usage": usage.__dict__,
                    "cost_usd": result["cost"],
                    "estimated": result["estimated"],
                },
                indent=2,
            )
        )
    else:
        if result["summary"] is not None:
            print(result["summary"])
            print()
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

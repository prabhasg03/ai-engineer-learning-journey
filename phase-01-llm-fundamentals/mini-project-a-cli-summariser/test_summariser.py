"""Tests for the CLI summariser (Mini-project A).

Hand-written, plain asserts. Run with:

    python -m pytest -q

No network is required: the API call is replaced with a fake response object.
"""

from __future__ import annotations

import json

import pytest

import summariser
from summariser import (
    STYLES,
    Usage,
    build_messages,
    compute_cost,
    count_tokens,
    extract_content,
    format_report,
    parse_usage,
    read_text,
)


# ---------------------------------------------------------------------------
# count_tokens
# ---------------------------------------------------------------------------


def test_count_tokens_is_positive_for_nonempty_text():
    assert count_tokens("hello world") >= 1


def test_count_tokens_grows_with_length():
    short = count_tokens("hello")
    long = count_tokens("hello " * 50)
    assert long > short


def test_count_tokens_of_empty_string():
    # Non-negative; tokenizers may return 0 for the empty string.
    assert count_tokens("") >= 0


# ---------------------------------------------------------------------------
# compute_cost
# ---------------------------------------------------------------------------


def test_compute_cost_matches_two_price_formula():
    # 1,000,000 in @ $3 + 1,000,000 out @ $15 = $18
    assert compute_cost(1_000_000, 1_000_000, 3.0, 15.0) == pytest.approx(18.0)


def test_compute_cost_is_zero_for_no_tokens():
    assert compute_cost(0, 0, 3.0, 15.0) == 0.0


def test_compute_cost_output_is_pricier_than_input():
    only_input = compute_cost(1_000, 0, 3.0, 15.0)
    only_output = compute_cost(0, 1_000, 3.0, 15.0)
    assert only_output > only_input


# ---------------------------------------------------------------------------
# read_text
# ---------------------------------------------------------------------------


def test_read_text_returns_file_contents(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("hello summariser", encoding="utf-8")
    assert read_text(p) == "hello summariser"


def test_read_text_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        read_text("does-not-exist-anywhere.txt")


def test_read_text_empty_file_raises(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(ValueError):
        read_text(p)


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------


def test_build_messages_has_system_then_user():
    messages = build_messages("some document", "paragraph")
    assert [m["role"] for m in messages] == ["system", "user"]


def test_build_messages_wraps_document_in_delimiters():
    messages = build_messages("the body text", "paragraph")
    user = messages[-1]["content"]
    assert "<<<DOCUMENT>>>" in user
    assert "<<</DOCUMENT>>>" in user
    assert "the body text" in user


def test_build_messages_style_changes_instruction():
    paragraph = build_messages("x", "paragraph")[0]["content"]
    bullets = build_messages("x", "bullets")[0]["content"]
    assert paragraph != bullets
    assert STYLES["bullets"] in bullets


def test_build_messages_rejects_unknown_style():
    with pytest.raises(ValueError):
        build_messages("x", "haiku")


def test_build_messages_constrains_to_source_text():
    system = build_messages("x", "tldr")[0]["content"].lower()
    assert "only information from the provided text" in system


# ---------------------------------------------------------------------------
# parse_usage
# ---------------------------------------------------------------------------


def test_parse_usage_reads_all_fields():
    usage = parse_usage(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}}
    )
    assert usage == Usage(prompt_tokens=10, completion_tokens=4, total_tokens=14)


def test_parse_usage_defaults_to_zero_when_missing():
    usage = parse_usage({})
    assert usage == Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)


def test_parse_usage_infers_total_when_absent():
    usage = parse_usage({"usage": {"prompt_tokens": 7, "completion_tokens": 3}})
    assert usage.total_tokens == 10


# ---------------------------------------------------------------------------
# extract_content
# ---------------------------------------------------------------------------


def test_extract_content_returns_message_text():
    response = {"choices": [{"message": {"content": "  a summary  "}}]}
    assert extract_content(response) == "a summary"


def test_extract_content_raises_on_bad_shape():
    with pytest.raises(ValueError):
        extract_content({"choices": []})


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


def test_format_report_contains_numbers_and_label():
    report = format_report(
        "test-model", Usage(100, 20, 120), 0.00123, source_tokens=90
    )
    assert "RUN REPORT" in report
    assert "test-model" in report
    assert "100" in report
    assert "0.001230" in report


def test_format_report_marks_estimate():
    report = format_report("m", Usage(1, 1, 2), 0.0, source_tokens=1, estimated=True)
    assert "ESTIMATE" in report


# ---------------------------------------------------------------------------
# summarise (estimate-only and with a faked API call)
# ---------------------------------------------------------------------------


def test_summarise_estimate_only_does_not_call_api(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("call_api should not run in estimate-only mode")

    monkeypatch.setattr(summariser, "call_api", explode)

    result = summariser.summarise(
        "some text to summarise",
        base_url="http://unused",
        model="m",
        style="bullets",
        temperature=0.0,
        max_tokens=64,
        price_in=3.0,
        price_out=15.0,
        estimate_only=True,
    )
    assert result["estimated"] is True
    assert result["summary"] is None
    assert result["usage"].completion_tokens == 64
    assert result["cost"] > 0


def test_summarise_uses_reported_usage(monkeypatch):
    fake_response = {
        "choices": [{"message": {"content": "the summary"}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    }
    monkeypatch.setattr(summariser, "call_api", lambda *a, **k: fake_response)

    result = summariser.summarise(
        "body",
        base_url="http://unused",
        model="m",
        style="paragraph",
        temperature=0.0,
        max_tokens=100,
        price_in=3.0,
        price_out=15.0,
    )
    assert result["summary"] == "the summary"
    assert result["usage"].prompt_tokens == 50
    assert result["cost"] == pytest.approx(50 / 1e6 * 3.0 + 10 / 1e6 * 15.0)


def test_summarise_falls_back_when_usage_absent(monkeypatch):
    fake_response = {"choices": [{"message": {"content": "a short summary"}}]}
    monkeypatch.setattr(summariser, "call_api", lambda *a, **k: fake_response)

    result = summariser.summarise(
        "body",
        base_url="http://unused",
        model="m",
        style="tldr",
        temperature=0.0,
        max_tokens=100,
        price_in=3.0,
        price_out=15.0,
    )
    assert result["usage"].prompt_tokens > 0
    assert result["usage"].completion_tokens > 0


# ---------------------------------------------------------------------------
# main / CLI
# ---------------------------------------------------------------------------


def test_main_estimate_only_prints_report(tmp_path, capsys):
    p = tmp_path / "doc.txt"
    p.write_text("A document about deployment checklists.", encoding="utf-8")

    code = summariser.main([str(p), "--estimate-only"])
    out = capsys.readouterr().out

    assert code == 0
    assert "ESTIMATE" in out
    assert "input tokens" in out


def test_main_json_output_is_valid_json(tmp_path, capsys):
    p = tmp_path / "doc.txt"
    p.write_text("A document about deployment checklists.", encoding="utf-8")

    code = summariser.main([str(p), "--estimate-only", "--json"])
    out = capsys.readouterr().out

    assert code == 0
    parsed = json.loads(out)
    assert parsed["estimated"] is True
    assert "usage" in parsed


def test_main_missing_file_returns_error_code(capsys):
    code = summariser.main(["no-such-file.txt", "--estimate-only"])
    err = capsys.readouterr().err
    assert code == 2
    assert "not found" in err.lower()

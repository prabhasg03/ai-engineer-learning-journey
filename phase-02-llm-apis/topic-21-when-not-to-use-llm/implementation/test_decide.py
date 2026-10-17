"""Tests for Topic 21 - the decision framework: constraints, candidates, trade-offs,
a justified choice, and the condition that would flip it.

Everything is offline and deterministic: no network, no randomness, no clock.
"""
from __future__ import annotations

import pytest

from decide import (
    CLASSICAL_ML_KINDS,
    DETERMINISTIC_KINDS,
    EXTRACTION_CRITERIA,
    KIND_CLASSIFIER,
    KIND_DETERMINISTIC,
    KIND_LARGE_LLM,
    KIND_LOOKUP,
    KIND_REGEX,
    KIND_SMALL_LLM,
    LLM_KINDS,
    Candidate,
    Criterion,
    Delta,
    Decision,
    apply_hard_constraints,
    choose_extraction,
    choose_faq,
    choose_task_type,
    cost_constraint,
    decide,
    deterministic_first,
    exactness_constraint,
    flip_thresholds,
    latency_constraint,
    never_llm_reason,
    offline_constraint,
    score_candidates,
    sensitivity,
    verifiability_gate,
)


# ---------------------------------------------------------------------------
# Fixtures: a small, readable candidate set
# ---------------------------------------------------------------------------
def code_candidate(**overrides) -> Candidate:
    """Deterministic code: cheap, exact, testable - but lower quality on hard input."""
    base = dict(
        name="code",
        kind=KIND_DETERMINISTIC,
        scores={"quality": 0.70, "cost": 0.55},
        latency_ms=3.0,
        cost_usd=0.0,
        exact=True,
        verifiable=True,
    )
    base.update(overrides)
    return Candidate(**base)


def llm_candidate(**overrides) -> Candidate:
    """An LLM: better quality, worse cost/latency, needs the network."""
    base = dict(
        name="llm",
        kind=KIND_SMALL_LLM,
        scores={"quality": 0.98, "cost": 0.20},
        latency_ms=900.0,
        cost_usd=0.0004,
        requires_network=True,
        exact=False,
        verifiable=True,
    )
    base.update(overrides)
    return Candidate(**base)


def quality_criteria() -> list[Criterion]:
    return [Criterion("quality", 0.70), Criterion("cost", 0.30)]


# ---------------------------------------------------------------------------
# Hard constraints
# ---------------------------------------------------------------------------
def test_hard_constraints_eliminate_and_report_the_reason():
    result = apply_hard_constraints([code_candidate(), llm_candidate()], [latency_constraint(50.0)])
    assert [c.name for c in result.survivors] == ["code"]
    assert result.reason_for("llm") == "latency <= 50ms"
    assert result.reason_for("code") is None
    assert any("latency" in line and "llm" in line for line in result.report())


def test_offline_and_exactness_constraints():
    offline = apply_hard_constraints([code_candidate(), llm_candidate()], [offline_constraint()])
    assert [c.name for c in offline.survivors] == ["code"]
    assert offline.reason_for("llm") == "offline / no network"

    approximate = llm_candidate(name="approximate")
    exact = apply_hard_constraints([code_candidate(), approximate], [exactness_constraint()])
    assert [c.name for c in exact.survivors] == ["code"]
    assert exact.reason_for("approximate") == "exact output required"


def test_hard_constraint_order_reports_the_first_failure_only():
    result = apply_hard_constraints(
        [llm_candidate()], [latency_constraint(50.0), cost_constraint(0.0001), offline_constraint()]
    )
    assert result.reason_for("llm") == "latency <= 50ms"
    assert len(result.eliminated) == 1


def test_a_budget_constraint_flips_the_choice_from_llm_to_code():
    criteria = quality_criteria()
    unbudgeted = decide([code_candidate(), llm_candidate()], criteria)
    assert unbudgeted.winner.name == "llm"          # the LLM wins on the soft scores

    squeezed = decide([code_candidate(), llm_candidate()], criteria, [cost_constraint(0.0)])
    assert squeezed.winner.name == "code"           # $0.0004/request is still too much
    assert squeezed.constraints.reason_for("llm") == "cost <= $0/request"
    assert squeezed.gate.allowed is True


def test_decide_raises_when_every_candidate_is_eliminated():
    with pytest.raises(ValueError, match="no candidate survives"):
        decide([llm_candidate()], quality_criteria(), [offline_constraint(), cost_constraint(0.0)])


def test_deterministic_first_lists_deterministic_candidates():
    regex = code_candidate(name="regex", kind=KIND_REGEX)
    lookup = code_candidate(name="lookup", kind=KIND_LOOKUP)
    found = deterministic_first([llm_candidate(), regex, lookup])
    assert [c.name for c in found] == ["regex", "lookup"]
    assert deterministic_first([llm_candidate()]) == []
    assert KIND_DETERMINISTIC in DETERMINISTIC_KINDS and KIND_LOOKUP in DETERMINISTIC_KINDS


def test_deterministic_option_eliminated_by_a_constraint_justifies_an_llm():
    slow_rules = code_candidate(name="rule-engine", latency_ms=5000.0)
    fast_llm = llm_candidate(name="quick-llm", latency_ms=900.0)
    decision = decide([slow_rules, fast_llm], quality_criteria(), [latency_constraint(1000.0)])
    assert decision.winner.name == "quick-llm"
    assert "eliminated by hard constraints" in decision.justification
    assert decision.winner.kind in LLM_KINDS


# ---------------------------------------------------------------------------
# Weighted ranking
# ---------------------------------------------------------------------------
def test_weighted_ranking_normalises_the_weights():
    ranked = score_candidates([code_candidate(), llm_candidate()], [Criterion("quality", 7.0), Criterion("cost", 3.0)])
    assert ranked.weight_total == pytest.approx(10.0)
    llm = ranked.by_name()["llm"]
    assert llm.total == pytest.approx(0.7 * 0.98 + 0.3 * 0.20)
    assert llm.contribution("quality") == pytest.approx(0.686)
    assert ranked.order() == ["llm", "code"]

    scaled = score_candidates([code_candidate(), llm_candidate()], [Criterion("quality", 0.7), Criterion("cost", 0.3)])
    assert scaled.order() == ranked.order()
    assert scaled.winner.total == pytest.approx(ranked.winner.total)


def test_missing_scores_and_empty_inputs_fail_loudly():
    with pytest.raises(ValueError, match="missing a score for criterion 'cost'"):
        score_candidates([Candidate("half", KIND_DETERMINISTIC, {"quality": 0.5})], quality_criteria())
    with pytest.raises(ValueError, match="no candidates"):
        score_candidates([], quality_criteria())
    with pytest.raises(ValueError, match="no criteria"):
        score_candidates([code_candidate()], [])
    with pytest.raises(ValueError, match="weights sum to 0"):
        score_candidates([code_candidate()], [Criterion("quality", 0.0)])
    with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
        Candidate("bad", KIND_DETERMINISTIC, {"quality": 1.5})


def test_tie_break_prefers_deterministic_then_alphabetical():
    zeta = code_candidate(name="zeta-code", scores={"quality": 0.5, "cost": 0.5})
    alpha = llm_candidate(name="alpha-llm", scores={"quality": 0.5, "cost": 0.5})
    beta = code_candidate(name="beta-code", scores={"quality": 0.5, "cost": 0.5})
    ranked = score_candidates([alpha, zeta, beta], quality_criteria())
    # deterministic candidates first (alphabetically), then the LLM
    assert ranked.order() == ["beta-code", "zeta-code", "alpha-llm"]
    assert ranked.winner.total == pytest.approx(0.5)


def test_criterion_direction_lower_inverts_the_ranking():
    # "error_rate" is a value-like axis where LOWER is better.
    higher = [Criterion("error_rate", 1.0, "higher")]
    lower = [Criterion("error_rate", 1.0, "lower")]
    good = code_candidate(name="good", scores={"error_rate": 0.05})
    bad = code_candidate(name="bad", scores={"error_rate": 0.40})
    assert score_candidates([good, bad], higher).order() == ["bad", "good"]
    assert score_candidates([good, bad], lower).order() == ["good", "bad"]
    with pytest.raises(ValueError, match="direction must be"):
        Criterion("x", 1.0, "sideways")


def test_invalid_weights_and_stakes_are_rejected():
    with pytest.raises(ValueError, match="weight must be"):
        Criterion("quality", -1.0)
    with pytest.raises(ValueError, match="stakes must be"):
        decide([code_candidate()], quality_criteria(), stakes="critical")


# ---------------------------------------------------------------------------
# Verifiability gate
# ---------------------------------------------------------------------------
def test_verifiability_gate_blocks_high_stakes_unverifiable_output():
    unverifiable = llm_candidate(name="rag", verifiable=False)
    verdict = verifiability_gate(unverifiable, stakes="high")
    assert verdict.allowed is False
    assert any("no cheap way to check" in w.message for w in verdict.blocking)
    assert bool(verdict) is False

    medium = verifiability_gate(unverifiable, stakes="medium")
    assert medium.allowed is True
    assert [w.severity for w in medium.warnings] == ["warn"]

    safe = verifiability_gate(code_candidate(), stakes="high")
    assert safe.allowed is True
    assert safe.warnings == []


def test_verifiability_gate_flags_exactness_and_rewards_a_verifier():
    verdict = verifiability_gate(llm_candidate(), stakes="medium", requires_exactness=True)
    assert verdict.allowed is False
    assert any("exactness is required" in w.message for w in verdict.blocking)

    with_verifier = verifiability_gate(llm_candidate(), stakes="high")
    assert with_verifier.allowed is True
    assert any("ship the verifier" in w.message for w in with_verifier.warnings)


def test_never_llm_reason_names_the_no_go_areas():
    for feature in ("arithmetic", "authorization", "cryptographic_exactness", "legal_exactness"):
        reason = never_llm_reason(feature)
        assert reason is not None and len(reason) > 20
    assert never_llm_reason("three-word summary") is None


# ---------------------------------------------------------------------------
# Sensitivity: what flips it
# ---------------------------------------------------------------------------
def test_flip_thresholds_find_the_fragile_axis():
    ranked = score_candidates([code_candidate(), llm_candidate()], quality_criteria())
    sensitivity_report = flip_thresholds(ranked)
    assert sensitivity_report.runner_up == "code"
    # margin = 0.746 - 0.655 = 0.091; dropping the winner's score by d costs w*d/W
    closest = sensitivity_report.closest
    assert closest is not None
    assert closest.criterion == "quality"
    assert closest.required_score_drop == pytest.approx(0.091 / 0.7)
    assert closest.feasible is True                     # 0.13 <= the 0.98 the LLM has
    assert "wins" in closest.narrative
    # ...while the cost axis cannot flip it on its own: 0.091 / 0.30 > the 0.20 the LLM has
    cost_finding = next(f for f in sensitivity_report.findings if f.criterion == "cost")
    assert cost_finding.required_score_drop == pytest.approx(0.091 / 0.3)
    assert cost_finding.feasible is False


def test_flip_thresholds_report_an_unreachable_single_axis():
    strong = code_candidate(name="strong", scores={"quality": 1.0, "cost": 1.0})
    weak = llm_candidate(name="weak", scores={"quality": 0.0, "cost": 0.0})
    ranked = score_candidates([strong, weak], quality_criteria())
    finding = flip_thresholds(ranked).closest
    assert finding is not None
    assert finding.feasible is False            # the margin is larger than the score itself
    assert "falls by >=" in finding.narrative


def test_sensitivity_detects_a_flip_and_reports_what_flips_it():
    decision = decide([code_candidate(), llm_candidate()], quality_criteria())
    checks = sensitivity(
        decision,
        [
            Delta("LLM quality collapses to 0.60", "quality", "llm", score_delta=-0.38),
            Delta("tiny nudge down to the LLM", "quality", "llm", score_delta=-0.01),
            Delta("code quality drops further", "quality", "code", score_delta=-0.20),
            Delta("quality weight x1.1", "quality", "llm", weight_multiplier=1.1),
        ],
    )
    flipped = [c for c in checks if c.flipped]
    assert [c.new_winner for c in flipped] == ["code"]     # only the collapse flips it
    assert flipped[0].delta.description == "LLM quality collapses to 0.60"
    assert "winner becomes code" in flipped[0].reason
    assert all("no flip" in c.reason for c in checks[1:])
    assert all(c.new_winner in {"code", "llm"} for c in checks)


def test_decide_states_a_justification_and_a_flip_condition():
    decision = decide([code_candidate(), llm_candidate()], quality_criteria(), stakes="medium")
    assert isinstance(decision, Decision)
    assert "llm" in decision.justification and "decisive axes" in decision.justification
    assert decision.flip_condition.startswith("if 'quality' for llm falls by >=")
    assert decision.alternatives == ["code"]
    report = decision.report()
    assert "DECISION" in report and "flip condition" in report and "most fragile axis" in report


def test_deterministic_first_applies_when_a_deterministic_option_wins():
    weak_llm = llm_candidate(name="tiny-llm", scores={"quality": 0.10, "cost": 0.50})
    decision = decide([code_candidate(), weak_llm], quality_criteria())
    assert decision.winner.name == "code"
    assert decision.winner.is_deterministic
    assert "deterministic-first rule applied" in decision.justification


# ---------------------------------------------------------------------------
# Classic flips: extraction
# ---------------------------------------------------------------------------
def test_regex_chosen_for_a_known_fixed_format():
    decision = choose_extraction("INV-1042 | 2026-04-18 | 250.00 USD", known_format=True)
    assert decision.winner.name == "regex-parser"
    assert decision.winner.kind == KIND_REGEX
    assert decision.winner.is_deterministic
    assert decision.winner.exact is True
    assert decision.winner.cost_usd == 0.0
    assert [c.name for c in decision.constraints.survivors] == [
        "regex-parser",
        "small-llm-structured",
        "large-llm-structured",
    ]
    assert decision.ranked.order()[1] == "small-llm-structured"
    assert "drifts" in decision.flip_condition


def test_llm_chosen_when_the_format_drifts_and_the_flip_is_named():
    decision = choose_extraction(
        "Invoice #A-77\nTotal: 250,00 EUR\nVAT: 20%", known_format=True, format_stability="drifting"
    )
    assert decision.winner.name == "small-llm-structured"
    assert decision.winner.kind == KIND_SMALL_LLM
    assert "frozen" in decision.flip_condition
    assert "regex-parser" in decision.flip_condition
    assert decision.ranked.order().index("regex-parser") == 2      # the parser is now the worst


def test_large_llm_chosen_for_unstructured_input():
    decision = choose_extraction("Dear Sir, please find attached the statement of account...", known_format=False)
    assert decision.winner.name == "large-llm-structured"
    assert decision.winner.kind == KIND_LARGE_LLM
    assert "published schema" in decision.flip_condition
    with pytest.raises(ValueError, match="format_stability"):
        choose_extraction("x", True, format_stability="chaotic")


def test_extraction_decision_under_a_latency_budget_drops_the_large_model():
    unstructured = choose_extraction("x", known_format=False)
    candidates = [score.candidate for score in unstructured.ranked.scores]
    squeezed = decide(candidates, EXTRACTION_CRITERIA, [latency_constraint(1000.0)])
    assert squeezed.winner.name == "small-llm-structured"          # 900ms fits, 2500ms does not
    assert squeezed.constraints.reason_for("large-llm-structured") == "latency <= 1000ms"
    assert squeezed.winner.kind in LLM_KINDS
    assert "eliminated by hard constraints" not in squeezed.justification   # the dead one was an LLM


# ---------------------------------------------------------------------------
# Classic flips: classifier vs generation, and FAQ lookup vs retrieval
# ---------------------------------------------------------------------------
def test_classifier_chosen_for_closed_set_labeling():
    decision = choose_task_type("Route this support ticket to the right team")
    assert decision.winner.name == "classifier"
    assert decision.winner.kind == KIND_CLASSIFIER
    assert decision.winner.kind in CLASSICAL_ML_KINDS
    assert decision.winner.latency_ms < 100
    assert "label set stops being fixed" in decision.flip_condition
    assert decision.gate.allowed is True

    sentiment = choose_task_type("Classify the sentiment of this review as positive or negative")
    assert sentiment.winner.name == "classifier"


def test_generation_chosen_for_open_ended_output():
    decision = choose_task_type("Summarise this customer email in three friendly bullets")
    assert decision.winner.name == "generation"
    assert "finite label set" in decision.flip_condition
    assert decision.ranked.by_name()["classifier"].total < decision.ranked.winner.total
    assert choose_task_type("Write an apology email for a late delivery").winner.name == "generation"


def test_faq_lookup_vs_retrieval_vs_rag():
    fixed = choose_faq(corpus_size=40)
    assert fixed.winner.name == "lookup-table"
    assert fixed.winner.kind == KIND_LOOKUP
    assert "fixed" in fixed.flip_condition

    varied = choose_faq(corpus_size=40, question_variety="paraphrased")
    assert varied.winner.name == "embedding-retrieval"
    assert "spanning several documents" in varied.flip_condition

    synthesis = choose_faq(corpus_size=5000, question_variety="varied", answers_span_documents=True)
    assert synthesis.winner.name == "rag-generation"
    assert "one retrievable chunk" in synthesis.flip_condition
    assert synthesis.gate.allowed is True      # low stakes: unverifiable RAG is a warn, not a block

    with pytest.raises(ValueError):
        choose_faq(corpus_size=0)
    with pytest.raises(ValueError, match="question_variety"):
        choose_faq(corpus_size=10, question_variety="anything")

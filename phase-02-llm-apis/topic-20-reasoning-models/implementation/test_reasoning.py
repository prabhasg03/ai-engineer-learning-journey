"""Tests for Topic 20 - reasoning/thinking tokens, billing, TTC, effort choice.

Everything is offline and deterministic: no network, no clock, no randomness.
"""
from __future__ import annotations

import pytest

from reasoning import (
    ADAPTIVE_THINKING_TARGETS,
    BASE_LATENCY_S,
    EFFORT_ORDER,
    EFFORT_TO_THINKING_BUDGET,
    MIN_THINKING_BUDGET,
    PRICE_TABLE,
    RECOMMENDED_REASONING_RESERVE,
    THINKING_TOKENS_PER_SECOND,
    VISIBLE_TOKENS_PER_SECOND,
    CompletionResult,
    Difficulty,
    Effort,
    EffortChoice,
    ModelSpec,
    OutcomeVerifier,
    ProcessVerifier,
    Sample,
    SubTask,
    TaskProfile,
    Usage,
    best_of_n,
    build_reasoning_prompt,
    choose_effort,
    cost_per_request,
    detect_and_strip_step_by_step,
    detect_step_by_step,
    difficulty_band,
    estimate,
    estimate_cost,
    majority_vote,
    meets_quality_bar,
    parallel_cost,
    planned_thinking_tokens,
    planner_worker_split,
    refine,
    recommended_reserve_warnings,
    route_turn,
    run_completion,
    serial_cost,
    validate_thinking_budget,
    will_fit,
)

SMALL = PRICE_TABLE["reasoning-small"]
LARGE = PRICE_TABLE["reasoning-large"]
FAST = PRICE_TABLE["fast-small"]


# ---------------------------------------------------------------------------
# The effort ladder and thinking budgets
# ---------------------------------------------------------------------------
def test_effort_budget_ladder_matches_medium_row():
    # The public one-number ladder is the MEDIUM-difficulty target.
    for effort in EFFORT_ORDER:
        assert EFFORT_TO_THINKING_BUDGET[effort] == ADAPTIVE_THINKING_TARGETS[effort][Difficulty.MEDIUM]
    assert EFFORT_TO_THINKING_BUDGET[Effort.NONE] == 0
    assert list(EFFORT_ORDER) == [
        Effort.NONE,
        Effort.MINIMAL,
        Effort.LOW,
        Effort.MEDIUM,
        Effort.HIGH,
        Effort.XHIGH,
        Effort.MAX,
    ]


def test_planned_thinking_monotonic_in_effort():
    # Strictly more thinking as effort rises on a medium prompt...
    medium = [planned_thinking_tokens(e, Difficulty.MEDIUM) for e in EFFORT_ORDER]
    assert medium == sorted(medium)
    assert len(set(medium)) == len(medium)
    # ...and never less as the prompt gets harder, at a fixed effort.
    for effort in EFFORT_ORDER:
        row = [planned_thinking_tokens(effort, d) for d in Difficulty]
        assert row == sorted(row)


def test_low_effort_skips_thinking_on_easy_prompt():
    # Adaptive semantics: low effort may skip thinking entirely on easy input.
    assert planned_thinking_tokens(Effort.LOW, Difficulty.EASY) == 0
    assert planned_thinking_tokens(Effort.LOW, Difficulty.HARD) > 0
    assert planned_thinking_tokens(Effort.MINIMAL, Difficulty.EASY) == 0
    # ...but a harder prompt earns thinking even at minimal effort.
    assert planned_thinking_tokens(Effort.MINIMAL, Difficulty.HARD) > 0


def test_none_effort_never_thinks_and_bands_are_ordered():
    for difficulty in Difficulty:
        assert planned_thinking_tokens(Effort.NONE, difficulty) == 0
    assert difficulty_band(0.1) is Difficulty.EASY
    assert difficulty_band(0.5) is Difficulty.MEDIUM
    assert difficulty_band(0.9) is Difficulty.HARD
    with pytest.raises(ValueError):
        difficulty_band(1.5)


# ---------------------------------------------------------------------------
# Manual extended-thinking budget validation (Anthropic-shaped)
# ---------------------------------------------------------------------------
def test_manual_budget_below_1024_rejected():
    validate_thinking_budget(MIN_THINKING_BUDGET, 4096)  # 1024 is the floor
    with pytest.raises(ValueError, match=">= 1024"):
        validate_thinking_budget(1023, 4096)
    with pytest.raises(TypeError):
        validate_thinking_budget(2048.0, 4096)  # type: ignore[arg-type]


def test_manual_budget_must_be_less_than_max_tokens():
    validate_thinking_budget(2047, 2048)
    with pytest.raises(ValueError, match="budget_tokens < max_tokens"):
        validate_thinking_budget(2048, 2048)
    with pytest.raises(ValueError, match="budget_tokens < max_tokens"):
        validate_thinking_budget(4096, 2048)


def test_interleaved_budget_may_exceed_max_tokens():
    # Interleaved thinking spans every thinking block in one turn, so its budget
    # is allowed to exceed max_tokens. The 1024 floor still applies.
    validate_thinking_budget(4096, 2048, interleaved=True)
    validate_thinking_budget(2048, 2048, interleaved=True)
    with pytest.raises(ValueError, match=">= 1024"):
        validate_thinking_budget(512, 2048, interleaved=True)


# ---------------------------------------------------------------------------
# Billing: thinking tokens are OUTPUT tokens
# ---------------------------------------------------------------------------
def test_thinking_tokens_billed_as_output():
    usage = Usage(input_tokens=800, visible_output_tokens=300, reasoning_tokens=4096)
    assert usage.billed_output_tokens == 300 + 4096
    assert usage.total_tokens == 800 + 300 + 4096

    breakdown = estimate_cost(usage, SMALL)
    assert breakdown.billed_output_tokens == 4396
    # billed_output * output price, reasoning included
    assert breakdown.output_cost == pytest.approx(4396 * 2.20 / 1_000_000)
    assert breakdown.reasoning_cost == pytest.approx(4096 * 2.20 / 1_000_000)
    assert breakdown.visible_output_cost == pytest.approx(300 * 2.20 / 1_000_000)
    assert breakdown.input_cost == pytest.approx(800 * 0.55 / 1_000_000)
    assert breakdown.total_cost == pytest.approx(0.00044 + 0.0096712)
    # Same visible output WITHOUT thinking is the cheap case.
    assert cost_per_request(800, 300, 0, SMALL) == pytest.approx(0.0011)
    assert cost_per_request(800, 300, 4096, SMALL) > cost_per_request(800, 300, 0, SMALL)


def test_reasoning_dominates_the_bill_on_a_thinking_heavy_call():
    usage = Usage(800, 300, 4096)
    breakdown = estimate_cost(usage, SMALL)
    assert breakdown.reasoning_share == pytest.approx(0.891, abs=0.002)
    # Thinking is charged at the OUTPUT rate, never the (cheaper) input rate.
    assert breakdown.reasoning_cost > SMALL.input_cost(4096)
    assert estimate_cost(Usage(100, 100, 0), LARGE).reasoning_cost == 0.0


def test_provider_usage_payloads_name_thinking_differently():
    usage = Usage(input_tokens=100, visible_output_tokens=50, reasoning_tokens=200)

    openai_payload = usage.to_usage_payload("openai")
    assert openai_payload["output_tokens"] == 250
    assert openai_payload["output_tokens_details"] == {"reasoning_tokens": 200}

    anthropic = usage.to_usage_payload("anthropic")
    assert anthropic["output_tokens_details"] == {"thinking_tokens": 200}
    # When streaming, the count only lands on the final message_delta.
    early = usage.to_usage_payload("anthropic", streaming=True, final_delta=False)
    assert early["output_tokens_details"] == {"thinking_tokens": None}
    late = usage.to_usage_payload("anthropic", streaming=True, final_delta=True)
    assert late["output_tokens_details"] == {"thinking_tokens": 200}

    assert usage.output_tokens_details("openai") == {"reasoning_tokens": 200}
    assert usage.output_tokens_details("anthropic") == {"thinking_tokens": 200}
    with pytest.raises(ValueError):
        usage.to_usage_payload("gemini")


# ---------------------------------------------------------------------------
# max_output_tokens: you can pay for thinking and get nothing back
# ---------------------------------------------------------------------------
def test_incomplete_when_thinking_eats_the_whole_budget():
    result = run_completion(
        prompt="prove the recurrence",
        input_tokens=1000,
        planned_thinking=30_000,
        planned_visible=500,
        max_output_tokens=20_000,
        price=SMALL,
    )
    assert isinstance(result, CompletionResult)
    assert result.status == "incomplete"
    assert result.incomplete_reason == "max_output_tokens"
    assert result.has_visible_output is False      # nothing visible at all
    assert result.usage.reasoning_tokens == 20_000  # it spent the whole cap
    assert result.usage.visible_output_tokens == 0
    # ...and the input plus the thinking are still billed.
    assert result.cost == pytest.approx(1000 * 0.55 / 1_000_000 + 20_000 * 2.20 / 1_000_000)
    assert result.cost > 0.0
    assert result.thought_summary is not None      # the summary is the only artefact


def test_truncated_mid_answer_is_also_incomplete():
    result = run_completion(
        prompt="write the report",
        input_tokens=500,
        planned_thinking=4096,
        planned_visible=800,
        max_output_tokens=4500,
        price=SMALL,
    )
    assert result.status == "incomplete"
    assert result.incomplete_reason == "max_output_tokens"
    assert result.usage.reasoning_tokens == 4096
    assert result.usage.visible_output_tokens == 4500 - 4096
    assert result.has_visible_output is True


def test_completed_when_output_budget_is_enough():
    thinking, visible = 4096, 800
    assert will_fit(thinking + visible, thinking, visible) is True
    assert will_fit(thinking + visible - 1, thinking, visible) is False
    result = run_completion(
        prompt="summarise",
        input_tokens=500,
        planned_thinking=thinking,
        planned_visible=visible,
        max_output_tokens=thinking + visible,
        price=SMALL,
    )
    assert result.finished is True
    assert result.incomplete_reason is None
    assert result.usage.billed_output_tokens == thinking + visible
    assert result.usage.reasoning_tokens == thinking


def test_reserve_warning_uses_openai_experimenting_advice():
    assert recommended_reserve_warnings(8000)  # headroom is thin
    assert recommended_reserve_warnings(RECOMMENDED_REASONING_RESERVE) == []
    assert recommended_reserve_warnings(RECOMMENDED_REASONING_RESERVE + 1) == []


# ---------------------------------------------------------------------------
# Parallel TTC: best-of-N, self-consistency, cost/latency shape
# ---------------------------------------------------------------------------
def test_best_of_n_picks_highest_scoring_sample():
    samples = [Sample("41", 0), Sample("42", 1), Sample("40", 2)]
    verifier = OutcomeVerifier({"42": 1.0, "41": 0.3, "40": 0.0})
    choice = best_of_n(samples, verifier)
    assert choice.sample.text == "42"
    assert choice.score == 1.0
    assert choice.tied == 1
    assert choice.used_tie_break is False
    with pytest.raises(ValueError):
        best_of_n([], verifier)


def test_best_of_n_tie_falls_back_to_the_tie_break_verifier():
    samples = [Sample("a", 0), Sample("b", 1)]
    verifier = OutcomeVerifier({"a": 0.5, "b": 0.5})
    assert best_of_n(samples, verifier).sample.text == "a"  # deterministic default
    tie_break = OutcomeVerifier({"a": 0.2, "b": 0.9})
    choice = best_of_n(samples, verifier, tie_break=tie_break)
    assert choice.sample.text == "b"
    assert choice.tied == 2
    assert choice.used_tie_break is True


def test_majority_vote_and_its_deterministic_tie_break():
    samples = [Sample("yes", 0), Sample("no", 1), Sample("yes", 2), Sample("yes", 3), Sample("maybe", 4)]
    choice = majority_vote(samples)
    assert choice.sample.text == "yes"
    assert choice.votes == 3
    assert choice.total_votes == 5
    assert choice.vote_share == pytest.approx(0.6)
    assert choice.tied == 1

    tied = majority_vote([Sample("first", 0), Sample("second", 1)])
    assert tied.sample.text == "first"       # earliest occurrence wins
    assert tied.tied == 2
    assert tied.vote_share == pytest.approx(0.5)
    with pytest.raises(ValueError):
        majority_vote([])


def test_process_verifier_scores_the_worst_step():
    verifier = ProcessVerifier({"check inputs": 1.0, "compute total": 0.2})
    assert verifier.score("check inputs; compute total") == 0.2
    mean = ProcessVerifier({"check inputs": 1.0, "compute total": 0.2}, aggregate="mean")
    assert mean.score("check inputs; compute total") == pytest.approx(0.6)
    assert verifier.score("") == 0.0


def test_serial_refine_shows_diminishing_returns():
    # Every step rewrites the previous version - the chain is serial, not N samples.
    rubric = {
        "draft(q)": 0.30,
        "draft(q);edited1": 0.70,
        "draft(q);edited1;edited2": 0.80,
        "draft(q);edited1;edited2;edited3": 0.85,
    }
    verifier = OutcomeVerifier(rubric)
    trace = refine("q", 3, verifier=verifier)
    assert len(trace.steps) == 4              # draft + 3 refinement steps
    assert trace.final_text == "draft(q);edited1;edited2;edited3"
    assert trace.scores == [0.30, 0.70, 0.80, 0.85]
    gains = [b.score - a.score for a, b in zip(trace.steps, trace.steps[1:])]
    assert gains == sorted(gains, reverse=True)
    assert gains[0] > gains[-1]
    assert trace.gain == pytest.approx(0.55)
    with pytest.raises(ValueError):
        refine("q", 0, verifier=verifier)


def test_parallel_cost_scales_while_latency_stays_one_sample():
    usage = Usage(1000, 300, 4096)
    one = estimate_cost(usage, SMALL).total_cost
    four_cached = parallel_cost(usage, SMALL, 4, cached_input=True)
    four_cold = parallel_cost(usage, SMALL, 4, cached_input=False)
    assert parallel_cost(usage, SMALL, 1) == pytest.approx(one)
    assert four_cached > one
    # A warm prefix cache makes the extra samples cheaper than a cold one.
    assert four_cached < four_cold
    assert four_cold == pytest.approx(4 * (1000 * 0.55 / 1_000_000 + 4396 * 2.20 / 1_000_000))
    with pytest.raises(ValueError):
        parallel_cost(usage, SMALL, 0)

    profile = TaskProfile("proof", difficulty=0.9, visible_output_tokens=300)
    single = estimate(profile, Effort.HIGH)
    parallel = estimate(profile, Effort.HIGH, samples=4)
    assert parallel.latency_s == pytest.approx(single.latency_s)
    assert parallel.cost_usd > single.cost_usd


def test_parallel_quality_only_improves_when_the_answer_is_verifiable():
    verifiable = TaskProfile("math", difficulty=0.9, verifiable=True)
    unverifiable = TaskProfile("write a poem", difficulty=0.9, verifiable=False)
    single_v = estimate(verifiable, Effort.HIGH)
    best4_v = estimate(verifiable, Effort.HIGH, samples=4)
    assert best4_v.quality > single_v.quality            # verifier raises the ceiling
    single_u = estimate(unverifiable, Effort.HIGH)
    best4_u = estimate(unverifiable, Effort.HIGH, samples=4)
    assert best4_u.quality == pytest.approx(single_u.quality)  # nothing to pick with
    assert best4_u.cost_usd > single_u.cost_usd                # but you still pay N x

    usage = Usage(500, 300, 4096)
    assert serial_cost(usage, SMALL, 8192) > estimate_cost(usage, SMALL).total_cost
    assert serial_cost(usage, SMALL, 0) == pytest.approx(estimate_cost(usage, SMALL).total_cost)


# ---------------------------------------------------------------------------
# Cost/latency/quality estimator and effort choice
# ---------------------------------------------------------------------------
def test_estimate_cost_and_latency_grow_with_effort():
    profile = TaskProfile("hard multi-step", difficulty=0.5, input_tokens=800, visible_output_tokens=300)
    estimates = [estimate(profile, effort) for effort in EFFORT_ORDER]
    costs = [e.cost_usd for e in estimates]
    latencies = [e.latency_s for e in estimates]
    qualities = [e.quality for e in estimates]
    assert costs == sorted(costs)
    assert len(set(round(c, 9) for c in costs)) == len(costs)   # strictly rising
    assert latencies == sorted(latencies)
    assert qualities == sorted(qualities)
    # Diminishing returns: the last rung buys far less quality per dollar.
    per_dollar_early = (qualities[3] - qualities[2]) / (costs[3] - costs[2])
    per_dollar_late = (qualities[6] - qualities[5]) / (costs[6] - costs[5])
    assert per_dollar_early > per_dollar_late
    # Latency is dominated by thinking, not by the visible answer.
    top = estimates[-1]
    base = BASE_LATENCY_S + profile.visible_output_tokens / VISIBLE_TOKENS_PER_SECOND
    assert top.latency_s == pytest.approx(base + top.thinking_tokens / THINKING_TOKENS_PER_SECOND)
    assert top.thinking_tokens == EFFORT_TO_THINKING_BUDGET[Effort.MAX]
    assert estimate(profile, Effort.NONE).thinking_tokens == 0


def test_choose_effort_stays_low_for_an_easy_profile():
    profile = TaskProfile("classify a support ticket", difficulty=0.1, latency_sensitive=True)
    assert meets_quality_bar(0.8, 0.8)  # a bar sits ON the estimate, it is not a measurement
    choice = choose_effort(profile, quality_bar=0.8)
    assert isinstance(choice, EffortChoice)
    assert choice.effort is Effort.NONE
    assert choice.estimate.thinking_tokens == 0
    assert choice.met_quality_bar is True
    assert choice.met_budget and choice.met_latency
    assert choice.estimate.cost_usd < 0.001
    # No thinking => latency is just the base plus the visible answer.
    assert choice.estimate.latency_s == pytest.approx(
        BASE_LATENCY_S + profile.visible_output_tokens / VISIBLE_TOKENS_PER_SECOND
    )


def test_choose_effort_escalates_on_a_hard_profile():
    easy = choose_effort(TaskProfile("lookup", difficulty=0.1), quality_bar=0.85)
    hard = choose_effort(TaskProfile("debug a race condition", difficulty=0.9), quality_bar=0.9)
    assert EFFORT_ORDER.index(hard.effort) > EFFORT_ORDER.index(easy.effort)
    assert hard.effort in (Effort.HIGH, Effort.XHIGH, Effort.MAX)
    assert hard.estimate.thinking_tokens >= EFFORT_TO_THINKING_BUDGET[Effort.HIGH]
    assert hard.estimate.quality >= 0.9
    # The ladder was walked in order and every rung is reported for auditing.
    assert [e.effort for e in hard.considered] == list(EFFORT_ORDER)[: EFFORT_ORDER.index(hard.effort) + 1]


def test_choose_effort_reports_when_a_budget_blocks_the_quality_bar():
    profile = TaskProfile("extract fields", difficulty=0.1)
    unbudgeted = choose_effort(profile, quality_bar=0.87)
    assert unbudgeted.met_quality_bar is True
    assert unbudgeted.effort is Effort.MEDIUM or EFFORT_ORDER.index(unbudgeted.effort) > EFFORT_ORDER.index(Effort.LOW)

    squeezed = choose_effort(profile, quality_bar=0.87, budget_usd=0.0015)
    assert squeezed.met_budget is False
    assert squeezed.met_quality_bar is True
    assert squeezed.effort is Effort.MAX          # escalated as far as allowed
    assert "relax" in squeezed.reason

    capped = choose_effort(TaskProfile("debug", difficulty=0.9), quality_bar=0.99, max_effort=Effort.MEDIUM)
    assert capped.effort is Effort.MEDIUM
    assert capped.met_quality_bar is False
    assert capped.estimate.quality < 0.99


# ---------------------------------------------------------------------------
# Prompting differences
# ---------------------------------------------------------------------------
def test_prompt_builder_gives_goals_and_never_scripts_the_process():
    prompt = build_reasoning_prompt(
        "Decide whether invoice INV-77 should be auto-approved.",
        constraints=["refunds above $500 need a human", "no PII in the output"],
        success_criteria=["returns approve/reject plus a one-line reason"],
        context=["policy v3 applies from 2026-01-01"],
        output_contract="JSON with keys decision, reason",
    )
    assert detect_step_by_step(prompt) == []
    assert "step by step" not in prompt.lower()
    assert "take a deep breath" not in prompt.lower()
    assert "# Goal" in prompt and "# Constraints" in prompt and "# Success criteria" in prompt
    assert "INV-77" in prompt
    assert "JSON with keys decision, reason" in prompt
    assert "short sentence stating what you are about to do" in prompt

    terse = build_reasoning_prompt("Answer in one word.", ask_for_preamble=False)
    assert "short sentence" not in terse
    with pytest.raises(ValueError):
        build_reasoning_prompt("   ")


def test_detect_and_strip_step_by_step_shows_what_to_delete():
    prompt = "Summarise this invoice. Think step by step. Return JSON with the total. Take a deep breath."
    assert detect_step_by_step(prompt) == ["think step by step", "take a deep breath"]
    cleaned, removed = detect_and_strip_step_by_step(prompt)
    assert removed == ["Think step by step.", "Take a deep breath."]
    assert detect_step_by_step(cleaned) == []
    assert cleaned == "Summarise this invoice. Return JSON with the total."
    assert detect_and_strip_step_by_step("Give the goal and the constraints.") == (
        "Give the goal and the constraints.",
        [],
    )


# ---------------------------------------------------------------------------
# Planner / worker routing
# ---------------------------------------------------------------------------
def reasoning_model() -> ModelSpec:
    return ModelSpec("reasoning-large", "reasoning", LARGE, est_input_tokens=800, est_output_tokens=400)


def fast_model() -> ModelSpec:
    return ModelSpec("fast-small", "fast", FAST)


def test_planner_worker_split_routes_hard_subtasks_to_the_reasoning_model():
    subtasks = [
        SubTask("parse the invoice header", difficulty=0.2, value="low"),
        SubTask("reconcile the totals across documents", difficulty=0.85, value="medium"),
        SubTask("decide the refund outcome", difficulty=0.4, value="high"),
    ]
    plan = planner_worker_split(reasoning_model(), fast_model(), subtasks)
    by_name = {a.subtask: a for a in plan.assignments}

    assert by_name["parse the invoice header"].model == "fast-small"
    assert by_name["reconcile the totals across documents"].model == "reasoning-large"
    assert "hard turn" in by_name["reconcile the totals across documents"].reason
    assert by_name["decide the refund outcome"].model == "reasoning-large"
    assert by_name["decide the refund outcome"].reason == "high-value turn"

    # The planning turn and the final audit are reasoning turns too.
    assert by_name["<plan>"].model == "reasoning-large"
    assert by_name["<audit>"].model == "reasoning-large"
    assert plan.reasoning_calls == 4
    assert plan.worker_calls == 1
    assert plan.summary() == {"plan_model_calls": 4, "worker_model_calls": 1, "total_calls": 5}


def test_planner_worker_split_validates_model_kinds_and_route_turn_rules():
    with pytest.raises(ValueError, match="kind='reasoning'"):
        planner_worker_split(fast_model(), fast_model(), [])
    with pytest.raises(ValueError, match="kind='fast'"):
        planner_worker_split(reasoning_model(), reasoning_model(), [])

    easy = route_turn(SubTask("lookup status", 0.1), fast_model(), reasoning_model())
    assert easy.model == "fast-small"
    planned = route_turn(SubTask("design the migration", 0.05, needs_planning=True), fast_model(), reasoning_model())
    assert planned.model == "reasoning-large"
    assert planned.reason == "needs planning/decomposition"

    no_value_bias = planner_worker_split(
        reasoning_model(),
        fast_model(),
        [SubTask("write the email", 0.2, value="high")],
        high_value_routes_to_planner=False,
        audit=False,
    )
    assert no_value_bias.worker_calls == 1
    assert no_value_bias.reasoning_calls == 1   # the planning turn only


def test_planner_worker_split_is_cheaper_than_all_reasoning_calls():
    subtasks = [SubTask(f"step {i}", difficulty=0.2, value="low") for i in range(8)]
    plan = planner_worker_split(reasoning_model(), fast_model(), subtasks, audit=False)
    specs = {reasoning_model().name: reasoning_model(), fast_model().name: fast_model()}
    plan_cost = sum(specs[a.model].call_cost(0) for a in plan.assignments)
    mixed = reasoning_model().call_cost(0) + 8 * fast_model().call_cost(0)
    all_reasoning = 9 * reasoning_model().call_cost(0)
    assert plan.worker_calls == 8
    assert plan_cost == pytest.approx(mixed)
    assert mixed < all_reasoning

"""Tests for Topic 19c - routing strategies, auto routing, affinity, market."""
from __future__ import annotations

import pytest

from routing import (
    AutoRouter,
    CostBased,
    Decision,
    Deployment,
    FakeClock,
    LatencyBased,
    LeastBusy,
    MarketOffer,
    RouteChoice,
    RoutingError,
    RoutingGroup,
    SessionAffinity,
    SimpleShuffle,
    UsageBased,
    heuristic_tier,
    market_route,
    score_prompt,
)


def dep(id, **kw):
    return Deployment(id=id, model=kw.pop("model", id), **kw)


def choice(rng=lambda: 0.5, now=0.0, usage=None):
    return RouteChoice(rng=rng, now=now, usage=usage or {})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
def test_simple_shuffle_is_weighted_and_deterministic():
    a, b = dep("a", weight=1.0), dep("b", weight=3.0)
    assert SimpleShuffle().select([a, b], choice(rng=lambda: 0.1)).id == "a"
    assert SimpleShuffle().select([a, b], choice(rng=lambda: 0.9)).id == "b"


def test_latency_based_prefers_the_fastest():
    a = dep("a")
    b = dep("b")
    a.record_success(800.0, now=0.0)
    b.record_success(120.0, now=0.0)
    assert LatencyBased().select([a, b], choice(now=1.0)).id == "b"


def test_latency_based_tries_untested_deployment_first():
    a = dep("a")
    b = dep("b")
    a.record_success(50.0, now=0.0)  # only a has data
    assert LatencyBased().select([a, b], choice(now=1.0)).id == "b"


def test_least_busy_picks_fewest_in_flight():
    a, b = dep("a", in_flight=4), dep("b", in_flight=1)
    assert LeastBusy().select([a, b], choice()).id == "b"


def test_cost_based_picks_cheapest():
    a, b = dep("a", cost_per_1k=0.5), dep("b", cost_per_1k=0.1)
    assert CostBased().select([a, b], choice()).id == "b"


def test_usage_based_balances_by_reported_usage():
    a, b = dep("a"), dep("b")
    ctx = choice(usage={"a": 0.95, "b": 0.10})
    assert UsageBased().select([a, b], ctx).id == "b"


# ---------------------------------------------------------------------------
# Group selection + cooldowns
# ---------------------------------------------------------------------------
def test_cooled_down_deployment_is_skipped():
    a, b = dep("a"), dep("b")
    a.cooldown_until = 100.0
    group = RoutingGroup("g", [a, b], strategy=LeastBusy())
    assert group.pick(choice(now=0.0)).id == "b"


def test_all_cooled_down_raises():
    a = dep("a")
    a.cooldown_until = 100.0
    group = RoutingGroup("g", [a], strategy=SimpleShuffle())
    with pytest.raises(RoutingError):
        group.pick(choice(now=0.0))


def test_record_failure_and_recovery():
    a = dep("a", cooldown_time=30.0)
    a.record_failure(now=0.0)
    assert not a.available(0.0)
    assert a.available(30.0)
    a.record_success(10.0, now=30.0)
    assert a.recent_latency(now=30.0) == 10.0


# ---------------------------------------------------------------------------
# Auto routing: the complexity scorer
# ---------------------------------------------------------------------------
def test_simple_question_is_simple():
    tier, cause, _ = heuristic_tier("What is the capital of France?")
    assert tier == "SIMPLE"
    assert cause == "complexity_scorer"


def test_two_reasoning_markers_short_circuit_to_reasoning():
    tier, cause, scores = heuristic_tier("Prove it step by step and derive the result")
    assert tier == "REASONING"
    assert cause == "literal_keyword_match"
    assert scores["reasoningMarkers"] >= 2


def test_code_and_technical_prompt_is_more_than_simple():
    tier, _, _ = heuristic_tier("Explain the async algorithm then show the sql")
    assert tier in ("MEDIUM", "COMPLEX", "REASONING")
    assert tier != "SIMPLE"


def test_medium_prompt_between_simple_and_complex():
    tier, cause, _ = heuristic_tier("Summarize this api response")
    assert tier == "MEDIUM"
    assert cause == "complexity_scorer"


def test_score_prompt_reports_all_seven_dimensions():
    scores = score_prompt("Write ```code``` with recursion, then prove it?")
    assert set(scores) == {
        "tokenCount",
        "codePresence",
        "reasoningMarkers",
        "technicalTerms",
        "simpleIndicators",
        "multiStepPatterns",
        "questionComplexity",
    }
    assert scores["codePresence"] == 1.0
    assert scores["questionComplexity"] == 1.0


def test_auto_router_routes_and_explains_cause():
    groups = {
        "SIMPLE": RoutingGroup("SIMPLE", [dep("s1")]),
        "MEDIUM": RoutingGroup("MEDIUM", [dep("m1")]),
        "REASONING": RoutingGroup("REASONING", [dep("r1")]),
    }
    router = AutoRouter(groups, rng=lambda: 0.5)
    decision = router.route("What is 2 + 2?")
    assert isinstance(decision, Decision)
    assert decision.tier == "SIMPLE"
    assert decision.deployment.id == "s1"
    assert decision.cause == "complexity_scorer"


def test_adaptive_exploration_overrides_the_heuristic():
    groups = {
        "SIMPLE": RoutingGroup("SIMPLE", [dep("s1")]),
        "COMPLEX": RoutingGroup("COMPLEX", [dep("c1")]),
    }
    router = AutoRouter(groups, rng=lambda: 0.5, explore=1.0)
    decision = router.route("What is the capital of France?")
    assert decision.cause == "adaptive_thompson_sampling"
    assert decision.tier in groups


def test_reward_updates_the_posterior():
    groups = {"SIMPLE": RoutingGroup("SIMPLE", [dep("s1")])}
    router = AutoRouter(groups)
    router.reward("SIMPLE", True)
    router.reward("SIMPLE", False)
    assert router.alpha["SIMPLE"] == 2.0
    assert router.beta["SIMPLE"] == 2.0


# ---------------------------------------------------------------------------
# Session affinity
# ---------------------------------------------------------------------------
def test_session_affinity_pins_the_same_deployment():
    a, b = dep("a"), dep("b")
    group = RoutingGroup("g", [a, b], strategy=SimpleShuffle(), affinity=SessionAffinity(enabled=True))
    first = group.pick(choice(rng=lambda: 0.95), session_id="s1")
    second = group.pick(choice(rng=lambda: 0.0), session_id="s1")
    assert first.id == second.id == "b"


def test_affinity_disabled_keeps_no_pins():
    group = RoutingGroup("g", [dep("a")], affinity=SessionAffinity(enabled=False))
    group.pick(choice(), session_id="s1")
    assert group.affinity._pins == {}


def test_affinity_ttl_expires():
    affinity = SessionAffinity(enabled=True, idle_ttl=10.0)
    affinity.pin("s1", "a", now=0.0)
    assert affinity.get("s1", now=5.0) == "a"
    assert affinity.get("s1", now=10.0) is None


def test_affinity_falls_through_when_pinned_deployment_is_cooled_down():
    a, b = dep("a"), dep("b")
    group = RoutingGroup("g", [a, b], strategy=SimpleShuffle(), affinity=SessionAffinity(enabled=True))
    group.pick(choice(rng=lambda: 0.95), session_id="s1")  # pins b
    b.cooldown_until = 100.0
    chosen = group.pick(choice(rng=lambda: 0.0, now=1.0), session_id="s1")
    assert chosen.id == "a"


# ---------------------------------------------------------------------------
# Hosted / market-based routing
# ---------------------------------------------------------------------------
OFFERS = [
    MarketOffer("openai/gpt-4o", price_per_1k=5.0, quality=0.90),
    MarketOffer("openai/gpt-4o-mini", price_per_1k=0.5, quality=0.70),
    MarketOffer("anthropic/claude", price_per_1k=3.0, quality=0.95),
]


def test_market_route_prefers_quality_by_default():
    assert market_route(OFFERS).model == "anthropic/claude"


def test_market_route_can_prefer_price():
    assert market_route(OFFERS, prefer="price").model == "openai/gpt-4o-mini"


def test_market_route_respects_filters_and_wildcards():
    chosen = market_route(OFFERS, max_price=1.0, allowed=["openai/*"])
    assert chosen.model == "openai/gpt-4o-mini"

    chosen = market_route(OFFERS, excluded=["openai/*"])
    assert chosen.model == "anthropic/claude"


def test_market_route_raises_when_nothing_qualifies():
    with pytest.raises(RoutingError):
        market_route(OFFERS, min_quality=0.99, max_price=0.1)

"""Tests for Topic 19a - ordered failover, fallback types, attribution, guards.

Everything is offline and deterministic: a "responder" stands in for the
network and a FakeClock stands in for wall time.
"""
from __future__ import annotations

from fallbacks import (
    Deployment,
    ErrorKind,
    FakeClock,
    ModelGroup,
    ProviderError,
    Router,
    fallback_type_for,
)


def dep(id_: str, model: str | None = None, max_input_tokens: int | None = None, cost: float = 0.0) -> Deployment:
    return Deployment(id_, model or id_, max_input_tokens=max_input_tokens, cost_per_1k_tokens=cost)


def base_groups() -> list[ModelGroup]:
    return [
        ModelGroup("primary", [dep("p1", "openai/gpt-a")]),
        ModelGroup("backup", [dep("b1", "anthropic/claude-b")]),
        ModelGroup("backup2", [dep("b2", "google/gemini-c")]),
    ]


def responder_ok(deployment: Deployment, tokens: int) -> str:
    return f"ok:{deployment.id}"


def responder_fail_primary(deployment: Deployment, tokens: int) -> str:
    if deployment.id == "p1":
        raise ProviderError(ErrorKind.RATE_LIMIT, "429 rate limited")
    return f"ok:{deployment.id}"


# ---------------------------------------------------------------------------
# Happy path + basic failover
# ---------------------------------------------------------------------------
def test_primary_serves_without_fallback():
    router = Router(base_groups(), responder_ok)
    log = router.completion("primary")
    assert log.ok
    assert log.served_model_group == "primary"
    assert log.served_by_fallback is False
    assert log.attempted_fallbacks == 0


def test_general_fallback_after_num_retries():
    calls: list[str] = []

    def responder(deployment: Deployment, tokens: int) -> str:
        calls.append(deployment.id)
        if deployment.id == "p1":
            raise ProviderError(ErrorKind.RATE_LIMIT, "429")
        return f"ok:{deployment.id}"

    router = Router(
        base_groups(), responder, fallbacks={"primary": ["backup"]}, num_retries=2
    )
    log = router.completion("primary")
    assert log.ok
    assert log.served_model_group == "backup"
    assert log.attempted_fallbacks == 1
    # primary deployment is tried 1 + num_retries times before failover
    assert calls.count("p1") == 3


def test_fallback_chain_is_in_order():
    def responder(deployment: Deployment, tokens: int) -> str:
        if deployment.id in ("p1", "b1"):
            raise ProviderError(ErrorKind.SERVER, "500")
        return f"ok:{deployment.id}"

    router = Router(base_groups(), responder, fallbacks={"primary": ["backup", "backup2"]})
    log = router.completion("primary")
    assert log.ok
    assert log.served_model_group == "backup2"
    assert log.attempted_fallbacks == 2


def test_original_model_group_recorded_on_fallback():
    router = Router(base_groups(), responder_fail_primary, fallbacks={"primary": ["backup"]})
    log = router.completion("primary")
    row = log.as_row()
    assert row["original_model_group"] == "primary"
    assert row["model_group"] == "backup"
    assert row["attempted_fallbacks"] == 1
    assert row["status"] == "success"


# ---------------------------------------------------------------------------
# The three fallback types
# ---------------------------------------------------------------------------
def test_content_policy_selects_content_policy_map():
    def responder(deployment: Deployment, tokens: int) -> str:
        if deployment.id == "p1":
            raise ProviderError(ErrorKind.CONTENT_POLICY, "content filtered")
        return f"ok:{deployment.id}"

    router = Router(
        base_groups(),
        responder,
        fallbacks={"primary": ["backup2"]},
        content_policy_fallbacks={"primary": ["backup"]},
    )
    log = router.completion("primary")
    # content_policy_fallbacks, not the general map, decides the target
    assert log.served_model_group == "backup"
    assert fallback_type_for(ErrorKind.CONTENT_POLICY) == "content_policy_fallbacks"


def test_context_window_fallback_needs_pre_call_checks():
    groups = [
        ModelGroup("tiny", [dep("t1", "openai/gpt-mini", max_input_tokens=10)]),
        ModelGroup("big-context", [dep("big1", "openai/gpt-big", max_input_tokens=100_000)]),
    ]

    def responder(deployment: Deployment, tokens: int) -> str:
        return f"ok:{deployment.id}:{tokens}"

    # Pre-call checks ON: a too-long prompt is caught before calling, and the
    # context-window fallback map is used.
    on = Router(
        groups,
        responder,
        context_window_fallbacks={"tiny": ["big-context"]},
        enable_pre_call_checks=True,
    )
    log = on.completion("tiny", tokens=50)
    assert log.ok
    assert log.served_model_group == "big-context"
    assert on._cooled_down("t1") is False  # context-window errors do not cool down here

    # Pre-call checks OFF: the prompt is sent, the stub accepts it, no fallback.
    off = Router(
        groups,
        responder,
        context_window_fallbacks={"tiny": ["big-context"]},
        enable_pre_call_checks=False,
    )
    log2 = off.completion("tiny", tokens=50)
    assert log2.served_model_group == "tiny"
    assert log2.served_by_fallback is False


def test_context_window_kind_maps_to_context_window_map():
    assert fallback_type_for(ErrorKind.CONTEXT_WINDOW) == "context_window_fallbacks"
    assert fallback_type_for(ErrorKind.RATE_LIMIT) == "fallbacks"


# ---------------------------------------------------------------------------
# default_fallbacks, precedence, disable
# ---------------------------------------------------------------------------
def test_default_fallbacks_used_when_group_has_no_specific_entry():
    router = Router(base_groups(), responder_fail_primary, default_fallbacks=["backup2"])
    log = router.completion("primary")
    assert log.served_model_group == "backup2"


def test_specific_entry_overrides_default():
    router = Router(
        base_groups(),
        responder_fail_primary,
        fallbacks={"primary": ["backup"]},
        default_fallbacks=["backup2"],
    )
    log = router.completion("primary")
    assert log.served_model_group == "backup"


def test_disable_fallbacks_per_request():
    router = Router(base_groups(), responder_fail_primary, fallbacks={"primary": ["backup"]})
    log = router.completion("primary", disable_fallbacks=True)
    assert log.ok is False
    assert log.attempted_fallbacks == 0
    assert log.served_model_group == "primary"


# ---------------------------------------------------------------------------
# Guards: key model access + budget
# ---------------------------------------------------------------------------
def test_key_model_access_enforced_on_fallbacks():
    router = Router(
        base_groups(),
        responder_fail_primary,
        fallbacks={"primary": ["backup"]},
        allowed_models=["primary"],  # key may not call the fallback group
    )
    log = router.completion("primary")
    assert log.ok is False
    assert log.attempted_fallbacks == 0  # unauthorised target is skipped


def test_budget_enforced_on_fallbacks():
    groups = [
        ModelGroup("primary", [dep("p1", cost=0.0)]),
        ModelGroup("expensive", [dep("e1", cost=5.0)]),
    ]
    router = Router(
        groups,
        responder_fail_primary,
        fallbacks={"primary": ["expensive"]},
        budget_ceiling=1.0,
    )
    log = router.completion("primary")
    assert log.ok is False
    assert log.attempted_fallbacks == 0


# ---------------------------------------------------------------------------
# Retries + cooldown interactions
# ---------------------------------------------------------------------------
def test_permanent_error_is_not_retried_within_group():
    calls: list[str] = []

    def responder(deployment: Deployment, tokens: int) -> str:
        calls.append(deployment.id)
        raise ProviderError(ErrorKind.AUTH, "401 unauthorised")

    router = Router(base_groups(), responder, num_retries=5)
    router.completion("primary", disable_fallbacks=True)
    assert calls.count("p1") == 1  # permanent error: one attempt only


def test_cooldown_after_allowed_fails_then_recovery():
    clock = FakeClock()
    calls: list[str] = []

    def responder(deployment: Deployment, tokens: int) -> str:
        calls.append(deployment.id)
        if deployment.id == "p1":
            raise ProviderError(ErrorKind.SERVER, "500")
        return f"ok:{deployment.id}"

    router = Router(
        base_groups(),
        responder,
        fallbacks={"primary": ["backup"]},
        num_retries=0,
        allowed_fails=1,
        cooldown_time=30.0,
        clock=clock,
    )
    first = router.completion("primary")
    assert first.served_model_group == "backup"
    # p1 failed once (allowed_fails=1) -> it is now cooling down
    assert router._cooled_down("p1") is True

    # While cooled down, p1 is skipped entirely.
    calls.clear()
    second = router.completion("primary")
    assert second.served_model_group == "backup"
    assert "p1" not in calls

    # After the cooldown expires, p1 is attempted again.
    clock.advance(31)
    assert router._cooled_down("p1") is False
    calls.clear()
    router.completion("primary")
    assert "p1" in calls


def test_attempt_log_records_every_try():
    router = Router(base_groups(), responder_fail_primary, fallbacks={"primary": ["backup"]})
    log = router.completion("primary")
    ids = [a.deployment_id for a in log.attempts]
    assert ids == ["p1", "b1"]
    assert log.attempts[0].ok is False
    assert log.attempts[1].ok is True


def test_failed_request_reports_error():
    def responder(deployment: Deployment, tokens: int) -> str:
        raise ProviderError(ErrorKind.OVERLOAD, "529 overloaded")

    router = Router(base_groups(), responder, fallbacks={"primary": ["backup", "backup2"]})
    log = router.completion("primary")
    assert log.ok is False
    assert log.attempted_fallbacks == 2
    assert log.error is not None

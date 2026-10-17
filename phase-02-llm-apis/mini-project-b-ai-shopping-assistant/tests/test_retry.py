"""Retry tests - the reliability contract, with no real sleeping.

Every test injects a ``FakeClock`` and a ``FakeRng`` so the delay schedule is
asserted exactly instead of being slept through.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.retry import (
    ApiError,
    ErrorKind,
    FakeClock,
    FakeRng,
    RetryError,
    RetryPolicy,
    backoff_delay,
    classify_error,
    parse_retry_after,
    retry_call,
    retry_or_raise,
)


def _policy(**over) -> RetryPolicy:
    base = dict(
        max_attempts=3,
        base=1.0,
        multiplier=2.0,
        max_delay=100.0,
        jitter="none",
        max_elapsed=None,
    )
    base.update(over)
    return RetryPolicy(**base)


def test_a_call_that_succeeds_first_time_is_not_retried():
    clock, rng = FakeClock(), FakeRng()
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        return "ok"

    outcome = retry_call(fn, _policy(), clock=clock, rng=rng)

    assert outcome.ok is True
    assert outcome.value == "ok"
    assert outcome.attempts == 1
    assert outcome.delays == []
    assert calls["n"] == 1
    assert clock.now() == 0.0


def test_a_transient_failure_is_retried_and_then_succeeds():
    """503 twice, then 200: the classic overload case."""
    clock, rng = FakeClock(), FakeRng()
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ApiError(503, "service unavailable")
        return "recovered"

    outcome = retry_call(fn, _policy(), clock=clock, rng=rng)

    assert outcome.ok is True
    assert outcome.value == "recovered"
    assert outcome.attempts == 3
    assert outcome.delays == [1.0, 2.0]  # exponential, jitter off
    assert outcome.total_slept == 3.0
    assert clock.now() == 3.0


def test_a_transient_failure_that_never_recovers_exhausts_the_budget_and_permanent_errors_do_not_retry():
    calls = {"n": 0}

    def always_transient() -> str:
        calls["n"] += 1
        raise ApiError(429, "rate limited")

    outcome = retry_call(always_transient, _policy(max_attempts=4), clock=FakeClock(), rng=FakeRng())

    assert outcome.ok is False
    assert outcome.attempts == 4
    assert calls["n"] == 4
    assert outcome.kind is ErrorKind.RATE_LIMIT
    assert isinstance(outcome.error, ApiError)

    permanent_calls = {"n": 0}

    def unauthorized() -> str:
        permanent_calls["n"] += 1
        raise ApiError(401, "unauthorized")

    permanent = retry_call(
        unauthorized, _policy(max_attempts=5), clock=FakeClock(), rng=FakeRng()
    )

    assert permanent.ok is False
    assert permanent_calls["n"] == 1  # a 401 is not going to fix itself
    assert permanent.attempts == 1
    assert permanent.delays == []
    assert permanent.kind is ErrorKind.CLIENT_PERMANENT


def test_retry_after_header_wins_over_the_computed_backoff_and_is_capped():
    """The server knows how long it needs; our jitter is only a fallback."""
    def fn() -> str:
        raise ApiError(429, "slow down", headers={"Retry-After": "7"})

    outcome = retry_call(
        fn,
        _policy(max_attempts=2, base=0.1),
        clock=FakeClock(),
        rng=FakeRng([1.0]),
    )

    assert outcome.retry_after_used is True
    assert outcome.delays == [7.0]  # header value, not the 0.1 s backoff
    assert outcome.total_slept == 7.0

    def reckless() -> str:
        raise ApiError(429, "wait", headers={"retry-after": "600"})

    capped = retry_call(
        reckless,
        _policy(max_attempts=2, max_delay=5.0),
        clock=FakeClock(),
        rng=FakeRng(),
    )

    assert capped.delays == [5.0]
    assert capped.retry_after_used is True


def test_backoff_delay_is_exponential_and_respects_the_ceiling():
    policy = _policy(base=0.5, multiplier=2.0, max_delay=3.0)
    rng = FakeRng()

    assert [backoff_delay(policy, n, rng) for n in (1, 2, 3, 4)] == [0.5, 1.0, 2.0, 3.0]

    full = _policy(base=1.0, multiplier=2.0, max_delay=10.0, jitter="full")
    delay = backoff_delay(full, 3, FakeRng([0.5]))  # uniform(0, 4) with rng 0.5
    assert delay == 2.0

    with pytest.raises(ValueError):
        backoff_delay(_policy(jitter="banana"), 1, FakeRng())


def test_max_elapsed_stops_the_call_from_sleeping_past_its_budget():
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise ApiError(500, "boom")

    outcome = retry_call(
        fn,
        _policy(max_attempts=5, base=10.0, max_elapsed=5.0),
        clock=FakeClock(),
        rng=FakeRng(),
    )

    assert outcome.ok is False
    assert calls["n"] == 1
    assert outcome.delays == []


@pytest.mark.parametrize(
    ("exc", "expected_kind", "retryable"),
    [
        (ApiError(429, "rate"), ErrorKind.RATE_LIMIT, True),
        (ApiError(400, "bad request"), ErrorKind.CLIENT_PERMANENT, False),
        (TimeoutError("read timed out"), ErrorKind.TIMEOUT, True),
        (ValueError("something odd"), ErrorKind.UNKNOWN, False),
    ],
)
def test_error_classification_decides_whether_to_retry(exc, expected_kind, retryable):
    kind, is_retryable = classify_error(exc)

    assert kind is expected_kind
    assert is_retryable is retryable


def test_parse_retry_after_handles_seconds_and_http_dates():
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after(" 2.5 ") == 2.5
    assert parse_retry_after("-4") == 0.0
    assert parse_retry_after("not a number") is None
    assert parse_retry_after(None) is None

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    later = "Thu, 01 Jan 2026 12:00:05 GMT"
    assert parse_retry_after(later, now=now) == 5.0


def test_retry_or_raise_surfaces_one_exception_type_at_the_boundary():
    def fn() -> str:
        raise ApiError(503, "down")

    with pytest.raises(RetryError) as excinfo:
        retry_or_raise(fn, _policy(max_attempts=2), clock=FakeClock(), rng=FakeRng())

    assert excinfo.value.attempts == 2
    assert excinfo.value.kind is ErrorKind.SERVER
    assert isinstance(excinfo.value.last_error, ApiError)

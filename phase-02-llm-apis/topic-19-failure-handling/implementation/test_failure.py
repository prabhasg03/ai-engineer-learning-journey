"""Topic 19 tests - error taxonomy, backoff + jitter, Retry-After, the retry
wrapper and the circuit breaker.

Deterministic by construction: a FakeClock records sleeps instead of blocking
and a FakeRng scales [0, 1] samples into the jitter range, so delay schedules
are asserted exactly.
"""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from failure_core import (
    ApiError,
    BreakerOpen,
    BreakerState,
    CircuitBreaker,
    ErrorKind,
    FakeClock,
    FakeRng,
    RetryPolicy,
    backoff_delay,
    call_with_breaker,
    classify_error,
    parse_retry_after,
    retry_after_from_headers,
    retry_call,
)


def always_raise(exc: BaseException):
    """Return a zero-arg callable that always raises ``exc``."""

    def fn():
        raise exc

    return fn


# --------------------------------------------------------------------------- #
# 1. Error taxonomy
# --------------------------------------------------------------------------- #


def test_rate_limit_429_is_transient():
    kind, retryable = classify_error(ApiError(429, "rate limit exceeded"))
    assert kind is ErrorKind.RATE_LIMIT
    assert retryable is True


def test_overload_529_is_transient():
    kind, retryable = classify_error(ApiError(529, "overloaded_error"))
    assert kind is ErrorKind.OVERLOAD
    assert retryable is True


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_transient(status):
    kind, retryable = classify_error(ApiError(status, "server error"))
    assert kind is ErrorKind.SERVER
    assert retryable is True


@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("read timeout"),
        ApiError(408, "request timeout"),
        RuntimeError("request timed out after 30s"),
    ],
)
def test_timeouts_are_transient(exc):
    kind, retryable = classify_error(exc)
    assert kind is ErrorKind.TIMEOUT
    assert retryable is True


@pytest.mark.parametrize(
    "exc", [ConnectionError("connection reset by peer"), RuntimeError("dns lookup failed")]
)
def test_network_errors_are_transient(exc):
    kind, retryable = classify_error(exc)
    assert kind is ErrorKind.NETWORK
    assert retryable is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_permanent(status):
    kind, retryable = classify_error(ApiError(status, "client error"))
    assert kind is ErrorKind.CLIENT_PERMANENT
    assert retryable is False


def test_conflict_409_is_transient():
    kind, retryable = classify_error(ApiError(409, "conflict"))
    assert kind is ErrorKind.CONFLICT
    assert retryable is True


def test_status_is_found_in_message_text_and_nested_response():
    kind, _ = classify_error(RuntimeError("Error code: 503 - service unavailable"))
    assert kind is ErrorKind.SERVER

    response = type("Resp", (), {"status_code": 429})()
    exc = type("APIStatusError", (Exception,), {"response": response})("slow down")
    kind, retryable = classify_error(exc)
    assert kind is ErrorKind.RATE_LIMIT and retryable is True


def test_unknown_error_is_not_retryable():
    kind, retryable = classify_error(ValueError("boom"))
    assert kind is ErrorKind.UNKNOWN
    assert retryable is False


# --------------------------------------------------------------------------- #
# 2. Retry-After parsing
# --------------------------------------------------------------------------- #


def test_parse_retry_after_seconds():
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("  2.5 ") == 2.5
    assert parse_retry_after("-5") == 0.0


def test_parse_retry_after_http_date():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert parse_retry_after(format_datetime(now + timedelta(seconds=7)), now=now) == pytest.approx(7.0)
    # A date in the past means "retry now", never a negative sleep.
    assert parse_retry_after(format_datetime(now - timedelta(seconds=5)), now=now) == 0.0


def test_retry_after_lookup_is_case_insensitive_and_garbage_safe():
    assert retry_after_from_headers({"retry-after": "2"}) == 2.0
    assert retry_after_from_headers({"Retry-After": " 2 "}) == 2.0
    assert retry_after_from_headers({"RETRY-AFTER": "2"}) == 2.0
    assert retry_after_from_headers({"X-Request-Id": "abc"}) is None
    assert retry_after_from_headers(None) is None
    assert parse_retry_after("soon") is None
    assert parse_retry_after("") is None
    assert parse_retry_after(None) is None


# --------------------------------------------------------------------------- #
# 3. Exponential backoff + jitter
# --------------------------------------------------------------------------- #


def test_no_jitter_delay_sequence_is_exact():
    clk = FakeClock()
    policy = RetryPolicy(max_attempts=4, base=0.5, multiplier=2.0, max_delay=60.0, jitter="none")
    out = retry_call(always_raise(ApiError(503)), policy, clk, FakeRng())
    assert out.ok is False
    assert out.attempts == 4
    assert out.delays == [0.5, 1.0, 2.0]          # base * 2**(attempt-1)
    assert out.total_slept == pytest.approx(3.5)
    assert clk.now() == pytest.approx(3.5)


def test_delay_is_capped_at_max_delay():
    policy = RetryPolicy(base=1.0, multiplier=10.0, max_delay=5.0, jitter="none")
    assert backoff_delay(policy, 1, FakeRng()) == 1.0
    assert backoff_delay(policy, 3, FakeRng()) == 5.0   # raw 100 -> capped


def test_full_jitter_spans_zero_to_delay():
    policy = RetryPolicy(base=1.0, multiplier=2.0, max_delay=10.0, jitter="full")
    assert backoff_delay(policy, 1, FakeRng([0.0])) == 0.0
    assert backoff_delay(policy, 3, FakeRng([1.0])) == 4.0   # capped 4.0 * 1.0
    for sample in (0.0, 0.25, 0.5, 0.75, 1.0):
        for attempt in (1, 2, 3):
            capped = min(policy.base * policy.multiplier ** (attempt - 1), policy.max_delay)
            delay = backoff_delay(policy, attempt, FakeRng([sample]))
            assert 0.0 <= delay <= capped


def test_equal_jitter_spans_half_to_full():
    policy = RetryPolicy(base=1.0, multiplier=2.0, max_delay=10.0, jitter="equal")
    assert backoff_delay(policy, 1, FakeRng([0.0])) == 0.5
    assert backoff_delay(policy, 1, FakeRng([1.0])) == 1.0
    assert backoff_delay(policy, 3, FakeRng([0.5])) == pytest.approx(3.0)  # 2.0 + 0.5*2.0


def test_decorrelated_jitter_uses_previous_delay_and_respects_cap():
    policy = RetryPolicy(base=0.5, multiplier=2.0, max_delay=10.0, jitter="decorrelated")
    d1 = backoff_delay(policy, 1, FakeRng([0.0]))                    # uniform(0.5, 1.5)
    d2 = backoff_delay(policy, 2, FakeRng([1.0]), prev_delay=d1)     # uniform(0.5, 1.5)
    d3 = backoff_delay(policy, 3, FakeRng([0.5]), prev_delay=d2)     # uniform(0.5, 4.5)
    assert (d1, d2, d3) == (0.5, 1.5, pytest.approx(2.5))

    capped = RetryPolicy(base=1.0, multiplier=2.0, max_delay=1.5, jitter="decorrelated")
    assert backoff_delay(capped, 2, FakeRng([1.0]), prev_delay=1.5) == 1.5


def test_unknown_jitter_mode_is_rejected():
    with pytest.raises(ValueError):
        backoff_delay(RetryPolicy(jitter="chaotic"), 1, FakeRng())


# --------------------------------------------------------------------------- #
# 4. The retry wrapper
# --------------------------------------------------------------------------- #


def test_succeeds_after_k_transient_failures():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ApiError(503, "server error")
        return "done"

    clk = FakeClock()
    policy = RetryPolicy(max_attempts=5, base=0.1, multiplier=2.0, max_delay=10.0, jitter="none")
    out = retry_call(fn, policy, clk, FakeRng())
    assert out.ok is True
    assert out.value == "done"
    assert out.attempts == 3
    assert len(calls) == 3
    assert out.delays == [0.1, 0.2]
    assert out.kind is None and out.error is None


def test_gives_up_after_max_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise ApiError(503)

    policy = RetryPolicy(max_attempts=6, base=0.5, multiplier=2.0, max_delay=60.0, jitter="none")
    out = retry_call(fn, policy, FakeClock(), FakeRng())
    assert out.ok is False
    assert out.attempts == 6 == len(calls)
    assert len(out.delays) == 5
    assert out.delays == [0.5, 1.0, 2.0, 4.0, 8.0]
    assert out.kind is ErrorKind.SERVER
    assert isinstance(out.error, ApiError)


def test_permanent_error_is_not_retried():
    calls = []

    def fn():
        calls.append(1)
        raise ApiError(401, "invalid api key")

    out = retry_call(fn, RetryPolicy(max_attempts=5), FakeClock(), FakeRng())
    assert out.ok is False
    assert out.attempts == 1
    assert calls == [1]
    assert out.delays == []
    assert out.total_slept == 0.0
    assert out.kind is ErrorKind.CLIENT_PERMANENT


def test_retry_after_seconds_overrides_backoff():
    exc = ApiError(429, "slow down", {"Retry-After": "4"})
    policy = RetryPolicy(max_attempts=3, base=0.5, multiplier=2.0, max_delay=10.0, jitter="none")
    out = retry_call(always_raise(exc), policy, FakeClock(), FakeRng())
    assert out.delays == [4.0, 4.0]          # server value, not 0.5/1.0
    assert out.total_slept == pytest.approx(8.0)
    assert out.retry_after_used is True
    assert out.kind is ErrorKind.RATE_LIMIT


def test_retry_after_is_capped_at_max_delay():
    exc = ApiError(503, "overloaded", {"retry-after": "300"})
    policy = RetryPolicy(max_attempts=2, base=0.5, max_delay=2.0, jitter="none")
    out = retry_call(always_raise(exc), policy, FakeClock(), FakeRng())
    assert out.delays == [2.0]
    assert out.retry_after_used is True


def test_retry_after_http_date_is_honoured():
    fixed_now = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
    header = format_datetime(fixed_now + timedelta(seconds=6))
    exc = ApiError(503, "unavailable", {"Retry-After": header})
    policy = RetryPolicy(max_attempts=2, base=0.5, max_delay=60.0, jitter="none")
    out = retry_call(always_raise(exc), policy, FakeClock(), FakeRng(), now_fn=lambda: fixed_now)
    assert out.delays == [pytest.approx(6.0)]
    assert out.retry_after_used is True


def test_max_elapsed_stops_retrying_early():
    policy = RetryPolicy(
        max_attempts=10, base=1.0, multiplier=1.0, max_delay=5.0, jitter="none", max_elapsed=2.5
    )
    out = retry_call(always_raise(ApiError(503)), policy, FakeClock(), FakeRng())
    assert out.ok is False
    assert out.attempts == 3               # third sleep would blow the budget
    assert out.delays == [1.0, 1.0]
    assert out.total_slept == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# 5. Circuit breaker
# --------------------------------------------------------------------------- #


def test_breaker_opens_after_threshold_failures():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, window=60.0, cooldown=30.0, clock=clk)
    assert breaker.state is BreakerState.CLOSED
    assert breaker.allow() is True
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.failure_count == 2
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN


def test_open_breaker_short_circuits_calls():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, window=60.0, cooldown=30.0, clock=clk)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.allow() is False            # still inside the cooldown

    calls = []

    def fn():
        calls.append(1)
        return "never"

    with pytest.raises(BreakerOpen):
        call_with_breaker(fn, breaker)
    assert calls == []                          # the dependency was not touched


def test_half_open_success_closes_the_breaker():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, window=60.0, cooldown=30.0, clock=clk)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN

    clk.sleep(30.0)                             # cooldown elapsed
    assert breaker.allow() is True
    assert breaker.state is BreakerState.HALF_OPEN

    breaker.record_success()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.failure_count == 0


def test_half_open_failure_reopens_the_breaker():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, window=60.0, cooldown=10.0, clock=clk)
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN

    clk.sleep(10.0)
    assert breaker.allow() is True
    assert breaker.state is BreakerState.HALF_OPEN
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN
    assert breaker.allow() is False             # cooldown restarts


def test_window_forgets_old_failures():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, window=10.0, cooldown=5.0, clock=clk)
    breaker.record_failure()
    clk.sleep(1.0)
    breaker.record_failure()
    clk.sleep(20.0)                             # both old failures fall out of the window
    breaker.record_failure()
    assert breaker.failure_count == 1
    assert breaker.state is BreakerState.CLOSED


def test_call_with_breaker_counts_only_transient_failures():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, window=60.0, cooldown=30.0, clock=clk)

    for _ in range(4):                          # 400s are the caller's fault, not the API's
        with pytest.raises(ApiError):
            call_with_breaker(always_raise(ApiError(400, "bad request")), breaker)
    assert breaker.state is BreakerState.CLOSED
    assert breaker.failure_count == 0

    for _ in range(2):                          # 503s are the dependency's fault
        with pytest.raises(ApiError):
            call_with_breaker(always_raise(ApiError(503, "server error")), breaker)
    assert breaker.state is BreakerState.OPEN


def test_call_with_breaker_returns_value_and_recovers():
    clk = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, window=60.0, cooldown=5.0, clock=clk)
    with pytest.raises(ApiError):
        call_with_breaker(always_raise(ApiError(503)), breaker)
    breaker.record_failure()
    assert breaker.state is BreakerState.OPEN

    clk.sleep(5.0)
    assert call_with_breaker(lambda: "healthy", breaker) == "healthy"
    assert breaker.state is BreakerState.CLOSED

"""Topic 19 - Failure handling: error taxonomy, retries with backoff + jitter,
Retry-After, timeouts, idempotency and a circuit breaker.

Scope note: this topic owns *retries*. Provider / model fallback chains
("the primary model failed, try the backup") are Topic 19a
(phase-02-llm-apis/topic-19a-fallbacks-failover) and are deliberately NOT
implemented here.

Everything is hand-written and deterministic: inject a ``FakeClock`` and a
``FakeRng`` and delay schedules can be asserted exactly.
"""
from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------- #
# Clocks and randomness (injected so behaviour is deterministic in tests)
# --------------------------------------------------------------------------- #


class FakeClock:
    """Monotonic fake clock: ``sleep`` advances ``now`` instead of blocking."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class SystemClock:
    """Real clock for production paths (monotonic, never goes backwards)."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeRng:
    """Deterministic stand-in for ``random.uniform(a, b)``.

    Values are drawn in order from [0, 1] and scaled into the requested range;
    the last value repeats once the list is exhausted so long schedules can be
    driven from a short list.
    """

    def __init__(self, values: Optional[List[float]] = None) -> None:
        self.values = list(values or [0.0])
        self.i = 0

    def uniform(self, a: float, b: float) -> float:
        if b < a:
            return a
        if self.i < len(self.values):
            v = self.values[self.i]
            self.i += 1
        else:
            v = self.values[-1] if self.values else 0.0
        return a + (b - a) * v


# --------------------------------------------------------------------------- #
# Error taxonomy
# --------------------------------------------------------------------------- #


class ErrorKind(str, Enum):
    """What an API error *is*, which determines whether to retry it."""

    RATE_LIMIT = "rate_limit"            # 429 - transient, often has Retry-After
    OVERLOAD = "overload"                # 529 (Anthropic "overloaded") - transient
    TIMEOUT = "timeout"                  # connect/read/overall or 408 - transient
    SERVER = "server"                    # 500 / 502 / 503 / 504 - transient
    CONFLICT = "conflict"                # 409 - retried by the OpenAI SDK
    CLIENT_PERMANENT = "client_permanent"  # 400 / 401 / 403 / 404 / 422 - do NOT retry
    NETWORK = "network"                  # connection reset / DNS - transient
    UNKNOWN = "unknown"                  # not classified, treated as permanent


#: HTTP status -> (kind, retryable)
_STATUS_KINDS: Dict[int, Tuple[ErrorKind, bool]] = {
    408: (ErrorKind.TIMEOUT, True),
    409: (ErrorKind.CONFLICT, True),
    429: (ErrorKind.RATE_LIMIT, True),
    529: (ErrorKind.OVERLOAD, True),  # Anthropic overloaded_error
}


class ApiError(Exception):
    """A mock/SDK-shaped API error carrying a status code and headers."""

    def __init__(
        self,
        status_code: int,
        message: str = "",
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.headers = dict(headers or {})


_STATUS_RE = re.compile(r"\b(400|401|403|404|408|409|422|429|529|5\d\d)\b")


def _status_of(exc: BaseException) -> Optional[int]:
    """Best-effort extraction of an HTTP status from any error object."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    match = _STATUS_RE.search(str(exc))
    if match:
        return int(match.group(1))
    return None


def _kind_for_status(status: int) -> Tuple[ErrorKind, bool]:
    if status in _STATUS_KINDS:
        return _STATUS_KINDS[status]
    if 500 <= status <= 599:
        return ErrorKind.SERVER, True
    if 400 <= status <= 499:
        return ErrorKind.CLIENT_PERMANENT, False
    return ErrorKind.UNKNOWN, False


def classify_error(exc: BaseException) -> Tuple[ErrorKind, bool]:
    """Classify an error as ``(ErrorKind, retryable)``.

    Retryable = transient: another attempt could plausibly succeed. Permanent
    errors (auth, bad request, not found, validation) must not be retried --
    retrying them just burns budget and can duplicate work.
    """
    if isinstance(exc, TimeoutError):  # covers socket.timeout
        return ErrorKind.TIMEOUT, True
    if isinstance(exc, ConnectionError):  # reset / refused / aborted
        return ErrorKind.NETWORK, True

    status = _status_of(exc)
    if status is not None:
        return _kind_for_status(status)

    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return ErrorKind.TIMEOUT, True
    if any(word in message for word in ("connection", "network", "dns", "unreachable")):
        return ErrorKind.NETWORK, True
    if isinstance(exc, OSError):
        return ErrorKind.NETWORK, True
    return ErrorKind.UNKNOWN, False


def error_headers(exc: BaseException) -> Dict[str, str]:
    """Pull HTTP-ish headers off an error object (SDK errors expose both)."""
    headers = getattr(exc, "headers", None)
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    return {}


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Parse a ``Retry-After`` header value into seconds from ``now``.

    The header is either a number of seconds (``"3"``) or an HTTP-date
    (``"Wed, 01 Jan 2026 12:00:05 GMT"``). Returns ``None`` when unparseable,
    and never a negative number.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (when - reference).total_seconds())


def retry_after_from_headers(
    headers: Optional[Mapping[str, str]], now: Optional[datetime] = None
) -> Optional[float]:
    """Case-insensitive ``Retry-After`` lookup (HTTP header names are not case
    sensitive, and servers differ: ``Retry-After`` vs ``retry-after``)."""
    if not headers:
        return None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            return parse_retry_after(str(value), now=now)
    return None


# --------------------------------------------------------------------------- #
# Retry policy: exponential backoff + jitter
# --------------------------------------------------------------------------- #

#: Allowed jitter modes.
JITTER_MODES = ("none", "full", "equal", "decorrelated")


@dataclass
class RetryPolicy:
    """Retry budget and backoff shape.

    ``max_attempts`` counts total tries (1 initial + max_attempts - 1 retries),
    matching ``max_retries = max_attempts - 1`` in the vendors' SDKs.
    """

    max_attempts: int = 3
    base: float = 0.5                     # first backoff in seconds
    multiplier: float = 2.0               # exponential growth per attempt
    max_delay: float = 60.0               # per-sleep ceiling
    jitter: str = "full"                  # none | full | equal | decorrelated
    max_elapsed: Optional[float] = None   # total sleep budget across retries


def backoff_delay(
    policy: RetryPolicy,
    attempt: int,
    rng: FakeRng,
    prev_delay: Optional[float] = None,
) -> float:
    """Delay before the try that follows failure number ``attempt``.

    Base::

        delay = min(base * multiplier ** (attempt - 1), max_delay)

    Jitter modes (jitter spreads retries so clients do not sync up into a
    thundering herd):

    * ``none``         -- the raw backoff
    * ``full``         -- ``uniform(0, delay)``
    * ``equal``        -- ``delay/2 + uniform(0, delay/2)``
    * ``decorrelated`` -- ``min(max_delay, uniform(base, prev * 3))``
    """
    if policy.jitter not in JITTER_MODES:
        raise ValueError(f"unknown jitter mode: {policy.jitter!r}")

    raw = policy.base * (policy.multiplier ** max(0, attempt - 1))
    capped = min(raw, policy.max_delay)

    if policy.jitter == "none":
        return capped
    if policy.jitter == "full":
        return rng.uniform(0.0, capped)
    if policy.jitter == "equal":
        half = capped / 2.0
        return half + rng.uniform(0.0, half)

    prev = policy.base if prev_delay is None else prev_delay
    return min(policy.max_delay, rng.uniform(policy.base, prev * 3.0))


# --------------------------------------------------------------------------- #
# The retry wrapper
# --------------------------------------------------------------------------- #


@dataclass
class RetryOutcome:
    """Everything you want to log about one wrapped call."""

    ok: bool
    value: Any = None
    error: Optional[Exception] = None
    kind: Optional[ErrorKind] = None
    attempts: int = 0
    delays: List[float] = field(default_factory=list)
    total_slept: float = 0.0
    retry_after_used: bool = False


def retry_call(
    fn: Callable[[], Any],
    policy: Optional[RetryPolicy] = None,
    clock: Any = None,
    rng: Any = None,
    sleep: Optional[Callable[[float], None]] = None,
    headers_of: Optional[Callable[[BaseException], Mapping[str, str]]] = None,
    now_fn: Optional[Callable[[], datetime]] = None,
) -> RetryOutcome:
    """Call ``fn`` with bounded exponential backoff.

    * permanent errors are returned immediately (never retried);
    * transient errors are retried up to ``policy.max_attempts`` tries;
    * a ``Retry-After`` header on the error wins over the computed backoff,
      capped at ``policy.max_delay``;
    * ``policy.max_elapsed`` caps the total time slept across the call.

    ``now_fn`` supplies wall-clock time for *HTTP-date* Retry-After values
    (inject it in tests for an exact result; numeric Retry-After ignores it).
    """
    pol = policy or RetryPolicy()
    clk = clock if clock is not None else SystemClock()
    gen = rng if rng is not None else random
    do_sleep = sleep if sleep is not None else clk.sleep
    get_headers = headers_of if headers_of is not None else error_headers
    wall_now = now_fn if now_fn is not None else (lambda: datetime.now(timezone.utc))

    delays: List[float] = []
    total = 0.0
    retry_after_used = False
    prev_delay: Optional[float] = None
    last_error: Optional[Exception] = None
    last_kind: Optional[ErrorKind] = None

    for attempt in range(1, pol.max_attempts + 1):
        try:
            value = fn()
            return RetryOutcome(
                ok=True,
                value=value,
                attempts=attempt,
                delays=delays,
                total_slept=total,
                retry_after_used=retry_after_used,
            )
        except Exception as exc:  # noqa: BLE001 - we classify, we do not swallow
            last_error = exc
            kind, retryable = classify_error(exc)
            last_kind = kind

            if not retryable or attempt >= pol.max_attempts:
                break

            server_delay = retry_after_from_headers(get_headers(exc), now=wall_now())
            if server_delay is not None:
                delay = min(server_delay, pol.max_delay)
                retry_after_used = True
            else:
                delay = backoff_delay(pol, attempt, gen, prev_delay)

            if pol.max_elapsed is not None and total + delay > pol.max_elapsed:
                break  # out of time budget: give up rather than sleep past it

            delays.append(delay)
            total += delay
            prev_delay = delay
            do_sleep(delay)

    return RetryOutcome(
        ok=False,
        error=last_error,
        kind=last_kind,
        attempts=len(delays) + 1 if last_error is not None else 0,
        delays=delays,
        total_slept=total,
        retry_after_used=retry_after_used,
    )


# --------------------------------------------------------------------------- #
# Circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
# --------------------------------------------------------------------------- #


class BreakerState(str, Enum):
    CLOSED = "closed"        # healthy: calls flow
    OPEN = "open"            # tripped: calls short-circuit
    HALF_OPEN = "half_open"  # one trial call allowed after the cooldown


class BreakerOpen(RuntimeError):
    """Raised when a call is rejected because the breaker is OPEN."""


@dataclass
class CircuitBreaker:
    """Stop hammering a dead dependency.

    Counts failures inside a rolling ``window``; ``failure_threshold`` failures
    within that window trip the breaker OPEN. After ``cooldown`` seconds the
    breaker allows a single HALF_OPEN trial: success closes it, failure re-opens
    it. Retries live *inside* a request; the breaker spans requests.
    """

    failure_threshold: int = 5
    window: float = 60.0
    cooldown: float = 30.0
    clock: Any = field(default_factory=SystemClock)

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _failures: List[float] = field(default_factory=list, init=False)
    _opened_at: Optional[float] = None

    # -- introspection ----------------------------------------------------- #
    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        self._prune(self.clock.now())
        return len(self._failures)

    # -- internal ---------------------------------------------------------- #
    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        self._failures = [t for t in self._failures if t >= cutoff]

    # -- public API -------------------------------------------------------- #
    def allow(self) -> bool:
        """True if a call may proceed; moves OPEN -> HALF_OPEN after cooldown."""
        now = self.clock.now()
        if self._state is BreakerState.OPEN:
            if self._opened_at is not None and now - self._opened_at >= self.cooldown:
                self._state = BreakerState.HALF_OPEN
                return True
            return False
        self._prune(now)
        return True

    def record_success(self) -> None:
        self._state = BreakerState.CLOSED
        self._failures.clear()
        self._opened_at = None

    def record_failure(self) -> None:
        now = self.clock.now()
        if self._state is BreakerState.HALF_OPEN:
            self._open(now)
            return
        self._failures.append(now)
        self._prune(now)
        if len(self._failures) >= self.failure_threshold:
            self._open(now)

    def _open(self, now: float) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = now


def call_with_breaker(fn: Callable[[], Any], breaker: CircuitBreaker) -> Any:
    """Run ``fn`` through a breaker; short-circuit when OPEN.

    Only *transient* failures count toward tripping the breaker -- a 400 means
    the request was wrong, not that the dependency is down.
    """
    if not breaker.allow():
        raise BreakerOpen("circuit breaker is open")
    try:
        value = fn()
    except Exception as exc:
        _, retryable = classify_error(exc)
        if retryable:
            breaker.record_failure()
        raise
    breaker.record_success()
    return value


__all__ = [
    "ApiError",
    "BreakerOpen",
    "BreakerState",
    "CircuitBreaker",
    "ErrorKind",
    "FakeClock",
    "FakeRng",
    "JITTER_MODES",
    "RetryOutcome",
    "RetryPolicy",
    "SystemClock",
    "backoff_delay",
    "call_with_breaker",
    "classify_error",
    "error_headers",
    "parse_retry_after",
    "retry_after_from_headers",
    "retry_call",
]

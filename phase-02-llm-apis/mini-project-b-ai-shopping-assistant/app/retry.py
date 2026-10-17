"""Hand-written retry with exponential backoff + jitter (topic 19).

Every *outbound* call in this project goes through :func:`retry_call`.  That
matters because an LLM endpoint is the least reliable dependency you are
likely to have: it rate-limits (429), it overloads (500/503/529), and it times
out.  Retrying is only safe for errors that are *transient*; a 400 or a 401
means the request itself is wrong and retrying just burns budget, so the
classifier refuses to retry those.

Design decisions (the LLM-specific ones are called out in the comments):

* The clock, the RNG and the sleep function are **injected**.  Production uses
  :class:`SystemClock` and the ``random`` module; tests inject
  :class:`FakeClock` + :class:`FakeRng` and can then assert an *exact* delay
  schedule instead of sleeping for real.
* Error classification is duck-typed, so this module has **no third-party
  imports** - it works on ``httpx.HTTPStatusError``, ``urllib`` errors, or a
  hand-rolled exception alike.
* ``Retry-After`` wins over our computed backoff: the server knows better than
  our jitter how long it needs.  It is still capped by ``max_delay`` so a
  hostile (or buggy) header cannot stall the request for an hour.
* ``max_elapsed`` caps the total sleep budget, which is what actually protects
  an interactive endpoint's latency tail.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Callable, Mapping, Optional

__all__ = [
    "ApiError",
    "ErrorKind",
    "FakeClock",
    "FakeRng",
    "JITTER_MODES",
    "RetryError",
    "RetryOutcome",
    "RetryPolicy",
    "SystemClock",
    "backoff_delay",
    "classify_error",
    "error_headers",
    "parse_retry_after",
    "retry_after_from_headers",
    "retry_call",
    "retry_or_raise",
]


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

    Values are drawn in order from ``[0, 1]`` and scaled into the requested
    range; the last value repeats once the list is exhausted so a long schedule
    can be driven from a short list.
    """

    def __init__(self, values: Optional[list[float]] = None) -> None:
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

    RATE_LIMIT = "rate_limit"              # 429 - transient, often has Retry-After
    OVERLOAD = "overload"                  # 529 ("overloaded") - transient
    TIMEOUT = "timeout"                    # 408 / connect / read timeout
    SERVER = "server"                      # 500/502/503/504 - transient
    CONFLICT = "conflict"                  # 409 - safe to retry
    CLIENT_PERMANENT = "client_permanent"  # 400/401/403/404/422 - do NOT retry
    NETWORK = "network"                    # connection reset / DNS - transient
    UNKNOWN = "unknown"                    # not classified -> treated as permanent


#: Specific status codes with a non-obvious classification.
_STATUS_KINDS: dict[int, tuple[ErrorKind, bool]] = {
    408: (ErrorKind.TIMEOUT, True),
    409: (ErrorKind.CONFLICT, True),
    429: (ErrorKind.RATE_LIMIT, True),
    529: (ErrorKind.OVERLOAD, True),
}


class ApiError(Exception):
    """A small SDK-shaped API error carrying a status code and headers.

    Used by the fake server in the tests and available to any caller that wants
    an explicit error object instead of an HTTP library's exception.
    """

    def __init__(
        self,
        status_code: int,
        message: str = "",
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code
        self.headers = dict(headers or {})


def _status_of(exc: BaseException) -> Optional[int]:
    """Best-effort extraction of an HTTP status from any error object.

    ``httpx.HTTPStatusError`` exposes ``.response.status_code``; ``urllib``
    raises ``HTTPError`` which *is* a response; our own :class:`ApiError`
    exposes ``.status_code``.  Falling back to a regex over ``str(exc)`` keeps
    the classifier useful for hand-rolled errors too.
    """
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value

    import re

    match = re.search(r"\b(4\d\d|5\d\d)\b", str(exc))
    return int(match.group(1)) if match else None


def _kind_for_status(status: int) -> tuple[ErrorKind, bool]:
    if status in _STATUS_KINDS:
        return _STATUS_KINDS[status]
    if 500 <= status <= 599:
        return ErrorKind.SERVER, True
    if 400 <= status <= 499:
        return ErrorKind.CLIENT_PERMANENT, False
    return ErrorKind.UNKNOWN, False


def classify_error(exc: BaseException) -> tuple[ErrorKind, bool]:
    """Classify an error as ``(ErrorKind, retryable)``.

    Retryable means transient: another attempt could plausibly succeed.
    Permanent errors (auth, bad request, not found, validation) must not be
    retried - retrying them wastes budget and can duplicate side effects.
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


def error_headers(exc: BaseException) -> dict[str, str]:
    """Pull HTTP-ish headers off an error object (SDKs expose both shapes)."""
    headers = getattr(exc, "headers", None)
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        return {str(k): str(v) for k, v in headers.items()}
    return {}


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """Parse a ``Retry-After`` value into seconds from ``now``.

    The header is either a number of seconds (``"3"``) or an HTTP-date
    (``"Wed, 01 Jan 2026 12:00:05 GMT"``).  Returns ``None`` when unparseable,
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
    """Case-insensitive ``Retry-After`` lookup (header names are not case sensitive)."""
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

    ``max_attempts`` counts total tries (1 initial + ``max_attempts - 1``
    retries), matching ``max_retries = max_attempts - 1`` in the vendor SDKs.
    """

    max_attempts: int = 3
    base: float = 0.5                    # first backoff in seconds
    multiplier: float = 2.0              # exponential growth per attempt
    max_delay: float = 8.0               # per-sleep ceiling
    jitter: str = "full"                 # none | full | equal | decorrelated
    max_elapsed: Optional[float] = 20.0  # total sleep budget across retries


def backoff_delay(
    policy: RetryPolicy,
    attempt: int,
    rng: Any,
    prev_delay: Optional[float] = None,
) -> float:
    """Delay *before* the try that follows failure number ``attempt``.

    Base::

        delay = min(base * multiplier ** (attempt - 1), max_delay)

    Jitter modes (jitter spreads retries so many clients do not re-sync into a
    thundering herd):

    * ``none``         - the raw backoff
    * ``full``         - ``uniform(0, delay)``
    * ``equal``        - ``delay/2 + uniform(0, delay/2)``
    * ``decorrelated`` - ``min(max_delay, uniform(base, prev * 3))``
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
    """Everything worth logging about one wrapped call."""

    ok: bool
    value: Any = None
    error: Optional[BaseException] = None
    kind: Optional[ErrorKind] = None
    attempts: int = 0
    delays: list[float] = field(default_factory=list)
    total_slept: float = 0.0
    retry_after_used: bool = False


class RetryError(RuntimeError):
    """Raised by :func:`retry_or_raise` when the retry budget is exhausted."""

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        kind: Optional[ErrorKind] = None,
        last_error: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.kind = kind
        self.last_error = last_error


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

    delays: list[float] = []
    total = 0.0
    retry_after_used = False
    prev_delay: Optional[float] = None
    last_error: Optional[BaseException] = None
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
        except BaseException as exc:  # we classify, we do not swallow
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


def retry_or_raise(fn: Callable[[], Any], policy: Optional[RetryPolicy] = None, **kwargs: Any) -> Any:
    """Convenience wrapper: return the value or raise :class:`RetryError`.

    The LLM client uses this so callers only have to handle one exception type
    at the boundary instead of the vendor's whole error tree.
    """
    outcome = retry_call(fn, policy, **kwargs)
    if not outcome.ok:
        raise RetryError(
            f"call failed after {outcome.attempts} attempt(s): {outcome.error}",
            attempts=outcome.attempts,
            kind=outcome.kind,
            last_error=outcome.error,
        ) from outcome.error
    return outcome.value

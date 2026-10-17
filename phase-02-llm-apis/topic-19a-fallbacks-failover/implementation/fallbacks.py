"""Topic 19a - Fallbacks / failover (ordered provider failover after retries).

A hand-written model of the failover semantics that production gateways
(LiteLLM, Cloudflare, OpenRouter) expose:

  * a request names a *model group*; the group's deployments are tried with
    ``num_retries`` retries each;
  * when the group still fails, the router fails over, IN ORDER, to the groups
    listed in the matching fallback map;
  * WHICH map is consulted depends on the error that ended the primary attempt:

        content-policy violation  -> content_policy_fallbacks
        context-window exceeded   -> context_window_fallbacks (pre-call check)
        everything else (429/5xx) -> fallbacks, then default_fallbacks

  * every attempt is recorded, so spend logs can distinguish a fallback-served
    request from a directly-served one (``attempted_fallbacks``,
    ``original_model_group``);
  * the calling key's model access and remaining budget are enforced on every
    fallback target before it is tried.

Model groups hold one or more deployments. A deployment is a concrete way to
serve the group (a provider + endpoint + its own limits/prices).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple


class ErrorKind(str, Enum):
    """The handful of error classes that drive failover decisions."""

    RATE_LIMIT = "rate_limit"          # 429
    OVERLOAD = "overload"             # 5xx / 529
    TIMEOUT = "timeout"               # connect/read/overall timeout
    SERVER = "server"                 # other 5xx
    CONTENT_POLICY = "content_policy"  # provider content filter
    CONTEXT_WINDOW = "context_window"  # prompt larger than the model window
    AUTH = "auth"                     # 401/403
    CLIENT = "client"                 # 400/404/422 - caller bug


# Errors that will not succeed by simply retrying the SAME deployment.
PERMANENT = {
    ErrorKind.AUTH,
    ErrorKind.CLIENT,
    ErrorKind.CONTENT_POLICY,
    ErrorKind.CONTEXT_WINDOW,
}

# 429/5xx/timeout are the transient errors general fallbacks exist for.
TRANSIENT = {ErrorKind.RATE_LIMIT, ErrorKind.OVERLOAD, ErrorKind.TIMEOUT, ErrorKind.SERVER}


class ProviderError(Exception):
    """An error raised by a provider call, tagged with its kind."""

    def __init__(self, kind: ErrorKind, message: str, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


@dataclass
class Deployment:
    """One concrete way to serve a model group (provider + endpoint)."""

    id: str
    model: str
    max_input_tokens: Optional[int] = None
    cost_per_1k_tokens: float = 0.0


@dataclass
class ModelGroup:
    """A logical model name, backed by one or more deployments."""

    name: str
    deployments: List[Deployment] = field(default_factory=list)


class FakeClock:
    """Deterministic clock so cooldown behaviour is testable."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# A responder plays the role of a network call: given a deployment and the
# prompt size, it returns completion text or raises ProviderError.
Responder = Callable[[Deployment, int], str]


@dataclass
class Attempt:
    group: str
    deployment_id: str
    error_kind: Optional[ErrorKind]
    ok: bool


@dataclass
class SpendLog:
    """The record a gateway writes per request, including attribution."""

    request_model_group: str          # what the client asked for
    served_model_group: str           # what actually answered
    attempted_fallbacks: int          # 0 == the requested group served it
    ok: bool
    output: Optional[str] = None
    error: Optional[str] = None
    attempts: List[Attempt] = field(default_factory=list)

    @property
    def served_by_fallback(self) -> bool:
        return self.attempted_fallbacks > 0

    def as_row(self) -> Dict[str, object]:
        """The shape written to a spend-log table."""
        return {
            "model_group": self.served_model_group,
            "original_model_group": self.request_model_group,
            "attempted_fallbacks": self.attempted_fallbacks,
            "status": "success" if self.ok else "failure",
        }


class Router:
    """Ordered failover after retries, with attribution and guards."""

    def __init__(
        self,
        groups: Sequence[ModelGroup],
        responder: Responder,
        *,
        fallbacks: Optional[Dict[str, List[str]]] = None,
        context_window_fallbacks: Optional[Dict[str, List[str]]] = None,
        content_policy_fallbacks: Optional[Dict[str, List[str]]] = None,
        default_fallbacks: Optional[List[str]] = None,
        num_retries: int = 0,
        request_timeout: Optional[float] = None,
        allowed_fails: Optional[int] = None,
        cooldown_time: float = 0.0,
        enable_pre_call_checks: bool = False,
        allowed_models: Optional[Sequence[str]] = None,
        budget_ceiling: Optional[float] = None,
        clock: Optional[FakeClock] = None,
    ) -> None:
        self.groups = {g.name: g for g in groups}
        self.responder = responder
        self.fallbacks = dict(fallbacks or {})
        self.context_window_fallbacks = dict(context_window_fallbacks or {})
        self.content_policy_fallbacks = dict(content_policy_fallbacks or {})
        self.default_fallbacks = list(default_fallbacks or [])
        self.num_retries = num_retries
        self.request_timeout = request_timeout
        self.allowed_fails = allowed_fails
        self.cooldown_time = cooldown_time
        self.enable_pre_call_checks = enable_pre_call_checks
        self.allowed_models = set(allowed_models) if allowed_models is not None else None
        self.budget_ceiling = budget_ceiling
        self.clock = clock or FakeClock()
        # Cooldown bookkeeping (circuit-breaker-lite, per deployment).
        self._failures: Dict[str, List[float]] = {}
        self._cooldown_until: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Deployment health
    # ------------------------------------------------------------------
    def _cooled_down(self, dep_id: str) -> bool:
        return self._cooldown_until.get(dep_id, 0.0) > self.clock.now()

    def _record_failure(self, dep: Deployment) -> None:
        if self.allowed_fails is None:
            return
        window = [t for t in self._failures.get(dep.id, []) if self.clock.now() - t < 60.0]
        window.append(self.clock.now())
        self._failures[dep.id] = window
        # Once the deployment reaches ``allowed_fails`` failures inside the
        # one-minute window, cool it down for ``cooldown_time`` seconds.
        if len(window) >= self.allowed_fails and self.cooldown_time:
            self._cooldown_until[dep.id] = self.clock.now() + self.cooldown_time

    def _record_success(self, dep: Deployment) -> None:
        self._failures.pop(dep.id, None)

    # ------------------------------------------------------------------
    # Guards applied to fallback targets
    # ------------------------------------------------------------------
    def _model_allowed(self, group: str) -> bool:
        return self.allowed_models is None or group in self.allowed_models

    def _affordable(self, group: str) -> bool:
        if self.budget_ceiling is None:
            return True
        group_obj = self.groups.get(group)
        if group_obj is None:
            return False
        cheapest = min((d.cost_per_1k_tokens for d in group_obj.deployments), default=0.0)
        return cheapest <= self.budget_ceiling

    # ------------------------------------------------------------------
    # One model group (all deployments, num_retries each)
    # ------------------------------------------------------------------
    def _attempt_group(
        self, group: str, tokens: int, attempts: List[Attempt]
    ) -> Tuple[Optional[str], Optional[ProviderError]]:
        mg = self.groups.get(group)
        if mg is None:
            return None, ProviderError(ErrorKind.CLIENT, f"no deployments for model group {group!r}")

        last: Optional[ProviderError] = None
        for dep in mg.deployments:
            if self._cooled_down(dep.id):
                continue
            for _ in range(self.num_retries + 1):
                # Pre-call context-window check: only runs when enabled, and
                # only needs a per-deployment max_input_tokens override.
                if (
                    self.enable_pre_call_checks
                    and dep.max_input_tokens is not None
                    and tokens > dep.max_input_tokens
                ):
                    last = ProviderError(
                        ErrorKind.CONTEXT_WINDOW,
                        f"{dep.model}: {tokens} tokens > max_input_tokens {dep.max_input_tokens}",
                    )
                    attempts.append(Attempt(group, dep.id, last.kind, False))
                    self._record_failure(dep)
                    break  # permanent for this deployment: do not retry

                try:
                    out = self.responder(dep, tokens)
                except ProviderError as exc:
                    last = exc
                    attempts.append(Attempt(group, dep.id, exc.kind, False))
                    self._record_failure(dep)
                    if exc.kind in PERMANENT:
                        break  # pointless to retry a permanent error
                    continue

                attempts.append(Attempt(group, dep.id, None, True))
                self._record_success(dep)
                return out, None

        if last is None:
            last = ProviderError(ErrorKind.CLIENT, f"all deployments for {group!r} are cooling down")
        return None, last

    def _chain_for(self, group: str, kind: ErrorKind) -> List[str]:
        """Pick the ordered fallback chain the error selects."""
        if kind is ErrorKind.CONTEXT_WINDOW:
            chain = self.context_window_fallbacks.get(group)
        elif kind is ErrorKind.CONTENT_POLICY:
            chain = self.content_policy_fallbacks.get(group)
        else:
            chain = self.fallbacks.get(group)
        if chain is None:
            # A group with no specific entry falls back to the default list.
            chain = self.default_fallbacks
        return list(chain or [])

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def completion(
        self, model_group: str, tokens: int = 0, *, disable_fallbacks: bool = False
    ) -> SpendLog:
        attempts: List[Attempt] = []

        out, err = self._attempt_group(model_group, tokens, attempts)
        if out is not None:
            return SpendLog(model_group, model_group, 0, True, output=out, attempts=attempts)

        log = SpendLog(model_group, model_group, 0, False, error=str(err), attempts=attempts)
        if disable_fallbacks:
            return log

        chain = self._chain_for(model_group, err.kind)  # type: ignore[union-attr]
        for target in chain:
            if not self._model_allowed(target):
                continue
            if not self._affordable(target):
                continue
            log.attempted_fallbacks += 1
            out, err2 = self._attempt_group(target, tokens, attempts)
            if out is not None:
                log.ok = True
                log.output = out
                log.error = None
                log.served_model_group = target
                return log
        return log


def fallback_type_for(kind: ErrorKind) -> str:
    """Name the fallback map a given error selects (for teaching/telemetry)."""
    if kind is ErrorKind.CONTEXT_WINDOW:
        return "context_window_fallbacks"
    if kind is ErrorKind.CONTENT_POLICY:
        return "content_policy_fallbacks"
    return "fallbacks"

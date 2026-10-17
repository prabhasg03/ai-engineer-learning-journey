"""Topic 19c - model routing for production.

19a decides *which group* to call after a failure; 19b exposes *one endpoint*.
19c decides *which deployment, and which tier*, before the call:

  * routing strategies inside a model group: simple-shuffle / latency-based /
    least-busy / cost-based / usage-based;
  * auto routing: score a prompt on seven cheap dimensions, map it to a tier
    (SIMPLE / MEDIUM / COMPLEX / REASONING), and record *why* it chose
    (``cause=``); keyword rules escalate, and an optional Thompson-sampling
    bandit explores cheaper tiers adaptively;
  * the hosted (market-based) contrast: pick by price/quality with
    allow/exclude wildcards;
  * session / deployment affinity with an idle TTL that falls through to the
    group when the pinned deployment is cooled down.

Everything takes injected clocks / RNGs so behaviour is deterministic offline.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Callable, Dict, List, Optional, Sequence, Tuple

TIERS = ("SIMPLE", "MEDIUM", "COMPLEX", "REASONING")


class RoutingError(Exception):
    """No deployment could serve the request."""


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# Deployments + strategies
# ---------------------------------------------------------------------------
@dataclass
class Deployment:
    id: str
    model: str
    provider: str = ""
    cost_per_1k: float = 0.0
    weight: float = 1.0
    latency_ttl: float = 60.0
    cooldown_time: float = 30.0
    in_flight: int = 0
    cooldown_until: float = 0.0
    # (timestamp, milliseconds)
    latency_samples: List[Tuple[float, float]] = field(default_factory=list)

    def available(self, now: float) -> bool:
        return now >= self.cooldown_until

    def record_success(self, latency_ms: float, now: float) -> None:
        self.latency_samples.append((now, latency_ms))
        self.latency_samples = [
            s for s in self.latency_samples if now - s[0] <= self.latency_ttl
        ]
        self.cooldown_until = 0.0

    def record_failure(self, now: float) -> None:
        self.cooldown_until = now + self.cooldown_time

    def recent_latency(self, now: float) -> Optional[float]:
        recent = [ms for ts, ms in self.latency_samples if now - ts <= self.latency_ttl]
        if not recent:
            return None
        return statistics.fmean(recent)


@dataclass
class RouteChoice:
    """Context a strategy needs: an RNG, the clock value, and usage counters."""

    rng: Callable[[], float] = field(default=lambda: 0.5)
    now: float = 0.0
    usage: Dict[str, float] = field(default_factory=dict)


class Strategy:
    name = "strategy"

    def select(self, candidates: Sequence[Deployment], ctx: RouteChoice) -> Deployment:
        raise NotImplementedError


class SimpleShuffle(Strategy):
    """The default: a weighted-random pick across healthy deployments."""

    name = "simple-shuffle"

    def select(self, candidates, ctx):
        total = sum(d.weight for d in candidates)
        roll = ctx.rng() * total
        cumulative = 0.0
        for deployment in candidates:
            cumulative += deployment.weight
            if roll < cumulative:
                return deployment
        return candidates[-1]


class LatencyBased(Strategy):
    """Send to whoever has been fastest recently (a light load balancer)."""

    name = "latency-based-routing"

    def select(self, candidates, ctx):
        def key(deployment: Deployment):
            latency = deployment.recent_latency(ctx.now)
            # No samples yet -> try it, so every deployment gets measured once.
            return (0, 0.0) if latency is None else (1, latency)

        return min(candidates, key=key)


class LeastBusy(Strategy):
    """Fewest in-flight requests first (pairs well with slow streams)."""

    name = "least-busy"

    def select(self, candidates, ctx):
        return min(candidates, key=lambda d: d.in_flight)


class CostBased(Strategy):
    """Cheapest deployment that is still healthy."""

    name = "cost-based-routing"

    def select(self, candidates, ctx):
        return min(candidates, key=lambda d: d.cost_per_1k)


class UsageBased(Strategy):
    """Balances by consumption of a quota (tpm/rpm) reported in ``ctx.usage``."""

    name = "usage-based-routing"

    def select(self, candidates, ctx):
        return min(candidates, key=lambda d: ctx.usage.get(d.id, 0.0))


# ---------------------------------------------------------------------------
# Session affinity
# ---------------------------------------------------------------------------
class SessionAffinity:
    """Pin a session to a model/deployment for a TTL; fall through when down.

    Defaults mirror LiteLLM: off by default, one-hour idle TTL.
    """

    def __init__(self, *, enabled: bool = False, idle_ttl: float = 3600.0) -> None:
        self.enabled = enabled
        self.idle_ttl = idle_ttl
        self._pins: Dict[str, Tuple[str, float, float]] = {}  # sid -> (dep_id, expiry, last)

    def pin(self, session_id: str, deployment_id: str, now: float) -> None:
        self._pins[session_id] = (deployment_id, now + self.idle_ttl, now)

    def get(self, session_id: str, now: float) -> Optional[str]:
        entry = self._pins.get(session_id)
        if entry is None:
            return None
        deployment_id, expiry, _ = entry
        if now >= expiry:
            self._pins.pop(session_id, None)
            return None
        return deployment_id

    def clear(self, session_id: str) -> None:
        self._pins.pop(session_id, None)


@dataclass
class RoutingGroup:
    """A model group: several deployments, one strategy, optional affinity."""

    name: str
    deployments: List[Deployment]
    strategy: Strategy = field(default_factory=SimpleShuffle)
    affinity: SessionAffinity = field(default_factory=SessionAffinity)

    def available(self, now: float) -> List[Deployment]:
        healthy = [d for d in self.deployments if d.available(now)]
        if not healthy:
            raise RoutingError(f"model group {self.name!r} has no healthy deployment")
        return healthy

    def pick(self, ctx: RouteChoice, session_id: Optional[str] = None) -> Deployment:
        if session_id and self.affinity.enabled:
            pinned = self.affinity.get(session_id, ctx.now)
            if pinned is not None:
                for deployment in self.deployments:
                    if deployment.id == pinned and deployment.available(ctx.now):
                        return deployment
                # Pinned deployment cooled down -> fall through and re-pin.
        chosen = self.strategy.select(self.available(ctx.now), ctx)
        if session_id and self.affinity.enabled:
            self.affinity.pin(session_id, chosen.id, ctx.now)
        return chosen


# ---------------------------------------------------------------------------
# Auto routing (complexity scorer)
# ---------------------------------------------------------------------------
_REASONING_MARKERS = (
    "prove", "derive", "step by step", "step-by-step", "chain of thought",
    "think carefully", "reason", "why does", "explain why", "analyze",
)
_MULTI_STEP = ("then", "after that", "first", "finally", "next", "and then")
_SIMPLE = ("what is", "who is", "when", "define", "translate", "hello", "hi ")
_TECHNICAL = (
    "algorithm", "complexity", "api", "sql", "regex", "kubernetes", "async",
    "recursion", "compile", "docker", "distributed", "consensus", "latency",
)
_CODE_HINT = re.compile(r"```|\bdef \b|\bclass \b|\bfunction\b|\bimport \b|[{};]|=>")


def score_prompt(prompt: str) -> Dict[str, float]:
    """Score a prompt on seven cheap, explainable dimensions."""
    lowered = prompt.lower()
    words = prompt.split()
    token_count = len(words)
    return {
        "tokenCount": float(token_count),
        "codePresence": float(bool(_CODE_HINT.search(prompt))),
        "reasoningMarkers": float(sum(1 for m in _REASONING_MARKERS if m in lowered)),
        "technicalTerms": float(sum(1 for t in _TECHNICAL if t in lowered)),
        "simpleIndicators": float(sum(1 for s in _SIMPLE if lowered.startswith(s))),
        "multiStepPatterns": float(sum(1 for m in _MULTI_STEP if m in lowered)),
        "questionComplexity": float(prompt.count("?")),
    }


def heuristic_tier(prompt: str) -> Tuple[str, str, Dict[str, float]]:
    """Map a prompt to a tier. Returns ``(tier, cause, scores)``.

    ``cause`` is one of the LiteLLM-style strings; here ``literal_keyword_match``
    for keyword escalation and ``complexity_scorer`` for the weighted score.
    """
    scores = score_prompt(prompt)

    # Keyword short-circuit: two or more reasoning markers always win.
    if scores["reasoningMarkers"] >= 2:
        return "REASONING", "literal_keyword_match", scores

    weighted = (
        0.10 * scores["tokenCount"]
        + 2.0 * scores["codePresence"]
        + 1.5 * scores["reasoningMarkers"]
        + 0.8 * scores["technicalTerms"]
        + 1.2 * scores["multiStepPatterns"]
        + 1.0 * scores["questionComplexity"]
        - 1.5 * scores["simpleIndicators"]
    )

    if weighted >= 6.0:
        tier = "REASONING"
    elif weighted >= 3.0:
        tier = "COMPLEX"
    elif weighted >= 1.0:
        tier = "MEDIUM"
    else:
        tier = "SIMPLE"
    return tier, "complexity_scorer", scores


@dataclass
class Decision:
    tier: str
    cause: str
    scores: Dict[str, float]
    deployment: Deployment


class AutoRouter:
    """Exposes an ``auto`` group: score the prompt, pick a tier, then a deployment.

    With ``explore > 0`` it occasionally samples a tier from a Beta posterior
    (Thompson sampling) so cheap tiers get a chance; ``reward()`` updates it.
    """

    def __init__(
        self,
        groups: Dict[str, RoutingGroup],
        *,
        rng: Callable[[], float] = lambda: 0.5,
        explore: float = 0.0,
    ) -> None:
        self.groups = groups
        self.rng = rng
        self.explore = explore
        self.alpha = {tier: 1.0 for tier in groups}
        self.beta = {tier: 1.0 for tier in groups}

    def _beta_sample(self, a: float, b: float) -> float:
        """Approximate Beta(a, b) using the k-th order statistic of uniforms."""
        n = int(round(a + b)) - 1
        if n <= 0:
            return self.rng()
        uniforms = sorted(self.rng() for _ in range(n))
        k = max(0, min(int(round(a)) - 1, n - 1))
        return uniforms[k]

    def _thompson(self, now: float) -> str:
        best_tier, best_value = None, -1.0
        for tier in self.groups:
            value = self._beta_sample(self.alpha[tier], self.beta[tier])
            if value > best_value:
                best_tier, best_value = tier, value
        return best_tier or next(iter(self.groups))

    def route(self, prompt: str, *, now: float = 0.0, session_id: Optional[str] = None) -> Decision:
        tier, cause, scores = heuristic_tier(prompt)
        if self.explore > 0.0 and self.rng() < self.explore:
            tier = self._thompson(now)
            cause = "adaptive_thompson_sampling"
        group = self.groups[tier]
        deployment = group.pick(RouteChoice(rng=self.rng, now=now), session_id=session_id)
        return Decision(tier=tier, cause=cause, scores=scores, deployment=deployment)

    def reward(self, tier: str, success: bool) -> None:
        if success:
            self.alpha[tier] = self.alpha.get(tier, 1.0) + 1.0
        else:
            self.beta[tier] = self.beta.get(tier, 1.0) + 1.0


# ---------------------------------------------------------------------------
# Hosted / market-based routing (the contrast)
# ---------------------------------------------------------------------------
@dataclass
class MarketOffer:
    model: str
    price_per_1k: float
    quality: float
    provider: str = ""


def market_route(
    offers: Sequence[MarketOffer],
    *,
    min_quality: float = 0.0,
    max_price: float = float("inf"),
    allowed: Optional[Sequence[str]] = None,
    excluded: Optional[Sequence[str]] = None,
    prefer: str = "quality",
) -> MarketOffer:
    """Hosted-market routing: filter by quality/price/wildcards, then pick.

    ``allowed`` / ``excluded`` use shell-style wildcards (``openai/*``,
    ``*/deprecated``). ``prefer`` is ``"quality"`` or ``"price"``.
    """
    allowed = list(allowed) if allowed is not None else ["*"]
    excluded = list(excluded or [])

    def wildcard_ok(name: str) -> bool:
        if any(fnmatch(name, pattern) for pattern in excluded):
            return False
        return any(fnmatch(name, pattern) for pattern in allowed)

    candidates = [
        offer
        for offer in offers
        if offer.quality >= min_quality
        and offer.price_per_1k <= max_price
        and wildcard_ok(offer.model)
    ]
    if not candidates:
        raise RoutingError("no offer satisfies the quality/price/wildcard filters")
    if prefer == "price":
        return min(candidates, key=lambda o: (o.price_per_1k, -o.quality))
    return max(candidates, key=lambda o: (o.quality, -o.price_per_1k))

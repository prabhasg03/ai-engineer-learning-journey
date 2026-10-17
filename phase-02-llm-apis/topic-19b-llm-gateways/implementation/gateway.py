"""Topic 19b - LLM gateways.

A hand-written model of what an LLM gateway (LiteLLM Proxy, Cloudflare AI
Gateway, OpenRouter) does for a fleet of apps:

  * ONE OpenAI-shaped endpoint for many models; the gateway fans the request
    out to the provider that actually owns the model;
  * virtual keys: per user/team/project model access, budgets and rate limits,
    with spend tracked per key/team/tag;
  * central controls: structured logs, guardrails (here: PII masking);
  * dynamic routes: versioned, code-free request flows built from nodes
    (conditional / percentage / rate-limit / budget-limit / model) with a
    fallback, deployable and roll-back-able without a code change.

The provider call is injected as a ``caller`` callable, so everything is
deterministic and offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


class GatewayError(Exception):
    """An error the gateway returns to the client, with an HTTP status."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@dataclass
class VirtualKey:
    """A per user/team/project credential with its own limits and spend."""

    key: str
    owner: str
    team: str
    allowed_models: set
    max_budget: float = float("inf")
    rpm_limit: int = 10 ** 9
    tpm_limit: int = 10 ** 12
    spend: float = 0.0
    request_times: List[float] = field(default_factory=list)
    token_events: List[Tuple[float, int]] = field(default_factory=list)
    tag_spend: Dict[str, float] = field(default_factory=dict)


@dataclass
class ModelDeployment:
    """Where a model name actually lives, and what it costs."""

    model: str
    provider: str
    input_cost_per_token: float = 0.0
    output_cost_per_token: float = 0.0


@dataclass
class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int


# Injected provider call: (deployment, messages, prompt_tokens) -> result.
Caller = Callable[[ModelDeployment, List[Dict[str, str]], int], CompletionResult]


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
class Guardrail:
    """Transform text before it leaves / reaches the client."""

    def mask(self, text: str) -> str:  # pragma: no cover - interface
        return text


class PIIMasker(Guardrail):
    """A tiny, deterministic PII masker (email / phone / card-like numbers)."""

    _EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    _PHONE = re.compile(r"\b(?:\+?\d[\d\s-]{7,}\d)\b")
    _CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")

    def mask(self, text: str) -> str:
        text = self._EMAIL.sub("[email]", text)
        text = self._CARD.sub("[card]", text)
        text = self._PHONE.sub("[phone]", text)
        return text


# ---------------------------------------------------------------------------
# Dynamic routes
# ---------------------------------------------------------------------------
@dataclass
class RouteContext:
    request_model: str
    metadata: Dict[str, Any]
    key: VirtualKey
    prompt_tokens: int


class RouteNode:
    """A node returns a model name to use, or None to fall through."""

    def resolve(self, ctx: RouteContext, rng: Callable[[], float], gateway: "Gateway") -> Optional[str]:
        raise NotImplementedError


class ModelNode(RouteNode):
    def __init__(self, model: str) -> None:
        self.model = model

    def resolve(self, ctx, rng, gateway):
        return self.model


class ConditionalNode(RouteNode):
    """If/else on request metadata, headers or body."""

    def __init__(self, predicate: Callable[[RouteContext], bool], when_true: str, when_false: str) -> None:
        self.predicate = predicate
        self.when_true = when_true
        self.when_false = when_false

    def resolve(self, ctx, rng, gateway):
        return self.when_true if self.predicate(ctx) else self.when_false


class PercentageNode(RouteNode):
    """Probabilistic split for A/B tests and gradual rollouts."""

    def __init__(self, choices: Sequence[Tuple[str, float]]) -> None:
        total = sum(weight for _, weight in choices)
        if total <= 0:
            raise ValueError("percentage weights must sum to > 0")
        self.choices = [(model, weight / total) for model, weight in choices]

    def resolve(self, ctx, rng, gateway):
        r = rng()
        cumulative = 0.0
        for model, weight in self.choices:
            cumulative += weight
            if r < cumulative:
                return model
        return self.choices[-1][0]


class RateLimitNode(RouteNode):
    """Switch to a fallback once a request quota is exceeded."""

    def __init__(self, bucket: str, period_s: float, limit: int, when_ok: str, when_exceeded: str) -> None:
        self.bucket = bucket
        self.period_s = period_s
        self.limit = limit
        self.when_ok = when_ok
        self.when_exceeded = when_exceeded

    def resolve(self, ctx, rng, gateway):
        if gateway.consume_rate_limit(self.bucket, self.period_s, self.limit, ctx.key.key):
            return self.when_ok
        return self.when_exceeded


class BudgetLimitNode(RouteNode):
    """Switch to a fallback once the key's spend passes a threshold."""

    def __init__(self, limit: float, when_ok: str, when_exceeded: str) -> None:
        self.limit = limit
        self.when_ok = when_ok
        self.when_exceeded = when_exceeded

    def resolve(self, ctx, rng, gateway):
        return self.when_ok if ctx.key.spend < self.limit else self.when_exceeded


@dataclass
class DynamicRoute:
    """A named, versioned flow of nodes ending in a model choice."""

    name: str
    nodes: List[RouteNode]

    def resolve(self, ctx: RouteContext, rng: Callable[[], float], gateway: "Gateway") -> str:
        for node in self.nodes:
            model = node.resolve(ctx, rng, gateway)
            if model:
                return model
        raise GatewayError(500, "route_error", f"route {self.name!r} produced no model")


class RouteRegistry:
    """Version + rollback for dynamic routes (no code change to re-route)."""

    def __init__(self) -> None:
        self._versions: Dict[str, Dict[str, DynamicRoute]] = {}
        self._live: Dict[str, str] = {}

    def publish(self, route: DynamicRoute, version: str) -> None:
        self._versions.setdefault(route.name, {})[version] = route

    def deploy(self, name: str, version: str) -> None:
        if version not in self._versions.get(name, {}):
            raise GatewayError(404, "route_version_not_found", f"{name}@{version}")
        self._live[name] = version

    def rollback(self, name: str, version: str) -> None:
        self.deploy(name, version)

    def get(self, name: str) -> Optional[DynamicRoute]:
        version = self._live.get(name)
        if version is None:
            return None
        return self._versions[name][version]

    def versions(self, name: str) -> List[str]:
        return sorted(self._versions.get(name, {}))


@dataclass
class LogRecord:
    key: str
    team: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost: float
    route: Optional[str]
    tags: List[str]


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------
class Gateway:
    def __init__(
        self,
        models: Sequence[ModelDeployment],
        caller: Caller,
        *,
        clock: Optional[FakeClock] = None,
        guardrails: Optional[Sequence[Guardrail]] = None,
        rng: Optional[Callable[[], float]] = None,
        routes: Optional[RouteRegistry] = None,
    ) -> None:
        self.models = {m.model: m for m in models}
        self.caller = caller
        self.clock = clock or FakeClock()
        self.guardrails = list(guardrails or [])
        self.rng = rng or (lambda: 0.5)
        self.routes = routes or RouteRegistry()
        self.keys: Dict[str, VirtualKey] = {}
        self.logs: List[LogRecord] = []
        self.team_spend: Dict[str, float] = {}
        self._buckets: Dict[str, List[float]] = {}

    def add_key(self, key: VirtualKey) -> None:
        self.keys[key.key] = key

    # -- rate limiting --------------------------------------------------
    def consume_rate_limit(self, bucket: str, period_s: float, limit: int, key_id: str) -> bool:
        now = self.clock.now()
        stamps = [t for t in self._buckets.get(bucket, []) if now - t < period_s]
        if len(stamps) >= limit:
            self._buckets[bucket] = stamps
            return False
        stamps.append(now)
        self._buckets[bucket] = stamps
        return True

    def _key_rpm_exceeded(self, key: VirtualKey) -> bool:
        now = self.clock.now()
        key.request_times = [t for t in key.request_times if now - t < 60.0]
        return len(key.request_times) >= key.rpm_limit

    # -- request handling ----------------------------------------------
    def completion(
        self,
        *,
        api_key: str,
        model: str,
        messages: List[Dict[str, str]],
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        prompt_tokens: int = 0,
        _is_fallback: bool = False,
    ) -> Dict[str, Any]:
        key = self.keys.get(api_key)
        if key is None:
            raise GatewayError(401, "invalid_api_key", "missing or unknown API key")

        ctx = RouteContext(model, dict(metadata or {}), key, prompt_tokens)
        route = self.routes.get(model)
        target = route.resolve(ctx, self.rng, self) if route else model

        if target not in key.allowed_models:
            raise GatewayError(403, "model_not_allowed", f"key {key.key!r} may not call {target!r}")

        deployment = self.models.get(target)
        if deployment is None:
            raise GatewayError(404, "model_not_found", f"no provider for {target!r}")

        if self._key_rpm_exceeded(key):
            raise GatewayError(429, "rate_limit_exceeded", f"key {key.key!r} over {key.rpm_limit} rpm")

        estimate = deployment.input_cost_per_token * (prompt_tokens + 64)
        if key.spend + estimate > key.max_budget:
            raise GatewayError(402, "budget_exceeded", f"key {key.key!r} over budget")

        # Guardrail the input.
        outbound = [dict(m) for m in messages]
        for message in outbound:
            content = message.get("content")
            if isinstance(content, str):
                for guard in self.guardrails:
                    content = guard.mask(content)
                message["content"] = content

        result = self.caller(deployment, outbound, prompt_tokens)

        cost = (
            deployment.input_cost_per_token * result.input_tokens
            + deployment.output_cost_per_token * result.output_tokens
        )
        key.spend += cost
        key.request_times.append(self.clock.now())
        key.token_events.append((self.clock.now(), result.input_tokens + result.output_tokens))
        for tag in tags or []:
            key.tag_spend[tag] = key.tag_spend.get(tag, 0.0) + cost
        self.team_spend[key.team] = self.team_spend.get(key.team, 0.0) + cost

        text = result.text
        for guard in self.guardrails:
            text = guard.mask(text)

        self.logs.append(
            LogRecord(
                key=key.key,
                team=key.team,
                model=target,
                provider=deployment.provider,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=cost,
                route=route.name if route else None,
                tags=list(tags or []),
            )
        )

        return {
            "id": f"chatcmpl-{len(self.logs)}",
            "object": "chat.completion",
            "model": target,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": result.input_tokens,
                "completion_tokens": result.output_tokens,
                "total_tokens": result.input_tokens + result.output_tokens,
            },
            "x_gateway": {
                "route": route.name if route else None,
                "tags": list(tags or []),
                "cost": cost,
            },
        }


def recommend_gateway(
    num_apps: int,
    *,
    shared_keys: bool = False,
    spend_visibility: bool = False,
    central_logs: bool = False,
    guardrails: bool = False,
    dynamic_routes: bool = False,
) -> Tuple[str, str]:
    """Defend gateway-vs-SDK for a given team size."""
    if num_apps > 1 or shared_keys or spend_visibility or central_logs or guardrails or dynamic_routes:
        reasons = []
        if num_apps > 1:
            reasons.append(f"{num_apps} apps")
        if shared_keys:
            reasons.append("shared keys")
        if spend_visibility:
            reasons.append("spend visibility")
        if central_logs:
            reasons.append("central logs")
        if guardrails:
            reasons.append("guardrails")
        if dynamic_routes:
            reasons.append("code-free routing")
        return "gateway", "use a gateway: " + ", ".join(reasons)
    return "sdk", "one app, one key, no shared controls: call the provider SDK directly"

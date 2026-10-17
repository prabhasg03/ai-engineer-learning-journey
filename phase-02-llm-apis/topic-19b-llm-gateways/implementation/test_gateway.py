"""Tests for Topic 19b - gateway fan-out, virtual keys, dynamic routes, guardrails."""
from __future__ import annotations

import pytest

from gateway import (
    BudgetLimitNode,
    ConditionalNode,
    CompletionResult,
    DynamicRoute,
    FakeClock,
    Gateway,
    GatewayError,
    ModelDeployment,
    ModelNode,
    PIIMasker,
    PercentageNode,
    RateLimitNode,
    VirtualKey,
    recommend_gateway,
)

MODELS = [
    ModelDeployment("gpt-small", "openai", 1e-6, 2e-6),
    ModelDeployment("claude-big", "anthropic", 5e-6, 15e-6),
    ModelDeployment("local-free", "local", 0.0, 0.0),
]


def echo_caller(deployment, messages, prompt_tokens):
    last = messages[-1]["content"] if messages else ""
    return CompletionResult("echo:" + last, prompt_tokens or 5, 10)


def fixed_caller(text="all good"):
    def caller(deployment, messages, prompt_tokens):
        return CompletionResult(text, prompt_tokens or 5, 10)

    return caller


def make_key(key="sk-1", models=("gpt-small",), **kw):
    return VirtualKey(key=key, owner="alice", team="eng", allowed_models=set(models), **kw)


def make_gateway(caller=None, **kw):
    return Gateway(MODELS, caller or echo_caller, **kw)


def chat(model, content="hi"):
    return {"model": model, "messages": [{"role": "user", "content": content}]}


# ---------------------------------------------------------------------------
# One endpoint, provider fan-out, OpenAI shape
# ---------------------------------------------------------------------------
def test_openai_shaped_response_and_provider_fanout():
    gw = make_gateway()
    gw.add_key(make_key(models=["gpt-small", "claude-big"]))
    resp = gw.completion(api_key="sk-1", model="claude-big", messages=[{"role": "user", "content": "hi"}], prompt_tokens=10)
    assert resp["object"] == "chat.completion"
    assert resp["model"] == "claude-big"
    assert resp["choices"][0]["message"]["content"] == "echo:hi"
    assert resp["usage"]["total_tokens"] == 20
    assert gw.logs[-1].provider == "anthropic"


def test_missing_key_is_401():
    gw = make_gateway()
    with pytest.raises(GatewayError) as exc:
        gw.completion(api_key="nope", model="gpt-small", messages=[{"role": "user", "content": "hi"}])
    assert exc.value.status == 401


def test_model_access_is_403():
    gw = make_gateway()
    gw.add_key(make_key(models=["gpt-small"]))
    with pytest.raises(GatewayError) as exc:
        gw.completion(api_key="sk-1", model="claude-big", messages=[{"role": "user", "content": "hi"}])
    assert exc.value.status == 403


def test_unknown_model_is_404():
    gw = make_gateway()
    gw.add_key(make_key(models=["ghost"]))
    with pytest.raises(GatewayError) as exc:
        gw.completion(api_key="sk-1", model="ghost", messages=[{"role": "user", "content": "hi"}])
    assert exc.value.status == 404


# ---------------------------------------------------------------------------
# Virtual-key budgets and rate limits
# ---------------------------------------------------------------------------
def test_budget_exceeded_is_402():
    gw = make_gateway()
    gw.add_key(make_key(models=["gpt-small"], max_budget=0.0))
    with pytest.raises(GatewayError) as exc:
        gw.completion(api_key="sk-1", model="gpt-small", messages=[{"role": "user", "content": "hi"}], prompt_tokens=100)
    assert exc.value.status == 402


def test_rpm_limit_is_429():
    gw = make_gateway()
    gw.add_key(make_key(models=["gpt-small"], rpm_limit=1))
    gw.completion(api_key="sk-1", model="gpt-small", messages=[{"role": "user", "content": "a"}])
    with pytest.raises(GatewayError) as exc:
        gw.completion(api_key="sk-1", model="gpt-small", messages=[{"role": "user", "content": "b"}])
    assert exc.value.status == 429


def test_spend_tracked_per_key_team_and_tag():
    gw = make_gateway()
    gw.add_key(make_key(models=["claude-big"]))
    gw.completion(
        api_key="sk-1",
        model="claude-big",
        messages=[{"role": "user", "content": "hi"}],
        prompt_tokens=10,
        tags=["trial"],
    )
    key = gw.keys["sk-1"]
    assert key.spend > 0
    assert gw.team_spend["eng"] == pytest.approx(key.spend)
    assert key.tag_spend["trial"] == pytest.approx(key.spend)
    assert gw.logs[-1].tags == ["trial"]


# ---------------------------------------------------------------------------
# Dynamic routes
# ---------------------------------------------------------------------------
def test_conditional_route_uses_metadata():
    gw = make_gateway()
    route = DynamicRoute(
        "support",
        [ConditionalNode(lambda ctx: ctx.metadata.get("user_plan") == "paid", "claude-big", "gpt-small")],
    )
    gw.routes.publish(route, "v1")
    gw.routes.deploy("support", "v1")
    gw.add_key(make_key(models=["gpt-small", "claude-big"]))

    paid = gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "hi"}], metadata={"user_plan": "paid"}, prompt_tokens=5)
    free = gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "hi"}], metadata={"user_plan": "free"}, prompt_tokens=5)
    assert paid["model"] == "claude-big"
    assert free["model"] == "gpt-small"
    assert paid["x_gateway"]["route"] == "support"


def test_percentage_route_split_is_deterministic():
    route = DynamicRoute("ab", [PercentageNode([("gpt-small", 0.9), ("claude-big", 0.1)])])

    low = make_gateway(rng=lambda: 0.05)
    low.routes.publish(route, "v1")
    low.routes.deploy("ab", "v1")
    low.add_key(make_key(models=["gpt-small", "claude-big"]))

    high = make_gateway(rng=lambda: 0.95)
    high.routes.publish(route, "v1")
    high.routes.deploy("ab", "v1")
    high.add_key(make_key(models=["gpt-small", "claude-big"]))

    assert low.completion(api_key="sk-1", model="ab", messages=[{"role": "user", "content": "x"}])["model"] == "gpt-small"
    assert high.completion(api_key="sk-1", model="ab", messages=[{"role": "user", "content": "x"}])["model"] == "claude-big"


def test_rate_limit_node_falls_back():
    gw = make_gateway()
    route = DynamicRoute("support", [RateLimitNode("support", 60.0, 1, "claude-big", "gpt-small")])
    gw.routes.publish(route, "v1")
    gw.routes.deploy("support", "v1")
    gw.add_key(make_key(models=["gpt-small", "claude-big"]))

    first = gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "a"}])
    second = gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "b"}])
    assert first["model"] == "claude-big"
    assert second["model"] == "gpt-small"


def test_budget_limit_node_falls_back():
    gw = make_gateway()
    route = DynamicRoute("support", [BudgetLimitNode(0.001, "claude-big", "gpt-small")])
    gw.routes.publish(route, "v1")
    gw.routes.deploy("support", "v1")
    gw.add_key(make_key(models=["gpt-small", "claude-big"]))
    # key.spend is 0, which is < 0.001, so the premium model is allowed
    assert gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "x"}])["model"] == "claude-big"
    # raise the spend above the threshold
    gw.keys["sk-1"].spend = 5.0
    assert gw.completion(api_key="sk-1", model="support", messages=[{"role": "user", "content": "x"}])["model"] == "gpt-small"


def test_route_versions_deploy_and_rollback():
    gw = make_gateway()
    gw.routes.publish(DynamicRoute("r", [ModelNode("gpt-small")]), "v1")
    gw.routes.publish(DynamicRoute("r", [ModelNode("claude-big")]), "v2")
    gw.add_key(make_key(models=["gpt-small", "claude-big"]))

    gw.routes.deploy("r", "v1")
    assert gw.completion(api_key="sk-1", model="r", messages=[{"role": "user", "content": "x"}])["model"] == "gpt-small"

    gw.routes.deploy("r", "v2")
    assert gw.completion(api_key="sk-1", model="r", messages=[{"role": "user", "content": "x"}])["model"] == "claude-big"

    gw.routes.rollback("r", "v1")
    assert gw.completion(api_key="sk-1", model="r", messages=[{"role": "user", "content": "x"}])["model"] == "gpt-small"
    assert gw.routes.versions("r") == ["v1", "v2"]


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
def test_guardrail_masks_pii_on_input():
    gw = make_gateway(guardrails=[PIIMasker()])
    gw.add_key(make_key(models=["gpt-small"]))
    resp = gw.completion(
        api_key="sk-1",
        model="gpt-small",
        messages=[{"role": "user", "content": "email me at a.b@example.com please"}],
    )
    content = resp["choices"][0]["message"]["content"]
    assert "[email]" in content
    assert "a.b@example.com" not in content


def test_guardrail_masks_pii_on_output():
    gw = make_gateway(caller=fixed_caller("call me on +1 555 123 4567"), guardrails=[PIIMasker()])
    gw.add_key(make_key(models=["gpt-small"]))
    resp = gw.completion(api_key="sk-1", model="gpt-small", messages=[{"role": "user", "content": "hi"}])
    assert "[phone]" in resp["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Gateway vs SDK
# ---------------------------------------------------------------------------
def test_recommend_gateway_sdk_vs_gateway():
    assert recommend_gateway(1)[0] == "sdk"
    assert recommend_gateway(3)[0] == "gateway"
    assert recommend_gateway(1, spend_visibility=True)[0] == "gateway"
    assert recommend_gateway(1, guardrails=True)[0] == "gateway"

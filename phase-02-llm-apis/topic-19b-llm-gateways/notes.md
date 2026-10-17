# Topic 19b — LLM gateways

**Before:** 19a · **Sources:** [LiteLLM AI Gateway](https://docs.litellm.ai/docs/simple_proxy) · [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/) · [Cloudflare — Dynamic routing](https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/)

**Done when:** you route two providers through one OpenAI-compatible endpoint
with per-key budgets, and can defend gateway-vs-SDK for a given team size.

## Learning checklist

- [ ] One endpoint for 100+ models: OpenAI-shaped requests, gateway fans out to the model's owning provider
- [ ] Virtual keys: per user/team/project models + budgets + rate limits; spend tracking per key/team/tag
- [ ] Central controls: logging (Langfuse/Datadog/OTel), guardrails (filters, PII masking), Admin UI
- [ ] Dynamic routes: conditional / percentage (A/B) / rate-limit / budget-limit nodes with fallback; version + rollback without code change
- [ ] Gateway vs SDK decision: gateway past one app/person or when keys/spend/central-logs/guardrails matter

---

## 1. What a gateway is for

Without a gateway every app talks to every provider directly: each app holds
provider keys, implements retries/fallbacks, and reports nothing centrally. A
gateway puts **one OpenAI-compatible endpoint** in front of many providers:

```
app  ──(OpenAI shape, one key)──▶  GATEWAY  ──▶  provider A
                                              ├─▶  provider B
                                              └─▶  self-hosted vLLM
```

The client still sends `POST /v1/chat/completions` with `{model, messages}`.
The gateway fans the request out to whichever provider owns that model, and
returns the provider's answer restamped into the OpenAI shape.

## 2. Virtual keys

A **virtual key** is a gateway-issued credential scoped to a user, team or
project. It carries:

| Field | Enforced as |
| --- | --- |
| allowed models | 403 if the requested model is not on the list |
| max budget ($) | 402 once spend would exceed the cap |
| rpm / tpm limits | 429 once the rate/window is exceeded |
| tags | spend attributed per tag (e.g. `trial`, `feature-x`) |

Spend is tracked per **key**, per **team** and per **tag**, so a chargeback or
dashboard is a query, not a spreadsheet. This is the single biggest reason
teams adopt a gateway.

## 3. Central controls

Because all traffic funnels through one process, you get, once, for every app:

- **Logging / observability** — every request logged with model, tokens, cost,
  latency, key/team/tag; exported to Langfuse / Datadog / OTel.
- **Guardrails** — input and output filters: PII masking, prompt-injection
  checks, banned-topic filters, length caps.
- **An Admin UI** — create keys, set budgets, watch spend, flip routes.

## 4. Dynamic routes

A **dynamic route** is a named, versioned request flow you build visually or as
JSON — and change **without touching application code**. Node types:

| Node | Behaviour |
| --- | --- |
| Start | entry point |
| Conditional | If/Else on request body / headers / metadata (`user_plan == "paid"`) |
| Percentage | probabilistic split — A/B tests, gradual rollouts |
| Model | call a provider/model |
| Rate Limit | enforce a request quota per key/period; switch to fallback when exceeded |
| Budget Limit | enforce a cost quota per key/period; switch to fallback when exceeded |
| End | return the final response |

```json
{
  "route": "support",
  "nodes": [
    {"type": "conditional", "if": "user_plan == 'paid'", "then": "o4-mini-high", "else": "gpt-4.1"},
    {"type": "model", "provider": "openai", "model": "gpt-4.1"}
  ]
}
```

**Versions + rollback**: each edit produces a draft; you *deploy* a version to
make it live and can roll back instantly. Dynamic routes accept the OpenAI chat
completions shape only and are scoped to the gateway that defined them.

## 5. Gateway vs SDK — the decision

| Situation | Choose |
| --- | --- |
| One app, one person, one key | **SDK** (direct to the provider) |
| Several apps/users sharing keys, budgets | **Gateway** |
| You need spend visibility / chargeback | **Gateway** |
| Central logging, guardrails, PII masking | **Gateway** |
| Code-free routing, A/B, rollout/rollback | **Gateway** |

Rule of thumb: **past one app or one person, or the moment keys/spend/central
logs/guardrails matter, use a gateway.** Below that the extra hop and config
are pure overhead.

## 6. Implementation walkthrough (`gateway.py`)

- `VirtualKey` — allowed models, `max_budget`, `rpm_limit`, and mutable `spend`,
  `request_times`, `token_events`, `tag_spend`.
- `ModelDeployment` — where a model lives (`provider`) and its per-token prices.
- `Gateway.completion(api_key, model, messages, tags, metadata, prompt_tokens)`:
  1. authenticate the key (401), resolve a route alias if the `model` names one,
  2. enforce model access (403) and existence (404),
  3. enforce rpm (429) and budget (402),
  4. guardrail the input, call the injected `caller`,
  5. compute cost, add to key/team/tag spend, append a `LogRecord`,
  6. guardrail the output and return the OpenAI-shaped response.
- `DynamicRoute` + node classes (`ConditionalNode`, `PercentageNode`,
  `RateLimitNode`, `BudgetLimitNode`, `ModelNode`) resolve a model name;
  `RouteRegistry` holds versions and implements `deploy` / `rollback`.
- `PIIMasker` — a deterministic email/phone/card masker used as both an input
  and output guardrail.
- `recommend_gateway(...)` — encodes the gateway-vs-SDK table.

Run it: `python -m pytest -q` (15 tests), or open `gateway_demo.ipynb`.

## 7. Pitfalls

- Treating the gateway as just a proxy — the value is keys/budgets/telemetry/
  guardrails; without those you have added a hop for nothing.
- Budget checked only against the *requested* model (a cheap model that falls
  back to a paid one can blow the cap) — re-check on the model that bills.
- Forgetting that dynamic routes are versioned: a draft is not live until
  deployed; use rollback rather than editing in place.
- Letting guardrails run only on output (PII can leave in the prompt) or only on
  input (the model can emit PII).
- Percentage routes need a seedable RNG in tests or your tests are flaky.

## 8. Exercises

1. Add a third provider and show one key calling three models through the single
   endpoint.
2. Add a `tpm_limit` and reject when a key's token window is exhausted.
3. Build a route: rate-limit node → premium model, fallback → cheap model, and
   prove the fallback fires under load.
4. Publish route `v1`, deploy, then publish `v2`, deploy, and roll back — with
   no application redeploy.
5. Extend `recommend_gateway` with a `num_teams` parameter and justify the flip.

## 9. Sources

- LiteLLM AI Gateway (one endpoint, virtual keys, budgets, logging): <https://docs.litellm.ai/docs/simple_proxy>
- Cloudflare AI Gateway: <https://developers.cloudflare.com/ai-gateway/>
- Cloudflare Dynamic routing (nodes, versions, rollback): <https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/>
- Related: topic 19a (fallbacks), topic 19c (routing), topic 14 (streaming).

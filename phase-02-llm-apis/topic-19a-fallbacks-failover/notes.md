# Topic 19a — Fallbacks / failover

**Before:** 19 · **Sources:** [LiteLLM — Fallbacks (Provider Failover)](https://docs.litellm.ai/docs/proxy/reliability) · [Cloudflare — Dynamic routing](https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/)

**Done when:** a failing primary model fails over to a backup in order, you can
name which fallback type fired, and spend logs distinguish fallback-served from
direct requests.

## Learning checklist

- [ ] Ordered failover after `num_retries`: `fallbacks=[{"gpt-4o-mini": ["gpt-4o"]}]`; in-order semantics
- [ ] Three types: general `fallbacks` (rate-limit/5xx) vs `context_window_fallbacks` (needs `enable_pre_call_checks` + `max_input_tokens`) vs `content_policy_fallbacks` (policy violation)
- [ ] Combo: `num_retries` + `request_timeout` + `allowed_fails`/`cooldown_time`; default vs per-request fallbacks; `disable_fallbacks`
- [ ] Attribution: spend logs carry `attempted_fallbacks` + `original_model_group`; key-access and budget enforcement on fallback targets

---

## 1. Retry is not failover

Topic 19 answers *"this one call failed — try it again"*. Fallback answers a
different question: *"this model/provider is down — who serves the request
instead?"*

| | Retry (topic 19) | Fallback (this topic) |
| --- | --- | --- |
| Scope | one deployment | across model groups |
| Trigger | transient error | retries exhausted / policy error |
| Result | same model answers | a different model answers |
| Risk | thundering herd | silent quality change |

They compose: **retry first (per deployment), then fail over (across groups).**

## 2. Model groups and deployments

A **model group** is the logical name a client asks for (`gpt-4o-mini`). It is
backed by one or more **deployments** — concrete provider/endpoint pairs
(`azure/…`, `openai/…`, a self-hosted vLLM box). Load balancing to topic 19c
picks *between deployments inside a group*; fallback moves *between groups*.

```yaml
model_list:
  - model_name: zephyr-beta            # group
    litellm_params: {model: huggingface/…, api_base: http://0.0.0.0:8001}
  - model_name: zephyr-beta            # same group, second deployment
    litellm_params: {model: huggingface/…, api_base: http://0.0.0.0:8002}
  - model_name: gpt-4o-mini            # the backup group
    litellm_params: {model: openai/gpt-4o-mini}
```

## 3. Ordered failover after `num_retries`

```yaml
litellm_settings:
  num_retries: 3
  fallbacks: [{"zephyr-beta": ["gpt-4o-mini"]}]
```

Semantics:

```
completion("zephyr-beta")
  -> try zephyr-beta (each deployment), num_retries times
  -> still failing? take the FIRST target in fallbacks["zephyr-beta"]
  -> that target is itself tried (with its own retries)
  -> if it fails too, the NEXT target in the list, in order
```

Fallbacks are **in order**: `["gpt-4o-mini", "gpt-4o", "gpt-4.1"]` tries
`gpt-4o-mini` first, then `gpt-4o`, then `gpt-4.1`. The list is terminal — once
a chain is chosen, later targets only run if earlier ones fail.

```python
fallbacks=[{"gpt-4o-mini": ["gpt-4o"]}]
```

## 4. The three fallback types

The error that ended the primary attempt decides **which map is consulted**:

| Map | Fires on | Example error |
| --- | --- | --- |
| `fallbacks` | everything else | `RateLimitError` (429), 5xx |
| `context_window_fallbacks` | prompt too big for the model | `ContextWindowExceededError` |
| `content_policy_fallbacks` | provider content filter | `ContentPolicyViolationError` |
| `default_fallbacks` | any group with no specific entry | — |

### Context-window fallbacks need a pre-call check

`context_window_fallbacks` only helps if the gateway checks the prompt **before**
calling. That requires **both**:

1. `router_settings.enable_pre_call_checks: true`, and
2. a per-deployment `model_info.max_input_tokens` (which overrides the provider
   default and lets you test with a tiny window).

```yaml
router_settings:
  enable_pre_call_checks: true            # required for enforcement
model_list:
  - model_name: gpt-4o-mini
    litellm_params: {model: openai/gpt-4o-mini}
    model_info:
      max_input_tokens: 10                # reject prompts > 10 tokens
litellm_settings:
  context_window_fallbacks: [{"gpt-4o-mini": ["gpt-4o"]}]
```

Without the pre-call check the request is simply sent and fails at the provider
(if at all). With it, a 306-token prompt against a 10-token window raises
`ContextWindowExceededError … Max Input Tokens=10, Got=306` and the fallback runs.

### Content-policy fallbacks cross providers

```yaml
litellm_settings:
  content_policy_fallbacks: [{"gpt-4o-mini": ["claude-opus"]}]
```

Useful when one provider's safety filter is stricter than another's.

## 5. Retries + timeouts + cooldowns together

```yaml
litellm_settings:
  num_retries: 3          # retry each model group 3 times
  request_timeout: 10     # a call that takes > 10s raises Timeout
  allowed_fails: 3        # after 3 failures in a minute...
  cooldown_time: 30       # ...cool the deployment down for 30s
  fallbacks: [{"zephyr-beta": ["gpt-4o-mini"]}]
```

- `request_timeout` turns a slow provider into a *transient* error the retry
  loop (and then the fallback) can act on.
- `allowed_fails` / `cooldown_time` implement **circuit-breaker-lite** per
  deployment: a deployment that fails repeatedly is skipped for a while, so a
  dead provider is taken out of rotation instead of being hammered.

## 6. `default_fallbacks`, precedence, and disabling

- `default_fallbacks: ["claude-opus"]` — used when a group has **no entry** in
  the specific map (e.g. a misconfigured group name).
- A **specific** entry (`{"zephyr-beta": ["gpt-4o-mini"]}`) **overrides** the
  default for that group.
- `disable_fallbacks: true` in a single request body turns fallbacks off for
  that request (also available per key). Useful when a caller must know it is
  talking to exactly the model it asked for, and acceptable to fail instead.

```json
{"model": "gpt-4o-mini", "messages": [...], "disable_fallbacks": true}
```

## 7. Attribution: which requests were fallback-served?

Every spend-log row records whether the request was served by the group the
client asked for, or by a fallback. The proxy writes two keys into the
`metadata` column:

| Key | Meaning |
| --- | --- |
| `attempted_fallbacks` | number of fallback attempts. `0` = the requested group served it |
| `original_model_group` | the model group the client originally requested |

```sql
SELECT model_group,
       metadata->>'attempted_fallbacks' AS attempted_fallbacks,
       metadata->>'original_model_group' AS original_model_group
FROM "LiteLLM_SpendLogs";
```

A request to `gpt-4o` that fails over to `claude-opus` produces a row with
`model_group=claude-opus`, `attempted_fallbacks=1`,
`original_model_group=gpt-4o`. Without these keys you cannot tell a
fallback-served request from a directly-served one after the fact.

## 8. Guards on fallback targets

Fallbacks must not become a **privilege-escalation** or **budget-bypass** path:

- **Model access** — the calling key's/team's/project's allowed models are
  re-checked on every fallback target. A target the caller may not call
  directly is skipped; if none remain, the caller gets the *primary* error.
  (Off switch: `general_settings.enforce_fallback_model_access: false`.)
- **Budget** — the key's/user's remaining budget is re-checked on every target,
  because the budget check happens at authentication against the *requested*
  model, not the model that ends up billing. Matters most when the primary is a
  free/zero-cost model that would otherwise fail over to a paid one.
  (Off switch: `general_settings.enforce_fallback_budget: false`.)

## 9. Cross-provider gotchas

- **Encrypted reasoning is not portable.** A fallback to another provider/API
  key cannot decrypt reasoning the failed deployment produced (Responses-API
  encrypted reasoning items, or `/v1/messages` thinking blocks). The fallback
  drops what the target cannot decrypt and reasons fresh **on that turn**.
- **Prompt caches go cold.** A fallback target has its own prefix cache, so the
  next turn pays a cache *write* on the new provider. Session affinity (19c)
  exists partly to avoid this.
- **Quality can silently change.** The fallback is a *different* model. Tag
  fallback-served requests (via `attempted_fallbacks`) so you can evaluate them.

## 10. Implementation walkthrough (`fallbacks.py`)

- `ModelGroup` / `Deployment` — a group backed by one or more deployments, each
  with an optional `max_input_tokens` and `cost_per_1k_tokens`.
- `Router.completion(group, tokens, disable_fallbacks=False)`:
  1. `_attempt_group(group)` — try each deployment, `1 + num_retries` attempts,
     skipping cooled-down deployments; a **pre-call** context check raises
     `CONTEXT_WINDOW` before the responder is called.
  2. On failure, `_chain_for(group, kind)` selects the map by error kind.
  3. Walk the chain in order, skipping targets the key may not call or cannot
     afford, counting `attempted_fallbacks`.
  4. Return a `SpendLog` carrying `original_model_group`, `served_model_group`,
     `attempted_fallbacks`, the full `attempts` list and the `as_row()` dict.
- `ProviderError(kind, message)` + `ErrorKind` + `PERMANENT`/`TRANSIENT` sets
  decide retry-vs-skip inside a group.

Run it: `python -m pytest -q` (16 tests), or open `fallbacks_demo.ipynb`.

## 11. Pitfalls

- Forgetting `enable_pre_call_checks` — `context_window_fallbacks` silently
  never fires.
- Fallback chains that are not terminal: a chain's later targets only run when
  earlier ones fail; list extra targets at the end of the chain.
- Letting a fallback serve a model the key cannot call (privilege escalation) or
  bypass a budget (cost overrun) — always re-check access and budget.
- Reading `model_group` alone in spend logs — you lose the fact that a fallback
  answered. Always join `attempted_fallbacks` + `original_model_group`.
- Expecting the same quality/behaviour after a fallback across providers.

## 12. Exercises

1. Add a third backup and prove the chain is tried strictly in order.
2. Give two deployments to the primary group and show a failing deployment is
   skipped (cooldown) while the healthy one serves with `attempted_fallbacks=0`.
3. Make the primary a free model and a paid fallback; show the budget guard
   blocks the fallback once the key is over budget, returning the primary error.
4. Wire `content_policy_fallbacks` across providers and prove a policy error on
   provider A is served by provider B.
5. Add a `disable_fallbacks` key-level flag and show a request fails fast instead
   of silently changing models.

## 13. Sources

- LiteLLM — Fallbacks (Provider Failover): <https://docs.litellm.ai/docs/proxy/reliability>
- LiteLLM — Load balancing & order-based fallback: <https://docs.litellm.ai/docs/proxy/load_balancing>
- Cloudflare — Dynamic routing (conditional/percentage/rate/budget nodes with fallback): <https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/>
- Related: topic 19 (retries/backoff), topic 19b (gateways), topic 19c (routing).

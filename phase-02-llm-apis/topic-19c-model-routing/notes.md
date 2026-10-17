# Topic 19c — Model routing for production

**Before:** 19a, 19b · **Sources:** [LiteLLM routing strategies](https://docs.litellm.ai/docs/routing) · [LiteLLM auto routing](https://docs.litellm.ai/docs/proxy/auto_routing) · [Cloudflare AI Gateway](https://developers.cloudflare.com/ai-gateway/)

**Done when:** one `model="auto"` call picks both a *tier* and a *deployment*
deterministically, you can say *why* it chose (`cause=`), and you can defend
in-house routing against a hosted marketplace.

## Learning checklist

- [ ] Routing strategies: simple-shuffle / latency / least-busy / cost-based / usage-based
- [ ] Routing groups: several deployments per model name; strategy chooses one; re-checked on cooldown
- [ ] Auto routing tiers: SIMPLE / MEDIUM / COMPLEX / REASONING from a 7-dimension heuristic scorer
- [ ] `cause=` attribution; keyword short-circuit; adaptive (Thompson-sampling) exploration
- [ ] Hosted market-based routing contrast; allow/exclude wildcards
- [ ] Session affinity + idle TTL; fall through to the group when the pinned deployment is cooled down

---

## 1. Two questions routing answers

A request hits a model **group** (the name the client asks for, e.g. `gpt-4.1`
or `auto`). Two separate decisions follow:

1. **Which tier?** Only for `auto`: is this prompt simple, medium, complex or a
   reasoning task?
2. **Which deployment?** Every group is backed by several deployments
   (provider + region + host). The **strategy** picks one.

19a covers what happens *after* a deployment fails. 19c covers the *choice*.

## 2. Routing strategies

| Strategy | Picks | Use when |
| --- | --- | --- |
| `simple-shuffle` (default) | weighted random over healthy deployments | you have no signal; spreads load |
| `latency-based-routing` | lowest recent latency (per-deployment TTL) | interactive UX; the fastest provider wins |
| `least-busy` | fewest in-flight requests | long streams; avoids piling onto a slow dep |
| `cost-based-routing` | cheapest healthy deployment | batch/offline; margin matters |
| `usage-based-routing` | lowest tpm/rpm utilisation | you hold separate quotas per deployment |

Latency routing keeps a per-deployment TTL window (so a one-off slow call does
not condemn a healthy deployment). An **untested** deployment is tried first so
it gets measured at least once. Results feed a light load balancer, not a
scheduler — keep it simple.

## 3. Routing groups

```yaml
model_list:
  - model_name: gpt-4.1            # the group the client asks for
    litellm_params: {model: openai/gpt-4.1}
  - model_name: gpt-4.1
    litellm_params: {model: azure/gpt-4.1}   # same group, second deployment
router_settings:
  routing_strategy: latency-based-routing
  fallbacks: [{gpt-4.1: [gpt-4o-mini]}]
```

The group is the unit for retries/fallbacks (19a) *and* for strategy selection.
A deployment in cooldown is removed from the candidate set before the strategy
runs; if all are cooled down the request fails until one recovers.

## 4. Auto routing (complexity-based)

`model="auto"` scores the prompt on seven cheap, explainable dimensions and maps
it to a tier:

| Dimension | Counts |
| --- | --- |
| `tokenCount` | words in the prompt |
| `codePresence` | fenced code / `def` / `class` / braces / `=>` |
| `reasoningMarkers` | "prove", "derive", "step by step", "analyse", … |
| `technicalTerms` | algorithm, regex, sql, kubernetes, distributed, … |
| `simpleIndicators` | "what is", "who is", "define", "translate", "hi" |
| `multiStepPatterns` | "then", "after that", "first", "finally", … |
| `questionComplexity` | number of `?` |

Then a weighted sum maps to **SIMPLE / MEDIUM / COMPLEX / REASONING**, and the
router records **why** in `cause=`:

| `cause` | Meaning |
| --- | --- |
| `literal_keyword_match` | a keyword rule fired (≥ 2 reasoning markers → REASONING) |
| `complexity_scorer` | the weighted score decided |
| `semantic_keyword_match` | embedding-similarity rule (not shown here) |
| `llm_classifier` | a small model classified the prompt |
| `classifier_plugin` | your own classifier |
| `session_affinity_pin` | reused a pinned deployment |

Keyword rules **short-circuit** and escalate to the *highest* matched tier, so
"prove step by step" never lands on SIMPLE.

### Adaptive (Thompson sampling)

The heuristic is a prior, not gospel. With a small exploration rate the router
samples a tier from a **Beta posterior** per tier (`alpha` = successes, `beta` =
failures) and occasionally tries a cheaper tier. `reward(tier, success)` updates
the posterior, so good cheap choices get chosen more over time — this is the
bandit half of "adaptive routing".

## 5. Session affinity

By default **off** (`session_affinity: false`, `ttl: 3600`). When on, a session
id is pinned to the *model name* it first used, so a multi-turn chat does not
bounce between providers (keeps caching and behaviour stable). **Deployment
affinity** pins the deployment id instead — stricter, for sticky caches.

The pin is a *preference*, not a hard lock: if the pinned deployment is cooled
down (19a), the router **falls through** to the group and re-pins. Idle pins
expire after the TTL.

## 6. Hosted market-based routing (the contrast)

OpenRouter-style routers pick from a live market by price/quality instead of by
your own groups:

```text
filter: quality ≥ 0.8, price ≤ $2/1M, allowed=["openai/*","anthropic/*"], excluded=["*/deprecated"]
rank:   by quality (or by price)
```

**Wildcards** (`allowed` / `excluded`) let you express "any OpenAI or Anthropic
model except deprecated ones" without listing every model id. Trade-off: you
outsource choice and get less control over spend, data residency and fallbacks.
A hosted router usually also offers **session stickiness** (same `session_id` →
same model) which must **degrade gracefully**: if the sticky model errors or is
rate-limited, the router silently falls to the next candidate rather than
failing the turn.

## 7. Implementation walkthrough (`routing.py`)

- `Deployment` — cost, weight, in-flight count, cooldown, and a TTL-bounded
  latency sample list; `record_success` / `record_failure` / `recent_latency`.
- Strategy classes — `SimpleShuffle`, `LatencyBased`, `LeastBusy`, `CostBased`,
  `UsageBased`; each `select(candidates, ctx)` returns one deployment.
- `RoutingGroup.pick(ctx, session_id)` — consults affinity, filters cooled-down
  deployments, runs the strategy, re-pins.
- `score_prompt` / `heuristic_tier` — the seven dimensions and the
  `(tier, cause, scores)` decision, including the reasoning short-circuit.
- `AutoRouter.route` / `reward` — tier selection plus optional Thompson-sampling
  exploration (`_beta_sample` approximates Beta via order statistics, no NumPy).
- `SessionAffinity` — pin / get with idle TTL; `market_route` — the hosted
  contrast with quality/price filters and `fnmatch` wildcards.

Run it: `python -m pytest -q` (25 tests), or open `routing_demo.ipynb`.

## 8. Pitfalls

- Routing by **average** latency without a TTL window — one bad minute poisons a
  deployment forever.
- Forgetting to re-check the budget/access *after* routing: a cheap tier that
  routes to an expensive deployment (19b) can blow the cap.
- Treating the complexity scorer as truth: it is a cheap prior; log `cause=` and
  audit, and let the bandit correct it.
- Pinning sessions without a TTL — a user's stickiness outlives the deployment.
- Hard-coding deployment lists: hosted wildcards exist precisely so an allow
  list is "any `openai/*`", not twenty stale ids.

## 9. Exercises

1. Add `LatencyBased(ttl=...)` and show that a stale sample ages out of the
   window.
2. Add a `least-busy` group, increment `in_flight` around a call, and prove the
   next call goes elsewhere.
3. Log `cause=` for 20 prompts and find one the scorer got wrong; add a keyword
   rule that fixes it.
4. Run the auto router with `explore=0.2`, reward a cheap tier, and show its
   selection share rising.
5. Turn on session affinity for a chat and show the pinned model survives a
   round-trip; then cool the deployment down and show the fall-through.

## 10. Sources

- LiteLLM routing strategies (simple-shuffle, latency, least-busy, cost/usage): <https://docs.litellm.ai/docs/routing>
- LiteLLM auto routing (tiers, 7-dimension scorer, `cause`, adaptive): <https://docs.litellm.ai/docs/proxy/auto_routing>
- Cloudflare AI Gateway dynamic routing: <https://developers.cloudflare.com/ai-gateway/features/dynamic-routing/>
- Related: topic 19a (fallbacks), topic 19b (gateways), topic 20 (reasoning budgets).

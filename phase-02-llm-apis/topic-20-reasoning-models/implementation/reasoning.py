"""Topic 20 - Reasoning models and test-time compute.

A hand-written, offline model of the economics and control knobs of reasoning
("thinking") models, plus the two families of test-time-compute (TTC) strategy.

What thinking tokens are
------------------------
* Generated internally *before* the visible output (and, with interleaved
  thinking, *between* tool calls / visible blocks).
* NOT returned as text through the API - only optional summaries
  (``reasoning.summary`` on OpenAI, ``thinking`` blocks on Anthropic).
* They DO occupy the context window.
* They ARE billed as OUTPUT tokens.
* Counted by OpenAI in ``usage.output_tokens_details.reasoning_tokens`` and by
  Anthropic in ``usage.output_tokens_details.thinking_tokens`` (on the final
  ``message_delta`` when streaming).

The knobs
---------
* OpenAI: ``reasoning.effort`` ladder ``none < minimal < low < medium < high <
  xhigh < max`` (model-dependent), plus ``reasoning.mode`` (standard/pro),
  ``reasoning.summary`` (auto/concise/detailed) and ``reasoning.context``
  (current_turn/all_turns).
* Anthropic: manual extended thinking ``{"type": "enabled", "budget_tokens": N}``
  (N >= 1024, must be LESS than ``max_tokens``; interleaved thinking is the
  exception because its budget spans every thinking block in the turn) or
  adaptive thinking ``{"type": "adaptive"}`` +
  ``output_config={"effort": low|medium|high|xhigh|max}`` where the model decides
  whether/how much to think - ``low`` may skip thinking entirely on easy input.
  The budget is a TARGET, not a hard cap.

Billing
-------
``billed_output = visible_output + reasoning``, priced at the OUTPUT rate.
``max_output_tokens`` caps thinking + output together: a call that exhausts it
while still thinking returns ``status=incomplete``, ``reason=max_output_tokens``
with NO visible text - and you still pay for the input and the thinking.

Test-time compute
-----------------
* PARALLEL: draw N independent samples (best-of-N) or sample-and-vote
  (self-consistency / majority vote). Latency ~ one sample, cost ~ N x, and the
  result is only as good as the verifier/scorer.
* SERIAL: one longer chain (bigger thinking budget, or a chain of refinement
  steps). Latency and cost both grow; no extra sampling.
* Verifiers: outcome reward (score the final answer) vs process reward (score
  each step). A strong verifier raises the ceiling; verifier quality is the real
  limit of best-of-N.

Everything here is deterministic and offline: no network, no frameworks.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Effort ladder, difficulty bands, thinking budgets
# ---------------------------------------------------------------------------


class Effort(str, Enum):
    """Provider-agnostic effort ladder, named after OpenAI's ``reasoning.effort``."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


EFFORT_ORDER: Tuple[Effort, ...] = (
    Effort.NONE,
    Effort.MINIMAL,
    Effort.LOW,
    Effort.MEDIUM,
    Effort.HIGH,
    Effort.XHIGH,
    Effort.MAX,
)

# Anthropic's floor for a MANUAL budget_tokens you pass yourself. Adaptive
# effort levels are the provider's business and may sit below this.
MIN_THINKING_BUDGET = 1024

# OpenAI's advice when experimenting with reasoning models: reserve roughly
# this many tokens for reasoning + output together.
RECOMMENDED_REASONING_RESERVE = 25_000


class Difficulty(str, Enum):
    """Coarse band for a prompt, used to model adaptive thinking."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Target thinking tokens per (effort, difficulty) for ADAPTIVE thinking: the
# model decides how much to think, and a low effort may skip thinking entirely
# on an easy prompt (hence the zeros).
ADAPTIVE_THINKING_TARGETS: Dict[Effort, Dict[Difficulty, int]] = {
    Effort.NONE: {Difficulty.EASY: 0, Difficulty.MEDIUM: 0, Difficulty.HARD: 0},
    Effort.MINIMAL: {Difficulty.EASY: 0, Difficulty.MEDIUM: 128, Difficulty.HARD: 512},
    Effort.LOW: {Difficulty.EASY: 0, Difficulty.MEDIUM: 1024, Difficulty.HARD: 2048},
    Effort.MEDIUM: {Difficulty.EASY: 1024, Difficulty.MEDIUM: 4096, Difficulty.HARD: 8192},
    Effort.HIGH: {Difficulty.EASY: 4096, Difficulty.MEDIUM: 16384, Difficulty.HARD: 32768},
    Effort.XHIGH: {Difficulty.EASY: 8192, Difficulty.MEDIUM: 32768, Difficulty.HARD: 65536},
    Effort.MAX: {Difficulty.EASY: 16384, Difficulty.MEDIUM: 65536, Difficulty.HARD: 131072},
}

# One-number summary of the ladder: the target for a MEDIUM-difficulty prompt.
EFFORT_TO_THINKING_BUDGET: Dict[Effort, int] = {
    effort: row[Difficulty.MEDIUM] for effort, row in ADAPTIVE_THINKING_TARGETS.items()
}


def difficulty_band(difficulty: float) -> Difficulty:
    """Map a 0..1 difficulty to its band."""
    if not 0.0 <= difficulty <= 1.0:
        raise ValueError(f"difficulty must be in [0, 1], got {difficulty!r}")
    if difficulty < 1.0 / 3.0:
        return Difficulty.EASY
    if difficulty < 2.0 / 3.0:
        return Difficulty.MEDIUM
    return Difficulty.HARD


def planned_thinking_tokens(effort: Effort, difficulty: Difficulty) -> int:
    """Thinking tokens an adaptive model would target, in tokens.

    Zero is a real answer: ``reasoning.effort=low`` may skip thinking entirely
    on easy input, and effort ``none`` never thinks.
    """
    return ADAPTIVE_THINKING_TARGETS[effort][difficulty]


def validate_thinking_budget(budget_tokens: int, max_tokens: int, *, interleaved: bool = False) -> None:
    """Validate a MANUAL Anthropic ``thinking.budget_tokens``.

    Rules: the budget must be an int >= 1024, and it must be strictly LESS than
    ``max_tokens`` - except with interleaved thinking, where the budget spans
    every thinking block in one turn and may therefore exceed ``max_tokens``.
    Raises ``ValueError`` with the reason instead of returning a bool.
    """
    if isinstance(budget_tokens, bool) or not isinstance(budget_tokens, int):
        raise TypeError(f"budget_tokens must be an int, got {type(budget_tokens).__name__}")
    if max_tokens <= 0:
        raise ValueError(f"max_tokens must be positive, got {max_tokens}")
    if budget_tokens < MIN_THINKING_BUDGET:
        raise ValueError(
            f"thinking budget_tokens must be >= {MIN_THINKING_BUDGET} (got {budget_tokens})"
        )
    if not interleaved and budget_tokens >= max_tokens:
        raise ValueError(
            "manual extended thinking requires budget_tokens < max_tokens "
            f"(got budget={budget_tokens}, max_tokens={max_tokens}); interleaved "
            "thinking is the exception because its budget spans every thinking "
            "block in the turn"
        )


# ---------------------------------------------------------------------------
# Prices, usage, billing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Price:
    """Per-million-token prices for one model."""

    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: Optional[float] = None

    def input_cost(self, tokens: int) -> float:
        return tokens * self.input_per_mtok / 1_000_000.0

    def cached_input_cost(self, tokens: int) -> float:
        rate = self.cached_input_per_mtok
        if rate is None:
            rate = self.input_per_mtok
        return tokens * rate / 1_000_000.0

    def output_cost(self, tokens: int) -> float:
        return tokens * self.output_per_mtok / 1_000_000.0


PRICE_TABLE: Dict[str, Price] = {
    # A reasoning-tier model: expensive output (thinking is billed here).
    "reasoning-large": Price(2.50, 10.00, cached_input_per_mtok=0.25),
    # A cheaper reasoning model.
    "reasoning-small": Price(0.55, 2.20, cached_input_per_mtok=0.055),
    # A fast non-reasoning model, for planner/worker routing.
    "fast-small": Price(0.15, 0.60, cached_input_per_mtok=0.015),
}


def price_for(model: str) -> Price:
    """Look up a model's prices (falls back to the reasoning-large price)."""
    return PRICE_TABLE.get(model, PRICE_TABLE["reasoning-large"])


@dataclass(frozen=True)
class Usage:
    """Token accounting for one call, with thinking kept separate from visible."""

    input_tokens: int
    visible_output_tokens: int
    reasoning_tokens: int = 0

    @property
    def billed_output_tokens(self) -> int:
        """Thinking and visible output are billed together at the output rate."""
        return self.visible_output_tokens + self.reasoning_tokens

    @property
    def total_tokens(self) -> int:
        """Everything that occupies the window: input + visible + thinking."""
        return self.input_tokens + self.billed_output_tokens

    def output_tokens_details(self, provider: str = "openai") -> Dict[str, int]:
        """The provider's name for the hidden reasoning count."""
        key = _reasoning_usage_key(provider)
        return {key: self.reasoning_tokens}

    def to_usage_payload(
        self,
        provider: str = "openai",
        *,
        streaming: bool = False,
        final_delta: bool = True,
    ) -> Dict[str, object]:
        """The provider-shaped ``usage`` object.

        OpenAI reports ``output_tokens_details.reasoning_tokens``. Anthropic
        reports ``output_tokens_details.thinking_tokens``, and when streaming it
        only lands on the final ``message_delta`` - earlier deltas carry None.
        """
        key = _reasoning_usage_key(provider)
        payload: Dict[str, object] = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.billed_output_tokens,
        }
        if provider == "anthropic":
            counting_now = (not streaming) or final_delta
            payload["output_tokens_details"] = {
                key: self.reasoning_tokens if counting_now else None
            }
        else:
            payload["output_tokens_details"] = {key: self.reasoning_tokens}
        return payload


def _reasoning_usage_key(provider: str) -> str:
    if provider == "anthropic":
        return "thinking_tokens"
    if provider in ("openai", "openai-responses"):
        return "reasoning_tokens"
    raise ValueError(f"unknown provider {provider!r} (expected 'openai' or 'anthropic')")


@dataclass(frozen=True)
class CostBreakdown:
    """Where the money went on one call."""

    input_cost: float
    visible_output_cost: float
    reasoning_cost: float
    billed_output_tokens: int

    @property
    def output_cost(self) -> float:
        return self.visible_output_cost + self.reasoning_cost

    @property
    def total_cost(self) -> float:
        return self.input_cost + self.output_cost

    @property
    def reasoning_share(self) -> float:
        """Fraction of the total bill that hidden thinking consumed."""
        total = self.total_cost
        return 0.0 if total == 0 else self.reasoning_cost / total


def estimate_cost(usage: Usage, price: Price) -> CostBreakdown:
    """Bill a call: thinking tokens are charged at the OUTPUT rate."""
    return CostBreakdown(
        input_cost=price.input_cost(usage.input_tokens),
        visible_output_cost=price.output_cost(usage.visible_output_tokens),
        reasoning_cost=price.output_cost(usage.reasoning_tokens),
        billed_output_tokens=usage.billed_output_tokens,
    )


def cost_per_request(
    input_tokens: int,
    visible_output_tokens: int,
    reasoning_tokens: int,
    price: Price,
) -> float:
    """Convenience: input + (visible + thinking) * output_price."""
    usage = Usage(input_tokens, visible_output_tokens, reasoning_tokens)
    return estimate_cost(usage, price).total_cost


# ---------------------------------------------------------------------------
# One completion: reasoning first, then visible output, capped by max_output_tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletionResult:
    """Outcome of one simulated reasoning call."""

    status: str                                # "completed" | "incomplete"
    visible_text: str
    usage: Usage
    cost: float
    thought_summary: Optional[str] = None      # a readable summary of hidden thinking
    incomplete_reason: Optional[str] = None    # e.g. "max_output_tokens"

    @property
    def has_visible_output(self) -> bool:
        return bool(self.visible_text)

    @property
    def finished(self) -> bool:
        return self.status == "completed"


def run_completion(
    *,
    prompt: str,
    input_tokens: int,
    planned_thinking: int,
    planned_visible: int,
    max_output_tokens: int,
    price: Price,
    summary: bool = True,
) -> CompletionResult:
    """Simulate one reasoning call whose output budget is ``max_output_tokens``.

    Thinking is spent FIRST. If the cap is exhausted while still thinking, the
    call ends ``incomplete`` with no visible text at all - and the input plus
    the thinking are still billed.
    """
    if max_output_tokens <= 0:
        raise ValueError(f"max_output_tokens must be positive, got {max_output_tokens}")
    if planned_thinking < 0 or planned_visible < 0:
        raise ValueError("planned token counts must be >= 0")

    thinking_used = min(planned_thinking, max_output_tokens)
    remaining = max_output_tokens - thinking_used

    if planned_thinking >= max_output_tokens:
        # Ran out of budget before producing a single visible token.
        visible = 0
        status, reason = "incomplete", "max_output_tokens"
    elif planned_visible > remaining:
        # Truncated mid-answer.
        visible = remaining
        status, reason = "incomplete", "max_output_tokens"
    else:
        visible = planned_visible
        status, reason = "completed", None

    usage = Usage(input_tokens, visible, thinking_used)
    text = "" if visible == 0 else f"answer: {prompt.strip()[:40]}"
    summary_text = None
    if summary and thinking_used:
        summary_text = f"(readable summary of {thinking_used} hidden thinking tokens)"
    return CompletionResult(
        status=status,
        visible_text=text,
        usage=usage,
        cost=estimate_cost(usage, price).total_cost,
        thought_summary=summary_text,
        incomplete_reason=reason,
    )


def will_fit(max_output_tokens: int, planned_thinking: int, planned_visible: int) -> bool:
    """Does one call fit in ``max_output_tokens`` (thinking + visible together)?"""
    return planned_thinking + planned_visible <= max_output_tokens


def recommended_reserve_warnings(max_output_tokens: int) -> List[str]:
    """OpenAI's experimenting advice: headroom for reasoning + output."""
    if max_output_tokens < RECOMMENDED_REASONING_RESERVE:
        return [
            f"max_output_tokens={max_output_tokens} is below the ~"
            f"{RECOMMENDED_REASONING_RESERVE:,} tokens worth reserving for reasoning "
            "+ output while experimenting; raising it and lowering effort is safer "
            "than getting status=incomplete"
        ]
    return []


# ---------------------------------------------------------------------------
# Verifiers (outcome vs process reward)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutcomeVerifier:
    """Outcome reward: score the FINAL answer only."""

    rubric: Dict[str, float] = field(default_factory=dict)
    default: float = 0.0

    def score(self, answer: str) -> float:
        return self.rubric.get(answer.strip(), self.default)


def _split_steps(answer: str) -> List[str]:
    return [part.strip() for part in answer.split(";") if part.strip()]


@dataclass(frozen=True)
class ProcessVerifier:
    """Process reward: score each step, then aggregate.

    ``aggregate="min"`` behaves like a checklist - every step must pass - which
    is the strictest and most useful default for multi-step work. ``"mean"``
    averages instead.
    """

    step_scores: Dict[str, float] = field(default_factory=dict)
    default: float = 0.0
    aggregate: str = "min"
    steps_of: Callable[[str], Sequence[str]] = _split_steps

    def score(self, answer: str) -> float:
        steps = list(self.steps_of(answer))
        if not steps:
            return self.default
        values = [self.step_scores.get(step, self.default) for step in steps]
        if self.aggregate == "mean":
            return sum(values) / len(values)
        return min(values)


@dataclass(frozen=True)
class Sample:
    """One independently drawn candidate answer."""

    text: str
    sample_index: int = 0


@dataclass(frozen=True)
class Selection:
    """The winner of a parallel TTC strategy."""

    sample: Sample
    score: float
    tied: int = 1                 # how many samples shared the top score / vote count
    used_tie_break: bool = False  # did a secondary verifier decide it?
    votes: int = 0                # majority vote: count for the winner
    total_votes: int = 0          # majority vote: number of samples

    @property
    def vote_share(self) -> float:
        return 0.0 if not self.total_votes else self.votes / self.total_votes


def best_of_n(
    samples: Sequence[Sample],
    verifier: OutcomeVerifier,
    tie_break: Optional[OutcomeVerifier] = None,
) -> Selection:
    """PARALLEL TTC: keep the highest-scoring of N independent samples.

    Ties are settled by ``tie_break`` when given; otherwise the earliest sample
    wins, so the result is deterministic.
    """
    if not samples:
        raise ValueError("best_of_n needs at least one sample")
    scores = [verifier.score(s.text) for s in samples]
    top = max(scores)
    tied = [i for i, s in enumerate(scores) if s == top]
    if len(tied) == 1:
        winner, used = tied[0], False
    elif tie_break is not None:
        winner = max(tied, key=lambda i: (tie_break.score(samples[i].text), -i))
        used = True
    else:
        winner, used = tied[0], False
    return Selection(samples[winner], scores[winner], tied=len(tied), used_tie_break=used)


def majority_vote(samples: Sequence[Sample]) -> Selection:
    """PARALLEL TTC: self-consistency - the most common answer wins.

    Deterministic on ties: the answer seen first keeps the win, and ``tied``
    counts how many answers matched its vote count.
    """
    if not samples:
        raise ValueError("majority_vote needs at least one sample")
    counts: Dict[str, int] = {}
    first_seen: Dict[str, int] = {}
    first_sample: Dict[str, Sample] = {}
    for sample in samples:
        key = sample.text.strip()
        counts[key] = counts.get(key, 0) + 1
        first_seen.setdefault(key, sample.sample_index)
        first_sample.setdefault(key, sample)
    top = max(counts.values())
    winners = [key for key, count in counts.items() if count == top]
    best = min(winners, key=lambda key: first_seen[key])
    return Selection(
        first_sample[best],
        score=top / len(samples),
        tied=len(winners),
        votes=top,
        total_votes=len(samples),
    )


def parallel_cost(usage: Usage, price: Price, n: int, *, cached_input: bool = True) -> float:
    """Cost of drawing ``n`` samples.

    Latency is ~one sample; cost is ~N x. The prompt is usually identical across
    samples, so the input prefix is billed once and then re-read from the cache
    (``cached_input=True``); set it False to model a cold cache on every sample.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    first_input = price.input_cost(usage.input_tokens)
    if n == 1:
        input_cost = first_input
    elif cached_input:
        input_cost = first_input + price.cached_input_cost(usage.input_tokens) * (n - 1)
    else:
        input_cost = first_input * n
    return input_cost + price.output_cost(usage.billed_output_tokens) * n


def serial_cost(usage: Usage, price: Price, extra_thinking_tokens: int) -> float:
    """Cost of one longer SERIAL chain: same call, more thinking."""
    if extra_thinking_tokens < 0:
        raise ValueError("extra_thinking_tokens must be >= 0")
    grown = Usage(usage.input_tokens, usage.visible_output_tokens, usage.reasoning_tokens + extra_thinking_tokens)
    return estimate_cost(grown, price).total_cost


@dataclass(frozen=True)
class RefineStep:
    index: int
    text: str
    score: float


@dataclass(frozen=True)
class RefineTrace:
    """A SERIAL refinement chain: step 0 is the first draft."""

    prompt: str
    steps: List[RefineStep]

    @property
    def final_text(self) -> str:
        return self.steps[-1].text

    @property
    def scores(self) -> List[float]:
        return [step.score for step in self.steps]

    @property
    def gain(self) -> float:
        return self.steps[-1].score - self.steps[0].score


def refine(
    prompt: str,
    steps: int,
    *,
    verifier: OutcomeVerifier,
    improver: Optional[Callable[[str, int], str]] = None,
) -> RefineTrace:
    """SERIAL TTC mock: one chain of ``steps`` refinements, no extra sampling.

    Each step rewrites the previous text; the verifier scores every version so
    the trace shows the (usually diminishing) returns of a longer chain.
    """
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps}")
    text = f"draft({prompt.strip()[:24]})"
    trace = [RefineStep(0, text, verifier.score(text))]
    for index in range(1, steps + 1):
        text = improver(text, index) if improver else f"{text};edited{index}"
        trace.append(RefineStep(index, text, verifier.score(text)))
    return RefineTrace(prompt=prompt, steps=trace)


# ---------------------------------------------------------------------------
# Cost / latency / quality estimator and effort selection
# ---------------------------------------------------------------------------

THINKING_TOKENS_PER_SECOND = 120.0
VISIBLE_TOKENS_PER_SECOND = 60.0
BASE_LATENCY_S = 0.4


@dataclass(frozen=True)
class TaskProfile:
    """What a task asks of a model, before any knob is turned."""

    name: str
    difficulty: float                 # 0..1
    input_tokens: int = 500
    visible_output_tokens: int = 300
    verifiable: bool = True           # can a program check the answer?
    latency_sensitive: bool = False   # does first-visible-token time matter?
    stakes: str = "medium"            # low | medium | high

    @property
    def band(self) -> Difficulty:
        return difficulty_band(self.difficulty)


@dataclass(frozen=True)
class Estimate:
    effort: Effort
    thinking_tokens: int
    cost_usd: float
    latency_s: float
    quality: float


# A quality bar is an estimate, not a measurement: compare with a hair of slack
# so that "the model already sits exactly on the bar" does not escalate effort
# over a floating-point artefact.
QUALITY_TOLERANCE = 1e-9


def meets_quality_bar(quality: float, quality_bar: float) -> bool:
    """Float-safe ``quality >= quality_bar``."""
    return quality + QUALITY_TOLERANCE >= quality_bar


def quality_from_thinking(difficulty: float, thinking_tokens: int) -> float:
    """Diminishing returns: q = base + (1 - base) * (1 - exp(-thinking / k)).

    The base is the quality floor with no thinking; ``k`` grows with difficulty,
    so a hard task needs far more thinking to buy the same quality.
    """
    base = 0.85 - 0.5 * difficulty
    k = 1000.0 + 12000.0 * difficulty
    return base + (1.0 - base) * (1.0 - math.exp(-thinking_tokens / k))


def estimate(
    profile: TaskProfile,
    effort: Effort,
    *,
    model: str = "reasoning-small",
    price: Optional[Price] = None,
    samples: int = 1,
) -> Estimate:
    """Estimate (cost, latency, quality) for one profile at one effort.

    ``samples > 1`` models PARALLEL TTC: latency stays ~one sample, cost grows,
    and quality improves ONLY when the profile is verifiable (someone has to
    pick the winner).
    """
    if samples < 1:
        raise ValueError(f"samples must be >= 1, got {samples}")
    p = price or price_for(model)
    thinking = planned_thinking_tokens(effort, profile.band)
    usage = Usage(profile.input_tokens, profile.visible_output_tokens, thinking)
    cost = (
        parallel_cost(usage, p, samples) if samples > 1 else estimate_cost(usage, p).total_cost
    )
    latency = (
        BASE_LATENCY_S
        + thinking / THINKING_TOKENS_PER_SECOND
        + profile.visible_output_tokens / VISIBLE_TOKENS_PER_SECOND
    )
    quality = quality_from_thinking(profile.difficulty, thinking)
    if samples > 1 and profile.verifiable:
        # best-of-N + a working verifier raises the ceiling: 1 - (1 - q) ** N
        quality = 1.0 - (1.0 - quality) ** samples
    return Estimate(
        effort=effort,
        thinking_tokens=thinking,
        cost_usd=cost,
        latency_s=latency,
        quality=quality,
    )


@dataclass(frozen=True)
class EffortChoice:
    """The result of choosing an effort level for a profile."""

    effort: Effort
    estimate: Estimate
    reason: str
    met_quality_bar: bool
    met_budget: bool
    met_latency: bool
    considered: List[Estimate] = field(default_factory=list)


def choose_effort(
    profile: TaskProfile,
    *,
    quality_bar: float = 0.8,
    budget_usd: Optional[float] = None,
    latency_budget_s: Optional[float] = None,
    model: str = "reasoning-small",
    samples: int = 1,
    max_effort: Effort = Effort.MAX,
) -> EffortChoice:
    """Pick the CHEAPEST effort that clears the quality bar inside the budgets.

    Escalates one rung at a time and stops at the first effort that satisfies
    the quality bar and both budgets. If nothing qualifies, it returns the
    highest allowed effort and says so - so a caller can decide to relax a
    constraint rather than being handed a silent overrun.
    """
    ceiling = EFFORT_ORDER.index(max_effort)
    ladder = [effort for effort in EFFORT_ORDER if EFFORT_ORDER.index(effort) <= ceiling]
    considered: List[Estimate] = []
    for effort in ladder:
        est = estimate(profile, effort, model=model, samples=samples)
        considered.append(est)
        affordable = budget_usd is None or est.cost_usd <= budget_usd
        fast_enough = latency_budget_s is None or est.latency_s <= latency_budget_s
        if meets_quality_bar(est.quality, quality_bar) and affordable and fast_enough:
            return EffortChoice(
                effort=effort,
                estimate=est,
                reason=(
                    f"cheapest effort clearing quality bar {quality_bar:.2f} "
                    f"(q={est.quality:.3f}) within the given budget/latency"
                ),
                met_quality_bar=True,
                met_budget=affordable,
                met_latency=fast_enough,
                considered=considered,
            )
    top = considered[-1]
    return EffortChoice(
        effort=ladder[-1],
        estimate=top,
        reason=(
            f"no effort up to {ladder[-1].value} cleared quality bar {quality_bar:.2f} "
            "inside the constraints; relax a budget or the bar, move to parallel TTC, "
            "or route to a stronger model"
        ),
        met_quality_bar=meets_quality_bar(top.quality, quality_bar),
        met_budget=budget_usd is None or top.cost_usd <= budget_usd,
        met_latency=latency_budget_s is None or top.latency_s <= latency_budget_s,
        considered=considered,
    )


# ---------------------------------------------------------------------------
# Prompting a reasoning model: goals + constraints, no "think step by step"
# ---------------------------------------------------------------------------

# Over-scripting a model that already thinks: harmless at best, harmful at worst.
STEP_BY_STEP_PHRASES: Tuple[str, ...] = (
    "think step by step",
    "think step-by-step",
    "reason step by step",
    "solve it step by step",
    "walk through it step by step",
    "let's think step by step",
    "take a deep breath",
)


def detect_step_by_step(prompt: str) -> List[str]:
    """Return the process-scripting phrases found in a prompt (empty = clean)."""
    lowered = prompt.lower()
    return [phrase for phrase in STEP_BY_STEP_PHRASES if phrase in lowered]


def _sentences(text: str) -> List[str]:
    return [piece for piece in re.split(r"(?<=[.!?])\s+|\n+", text) if piece.strip()]


def detect_and_strip_step_by_step(prompt: str) -> Tuple[str, List[str]]:
    """Split a prompt into (cleaned prompt, removed sentences).

    Shows what to delete when someone has scripted the model's process: the
    whole offending sentence goes, not just the phrase.
    """
    kept: List[str] = []
    removed: List[str] = []
    for sentence in _sentences(prompt):
        if detect_step_by_step(sentence):
            removed.append(sentence.strip())
        else:
            kept.append(sentence.strip())
    return " ".join(kept).strip(), removed


def build_reasoning_prompt(
    goal: str,
    constraints: Sequence[str] = (),
    success_criteria: Sequence[str] = (),
    *,
    context: Sequence[str] = (),
    output_contract: Optional[str] = None,
    ask_for_preamble: bool = True,
) -> str:
    """Build the prompt a reasoning model wants: goal + constraints + success.

    Deliberately does NOT script the process ("think step by step") - the model
    already thinks. ``ask_for_preamble`` asks for one short sentence up front so
    the first VISIBLE token arrives sooner while the thinking streams behind it.
    """
    if not goal.strip():
        raise ValueError("goal must not be empty")
    lines: List[str] = ["# Goal", goal.strip(), "", "# Constraints"]
    lines += [f"- {c.strip()}" for c in constraints] or ["- (none given)"]
    lines += ["", "# Success criteria"]
    lines += [f"- {c.strip()}" for c in success_criteria] or ["- (none given)"]
    if context:
        lines += ["", "# Context"]
        lines += [f"- {c.strip()}" for c in context]
    lines += ["", "# Output"]
    if output_contract:
        lines.append(f"- Return: {output_contract.strip()}")
    if ask_for_preamble:
        lines.append(
            "- Open with one short sentence stating what you are about to do, "
            "then give the answer."
        )
    lines.append(
        "- Reason as deeply as the task requires; the reasoning itself does not "
        "need to be written out unless asked for."
    )
    prompt = "\n".join(lines)
    found = detect_step_by_step(prompt)
    if found:  # pragma: no cover - guards the builder's own invariant
        raise ValueError(f"generated prompt contains banned filler: {found}")
    return prompt


# ---------------------------------------------------------------------------
# Planner / worker routing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubTask:
    """One unit of work handed to a model."""

    name: str
    difficulty: float            # 0..1
    value: str = "medium"        # low | medium | high
    needs_planning: bool = False  # decomposition/decision-heavy, not just execution


@dataclass(frozen=True)
class ModelSpec:
    """A model a planner/worker split can route to."""

    name: str
    kind: str                     # "reasoning" | "fast"
    price: Price
    est_input_tokens: int = 400
    est_output_tokens: int = 200

    def call_cost(self, reasoning_tokens: int = 0) -> float:
        usage = Usage(self.est_input_tokens, self.est_output_tokens, reasoning_tokens)
        return estimate_cost(usage, self.price).total_cost


@dataclass(frozen=True)
class RouteAssignment:
    subtask: str
    model: str
    reason: str


@dataclass(frozen=True)
class RoutingPlan:
    """Who does what: a reasoning model plans and audits, a fast model executes."""

    plan_model: str
    worker_model: str
    assignments: List[RouteAssignment]

    @property
    def reasoning_calls(self) -> int:
        return sum(1 for a in self.assignments if a.model == self.plan_model)

    @property
    def worker_calls(self) -> int:
        return sum(1 for a in self.assignments if a.model == self.worker_model)

    def summary(self) -> Dict[str, int]:
        return {
            "plan_model_calls": self.reasoning_calls,
            "worker_model_calls": self.worker_calls,
            "total_calls": len(self.assignments),
        }


def route_turn(
    subtask: SubTask,
    fast_model: ModelSpec,
    reasoning_model: ModelSpec,
    *,
    hard_threshold: float = 0.6,
    high_value_routes_to_planner: bool = True,
) -> RouteAssignment:
    """Route ONE turn by difficulty and value - the topic 19c auto-tier idea.

    Hard or high-value turns go to the reasoning model (it plans, decides, or
    repairs); easy turns go to the fast model (it executes).
    """
    hard = subtask.difficulty >= hard_threshold
    valuable = high_value_routes_to_planner and subtask.value == "high"
    if subtask.needs_planning:
        return RouteAssignment(subtask.name, reasoning_model.name, "needs planning/decomposition")
    if hard:
        return RouteAssignment(
            subtask.name,
            reasoning_model.name,
            f"hard turn (difficulty {subtask.difficulty:.2f} >= {hard_threshold:.2f})",
        )
    if valuable:
        return RouteAssignment(subtask.name, reasoning_model.name, "high-value turn")
    return RouteAssignment(
        subtask.name,
        fast_model.name,
        f"easy turn (difficulty {subtask.difficulty:.2f}) - fast model executes",
    )


def planner_worker_split(
    plan_model: ModelSpec,
    worker_model: ModelSpec,
    subtasks: Sequence[SubTask],
    *,
    hard_threshold: float = 0.6,
    high_value_routes_to_planner: bool = True,
    audit: bool = True,
) -> RoutingPlan:
    """Split a task: the reasoning model plans (and audits), the fast model executes."""
    if plan_model.kind != "reasoning":
        raise ValueError("plan_model must have kind='reasoning'")
    if worker_model.kind != "fast":
        raise ValueError("worker_model must have kind='fast'")
    assignments: List[RouteAssignment] = [
        RouteAssignment("<plan>", plan_model.name, "decompose the task into sub-tasks (planning turn)")
    ]
    for subtask in subtasks:
        assignments.append(
            route_turn(
                subtask,
                worker_model,
                plan_model,
                hard_threshold=hard_threshold,
                high_value_routes_to_planner=high_value_routes_to_planner,
            )
        )
    if audit:
        assignments.append(
            RouteAssignment("<audit>", plan_model.name, "audit the assembled result before it ships")
        )
    return RoutingPlan(plan_model.name, worker_model.name, assignments)

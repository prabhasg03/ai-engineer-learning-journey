"""Topic 21 - Decision: when NOT to use an LLM.

A hand-written decision framework for the question every feature eventually asks:
*should this be a model at all?*

The framework, in order
-----------------------
1. **Constraints** — the hard requirements (latency budget, cost ceiling,
   offline/privacy, exactness, scale). These are pass/fail, not scores.
2. **Candidates** — deterministic code, regex/parser, SQL/lookup, a classical ML
   classifier, embedding + nearest neighbour, a small LLM, a large/reasoning LLM.
3. **Trade-offs** — score the survivors on weighted criteria
   (capability/quality, verifiability, cost, latency, determinism,
   maintainability).
4. **Justified choice + sensitivity** — name the winner AND the single change that
   would flip it. A decision without a flip condition is an opinion.

The rules this module encodes
-----------------------------
* **Deterministic first.** If a deterministic method meets the requirement, prefer
  it: cheaper, faster, exactly testable, no hallucination, no prompt-injection
  surface. Reach for an LLM only for genuinely open-ended language or ambiguity.
* **Verifiability is an axis.** If the output can be checked cheaply and exactly
  (regex match, unit test, schema validation, ground truth), LLM generation is
  safe - a verifier catches errors, and best-of-N / self-consistency (topic 20)
  becomes viable. Low verifiability + high stakes argues for deterministic code,
  heavy guardrails, or human review.
* **Budgets decide as often as capability.** A 3s p99 and $0.0001/request kill an
  LLM even when it is more capable; conversely a $0.02 reasoning call is trivial
  next to a human's minute.
* **Never** an LLM for exact arithmetic, deterministic transforms, authorization,
  cryptographic/legal exactness, or anything unverifiable where errors are
  unacceptable.

Everything here is deterministic and offline: no network, no frameworks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Candidate kinds
# ---------------------------------------------------------------------------

KIND_DETERMINISTIC = "deterministic"   # hand-written code / deterministic transform
KIND_REGEX = "regex_parser"            # regex or grammar over a KNOWN format
KIND_LOOKUP = "lookup"                 # SQL / key-value / lookup table
KIND_CLASSIFIER = "classifier"         # classical ML over features
KIND_EMBEDDING = "embedding_knn"       # embedding + nearest neighbour retrieval
KIND_SMALL_LLM = "small_llm"
KIND_LARGE_LLM = "large_llm"
KIND_REASONING_LLM = "reasoning_llm"

DETERMINISTIC_KINDS = frozenset({KIND_DETERMINISTIC, KIND_REGEX, KIND_LOOKUP})
LLM_KINDS = frozenset({KIND_SMALL_LLM, KIND_LARGE_LLM, KIND_REASONING_LLM})
CLASSICAL_ML_KINDS = frozenset({KIND_CLASSIFIER, KIND_EMBEDDING})


# ---------------------------------------------------------------------------
# Constraints: hard, pass/fail requirements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Constraint:
    """A hard requirement. Failing it eliminates a candidate - it is not a score."""

    name: str
    predicate: Callable[["Candidate"], bool]
    detail: str = ""

    def passes(self, candidate: "Candidate") -> bool:
        return bool(self.predicate(candidate))


def latency_constraint(budget_ms: float) -> Constraint:
    """p99 latency ceiling in milliseconds."""
    return Constraint(
        name=f"latency <= {budget_ms:g}ms",
        predicate=lambda c: c.latency_ms <= budget_ms,
        detail="a latency budget kills an LLM even when it is more capable",
    )


def cost_constraint(ceiling_usd: float) -> Constraint:
    """Cost ceiling in USD per request."""
    return Constraint(
        name=f"cost <= ${ceiling_usd:g}/request",
        predicate=lambda c: c.cost_usd <= ceiling_usd,
        detail="at scale, $/request decides before capability does",
    )


def offline_constraint() -> Constraint:
    """No network / no third-party data egress allowed."""
    return Constraint(
        name="offline / no network",
        predicate=lambda c: not c.requires_network,
        detail="privacy or air-gap requirement: a hosted model cannot be called at all",
    )


def exactness_constraint() -> Constraint:
    """The output must be exactly right, with no tolerance for approximation."""
    return Constraint(
        name="exact output required",
        predicate=lambda c: c.exact,
        detail="exactness rules out sampling-based candidates entirely",
    )


@dataclass(frozen=True)
class Candidate:
    """One way to build the feature, with everything a decision needs to know."""

    name: str
    kind: str
    scores: Dict[str, float] = field(default_factory=dict)   # criterion -> 0..1 (higher = better)
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    requires_network: bool = False
    exact: bool = False          # is the output exact by construction?
    verifiable: bool = True      # can the output be checked cheaply and exactly?
    notes: str = ""

    def __post_init__(self) -> None:
        for criterion, score in self.scores.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"{self.name}: score for {criterion!r} must be in [0, 1], got {score}")

    @property
    def is_deterministic(self) -> bool:
        return self.kind in DETERMINISTIC_KINDS

    @property
    def is_llm(self) -> bool:
        return self.kind in LLM_KINDS

    def with_score(self, criterion: str, score: float) -> "Candidate":
        """A copy with one criterion score replaced (used by sensitivity analysis)."""
        updated = dict(self.scores)
        updated[criterion] = score
        return replace(self, scores=updated)


@dataclass(frozen=True)
class Elimination:
    candidate: Candidate
    constraint: Constraint


@dataclass(frozen=True)
class ConstraintResult:
    """What survived the hard constraints, and what died on which one."""

    survivors: List[Candidate]
    eliminated: List[Elimination]

    def reason_for(self, name: str) -> Optional[str]:
        for elimination in self.eliminated:
            if elimination.candidate.name == name:
                return elimination.constraint.name
        return None

    def report(self) -> List[str]:
        lines = [f"survivor: {c.name} ({c.kind})" for c in self.survivors]
        lines += [
            f"eliminated: {e.candidate.name} fails '{e.constraint.name}' - {e.constraint.detail}"
            for e in self.eliminated
        ]
        return lines


def apply_hard_constraints(
    candidates: Sequence[Candidate], constraints: Sequence[Constraint]
) -> ConstraintResult:
    """Drop every candidate that fails any hard constraint (first failure wins)."""
    survivors: List[Candidate] = []
    eliminated: List[Elimination] = []
    for candidate in candidates:
        for constraint in constraints:
            if not constraint.passes(candidate):
                eliminated.append(Elimination(candidate, constraint))
                break
        else:
            survivors.append(candidate)
    return ConstraintResult(survivors, eliminated)


def deterministic_first(candidates: Sequence[Candidate]) -> List[Candidate]:
    """The deterministic candidates, in order.

    If this list is non-empty after the hard constraints, stop arguing: the
    deterministic-first rule says prefer it.
    """
    return [c for c in candidates if c.is_deterministic]


# ---------------------------------------------------------------------------
# Criteria and weighted ranking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Criterion:
    """One scoring axis and its weight.

    ``direction="higher"`` (default) means a higher score is better.
    ``direction="lower"`` means the candidate's score on this axis is a raw
    *value-like* number (e.g. a normalised cost or error rate) and a LOWER one is
    better, so the ranking inverts it.
    """

    name: str
    weight: float = 1.0
    direction: str = "higher"

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(f"criterion {self.name!r}: weight must be >= 0, got {self.weight}")
        if self.direction not in ("higher", "lower"):
            raise ValueError(
                f"criterion {self.name!r}: direction must be 'higher' or 'lower', got {self.direction!r}"
            )

    def effective(self, raw: float) -> float:
        return raw if self.direction == "higher" else 1.0 - raw


@dataclass(frozen=True)
class Score:
    candidate: Candidate
    total: float                      # normalised weighted total, 0..1
    breakdown: Dict[str, float]       # criterion -> normalised weighted contribution

    def contribution(self, criterion: str) -> float:
        return self.breakdown.get(criterion, 0.0)


@dataclass(frozen=True)
class Ranked:
    """Candidates ordered best-first, with the weights used."""

    scores: List[Score]
    criteria: List[Criterion]
    weight_total: float

    @property
    def winner(self) -> Score:
        if not self.scores:
            raise ValueError("nothing was ranked")
        return self.scores[0]

    @property
    def runner_up(self) -> Optional[Score]:
        return self.scores[1] if len(self.scores) > 1 else None

    def by_name(self) -> Dict[str, Score]:
        return {score.candidate.name: score for score in self.scores}

    def order(self) -> List[str]:
        return [score.candidate.name for score in self.scores]


def score_candidates(candidates: Sequence[Candidate], criteria: Sequence[Criterion]) -> Ranked:
    """Weighted ranking with normalised weights and a deterministic tie-break.

    Tie-break: exact ties go to the deterministic/simpler candidate, then
    alphabetically by name - so the same inputs always produce the same order.
    """
    if not candidates:
        raise ValueError("no candidates to score")
    if not criteria:
        raise ValueError("no criteria to score against")
    weight_total = sum(c.weight for c in criteria)
    if weight_total <= 0:
        raise ValueError("criteria weights sum to 0")

    for candidate in candidates:
        for criterion in criteria:
            if criterion.name not in candidate.scores:
                raise ValueError(f"{candidate.name}: missing a score for criterion {criterion.name!r}")

    scores: List[Score] = []
    for candidate in candidates:
        breakdown = {
            criterion.name: criterion.weight * criterion.effective(candidate.scores[criterion.name]) / weight_total
            for criterion in criteria
        }
        scores.append(Score(candidate, sum(breakdown.values()), breakdown))

    scores.sort(key=lambda s: (-round(s.total, 12), 0 if s.candidate.is_deterministic else 1, s.candidate.name))
    return Ranked(scores, list(criteria), weight_total)


# ---------------------------------------------------------------------------
# Verifiability gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateWarning:
    severity: str      # "block" | "warn"
    message: str


@dataclass(frozen=True)
class GateVerdict:
    allowed: bool
    warnings: List[GateWarning]

    @property
    def blocking(self) -> List[GateWarning]:
        return [w for w in self.warnings if w.severity == "block"]

    def __bool__(self) -> bool:
        return self.allowed


def verifiability_gate(
    candidate: Candidate, *, stakes: str = "medium", requires_exactness: bool = False
) -> GateVerdict:
    """Flag the risky combinations: low verifiability where errors are costly.

    * high stakes + unverifiable  -> BLOCK (add a verifier/human review, or go
      deterministic)
    * medium stakes + unverifiable -> warn
    * exactness required + not exact -> BLOCK
    * verifiable LLM -> warn only, telling you to actually *build* the verifier
      (that is what makes best-of-N / self-consistency viable)
    """
    warnings: List[GateWarning] = []
    if not candidate.verifiable and stakes == "high":
        warnings.append(
            GateWarning(
                "block",
                f"{candidate.name}: high stakes with no cheap way to check the output - "
                "add a verifier or human review, or choose a deterministic/exact candidate",
            )
        )
    elif not candidate.verifiable and stakes == "medium":
        warnings.append(
            GateWarning("warn", f"{candidate.name}: medium stakes with unverifiable output - plan a sampling audit")
        )
    if requires_exactness and not candidate.exact:
        warnings.append(
            GateWarning(
                "block",
                f"{candidate.name}: exactness is required but the candidate only approximates "
                f"(kind={candidate.kind})",
            )
        )
    if candidate.is_llm and candidate.verifiable:
        warnings.append(
            GateWarning(
                "warn",
                f"{candidate.name}: output is verifiable - ship the verifier, not just the prompt "
                "(a verifier is what makes best-of-N / self-consistency viable, topic 20)",
            )
        )
    allowed = not any(w.severity == "block" for w in warnings)
    return GateVerdict(allowed, warnings)


NEVER_LLM: Dict[str, str] = {
    "arithmetic": "exact arithmetic has one right answer: call a calculator or code, not a sampler",
    "unit_conversion": "deterministic transforms are exactly testable: write the function",
    "deterministic_transform": "a deterministic transform belongs in code, where it is testable and free",
    "authorization": "authorization must be exact and auditable: policy code, not a model",
    "cryptographic_exactness": "cryptographic operations must be exact and constant-time: never a model",
    "legal_exactness": "exact legal wording must not be paraphrased by a model",
    "arithmetic_over_documents": "totals must reconcile exactly: extract with a parser, then compute in code",
}


def never_llm_reason(feature_kind: str) -> Optional[str]:
    """Why this feature kind must not be an LLM, or None if it may be."""
    return NEVER_LLM.get(feature_kind)


# ---------------------------------------------------------------------------
# Decision + sensitivity ("what flips it")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlipFinding:
    criterion: str
    required_score_drop: float   # how far the winner's score on this axis must FALL
    feasible: bool               # can that much drop actually happen?
    runner_up: str
    narrative: str


@dataclass(frozen=True)
class Sensitivity:
    runner_up: Optional[str]
    findings: List[FlipFinding]

    @property
    def closest(self) -> Optional[FlipFinding]:
        """The most fragile axis: the smallest drop that hands the win over."""
        if not self.findings:
            return None
        ranked = sorted(self.findings, key=lambda f: (not f.feasible, f.required_score_drop))
        return ranked[0]


def flip_thresholds(ranked: Ranked, *, winner_index: int = 0) -> Sensitivity:
    """Analytic sensitivity: how far the winner's score must fall on each axis.

    ``total = sum(w_i * s_i) / W``, so dropping the winner's score on one criterion
    by ``d`` costs ``w_i * d / W``. Setting that equal to the margin over the
    runner-up gives ``d* = (winner_total - runner_total) * W / w_i``.
    """
    if len(ranked.scores) <= winner_index + 1:
        return Sensitivity(runner_up=None, findings=[])
    winner = ranked.scores[winner_index]
    runner = ranked.scores[winner_index + 1]
    margin = winner.total - runner.total
    findings: List[FlipFinding] = []
    for criterion in ranked.criteria:
        if criterion.weight <= 0:
            continue
        required = margin * ranked.weight_total / criterion.weight
        current = winner.candidate.scores[criterion.name]
        findings.append(
            FlipFinding(
                criterion=criterion.name,
                required_score_drop=required,
                feasible=required <= current,
                runner_up=runner.candidate.name,
                narrative=(
                    f"if '{criterion.name}' for {winner.candidate.name} falls by >= {required:.3f} "
                    f"(now {current:.2f}), {runner.candidate.name} wins"
                ),
            )
        )
    return Sensitivity(runner_up=runner.candidate.name, findings=findings)


@dataclass(frozen=True)
class Delta:
    """One what-if change: move a candidate's score, or reweight a criterion."""

    description: str
    criterion: str
    candidate: str
    score_delta: float = 0.0
    weight_multiplier: float = 1.0


@dataclass(frozen=True)
class SensitivityCheck:
    delta: Delta
    flipped: bool
    new_winner: str

    @property
    def reason(self) -> str:
        return (
            f"{self.delta.description} -> winner becomes {self.new_winner}"
            if self.flipped
            else f"{self.delta.description} -> still {self.new_winner} (no flip)"
        )


def sensitivity(decision: "Decision", deltas: Sequence[Delta]) -> List[SensitivityCheck]:
    """Re-run the ranking under each single change and report which ones flip it."""
    checks: List[SensitivityCheck] = []
    for delta in deltas:
        candidates = []
        for candidate in decision.ranked.scores:
            item = candidate.candidate
            if item.name == delta.candidate and delta.score_delta:
                item = item.with_score(
                    delta.criterion,
                    min(1.0, max(0.0, item.scores[delta.criterion] + delta.score_delta)),
                )
            candidates.append(item)
        criteria = [
            replace(c, weight=c.weight * delta.weight_multiplier) if c.name == delta.criterion else c
            for c in decision.ranked.criteria
        ]
        reranked = score_candidates(candidates, criteria)
        new_winner = reranked.winner.candidate.name
        checks.append(SensitivityCheck(delta, new_winner != decision.winner.name, new_winner))
    return checks


@dataclass(frozen=True)
class Decision:
    """The justified choice, with the flip condition that would overturn it."""

    winner: Candidate
    ranked: Ranked
    constraints: ConstraintResult
    justification: str
    flip_condition: str
    gate: GateVerdict
    stakes: str = "medium"

    @property
    def alternatives(self) -> List[str]:
        return [s.candidate.name for s in self.ranked.scores[1:]]

    def report(self) -> str:
        lines: List[str] = []
        lines.append(f"DECISION  {self.winner.name} ({self.winner.kind})   stakes={self.stakes}")
        lines.append("  constraints:")
        lines += [f"    {line}" for line in self.constraints.report()]
        lines.append("  ranking:")
        for score in self.ranked.scores:
            lines.append(f"    {score.candidate.name:14s} {score.total:.3f}")
        lines.append(f"  rationale: {self.justification}")
        lines.append(f"  flip condition: {self.flip_condition}")
        strength = flip_thresholds(self.ranked).closest
        if strength is not None:
            lines.append(f"  most fragile axis: {strength.narrative}")
        for warning in self.gate.warnings:
            lines.append(f"  [{warning.severity.upper()}] {warning.message}")
        return "\n".join(lines)


def decide(
    candidates: Sequence[Candidate],
    criteria: Sequence[Criterion],
    constraints: Sequence[Constraint] = (),
    *,
    stakes: str = "medium",
    requires_exactness: bool = False,
) -> Decision:
    """Constraints -> candidates -> trade-offs -> justified choice + sensitivity."""
    if stakes not in ("low", "medium", "high"):
        raise ValueError(f"stakes must be low|medium|high, got {stakes!r}")

    filtered = apply_hard_constraints(candidates, constraints)
    if not filtered.survivors:
        blocked = ", ".join(f"{e.candidate.name} ({e.constraint.name})" for e in filtered.eliminated)
        raise ValueError(
            "no candidate survives the hard constraints - relax a constraint or add a candidate: " + blocked
        )

    ranked = score_candidates(filtered.survivors, criteria)
    winner = ranked.winner
    gate = verifiability_gate(winner.candidate, stakes=stakes, requires_exactness=requires_exactness)

    deterministic = deterministic_first(filtered.survivors)
    deterministic_eliminated = [e for e in filtered.eliminated if e.candidate.is_deterministic]
    decisive = [
        c.name
        for c in ranked.criteria
        if winner.contribution(c.name) > 0.0
    ]
    decisive.sort(key=lambda name: -winner.contribution(name))
    others = len(ranked.scores) - 1
    parts = [
        f"{winner.candidate.name} ({winner.candidate.kind}) scores {winner.total:.3f}, "
        f"clear of {others} alternative{'s' if others != 1 else ''}"
    ]
    if ranked.runner_up is not None:
        parts.append(f"runner-up {ranked.runner_up.candidate.name} at {ranked.runner_up.total:.3f}")
    parts.append("decisive axes: " + ", ".join(decisive[:3]))
    if winner.candidate.is_deterministic:
        parts.append(
            "deterministic-first rule applied: a deterministic method meets the requirement "
            "(cheaper, exactly testable, no hallucination or prompt-injection surface)"
        )
    elif deterministic_eliminated:
        killed = ", ".join(f"{e.candidate.name} ({e.constraint.name})" for e in deterministic_eliminated)
        parts.append(
            "deterministic option(s) existed but were eliminated by hard constraints "
            f"[{killed}], so an LLM candidate is justified here"
        )
    justification = "; ".join(parts)

    if ranked.runner_up is None:
        flip = (
            "no rival survives the hard constraints: only a changed constraint, a new candidate, "
            "or a verifier/replay failure flips this"
        )
    else:
        closest = flip_thresholds(ranked).closest
        assert closest is not None
        flip = closest.narrative
        if not closest.feasible:
            flip += " (not reachable by this axis alone: the margin is larger than the score itself)"

    return Decision(
        winner=winner.candidate,
        ranked=ranked,
        constraints=filtered,
        justification=justification,
        flip_condition=flip,
        gate=gate,
        stakes=stakes,
    )


# ---------------------------------------------------------------------------
# Worked-example helpers: extraction, task type, FAQ
# ---------------------------------------------------------------------------

# Criteria used by the worked examples.
EXTRACTION_CRITERIA = [
    Criterion("accuracy", 0.35),
    Criterion("robustness", 0.25),
    Criterion("verifiability", 0.20),
    Criterion("maintainability", 0.20),
]
TASK_TYPE_CRITERIA = [
    Criterion("quality", 0.40),
    Criterion("cost_performance", 0.30),
    Criterion("latency_performance", 0.20),
    Criterion("verifiability", 0.10),
]
FAQ_CRITERIA = [
    Criterion("answer_quality", 0.40),
    Criterion("cost_performance", 0.25),
    Criterion("latency_performance", 0.20),
    Criterion("verifiability", 0.15),
]


def _extraction_candidates(scenario: str) -> List[Candidate]:
    parser = Candidate(
        "regex-parser",
        KIND_REGEX,
        latency_ms=2.0,
        cost_usd=0.0,
        exact=True,
        verifiable=True,
        notes="grammar over a known layout; unit-testable against a replay corpus",
    )
    small = Candidate(
        "small-llm-structured",
        KIND_SMALL_LLM,
        latency_ms=900.0,
        cost_usd=0.0004,
        requires_network=True,
        exact=False,
        verifiable=True,
        notes="schema-constrained extraction; the schema validation IS the verifier",
    )
    large = Candidate(
        "large-llm-structured",
        KIND_LARGE_LLM,
        latency_ms=2500.0,
        cost_usd=0.008,
        requires_network=True,
        exact=False,
        verifiable=True,
        notes="best raw accuracy on messy, unseen layouts",
    )
    if scenario == "known_stable":
        parser = replace(parser, scores={"accuracy": 1.0, "robustness": 0.80, "verifiability": 1.0, "maintainability": 0.70})
        small = replace(small, scores={"accuracy": 0.93, "robustness": 0.80, "verifiability": 0.80, "maintainability": 0.80})
        large = replace(large, scores={"accuracy": 0.96, "robustness": 0.85, "verifiability": 0.80, "maintainability": 0.60})
    elif scenario == "known_drifting":
        parser = replace(parser, scores={"accuracy": 0.55, "robustness": 0.05, "verifiability": 1.0, "maintainability": 0.30})
        small = replace(small, scores={"accuracy": 0.93, "robustness": 0.80, "verifiability": 0.80, "maintainability": 0.80})
        large = replace(large, scores={"accuracy": 0.96, "robustness": 0.85, "verifiability": 0.80, "maintainability": 0.60})
    else:  # unstructured
        parser = replace(parser, scores={"accuracy": 0.20, "robustness": 0.00, "verifiability": 1.0, "maintainability": 0.20})
        small = replace(small, scores={"accuracy": 0.80, "robustness": 0.70, "verifiability": 0.80, "maintainability": 0.80})
        large = replace(large, scores={"accuracy": 0.97, "robustness": 0.90, "verifiability": 0.80, "maintainability": 0.60})
    return [parser, small, large]


def choose_extraction(
    sample: str,
    known_format: bool,
    *,
    format_stability: str = "stable",
    stakes: str = "medium",
) -> Decision:
    """Regex/parser vs LLM extraction. The classic flip.

    * known format + stable -> the parser wins (deterministic, exact, free)
    * known format + drifting -> the small LLM with schema validation wins
    * unknown/unstructured -> the large LLM wins
    """
    if format_stability not in ("stable", "seasonal", "drifting"):
        raise ValueError(f"format_stability must be stable|seasonal|drifting, got {format_stability!r}")
    if known_format and format_stability == "stable":
        scenario = "known_stable"
    elif known_format:
        scenario = "known_drifting"
    else:
        scenario = "unstructured"
    decision = decide(_extraction_candidates(scenario), EXTRACTION_CRITERIA, stakes=stakes)
    flips = {
        "known_stable": (
            "if the vendor schema drifts (unparsed-field rate climbing past ~2%/week) or a second "
            "format appears, parser accuracy collapses and small-llm-structured wins on accuracy"
        ),
        "known_drifting": (
            "if the layout is frozen and validated regex coverage reaches 100% on a replay corpus, "
            "regex-parser wins on cost, latency, exactness and testability"
        ),
        "unstructured": (
            "if the documents are narrowed to one template with a published schema (and a sample of "
            "unseen documents parses cleanly), the parser or a classifier replaces the LLM"
        ),
    }
    decision = replace(decision, flip_condition=flips[scenario])
    if decision.winner.is_deterministic:
        decision = replace(
            decision,
            justification=decision.justification
            + f" [sample prefix checked: {sample.strip()[:40]!r}]",
        )
    return decision


def choose_task_type(task: str) -> Decision:
    """Closed-set labels -> a classifier; open-ended output -> generation.

    A keyword heuristic, deliberately crude: this helper demonstrates the *shape*
    of the argument, not a production router.
    """
    lowered = task.lower()
    closed_hints = (
        "route", "routing", "triage", "classif", "label", "categor", "intent",
        "sentiment", "priority", "spam", "tag",
    )
    open_hints = (
        "summar", "explain", "write", "draft", "rewrite", "compose", "generate",
        "brainstorm", "translate", "answer", "paraphrase", "chat",
    )
    closed_hits = [h for h in closed_hints if h in lowered]
    open_hits = [h for h in open_hints if h in lowered]
    no_signal = not closed_hits and not open_hits
    closed_set = no_signal or (len(closed_hits) >= len(open_hits) and bool(closed_hits))

    classifier = Candidate(
        "classifier",
        KIND_CLASSIFIER,
        latency_ms=5.0,
        cost_usd=0.0,
        exact=True,
        verifiable=True,
        notes="train on labelled history; every prediction is testable against a held-out set",
    )
    generation = Candidate(
        "generation",
        KIND_SMALL_LLM,
        latency_ms=900.0,
        cost_usd=0.0004,
        requires_network=True,
        exact=False,
        verifiable=not closed_set,
        notes="writes the answer, not a label",
    )
    if closed_set:
        classifier = replace(classifier, scores={"quality": 0.90, "cost_performance": 1.0, "latency_performance": 1.0, "verifiability": 1.0})
        generation = replace(generation, scores={"quality": 0.95, "cost_performance": 0.30, "latency_performance": 0.35, "verifiability": 0.60})
        flip = (
            "flips if the label set stops being fixed (new categories appear weekly, or labels need "
            "rationales) - then the closed-set classifier has no target and generation wins"
        )
        if no_signal:
            justification_extra = (
                "no open-ended output signals in the task description: with nothing demanding free-form "
                "text, deterministic-first prefers the cheaper, exactly testable candidate"
            )
        else:
            justification_extra = (
                f"closed-set signals found {closed_hits}: a fixed label set is a classification problem, "
                "and a classifier runs ~180x faster at ~5% less quality (and ~0 per request)"
            )
    else:
        classifier = replace(classifier, scores={"quality": 0.10, "cost_performance": 1.0, "latency_performance": 1.0, "verifiability": 0.60})
        generation = replace(generation, scores={"quality": 0.95, "cost_performance": 0.50, "latency_performance": 0.50, "verifiability": 0.40})
        flip = (
            "flips if the output can be constrained to a finite label set with ground-truth labels - "
            "then train the classifier and keep the LLM only as a labelling/weak-supervision aid"
        )
        justification_extra = (
            f"open-ended signals found {open_hits}: the output is text with many acceptable answers, "
            "which a classifier cannot produce at all"
        )
    decision = decide([classifier, generation], TASK_TYPE_CRITERIA, stakes="medium")
    return replace(decision, justification=decision.justification + "; " + justification_extra, flip_condition=flip)


def choose_faq(
    corpus_size: int,
    *,
    question_variety: str = "fixed",
    answers_span_documents: bool = False,
) -> Decision:
    """Fixed FAQ -> a lookup table; varied questions -> retrieval; synthesis -> RAG."""
    if corpus_size < 1:
        raise ValueError("corpus_size must be >= 1")
    if question_variety not in ("fixed", "paraphrased", "varied"):
        raise ValueError(f"question_variety must be fixed|paraphrased|varied, got {question_variety!r}")

    if answers_span_documents:
        scenario = "synthesis"
    elif question_variety != "fixed" or corpus_size > 200:
        scenario = "varied"
    else:
        scenario = "fixed"

    lookup = Candidate(
        "lookup-table",
        KIND_LOOKUP,
        latency_ms=1.0,
        cost_usd=0.0,
        exact=True,
        verifiable=True,
        notes="exact/near-exact match on a curated question list",
    )
    retrieval = Candidate(
        "embedding-retrieval",
        KIND_EMBEDDING,
        latency_ms=25.0,
        cost_usd=0.00002,
        requires_network=False,
        exact=False,
        verifiable=True,
        notes="nearest-neighbour over embedded FAQs; the source chunk is the citation",
    )
    rag = Candidate(
        "rag-generation",
        KIND_SMALL_LLM,
        latency_ms=1200.0,
        cost_usd=0.0006,
        requires_network=True,
        exact=False,
        verifiable=False,
        notes="retrieve then write; needed only when the answer must be synthesised",
    )
    if scenario == "fixed":
        lookup = replace(lookup, scores={"answer_quality": 0.95, "cost_performance": 0.90, "latency_performance": 0.95, "verifiability": 0.95})
        retrieval = replace(retrieval, scores={"answer_quality": 0.85, "cost_performance": 0.70, "latency_performance": 0.75, "verifiability": 0.70})
        rag = replace(rag, scores={"answer_quality": 0.90, "cost_performance": 0.40, "latency_performance": 0.45, "verifiability": 0.55})
        flip = (
            f"flips if the FAQ stops being fixed ({corpus_size} entries is small today): once questions "
            "are paraphrased, exact lookup misses and embedding-retrieval wins on answer_quality"
        )
    elif scenario == "varied":
        lookup = replace(lookup, scores={"answer_quality": 0.30, "cost_performance": 0.90, "latency_performance": 0.95, "verifiability": 0.95})
        retrieval = replace(retrieval, scores={"answer_quality": 0.90, "cost_performance": 0.70, "latency_performance": 0.75, "verifiability": 0.70})
        rag = replace(rag, scores={"answer_quality": 0.92, "cost_performance": 0.40, "latency_performance": 0.45, "verifiability": 0.55})
        flip = (
            "flips if the answers start spanning several documents (then retrieval alone returns a "
            "shelf of chunks instead of an answer, and rag-generation wins) - or if a curated "
            "question list is restored, where the lookup table is free and exact"
        )
    else:
        lookup = replace(lookup, scores={"answer_quality": 0.05, "cost_performance": 0.90, "latency_performance": 0.95, "verifiability": 0.95})
        retrieval = replace(retrieval, scores={"answer_quality": 0.45, "cost_performance": 0.70, "latency_performance": 0.75, "verifiability": 0.70})
        rag = replace(rag, scores={"answer_quality": 0.95, "cost_performance": 0.40, "latency_performance": 0.45, "verifiability": 0.55})
        flip = (
            "flips if every answer fits inside one retrievable chunk (then embedding-retrieval is "
            "enough and the generation step is pure cost), or if the corpus is curated into a fixed "
            "question list, where the lookup table wins outright"
        )
    decision = decide([lookup, retrieval, rag], FAQ_CRITERIA, stakes="low")
    return replace(decision, flip_condition=flip)

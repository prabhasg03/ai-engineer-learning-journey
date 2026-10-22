"""Topic 28 - where RAG fails, and how to tell which stage failed.

Given only symptoms, the job is to name the stage that broke. This module is a
small, deterministic diagnostic harness:

- ``Case`` is one observed query: what was retrieved, what reached the prompt,
  what the model answered, and what the labelled outcome was.
- ``locate_stage`` is the decision procedure: corpus miss -> retrieval miss ->
  ranking miss -> generation miss.
- ``diagnose`` adds *causes* (stale index, conflicting chunks, bad citations,
  over-abstention) on top of the symptomatic label, because "retrieval miss"
  is what you observe and "the index is 45 days stale" is why.
- ``BOUNDARIES`` is the failure-boundary habit written down: for every stage,
  what breaks, how you would notice, and what you would change.
- ``run_suite`` scores a labelled fixture so the diagnostic logic itself is
  tested the way an eval harness would test it.

No model, no network, no clock: every case is data, every diagnosis is a pure
function of that data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

STAGES = (
    "ingest",
    "chunk",
    "embed",
    "store",
    "query",
    "retrieve",
    "assemble",
    "answer",
)

LABELS = ("ok", "retrieval_miss", "ranking_miss", "generation_miss", "unanswerable")

# A stale-index probe older than this is treated as a likely cause.
STALE_AFTER_DAYS = 30

_ABSTENTION_PHRASES = (
    "i don't know",
    "i do not know",
    "cannot answer",
    "can't answer",
    "unable to answer",
    "not enough information",
    "no information",
)


def is_abstention(answer: str) -> bool:
    """Detect a refusal. Over-abstention is a generation failure, not success."""
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _ABSTENTION_PHRASES)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One observed RAG query, including the intermediate sets.

    ``retrieved_ids`` is the retriever's ordered result (say top 20);
    ``prompted_ids`` is the subset that survived dedupe/budget/reranking into
    the final prompt. Keeping both is what makes ranking misses separable from
    retrieval misses.
    """

    case_id: str
    question: str
    gold_ids: tuple[str, ...]
    corpus_ids: tuple[str, ...]
    retrieved_ids: tuple[str, ...]
    prompted_ids: tuple[str, ...]
    answer: str
    answer_correct: bool
    cited_ids: tuple[str, ...] = ()
    index_age_days: int = 0
    doc_changed_since_ingest: bool = False
    expected: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.expected and self.expected not in LABELS:
            raise ValueError(f"unknown expected label {self.expected!r}; expected one of {LABELS}")
        if self.index_age_days < 0:
            raise ValueError("index_age_days cannot be negative")


# ---------------------------------------------------------------------------
# The core decision procedure
# ---------------------------------------------------------------------------


def locate_stage(
    gold_in_corpus: bool,
    gold_retrieved: bool,
    gold_in_prompt: bool,
    answer_correct: bool,
) -> str:
    """Symptom -> stage. The order of the checks is the whole method.

    1. If the corpus does not contain the answer, nothing downstream can be
       blamed: the question is unanswerable by this corpus.
    2. If it exists but was not retrieved, the retrieval stage missed it.
    3. If it was retrieved but did not reach the prompt, ranking/assembly
       dropped it.
    4. If it reached the prompt and the answer is still wrong, generation
       ignored or contradicted the evidence.
    """
    if not gold_in_corpus:
        return "unanswerable"
    if not gold_retrieved:
        return "retrieval_miss"
    if not gold_in_prompt:
        return "ranking_miss"
    if not answer_correct:
        return "generation_miss"
    return "ok"


SYMPTOMS = {
    "ok": "the answer is supported by evidence that reached the prompt",
    "retrieval_miss": "the answer-bearing chunk never came back from retrieval",
    "ranking_miss": "the answer-bearing chunk was retrieved but did not survive into the prompt",
    "generation_miss": "the answer-bearing chunk was in the prompt and the answer still missed",
    "unanswerable": "the corpus does not contain the answer; the only correct answer is abstention",
}

# ---------------------------------------------------------------------------
# Causes: stale indices, conflicts, citations, over-abstention
# ---------------------------------------------------------------------------

_CLAIM_RE = re.compile(
    r"\bthe\s+(?P<subject>[a-z][a-z ]{2,40}?)\s+is\s+"
    r"(?P<value>\d+)\s+(?P<unit>days?|hours?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)


def _singular(unit: str) -> str:
    return unit[:-1] if unit.lower().endswith("s") else unit.lower()


@dataclass(frozen=True)
class Claim:
    chunk_id: str
    subject: str
    value: int
    unit: str


@dataclass(frozen=True)
class Conflict:
    subject: str
    statements: tuple[tuple[str, str], ...]  # (chunk_id, "30 days")


def extract_claims(chunk_texts: dict[str, str]) -> list[Claim]:
    """Pull simple numeric policy claims: "the <subject> is <n> <unit>"."""
    claims: list[Claim] = []
    for chunk_id in sorted(chunk_texts):
        for match in _CLAIM_RE.finditer(chunk_texts[chunk_id]):
            subject = " ".join(match.group("subject").lower().split())
            claims.append(
                Claim(
                    chunk_id=chunk_id,
                    subject=subject,
                    value=int(match.group("value")),
                    unit=_singular(match.group("unit")),
                )
            )
    return claims


def find_conflicts(claims: list[Claim]) -> list[Conflict]:
    """Two chunks state different values for the same subject -> conflict.

    Real systems should prefer the authoritative/newer source, or surface the
    contradiction instead of letting the model pick arbitrarily.
    """
    grouped: dict[str, list[Claim]] = {}
    for claim in claims:
        grouped.setdefault(claim.subject, []).append(claim)
    conflicts: list[Conflict] = []
    for subject in sorted(grouped):
        items = grouped[subject]
        if len({(item.value, item.unit) for item in items}) <= 1:
            continue
        statements = tuple(
            sorted(
                {
                    (
                        item.chunk_id,
                        f"{item.value} {item.unit}{'' if item.value == 1 else 's'}",
                    )
                    for item in items
                }
            )
        )
        conflicts.append(Conflict(subject=subject, statements=statements))
    return conflicts


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Diagnosis:
    case_id: str
    label: str
    symptom: str
    causes: tuple[str, ...]
    fixes: tuple[str, ...]
    notes: str

    def as_row(self) -> str:
        causes = ", ".join(self.causes) if self.causes else "-"
        return f"{self.case_id:<24} {self.label:<16} causes: {causes}"


BASE_FIXES = {
    "ok": (),
    "retrieval_miss": (
        "check chunking: the answer may be split across chunks or buried in boilerplate",
        "try hybrid retrieval (BM25 + vector) - exact names/IDs are where embeddings fail",
        "verify ANN recall (ef_search / probes) or run exact search on the same query",
        "re-embed with a stronger model; check query/document prefixes match",
        "check filters: metadata filters and tenant scoping can remove the only good chunk",
    ),
    "ranking_miss": (
        "rerank the retrieved set with a cross-encoder before budgeting",
        "retrieve a larger candidate set, then cut to the prompt budget",
        "deduplicate near-identical chunks so duplicates cannot crowd out the answer",
        "fix assembly: budget accounting, truncation policy, sandwich ordering",
    ),
    "generation_miss": (
        "put the strongest evidence at the start and end of the context (lost in the middle)",
        "tighten the instruction: answer only from context, cite or abstain",
        "add a groundedness/citation validator and a verifier pass",
        "reduce conflicting or noisy evidence; the model may be following the wrong chunk",
    ),
    "unanswerable": (
        "teach and calibrate abstention; reward a refusal when the corpus lacks the answer",
        "add the missing source documents (or route to a human)",
        "run a coverage check before generation; do not let the model free-wheel",
    ),
}

CAUSE_FIXES = {
    "stale_index": "reindex on a schedule and on document change; add a freshness canary",
    "conflict": "resolve conflicting sources by recency/authority before assembly, or show both",
    "citation_mismatch": "validate citation markers against the assembled evidence map",
    "over_abstention": "lower the refusal threshold when the gold chunk is present; few-shot grounded answers",
    "prompt_pruned": "log why each candidate was dropped (dedupe vs budget) and re-check the cutoff",
    "answered_unanswerable": "add a coverage/abstention check; the model answered from parametric memory",
}


def diagnose(
    case: Case,
    chunks: dict[str, str] | None = None,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> Diagnosis:
    """Classify one case: symptomatic label + attributable causes."""
    gold = set(case.gold_ids)
    corpus = set(case.corpus_ids)
    retrieved = set(case.retrieved_ids)
    prompted = set(case.prompted_ids)

    gold_in_corpus = bool(gold) and gold <= corpus
    gold_retrieved = bool(gold) and gold <= retrieved
    gold_in_prompt = bool(gold) and gold <= prompted
    abstained = is_abstention(case.answer)

    causes: list[str] = []
    if case.index_age_days > stale_after_days or case.doc_changed_since_ingest:
        causes.append("stale_index")
    if len(prompted) < len(retrieved):
        causes.append("prompt_pruned")
    if chunks:
        prompted_texts = {cid: chunks[cid] for cid in case.prompted_ids if cid in chunks}
        if find_conflicts(extract_claims(prompted_texts)):
            causes.append("conflict")
    if any(cited not in prompted for cited in case.cited_ids):
        causes.append("citation_mismatch")
    if not gold_in_corpus and not abstained:
        causes.append("answered_unanswerable")
    if gold_in_prompt and not case.answer_correct and abstained:
        causes.append("over_abstention")
    causes = list(dict.fromkeys(causes))

    label = locate_stage(gold_in_corpus, gold_retrieved, gold_in_prompt, case.answer_correct)

    fixes = list(BASE_FIXES[label])
    for cause in causes:
        fix = CAUSE_FIXES.get(cause)
        if fix:
            fixes.append(fix)

    notes = (
        f"gold={sorted(gold) or '-'}; "
        f"in_corpus={gold_in_corpus}, retrieved={gold_retrieved}, prompted={gold_in_prompt}; "
        f"answer_correct={case.answer_correct}, abstained={abstained}; "
        f"retrieved_n={len(retrieved)}, prompted_n={len(prompted)}"
    )

    return Diagnosis(
        case_id=case.case_id,
        label=label,
        symptom=SYMPTOMS[label],
        causes=tuple(causes),
        fixes=tuple(dict.fromkeys(fixes)),
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Failure boundaries: what breaks / how you notice / what you change
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Boundary:
    stage: str
    breaks: str
    notice: str
    change: str


BOUNDARIES: dict[str, Boundary] = {
    "ingest": Boundary(
        stage="ingest",
        breaks="a loader silently skips, truncates or corrupts a source document; the index never contains it",
        notice="source-document count vs indexed-document count; per-document checksums; a zero-document crawl",
        change="assert counts and checksums, fail the job on empty sources, alert on ingest volume anomalies",
    ),
    "chunk": Boundary(
        stage="chunk",
        breaks="the answer is split across a boundary, diluted by boilerplate, or trapped in a table/code fence",
        notice="chunk-level recall on labelled questions; inspect the chunks around each gold answer",
        change="paragraph/semantic chunking, modest overlap, keep structured blocks intact, tune size per corpus",
    ),
    "embed": Boundary(
        stage="embed",
        breaks="query and document vectors are incomparable: model/prefix drift, truncation, zero vectors, OOV",
        notice="vector norms, model id pinned per row, retrieval evals after every model change",
        change="pin model + task prefix, reject zero vectors, reindex on model change, evaluate on labelled queries",
    ),
    "store": Boundary(
        stage="store",
        breaks="stale rows from old document versions, partial writes, a missing/never-built index",
        notice="freshness canary document, row counts per source, index build logs, age of newest row",
        change="idempotent upserts keyed by chunk id, prune removed chunks, reindex triggers, freshness SLO",
    ),
    "query": Boundary(
        stage="query",
        breaks="the query is rewritten into something else, is empty, or is embedded with a different model/prefix",
        notice="log the final query text and its norm; compare rewritten vs raw query retrieval",
        change="guard query rewriting, fall back to the raw question, keep one embedding contract",
    ),
    "retrieve": Boundary(
        stage="retrieve",
        breaks="ANN under-recall, filters remove the answer, k is larger than the index, post-filtering returns too few",
        notice="recall@k vs exact search; filter cardinality; count returned rows vs requested k",
        change="raise ef_search/probes, pre-filter instead of post-filter, hybrid search, over-retrieve then rerank",
    ),
    "assemble": Boundary(
        stage="assemble",
        breaks="the answer-bearing chunk is deduped away, budget-dropped, truncated, or buried in the middle",
        notice="assert the gold chunk is cited; log dropped candidates and their reasons; record prompt order",
        change="budget accounting, near-duplicate detection, sandwich ordering, citation slots built at assembly",
    ),
    "answer": Boundary(
        stage="answer",
        breaks="the model ignores context, hallucinates, cites an unsupported source, or abstains when evidence is present",
        notice="groundedness/citation checks; gold-in-context counterfactual; refusal rate by answerability",
        change="grounded instructions, citation validation, verifier pass, calibrated abstention",
    ),
}

BOUNDARY_STAGES = tuple(BOUNDARIES)


def failure_boundary(stage: str) -> Boundary:
    if stage not in BOUNDARIES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {list(BOUNDARY_STAGES)}")
    return BOUNDARIES[stage]


# ---------------------------------------------------------------------------
# Symptom -> first diagnostic move
# ---------------------------------------------------------------------------

SYMPTOM_GUIDE: dict[str, str] = {
    "answer is wrong but cites a real chunk": (
        "generation_miss: the evidence reached the prompt, so check whether the cited chunk "
        "actually contains the claim; if not, add a groundedness check."
    ),
    "answer says it does not know though the document exists": (
        "over_abstention (generation_miss): confirm the gold chunk is in the prompt, then "
        "loosen the refusal instruction or improve the evidence ordering."
    ),
    "new documents never show up in answers": (
        "stale_index / ingest: run a freshness canary, compare source count to index count, "
        "and check the reindex trigger."
    ),
    "two answers contradict each other": (
        "conflict (surfaces as generation_miss): two chunks state different values for the "
        "same fact; detect the conflict at assembly and prefer recency/authority or surface both."
    ),
    "retrieval returns similar chunks but never the exact one": (
        "retrieval_miss: inspect chunk boundaries and ANN recall; try hybrid search and a "
        "larger ef_search/probes."
    ),
    "the answer cites a source that was not in the prompt": (
        "citation_mismatch (generation_miss): validate markers against the assembly map before "
        "returning the answer."
    ),
    "the answer is plausible but cites nothing": (
        "generation_miss / hallucination: require citations and run a groundedness check; "
        "abstain when no chunk supports the claim."
    ),
    "the model answers a question the corpus cannot answer": (
        "unanswerable: add a coverage check before generation and calibrate abstention; the "
        "answer came from parametric memory."
    ),
}


def guide(symptom: str) -> str:
    """Look up a symptom; accepts exact keys or a distinctive substring."""
    if symptom in SYMPTOM_GUIDE:
        return SYMPTOM_GUIDE[symptom]
    lowered = symptom.lower()
    matches = [key for key in SYMPTOM_GUIDE if lowered in key.lower()]
    if len(matches) == 1:
        return SYMPTOM_GUIDE[matches[0]]
    raise ValueError(f"unknown symptom {symptom!r}; known symptoms: {sorted(SYMPTOM_GUIDE)}")


# ---------------------------------------------------------------------------
# Suite scoring
# ---------------------------------------------------------------------------


@dataclass
class SuiteReport:
    total: int
    scored: int
    correct: int
    accuracy: float
    by_label: dict[str, int] = field(default_factory=dict)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"cases={self.total} scored={self.scored} correct={self.correct} "
            f"accuracy={self.accuracy:.2f}",
            "labels: " + ", ".join(f"{label}={count}" for label, count in sorted(self.by_label.items())),
        ]
        if self.mismatches:
            lines.append("mismatches: " + ", ".join(self.mismatches))
        return "\n".join(lines)


def run_suite(cases: list[Case], chunks: dict[str, str] | None = None) -> SuiteReport:
    """Diagnose every case and score labels against the fixture's expectations."""
    diagnoses = [diagnose(case, chunks=chunks) for case in cases]
    scored = sum(1 for case in cases if case.expected)
    correct = sum(
        1
        for case, diagnosis in zip(cases, diagnoses)
        if case.expected and diagnosis.label == case.expected
    )
    by_label: dict[str, int] = {}
    for diagnosis in diagnoses:
        by_label[diagnosis.label] = by_label.get(diagnosis.label, 0) + 1
    mismatches = [
        case.case_id
        for case, diagnosis in zip(cases, diagnoses)
        if case.expected and diagnosis.label != case.expected
    ]
    return SuiteReport(
        total=len(cases),
        scored=scored,
        correct=correct,
        accuracy=(correct / scored) if scored else 0.0,
        by_label=by_label,
        diagnoses=diagnoses,
        mismatches=mismatches,
    )


# ---------------------------------------------------------------------------
# Labelled fixture (also used by the notebook)
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = {
    "returns#00": (
        "We accept returns within 30 days of delivery. "
        "Refunds are issued within 5 business days after inspection."
    ),
    "returns#01": "Sale items are final sale and cannot be returned.",
    "returns#02": "The return window is 14 days for international orders.",
    "shipping#00": (
        "Shipping damage claims must be filed within 48 hours and require photos "
        "of the box and the item."
    ),
    "warranty#00": (
        "Manufacturer warranties cover defects for 12 months from the purchase date."
    ),
    "faq#00": "Orders can be tracked from the account page.",
    "policy#old": "The return window is 30 days for all customers.",
    "policy#new": "The return window is 14 days for all customers.",
}

_CORPUS = tuple(sorted(SAMPLE_CHUNKS))

SAMPLE_CASES = [
    Case(
        case_id="ok",
        question="How many days do I have to return an item?",
        gold_ids=("returns#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#00", "returns#01", "shipping#00"),
        prompted_ids=("returns#00", "returns#01", "shipping#00"),
        answer="Returns are accepted within 30 days of delivery. [1]",
        answer_correct=True,
        cited_ids=("returns#00",),
        expected="ok",
    ),
    Case(
        case_id="retrieval-miss",
        question="How long is the warranty?",
        gold_ids=("warranty#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#00", "shipping#00", "faq#00"),
        prompted_ids=("returns#00", "shipping#00", "faq#00"),
        answer="Warranties last 24 months. [1]",
        answer_correct=False,
        cited_ids=("returns#00",),
        expected="retrieval_miss",
    ),
    Case(
        case_id="ranking-miss",
        question="What is the return window for international orders?",
        gold_ids=("returns#02",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#00", "returns#02", "shipping#00"),
        prompted_ids=("returns#00", "shipping#00"),
        answer="Returns are accepted within 30 days. [1]",
        answer_correct=False,
        cited_ids=("returns#00",),
        expected="ranking_miss",
    ),
    Case(
        case_id="generation-miss",
        question="How long do manufacturer warranties cover defects?",
        gold_ids=("warranty#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("warranty#00", "returns#00"),
        prompted_ids=("warranty#00", "returns#00"),
        answer="Warranties cover defects for 24 months. [1]",
        answer_correct=False,
        cited_ids=("warranty#00",),
        expected="generation_miss",
    ),
    Case(
        case_id="unanswerable",
        question="Do you price match competitors?",
        gold_ids=("refunds#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#00", "faq#00"),
        prompted_ids=("returns#00", "faq#00"),
        answer="I don't know based on the available context.",
        answer_correct=True,
        expected="unanswerable",
    ),
    Case(
        case_id="stale-index",
        question="What is the current return window?",
        gold_ids=("returns#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#01", "shipping#00"),
        prompted_ids=("returns#01", "shipping#00"),
        answer="Sale items cannot be returned. [1]",
        answer_correct=False,
        cited_ids=("returns#01",),
        index_age_days=45,
        expected="retrieval_miss",
    ),
    Case(
        case_id="conflicting-chunks",
        question="What is the return window?",
        gold_ids=("policy#new",),
        corpus_ids=_CORPUS,
        retrieved_ids=("policy#old", "policy#new"),
        prompted_ids=("policy#old", "policy#new"),
        answer="The return window is 30 days. [1]",
        answer_correct=False,
        cited_ids=("policy#old",),
        expected="generation_miss",
    ),
    Case(
        case_id="citation-mismatch",
        question="How long is the warranty?",
        gold_ids=("warranty#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("warranty#00", "returns#00"),
        prompted_ids=("warranty#00", "returns#00"),
        answer="Warranties cover defects for 12 months. [7]",
        answer_correct=False,
        cited_ids=("ghost#00",),
        expected="generation_miss",
    ),
    Case(
        case_id="over-abstention",
        question="How long is the warranty?",
        gold_ids=("warranty#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("warranty#00", "returns#00"),
        prompted_ids=("warranty#00", "returns#00"),
        answer="I don't know based on the available context.",
        answer_correct=False,
        expected="generation_miss",
    ),
    Case(
        case_id="answered-unanswerable",
        question="Do you price match competitors?",
        gold_ids=("refunds#00",),
        corpus_ids=_CORPUS,
        retrieved_ids=("returns#00", "faq#00"),
        prompted_ids=("returns#00", "faq#00"),
        answer="Yes, we price match within 5 days. [1]",
        answer_correct=False,
        cited_ids=("returns#00",),
        expected="unanswerable",
    ),
]


if __name__ == "__main__":
    print("topic 28 - where RAG fails (offline diagnostic suite)")

    report = run_suite(SAMPLE_CASES, chunks=SAMPLE_CHUNKS)
    print()
    print(report.summary())
    print()
    for diagnosis in report.diagnoses:
        print(" ", diagnosis.as_row())

    print("\nconflicting chunks")
    claims = extract_claims(
        {chunk_id: SAMPLE_CHUNKS[chunk_id] for chunk_id in ("policy#old", "policy#new")}
    )
    for conflict in find_conflicts(claims):
        print(f"  {conflict.subject}: {conflict.statements}")

    print("\nfailure boundaries")
    for stage in BOUNDARY_STAGES:
        boundary = failure_boundary(stage)
        print(f"  {stage:<9} breaks: {boundary.breaks[:72]}...")

    print("\nsymptom guide")
    for symptom in (
        "new documents",
        "two answers contradict each other",
        "the answer is plausible but cites nothing",
    ):
        print(f"  {symptom!r} -> {guide(symptom)[:96]}...")

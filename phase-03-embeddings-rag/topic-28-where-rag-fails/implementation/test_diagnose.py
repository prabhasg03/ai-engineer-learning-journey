"""Tests for Topic 28: diagnosing RAG failures by stage.

Run:  python -m pytest -v
"""

from dataclasses import replace

import pytest

from diagnose import (
    BOUNDARIES,
    BOUNDARY_STAGES,
    CAUSE_FIXES,
    LABELS,
    SAMPLE_CASES,
    SAMPLE_CHUNKS,
    STAGES,
    SYMPTOM_GUIDE,
    Case,
    Claim,
    Diagnosis,
    diagnose,
    extract_claims,
    failure_boundary,
    find_conflicts,
    guide,
    is_abstention,
    locate_stage,
    run_suite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def case(case_id: str) -> Case:
    return next(item for item in SAMPLE_CASES if item.case_id == case_id)


def minimal_case(**overrides) -> Case:
    defaults = dict(
        case_id="c",
        question="q",
        gold_ids=("g",),
        corpus_ids=("g", "x"),
        retrieved_ids=("g", "x"),
        prompted_ids=("g", "x"),
        answer="a",
        answer_correct=True,
    )
    defaults.update(overrides)
    return Case(**defaults)


# ---------------------------------------------------------------------------
# Abstention recognition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I don't know.",
        "I do not know based on the context.",
        "Cannot answer that from the provided documents.",
        "There is not enough information.",
        "Unable to answer.",
    ],
)
def test_abstention_phrasings_are_recognised(text):
    assert is_abstention(text) is True


def test_real_answer_is_not_abstention():
    assert is_abstention("Returns are accepted within 30 days. [1]") is False


# ---------------------------------------------------------------------------
# Case validation
# ---------------------------------------------------------------------------


def test_case_rejects_unknown_expected_label():
    with pytest.raises(ValueError):
        minimal_case(expected="vibes")


def test_case_rejects_negative_index_age():
    with pytest.raises(ValueError):
        minimal_case(index_age_days=-1)


def test_case_allows_empty_expected_label():
    assert minimal_case().expected == ""


# ---------------------------------------------------------------------------
# The decision procedure: full truth table
# ---------------------------------------------------------------------------

TRUTH_TABLE = []
for _in_corpus in (False, True):
    for _retrieved in (False, True):
        for _prompted in (False, True):
            for _correct in (False, True):
                if not _in_corpus:
                    _expected = "unanswerable"
                elif not _retrieved:
                    _expected = "retrieval_miss"
                elif not _prompted:
                    _expected = "ranking_miss"
                elif not _correct:
                    _expected = "generation_miss"
                else:
                    _expected = "ok"
                TRUTH_TABLE.append((_in_corpus, _retrieved, _prompted, _correct, _expected))


@pytest.mark.parametrize("in_corpus,retrieved,prompted,correct,expected", TRUTH_TABLE)
def test_locate_stage_truth_table(in_corpus, retrieved, prompted, correct, expected):
    assert locate_stage(in_corpus, retrieved, prompted, correct) == expected


def test_unanswerable_beats_a_retrieval_failure():
    assert locate_stage(False, False, False, False) == "unanswerable"


def test_retrieval_miss_is_checked_before_ranking():
    # Inconsistent input on purpose: the gold was never retrieved, so a
    # "prompted" claim cannot rescue it.
    assert locate_stage(True, False, True, False) == "retrieval_miss"


# ---------------------------------------------------------------------------
# Diagnosing the labelled fixture
# ---------------------------------------------------------------------------


def test_ok_case_has_no_causes_or_fixes():
    diagnosis = diagnose(case("ok"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "ok"
    assert diagnosis.causes == ()
    assert diagnosis.fixes == ()


def test_retrieval_miss_when_gold_is_in_corpus_but_not_retrieved():
    diagnosis = diagnose(case("retrieval-miss"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "retrieval_miss"
    assert "never came back from retrieval" in diagnosis.symptom


def test_ranking_miss_when_gold_is_retrieved_but_pruned():
    diagnosis = diagnose(case("ranking-miss"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "ranking_miss"
    assert "prompt_pruned" in diagnosis.causes


def test_generation_miss_when_gold_was_in_the_prompt():
    diagnosis = diagnose(case("generation-miss"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "generation_miss"
    assert diagnosis.causes == ()


def test_unanswerable_case_is_not_blamed_on_retrieval():
    diagnosis = diagnose(case("unanswerable"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "unanswerable"
    assert "answered_unanswerable" not in diagnosis.causes


def test_answer_to_an_unanswerable_question_is_flagged():
    diagnosis = diagnose(case("answered-unanswerable"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "unanswerable"
    assert "answered_unanswerable" in diagnosis.causes
    assert any("coverage" in fix for fix in diagnosis.fixes)


def test_stale_index_is_a_cause_not_a_symptom():
    diagnosis = diagnose(case("stale-index"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "retrieval_miss"
    assert "stale_index" in diagnosis.causes
    assert any("reindex" in fix for fix in diagnosis.fixes)


def test_fresh_index_has_no_stale_cause():
    diagnosis = diagnose(case("retrieval-miss"), chunks=SAMPLE_CHUNKS)
    assert "stale_index" not in diagnosis.causes


def test_document_changed_since_ingest_is_stale():
    fresh = minimal_case(gold_ids=("missing",), index_age_days=0)
    stale = replace(fresh, doc_changed_since_ingest=True)
    assert "stale_index" not in diagnose(fresh).causes
    assert "stale_index" in diagnose(stale).causes


def test_conflicting_chunks_are_flagged_when_prompted():
    diagnosis = diagnose(case("conflicting-chunks"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "generation_miss"
    assert "conflict" in diagnosis.causes
    assert any("conflicting sources" in fix for fix in diagnosis.fixes)


def test_citation_mismatch_is_flagged():
    diagnosis = diagnose(case("citation-mismatch"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "generation_miss"
    assert "citation_mismatch" in diagnosis.causes


def test_over_abstention_is_flagged_when_evidence_was_present():
    diagnosis = diagnose(case("over-abstention"), chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == "generation_miss"
    assert "over_abstention" in diagnosis.causes


def test_diagnosis_notes_include_the_intermediate_sets():
    diagnosis = diagnose(case("ranking-miss"), chunks=SAMPLE_CHUNKS)
    assert "in_corpus=True" in diagnosis.notes
    assert "retrieved=True" in diagnosis.notes
    assert "prompted=False" in diagnosis.notes


def test_every_fixture_label_is_in_the_vocabulary():
    for item in SAMPLE_CASES:
        assert diagnose(item, chunks=SAMPLE_CHUNKS).label in LABELS


def test_diagnose_does_not_mutate_the_case():
    original = case("ok")
    diagnose(original, chunks=SAMPLE_CHUNKS)
    assert original == case("ok")


@pytest.mark.parametrize(
    "label",
    ["retrieval_miss", "ranking_miss", "generation_miss", "unanswerable"],
)
def test_failure_labels_come_with_fixes(label):
    fixture = next(item for item in SAMPLE_CASES if item.expected == label)
    diagnosis = diagnose(fixture, chunks=SAMPLE_CHUNKS)
    assert diagnosis.label == label
    assert diagnosis.fixes


def test_ok_has_no_fix_list():
    assert diagnose(case("ok")).fixes == ()


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_extract_claims_finds_subject_value_unit():
    claims = extract_claims({"a": "The return window is 30 days for all customers."})
    assert claims == [Claim("a", "return window", 30, "day")]


def test_extract_claims_handles_multiple_chunks_in_order():
    claims = extract_claims(
        {
            "b": "The warranty period is 12 months.",
            "a": "The return window is 30 days. The shipping cutoff is 2 hours.",
        }
    )
    assert [claim.chunk_id for claim in claims] == ["a", "a", "b"]
    assert [claim.subject for claim in claims] == ["return window", "shipping cutoff", "warranty period"]


def test_extract_claims_ignores_non_matching_text():
    assert extract_claims({"a": "Refunds are issued within 5 business days."}) == []


def test_conflicting_values_produce_a_conflict():
    claims = extract_claims(
        {
            "old": "The return window is 30 days.",
            "new": "The return window is 14 days.",
        }
    )
    conflicts = find_conflicts(claims)
    assert len(conflicts) == 1
    assert conflicts[0].subject == "return window"
    assert conflicts[0].statements == (("new", "14 days"), ("old", "30 days"))


def test_same_value_in_two_chunks_is_not_a_conflict():
    claims = extract_claims(
        {
            "a": "The return window is 30 days.",
            "b": "The return window is 30 days.",
        }
    )
    assert find_conflicts(claims) == []


def test_singular_and_plural_units_do_not_conflict():
    claims = extract_claims(
        {
            "a": "The return window is 1 day.",
            "b": "The return window is 1 days.",  # sloppy source, same fact
        }
    )
    assert find_conflicts(claims) == []


def test_conflicts_are_sorted_by_subject():
    claims = extract_claims(
        {
            "a": "The warranty period is 12 months. The return window is 30 days.",
            "b": "The warranty period is 24 months. The return window is 14 days.",
        }
    )
    conflicts = find_conflicts(claims)
    assert [conflict.subject for conflict in conflicts] == ["return window", "warranty period"]


def test_single_claim_has_no_conflict():
    claims = [Claim("a", "return window", 30, "day")]
    assert find_conflicts(claims) == []


# ---------------------------------------------------------------------------
# Failure boundaries: what breaks / notice / change
# ---------------------------------------------------------------------------


def test_boundaries_cover_every_pipeline_stage():
    assert set(BOUNDARIES) == set(STAGES)
    assert set(BOUNDARY_STAGES) == set(STAGES)


def test_every_boundary_has_all_three_answers():
    for stage, boundary in BOUNDARIES.items():
        assert boundary.stage == stage
        assert len(boundary.breaks) > 20
        assert len(boundary.notice) > 20
        assert len(boundary.change) > 20


def test_failure_boundary_lookup_returns_the_entry():
    boundary = failure_boundary("assemble")
    assert "budget" in boundary.breaks.lower() or "buried" in boundary.breaks.lower()


def test_failure_boundary_rejects_unknown_stage():
    with pytest.raises(ValueError):
        failure_boundary("deploy")


# ---------------------------------------------------------------------------
# Symptom guide
# ---------------------------------------------------------------------------


def test_guide_matches_an_exact_symptom():
    answer = guide("two answers contradict each other")
    assert answer.startswith("conflict")


def test_guide_matches_a_distinctive_substring():
    answer = guide("new documents")
    assert "stale_index" in answer


def test_guide_rejects_an_unknown_symptom():
    with pytest.raises(ValueError):
        guide("the model is haunted")


def test_every_symptom_entry_names_a_label_or_stage():
    for symptom, text in SYMPTOM_GUIDE.items():
        assert len(text) > 30
        assert any(label in text for label in LABELS) or "stale_index" in text


def test_cause_fixes_are_documented_for_every_cause_we_emit():
    emitted = {
        "stale_index",
        "conflict",
        "citation_mismatch",
        "over_abstention",
        "prompt_pruned",
        "answered_unanswerable",
    }
    assert emitted <= set(CAUSE_FIXES)


# ---------------------------------------------------------------------------
# Suite scoring
# ---------------------------------------------------------------------------


def test_suite_scores_the_labelled_fixture_perfectly():
    report = run_suite(SAMPLE_CASES, chunks=SAMPLE_CHUNKS)
    assert report.total == len(SAMPLE_CASES)
    assert report.scored == len(SAMPLE_CASES)
    assert report.accuracy == 1.0
    assert report.mismatches == []


def test_suite_counts_diagnoses_by_label():
    report = run_suite(SAMPLE_CASES, chunks=SAMPLE_CHUNKS)
    assert report.by_label["ok"] == 1
    assert report.by_label["retrieval_miss"] == 2
    assert report.by_label["ranking_miss"] == 1
    assert report.by_label["generation_miss"] == 4
    assert report.by_label["unanswerable"] == 2
    assert sum(report.by_label.values()) == len(SAMPLE_CASES)


def test_suite_reports_a_mislabeled_case():
    broken = replace(case("retrieval-miss"), expected="generation_miss")
    report = run_suite([broken], chunks=SAMPLE_CHUNKS)
    assert report.mismatches == ["retrieval-miss"]
    assert report.accuracy == 0.0
    assert report.correct == 0


def test_suite_handles_an_empty_list():
    report = run_suite([])
    assert report.total == 0
    assert report.accuracy == 0.0
    assert report.diagnoses == []


def test_suite_ignores_unscored_cases():
    unscored = replace(case("ok"), expected="")
    report = run_suite([unscored], chunks=SAMPLE_CHUNKS)
    assert report.scored == 0
    assert report.accuracy == 0.0
    assert report.mismatches == []


def test_suite_summary_contains_accuracy_and_labels():
    summary = run_suite(SAMPLE_CASES, chunks=SAMPLE_CHUNKS).summary()
    assert "accuracy=1.00" in summary
    assert "retrieval_miss=2" in summary


def test_diagnosis_as_row_is_compact_and_complete():
    diagnosis = diagnose(case("stale-index"), chunks=SAMPLE_CHUNKS)
    row = diagnosis.as_row()
    assert "stale-index" in row
    assert "retrieval_miss" in row
    assert "stale_index" in row


def test_diagnosis_is_hashable_and_frozen():
    diagnosis: Diagnosis = diagnose(case("ok"))
    with pytest.raises(Exception):
        diagnosis.label = "generation_miss"  # type: ignore[misc]

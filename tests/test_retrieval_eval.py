"""SYNTHETIC scorer checks; the actual corpus evaluation uses dated excerpts."""
import pytest
from infodesk.evaluate_retrieval import evaluate, score_passages
from infodesk.sources import ROOT


def test_SYNTHETIC_scorer_requires_quote_and_source():
    expected = [{'source': 'SYNTHETIC-source', 'quote': 'SYNTHETIC expected evidence'}]
    wrong = [{'source_id': 'SYNTHETIC-other', 'body': 'SYNTHETIC expected evidence'}]
    assert score_passages(wrong, expected)['evidence_recall'] == 0
    hits = wrong + [{'source_id': 'SYNTHETIC-source', 'body': 'SYNTHETIC expected evidence'}]
    score = score_passages(hits, expected)
    # SOURCE: the relevant quote is at rank two in this fixture.
    assert score['reciprocal_rank'] == .5
    assert score['evidence_recall'] == 1 and not score['top1_relevant']


def test_SYNTHETIC_negative_is_not_scored_as_model_abstention():
    score = score_passages([], [])
    assert score['evidence_recall'] is None and score['top1_relevant'] is None


def test_recorded_evaluation_annotations_are_valid_and_failures_stay_visible():
    report = evaluate(ROOT / 'evals/retrieval-cases.json', repeats=1)
    assert report['summary']['cases'] == len(report['cases'])
    assert all(case['retrieval_ms_samples'] for case in report['cases'])
    assert report['summary']['answerable'] and report['summary']['unanswerable']
    # This validates the evaluator, not a minimum accuracy target tuned to the development set.
    assert all(0 <= case['evidence_recall'] <= 1 for case in report['cases'] if case['expected'])


def test_SYNTHETIC_invalid_repeat_budget_is_rejected():
    with pytest.raises(ValueError):
        evaluate(ROOT / 'evals/retrieval-cases.json', repeats=0)

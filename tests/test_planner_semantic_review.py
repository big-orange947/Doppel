from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from benchmarks.planner_semantic_review import (
    PlannerSemanticReview,
    TemporalAlternative,
    review_planner_report,
)
from benchmarks.relation_planner_quality import DEFAULT_DATASET
from doppel_memory import PersonalMemoryQueryDraft

REVIEW_PATH = DEFAULT_DATASET.parent / "relation-planner-semantic-review-zh-v1.json"


def test_bundled_review_is_complete_but_explicitly_posthoc() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    review = PlannerSemanticReview.model_validate_json(REVIEW_PATH.read_bytes())
    review.validate_dataset(dataset)
    assert review.status == "posthoc_diagnostic"
    assert review.publication_ready is False
    assert {item for group in review.relation_groups for item in group.query_ids} == {
        item.query_id for item in dataset.queries
    }


def test_diagnostic_never_changes_scores_drafts_or_rewards_ambiguous_hard_filters() -> (
    None
):
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    cases = []
    for query_id, relation_types in [
        ("rel-q01", ["HELD_BY"]),
        ("rel-q12", []),
        ("rel-q54", ["LOCATED_AT"]),
        ("rel-q57", []),
        ("rel-q21", ["HELD_BY"]),
        ("rel-q25", None),
    ]:
        cases.append(
            {
                "query_id": query_id,
                "partition": "dev",
                "error": "ValidationError" if relation_types is None else "",
                "actual": None
                if relation_types is None
                else PersonalMemoryQueryDraft(relation_types=relation_types).model_dump(
                    mode="json"
                ),
            }
        )
    report = {
        "dataset": {"fingerprint": dataset.fingerprint},
        "metrics": {"score": 0.4},
        "cases": cases,
    }
    original = copy.deepcopy(report)
    result = review_planner_report(report, dataset, REVIEW_PATH)
    assert report == original
    assert result["legacy_scores_unchanged"] is True
    assert result["relation_assessment_counts"] == {
        "correct_explicit_type": 1,
        "missed_explicit_type": 1,
        "ambiguous_hard_filter": 1,
        "conservative_abstention": 1,
        "wrong_explicit_type": 1,
        "unavailable": 1,
    }


def test_open_interval_matches_only_an_explicit_open_interval_contract() -> None:
    start = datetime(2026, 8, 10, tzinfo=UTC)
    contract = TemporalAlternative.model_validate(
        {
            "time_from": {"minimum": start, "maximum": start},
        }
    )
    assert contract.accepts(PersonalMemoryQueryDraft(time_from=start))
    assert not contract.accepts(PersonalMemoryQueryDraft())
    assert not contract.accepts(PersonalMemoryQueryDraft(as_of=start))
    assert not contract.accepts(
        PersonalMemoryQueryDraft(
            time_from=start, time_to=datetime(2026, 8, 30, tzinfo=UTC)
        )
    )
    assert not contract.accepts(
        PersonalMemoryQueryDraft(time_from=datetime(2020, 1, 1, tzinfo=UTC))
    )
    point_contract = TemporalAlternative.model_validate(
        {
            "as_of": {"minimum": start, "maximum": start},
        }
    )
    assert not point_contract.accepts(PersonalMemoryQueryDraft(time_from=start))


def test_open_time_review_does_not_relabel_retrieval_gold() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    query = next(item for item in dataset.queries if item.query_id == "rel-q46")
    original = query.model_dump(mode="json")
    report = {
        "dataset": {"fingerprint": dataset.fingerprint},
        "cases": [
            {
                "query_id": query.query_id,
                "partition": query.partition,
                "error": "",
                "actual": PersonalMemoryQueryDraft(
                    intent="history", time_from=datetime(2026, 8, 10, tzinfo=UTC)
                ).model_dump(mode="json"),
            }
        ],
    }
    result = review_planner_report(report, dataset, REVIEW_PATH)
    assert result["cases"][0]["temporal_assessment"] == "matches_reviewed_shape"
    assert result["cases"][0]["retrieval_gold_needs_review"] is True
    assert query.model_dump(mode="json") == original


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unknown_query", "unknown_type", "wrong_dataset"]
)
def test_review_rejects_bad_annotation_references(mutation: str) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    raw = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        raw["relation_groups"][0]["query_ids"].append("rel-q01")
    elif mutation == "unknown_query":
        raw["relation_groups"][0]["query_ids"].append("unknown")
    elif mutation == "unknown_type":
        raw["relation_groups"][0]["expected_types"] = ["INVENTED"]
    else:
        raw["dataset_fingerprint"] = "0" * 64
    with pytest.raises(ValueError):
        PlannerSemanticReview.model_validate(raw).validate_dataset(dataset)

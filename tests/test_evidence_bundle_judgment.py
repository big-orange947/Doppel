from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.evidence_bundle_judgment import (
    EVIDENCE_RICH_PROFILE,
    RANK_FIRST_PROFILE,
    EvidenceJudgment,
    EvidenceJudgmentSelection,
    _load_profile_rows,
    _selection_cases,
    build_judgment_request,
    compare_default_profiles,
    load_selection,
    score_judgment,
    summarize,
)
from benchmarks.heterogeneous_retrieval_quality import load_dataset

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v4.json"
SELECTION = ROOT / "benchmarks/datasets/evidence-bundle-diagnostic-selection-v1.json"


def _fixture():
    dataset = load_dataset(DATASET)
    case = next(item for item in dataset.queries if item.required_memory_ids)
    memories = {memory.memory_id: memory for memory in dataset.memories}
    required = list(case.required_memory_ids)
    distractor = next(
        memory.memory_id
        for memory in dataset.memories
        if memory.scope == case.scope and memory.memory_id not in required
    )
    return dataset, case, memories, required + [distractor]


def test_request_exposes_opaque_items_but_not_store_or_gold_fields() -> None:
    _, case, memories, ranked = _fixture()

    request, mapping = build_judgment_request(case, ranked, memories, context_limit=10)
    encoded = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)

    assert list(mapping) == [f"item_{index:02d}" for index in range(1, len(ranked) + 1)]
    assert not set(mapping.values()).intersection(set(mapping))
    assert all(memory_id not in encoded for memory_id in ranked)
    assert "required_memory_ids" not in encoded
    assert "related_memory_ids" not in encoded
    assert "scope" not in request.input
    assert "retrieval" not in request.input
    assert request.input["question"] == case.query


def test_judgment_requires_support_when_answerable_and_none_when_abstaining() -> None:
    with pytest.raises(ValidationError):
        EvidenceJudgment(answerable=True, supporting_item_ids=[])
    with pytest.raises(ValidationError):
        EvidenceJudgment(answerable=False, supporting_item_ids=["item_01"])


def test_score_separates_retrieval_sufficiency_from_model_judgment() -> None:
    _, case, memories, ranked = _fixture()
    _, mapping = build_judgment_request(case, ranked, memories, context_limit=10)
    reverse = {memory_id: item_id for item_id, memory_id in mapping.items()}
    judgment = EvidenceJudgment(
        answerable=True,
        supporting_item_ids=[reverse[item] for item in case.required_memory_ids],
    )

    row = score_judgment(case, ranked, judgment, mapping, context_limit=10)

    assert row["retrieval_sufficient"] is True
    assert row["decision_correct"] is True
    assert row["support_exact"] is True
    assert row["support_recall"] == 1.0
    assert row["support_precision"] == 1.0
    assert row["end_to_end_success"] is True


def test_score_rejects_provider_ids_outside_the_bundle() -> None:
    _, case, memories, ranked = _fixture()
    _, mapping = build_judgment_request(case, ranked, memories, context_limit=10)

    with pytest.raises(ValueError, match="outside"):
        score_judgment(
            case,
            ranked,
            EvidenceJudgment(answerable=True, supporting_item_ids=["item_99"]),
            mapping,
            context_limit=10,
        )


def test_summary_reports_retrieval_judgment_and_end_to_end_separately() -> None:
    rows = [
        {
            "source_answerable": True,
            "retrieval_sufficient": True,
            "decision_correct": True,
            "support_exact": True,
            "support_recall": 1.0,
            "support_precision": 1.0,
            "end_to_end_success": True,
            "related_selected": 0,
            "hard_forbidden_selected": 0,
            "judged_answerable": True,
        },
        {
            "source_answerable": True,
            "retrieval_sufficient": False,
            "decision_correct": True,
            "support_exact": False,
            "support_recall": 0.0,
            "support_precision": 1.0,
            "end_to_end_success": False,
            "related_selected": 0,
            "hard_forbidden_selected": 0,
            "judged_answerable": False,
        },
        {
            "source_answerable": False,
            "retrieval_sufficient": False,
            "decision_correct": True,
            "support_exact": False,
            "support_recall": 1.0,
            "support_precision": 1.0,
            "end_to_end_success": False,
            "related_selected": 0,
            "hard_forbidden_selected": 0,
            "judged_answerable": False,
        },
    ]

    result = summarize(rows)

    assert result["retrieval_sufficiency_rate"] == 0.5
    assert result["judgment_accuracy"] == 1.0
    assert result["insufficient_bundle_abstention_rate"] == 1.0
    assert result["source_no_answer_abstention_rate"] == 1.0
    assert result["end_to_end_support_success_rate"] == 0.5


def test_default_comparison_prefers_end_to_end_gain_with_bounded_judgment_cost() -> (
    None
):
    rank_first = {
        "retrieval_sufficiency_rate": 0.8,
        "judgment_accuracy": 0.96,
        "source_no_answer_abstention_rate": 0.95,
        "exact_support_selection_rate": 0.9,
        "end_to_end_support_success_rate": 0.75,
    }
    evidence_rich = {
        "retrieval_sufficiency_rate": 0.9,
        "judgment_accuracy": 0.95,
        "source_no_answer_abstention_rate": 0.95,
        "exact_support_selection_rate": 0.91,
        "end_to_end_support_success_rate": 0.84,
    }

    comparison = compare_default_profiles(
        {
            RANK_FIRST_PROFILE: rank_first,
            EVIDENCE_RICH_PROFILE: evidence_rich,
        }
    )

    assert comparison is not None
    assert comparison["failures"] == []
    assert comparison["policy_preference_supported"] is True
    assert (
        comparison["deltas_evidence_rich_minus_rank_first"][
            "end_to_end_support_success_rate"
        ]
        == 0.09
    )


def test_profile_loader_binds_report_to_dataset_and_rejects_duplicates(
    tmp_path: Path,
) -> None:
    dataset, case, _, ranked = _fixture()
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "dataset": {"fingerprint": dataset.fingerprint},
                "profiles": {
                    "p": {"details": [{"case_id": case.case_id, "ids": ranked}]}
                },
            }
        ),
        "utf-8",
    )

    rows, _ = _load_profile_rows(path, dataset, ["p"])
    assert rows["p"][case.case_id] == ranked

    payload = json.loads(path.read_text("utf-8"))
    payload["profiles"]["p"]["details"][0]["ids"] = [ranked[0], ranked[0]]
    path.write_text(json.dumps(payload), "utf-8")
    with pytest.raises(ValueError, match="repeats"):
        _load_profile_rows(path, dataset, ["p"])


def test_diagnostic_selection_is_bound_unique_and_owner_diverse() -> None:
    dataset = load_dataset(DATASET)
    selection = EvidenceJudgmentSelection.model_validate_json(SELECTION.read_bytes())
    report = {
        "report_sha256": selection.source_retrieval_report_sha256,
    }

    loaded = load_selection(SELECTION, dataset, report)
    cases = _selection_cases(dataset, loaded)

    assert len(cases) == 16
    assert [len(group.case_ids) for group in loaded.groups] == [5, 3, 8]
    assert {case.partition for case in cases} == {"dev", "sealed"}
    assert {case.category for case in cases} == {
        "one_hop_relation",
        "two_hop_relation",
        "no_answer_related",
    }
    assert len({case.scope for case in cases}) == 8
    assert loaded.publication_ready is False
    assert loaded.status == "opened_posthoc_diagnostic"


def test_diagnostic_selection_rejects_report_fingerprint_mismatch() -> None:
    dataset = load_dataset(DATASET)

    with pytest.raises(ValueError, match="report fingerprint"):
        load_selection(SELECTION, dataset, {"report_sha256": "0" * 64})

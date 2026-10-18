from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_prospective_selection as runner
from benchmarks.public_memory_pilot import _hash, build_manifest
from tests.test_public_memory_fresh_cohort import SHA, dataset


def bound():
    raw = []
    for n in range(60):
        row = deepcopy(dataset()[0])
        row.update(
            question_id=f"fresh-{n}",
            answer_session_ids=[f"s-{n}"],
            haystack_session_ids=[f"s-{n}"],
        )
        row["haystack_sessions"][0][0]["content"] = f"Original source {n}"
        raw.append(row)
    parent = build_manifest(
        raw,
        dataset_namespace="synthetic",
        run_namespace="parent",
        source_sha256=SHA,
        diagnostic_count=50,
        reserved_count=2,
    )
    return raw, parent


def test_fixed_next_five_no_opened_reserved_groups_or_labels_in_manifest():
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, SHA)
    diagnostic = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    assert [r["case_id"] for r in manifest["cases"]] == [
        r["case_id"] for r in diagnostic[40:45]
    ]
    assert [r["ordinal"] for r in manifest["cases"]] == list(range(41, 46))
    assert len(cases) == 5
    assert "PRIVATE GOLD" not in str(manifest) and "PRIVATE QUESTION" not in str(
        manifest
    )
    assert "has_answer" not in str(manifest)


@pytest.mark.parametrize(
    "mutation", ["source", "payload", "count", "opened", "reserved", "fingerprint"]
)
def test_changed_or_overlapping_inputs_rejected(mutation):
    raw, parent = bound()
    diagnostic = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    sha = SHA
    if mutation == "source":
        sha = "b" * 64
    elif mutation == "payload":
        diagnostic[40]["history_payload_sha256"] = "changed"
    elif mutation == "count":
        diagnostic[40]["raw_turn_count"] += 1
    elif mutation == "opened":
        diagnostic[40].update(diagnostic[0])
    elif mutation == "reserved":
        diagnostic[40]["history_group"] = next(
            r["history_group"]
            for r in parent["cases"]
            if r["partition"] != "diagnostic"
        )
    else:
        parent["cases"].reverse()
    if mutation != "fingerprint":
        parent["manifest_fingerprint"] = _hash(
            {k: v for k, v in parent.items() if k != "manifest_fingerprint"}
        )
    with pytest.raises(ValueError):
        runner.prepare(raw, parent, sha)


def test_protocol_and_paid_budget_frozen_before_preparation():
    raw, parent = bound()
    _, manifest = runner.prepare(raw, parent, SHA)
    plan = runner.make_plan("prepare", manifest, {"model": "synthetic"})
    assert sum(s["max_calls"] for s in plan["stages"].values()) == 30
    assert plan["candidate_window"] == 80 and plan["source_limit"] == 20
    assert plan["context_byte_limit"] == 24000 and plan["graph_calls"] == 0
    assert plan["profiles"] == ["bge_content_only", "llm_metadata_up_to20"]
    assert not plan["publication_ready"]
    preparation = {"status": "complete", "plan": plan, "receipts": []}
    with pytest.raises(ValueError, match="five bounded"):
        runner.make_plan("evaluate", manifest, {"model": "synthetic"}, preparation)
    preparation["plan"]["source_sha256"] = {}
    with pytest.raises(ValueError, match="runtime code"):
        runner.make_plan("evaluate", manifest, {"model": "synthetic"}, preparation)


def item(start, end, size=100):
    return {
        "source_memory_id": "m",
        "source_span": {"start": start, "end": end, "source_char_count": size},
    }


@pytest.mark.parametrize(
    "spans,full",
    [
        ([(0, 10)], 0),
        ([(10, 100)], 0),
        ([(0, 50), (60, 100)], 0),
        ([(0, 60), (50, 100)], 1),
        ([(0, 100)], 1),
    ],
)
def test_fragment_source_presence_is_never_answer_support(spans, full):
    scoring = SimpleNamespace(evidence_turns=[(0, 0)], abstention=False)
    result = runner.fragment_annotations(
        scoring, [item(a, b) for a, b in spans], {(0, 0): {"memory_id": "m"}}
    )
    assert result["annotated_source_turns_present"] == 1
    assert result["full_annotated_turn_texts_retained"] == full
    assert result["fragment_answer_support_recall"] is None


def test_negative_label_not_counted_as_answerable_coverage():
    scoring = SimpleNamespace(evidence_turns=[(0, 0)], abstention=True)
    result = runner.fragment_annotations(
        scoring, [item(0, 100)], {(0, 0): {"memory_id": "m"}}
    )
    assert result["eligible_answerable"] is False

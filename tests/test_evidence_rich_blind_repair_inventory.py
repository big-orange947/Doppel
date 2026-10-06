"""Offline repair scope must preserve rejected review and unopened gold."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from benchmarks import evidence_rich_blind_repair_inventory as inventory
from benchmarks.evidence_rich_blind_authoring import split_owner_authoring_batches


def make_inputs() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    manifest = inventory.source.build_manifest()
    authored = {
        "status": "authored_unreviewed",
        "manifest_fingerprint": manifest.fingerprint,
        "review_complete": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "owners": [],
    }
    batches = []
    for owner in manifest.owners:
        authored["owners"].append(
            {
                "owner_key": owner.owner_key,
                "entity_names_by_id": {
                    e.entity_id: e.required_display_name
                    or f"{owner.owner_key}-{e.surface_key}"
                    for e in owner.entities
                },
                "memory_content_by_id": {
                    m.memory_id: m.memory_id for m in owner.memories
                },
                "edge_fact_by_memory_id": {
                    m.memory_id: m.memory_id if m.relation_type else ""
                    for m in owner.memories
                },
                "query_text_by_case_id": {q.case_id: q.case_id for q in owner.queries},
            }
        )
        for batch in split_owner_authoring_batches(owner):
            keys = sorted(
                s.surface_key
                for s in [*batch.entities, *batch.memories, *batch.queries]
            )
            issues = [
                {"surface_key": key, "issue_code": code, "detail": "original finding"}
                for (short, key, code) in inventory.DIAGNOSES
                if short == owner.owner_key[-2:] and key in keys
            ]
            batches.append(
                {
                    "batch_id": batch.batch_id,
                    "owner_key": owner.owner_key,
                    "reviewed_surface_count": len(keys),
                    "reviewed_surface_keys_sha256": inventory.compiler._fingerprint(
                        keys
                    ),
                    "issue_count": len(issues),
                    "issues": issues,
                }
            )
    review = {
        "status": "reviewed_rejected",
        "accepted": False,
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": "authored-test-sha",
        "review_complete": True,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "auto_rewrite_performed": False,
        "issue_count": 23,
        "batch_count": len(batches),
        "batches": batches,
    }
    return manifest, authored, review


@pytest.fixture(scope="module")
def inputs() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    return make_inputs()


def build(inputs: tuple[Any, dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    return inventory.build_inventory(
        *inputs, authored_sha256="authored-test-sha", review_sha256="review-test-sha"
    )


def test_inventory_preserves_inputs_and_does_not_approve(inputs: Any) -> None:
    before = deepcopy(inputs)
    result = build(inputs)
    assert inputs == before
    assert result["summary"]["reported_findings"] == 23
    assert result["summary"]["diagnoses"] == {
        "ambiguity": 6,
        "coherence_defect": 5,
        "suspected_false_positive": 12,
    }
    assert not any(result["gate"].values())
    assert result["usage"] == {"provider_calls": 0, "tokens": 0}
    assert all(f["decision"] == "pending_adjudication" for f in result["findings"])
    with pytest.raises(ValueError, match="accepted first semantic review"):
        inventory.compiler._validate_review(inputs[0], inputs[2], "authored-test-sha")


def test_all_temporal_owners_and_unflagged_relation_families_covered(
    inputs: Any,
) -> None:
    owners = {
        o["owner_key"]: {s["surface_key"] for s in o["slots"]}
        for o in build(inputs)["owners"]
    }
    for slots in owners.values():
        assert {"memory-temporary-residence", "query-temporary-as-of"} <= slots
    for number in (2, 10, 18):
        assert "entity-one-hop-anchor" in owners[f"owner-blind-{number:02d}"]
        assert "memory-stale-route" in owners[f"owner-blind-{number:02d}"]
    for number in (8, 16, 24):
        assert {
            "memory-one-hop",
            "memory-competing-first",
            "memory-two-hop-first",
            "memory-stale-route",
        } <= owners[f"owner-blind-{number:02d}"]
    assert all("query-no-answer" not in slots for slots in owners.values())


def test_entity_rename_closure_includes_text_only_distractor(inputs: Any) -> None:
    manifest, authored, review = deepcopy(inputs)
    owner = manifest.owners[1]
    entity = next(e for e in owner.entities if e.surface_key == "entity-branch-target")
    name = authored["owners"][1]["entity_names_by_id"][entity.entity_id]
    memory = owner.memories[-1]
    authored["owners"][1]["memory_content_by_id"][memory.memory_id] = (
        f"text-only reference: {name}"
    )
    result = build((manifest, authored, review))
    row = next(
        s
        for s in result["owners"][1]["slots"]
        if s["surface_key"] == memory.surface_key
    )
    assert row["reasons"] == ["entity_reference_consistency"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_batch",
        "coverage_hash",
        "duplicate_issue",
        "omitted_issue",
        "source_hash",
        "retrieval_opened",
        "accepted",
    ],
)
def test_incomplete_changed_or_accepted_review_is_rejected(
    inputs: Any, mutation: str
) -> None:
    manifest, authored, review = deepcopy(inputs)
    flagged = next(b for b in review["batches"] if b["issues"])
    if mutation == "missing_batch":
        review["batches"].pop()
    elif mutation == "coverage_hash":
        flagged["reviewed_surface_keys_sha256"] = "wrong"
    elif mutation == "duplicate_issue":
        flagged["issues"].append(flagged["issues"][0])
        flagged["issue_count"] += 1
    elif mutation == "omitted_issue":
        flagged["issues"].pop()
        flagged["issue_count"] -= 1
    elif mutation == "source_hash":
        review["authored_surfaces_sha256"] = "wrong"
    else:
        review[mutation] = True
    with pytest.raises(ValueError):
        build((manifest, authored, review))


def test_authority_binding_excludes_briefs_but_not_gold(inputs: Any) -> None:
    manifest = inputs[0]
    owner = manifest.owners[0]
    changed = owner.model_copy(
        update={
            "queries": [
                owner.queries[0].model_copy(update={"semantic_brief": "new prose"}),
                *owner.queries[1:],
            ]
        }
    )
    revised = manifest.model_copy(update={"owners": [changed, *manifest.owners[1:]]})
    assert inventory.authority_fingerprint(revised) == inventory.authority_fingerprint(
        manifest
    )
    changed = owner.model_copy(
        update={
            "queries": [
                owner.queries[0].model_copy(
                    update={"valid_at": "2026-03-16T00:00:00+08:00"}
                ),
                *owner.queries[1:],
            ]
        }
    )
    revised = manifest.model_copy(update={"owners": [changed, *manifest.owners[1:]]})
    assert inventory.authority_fingerprint(revised) != inventory.authority_fingerprint(
        manifest
    )

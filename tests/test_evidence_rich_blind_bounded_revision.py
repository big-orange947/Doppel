"""Corpus repairs cannot mutate gold, expand their scope, or grant acceptance."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_evidence_rich_blind_repair_inventory import make_inputs

from benchmarks import evidence_rich_blind_bounded_revision as revision
from benchmarks import evidence_rich_blind_repair_inventory as inventory


@pytest.fixture
def repair_inputs() -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest, authored, review = make_inputs()
    for owner, surfaces in zip(manifest.owners, authored["owners"], strict=True):
        names = {
            e.surface_key: surfaces["entity_names_by_id"][e.entity_id]
            for e in owner.entities
        }
        for memory in owner.memories:
            if memory.relation_type:
                text = f"{memory.memory_id}: {names[memory.source_entity_key]} -- {names[memory.target_entity_key]}"
                surfaces["memory_content_by_id"][memory.memory_id] = text
                surfaces["edge_fact_by_memory_id"][memory.memory_id] = text
            elif memory.surface_key == "memory-temporary-residence":
                surfaces["memory_content_by_id"][memory.memory_id] = (
                    "2026年2月1日开始临住，到2026年4月1日之前已经结束。"
                )
        query = next(
            q for q in owner.queries if q.surface_key == "query-temporary-as-of"
        )
        surfaces["query_text_by_case_id"][query.case_id] = "2026年3月的时候，住在哪里？"
    frozen = inventory.build_inventory(
        manifest,
        authored,
        review,
        authored_sha256="authored-test-sha",
        review_sha256="review-test-sha",
    )
    recipe = {
        "version": "test-curation",
        "description": "test-only",
        "temporal_replacements": [
            ["到2026年4月1日之前已经", "住到2026年3月31日，2026年4月1日起已经"]
        ],
        "owners": {},
    }
    return manifest, authored, frozen, recipe


def test_temporal_revision_keeps_gold_and_originals(repair_inputs: Any) -> None:
    original = deepcopy(repair_inputs)
    manifest, authored, changes = revision.revise(*repair_inputs)
    assert repair_inputs == original
    assert inventory.authority_fingerprint(manifest) == inventory.authority_fingerprint(
        original[0]
    )
    assert manifest.fingerprint != original[0].fingerprint
    assert len({(c["owner_key"], c["surface_key"]) for c in changes}) == 48
    assert {c["surface_key"] for c in changes} == {
        "memory-temporary-residence",
        "query-temporary-as-of",
    }
    assert authored["review_complete"] is False
    assert authored["retrieval_opened"] is False
    assert authored["curation"]["independent_review_passed"] is False
    assert authored["quality_metrics_available"] is False
    assert authored["acquisition"] == {"provider_calls": 0, "tokens": 0}
    assert "implementation_commit" not in authored
    assert authored["parent_authoring_provenance"]["acquisition"] == original[1].get(
        "acquisition", {}
    )


def test_rename_is_propagated_without_replacing_other_entities(
    repair_inputs: Any,
) -> None:
    source_manifest, original, frozen, recipe = repair_inputs
    recipe["owners"]["owner-blind-02"] = {
        "entity_names": {"entity-one-hop-anchor": "测试纪念证书"}
    }
    manifest, authored, changes = revision.revise(
        source_manifest, original, frozen, recipe
    )
    owner = manifest.owners[1]
    anchor = next(e for e in owner.entities if e.surface_key == "entity-one-hop-anchor")
    assert (
        authored["owners"][1]["entity_names_by_id"][anchor.entity_id] == "测试纪念证书"
    )
    for memory in owner.memories:
        if memory.source_entity_key == anchor.surface_key:
            assert (
                "测试纪念证书"
                in authored["owners"][1]["memory_content_by_id"][memory.memory_id]
            )
            assert (
                "测试纪念证书"
                in authored["owners"][1]["edge_fact_by_memory_id"][memory.memory_id]
            )
    assert not any(c["surface_key"] == "query-no-answer" for c in changes)


def test_name_replacement_is_single_pass_longest_first() -> None:
    assert revision._replace_names("ABC AB", {"AB": "ABC", "ABC": "new"}) == "new ABC"


@pytest.mark.parametrize(
    "mutation", ["gold", "unlisted_text", "unlisted_edge", "inventory_binding"]
)
def test_validation_rejects_expanded_scope_or_changed_authority(
    repair_inputs: Any, mutation: str
) -> None:
    before_manifest, before, frozen, _recipe = repair_inputs
    after_manifest, after, _ = revision.revise(*repair_inputs)
    if mutation == "gold":
        owner = after_manifest.owners[0]
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
        after_manifest = after_manifest.model_copy(
            update={"owners": [changed, *after_manifest.owners[1:]]}
        )
    elif mutation == "unlisted_text":
        query = before_manifest.owners[0].queries[-1]
        after["owners"][0]["query_text_by_case_id"][query.case_id] += " changed"
    elif mutation == "unlisted_edge":
        memory = next(
            m
            for m in before_manifest.owners[0].memories
            if m.surface_key == "memory-one-hop"
        )
        after["owners"][0]["edge_fact_by_memory_id"][memory.memory_id] += " changed"
    else:
        frozen["source"]["manifest_fingerprint"] = "wrong"
    with pytest.raises(ValueError):
        revision.validate_revision(
            before_manifest, after_manifest, before, after, frozen
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_owner",
        "unknown_memory",
        "unlisted_rename",
        "extra_recipe_field",
        "incomplete_date",
    ],
)
def test_bad_recipe_cannot_silently_drop_or_expand_edits(
    repair_inputs: Any, mutation: str
) -> None:
    recipe = repair_inputs[3]
    if mutation == "unknown_owner":
        recipe["owners"]["unrecognized"] = {}
    elif mutation == "unknown_memory":
        recipe["owners"]["owner-blind-01"] = {
            "memories": {"unknown": {"text": "x", "edge_fact": ""}}
        }
    elif mutation == "unlisted_rename":
        recipe["owners"]["owner-blind-01"] = {
            "entity_names": {"entity-peer": "somebody"}
        }
    elif mutation == "extra_recipe_field":
        recipe["scope"] = "other-scope"
    else:
        recipe["temporal_replacements"] = []
    with pytest.raises(ValueError):
        revision.revise(*repair_inputs)


def test_changed_source_hash_rejected(tmp_path: Path) -> None:
    path = tmp_path / "source.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="source hash mismatch"):
        revision._read_bound(path, "wrong")


def test_existing_output_never_overwritten(tmp_path: Path, monkeypatch: Any) -> None:
    prefix = tmp_path / "revised"
    output = Path(f"{prefix}-surfaces.json")
    output.write_text("keep", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["revision", "--output-prefix", str(prefix)])
    with pytest.raises(FileExistsError):
        revision.main()
    assert output.read_text(encoding="utf-8") == "keep"

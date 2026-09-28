"""Frozen structure checks for the owner-disjoint blind authoring manifest."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    BlindCorpusAuthoringManifest,
    build_authoring_request,
)

ROOT = Path(__file__).resolve().parents[1]
OPENED_V4 = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v4.json"
FROZEN_FINGERPRINT = "eb76c6d920d489fa0cd3dff7524b00ada82ec05ac8d511db9aae6f99177e9785"


def test_manifest_rebuild_has_frozen_counts_and_fingerprint() -> None:
    manifest = build_manifest()

    assert manifest.fingerprint == FROZEN_FINGERPRINT
    assert len(manifest.owners) == 24
    assert sum(len(owner.memories) for owner in manifest.owners) == 4_608
    assert sum(len(owner.queries) for owner in manifest.owners) == 240
    assert len(manifest.relation_types) == 17
    assert Counter(owner.partition for owner in manifest.owners) == {
        "dev": 6,
        "sealed": 12,
        "adversarial": 6,
    }
    assert all(len(owner.memories) == 192 for owner in manifest.owners)
    assert all(len(owner.queries) == 10 for owner in manifest.owners)
    assert all(
        sum(memory.corpus_role == "distractor" for memory in owner.memories) == 170
        for owner in manifest.owners
    )


def test_manifest_has_balanced_categories_and_diverse_two_hop_routes() -> None:
    manifest = build_manifest()
    queries = [query for owner in manifest.owners for query in owner.queries]
    categories = Counter(query.category for query in queries)
    pairs = {
        tuple(route)
        for query in queries
        for route in query.required_relation_routes
        if len(route) == 2
    }

    assert set(categories.values()) == {24}
    assert len(categories) == 10
    assert len(pairs) == 8
    assert ("HELD_BY", "LIVES_IN") not in pairs
    assert all(
        sum(bool(entity.shared_name_group) for entity in owner.entities) == 1
        for owner in manifest.owners
    )
    assert {
        entity.required_display_name
        for owner in manifest.owners
        for entity in owner.entities
        if entity.shared_name_group
    } == {"启明服务中心"}


def test_manifest_ids_do_not_reuse_opened_v4_ids_or_scopes() -> None:
    manifest = build_manifest()
    opened = json.loads(OPENED_V4.read_text("utf-8"))
    new_scopes = {owner.scope for owner in manifest.owners}
    new_memories = {
        memory.memory_id for owner in manifest.owners for memory in owner.memories
    }
    new_entities = {
        entity.entity_id for owner in manifest.owners for entity in owner.entities
    }
    new_cases = {query.case_id for owner in manifest.owners for query in owner.queries}

    assert new_scopes.isdisjoint(opened["scopes"])
    assert new_memories.isdisjoint(item["memory_id"] for item in opened["memories"])
    assert new_entities.isdisjoint(item["entity_id"] for item in opened["entities"])
    assert new_cases.isdisjoint(item["case_id"] for item in opened["queries"])


def test_every_owner_request_hides_private_identifiers_and_gold() -> None:
    nonces: set[str] = set()
    for owner in build_manifest().owners:
        request = build_authoring_request(owner)
        serialized = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
        nonces.add(str(request.input["authoring_nonce"]))
        assert owner.scope not in serialized
        assert owner.owner_key not in serialized
        assert all(entity.entity_id not in serialized for entity in owner.entities)
        assert all(memory.memory_id not in serialized for memory in owner.memories)
        assert all(query.case_id not in serialized for query in owner.queries)
        assert '"answerable"' not in serialized
        assert '"hard_forbidden_memory_keys"' not in serialized
    assert len(nonces) == 24


def test_top_level_validation_rejects_unknown_route_and_ineffective_gold() -> None:
    payload = build_manifest().model_dump(mode="json")
    payload["owners"][0]["queries"][5]["required_relation_routes"] = [
        ["UNKNOWN_RELATION"]
    ]
    with pytest.raises(ValueError, match="route type outside"):
        BlindCorpusAuthoringManifest.model_validate(payload)

    payload = build_manifest().model_dump(mode="json")
    payload["owners"][0]["queries"][0]["valid_at"] = "2024-01-01T00:00:00+08:00"
    with pytest.raises(ValueError, match="not effective"):
        BlindCorpusAuthoringManifest.model_validate(payload)

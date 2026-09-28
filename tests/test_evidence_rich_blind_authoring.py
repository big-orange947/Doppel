"""Authority-boundary tests for blind-corpus surface authoring."""

from __future__ import annotations

import json
from typing import Any

import pytest

from benchmarks.evidence_rich_blind_authoring import (
    AuthoredEntitySurface,
    AuthoredMemorySurface,
    AuthoredQuerySurface,
    HostEntitySlot,
    HostMemorySlot,
    HostQuerySlot,
    OwnerAuthoringManifest,
    OwnerSurfaceDraft,
    author_owner_surfaces,
    build_authoring_request,
    project_owner_surfaces,
)
from doppel_memory.intelligence import StructuredGenerationRequest


def _manifest() -> OwnerAuthoringManifest:
    return OwnerAuthoringManifest(
        owner_key="host-owner-01",
        scope="private-scope-secret",
        partition="sealed",
        entities=[
            HostEntitySlot(
                surface_key="entity-a",
                entity_id="private-entity-1",
                scope="private-scope-secret",
                entity_type="object",
                semantic_brief="一本摄影书",
            ),
            HostEntitySlot(
                surface_key="entity-b",
                entity_id="private-entity-2",
                scope="private-scope-secret",
                entity_type="person",
                semantic_brief="主人的一位朋友",
            ),
        ],
        memories=[
            HostMemorySlot(
                surface_key="memory-a",
                memory_id="private-memory-1",
                scope="private-scope-secret",
                kind="relation",
                semantic_brief="摄影书目前由朋友保管",
                subject_id="private-subject",
                authority="human_self",
                state="confirmed",
                valid_from="2026-01-01T00:00:00+08:00",
                relation_type="HELD_BY",
                source_entity_key="entity-a",
                target_entity_key="entity-b",
            ),
            HostMemorySlot(
                surface_key="memory-b",
                memory_id="private-memory-2",
                scope="private-scope-secret",
                kind="fact",
                semantic_brief="主人偏好纸质摄影书",
                subject_id="private-subject",
                authority="human_self",
                state="confirmed",
                valid_from="2026-01-01T00:00:00+08:00",
            ),
        ],
        queries=[
            HostQuerySlot(
                surface_key="query-a",
                case_id="private-case-1",
                scope="private-scope-secret",
                category="one_hop_relation",
                query_style="paraphrase",
                intent="lookup",
                temporal_view="current",
                semantic_brief="询问摄影书现在由谁保管",
                valid_at="2026-06-01T00:00:00+08:00",
                answerable=True,
                required_memory_keys=["memory-a"],
                required_relation_routes=[["HELD_BY"]],
            )
        ],
    )


def _draft() -> OwnerSurfaceDraft:
    return OwnerSurfaceDraft(
        entities=[
            AuthoredEntitySurface(surface_key="entity-a", name="潮汐摄影集"),
            AuthoredEntitySurface(surface_key="entity-b", name="林栩"),
        ],
        memories=[
            AuthoredMemorySurface(
                surface_key="memory-a",
                content="我的《潮汐摄影集》还放在林栩那里。",
                edge_fact="潮汐摄影集由林栩保管",
            ),
            AuthoredMemorySurface(
                surface_key="memory-b",
                content="我看摄影作品时更喜欢翻纸质书。",
            ),
        ],
        queries=[
            AuthoredQuerySurface(
                surface_key="query-a", query="我那本摄影集现在在谁手上？"
            )
        ],
    )


def test_provider_request_excludes_all_authority_and_gold_fields() -> None:
    request = build_authoring_request(_manifest())
    serialized = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)

    for secret in (
        "host-owner-01",
        "private-scope-secret",
        "private-entity-1",
        "private-memory-1",
        "private-subject",
        "private-case-1",
        "human_self",
        "confirmed",
        "2026-06-01",
    ):
        assert secret not in serialized
    for forbidden_field in (
        '"answerable"',
        '"required_memory_keys"',
        '"related_memory_keys"',
        '"hard_forbidden_memory_keys"',
    ):
        assert forbidden_field not in serialized
    assert '"surface_key": "memory-a"' in serialized
    assert '"type": "HELD_BY"' in serialized


def test_projection_changes_only_surface_fields() -> None:
    result = project_owner_surfaces(_manifest(), _draft())

    assert result.entity_names_by_id == {
        "private-entity-1": "潮汐摄影集",
        "private-entity-2": "林栩",
    }
    assert result.memory_content_by_id["private-memory-1"].startswith("我的")
    assert result.edge_fact_by_memory_id == {
        "private-memory-1": "潮汐摄影集由林栩保管",
        "private-memory-2": "",
    }
    assert result.query_text_by_case_id == {
        "private-case-1": "我那本摄影集现在在谁手上？"
    }


def test_projection_rejects_partial_extra_and_authority_fields() -> None:
    partial = _draft().model_dump(mode="json")
    partial["memories"] = partial["memories"][:1]
    with pytest.raises(ValueError, match="surface keys mismatch"):
        project_owner_surfaces(_manifest(), partial)

    injected = _draft().model_dump(mode="json")
    injected["memories"][0]["authority"] = "agent_output"
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        project_owner_surfaces(_manifest(), injected)


def test_projection_requires_relation_fact_and_rejects_fact_edge() -> None:
    missing_relation_fact = _draft().model_dump(mode="json")
    missing_relation_fact["memories"][0]["edge_fact"] = ""
    with pytest.raises(ValueError, match="requires an authored edge fact"):
        project_owner_surfaces(_manifest(), missing_relation_fact)

    invented_fact_edge = _draft().model_dump(mode="json")
    invented_fact_edge["memories"][1]["edge_fact"] = "不应存在"
    with pytest.raises(ValueError, match="cannot author an edge fact"):
        project_owner_surfaces(_manifest(), invented_fact_edge)


class _SurfaceModel:
    name = "tests.surface-model"
    version = "1"

    def __init__(self) -> None:
        self.request: StructuredGenerationRequest | None = None

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        self.request = request
        return _draft().model_dump(mode="json")


@pytest.mark.asyncio
async def test_authoring_runs_through_structured_model_boundary() -> None:
    model = _SurfaceModel()

    result = await author_owner_surfaces(_manifest(), model)

    assert model.request is not None
    assert result.query_text_by_case_id["private-case-1"].endswith("？")


def test_manifest_rejects_cross_scope_and_overlapping_gold() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["memories"][0]["scope"] = "other-owner"
    with pytest.raises(ValueError, match="one exact scope"):
        OwnerAuthoringManifest.model_validate(payload)

    payload = _manifest().model_dump(mode="json")
    payload["queries"][0]["related_memory_keys"] = ["memory-a"]
    with pytest.raises(ValueError, match="must not overlap"):
        OwnerAuthoringManifest.model_validate(payload)

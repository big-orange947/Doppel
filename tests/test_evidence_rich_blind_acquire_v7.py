"""Scope-local evidence uniqueness and three-parent V7 continuation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_acquire as v4
import benchmarks.evidence_rich_blind_acquire_v5 as v5
import benchmarks.evidence_rich_blind_acquire_v6 as v6
import benchmarks.evidence_rich_blind_acquire_v7 as v7
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    ProjectedOwnerSurfaces,
    split_owner_authoring_batches,
)
from doppel_memory.intelligence import StructuredGenerationRequest


class _CrossOwnerRepeatProvider:
    name = "tests.blind-surface-provider"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any | None = None
    ) -> None:
        del config, api_key
        self.usage_observer = usage_observer

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        if self.usage_observer is not None:
            self.usage_observer({"prompt_tokens": 100, "completion_tokens": 50})
        return {
            "entities": [
                {
                    "surface_key": item["surface_key"],
                    "name": item["required_display_name"]
                    or f"实体-{item['surface_key']}",
                }
                for item in request.input["entities"]
            ],
            "memories": [
                {
                    "surface_key": item["surface_key"],
                    "content": f"记忆-{item['surface_key']}",
                    "edge_fact": (
                        f"关系-{item['surface_key']}" if item["relation"] else ""
                    ),
                }
                for item in request.input["memories"]
            ],
            "queries": [
                {
                    "surface_key": item["surface_key"],
                    "query": f"问题-{item['surface_key']}？",
                }
                for item in request.input["queries"]
            ],
        }

    async def aclose(self) -> None:
        return None


def _projected(batch: Any, marker: str) -> ProjectedOwnerSurfaces:
    return ProjectedOwnerSurfaces(
        entity_names_by_id={
            item.entity_id: item.required_display_name
            or f"实体-{marker}-{item.surface_key}"
            for item in batch.entities
        },
        memory_content_by_id={
            item.memory_id: f"记忆-{marker}-{item.surface_key}"
            for item in batch.memories
        },
        edge_fact_by_memory_id={
            item.memory_id: (
                f"关系-{marker}-{item.surface_key}" if item.relation_type else ""
            )
            for item in batch.memories
        },
        query_text_by_case_id={
            item.case_id: f"问题-{marker}-{item.surface_key}？"
            for item in batch.queries
        },
    )


def test_registry_allows_cross_scope_evidence_but_rejects_same_scope() -> None:
    owners = build_manifest().owners[:2]
    first = split_owner_authoring_batches(owners[0])[0]
    second = split_owner_authoring_batches(owners[1])[0]
    first_surfaces = _projected(first, "共享")
    second_surfaces = _projected(second, "共享")
    registry = v7.ScopeSurfaceUniquenessRegistry()

    registry.add(first, first_surfaces)
    assert registry.collisions(second, second_surfaces) == ()

    second_part = split_owner_authoring_batches(owners[1])[1]
    second_part_surfaces = _projected(second_part, "第二批")
    duplicated = dict(second_part_surfaces.memory_content_by_id)
    duplicated[second_part.memories[0].memory_id] = next(
        iter(second_surfaces.memory_content_by_id.values())
    )
    same_scope_duplicate = second_part_surfaces.model_copy(
        update={"memory_content_by_id": duplicated}
    )
    registry.add(second, second_surfaces)
    assert registry.collisions(second_part, same_scope_duplicate) == (
        second_part.memories[0].surface_key,
    )


def _args(parser: Any, tmp_path: Path, version: int, calls: int) -> Any:
    values = [
        "--live-authoring",
        "--cache-dir",
        str(tmp_path / f"v{version}-cache"),
        "--progress-output",
        str(tmp_path / f"v{version}-progress.json"),
        "--output",
        str(tmp_path / f"v{version}-output.json"),
        "--max-new-calls",
        str(calls),
        "--model",
        "tests-model",
    ]
    parent_args = {
        5: ["--parent-cache-dir", str(tmp_path / "v4-cache")],
        6: [
            "--v4-cache-dir",
            str(tmp_path / "v4-cache"),
            "--v5-cache-dir",
            str(tmp_path / "v5-cache"),
        ],
        7: [
            "--v4-cache-dir",
            str(tmp_path / "v4-cache"),
            "--v5-cache-dir",
            str(tmp_path / "v5-cache"),
            "--v6-cache-dir",
            str(tmp_path / "v6-cache"),
        ],
    }
    values[1:1] = parent_args.get(version, [])
    return parser.parse_args(values)


@pytest.mark.asyncio
async def test_v7_replays_three_exhausted_layers_and_accepts_cross_scope_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    for module in (v4, v5, v6, v7):
        monkeypatch.setattr(
            module, "OpenAICompatibleStructuredOutputModel", _CrossOwnerRepeatProvider
        )
    monkeypatch.setattr(v4, "_git_commit_hash", lambda: "fixed-commit")

    assert await v4.run(_args(v4.parser(), tmp_path, 4, 5)) == 0
    assert await v5.run(_args(v5.parser(), tmp_path, 5, 3)) == 0
    assert await v6.run(_args(v6.parser(), tmp_path, 6, 3)) == 0
    v6_progress = json.loads((tmp_path / "v6-progress.json").read_text("utf-8"))
    assert v6_progress["completed_batch_count"] == 2
    assert v6_progress["provider_calls_cumulative"] == 11
    assert v6_progress["last_invocation"]["stopped_reason"] == (
        "SurfaceGenerationExhausted"
    )

    assert await v7.run(_args(v7.parser(), tmp_path, 7, 0)) == 0
    progress = json.loads((tmp_path / "v7-progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 3
    assert progress["provider_calls_cumulative"] == 11
    assert progress["accepted_attempts_by_batch"]["owner-blind-02:01"] == 1
    assert progress["evidence_uniqueness"] == "scope_local"
    assert progress["last_invocation"]["provider_calls"] == 0
    assert progress["last_invocation"]["v4_cache_hits"] == 3
    assert progress["last_invocation"]["surface_collision_attempts"] == 0
    assert progress["last_invocation"]["stopped_reason"] == "budget_exhausted"
    assert "test-only-secret" not in json.dumps(progress)

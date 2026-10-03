"""Resumability and budget tests for blind-corpus surface acquisition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_acquire as acquire
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    ProjectedOwnerSurfaces,
    split_owner_authoring_batches,
)
from doppel_memory.intelligence import StructuredGenerationRequest


class _FakeProvider:
    name = "tests.blind-surface-provider"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any | None = None
    ) -> None:
        del config, api_key
        self.usage_observer = usage_observer
        self.closed = False

    def _variant(self, request: StructuredGenerationRequest) -> str:
        return hashlib.sha256(
            str(request.input["authoring_nonce"]).encode()
        ).hexdigest()[:8]

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        if self.usage_observer is not None:
            self.usage_observer({"prompt_tokens": 100, "completion_tokens": 50})
        variant = self._variant(request)
        return {
            "entities": [
                {
                    "surface_key": item["surface_key"],
                    "name": item["required_display_name"]
                    or f"名称-{variant}-{item['surface_key']}",
                }
                for item in request.input["entities"]
            ],
            "memories": [
                {
                    "surface_key": item["surface_key"],
                    "content": f"自然表述-{variant}-{item['surface_key']}",
                    "edge_fact": (
                        f"关系表述-{variant}-{item['surface_key']}"
                        if item["relation"]
                        else ""
                    ),
                }
                for item in request.input["memories"]
            ],
            "queries": [
                {
                    "surface_key": item["surface_key"],
                    "query": f"自然问题-{variant}-{item['surface_key']}？",
                }
                for item in request.input["queries"]
            ],
        }

    async def aclose(self) -> None:
        self.closed = True


class _CollisionThenUniqueProvider(_FakeProvider):
    def _variant(self, request: StructuredGenerationRequest) -> str:
        if request.input["variation_attempt"] == 0:
            return "shared-attempt-zero"
        return super()._variant(request)


class _InvalidThenUniqueProvider(_FakeProvider):
    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        result = await super().generate(request)
        if request.input["variation_attempt"] == 0 and request.input["entities"]:
            mutable_keys = [
                item["surface_key"]
                for item in request.input["entities"]
                if not item["required_display_name"]
            ][:2]
            for entity in result["entities"]:
                if entity["surface_key"] in mutable_keys:
                    entity["name"] = "重复名称"
        return result


def _args(tmp_path: Path, *, max_new_calls: int, live: bool = True) -> Any:
    values = [
        "--cache-dir",
        str(tmp_path / "cache"),
        "--progress-output",
        str(tmp_path / "progress.json"),
        "--output",
        str(tmp_path / "surfaces.json"),
        "--max-new-calls",
        str(max_new_calls),
        "--model",
        "tests-model",
    ]
    if live:
        values.insert(0, "--live-authoring")
    return acquire.parser().parse_args(values)


def _projected_for_batch(batch: Any, variant: str) -> ProjectedOwnerSurfaces:
    return ProjectedOwnerSurfaces(
        entity_names_by_id={
            item.entity_id: item.required_display_name
            or f"实体-{variant}-{item.surface_key}"
            for item in batch.entities
        },
        memory_content_by_id={
            item.memory_id: f"记忆-{variant}-{item.surface_key}"
            for item in batch.memories
        },
        edge_fact_by_memory_id={
            item.memory_id: (
                f"关系-{variant}-{item.surface_key}" if item.relation_type else ""
            )
            for item in batch.memories
        },
        query_text_by_case_id={
            item.case_id: f"问题-{variant}-{item.surface_key}？"
            for item in batch.queries
        },
    )


def test_frozen_manifest_splits_into_exactly_two_batches_per_owner() -> None:
    manifest = build_manifest()
    batches = [
        batch
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(owner)
    ]

    assert len(batches) == 48
    for owner in manifest.owners:
        owner_batches = [item for item in batches if item.owner_key == owner.owner_key]
        assert [len(item.memories) for item in owner_batches] == [96, 96]
        assert len(owner_batches[0].entities) == len(owner.entities)
        assert len(owner_batches[0].queries) == len(owner.queries)
        assert not owner_batches[1].entities
        assert not owner_batches[1].queries
        assert {
            memory.memory_id for batch in owner_batches for memory in batch.memories
        } == {memory.memory_id for memory in owner.memories}


def test_global_registry_allows_scope_collisions_but_rejects_repeated_evidence() -> None:
    owners = build_manifest().owners[:2]
    first_batch = split_owner_authoring_batches(owners[0])[0]
    second_batch = split_owner_authoring_batches(owners[1])[0]
    first = _projected_for_batch(first_batch, "一")
    second = _projected_for_batch(second_batch, "二")
    registry = acquire.SurfaceUniquenessRegistry()

    registry.add(first_batch, first)
    assert registry.collisions(second_batch, second) == ()

    first_plain = next(item for item in first_batch.entities if not item.shared_name_group)
    second_plain = next(item for item in second_batch.entities if not item.shared_name_group)
    duplicated_names = dict(second.entity_names_by_id)
    duplicated_names[second_plain.entity_id] = first.entity_names_by_id[
        first_plain.entity_id
    ]
    duplicated = second.model_copy(
        update={"entity_names_by_id": duplicated_names}
    )
    first_query = first_batch.queries[0]
    second_query = second_batch.queries[0]
    duplicated_queries = dict(duplicated.query_text_by_case_id)
    duplicated_queries[second_query.case_id] = first.query_text_by_case_id[
        first_query.case_id
    ]
    duplicated = duplicated.model_copy(
        update={"query_text_by_case_id": duplicated_queries}
    )

    assert registry.collisions(second_batch, duplicated) == ()

    first_memory = first_batch.memories[0]
    second_memory = second_batch.memories[0]
    duplicated_memories = dict(duplicated.memory_content_by_id)
    duplicated_memories[second_memory.memory_id] = first.memory_content_by_id[
        first_memory.memory_id
    ]
    duplicated = duplicated.model_copy(
        update={"memory_content_by_id": duplicated_memories}
    )

    assert registry.collisions(second_batch, duplicated) == (second_memory.surface_key,)


@pytest.mark.asyncio
async def test_dry_run_is_zero_write_and_needs_no_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)

    assert await acquire.run(_args(tmp_path, max_new_calls=48, live=False)) == 0

    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "dry_run"
    assert plan["batch_count"] == 48
    assert plan["nominal_uncached_calls"] == 48
    assert plan["maximum_total_uncached_calls"] == 144
    assert plan["maximum_attempts_per_batch"] == 3
    assert plan["quality_metrics_available"] is False
    assert not tmp_path.joinpath("cache").exists()


@pytest.mark.asyncio
async def test_partial_authoring_resumes_from_raw_cache_without_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _FakeProvider)
    monkeypatch.setattr(acquire, "_git_commit_hash", lambda: "fixed-commit")
    args = _args(tmp_path, max_new_calls=1)

    assert await acquire.run(args) == 0
    first = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert first["completed_batch_count"] == 1
    assert first["provider_calls_cumulative"] == 1
    assert first["last_invocation"]["cache_hits"] == 0
    assert first["last_invocation"]["stopped_reason"] == "budget_exhausted"
    assert first["quality_metrics_available"] is False

    assert await acquire.run(args) == 0
    second = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert second["completed_batch_count"] == 2
    assert second["provider_calls_cumulative"] == 2
    assert second["last_invocation"]["cache_hits"] == 1
    assert second["usage_cumulative"] == {
        "calls_with_usage": 2,
        "completion_tokens": 100,
        "prompt_tokens": 200,
    }
    assert not (tmp_path / "surfaces.json").exists()
    serialized = json.dumps(second)
    assert "test-only-secret" not in serialized


@pytest.mark.asyncio
async def test_cross_owner_collision_uses_budgeted_reproducible_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    monkeypatch.setattr(
        acquire, "OpenAICompatibleStructuredOutputModel", _CollisionThenUniqueProvider
    )
    monkeypatch.setattr(acquire, "_git_commit_hash", lambda: "fixed-commit")

    assert await acquire.run(_args(tmp_path, max_new_calls=2)) == 0
    first = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert first["completed_batch_count"] == 2
    assert first["provider_calls_cumulative"] == 2

    assert await acquire.run(_args(tmp_path, max_new_calls=2)) == 0
    second = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert second["completed_batch_count"] == 3
    assert second["provider_calls_cumulative"] == 4
    assert second["last_invocation"]["cache_hits"] == 2
    assert second["last_invocation"]["surface_collision_attempts"] == 1
    assert second["accepted_attempts_by_batch"]["owner-blind-02:01"] == 2
    assert second["last_invocation"]["stopped_reason"] == "budget_exhausted"


@pytest.mark.asyncio
async def test_invalid_surface_attempt_is_bounded_and_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    monkeypatch.setattr(
        acquire, "OpenAICompatibleStructuredOutputModel", _InvalidThenUniqueProvider
    )
    monkeypatch.setattr(acquire, "_git_commit_hash", lambda: "fixed-commit")

    assert await acquire.run(_args(tmp_path, max_new_calls=2)) == 0
    progress = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 1
    assert progress["provider_calls_cumulative"] == 2
    assert progress["accepted_attempts_by_batch"]["owner-blind-01:01"] == 2
    assert (
        progress["last_invocation"]["surface_validation_rejection_attempts"]
        == 1
    )
    assert progress["last_invocation"]["stopped_reason"] == "budget_exhausted"


@pytest.mark.asyncio
async def test_complete_authoring_replays_cache_and_emits_all_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _FakeProvider)
    monkeypatch.setattr(acquire, "_git_commit_hash", lambda: "fixed-commit")

    assert await acquire.run(_args(tmp_path, max_new_calls=48)) == 0

    output = json.loads((tmp_path / "surfaces.json").read_text("utf-8"))
    progress = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert output["status"] == "authored_unreviewed"
    assert output["owner_count"] == 24
    assert output["review_complete"] is False
    assert output["retrieval_opened"] is False
    assert output["quality_metrics_available"] is False
    assert sum(len(item["memory_content_by_id"]) for item in output["owners"]) == 4_608
    assert sum(len(item["query_text_by_case_id"]) for item in output["owners"]) == 240
    assert progress["provider_calls_cumulative"] == 48
    assert progress["status"] == "complete"


@pytest.mark.asyncio
async def test_live_authoring_requires_key_before_new_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DOPPEL_API_KEY"):
        await acquire.run(_args(tmp_path, max_new_calls=1))
    assert not tmp_path.joinpath("cache").exists()


def test_authoring_manifest_rejects_binding_changes(tmp_path: Path) -> None:
    path = tmp_path / "cache" / acquire.MANIFEST_NAME
    acquire._bind_manifest(path, {"fingerprint": "one", "commit": "a"})
    acquire._bind_manifest(path, {"fingerprint": "one", "commit": "a"})

    with pytest.raises(ValueError, match="does not match"):
        acquire._bind_manifest(path, {"fingerprint": "two", "commit": "a"})

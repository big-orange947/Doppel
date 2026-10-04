"""Continuation guarantees for V5 sealed blind-corpus authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_acquire as v4
import benchmarks.evidence_rich_blind_acquire_v5 as v5
from doppel_memory.intelligence import StructuredGenerationRequest


class _PromptSensitiveProvider:
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
        strengthened = "same request" in request.instructions
        nonce = hashlib.sha256(
            str(request.input["authoring_nonce"]).encode()
        ).hexdigest()[:8]
        return {
            "entities": [
                {
                    "surface_key": item["surface_key"],
                    "name": item["required_display_name"]
                    or f"实体-{nonce}-{item['surface_key']}",
                }
                for item in request.input["entities"]
            ],
            "memories": [
                {
                    "surface_key": item["surface_key"],
                    "content": (
                        f"唯一记忆-{nonce}-{item['surface_key']}"
                        if strengthened
                        else "批内重复记忆"
                    ),
                    "edge_fact": (
                        f"唯一关系-{nonce}-{item['surface_key']}"
                        if item["relation"]
                        else ""
                    ),
                }
                for item in request.input["memories"]
            ],
            "queries": [
                {
                    "surface_key": item["surface_key"],
                    "query": f"问题-{nonce}-{item['surface_key']}？",
                }
                for item in request.input["queries"]
            ],
        }

    async def aclose(self) -> None:
        return None


def _v4_args(tmp_path: Path) -> Any:
    return v4.parser().parse_args(
        [
            "--live-authoring",
            "--cache-dir",
            str(tmp_path / "v4-cache"),
            "--progress-output",
            str(tmp_path / "v4-progress.json"),
            "--output",
            str(tmp_path / "v4-output.json"),
            "--max-new-calls",
            "3",
            "--model",
            "tests-model",
        ]
    )


def _v5_args(tmp_path: Path, *, max_new_calls: int) -> Any:
    return v5.parser().parse_args(
        [
            "--live-authoring",
            "--parent-cache-dir",
            str(tmp_path / "v4-cache"),
            "--cache-dir",
            str(tmp_path / "v5-cache"),
            "--progress-output",
            str(tmp_path / "v5-progress.json"),
            "--output",
            str(tmp_path / "v5-output.json"),
            "--max-new-calls",
            str(max_new_calls),
            "--model",
            "tests-model",
        ]
    )


def _provider_hashes(cache: Path) -> dict[str, str]:
    return {
        path.relative_to(cache).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(cache.glob("provider-output-v1/*/*.json"))
    }


def test_parent_cache_corruption_fails_closed(tmp_path: Path) -> None:
    cache = v5.ReadOnlyParentCache(
        tmp_path,
        {"name": "tests.blind-surface-provider", "version": "1"},
    )
    request = StructuredGenerationRequest(
        instructions="test",
        input={"value": 1},
        output_schema={"type": "object"},
    )
    path = cache._path(request)
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n", "utf-8")

    with pytest.raises(v5.ParentCacheIntegrityError):
        cache.get(request)
    assert cache.invalid_entries == 1


@pytest.mark.asyncio
async def test_v5_replays_exhausted_v4_and_continues_without_mutating_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    monkeypatch.setattr(
        v4, "OpenAICompatibleStructuredOutputModel", _PromptSensitiveProvider
    )
    monkeypatch.setattr(
        v5, "OpenAICompatibleStructuredOutputModel", _PromptSensitiveProvider
    )
    monkeypatch.setattr(v4, "_git_commit_hash", lambda: "fixed-commit")

    assert await v4.run(_v4_args(tmp_path)) == 0
    v4_progress = json.loads((tmp_path / "v4-progress.json").read_text("utf-8"))
    assert v4_progress["completed_batch_count"] == 0
    assert v4_progress["provider_calls_cumulative"] == 3
    assert v4_progress["last_invocation"]["stopped_reason"] == (
        "SurfaceGenerationExhausted"
    )
    before = _provider_hashes(tmp_path / "v4-cache")
    assert len(before) == 3

    assert await v5.run(_v5_args(tmp_path, max_new_calls=1)) == 0
    progress = json.loads((tmp_path / "v5-progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 1
    assert progress["provider_calls_cumulative"] == 4
    assert progress["accepted_attempts_by_batch"]["owner-blind-01:01"] == 4
    assert progress["last_invocation"]["provider_calls"] == 1
    assert progress["last_invocation"]["parent_cache_hits"] == 3
    assert progress["last_invocation"]["continuation_cache_hits"] == 0
    assert progress["last_invocation"]["stopped_reason"] == "budget_exhausted"
    assert _provider_hashes(tmp_path / "v4-cache") == before

    assert await v5.run(_v5_args(tmp_path, max_new_calls=0)) == 0
    replay = json.loads((tmp_path / "v5-progress.json").read_text("utf-8"))
    assert replay["completed_batch_count"] == 1
    assert replay["provider_calls_cumulative"] == 4
    assert replay["last_invocation"]["provider_calls"] == 0
    assert replay["last_invocation"]["parent_cache_hits"] == 3
    assert replay["last_invocation"]["continuation_cache_hits"] == 1
    assert _provider_hashes(tmp_path / "v4-cache") == before
    assert "test-only-secret" not in json.dumps(replay)

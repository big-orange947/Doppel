"""Two-parent continuation guarantees for V6 blind authoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_acquire as v4
import benchmarks.evidence_rich_blind_acquire_v5 as v5
import benchmarks.evidence_rich_blind_acquire_v6 as v6
from doppel_memory.intelligence import StructuredGenerationRequest


class _ThreeProtocolProvider:
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
        is_v6 = "audit the complete entities array" in request.instructions
        is_v5 = "same request" in request.instructions
        nonce = hashlib.sha256(
            str(request.input["authoring_nonce"]).encode()
        ).hexdigest()[:8]
        mutable_entities = [
            item
            for item in request.input["entities"]
            if not item["required_display_name"]
        ]
        duplicate_keys = {
            item["surface_key"] for item in mutable_entities[:2]
        }
        return {
            "entities": [
                {
                    "surface_key": item["surface_key"],
                    "name": (
                        item["required_display_name"]
                        or (
                            "重复实体"
                            if is_v5
                            and not is_v6
                            and item["surface_key"] in duplicate_keys
                            else f"实体-{nonce}-{item['surface_key']}"
                        )
                    ),
                }
                for item in request.input["entities"]
            ],
            "memories": [
                {
                    "surface_key": item["surface_key"],
                    "content": (
                        f"唯一记忆-{nonce}-{item['surface_key']}"
                        if is_v5 or is_v6
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


def _args(
    parser: Any,
    tmp_path: Path,
    *,
    version: int,
    max_new_calls: int,
) -> Any:
    values = [
        "--live-authoring",
        "--cache-dir",
        str(tmp_path / f"v{version}-cache"),
        "--progress-output",
        str(tmp_path / f"v{version}-progress.json"),
        "--output",
        str(tmp_path / f"v{version}-output.json"),
        "--max-new-calls",
        str(max_new_calls),
        "--model",
        "tests-model",
    ]
    if version == 5:
        values[1:1] = ["--parent-cache-dir", str(tmp_path / "v4-cache")]
    if version == 6:
        values[1:1] = [
            "--v4-cache-dir",
            str(tmp_path / "v4-cache"),
            "--v5-cache-dir",
            str(tmp_path / "v5-cache"),
        ]
    return parser.parse_args(values)


def _hashes(cache: Path) -> dict[str, str]:
    return {
        path.relative_to(cache).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(cache.glob("provider-output-v1/*/*.json"))
    }


@pytest.mark.asyncio
async def test_v6_replays_v4_and_v5_then_recovers_on_seventh_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-secret")
    for module in (v4, v5, v6):
        monkeypatch.setattr(
            module, "OpenAICompatibleStructuredOutputModel", _ThreeProtocolProvider
        )
    monkeypatch.setattr(v4, "_git_commit_hash", lambda: "fixed-commit")

    assert await v4.run(_args(v4.parser(), tmp_path, version=4, max_new_calls=3)) == 0
    assert await v5.run(_args(v5.parser(), tmp_path, version=5, max_new_calls=3)) == 0
    v5_progress = json.loads((tmp_path / "v5-progress.json").read_text("utf-8"))
    assert v5_progress["completed_batch_count"] == 0
    assert v5_progress["provider_calls_cumulative"] == 6
    assert v5_progress["last_invocation"]["stopped_reason"] == (
        "SurfaceGenerationExhausted"
    )
    v4_before = _hashes(tmp_path / "v4-cache")
    v5_before = _hashes(tmp_path / "v5-cache")
    assert len(v4_before) == 3
    assert len(v5_before) == 3

    assert await v6.run(_args(v6.parser(), tmp_path, version=6, max_new_calls=1)) == 0
    progress = json.loads((tmp_path / "v6-progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 1
    assert progress["provider_calls_cumulative"] == 7
    assert progress["accepted_attempts_by_batch"]["owner-blind-01:01"] == 7
    assert progress["last_invocation"]["provider_calls"] == 1
    assert progress["last_invocation"]["v4_cache_hits"] == 3
    assert progress["last_invocation"]["v5_cache_hits"] == 3
    assert progress["last_invocation"]["v6_cache_hits"] == 0
    assert progress["last_invocation"]["stopped_reason"] == "budget_exhausted"
    assert _hashes(tmp_path / "v4-cache") == v4_before
    assert _hashes(tmp_path / "v5-cache") == v5_before

    assert await v6.run(_args(v6.parser(), tmp_path, version=6, max_new_calls=0)) == 0
    replay = json.loads((tmp_path / "v6-progress.json").read_text("utf-8"))
    assert replay["completed_batch_count"] == 1
    assert replay["provider_calls_cumulative"] == 7
    assert replay["last_invocation"]["provider_calls"] == 0
    assert replay["last_invocation"]["v6_cache_hits"] == 1
    assert "test-only-secret" not in json.dumps(replay)

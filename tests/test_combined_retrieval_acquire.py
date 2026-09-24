"""Contracts for resumable, commit-bound combined topology acquisition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.combined_retrieval_acquire as acquire
from doppel_memory.intelligence import StructuredGenerationRequest

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks/datasets/combined-retrieval-zh-v2.json"
CATALOG = ROOT / "benchmarks/catalogs/personal-relations-v1.json"


class _FakeProvider:
    name = "tests.fake-provider"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any | None = None
    ) -> None:
        del config, api_key
        self.usage_observer = usage_observer
        self.closed = False

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        del request
        if self.usage_observer is not None:
            self.usage_observer({"prompt_tokens": 10, "completion_tokens": 2})
        return {"topologies": []}

    async def aclose(self) -> None:
        self.closed = True


def _args(tmp_path: Path, *, max_new_calls: int = 1) -> Any:
    return acquire.parser().parse_args(
        [
            "--live",
            "--dataset",
            str(DATASET),
            "--relation-catalog",
            str(CATALOG),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--progress-output",
            str(tmp_path / "progress.json"),
            "--output",
            str(tmp_path / "complete.json"),
            "--max-new-calls",
            str(max_new_calls),
            "--model",
            "tests-model",
        ]
    )


@pytest.mark.asyncio
async def test_partial_acquisition_resumes_without_exposing_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-key")
    monkeypatch.setattr(
        acquire, "OpenAICompatibleStructuredOutputModel", _FakeProvider
    )
    monkeypatch.setattr(acquire, "_git_commit_hash", lambda: "fixed-commit")
    args = _args(tmp_path)

    assert await acquire.run(args) == 0
    first = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert first["status"] == "incomplete"
    assert first["completed_case_count"] == 0
    assert first["provider_calls_cumulative"] == 1
    assert first["metrics_available"] is False
    assert not (tmp_path / "complete.json").exists()

    assert await acquire.run(args) == 0
    second = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert second["status"] == "incomplete"
    assert second["completed_case_count"] == 1
    assert second["provider_calls_cumulative"] == 2
    assert second["usage_cumulative"] == {
        "calls_with_usage": 2,
        "completion_tokens": 4,
        "prompt_tokens": 20,
    }
    assert not (tmp_path / "complete.json").exists()
    serialized = (tmp_path / "progress.json").read_text("utf-8")
    assert "test-only-key" not in serialized


def test_acquisition_manifest_rejects_binding_changes(tmp_path: Path) -> None:
    path = tmp_path / "cache" / acquire.MANIFEST_NAME
    acquire._bind_manifest(path, {"dataset": "one", "commit": "a"})
    acquire._bind_manifest(path, {"dataset": "one", "commit": "a"})

    with pytest.raises(ValueError, match="does not match"):
        acquire._bind_manifest(path, {"dataset": "two", "commit": "a"})


def test_topology_gate_applies_preregistered_thresholds() -> None:
    metrics = {
        "required_route_recall": 0.80,
        "one_hop_route_recall": 0.90,
        "two_hop_route_recall": 0.70,
        "no_path_false_candidate_rate": 0.10,
        "extra_routes_per_case": 0.25,
        "invalid_compilation_count": 0,
        "errors": 0,
    }
    assert acquire.topology_quality_gate(metrics)["passed"] is True

    metrics["two_hop_route_recall"] = 0.64
    failed = acquire.topology_quality_gate(metrics)
    assert failed["passed"] is False
    assert failed["failures"] == ["two_hop_route_recall"]


@pytest.mark.asyncio
async def test_dry_run_never_requires_key_or_writes_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    args = acquire.parser().parse_args(
        [
            "--dataset",
            str(DATASET),
            "--relation-catalog",
            str(CATALOG),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )

    assert await acquire.run(args) == 0
    assert not (tmp_path / "cache").exists()

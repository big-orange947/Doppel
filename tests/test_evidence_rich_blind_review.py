"""Independent semantic-review contracts for the blind evidence-rich corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_review as review_runner
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    OwnerSurfaceReview,
    SurfaceReviewIssue,
    build_review_request,
    split_owner_authoring_batches,
    validate_surface_review,
)
from doppel_memory.intelligence import StructuredGenerationRequest


def _write_authored(path: Path) -> dict[str, Any]:
    manifest = build_manifest()
    payload = {
        "runner": "doppel.evidence-rich-blind-authoring.v2",
        "status": "authored_unreviewed",
        "manifest_fingerprint": manifest.fingerprint,
        "review_complete": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "owners": [
            {
                "owner_key": owner.owner_key,
                "entity_names_by_id": {
                    item.entity_id: (
                        item.required_display_name or f"名称-{item.surface_key}"
                    )
                    for item in owner.entities
                },
                "memory_content_by_id": {
                    item.memory_id: f"自然表述-{item.surface_key}"
                    for item in owner.memories
                },
                "edge_fact_by_memory_id": {
                    item.memory_id: (
                        f"关系表述-{item.surface_key}" if item.relation_type else ""
                    )
                    for item in owner.memories
                },
                "query_text_by_case_id": {
                    item.case_id: f"自然问题-{item.surface_key}？"
                    for item in owner.queries
                },
            }
            for owner in manifest.owners
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    return payload


class _AcceptingReviewer:
    name = "tests.blind-surface-reviewer"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any | None = None
    ) -> None:
        del config, api_key
        self.usage_observer = usage_observer

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        if self.usage_observer is not None:
            self.usage_observer({"prompt_tokens": 120, "completion_tokens": 20})
        keys = [
            item["surface_key"]
            for group in ("entities", "memories", "queries")
            for item in request.input[group]
        ]
        return {"reviewed_surface_keys": keys, "issues": []}

    async def aclose(self) -> None:
        return None


class _RejectingReviewer(_AcceptingReviewer):
    version = "rejecting-1"

    async def generate(self, request: StructuredGenerationRequest) -> dict[str, Any]:
        result = await super().generate(request)
        first = result["reviewed_surface_keys"][0]
        result["issues"] = [
            {
                "surface_key": first,
                "issue_code": "semantic_drift",
                "detail": "表述没有完整表达给定语义",
            }
        ]
        return result


def _args(tmp_path: Path, *, max_new_calls: int, live: bool = True) -> Any:
    values = [
        "--authored-surfaces",
        str(tmp_path / "authored.json"),
        "--cache-dir",
        str(tmp_path / "review-cache"),
        "--progress-output",
        str(tmp_path / "progress.json"),
        "--output",
        str(tmp_path / "review.json"),
        "--max-new-calls",
        str(max_new_calls),
        "--model",
        "tests-review-model",
    ]
    if live:
        values.insert(0, "--live-review")
    return review_runner.parser().parse_args(values)


def test_review_request_hides_private_ids_and_gold(tmp_path: Path) -> None:
    manifest = build_manifest()
    owner = manifest.owners[0]
    batch = split_owner_authoring_batches(owner)[0]
    authored = _write_authored(tmp_path / "authored.json")
    draft = review_runner._draft_for_batch(batch, authored)
    request = build_review_request(batch, draft)
    serialized = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)

    assert owner.scope not in serialized
    assert owner.owner_key not in serialized
    assert all(item.memory_id not in serialized for item in batch.memories)
    assert all(item.case_id not in serialized for item in batch.queries)
    assert '"answerable"' not in serialized
    assert '"hard_forbidden_memory_keys"' not in serialized
    assert "自然表述-memory-current-residence" in serialized


def test_review_validation_requires_complete_exact_coverage() -> None:
    batch = split_owner_authoring_batches(build_manifest().owners[0])[1]
    keys = [item.surface_key for item in batch.memories]
    accepted = validate_surface_review(
        batch, OwnerSurfaceReview(reviewed_surface_keys=keys)
    )
    assert accepted.issues == []

    with pytest.raises(ValueError, match="reviewed surface keys mismatch"):
        validate_surface_review(
            batch, OwnerSurfaceReview(reviewed_surface_keys=keys[:-1])
        )
    with pytest.raises(ValueError, match="unknown surface key"):
        validate_surface_review(
            batch,
            OwnerSurfaceReview(
                reviewed_surface_keys=keys,
                issues=[
                    SurfaceReviewIssue(
                        surface_key="outside-batch",
                        issue_code="semantic_drift",
                        detail="错误引用",
                    )
                ],
            ),
        )


@pytest.mark.asyncio
async def test_review_dry_run_is_zero_write_and_allows_missing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)

    assert await review_runner.run(_args(tmp_path, max_new_calls=48, live=False)) == 0

    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "dry_run"
    assert plan["authored_surfaces_available"] is False
    assert plan["batch_count"] == 48
    assert plan["auto_rewrite_enabled"] is False
    assert not (tmp_path / "review-cache").exists()


@pytest.mark.asyncio
async def test_partial_review_resumes_without_exposing_quality_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_authored(tmp_path / "authored.json")
    monkeypatch.setenv("DOPPEL_API_KEY", "test-review-secret")
    monkeypatch.setattr(
        review_runner, "OpenAICompatibleStructuredOutputModel", _AcceptingReviewer
    )
    monkeypatch.setattr(review_runner, "_git_commit_hash", lambda: "fixed-review")
    args = _args(tmp_path, max_new_calls=1)

    assert await review_runner.run(args) == 0
    assert await review_runner.run(args) == 0

    progress = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 2
    assert progress["provider_calls_cumulative"] == 2
    assert progress["last_invocation"]["cache_hits"] == 1
    assert progress["quality_metrics_available"] is False
    assert progress["retrieval_opened"] is False
    assert not (tmp_path / "review.json").exists()
    assert "test-review-secret" not in json.dumps(progress)


@pytest.mark.asyncio
async def test_complete_review_replays_cache_and_accepts_without_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_authored(tmp_path / "authored.json")
    monkeypatch.setenv("DOPPEL_API_KEY", "test-review-secret")
    monkeypatch.setattr(
        review_runner, "OpenAICompatibleStructuredOutputModel", _AcceptingReviewer
    )
    monkeypatch.setattr(review_runner, "_git_commit_hash", lambda: "fixed-review")

    assert await review_runner.run(_args(tmp_path, max_new_calls=48)) == 0

    report = json.loads((tmp_path / "review.json").read_text("utf-8"))
    assert report["status"] == "reviewed_accepted"
    assert report["accepted"] is True
    assert report["issue_count"] == 0
    assert report["batch_count"] == 48
    assert report["auto_rewrite_performed"] is False
    assert report["retrieval_opened"] is False
    assert report["quality_metrics_available"] is False
    assert report["acquisition"]["provider_calls"] == 48


@pytest.mark.asyncio
async def test_rejected_review_is_preserved_and_returns_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_authored(tmp_path / "authored.json")
    monkeypatch.setenv("DOPPEL_API_KEY", "test-review-secret")
    monkeypatch.setattr(
        review_runner, "OpenAICompatibleStructuredOutputModel", _RejectingReviewer
    )
    monkeypatch.setattr(review_runner, "_git_commit_hash", lambda: "fixed-review")

    assert await review_runner.run(_args(tmp_path, max_new_calls=48)) == 1

    report = json.loads((tmp_path / "review.json").read_text("utf-8"))
    assert report["status"] == "reviewed_rejected"
    assert report["accepted"] is False
    assert report["issue_count"] == 48
    assert report["auto_rewrite_performed"] is False


@pytest.mark.asyncio
async def test_live_review_requires_authored_first_run_before_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    with pytest.raises(FileNotFoundError, match="authored surface artifact"):
        await review_runner.run(_args(tmp_path, max_new_calls=1))
    assert not (tmp_path / "review-cache").exists()

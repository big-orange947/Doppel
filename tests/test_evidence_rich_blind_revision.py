"""Pre-result schema repair, immutable parent reuse, and sealed revision behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks import evidence_rich_blind_compile as compiler
from benchmarks import evidence_rich_blind_review as reviewer
from benchmarks import evidence_rich_blind_revision as revision
from benchmarks.build_evidence_rich_blind_manifest import build_manifest as original
from benchmarks.build_evidence_rich_blind_manifest_v2 import (
    audit_relation_endpoints,
    build_manifest,
)
from benchmarks.evidence_rich_blind_authoring import (
    build_authoring_request,
    split_owner_authoring_batches,
)
from doppel_memory.openai_compatible import StructuredOutputProviderError


def _parents(tmp_path: Path) -> tuple[Path, Path]:
    manifest = original()
    authored = {
        "runner": "doppel.evidence-rich-blind-authoring.v8",
        "status": "authored_unreviewed",
        "manifest_fingerprint": manifest.fingerprint,
        "review_complete": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "acquisition": {"provider_calls": 78},
        "owners": [],
    }
    for owner in manifest.owners:
        authored["owners"].append(
            {
                "owner_key": owner.owner_key,
                "entity_names_by_id": {
                    e.entity_id: e.required_display_name or f"原-{e.surface_key}"
                    for e in owner.entities
                },
                "memory_content_by_id": {
                    m.memory_id: f"原-{owner.owner_key}-{m.surface_key}"
                    for m in owner.memories
                },
                "edge_fact_by_memory_id": {
                    m.memory_id: f"关系-{m.surface_key}" if m.relation_type else ""
                    for m in owner.memories
                },
                "query_text_by_case_id": {
                    q.case_id: f"问题-{q.surface_key}" for q in owner.queries
                },
            }
        )
    authored_path = tmp_path / "original-authored.json"
    authored_path.write_text(json.dumps(authored, ensure_ascii=False), "utf-8")
    rows = []
    for owner in manifest.owners:
        for batch in split_owner_authoring_batches(owner):
            keys = sorted(
                x.surface_key
                for x in [*batch.entities, *batch.memories, *batch.queries]
            )
            issues = (
                [
                    {
                        "surface_key": "memory-competing-first",
                        "issue_code": "relation_mismatch",
                        "detail": "文字与边端点不同",
                    }
                ]
                if batch.entities
                else []
            )
            rows.append(
                {
                    "batch_id": batch.batch_id,
                    "owner_key": owner.owner_key,
                    "reviewed_surface_count": len(keys),
                    "reviewed_surface_keys_sha256": acquire._fingerprint(keys),
                    "issue_count": len(issues),
                    "issues": issues,
                }
            )
    review = {
        "status": "reviewed_rejected",
        "accepted": False,
        "review_complete": True,
        "retrieval_opened": False,
        "auto_rewrite_performed": False,
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": acquire._sha256(authored_path),
        "batch_count": len(rows),
        "issue_count": sum(r["issue_count"] for r in rows),
        "batches": rows,
        "acquisition": {"provider_calls": 49},
    }
    review_path = tmp_path / "original-review.json"
    review_path.write_text(json.dumps(review), "utf-8")
    return authored_path, review_path


def _args(
    tmp_path: Path, authored: Path, review: Path, calls: int, stage: str = "author"
) -> Any:
    values = [
        stage,
        "--max-new-calls",
        str(calls),
        "--cache-dir",
        str(tmp_path / f"{stage}-cache"),
        "--progress-output",
        str(tmp_path / f"{stage}-progress.json"),
        "--output",
        str(tmp_path / f"{stage}-output.json"),
    ]
    if stage == "author":
        values += [
            "--live-authoring",
            "--parent-authored",
            str(authored),
            "--parent-review",
            str(review),
        ]
    else:
        values += [
            "--live-review",
            "--authored-surfaces",
            str(tmp_path / "author-output.json"),
        ]
    return revision.parser().parse_args(values)


class _FakeProvider:
    name = "tests.blind-revision"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any = None
    ) -> None:
        del config, api_key
        self.observer = usage_observer

    async def generate(self, request: Any) -> dict[str, Any]:
        if self.observer:
            self.observer(
                {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
            )
        if request.output_schema["title"] == "OwnerSurfaceReview":
            return {
                "reviewed_surface_keys": [
                    x["surface_key"]
                    for kind in ("entities", "memories", "queries")
                    for x in request.input[kind]
                ],
                "issues": [],
            }
        return {
            "entities": [
                {
                    "surface_key": x["surface_key"],
                    "name": x["required_display_name"] or f"新-{x['surface_key']}",
                }
                for x in request.input["entities"]
            ],
            "memories": [
                {
                    "surface_key": x["surface_key"],
                    "content": f"新-{x['surface_key']}",
                    "edge_fact": f"新关系-{x['surface_key']}" if x["relation"] else "",
                }
                for x in request.input["memories"]
            ],
            "queries": [
                {"surface_key": x["surface_key"], "query": f"新问题-{x['surface_key']}"}
                for x in request.input["queries"]
            ],
        }

    async def aclose(self) -> None:
        pass


def test_original_stays_frozen_and_revised_endpoints_are_coherent() -> None:
    old = original()
    revised = build_manifest()
    assert (
        old.fingerprint
        == "852dfde146d8ac2920683ac275eb5a35700bdb47e01cf09cad4dd0433065d253"
    )
    assert revised.fingerprint != old.fingerprint
    assert audit_relation_endpoints(old)
    assert audit_relation_endpoints(revised) == []
    assert len(revised.owners) == 24
    for old_owner, owner in zip(old.owners, revised.owners, strict=True):
        assert (
            split_owner_authoring_batches(old_owner)[1]
            == split_owner_authoring_batches(owner)[1]
        )
        memories = {m.surface_key: m for m in owner.memories}
        assert (
            memories["memory-competing-first"].source_entity_key
            == "entity-one-hop-anchor"
        )
        assert (
            "不得换成另一个相似对象"
            in memories["memory-competing-first"].semantic_brief
        )
        assert (
            memories["memory-no-answer-related"].source_entity_key
            != memories["memory-one-hop"].source_entity_key
        )
        assert "2026年2月1日" in memories["memory-temporary-residence"].semantic_brief
        assert "2026年4月1日" in memories["memory-temporary-residence"].semantic_brief


def test_seed_reuses_only_unchanged_issue_free_batches_and_detects_tampering(
    tmp_path: Path,
) -> None:
    authored, review = _parents(tmp_path)
    before = (authored.read_bytes(), review.read_bytes())
    seeds, binding = revision.load_parent_seed(authored, review)
    assert len(seeds) == 24
    assert all(key.endswith(":02") for key in seeds)
    assert binding["review_sha256"] == acquire._sha256(review)
    assert before == (authored.read_bytes(), review.read_bytes())
    raw = json.loads(review.read_text("utf-8"))
    raw["batches"][1]["reviewed_surface_keys_sha256"] = "wrong"
    review.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(ValueError, match="coverage"):
        revision.load_parent_seed(authored, review)


def test_flagged_unchanged_batch_is_never_seeded(tmp_path: Path) -> None:
    authored, review = _parents(tmp_path)
    raw = json.loads(review.read_text("utf-8"))
    raw["batches"][1]["issues"] = [
        {
            "surface_key": "memory-distractor-100",
            "issue_code": "semantic_drift",
            "detail": "不一致",
        }
    ]
    raw["batches"][1]["issue_count"] = 1
    raw["issue_count"] += 1
    review.write_text(json.dumps(raw), "utf-8")
    seeds, _ = revision.load_parent_seed(authored, review)
    assert len(seeds) == 23
    assert "owner-blind-01:02" not in seeds


def test_rejected_parent_cannot_be_compiled(tmp_path: Path) -> None:
    authored, review = _parents(tmp_path)
    with pytest.raises(ValueError, match="accepted first semantic review"):
        compiler._validate_review(
            original(), json.loads(review.read_text("utf-8")), acquire._sha256(authored)
        )


def test_revised_prompt_keeps_private_authority_fields_hidden() -> None:
    owner = build_manifest().owners[0]
    batch = split_owner_authoring_batches(owner)[0]
    request = revision.build_authoring_request_v2(batch)
    serialized = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    assert owner.scope not in serialized and owner.owner_key not in serialized
    assert all(m.memory_id not in serialized for m in batch.memories)
    assert all(q.case_id not in serialized for q in batch.queries)
    assert '"answerable"' not in serialized and '"corpus_role"' not in serialized
    assert (
        request.input["authoring_nonce"]
        != build_authoring_request(batch).input["authoring_nonce"]
    )
    assert "Cross-owner equality is permitted" in request.instructions
    assert request.input["relation_meanings"]["HELD_BY"] == "由目标保管、持有"


@pytest.mark.asyncio
async def test_revision_rejects_exposed_nonce_without_losing_inherited_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Leaking(_FakeProvider):
        async def generate(self, request: Any) -> dict[str, Any]:
            result = await super().generate(request)
            result["memories"][0]["content"] += request.input["authoring_nonce"]
            return result

    authored, review = _parents(tmp_path)
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-key")
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _Leaking)
    await revision.run(_args(tmp_path, authored, review, 1))
    progress = json.loads((tmp_path / "author-progress.json").read_text("utf-8"))
    assert progress["completed_batch_count"] == 24
    assert progress["last_invocation"]["surface_validation_rejection_attempts"] == 1
    assert not (tmp_path / "author-output.json").exists()


@pytest.mark.asyncio
async def test_revision_resumes_and_reviews_all_surfaces_without_changing_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authored, review = _parents(tmp_path)
    initial = (authored.read_bytes(), review.read_bytes())
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-key")
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _FakeProvider)
    monkeypatch.setattr(
        reviewer, "OpenAICompatibleStructuredOutputModel", _FakeProvider
    )
    assert await revision.run(_args(tmp_path, authored, review, 1)) == 0
    assert await revision.run(_args(tmp_path, authored, review, 23)) == 0
    a = json.loads((tmp_path / "author-output.json").read_text("utf-8"))
    assert a["acquisition"]["completed_batch_count"] == 48
    assert a["acquisition"]["provider_calls"] == 24
    assert a["parents"]["seed_batch_ids"] == sorted(
        revision.load_parent_seed(authored, review)[0]
    )
    assert a["status"] == "authored_unreviewed" and not a["retrieval_opened"]
    assert await revision.run(_args(tmp_path, authored, review, 48, "review")) == 0
    r = json.loads((tmp_path / "review-output.json").read_text("utf-8"))
    assert r["accepted"] is True and r["batch_count"] == 48
    assert r["acquisition"]["provider_calls"] == 48
    compiler._validate_authored(build_manifest(), a)
    compiler._validate_review(
        build_manifest(), r, acquire._sha256(tmp_path / "author-output.json")
    )
    dataset = compiler.compile_corpus(build_manifest(), a)
    compiler._validate_novel_surfaces(dataset)
    assert len(dataset.memories) == 4608 and len(dataset.queries) == 240
    assert initial == (authored.read_bytes(), review.read_bytes())


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["author", "review"])
async def test_provider_error_is_content_free_and_accounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    class _Failing(_FakeProvider):
        async def generate(self, request: Any) -> dict[str, Any]:
            raise StructuredOutputProviderError(
                "rate_limited", "secret-provider-body", status_code=429, retryable=True
            )

    authored, review = _parents(tmp_path)
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-key")
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _Failing)
    monkeypatch.setattr(reviewer, "OpenAICompatibleStructuredOutputModel", _Failing)
    if stage == "review":
        payload = json.loads(authored.read_text("utf-8"))
        payload["manifest_fingerprint"] = build_manifest().fingerprint
        for revised_owner, owner in zip(
            build_manifest().owners, payload["owners"], strict=True
        ):
            for entity in revised_owner.entities:
                owner["entity_names_by_id"].setdefault(
                    entity.entity_id, f"新增-{entity.surface_key}"
                )
        (tmp_path / "author-output.json").write_text(json.dumps(payload), "utf-8")
    await revision.run(_args(tmp_path, authored, review, 1, stage))
    progress = json.loads((tmp_path / f"{stage}-progress.json").read_text("utf-8"))
    assert progress["last_invocation"]["provider_error"] == {
        "code": "rate_limited",
        "http_status": 429,
        "retryable": True,
    }
    assert progress["provider_calls_cumulative"] == 1
    assert "secret-provider-body" not in json.dumps(progress)
    assert "test-only-key" not in json.dumps(progress)

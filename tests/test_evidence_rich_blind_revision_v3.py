"""Read-only retry replay and prose-only repair before any retrieval measurement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks import evidence_rich_blind_revision as v2
from benchmarks import evidence_rich_blind_revision_v3 as v3
from benchmarks.build_evidence_rich_blind_manifest_v2 import audit_relation_endpoints
from benchmarks.evidence_rich_blind_acquire_v5 import ParentCacheIntegrityError
from benchmarks.evidence_rich_blind_authoring import (
    project_owner_surfaces,
    split_owner_authoring_batches,
)
from benchmarks.relation_planner_quality import PROVIDER_OUTPUT_CACHE_NAMESPACE
from tests.test_evidence_rich_blind_revision import _args, _FakeProvider, _parents


class _FailingAuthor(_FakeProvider):
    """Nine accepted heads, a collision, and a six-attempt duplicate-name stop."""

    async def generate(self, request: Any) -> dict[str, Any]:
        result = await super().generate(request)
        batch_stop = "owner-blind-10:01"
        nonce = request.input["authoring_nonce"]
        attempt = request.input["variation_attempt"]
        stop_nonce = hashlib.sha256(
            f"blind-revision-v2:{batch_stop}:{attempt}".encode()
        ).hexdigest()[:24]
        duplicate_nonce = hashlib.sha256(
            b"blind-revision-v2:owner-blind-01:01:0"
        ).hexdigest()[:24]
        collision_nonce = hashlib.sha256(
            b"blind-revision-v2:owner-blind-02:01:0"
        ).hexdigest()[:24]
        if nonce in (stop_nonce, duplicate_nonce):
            result["entities"][1]["name"] = result["entities"][0]["name"]
        if nonce == collision_nonce:
            result["memories"][0]["content"] = request.input[
                "previously_accepted_owner_memory_texts"
            ][0]
        return result


async def _stopped_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    authored, review = _parents(tmp_path)
    monkeypatch.setenv("DOPPEL_API_KEY", "test-only-key")
    monkeypatch.setattr(
        acquire, "OpenAICompatibleStructuredOutputModel", _FailingAuthor
    )
    assert await v2.run(_args(tmp_path, authored, review, 30)) == 0
    cache = tmp_path / "author-cache"
    state = json.loads((cache / acquire.STATE_NAME).read_text("utf-8"))
    assert state["completed_batch_count"] == 33
    assert state["provider_calls"] == 17
    assert state["last_invocation"]["stopped_reason"] == "SurfaceGenerationExhausted"
    return authored, review, cache


def _v3_args(
    tmp_path: Path, authored: Path, review: Path, cache: Path, stage: str, calls: int
) -> Any:
    values = [
        stage,
        "--max-new-calls",
        str(calls),
        "--cache-dir",
        str(tmp_path / f"v3-{stage}-cache"),
        "--progress-output",
        str(tmp_path / f"v3-{stage}-progress.json"),
        "--output",
        str(tmp_path / f"v3-{stage}-output.json"),
    ]
    if stage == "author":
        values += [
            "--live-authoring",
            "--parent-authored",
            str(authored),
            "--parent-review",
            str(review),
            "--parent-cache-dir",
            str(cache),
        ]
    else:
        values += [
            "--live-review",
            "--authored-surfaces",
            str(tmp_path / "v3-author-output.json"),
        ]
    return v3.parser().parse_args(values)


def _inventory(cache: Path) -> dict[str, bytes]:
    return {
        p.relative_to(cache).as_posix(): p.read_bytes() for p in cache.rglob("*.json")
    }


def test_v3_corrects_prose_without_changing_authority_or_private_gold() -> None:
    old = v2.build_manifest()
    new = v3.build_manifest()
    assert (
        old.fingerprint
        == "a46ef5d4b2bc0e9a7246bbb07d7d68ec277f4584499b2bdc70c9957cf2d639b3"
    )
    assert new.fingerprint != old.fingerprint
    assert audit_relation_endpoints(new) == []
    for prior, owner in zip(old.owners, new.owners, strict=True):
        assert owner.entities == prior.entities and owner.queries == prior.queries
        for old_m, new_m in zip(prior.memories, owner.memories, strict=True):
            assert old_m.model_copy(update={"semantic_brief": ""}) == new_m.model_copy(
                update={"semantic_brief": ""}
            )
            if old_m.surface_key == "memory-competing-second":
                assert "指向共享别名机构" in old_m.semantic_brief
                assert "指向共享别名机构" not in new_m.semantic_brief
                assert new_m.target_entity_key in new_m.semantic_brief
            else:
                assert old_m == new_m
        for a, b in zip(
            split_owner_authoring_batches(prior),
            split_owner_authoring_batches(owner),
            strict=True,
        ):
            assert v3._surface_compatible(a, b)
    batch = split_owner_authoring_batches(new.owners[0])[0]
    changed = batch.model_copy(
        update={
            "memories": [
                batch.memories[0].model_copy(update={"authority": "agent_output"}),
                *batch.memories[1:],
            ]
        }
    )
    assert not v3._surface_compatible(batch, changed)


def test_request_has_explicit_name_and_reference_contract_without_private_ids() -> None:
    batch = split_owner_authoring_batches(v3.build_manifest().owners[0])[0]
    request = v3.build_authoring_request(batch, inherited_memory_texts=("参考文本",))
    assert request.input["output_contract"] == {
        "entity_count": 19,
        "distinct_entity_name_count": 19,
        "memory_count": 96,
        "query_count": 10,
        "inherited_texts_are_reference_only": True,
    }
    raw = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    assert batch.scope not in raw and batch.owner_key not in raw
    assert all(m.memory_id not in raw for m in batch.memories)
    assert all(q.case_id not in raw for q in batch.queries)
    assert '"answerable"' not in raw and '"corpus_role"' not in raw
    assert (
        request.input["authoring_nonce"]
        != v2.build_authoring_request_v2(batch).input["authoring_nonce"]
    )


@pytest.mark.asyncio
async def test_replay_keeps_exact_accepted_attempts_and_failed_cache_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authored, review, cache = await _stopped_parent(tmp_path, monkeypatch)
    before = _inventory(cache)
    monkeypatch.delenv("DOPPEL_API_KEY")
    seeds, parents = v3.load_parent_seed(cache, authored, review)
    assert len(seeds) == 33
    snapshot = parents["revision_v2"]
    assert snapshot["replayed_failure_counts"] == {
        "duplicate_entity_name": 7,
        "surface_collision": 1,
    }
    assert snapshot["accepted_attempts_by_batch"]["owner-blind-01:01"] == 2
    assert snapshot["accepted_attempts_by_batch"]["owner-blind-02:01"] == 2
    assert snapshot["seed_semantic_review_pending"] is True
    assert "owner-blind-10:01" not in seeds
    assert snapshot["provider_cache_entry_count"] == 17
    # Zero budget must not send a new call, even with no API key.
    assert await v3.run(_v3_args(tmp_path, authored, review, cache, "author", 0)) == 0
    progress = json.loads((tmp_path / "v3-author-progress.json").read_text("utf-8"))
    assert progress["seed_batch_count"] == 33
    assert progress["last_invocation"]["provider_calls"] == 0
    assert progress["completed_batch_count"] == 33
    assert _inventory(cache) == before
    assert not (tmp_path / "v3-author-output.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault", ["state_binding", "attempt", "envelope", "unexplained_file"]
)
async def test_parent_corruption_blocks_continuation_before_new_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    authored, review, cache = await _stopped_parent(tmp_path, monkeypatch)
    path = cache / acquire.STATE_NAME
    raw = json.loads(path.read_text("utf-8"))
    if fault == "state_binding":
        raw["binding_sha256"] = "wrong"
    elif fault == "attempt":
        raw["accepted_attempts_by_batch"]["owner-blind-01:01"] = 1
    else:
        file = next((cache / PROVIDER_OUTPUT_CACHE_NAMESPACE).glob("*/*.json"))
        if fault == "envelope":
            envelope = json.loads(file.read_text("utf-8"))
            envelope["request_fingerprint"] = "wrong"
            file.write_text(json.dumps(envelope), "utf-8")
        else:
            (file.parent / "unexplained.json").write_bytes(file.read_bytes())
    path.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(
        ParentCacheIntegrityError if fault == "envelope" else ValueError
    ):
        v3.load_parent_seed(cache, authored, review)
    assert not (tmp_path / "v3-author-cache").exists()


@pytest.mark.asyncio
async def test_fifteen_new_heads_then_full_review_and_compile_with_unchanged_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authored, review, cache = await _stopped_parent(tmp_path, monkeypatch)
    before = _inventory(cache)
    monkeypatch.setattr(acquire, "OpenAICompatibleStructuredOutputModel", _FakeProvider)
    monkeypatch.setattr(
        v2.review_runner, "OpenAICompatibleStructuredOutputModel", _FakeProvider
    )
    assert await v3.run(_v3_args(tmp_path, authored, review, cache, "author", 1)) == 0
    assert await v3.run(_v3_args(tmp_path, authored, review, cache, "author", 14)) == 0
    a = json.loads((tmp_path / "v3-author-output.json").read_text("utf-8"))
    assert a["acquisition"]["provider_calls"] == 15
    assert a["acquisition"]["completed_batch_count"] == 48
    assert a["parents"]["revision_v2"]["provider_calls"] == 17
    assert a["review_complete"] is False and a["retrieval_opened"] is False
    assert await v3.run(_v3_args(tmp_path, authored, review, cache, "review", 48)) == 0
    r = json.loads((tmp_path / "v3-review-output.json").read_text("utf-8"))
    assert r["accepted"] is True and r["batch_count"] == 48
    assert r["acquisition"]["provider_calls"] == 48
    v2.compile_runner._validate_authored(v3.build_manifest(), a)
    v2.compile_runner._validate_review(
        v3.build_manifest(), r, acquire._sha256(tmp_path / "v3-author-output.json")
    )
    dataset = v2.compile_runner.compile_corpus(v3.build_manifest(), a)
    v2.compile_runner._validate_novel_surfaces(dataset)
    assert len(dataset.memories) == 4608 and len(dataset.queries) == 240
    assert before == _inventory(cache)
    r["accepted"] = False
    with pytest.raises(ValueError, match="accepted first semantic review"):
        v2.compile_runner._validate_review(
            v3.build_manifest(), r, acquire._sha256(tmp_path / "v3-author-output.json")
        )


@pytest.mark.asyncio
async def test_duplicate_names_still_rejected_under_v3() -> None:
    batch = split_owner_authoring_batches(v3.build_manifest().owners[0])[0]
    raw = await _FakeProvider(None, api_key="fake").generate(
        v3.build_authoring_request(batch)
    )
    raw["entities"][1]["name"] = raw["entities"][0]["name"]
    with pytest.raises(ValueError, match="display names must be unique"):
        project_owner_surfaces(batch, raw)

"""Offline compiler gates for the blind evidence-rich retrieval corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import benchmarks.evidence_rich_blind_compile as compiler
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import split_owner_authoring_batches
from benchmarks.heterogeneous_retrieval_quality import HeterogeneousRetrievalDataset


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), "utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authored_payload() -> dict[str, Any]:
    manifest = build_manifest()
    return {
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
                    entity.entity_id: (
                        entity.required_display_name
                        if entity.required_display_name
                        else f"实体-{owner.owner_key}-{entity.surface_key}"
                    )
                    for entity in owner.entities
                },
                "memory_content_by_id": {
                    memory.memory_id: f"记忆-{owner.owner_key}-{memory.surface_key}"
                    for memory in owner.memories
                },
                "edge_fact_by_memory_id": {
                    memory.memory_id: (
                        f"关系-{owner.owner_key}-{memory.surface_key}"
                        if memory.relation_type
                        else ""
                    )
                    for memory in owner.memories
                },
                "query_text_by_case_id": {
                    query.case_id: f"问题-{owner.owner_key}-{query.surface_key}？"
                    for query in owner.queries
                },
            }
            for owner in manifest.owners
        ],
    }


def _accepted_review(authored_sha256: str) -> dict[str, Any]:
    manifest = build_manifest()
    batches = [
        batch
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(owner)
    ]
    return {
        "runner": "doppel.evidence-rich-blind-review.v1",
        "status": "reviewed_accepted",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": authored_sha256,
        "review_complete": True,
        "accepted": True,
        "issue_count": 0,
        "batch_count": 48,
        "batches": [
            {
                "batch_id": batch.batch_id,
                "owner_key": batch.owner_key,
                "reviewed_surface_count": len(
                    [*batch.entities, *batch.memories, *batch.queries]
                ),
                "reviewed_surface_keys_sha256": compiler._fingerprint(
                    sorted(
                        item.surface_key
                        for item in [
                            *batch.entities,
                            *batch.memories,
                            *batch.queries,
                        ]
                    )
                ),
                "issue_count": 0,
                "issues": [],
            }
            for batch in batches
        ],
        "auto_rewrite_performed": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
    }


def _args(tmp_path: Path, *, compile_enabled: bool = True) -> Any:
    values = [
        "--authored-surfaces",
        str(tmp_path / "authored.json"),
        "--review",
        str(tmp_path / "review.json"),
        "--output",
        str(tmp_path / "corpus.json"),
        "--report",
        str(tmp_path / "compile-report.json"),
    ]
    if compile_enabled:
        values.insert(0, "--compile")
    return compiler.parser().parse_args(values)


def _write_inputs(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    authored = _authored_payload()
    _write_json(tmp_path / "authored.json", authored)
    review = _accepted_review(_sha256(tmp_path / "authored.json"))
    _write_json(tmp_path / "review.json", review)
    return authored, review


def test_compile_builds_full_validated_heterogeneous_corpus(tmp_path: Path) -> None:
    authored, review = _write_inputs(tmp_path)
    manifest = build_manifest()
    compiler._validate_authored(manifest, authored)
    compiler._validate_review(manifest, review, _sha256(tmp_path / "authored.json"))

    dataset = compiler.compile_corpus(manifest, authored)
    compiler._validate_novel_surfaces(dataset)

    assert isinstance(dataset, HeterogeneousRetrievalDataset)
    assert len(dataset.scopes) == 24
    assert len(dataset.memories) == 4_608
    assert len(dataset.entities) == 384
    assert len(dataset.edges) == 240
    assert len(dataset.queries) == 240
    assert all(edge.memory_id for edge in dataset.edges)
    relation_queries = [
        query
        for query in dataset.queries
        if query.category in {"one_hop_relation", "two_hop_relation"}
    ]
    assert len(relation_queries) == 48
    assert all(query.entity_mentions for query in relation_queries)


def test_compile_cli_writes_unopened_corpus_and_hash_bound_report(
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path)

    assert compiler.run(_args(tmp_path)) == 0

    report = json.loads((tmp_path / "compile-report.json").read_text("utf-8"))
    corpus = HeterogeneousRetrievalDataset.model_validate_json(
        (tmp_path / "corpus.json").read_text("utf-8")
    )
    assert report["status"] == "compiled_unopened"
    assert report["corpus_sha256"] == _sha256(tmp_path / "corpus.json")
    assert report["corpus_fingerprint"] == corpus.fingerprint
    assert report["review_accepted"] is True
    assert report["retrieval_opened"] is False
    assert report["quality_metrics_available"] is False
    assert report["external_http_calls"] == 0
    assert report["provider_calls"] == 0


def test_compile_dry_run_allows_missing_inputs_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert compiler.run(_args(tmp_path, compile_enabled=False)) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "dry_run"
    assert plan["authored_surfaces_available"] is False
    assert plan["review_available"] is False
    assert plan["provider_calls"] == 0
    assert plan["retrieval_enabled"] is False
    assert not (tmp_path / "corpus.json").exists()


def test_compile_rejects_failed_review_and_preserves_no_output(tmp_path: Path) -> None:
    _, review = _write_inputs(tmp_path)
    review.update(status="reviewed_rejected", accepted=False, issue_count=1)
    _write_json(tmp_path / "review.json", review)

    with pytest.raises(ValueError, match="accepted first semantic review"):
        compiler.run(_args(tmp_path))
    assert not (tmp_path / "corpus.json").exists()


def test_compile_rejects_review_bound_to_different_authored_bytes(
    tmp_path: Path,
) -> None:
    authored, _ = _write_inputs(tmp_path)
    authored["extra-unreviewed-byte-change"] = True
    _write_json(tmp_path / "authored.json", authored)

    with pytest.raises(ValueError, match="not bound"):
        compiler.run(_args(tmp_path))
    assert not (tmp_path / "corpus.json").exists()


def test_compile_rejects_duplicate_surfaces_before_retrieval(tmp_path: Path) -> None:
    authored, _ = _write_inputs(tmp_path)
    first, second = authored["owners"][:2]
    first_text = next(iter(first["memory_content_by_id"].values()))
    second_key = next(iter(second["memory_content_by_id"]))
    second["memory_content_by_id"][second_key] = first_text
    _write_json(tmp_path / "authored.json", authored)
    _write_json(
        tmp_path / "review.json",
        _accepted_review(_sha256(tmp_path / "authored.json")),
    )

    with pytest.raises(ValueError, match="duplicate memory surface"):
        compiler.run(_args(tmp_path))
    assert not (tmp_path / "corpus.json").exists()


def test_compile_rejects_shared_name_that_violates_host_requirement(
    tmp_path: Path,
) -> None:
    authored, _ = _write_inputs(tmp_path)
    manifest = build_manifest()
    entity = next(
        item for item in manifest.owners[0].entities if item.shared_name_group
    )
    authored["owners"][0]["entity_names_by_id"][entity.entity_id] = "不一致的名称"
    _write_json(tmp_path / "authored.json", authored)
    _write_json(
        tmp_path / "review.json",
        _accepted_review(_sha256(tmp_path / "authored.json")),
    )

    with pytest.raises(ValueError, match="host requirement"):
        compiler.run(_args(tmp_path))


def test_compile_rejects_incomplete_review_coverage(tmp_path: Path) -> None:
    _, review = _write_inputs(tmp_path)
    review["batches"][0]["reviewed_surface_count"] -= 1
    _write_json(tmp_path / "review.json", review)

    with pytest.raises(ValueError, match="coverage count mismatch"):
        compiler.run(_args(tmp_path))


def test_compile_rejects_review_that_claims_an_automatic_rewrite(
    tmp_path: Path,
) -> None:
    _, review = _write_inputs(tmp_path)
    review["auto_rewrite_performed"] = True
    _write_json(tmp_path / "review.json", review)

    with pytest.raises(ValueError, match="must not rewrite"):
        compiler.run(_args(tmp_path))


def test_compile_rejects_internal_nonce_leaked_into_surface(tmp_path: Path) -> None:
    authored, _ = _write_inputs(tmp_path)
    owner = build_manifest().owners[0]
    batch = split_owner_authoring_batches(owner)[0]
    nonce = compiler.build_authoring_request(batch).input["authoring_nonce"]
    memory_id = owner.memories[0].memory_id
    authored["owners"][0]["memory_content_by_id"][memory_id] = f"泄漏-{nonce}"
    _write_json(tmp_path / "authored.json", authored)
    _write_json(
        tmp_path / "review.json",
        _accepted_review(_sha256(tmp_path / "authored.json")),
    )

    with pytest.raises(ValueError, match="variation nonce"):
        compiler.run(_args(tmp_path))

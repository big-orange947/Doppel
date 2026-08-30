"""Guards that keep quality fixtures outside product retrieval behavior."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from benchmarks.memory_quality import (
    build_metamorphic_memory_quality_dataset,
    load_memory_quality_dataset,
    run_memory_quality_benchmark,
)
from benchmarks.quality_suite import load_memory_quality_suite

_GENERIC_SUBSTITUTIONS = {
    "香菜": "茴香",
    "蓝色": "紫色",
    "绿色": "黄色",
    "花生": "芒果",
    "年糕": "团子",
    "豆包": "麻薯",
    "上海": "澜州",
    "北京": "雾城",
    "咖啡": "可乐",
    "AB型": "MN型",
}


def test_runtime_package_does_not_import_repository_benchmarks() -> None:
    violations: list[str] = []
    for path in sorted(Path("doppel_memory").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported = [node.module]
            if any(name == "benchmarks" or name.startswith("benchmarks.") for name in imported):
                violations.append(f"{path}:{node.lineno}")

    assert violations == []


def test_metamorphic_dataset_changes_language_without_changing_evidence_graph() -> None:
    original = load_memory_quality_dataset()
    transformed = build_metamorphic_memory_quality_dataset(
        original,
        _GENERIC_SUBSTITUTIONS,
        variant="fictional-entities-v1",
    )

    assert transformed.name.endswith(".metamorphic.fictional-entities-v1")
    assert transformed.fingerprint != original.fingerprint
    assert [scope.model_dump() for scope in transformed.scopes] == [
        scope.model_dump() for scope in original.scopes
    ]

    for before, after in zip(original.cases, transformed.cases, strict=True):
        assert before.name == after.name
        assert before.category == after.category
        assert [
            (message.message_id, message.scope, message.actor, message.at)
            for message in before.messages
        ] == [
            (message.message_id, message.scope, message.actor, message.at)
            for message in after.messages
        ]
        assert [
            (
                memory.memory_key,
                memory.scope,
                memory.kind,
                memory.subject,
                memory.status,
                memory.evidence_message_ids,
            )
            for memory in before.gold_memories
        ] == [
            (
                memory.memory_key,
                memory.scope,
                memory.kind,
                memory.subject,
                memory.status,
                memory.evidence_message_ids,
            )
            for memory in after.gold_memories
        ]
        assert [
            (
                query.name,
                query.scopes,
                query.required_evidence,
                query.forbidden_message_ids,
                query.limit,
            )
            for query in before.queries
        ] == [
            (
                query.name,
                query.scopes,
                query.required_evidence,
                query.forbidden_message_ids,
                query.limit,
            )
            for query in after.queries
        ]

    rendered = json.dumps(transformed.model_dump(mode="json"), ensure_ascii=False)
    assert all(source not in rendered for source in _GENERIC_SUBSTITUTIONS)
    assert all(target in rendered for target in _GENERIC_SUBSTITUTIONS.values())


@pytest.mark.parametrize(
    ("replacements", "message"),
    [
        ({}, "must not be empty"),
        ({"不存在的词": "替换词"}, "absent from quality text"),
        ({"上海": "上海"}, "must change"),
        ({"上海": "澜州", "北京": "澜州"}, "targets must be unique"),
    ],
)
def test_metamorphic_dataset_rejects_invalid_transformations(
    replacements: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_metamorphic_memory_quality_dataset(
            load_memory_quality_dataset(), replacements, variant="invalid-v1"
        )


async def test_deterministic_quality_metrics_generalize_after_entity_substitution() -> (
    None
):
    original = await run_memory_quality_benchmark(load_memory_quality_dataset())
    transformed = await run_memory_quality_benchmark(
        build_metamorphic_memory_quality_dataset(
            load_memory_quality_dataset(),
            _GENERIC_SUBSTITUTIONS,
            variant="fictional-entities-v1",
        )
    )

    quality_keys = {
        "query_count",
        "required_query_count",
        "abstention_query_count",
        "macro_evidence_recall",
        "macro_candidate_precision",
        "mean_reciprocal_rank",
        "abstention_accuracy",
        "forbidden_candidate_hits",
        "scope_leakage_count",
        "redundant_relevant_candidates",
        "average_candidates",
        "average_context_characters",
    }
    original_baselines = {item["name"]: item for item in original["baselines"]}
    transformed_baselines = {
        item["name"]: item for item in transformed["baselines"]
    }
    assert transformed_baselines.keys() == original_baselines.keys()
    for name, before in original_baselines.items():
        after = transformed_baselines[name]
        assert {key: before["aggregate"][key] for key in quality_keys} == {
            key: after["aggregate"][key] for key in quality_keys
        }
        assert after["correctness"] == before["correctness"]


def test_v2_quality_suite_is_explicitly_draft_and_below_publication_gates() -> None:
    first = load_memory_quality_suite()
    second = load_memory_quality_suite()
    audit = first.audit()

    assert first.fingerprint == second.fingerprint
    assert first.manifest.name == "doppel.personal-memory-retrieval.zh.v2"
    assert len(first.members) == 1
    assert len(first.variants) == 1
    assert audit["status"] == "draft"
    assert audit["publication_ready"] is False
    assert audit["partitions"] == {"dev": 1, "heldout": 0, "adversarial": 0}
    assert audit["counts"] == {
        "cases": 10,
        "messages": 34,
        "queries": 11,
        "users": 2,
        "metamorphic_variants": 1,
    }
    assert "missing required partitions: ['adversarial', 'heldout']" in audit["errors"]
    assert "suite status is draft" in audit["errors"]


def test_v2_quality_suite_rejects_dataset_path_escape(tmp_path: Path) -> None:
    manifest = {
        "suite_version": 2,
        "name": "escape-test",
        "members": [
            {
                "member_id": "escape",
                "partition": "dev",
                "dataset": "../outside.json",
            }
        ],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes the suite directory"):
        load_memory_quality_suite(path)

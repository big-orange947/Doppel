"""Diagnostic selection cannot change gold, remove distractors, or grant acceptance."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_evidence_rich_blind_repair_inventory import make_inputs

from benchmarks import evidence_rich_blind_diagnostic as diagnostic
from benchmarks.evidence_rich_blind_compile import _validate_review, compile_corpus
from benchmarks.heterogeneous_retrieval_live import _oracle_path_plan, _record
from doppel_memory.models import MemoryScope
from doppel_memory.relation_path_retrieval import RelationPathCandidateOntologyError


@pytest.fixture(scope="module")
def parent() -> Any:
    manifest, authored, _ = make_inputs()
    return compile_corpus(manifest, authored)


def test_fixed_selection_preserves_every_background_and_retained_gold(
    parent: Any,
) -> None:
    before = parent.model_dump(mode="json")
    subset = diagnostic.build_subset(parent)
    assert len(subset.queries) == 208
    assert len(subset.scopes) == 24
    assert len(subset.memories) == 4608
    for field in ("memories", "entities", "edges", "scopes", "relation_types"):
        assert getattr(parent, field) == getattr(subset, field)
    cases = {q.case_id: q for q in parent.queries}
    assert all(cases[q.case_id] == q for q in subset.queries)
    assert parent.model_dump(mode="json") == before
    assert not subset.publication_ready
    assert "NOT passed" in subset.description
    assert subset.requirements["min_queries"] == 208
    assert subset.requirements["min_category_episode_count"] == 0
    assert parent.requirements["min_queries"] == 240


def test_exclusions_predeclared_by_semantics_not_scores() -> None:
    assert len(diagnostic.EXCLUSIONS) == 32
    assert len(diagnostic.KNOWN_ISSUES) == 8
    assert (
        sum(
            reason == "count_completeness_audit_pending"
            for reason in diagnostic.EXCLUSIONS.values()
        )
        == 24
    )


def test_oracle_control_uses_declared_host_ontology(parent: Any) -> None:
    scope = MemoryScope(user_id="owner-01:diagnostic", agent_id="eval")
    for query in parent.queries:
        plan = _oracle_path_plan(
            query, scope, allowed_relation_types=parent.relation_types
        )
        if query.required_routes:
            assert plan.routes[0].steps == query.required_routes[0]
        else:
            assert not plan.routes
    query = next(q for q in parent.queries if q.required_routes)
    with pytest.raises(RelationPathCandidateOntologyError):
        _oracle_path_plan(query, scope, allowed_relation_types=())


def test_formal_rejected_review_is_still_rejected() -> None:
    manifest, _, review = make_inputs()
    with pytest.raises(ValueError, match="accepted first semantic review"):
        _validate_review(manifest, review, "authored-test-sha")


def test_identity_projection_uses_explicit_owner_not_prefix(parent: Any) -> None:
    for item in parent.memories:
        owner_id = parent.scopes[item.scope].user_id
        scope = MemoryScope(user_id=f"{owner_id}:run", agent_id="eval")
        record = _record(item, scope, owner_subject_id=owner_id)
        assert record.metadata["subject"] == (
            "owner" if item.subject_id == owner_id else "contact"
        )
        assert record.metadata["subject_id"] == (
            scope.user_id if item.subject_id == owner_id else item.subject_id
        )
    item = parent.memories[0].model_copy(update={"subject_id": "owner-Foreign"})
    record = _record(item, scope, owner_subject_id="arbitrary-account-id")
    assert record.metadata["subject"] == "contact"
    assert record.metadata["subject_id"] == "owner-Foreign"


def test_parent_with_missing_exclusion_rejected(parent: Any) -> None:
    changed = parent.model_copy(update={"queries": parent.queries[:-1]})
    with pytest.raises(ValueError, match="fixed 24-owner parent"):
        diagnostic.build_subset(changed)


def test_changed_count_population_rejected(parent: Any) -> None:
    queries = [
        q.model_copy(update={"intent": "lookup"}) if q.intent == "count" else q
        for q in parent.queries
    ]
    with pytest.raises(ValueError, match="count population"):
        diagnostic.build_subset(parent.model_copy(update={"queries": queries}))


def test_artifact_write_is_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    diagnostic.write_new(path, {"a": 1})
    with pytest.raises(FileExistsError):
        diagnostic.write_new(path, {"a": 2})
    assert json.loads(path.read_text("utf-8")) == {"a": 1}


@pytest.mark.parametrize(
    "database,user", [("user_data", "postgres"), ("doppel_ablation", "user")]
)
def test_non_benchmark_database_cannot_be_reset(
    monkeypatch: Any, database: str, user: str
) -> None:
    def inspect(name: str, port: str) -> Any:
        return {}, {
            "POSTGRES_DB": database,
            "POSTGRES_USER": user,
            "POSTGRES_PASSWORD": "fake-secret",
            "NEO4J_AUTH": "neo4j/fake-secret",
        }

    monkeypatch.setattr(diagnostic, "inspect_backend", inspect)
    with pytest.raises(RuntimeError, match="non-benchmark"):
        diagnostic.local_credentials()


def test_credentials_returned_only_in_memory(monkeypatch: Any) -> None:
    def inspect(name: str, port: str) -> Any:
        return {"name": name, "healthy": True}, {
            "POSTGRES_DB": "doppel_ablation",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "fake-pg-secret",
            "NEO4J_AUTH": "neo4j/fake-neo-secret",
        }

    monkeypatch.setattr(diagnostic, "inspect_backend", inspect)
    pg, neo, report = diagnostic.local_credentials()
    assert pg == "fake-pg-secret" and neo == "fake-neo-secret"
    assert "secret" not in json.dumps(report)


def test_frozen_selection_rejects_config_gold_or_code_changes(
    parent: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    subset = diagnostic.build_subset(parent)
    corpus = tmp_path / "corpus.json"
    diagnostic.write_new(corpus, subset.model_dump(mode="json"))
    monkeypatch.setattr(diagnostic, "CORPUS", corpus)
    selection = {
        "corpus_sha256": diagnostic.sha(corpus),
        "corpus_fingerprint": subset.fingerprint,
        "selected_case_ids": [q.case_id for q in subset.queries],
        "excluded_case_ids_with_reasons": diagnostic.EXCLUSIONS,
        "comparison_profiles": diagnostic.COMPARISON,
        "runtime_config": diagnostic.CONFIG,
        "implementation_hashes": diagnostic.code_hashes(),
        "source_hashes": {k: d for k, (_, d) in diagnostic.SOURCES.items()},
        "full_corpus_review_accepted": False,
        "publication_ready": False,
    }
    diagnostic.validate_frozen(selection, subset)
    for key in (
        "runtime_config",
        "implementation_hashes",
        "selected_case_ids",
        "full_corpus_review_accepted",
    ):
        changed = deepcopy(selection)
        changed[key] = True
        with pytest.raises(ValueError, match="frozen diagnostic"):
            diagnostic.validate_frozen(changed, subset)

"""Tests for the v0.9 personal retrieval ablation benchmark.

All tests are offline: they exercise dataset validation, evaluation metrics,
guard behaviour, metamorphic substitution, structural unavailability handling,
and schema conformance. Live Neo4j/pgvector profiles are only exercised by
``--require-live-*`` CLI runs or when the respective services are configured.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from benchmarks.personal_retrieval_ablation import (
    ALL_PROFILES,
    PLANNER_MODE_ORACLE,
    PLANNER_MODE_REPORT,
    PROFILE_DIRECT,
    PROFILE_EXECUTION,
    PROFILE_MAIN,
    PROFILE_RELATION,
    PROFILE_RELATION_BASE,
    PROFILE_RELATION_RERANKED,
    SOURCE_GRAPH,
    SOURCE_VECTOR,
    AblationDataset,
    AblationQuery,
    BenchmarkReportPlanner,
    _aggregate,
    _direct_scan,
    _evaluate_result,
    _FastEmbedRelationReranker,
    _memory_record,
    _run_case,
    _run_profiles,
    _safety_metrics,
    _sigmoid,
    apply_variant,
    load_ablation_dataset,
    substitute,
)
from doppel_memory import (
    DeterministicPersonalMemoryQueryPlanner,
    InMemoryStore,
    MemoryScope,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
    RelationCandidate,
    RelationRerankItem,
    RelationRerankRequest,
)
from doppel_memory.models import utc_now

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "personal-retrieval-ablation-result.schema.json"
)

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "datasets"
    / "personal-retrieval-ablation-zh-v1.json"
)
RELATION_DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "datasets"
    / "personal-relation-ablation-zh-v1.json"
)

NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")


def _dataset() -> AblationDataset:
    return load_ablation_dataset(DATASET_PATH)


def _query(
    query_id: str = "q-test",
    scopes: list[str] | None = None,
    required: list[str] | None = None,
    forbidden: list[str] | None = None,
    expected_abstain: bool = False,
    expected_ambiguous: bool = False,
    as_of: str | None = None,
) -> AblationQuery:
    return AblationQuery(
        query_id=query_id,
        query="测试查询",
        scopes=scopes or ["u1"],
        now=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        intent="current",
        as_of=datetime.fromisoformat(as_of) if as_of else None,
        required_memory_ids=required or [],
        forbidden_memory_ids=forbidden or [],
        expected_abstain=expected_abstain,
        expected_ambiguous=expected_ambiguous,
    )


def _hit(
    memory_id: str,
    *,
    scope: MemoryScope,
    state: str = "confirmed",
    valid_from: str = "2025-01-01T00:00:00Z",
    valid_to: str | None = None,
    evidence: bool = True,
    reasons: list[str] | None = None,
) -> SimpleNamespace:
    record = _memory_record(
        SimpleNamespace(
            memory_id=memory_id,
            scope="u1",
            content=f"{memory_id} content",
            subject="owner",
            subject_id=scope.user_id,
            authority="human_self",
            personal_memory_type="fact",
            temporal_status="current",
            state=state,
            valid_from=datetime.fromisoformat(valid_from),
            valid_to=datetime.fromisoformat(valid_to) if valid_to else None,
            topic_key="t",
            event_key="",
            revision_kind="",
            tags=["personal-memory"],
            evidence=[
                SimpleNamespace(message_id="e1", at=datetime(2026, 1, 1, tzinfo=UTC))
            ],
        ),
        scope,
        utc_now(),
    )
    return SimpleNamespace(
        record=record,
        score=1.0,
        lexical_score=0.5,
        semantic_score=0.5,
        effective_at=record.created_at,
        reasons=reasons or ["exact_scope", "lexical_match"],
    )


class RelationRerankerHarnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_fastembed_harness_batches_text_and_normalizes_logits(self) -> None:
        class FakeCrossEncoder:
            def __init__(self) -> None:
                self.calls: list[tuple[str, list[str], int]] = []

            def rerank(self, query, documents, *, batch_size):
                materialized = list(documents)
                self.calls.append((query, materialized, batch_size))
                return [0.0, 2.0, -2.0]

        scorer = _FastEmbedRelationReranker("fixture/model", batch_size=7)
        fake = FakeCrossEncoder()
        scorer._model = fake
        request = RelationRerankRequest(
            query_text="东西在哪里？",
            relation_hints=["位置"],
            items=[
                RelationRerankItem(
                    item_id="edge-1", relation_type="LOCATED_AT", fact="在书房"
                ),
                RelationRerankItem(
                    item_id="edge-2", relation_type="HELD_BY", fact="由小王保管"
                ),
                RelationRerankItem(
                    item_id="edge-3", relation_type="LIKES", fact="喜欢红茶"
                ),
            ],
        )

        scores = await scorer.rerank(request)

        self.assertEqual(
            [item.item_id for item in scores], ["edge-1", "edge-2", "edge-3"]
        )
        self.assertAlmostEqual(scores[0].score, 0.5)
        self.assertAlmostEqual(scores[1].score, _sigmoid(2.0))
        self.assertAlmostEqual(scores[2].score, _sigmoid(-2.0))
        self.assertEqual(
            fake.calls,
            [
                (
                    "东西在哪里？",
                    [
                        "LOCATED_AT\n在书房",
                        "HELD_BY\n由小王保管",
                        "LIKES\n喜欢红茶",
                    ],
                    7,
                )
            ],
        )
        self.assertEqual(scorer.name, "fastembed-cross-encoder:fixture/model")

    async def test_fastembed_harness_rejects_invalid_provider_output(self) -> None:
        class WrongLengthCrossEncoder:
            def rerank(self, query, documents, *, batch_size):
                del query, documents, batch_size
                return []

        scorer = _FastEmbedRelationReranker("fixture/model")
        scorer._model = WrongLengthCrossEncoder()
        request = RelationRerankRequest(
            query_text="位置",
            items=[
                RelationRerankItem(
                    item_id="edge-1", relation_type="LOCATED_AT", fact="在书房"
                )
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "different number"):
            await scorer.rerank(request)

    async def test_reranked_profile_is_unavailable_without_a_real_scorer(self) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        report = await _run_profiles(
            store=InMemoryStore(),
            scopes=scopes,
            dataset=dataset,
            profiles=("lexical_relation_reranked",),
            semantic_by_source={},
            relation_index=None,
            relation_reranked_index=None,
            graph=None,
            planner_modes=(PLANNER_MODE_ORACLE,),
        )

        profile = report["profiles"]["oracle"]["lexical_relation_reranked"]
        self.assertTrue(profile["unavailable"])
        self.assertIn("relation_reranker", profile["reason"])


class DatasetTest(unittest.TestCase):
    def test_relation_dataset_has_edge_gold_and_adversarial_coverage(self) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        self.assertEqual(len(dataset.queries), 65)
        self.assertEqual(len(dataset.fixtures), 28)
        self.assertGreaterEqual(len(dataset.scopes), 5)
        self.assertTrue(
            all(
                query.entity_mentions or query.relation_hints
                for query in dataset.queries
            )
        )
        self.assertGreaterEqual(
            sum(item.relation is not None for item in dataset.fixtures),
            10,
        )
        self.assertTrue(
            any(query.category == "wrong_relation" for query in dataset.queries)
        )
        self.assertTrue(
            any(query.category == "scope_collision" for query in dataset.queries)
        )
        self.assertGreaterEqual(
            sum(
                query.category == "semantic_paraphrase"
                for query in dataset.queries
            ),
            8,
        )
        self.assertGreaterEqual(
            sum(
                query.category == "same_entity_multi_relation"
                for query in dataset.queries
            ),
            8,
        )
        self.assertTrue(
            any(query.category == "expired_relation" for query in dataset.queries)
        )
        partitions = {query.partition for query in dataset.queries}
        self.assertEqual(partitions, {"dev", "heldout", "adversarial"})

    def test_dataset_model_rejects_duplicate_gold_ids(self) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        duplicate_fixture = dataset.model_dump(mode="python")
        duplicate_fixture["fixtures"].append(duplicate_fixture["fixtures"][0])
        with self.assertRaisesRegex(ValueError, "duplicate fixture IDs"):
            AblationDataset.model_validate(duplicate_fixture)

        duplicate_query = dataset.model_dump(mode="python")
        duplicate_query["queries"].append(duplicate_query["queries"][0])
        duplicate_query["requirements"]["min_queries"] += 1
        with self.assertRaisesRegex(ValueError, "duplicate query IDs"):
            AblationDataset.model_validate(duplicate_query)

    def test_relation_dataset_validator_rejects_missing_anchor(self) -> None:
        from benchmarks.personal_retrieval_ablation import validate_dataset_semantics

        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        broken = dataset.queries[0].model_copy(
            update={"entity_mentions": [], "relation_hints": []}
        )
        failures = validate_dataset_semantics(
            dataset.model_copy(update={"queries": [broken, *dataset.queries[1:]]})
        )
        self.assertTrue(any("entity or relation anchor" in item for item in failures))

    def test_dataset_meets_first_version_gates(self) -> None:
        dataset = _dataset()
        self.assertGreaterEqual(len(dataset.queries), 30)
        self.assertGreaterEqual(len(dataset.scopes), 5)
        partition_counts = {
            name: sum(1 for item in dataset.queries if item.partition == name)
            for name in ("dev", "heldout", "adversarial", "deferred_cross_subject")
        }
        for name in ("dev", "heldout", "adversarial"):
            self.assertGreater(partition_counts[name], 0, name)
        self.assertFalse(dataset.frozen)
        self.assertFalse(dataset.publication_ready)

    def test_all_fixtures_have_required_fields(self) -> None:
        dataset = _dataset()
        for item in dataset.fixtures:
            self.assertTrue(item.memory_id)
            self.assertTrue(item.content)
            self.assertTrue(item.scope in dataset.scopes)
            self.assertTrue(item.authority)
            self.assertTrue(item.personal_memory_type)
            self.assertTrue(item.state)
            self.assertTrue(any(tag == "personal-memory" for tag in item.tags))
            self.assertTrue(item.evidence)

    def test_every_query_has_scopes_and_labels(self) -> None:
        dataset = _dataset()
        for item in dataset.queries:
            self.assertTrue(item.query_id)
            self.assertTrue(item.query)
            self.assertTrue(item.scopes)
            self.assertTrue(item.intent)
            self.assertIn(
                item.partition,
                ("dev", "heldout", "adversarial", "deferred_cross_subject"),
            )
            self.assertTrue(not item.expected_abstain or not item.required_memory_ids)

    def test_fingerprint_is_stable(self) -> None:
        dataset = _dataset()
        self.assertEqual(dataset.fingerprint, _dataset().fingerprint)

    def test_profile_names_are_exact(self) -> None:

        self.assertEqual(
            PROFILE_MAIN,
            ("lexical", "lexical_vector", "lexical_graph", "lexical_vector_graph"),
        )
        self.assertEqual(
            PROFILE_DIRECT,
            ("vector_direct", "graph_direct", "composite_direct"),
        )
        self.assertEqual(
            PROFILE_RELATION_BASE,
            ("lexical_relation", "lexical_vector_relation"),
        )
        self.assertEqual(
            PROFILE_RELATION_RERANKED,
            (
                "lexical_relation_reranked",
                "lexical_vector_relation_reranked",
            ),
        )
        self.assertEqual(
            PROFILE_RELATION,
            (*PROFILE_RELATION_BASE, *PROFILE_RELATION_RERANKED),
        )
        self.assertEqual(PROFILE_EXECUTION, (*PROFILE_MAIN, *PROFILE_RELATION))
        self.assertEqual(tuple(ALL_PROFILES), (*PROFILE_EXECUTION, *PROFILE_DIRECT))

    def test_report_schema_validates(self) -> None:
        import pydantic

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        report = self._minimal_report()
        # Structural conformance without an extra jsonschema dependency.
        self.assertIn("required", schema)
        for key in schema["required"]:
            self.assertIn(key, report, key)
        self.assertIn(report["runner"], schema["properties"]["runner"]["enum"])
        report_keys = set(report["profiles"]["deterministic"]["lexical"])
        schema_required = set(schema["$defs"]["profile"]["required"])
        self.assertTrue(
            schema_required.issubset(report_keys), schema_required - report_keys
        )
        pydantic.TypeAdapter(dict).validate_python(report)

    @staticmethod
    def _minimal_report() -> dict:
        return {
            "runner": "doppel.personal-retrieval-ablation.v1",
            "dataset": {
                "name": "n",
                "version": "1",
                "status": "draft",
                "frozen": False,
                "publication_ready": False,
                "fingerprint": "f" * 64,
                "memory_count": 1,
                "query_count": 1,
                "partition_counts": {
                    "dev": 1,
                    "heldout": 1,
                    "adversarial": 1,
                    "deferred_cross_subject": 1,
                },
            },
            "environment": {"python": "3", "platform": "p"},
            "runtime": {
                "store": {"available": True},
                "vector": {"available": False, "reason": "x"},
                "graph": {"available": False, "reason": "x"},
            },
            "planner_modes": ["deterministic", "oracle"],
            "profiles": {
                "deterministic": {
                    "lexical": {
                        "query_count": 1,
                        "error_count": 0,
                        "recall_at_1": 0.0,
                        "recall_at_5": 0.0,
                        "mrr": 0.0,
                        "required_evidence_recall": 0.0,
                        "forbidden_hit_count": 0,
                        "scope_leakage_count": 0,
                        "temporal_violation_count": 0,
                        "provenance_failure_count": 0,
                        "abstention_accuracy": 1.0,
                        "ambiguity_accuracy": 1.0,
                        "count_accuracy": 1.0,
                        "latency_ms": {"p50": 1, "p95": 2, "max": 3},
                        "contribution": {
                            "vector": 0,
                            "graph": 0,
                            "both": 0,
                            "relation": 0,
                            "relation_reranker": 0,
                        },
                    }
                },
                "oracle": {
                    "lexical": {
                        "query_count": 1,
                        "error_count": 0,
                        "recall_at_1": 0.0,
                        "recall_at_5": 0.0,
                        "mrr": 0.0,
                        "required_evidence_recall": 0.0,
                        "forbidden_hit_count": 0,
                        "scope_leakage_count": 0,
                        "temporal_violation_count": 0,
                        "provenance_failure_count": 0,
                        "abstention_accuracy": 1.0,
                        "ambiguity_accuracy": 1.0,
                        "count_accuracy": 1.0,
                        "latency_ms": {"p50": 1, "p95": 2, "max": 3},
                        "contribution": {
                            "vector": 0,
                            "graph": 0,
                            "both": 0,
                            "relation": 0,
                            "relation_reranker": 0,
                        },
                    }
                },
            },
            "diagnostics": {},
            "comparisons": {},
            "hard_gates": {
                "planner_failures": [],
                "retrieval_failures": [],
                "security_failures": [],
                "fixture_validation_failures": [],
            },
            "hard_gates_by_profile": {
                "deterministic": {
                    "lexical": {
                        "planner_failures": [],
                        "retrieval_failures": [],
                        "security_failures": [],
                        "fixture_validation_failures": [],
                    }
                },
                "oracle": {
                    "lexical": {
                        "planner_failures": [],
                        "retrieval_failures": [],
                        "security_failures": [],
                        "fixture_validation_failures": [],
                    }
                },
            },
            "cases": [],
            "deferred_queries": [],
            "graph_final_hit_attribution": {"available": False},
            "metamorphic": {},
            "reproducibility": {
                "output_path": "report.json",
                "command": "python -m benchmark",
                "commit_hash": "a" * 40,
                "planner_modes": ["oracle", "deterministic"],
                "requested_profiles": ["lexical"],
                "gate_profiles": [],
                "executed_profiles": ["oracle:lexical"],
                "unavailable_profiles": [],
                "dataset_fingerprint": "f" * 64,
                "canonical_payload_sha256": "c" * 64,
                "file_sha256_sidecar": "report.json.sha256",
            },
            "elapsed_seconds": 1.0,
            "doppel_version": "0.9",
            "generated_at": "2026-08-30T00:00:00Z",
            "suite_fingerprint": "f" * 64,
        }


class EvaluationTest(unittest.IsolatedAsyncioTestCase):
    async def test_exact_scope_identity_reports_leakage(self) -> None:
        scope = MemoryScope(user_id="user-linz", agent_id="echo")
        foreign_scope = MemoryScope(user_id="user-wangv", agent_id="echo")
        hits = [
            _hit("m-ok", scope=scope),
            _hit("m-foreign", scope=foreign_scope),
        ]
        result = SimpleNamespace(
            plan=SimpleNamespace(intent="current", as_of=None),
            hits=hits,
            conflicts=[],
            matched_record_count=2,
            scanned_record_count=2,
            scanned_conflict_count=0,
            count=SimpleNamespace(status="not_requested", value=None),
            ambiguous=False,
            warnings=[],
        )
        case = _evaluate_result(
            result,
            _query(required=["m-ok"]),
            "lexical",
            1.0,
            allowed_scope_keys={scope.scope_key},
        )
        self.assertEqual(case["scope_leakage"], 1)

    async def test_same_memory_id_different_scope_not_deduplicated(self) -> None:
        # Exact (scope, memory_id) identity must keep u1 and u3 Python skills apart.
        dataset = _dataset()
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        store_dir = tempfile.mkdtemp(prefix="ablation-test-store-")
        from doppel_memory.sqlite_store import SQLiteStore

        store = SQLiteStore(database=str(Path(store_dir) / "s.sqlite3"))
        engine = PersonalMemoryQueryEngine(store)
        planner = DeterministicPersonalMemoryQueryPlanner()
        try:
            for item in dataset.fixtures:
                if item.memory_id not in {
                    "m-skill-python-u1",
                    "m-skill-python-u3",
                }:
                    continue
                record = _memory_record(item, scopes[item.scope], utc_now())
                await store.put(record)
            query = next(
                item
                for item in dataset.queries
                if item.query_id == "q-dev-adversarial-same-id-different-scope"
            )
            case = await _run_case(engine, planner, query, scopes, profile="lexical")
            self.assertIn("m-skill-python-u1", case["hits"])
            self.assertNotIn("m-skill-python-u3", case["hits"])
            self.assertEqual(case["scope_leakage"], 0)
        finally:
            await store.close()

    async def test_inactive_record_is_rejected(self) -> None:
        scope = MemoryScope(user_id="user-linz", agent_id="echo")
        hit = _hit("m-expired", scope=scope, state="expired")
        result = SimpleNamespace(
            plan=SimpleNamespace(intent="current", as_of=None),
            hits=[hit],
            conflicts=[],
            matched_record_count=1,
            scanned_record_count=1,
            scanned_conflict_count=0,
            count=SimpleNamespace(status="not_requested", value=None),
            ambiguous=False,
            warnings=[],
        )
        case = _evaluate_result(
            result,
            _query(expected_abstain=True),
            "lexical",
            1.0,
            allowed_scope_keys={scope.scope_key},
        )
        self.assertEqual(case["inactive_rejections"], 1)
        self.assertFalse(case["abstention_ok"])

    def test_asof_temporal_violation_detected(self) -> None:
        scope = MemoryScope(user_id="user-linz", agent_id="echo")
        hit = _hit(
            "m-future",
            scope=scope,
            valid_from="2027-01-01T00:00:00Z",
        )
        result = SimpleNamespace(
            plan=SimpleNamespace(
                intent="as_of", as_of=datetime(2026, 6, 15, tzinfo=UTC)
            ),
            hits=[hit],
            conflicts=[],
            matched_record_count=1,
            scanned_record_count=1,
            scanned_conflict_count=0,
            count=SimpleNamespace(status="not_requested", value=None),
            ambiguous=False,
            warnings=[],
        )
        case = _evaluate_result(
            result,
            _query(as_of="2026-06-15T00:00:00Z"),
            "lexical",
            1.0,
            allowed_scope_keys={scope.scope_key},
            mode=PLANNER_MODE_ORACLE,
        )
        self.assertEqual(case["temporal_violations"], 1)

    def test_semantic_source_reasons_parsed(self) -> None:
        scope = MemoryScope(user_id="user-linz", agent_id="echo")
        hit = _hit(
            "m-both",
            scope=scope,
            reasons=[
                "lexical_match",
                f"semantic_source:{SOURCE_VECTOR}",
                f"semantic_source:{SOURCE_GRAPH}",
            ],
        )
        result = SimpleNamespace(
            plan=SimpleNamespace(intent="current", as_of=None),
            hits=[hit],
            conflicts=[],
            matched_record_count=1,
            scanned_record_count=1,
            scanned_conflict_count=0,
            count=SimpleNamespace(status="not_requested", value=None),
            ambiguous=False,
            warnings=[],
        )
        case = _evaluate_result(
            result,
            _query(required=["m-both"]),
            "lexical_vector_graph",
            1.0,
            allowed_scope_keys={scope.scope_key},
        )
        self.assertEqual(case["contribution"]["both"], 1)

    async def test_graphiti_unavailable_is_structured(self) -> None:
        dataset = _dataset()

        async def probe_fail(*args: Any, **kwargs: Any) -> str:
            return "structured-unavailable: test"

        with (
            patch(
                "benchmarks.personal_retrieval_ablation._probe_neo4j",
                new=probe_fail,
            ),
            patch(
                "benchmarks.personal_retrieval_ablation._probe_postgres",
                new=probe_fail,
            ),
        ):
            from benchmarks.personal_retrieval_ablation import run_ablation

            report = await run_ablation(
                dataset, profiles=("lexical_graph",), run_metamorphic=False
            )
        self.assertFalse(report["runtime"]["graph"]["available"])
        self.assertTrue(report["runtime"]["graph"]["reason"])
        self.assertTrue(
            report["profiles"]["deterministic"]["lexical_graph"]["unavailable"]
        )

    async def test_pgvector_unavailable_is_structured(self) -> None:
        dataset = _dataset()

        async def probe_fail(*args: Any, **kwargs: Any) -> str:
            return "structured-unavailable: test"

        with (
            patch(
                "benchmarks.personal_retrieval_ablation._probe_postgres",
                new=probe_fail,
            ),
            patch(
                "benchmarks.personal_retrieval_ablation._probe_neo4j",
                new=probe_fail,
            ),
        ):
            from benchmarks.personal_retrieval_ablation import run_ablation

            report = await run_ablation(
                dataset, profiles=("lexical_vector",), run_metamorphic=False
            )
        self.assertFalse(report["runtime"]["vector"]["available"])
        self.assertTrue(
            report["profiles"]["deterministic"]["lexical_vector"]["unavailable"]
        )

    async def test_unexpected_errors_are_not_swallowed(self) -> None:
        dataset = _dataset()
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        query = next(
            item for item in dataset.queries if item.query_id == "q-dev-job-current"
        )

        async def _boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")

        engine = SimpleNamespace(query=_boom)
        planner = DeterministicPersonalMemoryQueryPlanner()
        case = await _run_case(engine, planner, query, scopes, profile="lexical")
        self.assertTrue(case["error"])
        self.assertIn("boom", case["error"])
        self.assertEqual(case["hits"], [])
        # The failure must not be recorded as a pass.
        aggregated = _aggregate([case])
        self.assertEqual(aggregated["error_count"], 1)


async def _raise_async(exc: BaseException):
    async def _inner(*args: Any, **kwargs: Any) -> None:
        raise exc

    return _inner


async def _probe_fail(*args: Any, **kwargs: Any) -> str:
    return "structured-unavailable: test"


class MetamorphicTest(unittest.TestCase):
    def test_substitute_preserves_ids(self) -> None:
        dataset = _dataset()
        variant = dataset.metamorphic_variants[0]
        changed = apply_variant(dataset, variant)
        self.assertEqual(
            [item.memory_id for item in changed.fixtures],
            [item.memory_id for item in dataset.fixtures],
        )
        self.assertEqual(
            [item.query_id for item in changed.queries],
            [item.query_id for item in dataset.queries],
        )

    def test_safety_metrics_equal_after_substitution(self) -> None:
        base = [
            {
                "query_id": "q1",
                "scope_leakage": 0,
                "forbidden": [],
                "abstention_ok": True,
                "count_ok": True,
                "missing": [],
            },
            {
                "query_id": "q2",
                "scope_leakage": 1,
                "forbidden": ["x"],
                "abstention_ok": False,
                "count_ok": False,
                "missing": ["y"],
            },
        ]
        same = [dict(item) for item in base]
        metrics = _safety_metrics(base, same)
        self.assertTrue(metrics["safe"])
        different = [dict(item) for item in base]
        different[0]["scope_leakage"] = 1
        metrics2 = _safety_metrics(base, different)
        self.assertFalse(metrics2["safe"])
        self.assertEqual(len(metrics2["diverged_queries"]), 1)

    def test_substitute_text(self) -> None:
        self.assertEqual(
            substitute("我住在上海，喜欢香菜", [("上海", "澜州"), ("香菜", "茴香")]),
            "我住在澜州，喜欢茴香",
        )


class RuntimeBoundaryTest(unittest.TestCase):
    def test_runtime_does_not_import_benchmarks(self) -> None:
        runtime_root = Path(__file__).resolve().parents[1] / "doppel_memory"
        offenders = []
        for path in runtime_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"(^|\n)\s*(import|from)\s+benchmarks", text):
                offenders.append(str(path))
        self.assertEqual(offenders, [])

    def test_report_contains_no_credentials(self) -> None:
        # CLI reports must not embed DSN passwords or API keys.
        sample = _aggregate([])
        dump = json.dumps(sample, ensure_ascii=False)
        for secret in ("password", "api_key", "Bearer"):
            self.assertNotIn(secret.lower(), dump.lower())


class DirectScanTest(unittest.IsolatedAsyncioTestCase):
    async def test_orphan_and_scope_leak_candidates_detected(self) -> None:
        dataset = _dataset()
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        good_scope = scopes["u1"]

        class FakeIndex:
            async def search(self, query, bound, *, filters=None, limit=10):
                return [
                    SimpleNamespace(
                        scope=good_scope, memory_id="m-residence-current"
                    ),  # ok
                    SimpleNamespace(
                        scope=scopes["u2"], memory_id="m-wang-residence"
                    ),  # leak
                    SimpleNamespace(scope=good_scope, memory_id="m-ghost"),  # orphan
                    SimpleNamespace(
                        scope=good_scope, memory_id="m-expired-taste"
                    ),  # inactive
                ]

        store_dir = tempfile.mkdtemp(prefix="ablation-ds-")
        from doppel_memory.sqlite_store import SQLiteStore

        store = SQLiteStore(database=str(Path(store_dir) / "s.sqlite3"))
        try:
            for item in dataset.fixtures:
                record = _memory_record(item, scopes[item.scope], utc_now())
                await store.put(record)
            report = await _direct_scan(FakeIndex(), store, dataset, scopes, "vector")
        finally:
            await store.close()
        self.assertGreaterEqual(report["candidate_count"], 4)
        self.assertGreaterEqual(report["scope_leak_candidate_count"], 1)
        self.assertGreaterEqual(report["orphan_candidate_count"], 1)
        self.assertGreaterEqual(report["inactive_candidate_count"], 1)


class PlannerModeTest(unittest.IsolatedAsyncioTestCase):
    async def test_oracle_plan_injects_intent_and_as_of(self) -> None:
        from benchmarks.personal_retrieval_ablation import BenchmarkOraclePlanner
        from doppel_memory.query import PersonalMemoryQueryRequest

        dataset = _dataset()
        planner = BenchmarkOraclePlanner(dataset.queries)
        fixture = next(
            item
            for item in dataset.queries
            if item.query_id == "q-dev-residence-asof-2024"
        )
        draft = await planner.plan(
            PersonalMemoryQueryRequest(query=fixture.query, now=fixture.now)
        )
        self.assertEqual(draft.intent, "as_of")
        self.assertEqual(draft.as_of, fixture.as_of)
        self.assertEqual(draft.topic_keys, [])
        self.assertEqual(draft.memory_types, [])

    async def test_oracle_planner_rejects_unknown_query(self) -> None:
        from datetime import UTC

        from benchmarks.personal_retrieval_ablation import BenchmarkOraclePlanner
        from doppel_memory.query import PersonalMemoryQueryRequest

        planner = BenchmarkOraclePlanner(_dataset().queries)
        with self.assertRaises(ValueError):
            await planner.plan(
                PersonalMemoryQueryRequest(
                    query="不在数据集里的查询", now=datetime(2026, 1, 1, tzinfo=UTC)
                )
            )

    async def test_report_planner_replays_complete_matching_dataset(
        self,
    ) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        payload = {
            "dataset": {"fingerprint": dataset.fingerprint},
            "planner": {"name": "provider-planner", "version": "5"},
            "cases": [
                {
                    "query": query.query,
                    "error": "",
                    "actual": {
                        "intent": query.intent,
                        "as_of": query.as_of.isoformat() if query.as_of else None,
                        "time_from": (
                            query.time_from.isoformat() if query.time_from else None
                        ),
                        "time_to": query.time_to.isoformat() if query.time_to else None,
                        "entity_mentions": query.entity_mentions,
                        "relation_hints": query.relation_hints,
                    },
                }
                for query in dataset.queries
                if query.partition != "deferred_cross_subject"
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planner.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            planner = BenchmarkReportPlanner(path, dataset)
            query = dataset.queries[0]
            draft = await planner.plan(
                PersonalMemoryQueryRequest(query=query.query, now=query.now)
            )

        self.assertEqual(draft.entity_mentions, query.entity_mentions)
        self.assertEqual(draft.relation_hints, query.relation_hints)
        self.assertEqual(planner.source["provider_calls_during_replay"], 0)

    async def test_report_planner_rejects_dataset_fingerprint_mismatch(
        self,
    ) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planner.json"
            path.write_text(
                json.dumps(
                    {
                        "dataset": {"fingerprint": "wrong"},
                        "planner": {"name": "provider", "version": "5"},
                        "cases": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                BenchmarkReportPlanner(path, dataset)

    async def test_deterministic_planner_failure_is_not_retrieval_temporal(
        self,
    ) -> None:
        from benchmarks.personal_retrieval_ablation import (
            PLANNER_MODE_DETERMINISTIC,
        )

        scope = MemoryScope(user_id="user-linz", agent_id="echo")
        hit = _hit("m-future", scope=scope, valid_from="2027-01-01T00:00:00Z")
        result = SimpleNamespace(
            plan=SimpleNamespace(
                intent="lookup",
                as_of=None,
                time_from=None,
                time_to=None,
            ),
            hits=[hit],
            conflicts=[],
            matched_record_count=1,
            scanned_record_count=1,
            scanned_conflict_count=0,
            count=SimpleNamespace(status="not_requested", value=None),
            ambiguous=False,
            warnings=[],
        )
        case = _evaluate_result(
            result,
            _query(as_of="2026-06-15T00:00:00Z"),
            "lexical",
            1.0,
            allowed_scope_keys={scope.scope_key},
            mode=PLANNER_MODE_DETERMINISTIC,
        )
        # Planner did not recognize as_of -> planner_temporal_miss, NOT a
        # retrieval temporal failure under the deterministic mode.
        self.assertIn("planner_temporal_miss", case["planner_failures"])
        self.assertNotIn("retrieval_temporal_failure", case["retrieval_failures"])
        self.assertEqual(case["temporal_violations"], 0)


class RelationProfileTest(unittest.IsolatedAsyncioTestCase):
    async def test_relation_profile_runs_engine_and_attributes_gold_hits(self) -> None:
        dataset = load_ablation_dataset(RELATION_DATASET_PATH)
        # Keep this unit focused on contribution accounting over the original
        # exact-surface cases. The expanded paraphrase/adversarial partition is
        # intentionally allowed to expose false promotions in live ablations.
        dataset = dataset.model_copy(update={"queries": dataset.queries[:30]})
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        store = InMemoryStore()
        records = [
            _memory_record(item, scopes[item.scope], utc_now())
            for item in dataset.fixtures
        ]
        for record in records:
            self.assertTrue((await store.put(record)).accepted)

        class _FixtureRelationIndex:
            def __init__(self, match_kind="lexical") -> None:
                self.match_kind = match_kind

            async def search_relations(
                self, request, requested_scopes, *, filters=None, limit=10
            ):
                del filters
                allowed = {scope.scope_key for scope in requested_scopes}
                anchors = [item.casefold() for item in request.entity_mentions]
                hints = [item.casefold() for item in request.relation_hints]
                candidates = []
                for fixture, record in zip(dataset.fixtures, records, strict=True):
                    relation = fixture.relation
                    if (
                        relation is None
                        or relation.edge_kind != "rich"
                        or record.scope.scope_key not in allowed
                    ):
                        continue
                    entities = (
                        relation.source_entity.casefold(),
                        relation.target_entity.casefold(),
                    )
                    if not any(
                        anchor in entity for anchor in anchors for entity in entities
                    ):
                        continue
                    relation_text = (
                        relation.relation_type + " " + relation.fact
                    ).casefold()
                    if hints and not any(hint in relation_text for hint in hints):
                        continue
                    if (
                        request.valid_at is not None
                        and fixture.valid_from is not None
                        and fixture.valid_from > request.valid_at
                    ):
                        continue
                    if (
                        request.valid_at is not None
                        and fixture.valid_to is not None
                        and fixture.valid_to < request.valid_at
                    ):
                        continue
                    candidates.append(
                        RelationCandidate(
                            scope=record.scope,
                            memory_id=record.memory_id,
                            source="fixture_relation",
                            score=0.9,
                            relation_type=relation.relation_type,
                            match_kind=self.match_kind,
                            reranker_score=(
                                0.9 if self.match_kind == "reranker" else None
                            ),
                            source_entity_name=relation.source_entity,
                            target_entity_name=relation.target_entity,
                            edge_id="edge-" + record.memory_id,
                            episode_ids=["episode-" + record.memory_id],
                            valid_at=fixture.valid_from,
                            invalid_at=fixture.valid_to,
                        )
                    )
                return candidates[:limit]

        report = await _run_profiles(
            store=store,
            scopes=scopes,
            dataset=dataset,
            profiles=(
                "lexical",
                "lexical_relation",
                "lexical_relation_reranked",
            ),
            semantic_by_source={},
            relation_index=_FixtureRelationIndex(),
            relation_reranked_index=_FixtureRelationIndex("reranker"),
            graph=None,
            planner_modes=(PLANNER_MODE_ORACLE,),
        )

        relation_metrics = report["profiles"]["oracle"]["lexical_relation"]
        lexical_metrics = report["profiles"]["oracle"]["lexical"]
        self.assertGreater(
            relation_metrics["recall_at_1"], lexical_metrics["recall_at_1"]
        )
        self.assertGreater(relation_metrics["contribution"]["relation"], 0)
        reranked_metrics = report["profiles"]["oracle"]["lexical_relation_reranked"]
        self.assertEqual(
            reranked_metrics["recall_at_1"], relation_metrics["recall_at_1"]
        )
        self.assertGreater(
            reranked_metrics["contribution"]["relation_reranker"], 0
        )
        self.assertEqual(
            relation_metrics["contribution"]["relation_reranker"], 0
        )
        self.assertIn(
            "oracle_lexical_relation_reranked_vs_lexical_relation",
            report["comparisons"],
        )
        attribution = report["relation_final_hit_attribution"]
        self.assertTrue(attribution["available"])
        self.assertGreater(attribution["correct_relation_final_hit_links"], 0)
        self.assertEqual(attribution["incorrect_relation_final_hit_links"], 0)


@unittest.skipUnless(
    NEO4J_PASSWORD,
    "requires live Neo4j (NEO4J_PASSWORD) so lexical_graph executes while vector is missing",
)
class PlannerModeLiveGraphTest(unittest.IsolatedAsyncioTestCase):
    async def test_vector_missing_makes_full_hybrid_unavailable(self) -> None:
        dataset = _dataset()

        async def probe_pg_fail(*args: Any, **kwargs: Any) -> str:
            return "structured-unavailable: test"

        with patch(
            "benchmarks.personal_retrieval_ablation._probe_postgres",
            new=probe_pg_fail,
        ):
            from benchmarks.personal_retrieval_ablation import run_ablation

            report = await run_ablation(
                dataset,
                profiles=(
                    "lexical_graph",
                    "lexical_vector",
                    "lexical_vector_graph",
                ),
                planner_modes=("oracle",),
                run_metamorphic=False,
            )
        oracle = report["profiles"]["oracle"]
        self.assertFalse(oracle["lexical_graph"].get("unavailable", False))
        self.assertTrue(oracle["lexical_vector"]["unavailable"])
        self.assertTrue(oracle["lexical_vector_graph"]["unavailable"])
        self.assertEqual(report["comparisons"], {})
        degradation = report["diagnostics"].get("composite_graph_only_degradation")
        self.assertIsNotNone(degradation)
        self.assertEqual(
            degradation["execution_profile"],
            "composite_graph_only_degradation",
        )

    def test_graph_only_degradation_never_named_full_hybrid(self) -> None:
        for name in PROFILE_MAIN:
            self.assertNotIn("degradation", name)
        self.assertNotIn("composite_graph_only_degradation", PROFILE_MAIN)

    def test_fixture_validator_rejects_plan_with_event_key(self) -> None:
        from benchmarks.personal_retrieval_ablation import validate_dataset_semantics

        dataset = _dataset()
        bad_fixture = dataset.fixtures[0].model_copy(
            update={"event_key": "evt-bad", "personal_memory_type": "plan"}
        )
        bad_dataset = dataset.model_copy(
            update={"fixtures": [bad_fixture, *dataset.fixtures[1:]]}
        )
        failures = validate_dataset_semantics(bad_dataset)
        self.assertTrue(
            any("event_key" in item and "plan" in item for item in failures)
        )

    def test_fixture_validator_rejects_invalid_required_at_asof(self) -> None:
        from benchmarks.personal_retrieval_ablation import validate_dataset_semantics

        dataset = _dataset()
        bad_query = dataset.queries[0].model_copy(
            update={
                "query_id": "q-invalid-asof",
                "as_of": datetime(2023, 1, 1, tzinfo=UTC),
                "partition": "dev",
                "required_memory_ids": ["m-residence-current"],
            }
        )
        bad_dataset = dataset.model_copy(update={"queries": [bad_query]})
        failures = validate_dataset_semantics(bad_dataset)
        self.assertTrue(any("not yet" in item for item in failures))

    def test_fixture_validator_rejects_owner_subject_mismatch(self) -> None:
        from benchmarks.personal_retrieval_ablation import validate_dataset_semantics

        dataset = _dataset()
        bad_fixture = dataset.fixtures[0].model_copy(
            update={"subject_id": "somebody-else"}
        )
        bad_dataset = dataset.model_copy(
            update={"fixtures": [bad_fixture, *dataset.fixtures[1:]]}
        )
        failures = validate_dataset_semantics(bad_dataset)
        self.assertTrue(any("does not match scope user" in item for item in failures))

    def test_future_asof_without_required_is_legal(self) -> None:
        dataset = _dataset()
        query = next(
            item
            for item in dataset.queries
            if item.query_id == "q-hold-residence-future-asof"
        )
        self.assertIsNotNone(query.as_of)
        self.assertGreater(query.as_of, query.now)
        self.assertEqual(query.required_memory_ids, [])

    def test_returned_edge_counts_not_passed_as_final_hit(self) -> None:
        from benchmarks.personal_retrieval_ablation import _build_final_hit_attribution

        report = {
            "diagnostics": {"graph_direct": {"edge_attribution_by_query": {}}},
            "cases": [],
        }
        attribution = _build_final_hit_attribution(
            report=report,
            dataset=_dataset(),
            per_mode={"oracle": {"lexical_graph": {}}},
        )
        self.assertFalse(attribution["available"])

    def test_graph_attribution_separates_links_hits_and_queries(self) -> None:
        from benchmarks.personal_retrieval_ablation import _build_final_hit_attribution

        dataset = _dataset()
        query_id = dataset.queries[0].query_id
        report = {
            "diagnostics": {
                "graph_direct": {
                    "edge_attribution_by_query": {
                        query_id: [
                            {
                                "memory_id": "m-residence-current",
                                "edge_uuid": "edge-fallback-1",
                                "episode_uuid": "episode-1",
                                "edge_kind": "fallback",
                            },
                            {
                                "memory_id": "m-residence-current",
                                "edge_uuid": "edge-fallback-2",
                                "episode_uuid": "episode-1",
                                "edge_kind": "fallback",
                            },
                            {
                                "memory_id": "m-item-camera",
                                "edge_uuid": "edge-rich-1",
                                "episode_uuid": "episode-2",
                                "edge_kind": "rich",
                            },
                        ]
                    }
                }
            },
            "cases": [
                {
                    "query_id": query_id,
                    "mode": "oracle",
                    "profile": "lexical_graph",
                    "error": "",
                    "hits": ["m-residence-current", "m-item-camera"],
                }
            ],
        }
        attribution = _build_final_hit_attribution(
            report=report,
            dataset=dataset,
            per_mode={"oracle": {"lexical_graph": {}}},
        )

        self.assertTrue(attribution["available"])
        graph_att = attribution["graph"]
        self.assertEqual(graph_att["fallback_edge_final_hit_links"], 2)
        self.assertEqual(graph_att["rich_edge_final_hit_links"], 1)
        self.assertEqual(graph_att["unique_final_hits_with_fallback"], 1)
        self.assertEqual(graph_att["unique_final_hits_with_rich"], 1)
        self.assertEqual(graph_att["unique_queries_with_fallback"], 1)
        self.assertEqual(graph_att["unique_queries_with_rich"], 1)

    def test_reproducibility_cli_args_exist(self) -> None:
        from benchmarks.personal_retrieval_ablation import _parser

        args = _parser().parse_args(
            [
                "--no-metamorphic",
                "--planner-modes",
                PLANNER_MODE_REPORT,
                "--planner-report",
                "data/doppel/planner.json",
                "--profiles",
                "lexical",
                "--gate-profiles",
                "lexical_relation,lexical_vector_relation",
                "--relation-reranker-model",
                "BAAI/bge-reranker-base",
                "--relation-reranker-threshold",
                "0.75",
                "--relation-reranker-cache-dir",
                "data/models",
                "--relation-reranker-batch-size",
                "16",
            ]
        )
        self.assertEqual(args.planner_modes, PLANNER_MODE_REPORT)
        self.assertEqual(args.planner_report, Path("data/doppel/planner.json"))
        self.assertTrue(args.no_metamorphic)
        self.assertEqual(args.gate_profiles, "lexical_relation,lexical_vector_relation")
        self.assertEqual(args.relation_reranker_model, "BAAI/bge-reranker-base")
        self.assertEqual(args.relation_reranker_threshold, 0.75)
        self.assertEqual(args.relation_reranker_cache_dir, Path("data/models"))
        self.assertEqual(args.relation_reranker_batch_size, 16)

    def test_profile_gate_is_not_failed_by_control_profile(self) -> None:
        from benchmarks.personal_retrieval_ablation import _parser, _validate_report

        empty = {
            "planner_failures": [],
            "retrieval_failures": [],
            "security_failures": [],
            "fixture_validation_failures": [],
        }
        control_failure = {
            **empty,
            "retrieval_failures": ["q-control:missing_required_hit"],
        }
        report = {
            "runtime": {
                "vector": {"available": True},
                "graph": {"available": True},
            },
            "profiles": {
                "oracle": {
                    "lexical": {
                        "query_count": 1,
                        "error_count": 0,
                        "scope_leakage_count": 0,
                        "temporal_violation_count": 0,
                    },
                    "lexical_relation": {
                        "query_count": 1,
                        "error_count": 0,
                        "scope_leakage_count": 0,
                        "temporal_violation_count": 0,
                    },
                }
            },
            "hard_gates": control_failure,
            "hard_gates_by_profile": {
                "oracle": {
                    "lexical": control_failure,
                    "lexical_relation": empty,
                }
            },
        }
        args = _parser().parse_args(
            [
                "--planner-modes",
                "oracle",
                "--profiles",
                "lexical,lexical_relation",
                "--gate-profiles",
                "lexical_relation",
            ]
        )

        self.assertEqual(_validate_report(report, args=args), [])

    def test_benchmark_has_no_http_client_import(self) -> None:
        src = (
            Path(__file__).resolve().parents[1]
            / "benchmarks"
            / "personal_retrieval_ablation.py"
        )
        text = src.read_text(encoding="utf-8")
        for forbidden in (
            "import httpx",
            "import requests",
            "from httpx",
            "from requests",
        ):
            self.assertNotIn(forbidden, text)

    def test_uv_lock_not_staged(self) -> None:
        import subprocess

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).resolve().parents[1],
        )
        staged = [
            line[3:]
            for line in result.stdout.splitlines()
            if len(line) > 3 and line[0] in "MA" and "uv.lock" in line
        ]
        self.assertEqual(staged, [])


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()

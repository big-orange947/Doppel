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
    PROFILE_DIRECT,
    PROFILE_MAIN,
    SOURCE_GRAPH,
    SOURCE_VECTOR,
    AblationDataset,
    AblationQuery,
    _aggregate,
    _direct_scan,
    _evaluate_result,
    _memory_record,
    _run_case,
    _safety_metrics,
    apply_variant,
    load_ablation_dataset,
    substitute,
)
from doppel_memory import (
    DeterministicPersonalMemoryQueryPlanner,
    MemoryScope,
    PersonalMemoryQueryEngine,
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
            evidence=[SimpleNamespace(message_id="e1", at=datetime(2026, 1, 1, tzinfo=UTC))],
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


class DatasetTest(unittest.TestCase):
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
        self.assertEqual(tuple(ALL_PROFILES), (*PROFILE_MAIN, *PROFILE_DIRECT))

    def test_report_schema_validates(self) -> None:
        import pydantic

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        report = self._minimal_report()
        # Structural conformance without an extra jsonschema dependency.
        self.assertIn("required", schema)
        for key in schema["required"]:
            self.assertIn(key, report, key)
        self.assertEqual(
            schema["properties"]["runner"]["const"], report["runner"]
        )
        report_keys = set(report["profiles"]["deterministic"]["lexical"])
        schema_required = set(schema["$defs"]["profile"]["required"])
        self.assertTrue(schema_required.issubset(report_keys), schema_required - report_keys)
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
                        "contribution": {"vector": 0, "graph": 0, "both": 0},
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
                        "contribution": {"vector": 0, "graph": 0, "both": 0},
                    }
                }
            },
            "diagnostics": {},
            "comparisons": {},
            "hard_gates": {
                "planner_failures": [],
                "retrieval_failures": [],
                "security_failures": [],
                "fixture_validation_failures": [],
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
            case = await _run_case(
                engine, planner, query, scopes, profile="lexical"
            )
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
            plan=SimpleNamespace(intent="as_of", as_of=datetime(2026, 6, 15, tzinfo=UTC)),
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

        with patch(
            "benchmarks.personal_retrieval_ablation._probe_neo4j",
            new=probe_fail,
        ), patch(
            "benchmarks.personal_retrieval_ablation._probe_postgres",
            new=probe_fail,
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

        with patch(
            "benchmarks.personal_retrieval_ablation._probe_postgres",
            new=probe_fail,
        ), patch(
            "benchmarks.personal_retrieval_ablation._probe_neo4j",
            new=probe_fail,
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
                    SimpleNamespace(scope=good_scope, memory_id="m-residence-current"),  # ok
                    SimpleNamespace(scope=scopes["u2"], memory_id="m-wang-residence"),  # leak
                    SimpleNamespace(scope=good_scope, memory_id="m-ghost"),  # orphan
                    SimpleNamespace(scope=good_scope, memory_id="m-expired-taste"),  # inactive
                ]

        store_dir = tempfile.mkdtemp(prefix="ablation-ds-")
        from doppel_memory.sqlite_store import SQLiteStore

        store = SQLiteStore(database=str(Path(store_dir) / "s.sqlite3"))
        try:
            for item in dataset.fixtures:
                record = _memory_record(item, scopes[item.scope], utc_now())
                await store.put(record)
            report = await _direct_scan(
                FakeIndex(), store, dataset, scopes, "vector"
            )
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
        self.assertNotIn(
            "retrieval_temporal_failure", case["retrieval_failures"]
        )
        self.assertEqual(case["temporal_violations"], 0)


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
        degradation = report["diagnostics"].get(
            "composite_graph_only_degradation"
        )
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
        self.assertTrue(
            any("does not match scope user" in item for item in failures)
        )

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
        self.assertEqual(attribution["fallback_edge_final_hit_links"], 2)
        self.assertEqual(attribution["rich_edge_final_hit_links"], 1)
        self.assertEqual(attribution["unique_final_hits_with_fallback"], 1)
        self.assertEqual(attribution["unique_final_hits_with_rich"], 1)
        self.assertEqual(attribution["unique_queries_with_fallback"], 1)
        self.assertEqual(attribution["unique_queries_with_rich"], 1)

    def test_reproducibility_cli_args_exist(self) -> None:
        from benchmarks.personal_retrieval_ablation import _parser

        args = _parser().parse_args(
            [
                "--no-metamorphic",
                "--planner-modes",
                "oracle",
                "--profiles",
                "lexical",
            ]
        )
        self.assertEqual(args.planner_modes, "oracle")
        self.assertTrue(args.no_metamorphic)

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

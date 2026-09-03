from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from benchmarks.relation_planner_quality import (
    DEFAULT_DATASET,
    CachedPlanner,
    PlannerCallBudget,
    PlannerCallBudgetExceeded,
    ReplayPlanner,
    UsageLedger,
    _async_main,
    _evaluate_case,
    _parser,
    _term_matches,
    run_relation_planner_quality,
)
from doppel_memory import (
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryRequest,
    StructuredOutputProviderError,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "relation-planner-quality-result.schema.json"
)


class _GoldPlanner:
    name = "tests.gold-relation-planner"
    version = "1"

    def __init__(self, dataset: Any) -> None:
        self.dataset = dataset
        self.by_query = {item.query: item for item in dataset.queries}
        self.calls = 0

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        self.calls += 1
        item = self.by_query[request.query]
        return PersonalMemoryQueryDraft(
            intent=item.intent,
            search_text=item.query,
            entity_mentions=item.entity_mentions,
            relation_hints=item.relation_hints,
            relation_types=self.dataset.relation_type_labels[item.query_id],
            as_of=item.as_of,
            subject=request.default_subject,
            subject_id=request.default_subject_id,
        )


class _StaticPlanner:
    name = "tests.static-relation-planner"
    version = "1"

    def __init__(self, draft: PersonalMemoryQueryDraft) -> None:
        self.draft = draft
        self.calls = 0

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        del request
        self.calls += 1
        return self.draft


@pytest.mark.asyncio
async def test_gold_planner_scores_every_relation_case() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    planner = _GoldPlanner(dataset)

    report = await run_relation_planner_quality(dataset, planner)

    assert report["metrics"]["case_count"] == 65
    assert report["metrics"]["provider_error_count"] == 0
    assert report["metrics"]["structural_failure_count"] == 0
    assert report["metrics"]["exact_structure_accuracy"] == 1
    assert report["metrics"]["typed_structure_accuracy"] == 1
    assert report["metrics"]["entity_recall"] == 1
    assert report["metrics"]["relation_recall"] == 1
    assert report["metrics"]["relation_type_exact_accuracy"] == 1
    assert report["metrics"]["relation_type_recall"] == 1
    assert report["metrics"]["relation_type_precision"] == 1
    assert report["metrics"]["relation_type_failure_count"] == 0
    assert report["metrics"]["relation_type_ontology_violation_count"] == 0
    assert report["by_partition"]["adversarial"]["exact_structure_accuracy"] == 1


@pytest.mark.asyncio
async def test_relation_mismatch_is_reported_without_retrieval() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    planner = _StaticPlanner(
        PersonalMemoryQueryDraft(
            intent="lookup",
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["购买"],
        )
    )

    report = await run_relation_planner_quality(dataset, planner)

    assert report["metrics"]["structural_failure_count"] > 0
    assert report["metrics"]["exact_structure_accuracy"] < 1
    assert report["metrics"]["unexpected_relation_count"] > 0


@pytest.mark.asyncio
async def test_relation_type_mismatch_and_ontology_violation_are_independent() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    query = dataset.queries[0]
    planner = _StaticPlanner(
        PersonalMemoryQueryDraft(
            intent=query.intent,
            search_text=query.query,
            entity_mentions=query.entity_mentions,
            relation_hints=query.relation_hints,
            relation_types=["INVENTED_BY_TEST"],
            subject_id=dataset.scopes[query.scopes[0]].user_id,
        )
    )

    case = await _evaluate_case(planner, dataset, query)

    assert case["structure_ok"] is True
    assert case["relation_type_ok"] is False
    assert case["typed_structure_ok"] is False
    assert case["expected_relation_types"] == ["HELD_BY"]
    assert case["unexpected_relation_types"] == ["INVENTED_BY_TEST"]
    assert case["relation_type_ontology_violations"] == ["INVENTED_BY_TEST"]


@pytest.mark.asyncio
async def test_interval_covering_gold_asof_is_a_valid_temporal_plan() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    query = next(item for item in dataset.queries if item.query_id == "rel-q03")
    planner = _StaticPlanner(
        PersonalMemoryQueryDraft(
            intent="history",
            search_text="银河帝国",
            time_from=datetime(2026, 5, 1, tzinfo=UTC),
            time_to=datetime(2026, 5, 31, 23, 59, tzinfo=UTC),
            entity_mentions=["银河帝国"],
            relation_hints=["手里"],
            subject_id=dataset.scopes[query.scopes[0]].user_id,
        )
    )

    case = await _evaluate_case(planner, dataset, query)

    assert case["intent_ok"] is False
    assert case["intent_semantics_ok"] is True
    assert case["as_of_date_ok"] is False
    assert case["interval_covers_as_of"] is True
    assert case["temporal_plan_ok"] is True
    assert case["structure_ok"] is True


@pytest.mark.asyncio
async def test_cache_hit_does_not_consume_call_budget(tmp_path: Path) -> None:
    base = _StaticPlanner(
        PersonalMemoryQueryDraft(
            search_text="相机",
            entity_mentions=["相机"],
            relation_hints=["位于"],
        )
    )
    budget = PlannerCallBudget(base, max_calls=1)
    cached = CachedPlanner(budget, tmp_path)
    request = PersonalMemoryQueryRequest(
        query="相机在哪里？",
        now=datetime(2026, 8, 31, tzinfo=UTC),
        default_subject_id="owner",
    )

    first = await cached.plan(request)
    second = await cached.plan(request)

    assert first == second
    assert base.calls == 1
    assert budget.calls == 1
    assert cached.hits == 1
    assert cached.misses == 1
    cache_files = list(tmp_path.rglob("*.json"))
    assert len(cache_files) == 1
    assert "api_key" not in cache_files[0].read_text(encoding="utf-8").casefold()


@pytest.mark.asyncio
async def test_budget_blocks_before_second_planner_call() -> None:
    base = _StaticPlanner(PersonalMemoryQueryDraft(search_text="test"))
    budget = PlannerCallBudget(base, max_calls=1)
    request = PersonalMemoryQueryRequest(
        query="test",
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    await budget.plan(request)
    with pytest.raises(PlannerCallBudgetExceeded):
        await budget.plan(request)
    assert base.calls == 1


def test_term_matching_is_unicode_and_punctuation_tolerant() -> None:
    matched, unexpected = _term_matches(
        ["《银河帝国》", "备用钥匙"],
        ["银河帝国", "我的备用钥匙"],
    )

    assert matched == 2
    assert unexpected == []


def test_usage_ledger_is_content_free_and_additive() -> None:
    ledger = UsageLedger()
    ledger.observe({"input_tokens": 10, "output_tokens": 3, "ignored": "text"})
    ledger.observe({"input_tokens": 5, "total_tokens": 9})

    assert ledger.report() == {
        "calls_with_usage": 2,
        "input_tokens": 15,
        "output_tokens": 3,
        "total_tokens": 9,
    }


def test_reference_cli_is_explicit_and_budgeted() -> None:
    args = _parser().parse_args(
        [
            "--planner",
            "reference",
            "--model",
            "deepseek-v4-flash",
            "--schema-mode",
            "json_object",
            "--max-tokens-parameter",
            "max_tokens",
            "--thinking",
            "disabled",
            "--max-calls",
            "5",
            "--max-relation-type-failures",
            "3",
        ]
    )

    assert args.planner == "reference"
    assert args.model == "deepseek-v4-flash"
    assert args.schema_mode == "json_object"
    assert args.max_tokens_parameter == "max_tokens"
    assert args.thinking == "disabled"
    assert args.max_calls == 5
    assert args.max_relation_type_failures == 3


@pytest.mark.asyncio
async def test_deterministic_planner_is_not_limited_by_provider_call_budget(
    tmp_path: Path,
) -> None:
    output = tmp_path / "deterministic.json"
    args = _parser().parse_args(
        [
            "--planner",
            "deterministic",
            "--no-cache",
            "--max-calls",
            "0",
            "--max-structural-failures",
            "65",
            "--max-relation-type-failures",
            "65",
            "--output",
            str(output),
        ]
    )

    exit_code = await _async_main(args)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert report["metrics"]["case_count"] == 65
    assert report["metrics"]["valid_case_count"] == 65
    assert report["metrics"]["provider_error_count"] == 0
    assert report["metrics"]["relation_type_failure_count"] == 65
    assert report["budget"] == {"max_calls": None, "calls": 0}


@pytest.mark.asyncio
async def test_prior_report_can_be_replayed_without_provider_calls(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "prior.json"
    report_path.write_text(
        json.dumps(
            {
                "planner": {"name": "prior", "version": "1"},
                "cases": [
                    {
                        "query": "相机在哪里？",
                        "error": "",
                        "actual": {
                            "intent": "current",
                            "entity_mentions": ["相机"],
                            "relation_hints": ["位于"],
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    planner = ReplayPlanner(report_path)

    draft = await planner.plan(
        PersonalMemoryQueryRequest(
            query="相机在哪里？",
            now=datetime(2026, 8, 31, tzinfo=UTC),
        )
    )

    assert draft.intent == "current"
    assert draft.entity_mentions == ["相机"]
    assert draft.relation_hints == ["位于"]


@pytest.mark.asyncio
async def test_unrequested_hard_filters_fail_structure() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    query = dataset.queries[0]

    class HardFilteringPlanner:
        name = "test.hard-filtering"
        version = "1"

        async def plan(self, request: PersonalMemoryQueryRequest) -> dict[str, object]:
            return {
                "intent": query.intent,
                "as_of": query.as_of,
                "entity_mentions": query.entity_mentions,
                "relation_hints": query.relation_hints,
                "memory_types": ["episode"],
            }

    report = await run_relation_planner_quality(dataset, HardFilteringPlanner())
    case = report["cases"][0]

    assert case["hard_filter_ok"] is False
    assert case["unexpected_hard_filters"] == ["memory_type:episode"]
    assert case["structure_ok"] is False
    assert report["metrics"]["unexpected_hard_filter_count"] >= 1


def test_dataset_remains_draft_and_has_all_partitions() -> None:
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    partitions = {item["partition"] for item in raw["queries"]}

    assert raw["frozen"] is False
    assert raw["publication_ready"] is False
    assert {"dev", "heldout", "adversarial"}.issubset(partitions)


def test_result_schema_tracks_runner_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["properties"]["runner"]["const"] == (
        "doppel.relation-planner-quality.v1"
    )
    assert "cases" in schema["required"]
    assert "metrics" in schema["required"]
    assert "usage" in schema["required"]


@pytest.mark.asyncio
async def test_auth_failure_stops_before_next_call_and_scores_are_unavailable() -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)

    class AuthFailure:
        name, version = "tests.auth", "1"
        calls = 0

        async def plan(self, request: PersonalMemoryQueryRequest) -> None:
            self.calls += 1
            raise StructuredOutputProviderError(
                "authentication_error", "do not persist secret text", status_code=401
            )

    planner = AuthFailure()
    report = await run_relation_planner_quality(dataset, planner)
    assert planner.calls == 1
    assert report["metrics"]["provider_error_count"] == 1
    assert report["metrics"]["not_run_case_count"] == 64
    assert report["execution"]["stopped_early"] is True
    assert report["execution"]["quality_measurement"] == "unavailable"
    for metric in (
        "entity_recall",
        "relation_recall",
        "relation_type_recall",
        "relation_type_precision",
    ):
        assert report["metrics"][metric] is None
    assert report["cases"][0]["http_status"] == 401
    assert "secret text" not in json.dumps(report)
    assert (
        sum(item["provider_error_count"] for item in report["by_partition"].values())
        == 1
    )


@pytest.mark.asyncio
async def test_validation_diagnostics_drop_values_extra_key_names_and_messages() -> (
    None
):
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    secret = "sk-test-secret-not-for-report"

    class InvalidPlanner:
        async def plan(self, request: PersonalMemoryQueryRequest) -> dict[str, Any]:
            return {"confidence": secret, secret: "sensitive value"}

    case = await _evaluate_case(InvalidPlanner(), dataset, dataset.queries[0])
    assert case["error"] == "ValidationError"
    assert case["error_code"] == "validation_error"
    assert case["validation_diagnostics_available"] is True
    assert case["validation_errors"] == [
        {"location": ["confidence"], "type": "float_parsing"},
        {"location": ["<unknown-field>"], "type": "extra_forbidden"},
    ]
    assert secret not in json.dumps(case)
    assert "sensitive value" not in json.dumps(case)


@pytest.mark.asyncio
async def test_replay_preserves_source_failure_without_inventing_new_provider_errors(
    tmp_path: Path,
) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    report = await run_relation_planner_quality(dataset, _GoldPlanner(dataset))
    report["cases"][0].update(error="ValidationError", actual=None)
    path = tmp_path / "source.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    replay = await run_relation_planner_quality(
        dataset, ReplayPlanner(path, dataset=dataset)
    )
    case = replay["cases"][0]
    assert case["error"] == "ValidationError"
    assert case["error_origin"] == "source_report"
    assert case["validation_diagnostics_available"] is False
    assert replay["metrics"]["valid_case_count"] == 64
    assert replay["budget"]["calls"] == 0
    assert replay["execution"]["complete"] is False


@pytest.mark.asyncio
async def test_replay_rejects_changed_request_and_duplicate_queries(
    tmp_path: Path,
) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    report = await run_relation_planner_quality(dataset, _GoldPlanner(dataset))
    path = tmp_path / "source.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    planner = ReplayPlanner(path, dataset=dataset)
    query = dataset.queries[0]
    with pytest.raises(ValueError, match="request fingerprint"):
        await planner.plan(PersonalMemoryQueryRequest(query=query.query, now=query.now))
    report["cases"].append(report["cases"][0])
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        ReplayPlanner(path)


@pytest.mark.asyncio
async def test_missing_key_is_rejected_before_provider_creation(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    args = _parser().parse_args(["--planner", "reference", "--model", "fake"])
    with pytest.raises(RuntimeError, match="DOPPEL_API_KEY is missing"):
        await _async_main(args)


@pytest.mark.asyncio
async def test_replay_keeps_safe_diagnostics_but_redacts_untrusted_report_fields(
    tmp_path: Path,
) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    report = await run_relation_planner_quality(dataset, _GoldPlanner(dataset))
    report["cases"][0].update(
        error="ValidationError",
        error_code="validation_error",
        actual=None,
        validation_errors=[
            {"location": ["as_of"], "type": "datetime_parsing", "input": "sk-secret"},
            {"location": ["sk-secret"], "type": "sk-secret"},
        ],
    )
    path = tmp_path / "source.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    replay = await run_relation_planner_quality(
        dataset, ReplayPlanner(path, dataset=dataset)
    )
    case = replay["cases"][0]
    assert case["validation_errors"] == [
        {"location": ["as_of"], "type": "datetime_parsing"},
        {"location": ["<unknown-field>"], "type": "custom_validation_error"},
    ]
    assert "sk-secret" not in json.dumps(case)


@pytest.mark.asyncio
async def test_legacy_all_auth_failure_replay_is_unmeasured_not_a_new_live_run(
    tmp_path: Path,
) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    source = {
        "dataset": {"fingerprint": dataset.fingerprint},
        "cases": [
            {
                "query": item.query,
                "actual": None,
                "error": "StructuredOutputProviderError",
                "error_code": "authentication_error",
            }
            for item in dataset.queries
        ],
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    replay = await run_relation_planner_quality(
        dataset, ReplayPlanner(path, dataset=dataset)
    )
    assert replay["execution"]["stopped_early"] is False
    assert replay["execution"]["quality_measurement"] == "unavailable"
    assert replay["metrics"]["provider_error_count"] == 65
    assert replay["metrics"]["entity_recall"] is None
    assert replay["budget"]["calls"] == 0
    assert all(item["error_origin"] == "source_report" for item in replay["cases"])

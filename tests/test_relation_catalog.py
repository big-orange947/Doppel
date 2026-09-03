"""Schema descriptions are host input, never query answers or extra authority."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from benchmarks.relation_planner_quality import (
    DEFAULT_DATASET,
    CachedPlanner,
    ReplayPlanner,
    _async_main,
    _fingerprint,
    _parser,
    _query_request,
    run_relation_planner_quality,
)
from doppel_memory import (
    DoppelClient,
    InMemoryStore,
    MemoryScope,
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
    ReferencePersonalMemoryQueryPlanner,
    RelationTypeDefinition,
    StructuredOutputProviderError,
)
from doppel_memory.query import (
    REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS,
    REFERENCE_RELATION_DEFINITION_INSTRUCTIONS,
    PersonalMemoryQueryPlanningError,
)

NOW = datetime(2026, 9, 3, tzinfo=UTC)
CATALOG = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/catalogs/personal-relations-v1.json"
)


def _definition(**updates: Any) -> RelationTypeDefinition:
    # Deliberately not a label or entity in the personal retrieval fixture.
    return RelationTypeDefinition.model_validate(
        {
            "name": "CALIBRATED_BY",
            "description": "The target calibrates the source.",
            "source_description": "The calibrated instrument.",
            "target_description": "The calibration provider.",
            "constraints": ["Calibration does not establish ownership."],
            **updates,
        }
    )


def _request(**updates: Any) -> PersonalMemoryQueryRequest:
    return PersonalMemoryQueryRequest.model_validate(
        {
            "query": "Who calibrated the sensor?",
            "now": NOW,
            "default_subject_id": "owner",
            **updates,
        }
    )


class _Model:
    name = "test.catalog-model"
    version = "1"

    def __init__(self, **output: Any) -> None:
        self.requests: list[Any] = []
        self.output = output

    async def generate(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return self.output


class _Planner:
    name = "test.catalog-planner"
    version = "1"

    def __init__(self, **output: Any) -> None:
        self.requests: list[PersonalMemoryQueryRequest] = []
        self.output = output

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        self.requests.append(request)
        return PersonalMemoryQueryDraft(**self.output)


def test_definition_normalizes_and_is_immutable() -> None:
    definition = _definition(name=" calibrated_by ", description=" Meaning ")
    assert definition.name == "CALIBRATED_BY"
    assert definition.description == "Meaning"
    assert isinstance(definition.constraints, tuple)
    with pytest.raises(ValidationError):
        definition.name = "OTHER"  # type: ignore[misc]


@pytest.mark.parametrize(
    "updates",
    [
        {"name": "bad label"},
        {"name": ""},
        {"description": " "},
        {"source_description": ""},
        {"target_description": None},
        {"constraints": [" "]},
        {"constraints": "not an array"},
        {"scopes": ["other-owner"]},
        {"query_id": "gold-answer"},
    ],
)
def test_definition_rejects_malformed_or_non_schema_fields(
    updates: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _definition(**updates)


def test_catalog_only_defines_allowlist_and_partial_catalog_never_widens_it() -> None:
    definition = _definition()
    assert _request(
        relation_type_definitions=[definition]
    ).available_relation_types == ["CALIBRATED_BY"]
    partial = _request(
        available_relation_types=["CALIBRATED_BY", "TESTED_BY"],
        relation_type_definitions=[definition],
    )
    assert partial.available_relation_types == ["CALIBRATED_BY", "TESTED_BY"]
    with pytest.raises(ValidationError, match="host allowlist"):
        _request(
            available_relation_types=["TESTED_BY"],
            relation_type_definitions=[definition],
        )
    with pytest.raises(ValidationError, match="unique"):
        _request(
            relation_type_definitions=[definition, _definition(name="calibrated_by")]
        )


async def test_labels_only_uses_shared_prompt_without_catalog_payload() -> None:
    request = _request(available_relation_types=["CALIBRATED_BY"])
    model = _Model()
    await ReferencePersonalMemoryQueryPlanner(model).plan(request)
    captured = model.requests[0]
    assert captured.instructions == REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS
    assert captured.input == request.model_dump(
        mode="json", exclude={"relation_type_definitions"}
    )
    assert "relation_type_definitions" not in captured.input


async def test_reference_receives_roles_and_constraints_without_output_schema_change() -> (
    None
):
    definition = _definition()
    model = _Model(subject="contact", subject_id="intruder")
    draft = await ReferencePersonalMemoryQueryPlanner(model).plan(
        _request(relation_type_definitions=[definition])
    )
    captured = model.requests[0]
    assert captured.instructions == (
        REFERENCE_PERSONAL_MEMORY_QUERY_INSTRUCTIONS
        + REFERENCE_RELATION_DEFINITION_INSTRUCTIONS
    )
    assert captured.input["relation_type_definitions"] == [
        definition.model_dump(mode="json")
    ]
    assert "relation_type_definitions" not in captured.output_schema["properties"]
    assert "scopes" not in captured.input
    assert draft.subject == "owner"
    assert draft.subject_id == "owner"
    assert draft.relation_types == []  # Descriptions cannot force a type selection.


async def test_reference_prompt_distinguishes_predicate_ambiguity_from_unknown_facts() -> (
    None
):
    model = _Model(relation_types=["CALIBRATED_BY"], entity_mentions=["sensor"])
    planner = ReferencePersonalMemoryQueryPlanner(model)
    draft = await planner.plan(_request(relation_type_definitions=[_definition()]))
    request = model.requests[0]
    assert planner.version.startswith("9.")
    assert "independently from whether its answer is known" in request.instructions
    assert (
        "requested meaning, endpoint roles, and explicit exclusions"
        in request.instructions
    )
    assert "does not prohibit selecting" in request.instructions
    assert "prefer an empty string" in request.instructions
    assert "at most 80 characters" in request.instructions
    assert "proper name" in request.instructions
    assert request.output_schema == PersonalMemoryQueryDraft.model_json_schema()
    assert draft.relation_types == ["CALIBRATED_BY"]
    # The prompt has no built-in vocabulary or fixture-specific entity aliases.
    for definition in _load_catalog():
        assert definition.name not in request.instructions


async def test_engine_forwards_catalog_without_changing_plan_or_retrieval_contract() -> (
    None
):
    scope = MemoryScope(user_id="owner", agent_id="assistant")
    engine = PersonalMemoryQueryEngine(InMemoryStore())
    planner = _Planner(relation_types=["CALIBRATED_BY"], entity_mentions=["sensor"])
    legacy = await engine.query(
        planner,
        "Who calibrated the sensor?",
        [scope],
        now=NOW,
        available_relation_types=["CALIBRATED_BY"],
    )
    defined = await engine.query(
        planner,
        "Who calibrated the sensor?",
        [scope],
        now=NOW,
        relation_type_definitions=[_definition()],
    )
    assert legacy.model_dump() == defined.model_dump()
    assert planner.requests[-1].relation_type_definitions == [_definition()]
    with pytest.raises(PersonalMemoryQueryPlanningError):
        await engine.plan(
            _Planner(relation_types=["INVENTED_TYPE"]),
            "sensor",
            [scope],
            now=NOW,
            relation_type_definitions=[_definition()],
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"description": "Different meaning."},
        {"source_description": "Different source role."},
        {"target_description": "Different target role."},
        {"constraints": ["Different boundary."]},
    ],
)
async def test_every_definition_semantic_field_separates_cache_entries(
    tmp_path: Path,
    updates: dict[str, Any],
) -> None:
    planner = _Planner()
    cache = CachedPlanner(planner, tmp_path)
    original = _request(relation_type_definitions=[_definition()])
    await cache.plan(original)
    await cache.plan(original)
    await cache.plan(_request(relation_type_definitions=[_definition(**updates)]))
    await cache.plan(_request(available_relation_types=["CALIBRATED_BY"]))
    assert cache.hits == 1
    assert len(planner.requests) == 3


def _load_catalog() -> list[RelationTypeDefinition]:
    return TypeAdapter(list[RelationTypeDefinition]).validate_json(CATALOG.read_bytes())


async def test_benchmark_passes_one_global_catalog_without_gold_or_score_changes() -> (
    None
):
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    definitions = _load_catalog()
    assert [item.name for item in definitions] == dataset.relation_types
    planner = _Planner()
    baseline = await run_relation_planner_quality(dataset, planner)
    planner.requests.clear()
    report = await run_relation_planner_quality(
        dataset, planner, relation_type_definitions=definitions
    )
    assert report["relation_catalog"]["mode"] == "definitions"
    assert report["relation_catalog"]["definition_count"] == 16
    assert report["dataset"] == baseline["dataset"]
    assert report["scoring_version"] == baseline["scoring_version"]
    for key in report["metrics"]:
        if key != "latency_ms":
            assert report["metrics"][key] == baseline["metrics"][key]
    for request in planner.requests:
        assert request.relation_type_definitions == definitions
        assert set(request.to_planner_input()) == {
            "query",
            "now",
            "default_subject",
            "default_subject_id",
            "available_relation_types",
            "relation_type_definitions",
        }


async def test_invalid_benchmark_catalog_stops_before_planner_calls() -> None:
    planner = _Planner()
    with pytest.raises(ValidationError, match="host allowlist"):
        await run_relation_planner_quality(
            load_ablation_dataset(DEFAULT_DATASET),
            planner,
            relation_type_definitions=[_definition()],
        )
    assert planner.requests == []


async def test_client_facade_forwards_definitions() -> None:
    planner = _Planner(relation_types=["CALIBRATED_BY"])
    client = DoppelClient(store=InMemoryStore())
    result = await client.query_personal_memory(
        "sensor",
        [MemoryScope(user_id="owner", agent_id="assistant")],
        planner=planner,
        now=NOW,
        relation_type_definitions=[_definition()],
    )
    assert result.plan.relation_types == ["CALIBRATED_BY"]
    assert planner.requests[0].relation_type_definitions == [_definition()]


async def test_failfast_report_fingerprints_include_catalog_even_for_not_run_cases() -> (
    None
):
    class AuthFailure(_Planner):
        async def plan(
            self, request: PersonalMemoryQueryRequest
        ) -> PersonalMemoryQueryDraft:
            self.requests.append(request)
            raise StructuredOutputProviderError(
                "authentication_error", "redacted", status_code=401
            )

    dataset = load_ablation_dataset(DEFAULT_DATASET)
    definitions = _load_catalog()
    planner = AuthFailure()
    report = await run_relation_planner_quality(
        dataset, planner, relation_type_definitions=definitions
    )
    assert len(planner.requests) == 1
    assert report["metrics"]["not_run_case_count"] == 64
    for case, query in zip(report["cases"], dataset.queries, strict=True):
        assert case["request_fingerprint"] == _fingerprint(
            _query_request(dataset, query, definitions).to_planner_input()
        )


async def test_replay_preserves_catalog_identity_and_supports_legacy_reports(
    tmp_path: Path,
) -> None:
    dataset = load_ablation_dataset(DEFAULT_DATASET)
    definitions = _load_catalog()
    report = await run_relation_planner_quality(
        dataset, _Planner(), relation_type_definitions=definitions
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="catalog fingerprint"):
        ReplayPlanner(path, dataset=dataset)
    replay = ReplayPlanner(path, dataset=dataset, relation_type_definitions=definitions)
    request = _query_request(dataset, dataset.queries[0], definitions)
    assert await replay.plan(request) == PersonalMemoryQueryDraft()
    with pytest.raises(ValueError, match="request fingerprint"):
        await replay.plan(_query_request(dataset, dataset.queries[0]))
    legacy = await run_relation_planner_quality(dataset, _Planner())
    legacy.pop("relation_catalog")
    path.write_text(json.dumps(legacy), encoding="utf-8")
    assert (
        await ReplayPlanner(path, dataset=dataset).plan(
            _query_request(dataset, dataset.queries[0])
        )
        == PersonalMemoryQueryDraft()
    )


async def test_catalog_cli_offline_and_strict_unknown_fields(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    args = _parser().parse_args(
        [
            "--relation-catalog",
            str(CATALOG),
            "--output",
            str(output),
            "--no-cache",
            "--max-structural-failures",
            "65",
        ]
    )
    await _async_main(args)
    report = json.loads(output.read_bytes())
    assert report["relation_catalog"]["definition_count"] == 16
    assert report["usage"]["calls_with_usage"] == 0
    assert output.with_suffix(".json.sha256").is_file()
    invalid = tmp_path / "invalid.json"
    invalid.write_text('[{"name":"HELD_BY","query_id":"gold"}]', encoding="utf-8")
    args.relation_catalog = invalid
    with pytest.raises(ValidationError):
        await _async_main(args)

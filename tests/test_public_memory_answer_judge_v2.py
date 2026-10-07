"""Synthetic Judge v2 boundaries; no provider, network or benchmark-score claim."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from benchmarks.public_memory_answer_judge_v2 import (
    CONTROLS_SCHEMA,
    JudgeCase,
    JudgeV2Error,
    _contains,
    _request_sha256,
    build_judge_request,
    build_plan,
    build_preserved_cases,
    compare_with_audit,
    derive_row_support,
    judge_case_output,
    load_controls,
    main,
    run_arm,
    summarise_judgments,
)
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig
from tests.test_public_memory_answer_audit import report_fixture
from tests.test_public_memory_answer_comparison import RecordingFactory

CONTROLS_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "datasets"
    / ("judge-v2-controls-v1.json")
)


def config(**overrides: Any) -> OpenAICompatibleStructuredOutputConfig:
    payload: dict[str, Any] = {
        "model": "fake-judge-v2",
        "base_url": "https://example.invalid/v1",
        "schema_mode": "json_object",
        "max_completion_tokens": 3072,
        "max_tokens_parameter": "max_tokens",
        "temperature": 0.0,
        "thinking": "disabled",
        "timeout_seconds": 120.0,
    }
    payload.update(overrides)
    return OpenAICompatibleStructuredOutputConfig.model_validate(payload)


def cited_entries(request: Any) -> list[dict[str, Any]]:
    ids = request.input["candidate_answer"]["cited_memory_ids"]
    texts = {
        item["memory_id"]: item["text"]
        for item in request.input["supplied_context_items"]
    }
    return [
        {
            "memory_id": memory_id,
            "support": "supported",
            "contradicts_answer": False,
            "quote": texts[memory_id][:30],
            "reason": "the cited text states what the answer relies on",
        }
        for memory_id in ids
    ]


def judge_response(request: Any, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "answer_match": "correct",
        "answer_match_reason": "agrees with the reference answer",
        "answer_makes_factual_claims": True,
        "commitment": "committed",
        "commitment_reason": "states the requested information",
        "citation_judgments": cited_entries(request),
        "absence_claim_checks": [],
        "faithfulness": "grounded",
        "faithfulness_reason": "claims match the supplied items",
    }
    base.update(overrides)
    return base


async def rows_fixture(tmp_path: Path) -> tuple[Any, list[JudgeCase], dict[str, Any]]:
    fx, report_path, _ = await report_fixture(tmp_path)
    cases, binding = build_preserved_cases(
        report_path, fx.comparison_path, fx.dataset_path
    )
    plan = build_plan(
        cases,
        arm="rows",
        controls_sha256=None,
        binding=binding,
        provider_config=config(),
        max_calls=18,
    )
    return fx, cases, plan


async def test_judge_request_hides_profiles_labels_and_flags(tmp_path: Path) -> None:
    _, cases, _ = await rows_fixture(tmp_path)
    request = build_judge_request(cases[0])
    payload = json.dumps(request.input, ensure_ascii=False)
    assert "raw_vector" not in payload and "memory_vector" not in payload
    assert "answer_correct" not in payload and "citation_supported" not in payload
    assert "old_judge" not in payload and "audit" not in payload.lower()
    assert "retrieval_or_packing_loss" not in payload
    assert "abstained" not in payload
    assert request.input["question"] and request.input["reference_answer"]
    assert request.input["candidate_answer"]["text"]
    assert len(request.input["supplied_context_items"]) >= 1
    assert request.instructions
    assert request.output_schema["title"] == "MemoryAnswerJudgeV2"
    assert set(request.input) == {
        "question",
        "question_reference_time",
        "reference_answer",
        "candidate_answer",
        "supplied_context_items",
    }


async def test_preserved_cases_bind_and_dedupe(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)
    assert len(cases) == 18
    assert plan["input_binding"]["logical_rows"] == 18
    distinct = {_request_sha256(build_judge_request(case)) for case in cases}
    assert len(distinct) == 17

    broken = deepcopy(plan)
    broken["case_keys_sha256"] = "0" * 64
    broken["plan_fingerprint"] = ""
    with pytest.raises(JudgeV2Error):
        await run_arm(
            cases,
            broken,
            run_dir=tmp_path / "nope",
            api_key="",
            cache_only=True,
            provider_factory=RecordingFactory(judge_response),
        )


@pytest.mark.parametrize(
    ("claims", "judged", "cited", "expected"),
    [
        (False, [], 0, "not_applicable"),
        (False, [{"support": "supported"}], 2, "not_applicable"),
        (True, [], 0, "unsupported"),
        (True, [{"support": "supported"}], 1, "supported"),
        (True, [{"support": "supported"}, {"support": "supported"}], 2, "supported"),
        (True, [{"support": "unsupported"}], 1, "unsupported"),
        (
            True,
            [{"support": "supported"}, {"support": "unsupported"}],
            2,
            "partially_supported",
        ),
        (True, [{"support": "partially_supported"}], 1, "partially_supported"),
    ],
)
def test_support_rule_is_frozen_and_code_derived(
    claims: bool, judged: list[dict[str, str]], cited: int, expected: str
) -> None:
    assert derive_row_support(claims, judged, cited)[0] == expected


async def test_judge_output_binding_and_text_hits(tmp_path: Path) -> None:
    _, cases, _ = await rows_fixture(tmp_path)
    case = cases[0]
    request = build_judge_request(case)
    valid = judge_response(request)
    derived = judge_case_output(case, valid)
    assert derived["citation_support"] == "supported"
    assert derived["citation_contradiction"] is False
    assert all(entry["text_hit"] for entry in derived["citation_judgments"])

    missing = judge_response(request)
    missing["citation_judgments"] = missing["citation_judgments"][:-1]
    with pytest.raises(JudgeV2Error, match="do not match the cited ids"):
        judge_case_output(case, missing)

    extra = judge_response(request)
    extra["citation_judgments"] = extra["citation_judgments"] + [
        {
            "memory_id": "mem-unknown",
            "support": "supported",
            "contradicts_answer": False,
            "quote": "x",
            "reason": "y",
        }
    ]
    with pytest.raises(JudgeV2Error, match="do not match the cited ids"):
        judge_case_output(case, extra)

    duplicated = judge_response(request)
    duplicated["citation_judgments"] = duplicated["citation_judgments"] * 2
    with pytest.raises(JudgeV2Error, match="repeated a cited record"):
        judge_case_output(case, duplicated)


def test_quote_hit_binds_one_record_not_the_concatenation() -> None:
    items = (
        {
            "memory_id": "mem-a",
            "channel": "raw",
            "role": "user",
            "authority": "human_self",
            "observed_at": "2023-01-01T00:00:00+00:00",
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
            "text": "alpha beta",
        },
        {
            "memory_id": "mem-b",
            "channel": "raw",
            "role": "user",
            "authority": "human_self",
            "observed_at": "2023-01-02T00:00:00+00:00",
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
            "text": "gamma delta",
        },
    )
    case = JudgeCase(
        case_key="synthetic",
        arm="controls",
        question="q",
        question_reference_time="2023-01-03T00:00:00+00:00",
        reference_answer="a",
        candidate_answer="alpha beta gamma delta",
        cited_memory_ids=("mem-a", "mem-b"),
        context_items=items,
        provenance={"control_id": "synthetic"},
    )
    output = {
        "answer_match": "correct",
        "answer_match_reason": "r",
        "answer_makes_factual_claims": True,
        "commitment": "committed",
        "commitment_reason": "r",
        "citation_judgments": [
            {
                "memory_id": "mem-a",
                "support": "supported",
                "contradicts_answer": False,
                "quote": "alpha beta gamma",
                "reason": "spans another record",
            },
            {
                "memory_id": "mem-b",
                "support": "supported",
                "contradicts_answer": False,
                "quote": "gamma delta",
                "reason": "inside this record",
            },
        ],
        "absence_claim_checks": [
            {
                "claim_quote": "not written here",
                "true_for_supplied_context": True,
                "reason": "synthetic",
            }
        ],
        "faithfulness": "grounded",
        "faithfulness_reason": "r",
    }
    derived = judge_case_output(case, output)
    hits = {
        entry["memory_id"]: entry["text_hit"] for entry in derived["citation_judgments"]
    }
    assert hits == {"mem-a": False, "mem-b": True}
    check = derived["absence_claim_checks"][0]
    assert check["claim_text_hit"] is False
    assert check["true_for_supplied_context"] is True


async def test_contradiction_and_metrics_are_independent(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)

    def responder(request: Any) -> dict[str, Any]:
        entries = cited_entries(request)
        if entries:
            entries[0] = {
                **entries[0],
                "support": "unsupported",
                "contradicts_answer": True,
                "reason": "contradicts a premise of the answer",
            }
        return judge_response(request, citation_judgments=entries)

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "judge-run",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    assert report["status"] == "complete"
    metrics = report["metrics"]
    assert metrics["judged_rows"] == 18
    assert metrics["citation_contradictions"] == 18
    # Every synthetic row cites one record, which the judge contradicts.
    assert metrics["citation_support"]["unsupported"] == 18
    assert metrics["citation_support"]["partially_supported"] == 0
    assert metrics["citation_support"]["supported"] == 0
    assert metrics["citation_supported_successes"] == 0
    assert metrics["answer_correct_lenient"] == "18/18"
    assert metrics["explicit_conclusion_rate"] == "18/18"
    assert report["judge_saw_profile_or_old_labels"] is False
    assert report["reference_answer_phrase_checks_used"] is False
    assert report["retrieval_or_packing_attribution_emitted"] is False
    assert set(report["profile_summary"]) == {
        "raw_vector",
        "raw_vector_reranked",
        "memory_vector",
        "memory_vector_reranked",
        "combined_vector",
        "combined_vector_reranked",
    }


async def test_sensitivity_and_not_applicable_never_count_as_supported(
    tmp_path: Path,
) -> None:
    _, cases, plan = await rows_fixture(tmp_path)

    def responder(request: Any) -> dict[str, Any]:
        entries = cited_entries(request)
        for index, entry in enumerate(entries):
            entries[index] = {**entry, "support": "unsupported"}
        return judge_response(
            request,
            answer_match="incorrect",
            answer_makes_factual_claims=False,
            commitment="refused_unavailable",
            citation_judgments=entries,
        )

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "judge-run",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    metrics = report["metrics"]
    assert metrics["citation_support"]["not_applicable"] == 18
    assert metrics["citation_supported_successes"] == 0
    assert metrics["answer_correct_lenient"] == "0/18"
    assert metrics["answer_correct_or_partial"] == "0/18"
    assert metrics["answer_correct_strict_committed"] == "0/18"
    assert metrics["explicit_conclusion_rate"] == "0/18"
    assert metrics["non_refusal_rate"] == "0/18"
    assert metrics["abstained_flag_consistency"] in {"18/18", "0/18"}


def test_metrics_report_lenient_and_strict_counts() -> None:
    def row(match: str, commitment: str, support: str, contradiction: bool) -> dict:
        return {
            "judge": {
                "status": "completed",
                "label": {
                    "answer_match": match,
                    "commitment": commitment,
                    "citation_support": support,
                    "citation_contradiction": contradiction,
                    "faithfulness": "grounded",
                    "citation_judgments": [],
                    "absence_claim_checks": [],
                },
            },
            "abstained_consistent": True,
        }

    rows = [
        row("correct", "committed", "supported", False),
        row("correct", "hedged_derivation", "supported", False),
        row("partially_correct", "committed", "partially_supported", False),
        row("incorrect", "refused_unavailable", "not_applicable", False),
    ]
    metrics = summarise_judgments(rows)
    assert metrics["answer_correct_lenient"] == "2/4"
    assert metrics["answer_correct_or_partial"] == "3/4"
    assert metrics["answer_correct_strict_committed"] == "1/4"
    assert metrics["explicit_conclusion_rate"] == "2/4"
    assert metrics["non_refusal_rate"] == "3/4"
    assert metrics["citation_supported_successes"] == 2


async def test_cache_reuse_and_key_free_replay(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)
    run_dir = tmp_path / "judge-run"
    first = RecordingFactory(judge_response)
    report = await run_arm(
        cases,
        plan,
        run_dir=run_dir,
        api_key="SECRET-KEY",
        cache_only=False,
        provider_factory=first,
    )
    assert report["status"] == "complete"
    assert report["budget"]["new_judge_calls"] == 17
    assert first.calls == 17

    second = RecordingFactory(judge_response)
    replay = await run_arm(
        cases,
        plan,
        run_dir=run_dir,
        api_key="",
        cache_only=True,
        provider_factory=second,
    )
    assert second.calls == 0
    assert replay["budget"]["new_judge_calls"] == 0
    assert replay["status"] == "complete"
    assert [row["judge"]["label"] for row in replay["rows"]] == [
        row["judge"]["label"] for row in report["rows"]
    ]
    assert "SECRET-KEY" not in json.dumps(report, ensure_ascii=False)

    def forbidden(request: Any) -> dict[str, Any]:
        raise AssertionError("cache-only must not reach the provider")

    empty = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "empty",
        api_key="",
        cache_only=True,
        provider_factory=RecordingFactory(forbidden),
    )
    assert empty["status"] == "partial"
    assert {row["judge"]["failure_class"] for row in empty["rows"]} <= {
        "missing_cached_output",
        "duplicate_of_failed_request",
    }
    assert empty["budget"]["ledger"]["attempts_reserved"] == 0


async def test_invalid_output_is_preserved_not_retried(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)

    def responder(request: Any) -> dict[str, Any]:
        return {"answer_match": "correct"}

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "judge-run",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    assert report["status"] == "partial"
    failed_classes = {row["judge"]["failure_class"] for row in report["rows"]}
    assert failed_classes <= {
        "invalid_structured_output",
        "duplicate_of_failed_request",
    }
    assert "invalid_structured_output" in failed_classes
    assert report["budget"]["new_judge_calls"] == 17
    assert report["metrics"]["judged_rows"] == 0

    def unbound(request: Any) -> dict[str, Any]:
        response = judge_response(request)
        response["citation_judgments"] = []
        return response

    unbound_report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "run2",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(unbound),
    )
    assert all(
        row["judge"]["failure_class"] == "invalid_judge_output"
        for row in unbound_report["rows"]
        if row["judge"]["failure_class"] is not None
        or row["judge"]["execution"] != "duplicate_request_in_invocation"
    )


async def test_key_redaction_in_failures(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)

    def responder(request: Any) -> dict[str, Any]:
        raise ValueError("SECRET-JUDGE-KEY leaked")

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "judge-run",
        api_key="SECRET-JUDGE-KEY",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    assert "SECRET-JUDGE-KEY" not in json.dumps(report, ensure_ascii=False)


def test_frozen_controls_are_valid_and_complete() -> None:
    cases = load_controls(CONTROLS_PATH)
    assert len(cases) == 6
    assert {case.provenance["group"] for case in cases} == {
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    }
    document = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))
    assert document["controls_schema"] == CONTROLS_SCHEMA
    assert document["frozen"] is True
    for case in cases:
        assert case.expected is not None
        assert case.question and case.candidate_answer
        ids = {item["memory_id"] for item in case.context_items}
        assert set(case.cited_memory_ids) <= ids

    broken = dict(document)
    broken["controls_schema"] = "wrong"
    path = CONTROLS_PATH.parent / "broken-controls.json"
    path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    try:
        with pytest.raises(JudgeV2Error, match="controls schema"):
            load_controls(path)
    finally:
        path.unlink()


async def test_controls_arm_matches_frozen_expectations(tmp_path: Path) -> None:
    cases = load_controls(CONTROLS_PATH)
    plan = build_plan(
        cases,
        arm="controls",
        controls_sha256="f" * 64,
        binding={"controls_sha256": "f" * 64},
        provider_config=config(),
        max_calls=6,
    )

    def expected_for(case: JudgeCase) -> dict[str, Any]:
        assert case.expected is not None
        return dict(case.expected)

    markers = {
        "c1": {
            "answer_match": "incorrect",
            "commitment": "refused_unavailable",
            "citation_support": "supported",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        },
        "c2": {
            "answer_match": "correct",
            "commitment": "hedged_derivation",
            "citation_support": "supported",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        },
        "c3": {
            "answer_match": "incorrect",
            "commitment": "refused_conflicting_premise",
            "citation_support": "partially_supported",
            "citation_contradiction": True,
            "faithfulness": "partly_grounded",
        },
        "c4": {
            "answer_match": "incorrect",
            "commitment": "refused_unavailable",
            "citation_support": "not_applicable",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        },
        "c5": {
            "answer_match": "correct",
            "commitment": "committed",
            "citation_support": "supported",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        },
        "c6": {
            "answer_match": "correct",
            "commitment": "committed",
            "citation_support": "supported",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        },
    }
    needles = {
        "c1": "No earlier status tier is recorded",
        "c2": "worked out to about $12",
        "c3": "cannot compute the per-mug price",
        "c4": "do not have any record",
        "c5": "such as Ruby, Python, or PHP",
        "c6": "reached 20,000 miles and became eligible",
    }

    def responder(request: Any) -> dict[str, Any]:
        text = request.input["candidate_answer"]["text"]
        chosen = None
        for key, needle in needles.items():
            if needle in text:
                chosen = key
                break
        assert chosen is not None
        labels = markers[chosen]
        entries = cited_entries(request)
        if labels["citation_contradiction"]:
            entries[0] = {
                **entries[0],
                "support": "unsupported",
                "contradicts_answer": True,
            }
            entries[1] = {**entries[1], "support": "supported"}
        elif labels["citation_support"] == "partially_supported":
            entries[0] = {**entries[0], "support": "supported"}
        return judge_response(
            request,
            answer_match=labels["answer_match"],
            commitment=labels["commitment"],
            answer_makes_factual_claims=labels["citation_support"] != "not_applicable",
            citation_judgments=entries,
            faithfulness=labels["faithfulness"],
        )

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "controls",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    assert report["status"] == "complete"
    assert report["gate"]["passed"] is True
    assert report["gate"]["mismatched_controls"] == []
    assert report["gate"]["invalid_controls"] == []
    for case in cases:
        assert expected_for(case)


async def test_controls_gate_fails_on_a_broken_judge(tmp_path: Path) -> None:
    cases = load_controls(CONTROLS_PATH)
    plan = build_plan(
        cases,
        arm="controls",
        controls_sha256="f" * 64,
        binding={"controls_sha256": "f" * 64},
        provider_config=config(),
        max_calls=6,
    )

    def responder(request: Any) -> dict[str, Any]:
        return judge_response(
            request,
            answer_match="correct",
            commitment="committed",
            answer_makes_factual_claims=True,
        )

    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "controls",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(responder),
    )
    assert report["gate"]["passed"] is False
    assert len(report["gate"]["mismatched_controls"]) >= 2


async def test_audit_comparison_is_reporting_only(tmp_path: Path) -> None:
    _, cases, plan = await rows_fixture(tmp_path)
    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "judge-run",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(judge_response),
    )
    decisions = [
        {
            "row": index,
            "answer_match": "incorrect",
            "commitment": "refused_unavailable",
            "citation_support": "not_applicable",
            "citation_contradiction": False,
            "faithfulness": "grounded",
        }
        for index in range(18)
    ]
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    comparison = compare_with_audit(report, path)
    assert comparison["mode"].startswith("reporting-only")
    assert comparison["rows_compared"] == 18
    assert comparison["agreement"]["answer_match"]["agree"] == 0
    assert comparison["agreement"]["answer_match"]["rows"] == 18
    assert (
        "audit"
        not in json.dumps(
            [build_judge_request(case).input for case in cases], ensure_ascii=False
        ).lower()
    )


def test_cli_preflight_and_no_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fx_comparison = CONTROLS_PATH
    output = tmp_path / "controls-preflight.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "public_memory_answer_judge_v2",
            "--arm",
            "controls",
            "--controls",
            str(fx_comparison),
            "--output",
            str(output),
            "--run-dir",
            str(tmp_path / "run"),
        ],
    )
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "preflight-no-provider"
    assert report["logical_rows"] == 6
    assert report["distinct_judge_requests"] == 6
    assert report["contains_profile_names"] is False
    assert report["contains_old_judge_fields"] is False
    assert report["contains_audit_labels"] is False
    assert not (tmp_path / "run").exists()
    assert "output:" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main()


def test_contains_normalizes_whitespace_and_case() -> None:
    assert _contains("Hello   World", "hello world") is True
    assert _contains("alpha beta", "beta gamma") is False

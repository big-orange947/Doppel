"""Synthetic boundary tests, not model rubric calibration or benchmark scores."""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import replace

import pytest

from benchmarks.public_memory_answer_judge_v2 import JudgeV2Error, load_controls
from benchmarks.public_memory_answer_judge_v21 import (
    CAPS,
    LABEL_FIELDS,
    STABILITY_INDICES,
    build_plan,
    build_request,
    control_gate,
    derive_label,
    main,
    require_gate,
    run_arm,
    stability_cases,
)
from tests.test_public_memory_answer_comparison import RecordingFactory
from tests.test_public_memory_answer_judge_v2 import CONTROLS_PATH, config


def observation(case):
    """Prescribed fake observations for protocol tests, never a live model score."""
    expected = case.expected
    items = {i["memory_id"]: i for i in case.context_items}
    contradiction = expected["citation_contradiction"]
    citations = [
        {
            "memory_id": key,
            "support": "unsupported"
            if contradiction and index == len(case.cited_memory_ids) - 1
            else "supported",
            "contradicts_answer": contradiction
            and index == len(case.cited_memory_ids) - 1,
            "quote": items[key]["text"],
            "reason": "prescribed synthetic observation",
        }
        for index, key in enumerate(case.cited_memory_ids)
    ]
    return {
        "answer_match": expected["answer_match"],
        "answer_match_reason": "synthetic",
        "answer_makes_factual_claims": bool(case.cited_memory_ids),
        "commitment": "refused_unavailable"
        if contradiction
        else expected["commitment"],
        "commitment_reason": "prescribed base commitment",
        "citation_judgments": citations,
        "absence_claim_checks": [
            {
                "claim_quote": case.candidate_answer,
                "true_for_supplied_context": not contradiction,
                "reason": "synthetic",
            }
        ]
        if expected["commitment"].startswith("refused")
        else [],
        "faithfulness": expected["faithfulness"],
        "faithfulness_reason": "synthetic",
    }


def fixture():
    cases = load_controls(CONTROLS_PATH)
    sha = hashlib.sha256(CONTROLS_PATH.read_bytes()).hexdigest()
    plan = build_plan(
        cases, arm="controls", binding={"controls_sha256": sha}, config=config()
    )
    payloads = {c.candidate_answer: observation(c) for c in cases}
    return (
        cases,
        sha,
        plan,
        RecordingFactory(
            lambda request: deepcopy(
                payloads[request.input["candidate_answer"]["text"]]
            )
        ),
    )


def test_payload_blind_to_expected_profile_audit_flags():
    cases, _, _, _ = fixture()
    for case in cases:
        poisoned = replace(
            case,
            expected={"AUDIT_SECRET": True},
            provenance={"profile": "PROFILE_SECRET", "reader_abstained_flag": True},
        )
        assert build_request(poisoned) == build_request(case)
        assert "SECRET" not in json.dumps(build_request(poisoned).input)
    assert "observed_at is the observation time" in build_request(cases[0]).instructions


@pytest.mark.parametrize("base", ["committed", "hedged_derivation", "no_claim"])
def test_false_absence_does_not_turn_a_nonrefusal_into_refusal(base):
    case = fixture()[0][2]
    raw = observation(case)
    raw["commitment"] = base
    label = derive_label(case, raw)
    assert label["commitment"] == base and label["model_commitment"] == base


def test_escalation_preserves_model_taxonomy_and_observations():
    case = fixture()[0][2]
    raw = observation(case)
    label = derive_label(case, raw)
    assert raw["commitment"] == "refused_unavailable"
    assert label["model_commitment"] == "refused_unavailable"
    assert label["commitment"] == "refused_conflicting_premise"
    assert label["false_absence_claims"] == 1
    assert label["citation_contradiction"] is True


def test_claims_scope_conflict_does_not_silently_override_support():
    case = fixture()[0][3]
    raw = observation(case)
    raw["answer_makes_factual_claims"] = True
    label = derive_label(case, raw)
    assert label["claims_scope_conflict"] is True
    assert label["citation_support"] == "unsupported"
    raw["absence_claim_checks"] = []
    assert derive_label(case, raw)["claims_scope_conflict"] is False


@pytest.mark.parametrize("field", ["citation", "absence"])
def test_unanchored_observation_cannot_drive_a_host_label(field):
    case = fixture()[0][2]
    raw = observation(case)
    if field == "citation":
        raw["citation_judgments"][0]["quote"] = "not in this named source"
    else:
        raw["absence_claim_checks"][0]["claim_quote"] = "not in the candidate answer"
    with pytest.raises(JudgeV2Error, match="not anchored"):
        derive_label(case, raw)


def test_contradiction_caps_all_supported_even_with_model_inconsistency():
    case = fixture()[0][2]
    raw = observation(case)
    for entry in raw["citation_judgments"]:
        entry["support"] = "supported"
    assert derive_label(case, raw)["citation_support"] == "partially_supported"


async def test_new_plan_cache_replay_and_cumulative_budget(tmp_path):
    cases, _, plan, provider = fixture()
    first = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "run",
        api_key="SECRET_KEY",
        cache_only=False,
        provider_factory=provider,
    )
    assert first["status"] == "complete" and first["gate"]["passed"]
    assert first["budget"]["new_judge_calls"] == 6
    assert first["metrics"]["host_escalated_commitments"] == 1
    assert first["metrics"]["citation_support"]["not_applicable"] == 1
    assert first["metrics"]["support_applicable_rows"] == 5
    assert "SECRET_KEY" not in json.dumps(first)
    _, _, _, replay_provider = fixture()
    replay = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "run",
        api_key="",
        cache_only=True,
        provider_factory=replay_provider,
    )
    assert replay_provider.calls == 0
    assert replay["budget"]["new_judge_calls"] == 0
    assert replay["metrics"] == first["metrics"]
    assert [r["judge"]["label"] for r in replay["rows"]] == [
        r["judge"]["label"] for r in first["rows"]
    ]
    assert replay["budget"]["ledger"]["attempts_reserved"] == 6


@pytest.mark.parametrize(
    "change", ["wrong_report", "wrong_config", "tampered_label", "two_mismatches"]
)
async def test_rows_gate_revalidates_controls_not_a_boolean(tmp_path, change):
    cases, sha, plan, provider = fixture()
    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "run",
        api_key="",
        cache_only=False,
        provider_factory=provider,
    )
    require_gate(report, cases, config(), sha)
    if change == "wrong_report":
        report["runner"] = "old-v2"
    elif change == "wrong_config":
        report["plan"]["provider_config"]["model"] = "different"
    elif change == "tampered_label":
        report["rows"][0]["judge"]["label"]["answer_match"] = "correct"
    else:
        for case, row in zip(cases[:2], report["rows"][:2], strict=True):
            row["judge"]["model_output"]["answer_match"] = "partially_correct"
            row["judge"]["label"] = derive_label(case, row["judge"]["model_output"])
        report["gate"]["passed"] = True  # Not trusted.
    with pytest.raises(JudgeV2Error):
        require_gate(report, cases, config(), sha)


async def test_changed_case_payload_fails_before_provider(tmp_path):
    cases, _, plan, provider = fixture()
    cases[0] = replace(cases[0], candidate_answer="different answer")
    with pytest.raises(JudgeV2Error, match="payload changed"):
        await run_arm(
            cases,
            plan,
            run_dir=tmp_path / "run",
            api_key="",
            cache_only=False,
            provider_factory=provider,
        )
    assert provider.calls == 0 and not (tmp_path / "run").exists()


async def test_unanchored_response_retained_failed_not_retried(tmp_path):
    cases, _, plan, _ = fixture()
    payloads = {c.candidate_answer: observation(c) for c in cases}
    for payload in payloads.values():
        if payload["citation_judgments"]:
            payload["citation_judgments"][0]["quote"] = "fabricated text"
    provider = RecordingFactory(
        lambda r: deepcopy(payloads[r.input["candidate_answer"]["text"]])
    )
    report = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "run",
        api_key="",
        cache_only=False,
        provider_factory=provider,
    )
    assert report["status"] == "partial" and not report["gate"]["passed"]
    assert provider.calls == 6
    assert any(
        r["judge"]["model_output"] is not None and r["judge"]["status"] == "failed"
        for r in report["rows"]
    )


async def test_stability_only_changes_cited_order_and_reports_changes(tmp_path):
    template = fixture()[0][1]
    cases = [
        replace(
            template, case_key=f"synthetic-{i}", arm="rows", provenance={"index": i}
        )
        for i in range(18)
    ]
    plan = build_plan(cases, arm="rows", binding={"synthetic": True}, config=config())
    provider = RecordingFactory(lambda r: observation(template))
    baseline = await run_arm(
        cases,
        plan,
        run_dir=tmp_path / "base",
        api_key="",
        cache_only=False,
        provider_factory=provider,
    )
    assert provider.calls == 1
    variants = stability_cases(cases, baseline, config())
    for case, index in zip(variants, STABILITY_INDICES, strict=True):
        original = build_request(cases[index]).model_dump(mode="json")
        changed = build_request(case).model_dump(mode="json")
        original["input"]["candidate_answer"]["cited_memory_ids"].reverse()
        assert original == changed
        assert "baseline_labels" not in json.dumps(changed)
    variant_plan = build_plan(
        variants, arm="stability", binding={"baseline": "synthetic"}, config=config()
    )
    changed = observation(template)
    changed["answer_match"] = "incorrect"
    results = await run_arm(
        variants,
        variant_plan,
        run_dir=tmp_path / "variant",
        api_key="",
        cache_only=False,
        provider_factory=RecordingFactory(lambda r: deepcopy(changed)),
    )
    assert results["label_agreement"]["answer_match"]["agree"] == 0
    assert results["label_agreement"]["citation_support"]["agree"] == 6
    assert set(results["label_agreement"]) == set(LABEL_FIELDS)


def test_cli_preflight_key_free_and_preserves_output(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    path = tmp_path / "preflight.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "judge-v21",
            "--arm",
            "controls",
            "--controls",
            str(CONTROLS_PATH),
            "--output",
            str(path),
            "--run-dir",
            str(tmp_path / "run"),
        ],
    )
    assert main() == 0
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["distinct_requests"] == 6 and report["api_key_read"] is False
    assert not (tmp_path / "run").exists()
    with pytest.raises(SystemExit):
        main()


def test_gate_must_cover_exact_control_set_and_caps_not_expandable():
    cases, _, _, _ = fixture()
    with pytest.raises(JudgeV2Error):
        control_gate(cases, [])
    with pytest.raises(JudgeV2Error):
        build_plan(cases[:1], arm="controls", binding={}, config=config())
    assert sum(CAPS.values()) == 30


def test_cli_exception_redacts_key_and_does_not_claim_zero_usage(tmp_path, monkeypatch):
    import benchmarks.public_memory_answer_judge_v21 as module

    async def broken(*args, **kwargs):
        raise RuntimeError("SECRET_PROVIDER_TEXT")

    monkeypatch.setattr(module, "run_arm", broken)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "SECRET_KEY")
    output = tmp_path / "failed.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "judge-v21",
            "--arm",
            "controls",
            "--controls",
            str(CONTROLS_PATH),
            "--output",
            str(output),
            "--run-dir",
            str(tmp_path / "run"),
            "--live",
        ],
    )
    assert main() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["failure_type"] == "RuntimeError"
    assert report["budget"]["new_judge_calls"] is None
    assert "SECRET" not in json.dumps(report)

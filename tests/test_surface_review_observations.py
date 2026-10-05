"""Offline protocol checks are not evidence of live semantic model quality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks import surface_review_calibration as v1
from benchmarks import surface_review_calibration_v2 as runner
from benchmarks.surface_review_controls import build_baseline_request, fingerprint
from benchmarks.surface_review_controls import build_controls as build_v1_controls
from benchmarks.surface_review_controls_v2 import build_controls
from benchmarks.surface_review_observations import (
    build_observed_request,
    validate_observed_review,
)
from tests.test_surface_review_calibration import FakeProvider as V1FakeProvider
from tests.test_surface_review_calibration import _response


def observed_response(control: Any) -> dict[str, Any]:
    """Deliberately idealized fixtures: only test schema/scoring/workflow plumbing."""
    raw = _response(control, True)
    raw["query_observations"] = [
        {
            "surface_key": q["surface_key"],
            "mode": "neutral",
            "contract": "neutral_required",
            "query_quote": q["authored_query"],
            "brief_quote": q["semantic_brief"],
            "explanation": "离线预置观察，不代表模型性能。",
        }
        for q in control.reviewer_input["queries"]
    ]
    raw["relation_observations"] = [
        {
            "surface_key": m["surface_key"],
            "field": field,
            "status": "bound",
            "source_entity_key": m["relation"]["source_entity_key"],
            "target_entity_key": m["relation"]["target_entity_key"],
            "source_quote": m[field],
            "target_quote": m[field],
            "explanation": "离线预置观察，不代表模型性能。",
        }
        for m in control.reviewer_input["memories"]
        if m.get("relation")
        for field in ("authored_content", "authored_edge_fact")
    ]
    return raw


def test_v1_immutable_and_v2_labels_not_sent() -> None:
    originals, revised = build_v1_controls(), build_controls()
    assert (
        fingerprint(originals)
        == "6bb7df9932077b198e4b365591bbd5cf65b93a91fb5b9e2b319ed09c7d5b9951"
    )
    assert len(revised) == 36 and sum(c.acceptable for c in revised) == 18
    assert (
        fingerprint(revised)
        == "1e04c7658cad564f3498b6f3278e374fb950912073690a2182f9cdc12d00f9d9"
    )
    for old, new in zip(originals, revised[:24], strict=True):
        assert build_baseline_request(old) == build_baseline_request(new)
        assert old.reviewer_input == new.reviewer_input
        assert old.allowed_issue_keys == new.allowed_issue_keys
        assert new.allowed_issue_codes == old.allowed_issue_codes + (
            ["temporal_mismatch"]
            if old.family == "return_and_readoption_lifecycle" and not old.acceptable
            else []
        )
    for c in revised:
        request = build_observed_request(build_baseline_request(c))
        encoded = json.dumps(request.model_dump(mode="json"))
        for private in (
            c.case_id,
            c.family,
            c.pair_id,
            "allowed_issue_keys",
            "allowed_issue_codes",
        ):
            assert private not in encoded
        assert "acceptable" not in json.dumps(request.input)
        assert (
            build_observed_request(
                build_baseline_request(
                    c.model_copy(update={"acceptable": not c.acceptable})
                )
            )
            == request
        )


def test_temporal_category_fix_is_explicit_rescoring_not_rewriting_v1() -> None:
    old, new = build_v1_controls()[18], build_controls()[18]
    issue = {
        "surface_key": "memory-b",
        "issue_code": "temporal_mismatch",
        "detail": "领养生命周期自相矛盾。",
    }
    assert v1.score_review(old, [issue])["missed_defect"]
    assert v1.score_review(new, [issue])["correct"]
    assert "temporal_mismatch" not in old.allowed_issue_codes


@pytest.mark.parametrize("mode", ["candidate_answer", "answerability_declaration"])
def test_query_observation_derives_contract_flag_without_model_issue(mode: str) -> None:
    c = build_controls()[2]
    raw = observed_response(c)
    raw["issues"] = []
    raw["query_observations"][0]["mode"] = mode
    review, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert review.issues == []
    assert len(effective) == 1 and effective[0]["issue_code"] == "answer_leak"
    assert effective[0]["sources"] == ["host_observation_comparison"]
    assert v1.score_review(c, effective)["correct"]


def test_confirmation_allowed_is_not_a_generic_ban_on_confirmation_queries() -> None:
    c = next(
        c
        for c in build_controls()
        if c.family == "permitted_confirmation_contract" and c.acceptable
    )
    raw = observed_response(c)
    raw["query_observations"][0].update(
        mode="candidate_answer", contract="confirmation_allowed"
    )
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert effective == []


def test_both_agreeing_fields_can_have_reversed_roles_and_are_merged() -> None:
    c = build_controls()[14]
    raw = observed_response(c)
    raw["issues"] = []
    for observation in raw["relation_observations"]:
        observation.update(
            source_entity_key="entity-b",
            target_entity_key="entity-a",
            source_quote="墨帆工作室",
            target_quote="江橙",
        )
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert len(effective) == 1 and effective[0]["issue_code"] == "relation_mismatch"
    assert len(effective[0]["citations"]) == 8
    assert v1.score_review(c, effective)["correct"]


def test_passive_word_order_is_not_endpoint_order_and_each_field_is_checked() -> None:
    c = next(
        c
        for c in build_controls()
        if c.family == "passive_and_active_custody" and c.acceptable
    )
    raw = observed_response(c)
    for observation in raw["relation_observations"]:
        observation.update(source_quote="红色测距仪", target_quote="顾秋")
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert effective == []
    c = next(
        c
        for c in build_controls()
        if c.family == "independent_content_edge_roles" and not c.acceptable
    )
    raw = observed_response(c)
    raw["issues"] = []
    raw["relation_observations"][1].update(
        source_entity_key="entity-b", target_entity_key="entity-a"
    )
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert v1.score_review(c, effective)["correct"]


def test_relation_not_expressed_has_grounded_flag_not_invented_binding() -> None:
    c = build_controls()[13]
    raw = observed_response(c)
    raw["issues"] = []
    raw["relation_observations"][1].update(
        status="not_expressed",
        source_entity_key="",
        target_entity_key="",
        target_quote="",
    )
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert v1.score_review(c, effective)["correct"]


@pytest.mark.parametrize(
    "fault",
    [
        "missing_query",
        "duplicate_query",
        "forged_query_quote",
        "forged_brief_quote",
        "uncertain_query",
        "missing_relation",
        "duplicate_relation",
        "unknown_endpoint",
        "forged_role_quote",
        "uncertain_relation",
        "not_expressed_invented_endpoint",
    ],
)
def test_incomplete_or_unverifiable_observations_are_errors(fault: str) -> None:
    c = (
        build_controls()[0]
        if fault
        in {
            "missing_query",
            "duplicate_query",
            "forged_query_quote",
            "forged_brief_quote",
            "uncertain_query",
        }
        else build_controls()[15]
    )
    raw = observed_response(c)
    if fault == "missing_query":
        raw["query_observations"] = []
    elif fault == "duplicate_query":
        raw["query_observations"] *= 2
    elif fault == "forged_query_quote":
        raw["query_observations"][0]["query_quote"] = "杜撰引用"
    elif fault == "forged_brief_quote":
        raw["query_observations"][0]["brief_quote"] = "杜撰引用"
    elif fault == "uncertain_query":
        raw["query_observations"][0]["mode"] = "uncertain"
    elif fault == "missing_relation":
        raw["relation_observations"].pop()
    elif fault == "duplicate_relation":
        raw["relation_observations"] *= 2
    elif fault == "unknown_endpoint":
        raw["relation_observations"][0]["source_entity_key"] = "ghost"
    elif fault == "forged_role_quote":
        raw["relation_observations"][0]["target_quote"] = "杜撰引用"
    elif fault == "uncertain_relation":
        raw["relation_observations"][0]["status"] = "uncertain"
    else:
        raw["relation_observations"][0]["status"] = "not_expressed"
    with pytest.raises(ValueError):
        validate_observed_review(build_observed_request(build_baseline_request(c)), raw)


def test_valid_quotes_cannot_prove_model_interpretation_correct_and_flags_are_not_waived() -> (
    None
):
    c = build_controls()[2]
    raw = observed_response(c)
    raw["issues"] = []
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert v1.score_review(c, effective)[
        "missed_defect"
    ]  # Model falsely called the supplied answer neutral.
    c = build_controls()[14]
    raw = observed_response(c)
    for r in raw["relation_observations"]:
        r.update(source_entity_key="entity-b", target_entity_key="entity-a")
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert effective[0]["sources"] == ["model_issue", "host_observation_comparison"]
    # A spurious model code is preserved rather than removed by a host check.
    raw["issues"][0]["issue_code"] = "duplicate_surface"
    _, effective = validate_observed_review(
        build_observed_request(build_baseline_request(c)), raw
    )
    assert len(effective) == 2 and not v1.score_review(c, effective)["correct"]


class FakeProvider(V1FakeProvider):
    async def generate(self, request: Any) -> dict[str, Any]:
        if self.observer:
            self.observer(
                {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130}
            )
        controls = {
            build_baseline_request(c).input["review_nonce"]: c for c in build_controls()
        }
        return observed_response(controls[request.input["review_nonce"]])


async def make_reference(
    tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, str]:
    monkeypatch.setenv("DOPPEL_API_KEY", "fake-only-key")
    monkeypatch.setattr(v1, "OpenAICompatibleStructuredOutputModel", V1FakeProvider)
    cache, output = tmp / "v1-cache", tmp / "v1.json"
    args = v1.parser().parse_args(
        [
            "--live",
            "--max-new-calls",
            "48",
            "--cache-dir",
            str(cache),
            "--progress-output",
            str(tmp / "v1-progress.json"),
            "--output",
            str(output),
        ]
    )
    assert await v1.run(args) == 0
    return output, cache, runner.acquire._sha256(output)


def args_for(
    tmp: Path, ref: tuple[Path, Path, str], calls: int, live: bool = True
) -> Any:
    values = [
        "--max-new-calls",
        str(calls),
        "--reference-report",
        str(ref[0]),
        "--reference-cache",
        str(ref[1]),
        "--reference-sha256",
        ref[2],
        "--cache-dir",
        str(tmp / "v2-cache"),
        "--output",
        str(tmp / "v2.json"),
        "--progress-output",
        str(tmp / "v2-progress.json"),
    ]
    if live:
        values.append("--live")
    return runner.parser().parse_args(values)


@pytest.mark.asyncio
async def test_dry_run_no_reference_or_key_or_network_or_file_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network/provider accessed")

    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", forbidden)
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    assert (
        await runner.run(
            args_for(
                tmp_path,
                (tmp_path / "absent.json", tmp_path / "absent-cache", "unused"),
                36,
                False,
            )
        )
        == 0
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_hash_bound_reference_budget_resume_and_free_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await make_reference(tmp_path, monkeypatch)
    before = {str(p): runner.acquire._sha256(p) for p in tmp_path.rglob("*.json")}
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(args_for(tmp_path, ref, 7)) == 2
    assert await runner.run(args_for(tmp_path, ref, 29)) == 0
    report = json.loads((tmp_path / "v2.json").read_text("utf-8"))
    assert report["provider_calls_cumulative"] == 36
    assert report["usage_cumulative"]["total_tokens"] == 4680
    assert report["reference"]["raw_response_count"] == 48
    assert (
        report["reference"]["original_usage_not_charged_to_v2"]["total_tokens"] == 6240
    )
    assert (
        report["gate"]["ok"] and not report["gate"]["blind_corpus_acceptance_granted"]
    )
    assert report["cohorts"]["opened_v1"]["control_count"] == 24
    assert report["cohorts"]["additional_development"]["control_count"] == 12
    for p, sha in before.items():
        assert runner.acquire._sha256(Path(p)) == sha
    monkeypatch.delenv("DOPPEL_API_KEY")
    args = args_for(tmp_path, ref, 0)
    args.output = tmp_path / "v2-replay.json"
    assert await runner.run(args) == 0
    replay = json.loads(args.output.read_text("utf-8"))
    assert (
        replay["last_invocation"]["provider_calls"] == 0
        and replay["last_invocation"]["cache_hits"] == 36
    )
    assert replay["usage_cumulative"] == report["usage_cumulative"]
    for p in tmp_path.rglob("*.json"):
        assert "fake-only-key" not in p.read_text("utf-8")
    with pytest.raises(ValueError, match="output exists"):
        await runner.run(args_for(tmp_path, ref, 36))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target", ["reference_report", "reference_cache", "candidate_cache"]
)
async def test_corrupt_artifacts_no_paid_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    ref = await make_reference(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    if target == "reference_report":
        ref[0].write_text("{}", "utf-8")
    elif target == "reference_cache":
        file = next(ref[1].glob("provider-output-v*/*/*.json"))
        file.write_text("{}", "utf-8")
    else:
        assert await runner.run(args_for(tmp_path, ref, 36)) == 0
        file = next((tmp_path / "v2-cache").glob("provider-output-v*/*/*.json"))
        file.write_text("{}", "utf-8")
    args = args_for(tmp_path, ref, 36)
    args.output = tmp_path / "diagnostic.json"
    if target == "candidate_cache":
        assert await runner.run(args) == 1
        report = json.loads(args.output.read_text("utf-8"))
        assert (
            report["last_invocation"]["provider_calls"] == 0
            and not report["gate"]["ok"]
        )
        assert file.read_text("utf-8") == "{}"
    else:
        with pytest.raises((ValueError, runner.ParentCacheIntegrityError)):
            await runner.run(args)
        assert not (tmp_path / "v2-cache").exists()


@pytest.mark.asyncio
async def test_reference_path_overlap_and_model_change_rejected_before_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await make_reference(tmp_path, monkeypatch)
    for change, value in (
        ("cache_dir", ref[1]),
        ("output", ref[0].parent / "v1-cache" / "oops.json"),
        ("model", "other-model"),
    ):
        args = args_for(tmp_path, ref, 36)
        setattr(args, change, value)
        with pytest.raises(ValueError):
            await runner.run(args)
    assert not (tmp_path / "v2-cache").exists()


@pytest.mark.asyncio
async def test_zero_budget_without_key_and_provider_failure_safe_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await make_reference(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    monkeypatch.delenv("DOPPEL_API_KEY")
    assert await runner.run(args_for(tmp_path, ref, 0)) == 2
    progress = json.loads((tmp_path / "v2-progress.json").read_text("utf-8"))
    assert (
        progress["provider_calls_cumulative"] == 0 and not progress["gate"]["complete"]
    )

    class Failing(FakeProvider):
        async def generate(self, request: Any) -> dict[str, Any]:
            raise runner.StructuredOutputProviderError(
                "authentication_error", "secret-response-body", status_code=401
            )

    monkeypatch.setenv("DOPPEL_API_KEY", "fake-only-key")
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", Failing)
    assert await runner.run(args_for(tmp_path, ref, 36)) == 2
    progress = json.loads((tmp_path / "v2-progress.json").read_text("utf-8"))
    assert (
        progress["provider_calls_cumulative"] == 1
        and progress["stopped"]["http_status"] == 401
    )
    assert "secret-response-body" not in json.dumps(progress)
    assert "fake-only-key" not in json.dumps(progress)

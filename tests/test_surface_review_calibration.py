"""No-label leakage, grounded quotes, strict cache, and bounded calibration workflow."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from benchmarks import surface_review_calibration as runner
from benchmarks.relation_planner_quality import PROVIDER_OUTPUT_CACHE_NAMESPACE
from benchmarks.surface_review_controls import (
    build_baseline_request,
    build_controls,
    fingerprint,
)
from benchmarks.surface_review_grounding import (
    build_grounded_request,
    validate_grounded_review,
)
from doppel_memory.openai_compatible import StructuredOutputProviderError


def _response(control: Any, grounded: bool) -> dict[str, Any]:
    slots = {
        s["surface_key"]: s
        for k in ("entities", "memories", "queries")
        for s in control.reviewer_input[k]
    }
    issues = []
    if not control.acceptable:
        key = control.allowed_issue_keys[0]
        issue: dict[str, Any] = {
            "surface_key": key,
            "issue_code": control.allowed_issue_codes[0],
            "detail": "离线测试的预置问题。",
        }
        if grounded:
            field = next(
                f for f in slots[key] if f.startswith("authored_") and slots[key][f]
            )
            issue["citations"] = [
                {"surface_key": key, "field": field, "quote": slots[key][field][:60]}
            ]
        issues.append(issue)
    return {"reviewed_surface_keys": list(slots), "issues": issues}


class FakeProvider:
    name = "tests.surface-review-calibration"
    version = "1"

    def __init__(
        self, config: Any, *, api_key: str, usage_observer: Any = None
    ) -> None:
        del config, api_key
        self.observer = usage_observer
        self.controls = {
            build_baseline_request(c).input["review_nonce"]: c for c in build_controls()
        }

    async def generate(self, request: Any) -> dict[str, Any]:
        if self.observer:
            self.observer(
                {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130}
            )
        return _response(
            self.controls[request.input["review_nonce"]],
            request.output_schema["title"] == "GroundedSurfaceReview",
        )

    async def aclose(self) -> None:
        pass


def _args(tmp_path: Path, calls: int, live: bool = True) -> Any:
    values = [
        "--max-new-calls",
        str(calls),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--progress-output",
        str(tmp_path / "progress.json"),
        "--output",
        str(tmp_path / "result.json"),
    ]
    if live:
        values.append("--live")
    return runner.parser().parse_args(values)


def test_controls_are_balanced_paired_and_labels_are_not_sent() -> None:
    controls = build_controls()
    assert len(controls) == 24 and sum(c.acceptable for c in controls) == 12
    assert len({c.case_id for c in controls}) == 24
    assert set(Counter(c.pair_id for c in controls).values()) == {2}
    assert len({c.family for c in controls}) == 12
    assert fingerprint(controls) == fingerprint(build_controls())
    assert (
        fingerprint(controls)
        == "6bb7df9932077b198e4b365591bbd5cf65b93a91fb5b9e2b319ed09c7d5b9951"
    )
    for c in controls:
        req = build_baseline_request(c)
        raw = json.dumps(req.model_dump(mode="json"))
        assert c.case_id not in raw and c.pair_id not in raw and c.family not in raw
        for key in (
            "acceptable",
            "allowed_issue_keys",
            "allowed_issue_codes",
            "expected_acceptable",
        ):
            assert key not in req.input
        assert (
            build_baseline_request(
                c.model_copy(update={"acceptable": not c.acceptable})
            )
            == req
        )
        assert (
            build_grounded_request(req).input["review_nonce"]
            == req.input["review_nonce"]
        )


@pytest.mark.parametrize(
    "fault",
    [
        "invented_quote",
        "wrong_field",
        "unknown_surface",
        "coverage",
        "duplicate_issue",
        "no_own_quote",
    ],
)
def test_grounding_rejects_invalid_citations_without_semantic_waivers(
    fault: str,
) -> None:
    c = next(c for c in build_controls() if not c.acceptable)
    req = build_grounded_request(build_baseline_request(c))
    raw = _response(c, True)
    citation = raw["issues"][0]["citations"][0]
    if fault == "invented_quote":
        citation["quote"] = "并不存在的引用字符串"
    elif fault == "wrong_field":
        citation["field"] = "authored_name"
    elif fault == "unknown_surface":
        citation["surface_key"] = "ghost"
    elif fault == "coverage":
        raw["reviewed_surface_keys"].append(raw["reviewed_surface_keys"][0])
    elif fault == "duplicate_issue":
        raw["issues"].append(raw["issues"][0])
    else:
        citation.update(
            surface_key="memory-a",
            field="authored_content",
            quote=c.reviewer_input["memories"][0]["authored_content"],
        )
    with pytest.raises(ValueError):
        validate_grounded_review(req, raw)


def test_valid_quote_is_not_proof_of_a_correct_conclusion() -> None:
    c = next(c for c in build_controls() if c.acceptable)
    req = build_grounded_request(build_baseline_request(c))
    raw = _response(c, True)
    raw["issues"] = [
        {
            "surface_key": "query-a",
            "issue_code": "answer_leak",
            "detail": "错误的测试结论。",
            "citations": [
                {
                    "surface_key": "query-a",
                    "field": "authored_query",
                    "quote": c.reviewer_input["queries"][0]["authored_query"],
                }
            ],
        }
    ]
    result = validate_grounded_review(req, raw)
    assert (
        runner.score_review(c, [i.model_dump(mode="json") for i in result.issues])[
            "false_positive"
        ]
        is True
    )


def test_missing_or_spurious_detections_do_not_pass_scoring() -> None:
    c = next(c for c in build_controls() if not c.acceptable)
    assert runner.score_review(c, [])["missed_defect"] is True
    issues = _response(c, False)["issues"]
    issues += [
        {
            "surface_key": "memory-a",
            "issue_code": "duplicate_surface",
            "detail": "多报。",
        }
    ]
    assert runner.score_review(c, issues)["correct"] is False
    summary = runner.summarize(build_controls(), [])
    assert not summary["gate"]["ok"]
    assert summary["profiles"]["grounded_v1"]["false_positive_rate"] is None
    assert summary["profiles"]["grounded_v1"]["defects_not_demonstrated"] == 12


@pytest.mark.asyncio
async def test_dry_run_never_constructs_provider_or_writes_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("provider accessed")

    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", forbidden)
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    assert await runner.run(_args(tmp_path, 48, live=False)) == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_budget_resume_and_cache_replay_do_not_double_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "fake-only-key")
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(_args(tmp_path, 10)) == 2
    progress = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert progress["provider_calls_cumulative"] == 10 and not progress["gate"]["ok"]
    assert not (tmp_path / "result.json").exists()
    assert await runner.run(_args(tmp_path, 38)) == 0
    report = json.loads((tmp_path / "result.json").read_text("utf-8"))
    assert report["provider_calls_cumulative"] == 48
    assert report["usage_cumulative"]["total_tokens"] == 6240
    assert (
        report["gate"]["ok"] and not report["gate"]["blind_corpus_acceptance_granted"]
    )
    monkeypatch.delenv("DOPPEL_API_KEY")
    args = _args(tmp_path, 0)
    args.output = tmp_path / "diagnostic-replay.json"
    assert await runner.run(args) == 0
    replay = json.loads(args.output.read_text("utf-8"))
    assert replay["last_invocation"]["provider_calls"] == 0
    assert replay["last_invocation"]["cache_hits"] == 48
    assert replay["provider_calls_cumulative"] == 48
    assert replay["usage_cumulative"] == report["usage_cumulative"]
    for path in tmp_path.rglob("*.json"):
        assert "fake-only-key" not in path.read_text("utf-8")
    with pytest.raises(ValueError, match="output exists"):
        await runner.run(_args(tmp_path, 48))


@pytest.mark.asyncio
async def test_zero_budget_requires_no_key_and_cannot_claim_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(_args(tmp_path, 0)) == 2
    report = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert report["provider_calls_cumulative"] == 0 and not report["gate"]["complete"]
    assert report["profiles"]["grounded_v1"]["false_positive_rate"] is None


@pytest.mark.asyncio
async def test_corrupt_cache_is_not_replaced_by_a_paid_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "fake-only-key")
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", FakeProvider)
    assert await runner.run(_args(tmp_path, 48)) == 0
    file = next((tmp_path / "cache" / PROVIDER_OUTPUT_CACHE_NAMESPACE).glob("*/*.json"))
    file.write_text('{"broken":true}', "utf-8")
    args = _args(tmp_path, 48)
    args.output = tmp_path / "corrupt-replay.json"
    assert await runner.run(args) == 1
    report = json.loads(args.output.read_text("utf-8"))
    assert not report["gate"]["ok"] and report["last_invocation"]["provider_calls"] == 0
    assert report["last_invocation"]["invalid_cache_entries"] == 1
    assert file.read_text("utf-8") == '{"broken":true}'


@pytest.mark.asyncio
async def test_provider_error_stops_without_body_or_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Failing(FakeProvider):
        async def generate(self, request: Any) -> dict[str, Any]:
            raise StructuredOutputProviderError(
                "authentication_error", "secret-response-body", status_code=401
            )

    monkeypatch.setenv("DOPPEL_API_KEY", "fake-only-key")
    monkeypatch.setattr(runner, "OpenAICompatibleStructuredOutputModel", Failing)
    assert await runner.run(_args(tmp_path, 48)) == 2
    report = json.loads((tmp_path / "progress.json").read_text("utf-8"))
    assert report["provider_calls_cumulative"] == 1
    assert report["stopped"]["http_status"] == 401
    assert "secret-response-body" not in json.dumps(
        report
    ) and "fake-only-key" not in json.dumps(report)

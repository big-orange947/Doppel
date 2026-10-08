"""Synthetic protocol checks, not evidence of live Reader intelligence."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

from benchmarks import public_memory_reader_v2 as reader
from benchmarks.public_memory_answer_comparison import (
    RUNNER as V1_RUNNER,
)
from benchmarks.public_memory_answer_comparison import (
    _canonical_sha256,
    _request_sha256,
    build_reader_request,
    build_rows,
)
from benchmarks.public_memory_pilot import _hash
from tests.test_public_memory_answer_comparison import (
    GOLD,
    RecordingFactory,
    config,
    fixture,
)


def setup(tmp_path):
    fx = fixture(tmp_path)
    rows = build_rows(fx.comparison, fx.cases, fx.manifest)
    baseline = {
        "runner": V1_RUNNER,
        "status": "complete",
        "plan": {"provider_config": config().model_dump(mode="json")},
        "input_sha256": {
            "dataset": reader._sha256(fx.dataset_path.read_bytes()),
            "manifest": reader._sha256(fx.manifest_path.read_bytes()),
            "comparison": fx.comparison_sha256,
        },
        "rows": [
            {
                "index": r.index,
                "case_id": r.case_id,
                "profile": r.profile,
                "reader": {
                    "status": "completed",
                    "request_sha256": _request_sha256(build_reader_request(r)),
                    "answer": "Previous answer.",
                    "abstained": False,
                    "cited_memory_ids": [r.context[0]["memory_id"]],
                },
            }
            for r in rows
        ],
    }
    binding = {
        **baseline["input_sha256"],
        "baseline": _canonical_sha256(baseline),
        "baseline_canonical": _canonical_sha256(baseline),
    }
    return fx, rows, baseline, reader.build_plan(rows, binding, config())


def response(request):
    ids = [i["memory_id"] for i in request.input["context_items"]]
    return {
        "answer": "A derived result with stated assumptions.",
        "abstained": False,
        "cited_memory_ids": ids,
        "derived": {
            "kind": "other",
            "input_memory_ids": ids,
            "result": "A derived result",
        },
    }


async def run(rows, baseline, plan, directory, factory, **kwargs):
    return await reader.run_reader(
        rows,
        baseline,
        plan,
        run_dir=directory,
        api_key="SYNTHETIC-SECRET",
        cache_only=kwargs.get("cache_only", False),
        provider_factory=factory,
    )


def test_request_is_gold_and_baseline_blind(tmp_path):
    _, rows, _, plan = setup(tmp_path)
    payload = reader.build_request(rows[0]).model_dump(mode="json")
    text = json.dumps(payload)
    assert GOLD not in text and "HISTORY_ONLY_SECRET" not in text
    assert "Previous answer." not in text
    assert set(payload["input"]) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    assert (
        "profile" not in payload["input"] and "reference_answer" not in payload["input"]
    )
    assert reader.build_request(rows[0]).input == build_reader_request(rows[0]).input
    changed = replace(rows[0], scoring=replace(rows[0].scoring, answer="NEW-GOLD"))
    assert reader.build_request(changed) == reader.build_request(rows[0])
    assert reader.CAP == 18 and plan["max_new_judge_calls"] == 0


@pytest.mark.parametrize(
    "derived",
    [None, {"kind": "ratio", "input_memory_ids": ["id"], "result": "7 units"}],
)
def test_optional_derived_schema(derived):
    output = reader.ReaderV2Output.model_validate(
        {
            "answer": "An answer",
            "abstained": False,
            "cited_memory_ids": ["id"],
            "derived": derived,
        }
    )
    assert (output.derived is not None) == (derived is not None)
    assert (
        reader.ReaderV2Output.model_validate(
            {"answer": "An answer", "abstained": False, "cited_memory_ids": []}
        ).derived
        is None
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"kind": "invented"},
        {"input_memory_ids": []},
        {"input_memory_ids": [" "]},
        {"result": " "},
        {"extra": True},
    ],
)
def test_invalid_derived_output(mutation):
    payload = {"kind": "count", "input_memory_ids": ["id"], "result": "3", **mutation}
    with pytest.raises(ValidationError):
        reader.DerivedOutput.model_validate(payload)


@pytest.mark.parametrize(
    "error", ["unknown", "uncited", "duplicate", "abstained", "duplicate_citation"]
)
def test_structural_problems_are_visible_not_repaired(tmp_path, error):
    _, rows, _, _ = setup(tmp_path)
    payload = response(reader.build_request(rows[0]))
    if error == "unknown":
        payload["derived"]["input_memory_ids"] = ["alien-id"]
    elif error == "uncited":
        payload["cited_memory_ids"] = []
    elif error == "duplicate":
        payload["derived"]["input_memory_ids"] *= 2
    elif error == "abstained":
        payload["abstained"] = True
    else:
        payload["cited_memory_ids"] *= 2
    output = reader.ReaderV2Output.model_validate(payload)
    checks = reader.structural_check(rows[0], output)
    assert not checks["structurally_valid"]
    assert output.model_dump(mode="json") == payload


def test_structure_does_not_verify_answer_arithmetic_or_absence(tmp_path):
    _, rows, _, _ = setup(tmp_path)
    payload = response(reader.build_request(rows[0]))
    payload["answer"] = "Wrong arithmetic with a valid id."
    payload["derived"]["result"] = "Wrong result"
    checks = reader.structural_check(
        rows[0], reader.ReaderV2Output.model_validate(payload)
    )
    assert checks["structurally_valid"]
    assert not checks["derivation_check"]["arithmetic_or_entailment_verified"]
    absence = reader.ReaderV2Output(
        answer="No information in these items.", abstained=True, cited_memory_ids=[]
    )
    assert reader.structural_check(rows[0], absence)["structurally_valid"]
    # Semantic absence, language and answer/flag agreement are not decided by regex.


@pytest.mark.asyncio
async def test_bounded_live_and_zero_call_replay(tmp_path):
    _, rows, baseline, plan = setup(tmp_path)
    factory = RecordingFactory(response)
    directory = tmp_path / "run"
    result = await run(rows, baseline, plan, directory, factory)
    assert result["status"] == "complete" and factory.calls == len(
        set(plan["request_sha256s"])
    )
    assert result["budget"]["new_reader_calls"] <= 18
    assert result["budget"]["new_judge_calls"] == 0
    assert not result["qa_metrics_available"] and not result["judge_executed"]
    assert result["metrics"]["answer_correct"] is None
    replay_factory = RecordingFactory(lambda request: pytest.fail("network reached"))
    replay = await run(rows, baseline, plan, directory, replay_factory, cache_only=True)
    assert replay_factory.calls == 0 and replay["budget"]["new_reader_calls"] == 0
    assert replay["metrics"] == result["metrics"]
    assert [r["reader"]["output"] for r in replay["rows"]] == [
        r["reader"]["output"] for r in result["rows"]
    ]
    assert "SYNTHETIC-SECRET" not in json.dumps(result)
    for path in directory.glob("provider-cache/*.json"):
        assert "SYNTHETIC-SECRET" not in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_outputs_are_not_retried_or_rebilled(tmp_path):
    _, rows, baseline, plan = setup(tmp_path)
    factory = RecordingFactory(lambda request: {"answer": "invalid"})
    directory = tmp_path / "run"
    result = await run(rows, baseline, plan, directory, factory)
    assert result["status"] == "partial"
    assert factory.calls == len(set(plan["request_sha256s"]))
    calls_before = factory.calls
    with pytest.raises(ValueError, match="cache-only"):
        await run(rows, baseline, plan, directory, factory)
    assert factory.calls == calls_before
    replay = await run(rows, baseline, plan, directory, factory, cache_only=True)
    assert replay["budget"]["new_reader_calls"] == 0
    assert replay["status"] == "partial"


@pytest.mark.parametrize("mutation", ["context", "baseline", "config", "plan"])
@pytest.mark.asyncio
async def test_mutations_fail_before_network(tmp_path, mutation):
    _, rows, baseline, plan = setup(tmp_path)
    factory = RecordingFactory(response)
    if mutation == "context":
        rows[0] = replace(rows[0], context=({**rows[0].context[0], "text": "Changed"},))
    elif mutation == "baseline":
        baseline["rows"][0]["reader"]["answer"] = "Changed old answer"
    elif mutation == "config":
        plan = reader.build_plan(rows, plan["input_binding"], config(temperature=0.3))
    else:
        plan["max_new_reader_calls"] = 19
        plan["plan_fingerprint"] = _hash(
            {k: v for k, v in plan.items() if k != "plan_fingerprint"}
        )
    with pytest.raises(ValueError):
        await run(rows, baseline, plan, tmp_path / "run", factory)
    assert factory.calls == 0 and not (tmp_path / "run").exists()


def test_plan_binds_payload_not_gold_and_cap_is_fixed(tmp_path):
    _, rows, _, plan = setup(tmp_path)
    copy_rows = deepcopy(rows)
    copy_rows[0] = replace(
        rows[0], scoring=replace(rows[0].scoring, answer="Other gold")
    )
    assert reader.build_plan(copy_rows, plan["input_binding"], config()) == plan
    copy_rows[0] = replace(
        rows[0], context=({**rows[0].context[0], "text": "Other evidence"},)
    )
    assert reader.build_plan(copy_rows, plan["input_binding"], config()) != plan
    with pytest.raises(ValueError):
        reader.build_plan(rows[:-1], plan["input_binding"], config())


def cli_args(fx, baseline_path, output, run_dir):
    return [
        "reader-v2",
        "--dataset",
        str(fx.dataset_path),
        "--manifest",
        str(fx.manifest_path),
        "--comparison",
        str(fx.comparison_path),
        "--comparison-sha256",
        fx.comparison_sha256,
        "--baseline",
        str(baseline_path),
        "--baseline-sha256",
        reader._sha256(baseline_path.read_bytes()),
        "--output",
        str(output),
        "--run-dir",
        str(run_dir),
    ]


def test_cli_preflight_reads_no_key_creates_no_ledger(tmp_path, monkeypatch):
    fx, _, baseline, _ = setup(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    output, directory = tmp_path / "out.json", tmp_path / "run"
    monkeypatch.setattr(sys, "argv", cli_args(fx, baseline_path, output, directory))
    original_get = reader.os.environ.get

    def guarded_get(name, default=None):
        if name == "DEEPSEEK_API_KEY":
            pytest.fail("key accessed")
        return original_get(name, default)

    monkeypatch.setattr(reader.os.environ, "get", guarded_get)
    assert reader.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "ready" and not result["api_key_read"]
    assert not directory.exists()
    with pytest.raises(SystemExit):
        reader.main()


def test_cli_redacts_unknown_failure_and_reports_unknown_usage(tmp_path, monkeypatch):
    fx, _, baseline, _ = setup(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    output = tmp_path / "out.json"
    monkeypatch.setattr(
        sys, "argv", cli_args(fx, baseline_path, output, tmp_path / "run") + ["--live"]
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "SYNTHETIC-SECRET")

    async def fail(*args, **kwargs):
        raise RuntimeError("SYNTHETIC-SECRET")

    monkeypatch.setattr(reader, "run_reader", fail)
    assert reader.main() == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["new_reader_calls"] is None
    assert "SYNTHETIC-SECRET" not in output.read_text(encoding="utf-8")

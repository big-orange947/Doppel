import json
from copy import deepcopy

import pytest
from test_public_memory_context_budget_qa import args, provider
from test_public_memory_context_budget_qa import plan as old_plan
from test_public_memory_context_budget_qa import queue as old_queue

from benchmarks import public_memory_rank_fusion_qa as final


@pytest.fixture(autouse=True)
def require_injected_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("tests must inject a fake provider")

    monkeypatch.setattr(final, "_default_provider_factory", forbidden)


def queue():
    work = old_queue()[:2]
    for item, arm in zip(work, final.ARMS, strict=True):
        item.update(arm=arm, budget=24000)
    return work


def plan():
    value = old_plan()
    for limits in value["stages"].values():
        limits.update(max_calls=50, max_total_request_bytes=5000000)
    return value


@pytest.mark.asyncio
async def test_execute_reuse_golden_separation_and_zero_call_replay(
    tmp_path, monkeypatch
):
    calls = []
    provider(monkeypatch, calls)
    monkeypatch.setattr(
        final, "_default_provider_factory", final.shared._default_provider_factory
    )
    work = queue()
    old = deepcopy(work[0]["baseline"])
    first = await final.execute(args(tmp_path / "live"), plan(), work)
    assert first["status"] == "complete"
    assert [name for name, _ in calls] == ["reader", "judge"]
    assert first["rows"][0]["reader_output"] == old["reader_output"]
    assert first["rows"][0]["grade"] == old["grade"]
    assert set(calls[0][1].input) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    assert first["summary"]["selection"]["profile"] is None
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    second = await final.execute(
        args(tmp_path / "replay", parents=[tmp_path / "live"], cache_only=True),
        plan(),
        work,
    )
    assert len(calls) == 2
    assert first["summary"] == second["summary"]
    assert all(
        value["ledger"]["attempts_reserved"] == 0 for value in second["usage"].values()
    )
    for a, b in zip(first["rows"], second["rows"], strict=True):
        assert a["reader_output"] == b["reader_output"]
        assert a["grade"] == b["grade"]
        assert a["checks"] == b["checks"]


@pytest.mark.asyncio
async def test_paid_failure_stops_and_preserves_attempt(tmp_path, monkeypatch):
    calls = []
    provider(monkeypatch, calls, fail=True)
    monkeypatch.setattr(
        final, "_default_provider_factory", final.shared._default_provider_factory
    )
    output = await final.execute(args(tmp_path / "fail"), plan(), queue())
    assert output["status"] == "failed"
    assert len(calls) == 1
    assert output["summary"]["selection"]["profile"] is None
    assert "SECRET" not in str(output)
    with pytest.raises(ValueError, match="new run"):
        await final.execute(args(tmp_path / "fail"), plan(), queue())


def rows(fusion_correct):
    return [
        {
            "ordinal": i,
            "arm": arm,
            "abstention_label": i <= 7,
            "question_type": "type",
            "context_bytes": 100,
            "grade": {"answer_correct": i <= (37 if arm == "bge" else fusion_correct)},
            "checks": {"structurally_valid": True},
        }
        for i in range(1, 51)
        for arm in final.ARMS
    ]


@pytest.mark.parametrize(
    "correct,selected",
    [(36, "bge"), (37, "bge"), (38, "bge"), (39, "bge"), (40, "fusion")],
)
def test_selection_rule_fixed_before_live_outcomes(correct, selected):
    result = final.summarize(rows(correct))
    assert result["selection"]["profile"] == selected
    assert result["selection"]["complete"]
    assert result["bge"]["answerable"]["completed"] == 43


@pytest.mark.parametrize("damage", ["negative", "structural", "incomplete"])
def test_gain_does_not_override_other_guards(damage):
    data = rows(41)
    if damage == "negative":
        data[1]["grade"]["answer_correct"] = False
    elif damage == "structural":
        data[1]["checks"]["structurally_valid"] = False
    else:
        data.pop()
    result = final.summarize(data)
    assert result["selection"]["profile"] == (None if damage == "incomplete" else "bge")


def test_recovery_subtracts_original_spend_and_preserves_requests(monkeypatch):
    plan = {
        "input_sha256": {},
        "arms": ["bge", "fusion"],
        "requests": ["same"],
        "rrf_k": 60,
        "weights": "equal",
        "decision": "frozen",
        "minimum_net_gain_to_select_fusion": 3,
        "code_sha256": {"shared": "same", final.__file__: "new"},
        "stages": {
            name: {"max_calls": 50, "config": {"model": "same"}}
            for name in ("reader", "judge")
        },
    }
    old = deepcopy(plan)
    old["plan_fingerprint"] = "original"
    old["code_sha256"][final.__file__] = "old"
    prior = {
        "status": "failed",
        "plan": old,
        "usage": {
            name: {
                "ledger": {
                    "attempts_reserved": count,
                    "attempt_status_counts": {
                        "failed": int(name == "reader"),
                        "reserved": 0,
                        "interrupted": 0,
                    },
                }
            }
            for name, count in (("reader", 3), ("judge", 2))
        },
    }
    raw = json.dumps(prior).encode()
    monkeypatch.setattr(final, "FAILED_REPORT_SHA", final.sha(raw))
    recovered = final.recovery_plan(plan, raw)
    assert recovered["stages"]["reader"]["max_calls"] == 48
    assert recovered["stages"]["judge"]["max_calls"] == 48
    assert recovered["requests"] == ["same"]
    assert old["stages"]["reader"]["max_calls"] == 50
    changed = deepcopy(plan)
    changed["requests"] = ["changed"]
    with pytest.raises(ValueError):
        final.recovery_plan(changed, raw)
    with pytest.raises(ValueError):
        final.recovery_plan(plan, b"different report")

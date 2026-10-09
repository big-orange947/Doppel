"""Reference-only grading boundary, control gate and durable replay tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.public_memory_expansion import PROFILES
from benchmarks.public_memory_task_accuracy import CONTROLS, build_plan, request, run
from tests.test_public_memory_answer_comparison import RecordingFactory


def rows():
    return [
        {
            "case_id": f"case-{i}",
            "profile": p,
            "question": f"Question {i}-{p}",
            "reference": "Oslo",
            "answer": "Oslo.",
        }
        for i in range(50)
        for p in PROFILES
    ]


def respond(req):
    assert set(req.input) == {"question", "reference_answer", "candidate_answer"}
    match = next(
        (
            c
            for c in CONTROLS
            if c[1] == req.input["question"]
            and c[2] == req.input["reference_answer"]
            and c[3] == req.input["candidate_answer"]
        ),
        None,
    )
    return {
        "answer_correct": match[-1] if match else True,
        "rationale": "Fake reference comparison",
    }


@pytest.mark.asyncio
async def test_bound_cap_and_key_free_replay(tmp_path):
    sample = rows()
    before = deepcopy(sample)
    plan = build_plan(sample, {"answers": "a" * 64})
    factory = RecordingFactory(respond)
    live = await run(
        sample,
        plan,
        run_dir=tmp_path,
        api_key="FAKE-KEY",
        cache_only=False,
        provider_factory=factory,
    )
    assert (
        live["control_gate"]
        and live["new_calls"] == 156
        and live["status"] == "complete"
    )
    assert all(s["correct"] == s["scored"] == 50 for s in live["summary"].values())
    assert sample == before
    replay = await run(
        sample,
        plan,
        run_dir=tmp_path,
        api_key="",
        cache_only=True,
        provider_factory=factory,
    )
    assert replay["new_calls"] == 0 and replay["summary"] == live["summary"]
    assert [r["output"] for r in replay["rows"]] == [r["output"] for r in live["rows"]]
    assert not live["reader_reexecuted"] and not live["context_support_assessed"]
    with pytest.raises(ValueError, match="cache-only"):
        await run(
            sample,
            plan,
            run_dir=tmp_path,
            api_key="FAKE-KEY",
            cache_only=False,
            provider_factory=factory,
        )


@pytest.mark.asyncio
async def test_absence_control_failure_closes_main_arm(tmp_path):
    sample = rows()
    plan = build_plan(sample, {"answers": "a" * 64})

    def failed_control(req):
        result = respond(req)
        if req.input["candidate_answer"] == CONTROLS[1][3]:
            result["answer_correct"] = True
        return result

    factory = RecordingFactory(failed_control)
    report = await run(
        sample,
        plan,
        run_dir=tmp_path,
        api_key="FAKE-KEY",
        cache_only=False,
        provider_factory=factory,
    )
    assert (
        not report["control_gate"] and report["rows"] == [] and report["new_calls"] == 6
    )
    assert factory.calls == 6
    assert all(s["unscored"] == 50 for s in report["summary"].values())


@pytest.mark.asyncio
async def test_changed_answer_cannot_spend(tmp_path):
    sample = rows()
    plan = build_plan(sample, {"answers": "a" * 64})
    sample[0]["answer"] = "changed"
    factory = RecordingFactory(respond)
    with pytest.raises(ValueError, match="changed"):
        await run(
            sample,
            plan,
            run_dir=tmp_path,
            api_key="FAKE-KEY",
            cache_only=False,
            provider_factory=factory,
        )
    assert factory.calls == 0


def test_request_withholds_evidence_profile_and_previous_judgment():
    req = request("Q", "REF", "ANSWER")
    assert set(req.input) == {"question", "reference_answer", "candidate_answer"}
    assert req.input["reference_answer"] == "REF"

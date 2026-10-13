from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_transient_cohort as experiment
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import AnswerRow


def synthetic_source():
    categories = (
        ["temporal-reasoning"] * 4
        + ["knowledge-update"] * 4
        + ["single-session-user"] * 2
    )
    return [
        {
            "question_id": str(n) + ("_abs" if n >= 8 else ""),
            "question_type": c,
            "question": "arbitrary",
            "answer": "GOLD_SENTINEL",
            "old_score": False,
        }
        for n, c in enumerate(categories)
    ]


def manifest(source):
    return {
        "cases": [
            {"case_id": r["question_id"], "partition": "diagnostic"} for r in source
        ]
    }


def test_fixed_source_order_selection_excludes_previous_reserved_and_scores():
    source = synthetic_source()
    m = manifest(source)
    m["cases"][0]["partition"] = "reserved"
    result = experiment.select_ids(source, m, {"1", "4"}, {"5"})
    assert result == ["2", "3", "6", "7", "8_abs"]
    modified = deepcopy(source)
    for r in modified:
        r.update(answer="DIFFERENT_GOLD", question="changed question", old_score=True)
    assert experiment.select_ids(modified, m, {"1", "4"}, {"5"}) == result


def test_missing_quota_and_duplicate_source_fail_no_silent_substitute():
    source = synthetic_source()
    with pytest.raises(ValueError, match="quotas"):
        experiment.select_ids(source, manifest(source), {"8_abs", "9_abs"}, set())
    with pytest.raises(ValueError, match="duplicate"):
        experiment.select_ids(source + [source[0]], manifest(source), set(), set())


def rows():
    cases = []
    for n, category in enumerate(
        [
            "single-session-user",
            "temporal-reasoning",
            "temporal-reasoning",
            "knowledge-update",
            "knowledge-update",
        ]
    ):
        identity = "fake-" + str(n) + ("_abs" if n == 0 else "")
        p = prepare_case(
            {
                "question_id": identity,
                "question_type": category,
                "question": "Current value?",
                "answer": "GOLD_SENTINEL",
                "question_date": "2024/01/03 (Wed) 10:30",
                "answer_session_ids": [] if n == 0 else ["s"],
                "haystack_session_ids": ["s"],
                "haystack_dates": ["2024/01/02 (Tue) 09:45"],
                "haystack_sessions": [[{"role": "user", "content": "The value is B."}]],
            },
            dataset_namespace="synthetic-cohort",
        )
        t = p.runtime.sessions[0].turns[0]
        context = (
            {
                "memory_id": identity + ":source",
                "channel": "raw",
                "role": "user",
                "actor": "owner",
                "authority": "human_self",
                "text": t.content,
                "observed_at": t.at.isoformat(),
                "temporal_status": None,
                "valid_from": None,
                "valid_to": None,
                "source_events": ["original"],
            },
        )
        cases.append(
            AnswerRow(n, identity, "raw_vector_reranked", p.runtime, p.scoring, context)
        )
    return cases


def factory(cfg, key, observer):
    class Fake:
        name, version = "fake-cohort", "1"

        async def generate(self, request):
            assert "GOLD_SENTINEL" not in request.model_dump_json()
            observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
            if "messages" in request.input:
                assert "question" not in request.input
                return {
                    "memories": [
                        {
                            "content": "Value B",
                            "subject": "owner",
                            "memory_type": "state",
                            "topic_key": "slot",
                            "temporal_status": "current",
                            "evidence_ids": [
                                request.input["messages"][0]["evidence_id"]
                            ],
                        }
                    ]
                }
            return {
                "answer": "B",
                "abstained": False,
                "cited_memory_ids": [request.input["context_items"][0]["memory_id"]],
            }

    return Fake()


async def balance(key):
    return 5.0


async def test_frozen_stage_budget_source_preservation_and_key_removed_replay(
    tmp_path, monkeypatch
):
    cases = rows()
    plan = await experiment.build_plan(cases, {"source": "synthetic"})
    assert (
        plan["max_analyzer_calls"] == 5
        and plan["max_reader_calls"] == 10
        and plan["max_judge_calls"] == 0
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await experiment.execute(
        args, cases, plan, provider_factory=factory, balance_reader=balance
    )
    assert live["status"] == "complete"
    assert live["usage"]["analyzer"]["ledger"]["attempts_reserved"] == 5
    assert live["usage"]["reader"]["ledger"]["attempts_reserved"] == 10
    assert all(
        len(r["arms"]) == 2 and not r["view"]["consolidation_applied"]
        for r in live["rows"]
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await experiment.execute(
        args, cases, plan, provider_factory=factory, balance_reader=balance
    )
    assert live["rows"] == replay["rows"]
    assert replay["usage"]["analyzer"]["cache_hits_this_instance"] == 5
    assert replay["usage"]["reader"]["cache_hits_this_instance"] == 10
    assert all(
        "fake-secret" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )
    row = cases[0]
    from doppel_memory.transient import TransientMemoryView

    paired = experiment.paired_requests(
        row,
        live["rows"][0]["analysis"]["proposals"],
        TransientMemoryView.model_validate(live["rows"][0]["view"]),
    )
    a, b = [paired[arm] for arm in experiment.ARMS]
    assert a.instructions == b.instructions and a.output_schema == b.output_schema
    assert a.input["context_items"] == b.input["context_items"]
    assert a.input["query_time_proposals"] == b.input["query_time_proposals"]


async def test_failure_preserved_and_never_retried(tmp_path, monkeypatch):
    cases = rows()
    plan = await experiment.build_plan(cases, {})
    calls = []

    def fail_factory(cfg, key, observer):
        class Fake:
            name, version = "failing-cohort", "1"

            async def generate(self, request):
                calls.append(1)
                raise RuntimeError("SECRET_PROVIDER_TEXT")

        return Fake()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    for _ in range(2):
        r = await experiment.execute(
            args, cases, plan, provider_factory=fail_factory, balance_reader=balance
        )
        assert r["status"] == "stopped" and r["rows"][0]["failure_stage"] == "analyzer"
        assert "SECRET_PROVIDER_TEXT" not in json.dumps(r)
    assert len(calls) == 1


async def test_quotas_or_duplicate_cases_cannot_change_fixed_plan():
    cases = rows()
    with pytest.raises(ValueError):
        await experiment.build_plan(cases[:-1], {})
    with pytest.raises(ValueError):
        await experiment.build_plan([*cases[:-1], cases[0]], {})


async def test_empty_balance_stops_before_provider_reservation(tmp_path, monkeypatch):
    cases = rows()
    plan = await experiment.build_plan(cases, {})

    async def empty(key):
        return 0.0

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    r = await experiment.execute(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        cases,
        plan,
        provider_factory=factory,
        balance_reader=empty,
    )
    assert r["status"] == "stopped"
    assert r["usage"]["analyzer"]["ledger"]["attempts_reserved"] == 0
    assert r["usage"]["reader"]["ledger"]["attempts_reserved"] == 0

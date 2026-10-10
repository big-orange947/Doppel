from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_lazy_diagnostic as experiment
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import AnswerRow
from doppel_memory.intelligence import (
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzer,
)


def row(identity="synthetic-1", index=0):
    prepared = prepare_case(
        {
            "question_id": identity,
            "question_type": "temporal-reasoning",
            "question": "What is the updated value?",
            "answer": "SECRET_GOLD",
            "question_date": "2024/01/03 (Wed) 10:30",
            "answer_session_ids": ["s"],
            "haystack_session_ids": ["s"],
            "haystack_dates": ["2024/01/02 (Tue) 09:45"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "The value is now B."},
                    {"role": "assistant", "content": "You might choose C."},
                ]
            ],
        },
        dataset_namespace="test-lazy",
    )
    context = tuple(
        {
            "channel": "raw",
            "memory_id": identity + ":" + str(t.turn_index),
            "role": t.role,
            "actor": "owner" if t.role == "user" else "agent",
            "authority": "human_self" if t.role == "user" else "agent_output",
            "text": t.content,
            "observed_at": t.at.isoformat(),
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
            "source_events": ["event-" + str(t.turn_index)],
        }
        for t in prepared.runtime.sessions[0].turns
    )
    return AnswerRow(
        index,
        identity,
        "s-raw-vector-reranked",
        prepared.runtime,
        prepared.scoring,
        context,
    )


async def test_real_analyzer_request_is_question_and_gold_free():
    r = row()
    request = await experiment.analyzer_request(r)
    assert "SECRET_GOLD" not in request.model_dump_json()
    assert r.runtime.query.query not in request.model_dump_json()
    changed = replace(
        r,
        runtime=replace(
            r.runtime, query=replace(r.runtime.query, query="Other question")
        ),
    )
    assert request == await experiment.analyzer_request(changed)
    assert {m["evidence_id"] for m in request.input["messages"]} == {
        i["memory_id"] for i in r.context
    }
    assert {m["actor"] for m in request.input["messages"]} == {"owner", "agent"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor", "contact"),
        ("role", "system"),
        ("authority", "agent_output"),
        ("text", "Source not in the bound history"),
        ("observed_at", "2020-01-01T00:00:00+00:00"),
        ("channel", "memory"),
        ("source_events", []),
    ],
)
def test_saved_source_binding_fail_closed(field, value):
    r = row()
    items = deepcopy(r.context)
    items[0][field] = value
    with pytest.raises(ValueError):
        experiment.messages(replace(r, context=items))


def test_original_evidence_retained_and_horizon_not_causal():
    r = row()
    changed = replace(
        r,
        runtime=replace(
            r.runtime,
            query=replace(r.runtime.query, reference_time=experiment.messages(r)[0].at),
        ),
    )
    proposal = {
        "content": "Unverified interpretation",
        "evidence_ids": [r.context[0]["memory_id"]],
    }
    a, b = (
        experiment.reader_request(changed),
        experiment.reader_request(changed, [proposal]),
    )
    assert a.input["context_items"] == b.input["context_items"]
    assert a.instructions == b.instructions and a.output_schema == b.output_schema
    assert a.input["query_time_proposals"] == []
    assert b.input["query_time_proposals"] == [proposal]
    assert "not causal replay" in b.input["observation_policy"]


async def test_miner_quarantines_wrong_subject_and_keeps_original_evidence():
    r = row()
    ids = [i["memory_id"] for i in r.context]

    class Fake:
        name, version = "scripted", "1"

        async def generate(self, request):
            return {
                "memories": [
                    {
                        "content": "Value B",
                        "subject": "owner",
                        "evidence_ids": [ids[0]],
                    },
                    {
                        "content": "Promoted assistant suggestion",
                        "subject": "owner",
                        "evidence_ids": [ids[1]],
                    },
                    {
                        "content": "Unknown",
                        "subject": "owner",
                        "evidence_ids": ["unknown"],
                    },
                ]
            }

    plan = await PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzer(Fake()), experiment.miner_config(2)
    ).propose(experiment.task_context(r))
    proposals = experiment.project_proposals(r, plan.proposals)
    assert len(proposals) == 1 and proposals[0]["state"] == "candidate"
    assert proposals[0]["evidence_ids"] == [ids[0]]
    assert (
        plan.next_checkpoint.metadata["proposal_diagnostics"][
            "evidence_rejected_drafts"
        ]
        == 2
    )
    foreign = replace(r, case_id="different-scope")
    with pytest.raises(ValueError, match="scope"):
        experiment.project_proposals(foreign, plan.proposals)


async def test_window_pagination_and_no_external_memory_access():
    context = experiment.task_context(row())
    first = await context.history.read(limit=1)
    last = await context.history.read(cursor=first.next_cursor, limit=1)
    assert first.has_more and not last.has_more
    assert len(first.messages + last.messages) == 2
    with pytest.raises(ValueError):
        await context.history.read(cursor="01")
    with pytest.raises(ValueError):
        await context.memories.recall("other history")


def factory(cfg, key, observer):
    class Fake:
        name, version = "fake-lazy-provider", "1"

        async def generate(self, request):
            observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
            if "messages" in request.input:
                return {
                    "memories": [
                        {
                            "content": "Value B",
                            "subject": "owner",
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


async def test_live_fake_and_key_removed_replay_with_fixed_caps(tmp_path, monkeypatch):
    rows = [row(), row("synthetic-2", 1)]
    plan = await experiment.build_plan(rows, {"source": "fixture"})
    assert (
        plan["max_analyzer_calls"] == 2
        and plan["max_reader_calls"] == 4
        and plan["max_judge_calls"] == 0
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await experiment.execute(
        args, rows, plan, provider_factory=factory, balance_reader=balance
    )
    assert live["status"] == "complete"
    assert live["usage"]["analyzer"]["ledger"]["attempts_reserved"] == 2
    assert live["usage"]["reader"]["ledger"]["attempts_reserved"] == 4
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await experiment.execute(
        args, rows, plan, provider_factory=factory, balance_reader=balance
    )
    assert live["rows"] == replay["rows"]
    assert replay["usage"]["reader"]["cache_hits_this_instance"] == 4
    assert replay["usage"]["analyzer"]["cache_hits_this_instance"] == 2
    assert all(
        "fake-secret" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )


async def test_preserved_failure_never_retried(tmp_path, monkeypatch):
    rows = [row()]
    plan = await experiment.build_plan(rows, {})
    calls = []

    def fail_factory(cfg, key, observer):
        class Fake:
            name, version = "failing", "1"

            async def generate(self, request):
                calls.append(1)
                raise RuntimeError("secret should never appear")

        return Fake()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-secret")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    for _ in range(2):
        report = await experiment.execute(
            args, rows, plan, provider_factory=fail_factory, balance_reader=balance
        )
        assert report["status"] == "stopped"
        assert "secret" not in json.dumps(report)
    assert len(calls) == 1


async def test_analyzer_request_must_match_frozen_hash(tmp_path):
    model = experiment.ProbeModel()
    wrapper = experiment.ReceiptedAnalyzerModel(
        model, tmp_path / "receipt.json", "wrong"
    )
    with pytest.raises(ValueError, match="frozen"):
        await wrapper.generate(await experiment.analyzer_request(row()))
    assert not (tmp_path / "receipt.json").exists()


def test_large_dynamic_reader_input_not_silently_truncated():
    with pytest.raises(ValueError, match="exceeds"):
        experiment.reader_request(row(), [{"content": "X" * experiment.MAX_BYTES}])

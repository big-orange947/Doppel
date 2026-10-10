from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_transient_view as experiment
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import AnswerRow
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_lazy_diagnostic import (
    analyzer_request,
    messages,
    miner_config,
    project_proposals,
    reader_request,
    task_context,
)
from benchmarks.public_memory_pilot import _hash
from doppel_memory.intelligence import (
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzer,
)


def fixture():
    prepared = prepare_case(
        {
            "question_id": "synthetic",
            "question_type": "knowledge-update",
            "question": "Current value?",
            "answer": "GOLD_NOT_RUNTIME",
            "question_date": "2024/01/03 (Wed) 10:30",
            "answer_session_ids": ["s"],
            "haystack_session_ids": ["s"],
            "haystack_dates": ["2024/01/02 (Tue) 09:45"],
            "haystack_sessions": [[{"role": "user", "content": "Current value B"}]],
        },
        dataset_namespace="test-transient",
    )
    turn = prepared.runtime.sessions[0].turns[0]
    context = (
        {
            "channel": "raw",
            "memory_id": "source",
            "role": "user",
            "actor": "owner",
            "authority": "human_self",
            "text": turn.content,
            "observed_at": turn.at.isoformat(),
            "temporal_status": None,
            "valid_from": None,
            "valid_to": None,
            "source_events": ["original"],
        },
    )
    return AnswerRow(
        0,
        "synthetic",
        "s-raw-vector-reranked",
        prepared.runtime,
        prepared.scoring,
        context,
    )


async def parents(tmp_path, monkeypatch):
    row = fixture()
    request = await analyzer_request(row)
    receipt = {
        "status": "completed",
        "request_sha256": _hash(request.model_dump(mode="json")),
        "output": {
            "memories": [
                {
                    "content": "Value B",
                    "subject": "owner",
                    "memory_type": "state",
                    "topic_key": "slot",
                    "temporal_status": "current",
                    "evidence_ids": ["source"],
                }
            ]
        },
    }
    model = experiment.ReceiptReplayModel(receipt, config(4096))
    generated = await PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzer(model), miner_config(len(messages(row)))
    ).propose(task_context(row))
    binding = {"source": "synthetic-bound-source"}
    plan = {
        "bindings": binding,
        "analyzer_requests": {row.case_id: receipt["request_sha256"]},
        "baseline_reader_requests": {
            row.case_id: _hash(reader_request(row).model_dump(mode="json"))
        },
    }
    plan["plan_fingerprint"] = _hash(plan)
    parent = {
        "runner": "doppel.public-memory-query-time-proposal-diagnostic.v1",
        "status": "complete",
        "plan": plan,
        "rows": [
            {
                "case_id": row.case_id,
                "analysis": {
                    "proposals": project_proposals(row, generated.proposals),
                    "checkpoint": generated.next_checkpoint.model_dump(mode="json"),
                },
            }
        ],
    }
    path = tmp_path / "parent.json"
    save(path, parent)
    save(tmp_path / "receipts" / "synthetic-analysis.json", receipt)
    monkeypatch.setattr(experiment, "load_rows", lambda args: ([row], binding))
    return SimpleNamespace(parent=path, parent_dir=tmp_path), parent


async def test_cache_derived_view_and_common_reader_contract(tmp_path, monkeypatch):
    args, _parent = await parents(tmp_path, monkeypatch)
    before = args.parent.read_bytes()
    _rows, requests, views, plan = await experiment.prepare(args)
    assert args.parent.read_bytes() == before
    a, b = [requests[("synthetic", arm)] for arm in experiment.ARMS]
    assert a.instructions == b.instructions and a.output_schema == b.output_schema
    assert a.input["context_items"] == b.input["context_items"]
    assert a.input["query_time_proposals"] == b.input["query_time_proposals"]
    assert a.input["temporal_view"] is None
    view = b.input["temporal_view"]
    assert view["claims"][0]["proposal_index"] == 0
    assert view["claims"][0]["evidence"][0]["evidence_id"] == "source"
    assert "text" not in view["claims"][0]["evidence"][0]
    assert not view["consolidation_applied"]
    assert views["synthetic"]["claims"][0]["evidence"][0]["text"] == "Current value B"
    assert plan["max_analyzer_calls"] == plan["max_judge_calls"] == 0
    assert plan["max_reader_calls"] == 2
    assert "GOLD_NOT_RUNTIME" not in b.model_dump_json()


@pytest.mark.parametrize(
    "changed",
    ["parent_binding", "parent_proposals", "receipt_request", "receipt_failure"],
)
async def test_parent_or_receipt_changes_fail_without_network(
    tmp_path, monkeypatch, changed
):
    args, parent = await parents(tmp_path, monkeypatch)
    if changed.startswith("receipt"):
        path = tmp_path / "receipts" / "synthetic-analysis.json"
        payload = json.loads(path.read_bytes())
        payload["request_sha256" if changed == "receipt_request" else "status"] = (
            "changed"
        )
        # Fixture mutation, not replacement of a real persisted receipt.
        path.unlink()
        save(path, payload)
    else:
        if changed == "parent_binding":
            parent["plan"]["bindings"] = {"source": "changed"}
        else:
            parent["rows"][0]["analysis"]["proposals"][0]["content"] = "tampered"
        args.parent.unlink()
        save(args.parent, parent)
    with pytest.raises(ValueError):
        await experiment.prepare(args)

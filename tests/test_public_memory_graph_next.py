from copy import deepcopy

import pytest

from benchmarks import public_memory_graph_next as runner
from benchmarks.public_memory_pilot import _hash
from doppel_memory.models import MemoryScope


def bind(value):
    return {**value, "plan_fingerprint": _hash(value)}


def inputs(monkeypatch):
    scopes = [MemoryScope(user_id=f"owner-{i}", agent_id="agent") for i in range(5)]
    rows = {
        s.scope_key: [{"memory_id": f"memory-{i}", "scope_key": s.scope_key}]
        for i, s in enumerate(scopes)
    }

    def build(records, selected, ingestion, *, max_records, max_calls):
        assert max_records == 10_000 and max_calls == 1500
        return bind(
            {
                "records": rows[selected[0].scope_key],
                "corpus_sha256": "corpus",
                "eligible_records": 1,
                "selected_records": 1,
            }
        )

    monkeypatch.setattr(runner, "build_plan", build)
    graph = bind({"records": rows[scopes[2].scope_key], "scope_ordinal": 3})
    receipt = {
        "scope_ordinal": 3,
        "status": "complete",
        "selected_scope_projection_complete": True,
        "corpus_unchanged": True,
        "vectors_unchanged": True,
        "other_scopes_unchanged": True,
        "graph_plan": graph,
        "plan": bind(
            {
                "scope_plans": [graph],
                "corpus_sha256": "corpus",
                "vectors": {},
                "binding": {"manifest": "manifest", "ingestion": "ingestion"},
            }
        ),
    }
    binding = {
        "manifest": "manifest",
        "ingestion": "ingestion",
        "predecessor": "receipt-sha",
    }
    return {}, scopes, {}, binding, {}, receipt


def test_next_source_scope_is_not_question_or_answer_selected(monkeypatch):
    args = inputs(monkeypatch)
    plan = runner.build_next(*args)
    assert plan["previous_scope_ordinal"] == 3 and plan["target_scope_ordinal"] == 4
    assert len(plan["scope_plans"]) == 1
    assert plan["scope_plans"][0]["records"][0]["scope_key"] == args[1][3].scope_key
    assert plan["max_calls"] == 1500 and plan["max_total_request_bytes"] == 32_000_000
    assert not plan["publication_ready"] and not plan["reserved_histories_executed"]
    assert "question" not in plan["binding"] and "answer" not in plan["binding"]
    for bound in [plan, *plan["scope_plans"]]:
        assert bound["plan_fingerprint"] == _hash(
            {k: v for k, v in bound.items() if k != "plan_fingerprint"}
        )


@pytest.mark.parametrize(
    "field",
    [
        "selected_scope_projection_complete",
        "corpus_unchanged",
        "vectors_unchanged",
        "other_scopes_unchanged",
    ],
)
def test_incomplete_or_mutated_predecessor_rejected(monkeypatch, field):
    args = inputs(monkeypatch)
    args[-1][field] = False
    with pytest.raises(ValueError, match="settled complete"):
        runner.build_next(*args)


def test_partial_predecessor_does_not_skip_to_next_history(monkeypatch):
    args = inputs(monkeypatch)
    args[-1]["status"] = "partial"
    with pytest.raises(ValueError, match="settled complete"):
        runner.build_next(*args)


@pytest.mark.parametrize("ordinal", [0, 5, True, "3"])
def test_invalid_or_exhausted_source_ordinal_rejected(monkeypatch, ordinal):
    args = inputs(monkeypatch)
    args[-1]["scope_ordinal"] = ordinal
    with pytest.raises(ValueError, match="source ordinal"):
        runner.build_next(*args)


def test_predecessor_plan_fingerprint_tampering_rejected(monkeypatch):
    args = inputs(monkeypatch)
    args[-1]["graph_plan"]["records"] = []
    with pytest.raises(ValueError, match="fingerprint"):
        runner.build_next(*args)


def test_cross_scope_predecessor_rejected_even_with_valid_fingerprints(monkeypatch):
    args = inputs(monkeypatch)
    receipt = args[-1]
    graph = bind(
        {
            "records": [{"memory_id": "foreign", "scope_key": args[1][0].scope_key}],
            "scope_ordinal": 3,
        }
    )
    receipt["graph_plan"] = graph
    envelope = {k: v for k, v in receipt["plan"].items() if k != "plan_fingerprint"}
    envelope["scope_plans"] = [graph]
    receipt["plan"] = bind(envelope)
    with pytest.raises(ValueError, match="source-order scope"):
        runner.build_next(*args)


def test_different_sources_cannot_reuse_predecessor_receipt(monkeypatch):
    args = list(inputs(monkeypatch))
    args[3] = {**args[3], "manifest": "changed"}
    with pytest.raises(ValueError, match="binding changed"):
        runner.build_next(*args)


def test_truncated_graph_selection_rejected(monkeypatch):
    args = inputs(monkeypatch)
    original = runner.build_plan

    def truncated(*pos, **kw):
        result = original(*pos, **kw)
        return {**result, "selected_records": 0}

    monkeypatch.setattr(runner, "build_plan", truncated)
    with pytest.raises(ValueError, match="complete next-history"):
        runner.build_next(*args)


def test_predecessor_record_set_cannot_silently_change(monkeypatch):
    args = inputs(monkeypatch)
    original = runner.build_plan
    previous_scope = args[1][2].scope_key

    def changed(*pos, **kw):
        result = deepcopy(original(*pos, **kw))
        if pos[1][0].scope_key == previous_scope:
            result["records"][0]["memory_id"] = "changed"
        return result

    monkeypatch.setattr(runner, "build_plan", changed)
    with pytest.raises(ValueError, match="whole source history"):
        runner.build_next(*args)

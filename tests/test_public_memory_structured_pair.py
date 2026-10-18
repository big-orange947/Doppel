from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_structured_pair as experiment
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import AnswerRow
from benchmarks.public_memory_pilot import _hash
from integrations.aml.contract import memory_scope


def synthetic_row():
    case = prepare_case(
        {
            "question_id": "fixture",
            "question_type": "multi-session",
            "question": "How many visits?",
            "answer": "GOLD_SENTINEL",
            "question_date": "2024/01/03 (Wed) 10:30",
            "answer_session_ids": ["s"],
            "haystack_session_ids": ["s"],
            "haystack_dates": ["2024/01/02 (Tue) 09:45"],
            "haystack_sessions": [
                [
                    {"role": "user", "content": "I visited an observatory."},
                    {"role": "assistant", "content": "You could visit a museum."},
                ]
            ],
        },
        dataset_namespace="structured-synthetic",
    )
    scope = memory_scope("synthetic", case.runtime.user_id)
    context = []
    for n, turn in enumerate(case.runtime.sessions[0].turns):
        actor = "owner" if turn.role == "user" else "agent"
        context.append(
            {
                "memory_id": f"source-{n}",
                "scope_key": scope.scope_key,
                "channel": "raw",
                "role": turn.role,
                "actor": actor,
                "authority": "human_self" if actor == "owner" else "agent_output",
                "text": turn.content,
                "observed_at": turn.at.isoformat(),
                "temporal_status": None,
                "valid_from": None,
                "valid_to": None,
                "source_events": [f"event-{n}"],
            }
        )
    return AnswerRow(
        0, "fixture", "fake", case.runtime, case.scoring, tuple(context)
    ), scope


class Analyzer:
    name, version = "fake-analyzer", "1"

    async def generate(self, request):
        assert "GOLD_SENTINEL" not in request.model_dump_json()
        assert set(request.input) == {"scope", "messages"}
        return {
            "memories": [
                {
                    "content": "Visited observatory",
                    "subject": "owner",
                    "memory_type": "episode",
                    "topic_key": "visits",
                    "event_key": "visit-one",
                    "temporal_status": "historical",
                    "confidence": 0.9,
                    "evidence_ids": ["source-0"],
                },
                {
                    "content": "Assistant suggested a museum",
                    "subject": "agent",
                    "memory_type": "fact",
                    "topic_key": "visits",
                    "confidence": 0.9,
                    "evidence_ids": ["source-1"],
                },
                {
                    "content": "Wrongly attributed museum",
                    "subject": "owner",
                    "memory_type": "fact",
                    "confidence": 0.9,
                    "evidence_ids": ["source-1"],
                },
            ]
        }


class Planner:
    name, version = "fake-planner", "1"

    async def generate(self, request):
        assert "GOLD_SENTINEL" not in request.model_dump_json()
        assert "messages" not in request.input
        return {
            "schema_version": 2,
            "operation": "count",
            "temporal_view": "unbounded",
            "search_text": "",
            "memory_types": ["episode"],
            "confidence": 1,
        }


async def test_real_miner_view_and_query_engine_without_promotion_or_global_count():
    row, scope = synthetic_row()
    original = deepcopy(row.context)
    view, audit = await experiment.structured_view(row, scope, Analyzer(), Planner())
    assert row.context == original
    assert len(view["claims"]) == 2  # bad subject/actor proposal quarantined
    assert all(c["state"] == "candidate" for c in view["claims"])
    assert {c["actor"] for c in view["claims"]} == {"owner", "agent"}
    assert all(c["validity_at_reference"] == "unknown" for c in view["claims"])
    assert all(
        e["evidence_id"] in {"source-0", "source-1"}
        for c in view["claims"]
        for e in c["evidence"]
    )
    assert not view["source_subset_complete_history"]
    assert view["query"]["whole_history_count"]["value"] is None
    assert view["query"]["whole_history_count"]["status"] == "indeterminate"
    assert audit["engine_result"]["scanned_record_count"] > 0
    assert audit["engine_result"]["plan"]["operation"] == "count"
    assert audit["production_writes"] == 0
    # Agent interpretations remain visible as attributed suggestions, but cannot
    # become an owner-fact query hit.
    selected = set(view["query"]["selected_claim_ids"])
    assert not any(
        c["claim_id"] in selected for c in view["claims"] if c["actor"] == "agent"
    )
    base = experiment.reader_request(row)
    augmented = experiment.augmented_request(row, view)
    assert augmented.instructions == base.instructions
    assert augmented.output_schema == base.output_schema
    assert augmented.input["context_items"] == base.input["context_items"]
    assert "GOLD_SENTINEL" not in augmented.model_dump_json()


async def test_requests_use_real_core_prompts_and_separate_question_from_analysis():
    row, scope = synthetic_row()
    requests = await experiment.requests_for(row, scope)
    assert "query" not in requests["analyzer"].input
    assert requests["planner"].input["query"] == row.runtime.query.query
    assert all("GOLD_SENTINEL" not in r.model_dump_json() for r in requests.values())


def selection_fixture():
    kinds = ["temporal-reasoning", "multi-session"] * 4 + [
        "knowledge-update",
        "single-session-user",
    ]
    data = [
        {
            "question_id": str(n) + ("_abs" if n == 9 else ""),
            "question_type": k,
            "answer": "old",
            "question": "old",
        }
        for n, k in enumerate(kinds)
    ]
    manifest = {
        "cases": [
            {
                "case_id": d["question_id"],
                "partition": "diagnostic",
                "history_group": d["question_id"],
            }
            for d in data
        ]
    }
    return data, manifest


def test_selection_ignores_answers_questions_and_scores():
    data, manifest = selection_fixture()
    result = [n for n, _, _ in experiment.choose_cases(data, manifest)]
    for r in data:
        r.update(answer="different", question="different", old_score="false")
    assert (
        [n for n, _, _ in experiment.choose_cases(data, manifest)]
        == result
        == [1, 2, 3, 4, 5, 6, 9, 10]
    )


def test_quota_does_not_silently_replace_reserved_or_duplicates():
    data, manifest = selection_fixture()
    manifest["cases"][-1]["partition"] = "reserved"
    with pytest.raises(ValueError, match="quota"):
        experiment.choose_cases(data, manifest)
    with pytest.raises(ValueError, match="duplicate"):
        experiment.choose_cases(data + [data[0]], manifest)


async def test_bound_model_stops_before_provider_on_changed_request(tmp_path):
    row, _ = synthetic_row()
    model = experiment.BoundModel(
        SimpleNamespace(name="unused", version="1"), tmp_path / "receipt.json", "wrong"
    )
    with pytest.raises(ValueError, match="frozen request"):
        await model.generate(experiment.reader_request(row))
    assert not list(tmp_path.iterdir())


async def test_oversize_view_never_truncates_original_sources(monkeypatch):
    row, scope = synthetic_row()
    monkeypatch.setattr(experiment, "MAX_VIEW_BYTES", 1)
    with pytest.raises(ValueError, match="no truncation"):
        await experiment.structured_view(row, scope, Analyzer(), Planner())


async def test_empty_analysis_still_exercises_planner_and_preserves_raw():
    class Empty:
        name, version = "empty", "1"

        async def generate(self, request):
            return {"memories": []}

    row, scope = synthetic_row()
    view, audit = await experiment.structured_view(row, scope, Empty(), Planner())
    assert view["claims"] == []
    assert audit["engine_result"]["scanned_record_count"] == 0
    assert experiment.augmented_request(row, view).input["context_items"] == list(
        row.context
    )


async def test_receipted_generation_retains_failures_without_retry(tmp_path):
    class Failing:
        name, version = "fail", "1"
        calls = 0

        async def generate(self, request):
            self.calls += 1
            raise RuntimeError("test")

    row, _ = synthetic_row()
    request = experiment.reader_request(row)
    provider = Failing()
    model = experiment.BoundModel(
        provider, tmp_path / "receipt.json", _hash(request.model_dump(mode="json"))
    )
    for _ in range(2):
        with pytest.raises((RuntimeError, ValueError)):
            await model.generate(request)
    assert provider.calls == 1


async def test_live_shape_and_key_free_cache_replay_deduplicate_identical_judges(
    tmp_path, monkeypatch
):
    calls = []

    def factory(cfg, key, observer):
        class Fake:
            name, version = "fake-provider", "1"

            async def generate(self, request):
                calls.append(request)
                observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
                if "messages" in request.input:
                    return await Analyzer().generate(request)
                if "default_subject" in request.input:
                    return await Planner().generate(request)
                if "candidate_answer" in request.input:
                    return {"answer_correct": True, "rationale": "synthetic"}
                return {
                    "answer": "One visit.",
                    "abstained": False,
                    "cited_memory_ids": ["source-0"],
                    "derived": None,
                }

        return Fake()

    monkeypatch.setattr(experiment, "_default_provider_factory", factory)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-key")
    row, scope = synthetic_row()
    rows = [(1, row, scope)]
    plan = await experiment.make_plan(rows, {"synthetic": "bound"})
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await experiment.execute(args, rows, plan)
    assert live["status"] == "complete", live
    assert len(calls) == 5  # identical answers share one cached judge request
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await experiment.execute(args, rows, plan)
    assert replay["status"] == "complete", replay
    assert replay["summary"] == live["summary"]
    assert len(calls) == 5
    assert sum(v["attempts_reserved"] for v in replay["usage"].values()) == 5
    assert all(
        "synthetic-key" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )

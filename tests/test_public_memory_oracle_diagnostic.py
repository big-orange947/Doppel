from copy import deepcopy
from types import SimpleNamespace

import pytest

from benchmarks.public_memory_oracle_diagnostic import (
    CATEGORIES,
    build_plan,
    execute,
    matched_oracle,
    prepare_rows,
    select_ids,
)
from benchmarks.public_memory_reader_v2 import build_request


def sample(identity, category="single-session-user"):
    return {
        "question_id": identity,
        "question_type": category,
        "question": "Where was the meeting?",
        "answer": "Room C",
        "question_date": "2026-10-02T00:00:00Z",
        "haystack_session_ids": ["noise", "source"],
        "haystack_dates": ["2026-10-01T00:00:00Z", "2026-09-30T00:00:00Z"],
        "haystack_sessions": [
            [{"role": "user", "content": "Irrelevant background."}],
            [
                {"role": "user", "content": "We met in Room C.", "has_answer": True},
                {"role": "assistant", "content": "I suggested a video call."},
            ],
        ],
        "answer_session_ids": ["source"],
    }


def fixtures():
    source = [
        sample("case-" + str(i), category) for i, category in enumerate(CATEGORIES)
    ]
    source.extend([sample("opened_abs"), sample("protected_abs"), sample("new_abs")])
    manifest = {
        "cases": [
            *[
                {"case_id": r["question_id"], "partition": "diagnostic"}
                for r in source[:7]
            ],
            {"case_id": "protected_abs", "partition": "reserved"},
        ]
    }
    oracle = deepcopy(source)
    for r in oracle:
        r["question_date"] = "2026-10-03T00:00:00Z"
        r["haystack_session_ids"] = ["source"]
        r["haystack_dates"] = [r["haystack_dates"][1]]
        r["haystack_sessions"] = [r["haystack_sessions"][1]]
    return source, oracle, manifest


def test_selection_uses_type_order_not_scores_and_protects_reserved():
    source, _, manifest = fixtures()
    assert select_ids(source, manifest) == [
        *["case-" + str(i) for i in range(6)],
        "opened_abs",
        "new_abs",
    ]
    with pytest.raises(ValueError, match="non-reserved"):
        select_ids(source, manifest, ["new_abs"])


def test_matched_projection_preserves_S_clock_text_and_original_input():
    s, o = sample("normal"), sample("normal")
    before = deepcopy(s)
    o["question_date"] = "2030-01-01T00:00:00Z"
    projected = matched_oracle(s, o)
    assert projected["question_date"] == before["question_date"]
    assert projected["haystack_session_ids"] == ["source"]
    assert s == before


def test_refusal_control_retains_source_sessions_not_empty_context():
    s, o = sample("q_abs"), sample("q_abs")
    s["answer_session_ids"] = []
    o["haystack_session_ids"] = ["noise"]
    assert matched_oracle(s, o)["haystack_session_ids"] == ["noise"]
    o["haystack_session_ids"] = ["absent"]
    with pytest.raises(ValueError, match="not present"):
        matched_oracle(s, o)


def test_reader_no_reference_labels_or_scoring_and_assistant_preserved():
    source, oracle, manifest = fixtures()
    rows = prepare_rows(source, oracle, manifest)
    request = build_request(rows[0])
    assert set(request.input) == {
        "question",
        "question_reference_time",
        "context_items",
    }
    assert "answer_session_ids" not in str(request.input) and "has_answer" not in str(
        request.input
    )
    assert request.input["context_items"][1]["authority"] == "agent_output"
    assert request.input["question_reference_time"].startswith("2026-10-02")
    assert rows[0].scoring.answer == "Room C"


def test_full_context_order_and_no_truncation_or_silent_oversize():
    source, oracle, manifest = fixtures()
    for s in source:
        if not s["question_id"].endswith("_abs"):
            s["answer_session_ids"] = ["noise", "source"]
    rows = prepare_rows(source, oracle, manifest)
    assert rows[0].context[0]["text"] == "We met in Room C."
    plan = build_plan(rows, {})
    assert plan["max_new_calls"] == 16 and not plan["official_longmemeval_metric"]
    source[0]["haystack_sessions"][1][0]["content"] = "x" * 120_000
    with pytest.raises(ValueError, match="exceeds bound"):
        build_plan(prepare_rows(source, oracle, manifest), {})


@pytest.mark.asyncio
async def test_fake_live_and_empty_key_replay_no_new_calls(tmp_path, monkeypatch):
    source, oracle, manifest = fixtures()
    rows = prepare_rows(source, oracle, manifest)
    plan = build_plan(rows, {})
    calls = []

    def factory(config, key, observer):
        class Fake:
            name, version = "fake-oracle-control", "1"

            async def generate(self, request):
                calls.append(request)
                observer({"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
                if "context_items" in request.input:
                    return {
                        "answer": "Room C",
                        "abstained": False,
                        "cited_memory_ids": [
                            request.input["context_items"][0]["memory_id"]
                        ],
                    }
                return {"answer_correct": True, "rationale": "Synthetic control."}

        return Fake()

    async def unchanged(key):
        return 5.0

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    args = SimpleNamespace(run_dir=tmp_path, cache_only=False)
    live = await execute(
        args, rows, plan, provider_factory=factory, balance_reader=unchanged
    )
    # Identical synthetic judge requests are legitimately content-cache deduplicated.
    assert live["status"] == "complete" and len(calls) == 9
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await execute(
        args, rows, plan, provider_factory=factory, balance_reader=unchanged
    )
    assert replay["rows"] == live["rows"] and len(calls) == 9
    assert all(v["cache_misses_this_instance"] == 0 for v in replay["usage"].values())


@pytest.mark.asyncio
async def test_balance_stop_before_network_and_no_auto_extension(tmp_path, monkeypatch):
    source, oracle, manifest = fixtures()
    rows = prepare_rows(source, oracle, manifest)
    plan = build_plan(rows, {})
    values = iter([5.0, 3.9, 3.9])

    async def declining(key):
        return next(values)

    class NoNetwork:
        name, version = "offline", "1"

        async def generate(self, request):
            pytest.fail("network must not be attempted")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    report = await execute(
        SimpleNamespace(run_dir=tmp_path, cache_only=False),
        rows,
        plan,
        provider_factory=lambda *_: NoNetwork(),
        balance_reader=declining,
    )
    assert report["stopped_reason"] == "balance_budget_reached"
    assert all(v["ledger"]["attempts_reserved"] == 0 for v in report["usage"].values())

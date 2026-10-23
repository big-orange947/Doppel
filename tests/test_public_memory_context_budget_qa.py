from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_context_budget_qa as budget
from benchmarks.public_memory_answer_comparison import AnswerRow, _request_sha256
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_task_accuracy import request as task_request


def queue():
    runtime = SimpleNamespace(
        query=SimpleNamespace(
            query="Which city?",
            reference_time=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )
    scoring = SimpleNamespace(
        answer="Oslo", category="single-session-user", abstention=False
    )
    source = {
        "channel": "raw",
        "memory_id": "m0",
        "scope_key": "owner1",
        "role": "user",
        "actor": "owner",
        "authority": "human_self",
        "text": "I live in Oslo",
        "observed_at": "2023-12-01T00:00:00+00:00",
        "temporal_status": None,
        "valid_from": None,
        "valid_to": None,
        "source_events": ["event0"],
    }
    old = {
        "reader_output": {
            "answer": "Unavailable",
            "abstained": True,
            "cited_memory_ids": [],
            "derived": None,
        },
        "grade": {"answer_correct": False, "rationale": "No city supplied"},
    }
    result = []
    for i, limit in enumerate(budget.BUDGETS):
        context = () if i == 0 else (source,)
        row = AnswerRow(i, "case1", "budget", runtime, scoring, context)
        result.append(
            {
                "ordinal": 1,
                "budget": limit,
                "row": row,
                "request": reader_request(row),
                "baseline": deepcopy(old),
            }
        )
    return result


class FakeModel:
    name, version = "fake", "frozen"

    def __init__(self, stage, observer, calls, fail=False):
        self.stage, self.observer, self.calls, self.fail = stage, observer, calls, fail

    async def generate(self, request):
        self.calls.append((self.stage, request))
        if self.fail:
            raise RuntimeError("SECRET-provider-error")
        self.observer({"input_tokens": 20, "output_tokens": 10, "total_tokens": 30})
        if self.stage == "reader":
            return {
                "answer": "Oslo",
                "abstained": False,
                "cited_memory_ids": ["m0"],
                "derived": None,
            }
        return {"answer_correct": True, "rationale": "Matches reference"}


def plan():
    return {
        "plan_fingerprint": "fake-plan",
        "stages": {
            name: {
                "max_calls": 58,
                "max_request_bytes": 100000,
                "max_total_request_bytes": 5800000,
            }
            for name in budget.STAGES
        },
    }


def args(path, *, parents=(), cache_only=False):
    return SimpleNamespace(
        run_dir=path, cache_only=cache_only, cache_parent=list(parents)
    )


def provider(monkeypatch, calls, *, fail=False):
    def factory(config, key, observer):
        stage = "reader" if config.max_completion_tokens == 2048 else "judge"
        return FakeModel(stage, observer, calls, fail=fail)

    monkeypatch.setattr(budget, "_default_provider_factory", factory)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-not-persisted")


@pytest.mark.asyncio
async def test_live_deduplicates_two_caps_and_reuses_baseline(tmp_path, monkeypatch):
    calls = []
    provider(monkeypatch, calls)
    work = queue()
    before = deepcopy([r["baseline"] for r in work])
    output = await budget.execute(args(tmp_path / "live"), plan(), work)
    assert output["status"] == "complete"
    assert [stage for stage, _ in calls] == ["reader", "judge"]
    assert output["rows"][0]["reader_output"] == before[0]["reader_output"]
    assert output["rows"][0]["grade"] == before[0]["grade"]
    assert [r["baseline"] for r in work] == before
    assert output["summary"]["48000"]["paired_vs_24000"] == {
        "paired": 1,
        "gains": 1,
        "losses": 0,
    }
    assert output["usage"]["reader"]["ledger"]["attempts_reserved"] == 1
    assert output["usage"]["judge"]["ledger"]["reported_tokens"]["total_tokens"] == 30
    payload = calls[0][1].input
    assert set(payload) == {"question", "question_reference_time", "context_items"}
    assert "reference_answer" not in payload
    assert payload["context_items"][0]["actor"] == "owner"
    assert calls[1][1].input == task_request("Which city?", "Oslo", "Oslo").input
    assert "context_items" not in calls[1][1].input


@pytest.mark.asyncio
async def test_cache_only_replay_zero_calls_and_identical_results(
    tmp_path, monkeypatch
):
    calls = []
    provider(monkeypatch, calls)
    first = await budget.execute(args(tmp_path / "first"), plan(), queue())
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    provider_count = len(calls)
    second = await budget.execute(
        args(tmp_path / "second", parents=[tmp_path / "first"], cache_only=True),
        plan(),
        queue(),
    )
    assert second["status"] == "complete"
    assert len(calls) == provider_count
    assert second["summary"] == first["summary"]
    for a, b in zip(first["rows"], second["rows"], strict=True):
        for field in ("reader_output", "grade", "checks", "context_sha256"):
            assert a[field] == b[field]
    assert all(
        value["ledger"]["attempts_reserved"] == 0 for value in second["usage"].values()
    )
    assert all(
        value["read_only_cache_hits_this_instance"] == 1
        for value in second["usage"].values()
    )


@pytest.mark.asyncio
async def test_failure_preserved_without_retry_or_followup_judge(tmp_path, monkeypatch):
    calls = []
    provider(monkeypatch, calls, fail=True)
    output = await budget.execute(args(tmp_path / "failed"), plan(), queue())
    assert output["status"] == "failed"
    assert len(calls) == 1
    assert output["failure"]["stage"] == "reader"
    assert output["usage"]["reader"]["ledger"]["attempt_status_counts"]["failed"] == 1
    assert output["usage"]["judge"]["ledger"]["attempts_reserved"] == 0
    assert "SECRET" not in str(output)
    assert (tmp_path / "failed" / "row-01-48000.json").is_file()
    with pytest.raises(ValueError, match="fresh run"):
        await budget.execute(args(tmp_path / "failed"), plan(), queue())


@pytest.mark.asyncio
async def test_cache_miss_never_bills(tmp_path, monkeypatch):
    calls = []
    provider(monkeypatch, calls)
    output = await budget.execute(
        args(tmp_path / "missing", cache_only=True), plan(), queue()
    )
    assert output["status"] == "failed"
    assert calls == []
    assert output["rows"][-1]["reader"]["execution"] == "cache_only_miss"


def test_baseline_conflict_fails_closed():
    work = queue()
    other = deepcopy(work[0])
    other["baseline"]["reader_output"]["answer"] = "Conflicting answer"
    work.append(other)
    with pytest.raises(ValueError, match="conflicting historical"):
        budget.seed_baseline(
            work, SimpleNamespace(results={}), SimpleNamespace(results={})
        )


def test_summary_reports_gains_and_losses_separately():
    def row(ordinal, cap, correct):
        return {
            "ordinal": ordinal,
            "budget": cap,
            "question_type": "temporal",
            "abstention_label": False,
            "grade": {"answer_correct": correct},
            "context_bytes": 100,
        }

    result = budget.summary(
        [
            row(1, 24000, False),
            row(1, 48000, True),
            row(2, 24000, True),
            row(2, 48000, False),
        ]
    )
    assert result["48000"]["paired_vs_24000"] == {"paired": 2, "gains": 1, "losses": 1}
    assert result["48000"]["correct"] == 1
    assert result["96000"]["accuracy"] is None


def test_immutable_output_and_finite_json(tmp_path):
    path = tmp_path / "report.json"
    budget.write_new(path, {"ready": True})
    with pytest.raises(FileExistsError):
        budget.write_new(path, {"ready": False})


def test_request_identity_includes_changed_context():
    work = queue()
    hashes = [_request_sha256(item["request"]) for item in work]
    assert hashes[0] != hashes[1]
    assert hashes[1] == hashes[2]

from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_public_memory_context_budget_qa import queue as sample_queue

from benchmarks import public_memory_reserved_final as reserved


@pytest.fixture(autouse=True)
def no_live_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no real provider in unit tests")

    monkeypatch.setattr(reserved, "_default_provider_factory", forbidden)


def metadata():
    return {
        "cases": [
            {
                "case_id": f"case{i}",
                "history_group": f"h{i}",
                "partition": "reserved-not-run",
                "raw_turn_count": 548 if i == 0 else 500,
                "chunk_count": 56 if i == 0 else 50,
            }
            for i in range(10)
        ]
        + [{"case_id": "opened", "history_group": "opened", "partition": "diagnostic"}]
    }


def test_exact_partition_and_frozen_size():
    assert len(reserved.reserved_metadata(metadata())) == 10
    parent = metadata()
    parent["cases"][0]["partition"] = "reserved"
    with pytest.raises(ValueError):
        reserved.reserved_metadata(parent)


@pytest.mark.parametrize(
    "damage",
    ["duplicate_id", "duplicate_history", "opened_history", "messages", "chunks"],
)
def test_metadata_rejects_drift(damage):
    parent = metadata()
    if damage == "duplicate_id":
        parent["cases"][1]["case_id"] = "case0"
    elif damage == "duplicate_history":
        parent["cases"][1]["history_group"] = "h0"
    elif damage == "opened_history":
        parent["cases"][0]["history_group"] = "opened"
    else:
        parent["cases"][0][
            "raw_turn_count" if damage == "messages" else "chunk_count"
        ] += 1
    with pytest.raises(ValueError):
        reserved.reserved_metadata(parent)


def preparation():
    sample = sample_queue()[1]
    cases, rows = [], []
    for i in range(1, 11):
        scoring = SimpleNamespace(
            case_id=f"case{i}",
            category="type",
            abstention=i == 6,
            answer="REFERENCE-ONLY",
        )
        case = SimpleNamespace(runtime=sample["row"].runtime, scoring=scoring)
        context = deepcopy(list(sample["row"].context))
        row = reserved.AnswerRow(
            i - 1,
            scoring.case_id,
            "reserved-fixed-fusion",
            case.runtime,
            scoring,
            tuple(context),
        )
        request = reserved.reader_request(row)
        cases.append(case)
        rows.append(
            {
                "ordinal": i,
                "case_id": scoring.case_id,
                "context": context,
                "context_sha256": reserved.sha(reserved.encoded(context)),
                "reader_request_sha256": reserved._request_sha256(request),
            }
        )
    return cases, {"status": "complete", "rows": rows}


def test_request_binding_never_supplies_gold_or_profile():
    cases, prepared = preparation()
    queue = reserved.requests_for(cases, prepared)
    assert len(queue) == 10
    assert all(
        set(request.input) == {"question", "question_reference_time", "context_items"}
        for _, request, _ in queue
    )
    assert all("REFERENCE-ONLY" not in str(request.input) for _, request, _ in queue)


@pytest.mark.parametrize("damage", ["partial", "digest", "request", "order"])
def test_paid_gate_rejects_incomplete_or_changed_preparation(damage):
    cases, prepared = preparation()
    if damage == "partial":
        prepared["rows"].pop()
    elif damage == "digest":
        prepared["rows"][0]["context_sha256"] = "bad"
    elif damage == "request":
        prepared["rows"][0]["reader_request_sha256"] = "bad"
    else:
        prepared["rows"].reverse()
    with pytest.raises(ValueError):
        reserved.requests_for(cases, prepared)


@pytest.mark.asyncio
async def test_existing_schema_never_reset():
    class Connection:
        async def fetchval(self, query, name):
            assert query.startswith("SELECT")
            assert name == "test-schema"
            return True

    with pytest.raises(ValueError, match="no reset"):
        await reserved.require_fresh_schema(Connection(), "test-schema")


def test_summary_keeps_positive_negative_denominators_separate():
    result = reserved.summary(
        [
            {
                "question_type": "type",
                "abstention_label": False,
                "grade": {"answer_correct": False},
            },
            {
                "question_type": "type",
                "abstention_label": True,
                "grade": {"answer_correct": True},
            },
        ]
    )
    assert result["expected"] == 10
    assert result["completed"] == 2
    assert result["answerable"]["correct"] == 0
    assert result["unanswerable"]["correct"] == 1
    assert result["by_type"]["type"]["completed"] == 1

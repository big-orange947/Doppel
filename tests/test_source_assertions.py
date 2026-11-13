"""Clause/source separation and explicit isolation; no paid model calls."""

from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    MemoryRecord,
    MemoryScope,
    PersonalMemoryAnalysisRequest,
)
from doppel_memory.source_assertions import (
    SourceAssertionPersonalMemoryAnalyzer,
    assemble_source_assertions,
)


def bound():
    return PersonalMemoryAnalysisRequest(
        scope=MemoryScope(user_id="u", agent_id="a"),
        messages=[
            ChatMessage.of(
                "owner",
                "My cousin rented a studio. I stayed at home.",
                datetime(2026, 11, 1, tzinfo=UTC),
                message_id="m",
            )
        ],
    )


class Model:
    name, version = "synthetic-assertions", "1"

    def __init__(self, invalid=False):
        self.invalid, self.calls = invalid, 0

    async def generate(self, request):
        self.calls += 1
        values = [
            {
                "evidence_id": "m",
                "clause": "My cousin rented a studio.",
                "memory_type": "fact",
                "topic_key": "cousin.rental",
            },
            {
                "evidence_id": "m",
                "clause": "I stayed at home.",
                "memory_type": "state",
                "topic_key": "location.self",
                "temporal_status": "current",
            },
        ]
        if self.invalid:
            values.insert(0, {"evidence_id": "m", "clause": "invented"})
        return {"memories": values}


async def materialize(tmp_path, model, **options):
    from benchmarks.personal_memory_lifecycle_probe import exercise

    request = bound()
    data = {
        "cases": [
            {
                "id": "u",
                "batches": [[request.messages[0].model_dump(mode="json")]],
                "queries": [],
            }
        ]
    }
    result = await exercise(
        data,
        tmp_path,
        model,
        analyzer=SourceAssertionPersonalMemoryAnalyzer(model, **options),
    )
    request = request.model_copy(
        update={"scope": MemoryScope(user_id="u", agent_id="synthetic-lifecycle-probe")}
    )
    records = [
        MemoryRecord.model_validate(r)
        for r in result["rows"][0]["records"]
        if r["extractor"] != "ingestor"
    ]
    return request, records, result


async def test_workflow_stores_distinct_clauses_and_context_once(tmp_path):
    request, records, result = await materialize(tmp_path / "state", Model())
    assert result["status"] == "complete"
    assert {r.content for r in records} == {
        "My cousin rented a studio.",
        "I stayed at home.",
    }
    packet = assemble_source_assertions(request, records)
    assert len(packet["claims"]) == 2 and len(packet["sources"]) == 1
    assert packet["sources"]["m"]["text"] == request.messages[0].text
    assert not packet["semantic_support_verified"]


async def test_isolation_reports_rejection_and_keeps_other_valid_assertions(tmp_path):
    reports = []
    _, records, result = await materialize(
        tmp_path / "state",
        Model(invalid=True),
        invalid_policy="isolate",
        diagnostics_observer=reports.append,
    )
    assert result["status"] == "complete" and len(records) == 2
    assert reports[0].total == 3 and reports[0].accepted == 2
    assert reports[0].rejected == [
        {"index": 0, "reason": "source_or_annotation_validation"}
    ]


async def test_default_still_rejects_entire_invalid_batch():
    with pytest.raises(ValueError, match="batch rejected"):
        await SourceAssertionPersonalMemoryAnalyzer(Model(invalid=True)).analyze(
            bound()
        )


def test_isolation_requires_accounting_and_has_separate_version():
    with pytest.raises(ValueError, match="diagnostic sink"):
        SourceAssertionPersonalMemoryAnalyzer(Model(), invalid_policy="isolate")
    assert (
        SourceAssertionPersonalMemoryAnalyzer(Model()).version
        != SourceAssertionPersonalMemoryAnalyzer(
            Model(), invalid_policy="isolate", diagnostics_observer=lambda _: None
        ).version
    )


@pytest.mark.parametrize(
    "change", ["source", "span", "actor", "scope", "inactive", "duplicate"]
)
async def test_context_revalidation_rejects_mismatches(tmp_path, change):
    request, records, _ = await materialize(tmp_path / "state", Model())
    if change == "source":
        request = request.model_copy(
            update={
                "messages": [
                    request.messages[0].model_copy(update={"text": "different"})
                ]
            }
        )
    if change == "span":
        records[0].metadata["source_assertion"]["end"] -= 1
    if change == "actor":
        records[0].actor = "agent"
    if change == "scope":
        records[0] = records[0].model_copy(
            update={"scope": MemoryScope(user_id="other", agent_id="a")}
        )
    if change == "inactive":
        records[0] = records[0].model_copy(
            update={"state": __import__("doppel_memory").MemoryState.EXPIRED}
        )
    if change == "duplicate":
        records.append(records[0])
    with pytest.raises(ValueError):
        assemble_source_assertions(request, records)


async def test_failed_diagnostic_publication_returns_no_partial_analysis():
    def fail(report):
        raise OSError("synthetic diagnostic outage")

    with pytest.raises(OSError):
        await SourceAssertionPersonalMemoryAnalyzer(
            Model(), invalid_policy="isolate", diagnostics_observer=fail
        ).analyze(bound())


async def test_unsupported_annotation_is_not_repaired_and_context_ambiguity_rejected():
    class Invalid(Model):
        async def generate(self, request):
            return {
                "memories": [
                    {
                        "evidence_id": "m",
                        "clause": "I stayed at home.",
                        "event_key": "bad",
                        "memory_type": "fact",
                    },
                    {"evidence_id": "m", "clause": "I stayed at home."},
                ]
            }

    reports = []
    result = await SourceAssertionPersonalMemoryAnalyzer(
        Invalid(), invalid_policy="isolate", diagnostics_observer=reports.append
    ).analyze(bound())
    assert len(result.memories) == 1 and reports[0].accepted == 1
    repeated = bound().model_copy(
        update={
            "messages": [
                bound()
                .messages[0]
                .model_copy(update={"text": "I stayed at home. I stayed at home."})
            ]
        }
    )
    result = await SourceAssertionPersonalMemoryAnalyzer(
        Invalid(), invalid_policy="isolate", diagnostics_observer=reports.append
    ).analyze(repeated)
    assert not result.memories and len(reports[-1].rejected) == 2

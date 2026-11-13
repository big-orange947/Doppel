"""Host-controlled source rendering, not proof of semantic interpretation."""

from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    MemoryScope,
    PersonalMemoryExtractor,
    PersonalMemoryExtractorConfig,
)
from doppel_memory.intelligence import PersonalMemoryAnalysisRequest
from doppel_memory.source_clauses import SourceClausePersonalMemoryAnalyzer


def message():
    return ChatMessage.of(
        "owner",
        "Lee bought a piano. I have not bought one.",
        datetime(2026, 11, 1, tzinfo=UTC),
        message_id="m",
    )


class Model:
    name, version = "synthetic-clause-model", "1"

    def __init__(self, **changes):
        self.changes, self.requests = changes, []

    async def generate(self, request):
        self.requests.append(request)
        return {
            "memories": [
                {
                    "evidence_id": "m",
                    "clause": "I have not bought one.",
                    "memory_type": "state",
                    "temporal_status": "current",
                    **self.changes,
                }
            ]
        }


async def test_content_and_actor_are_host_bound_and_whole_context_survives():
    source = message()
    analyzer = SourceClausePersonalMemoryAnalyzer(Model())
    proposals = await PersonalMemoryExtractor(
        analyzer, PersonalMemoryExtractorConfig(owner_target_scope="conversation")
    ).process(MemoryScope(user_id="u", agent_id="a"), source)
    assert len(proposals) == 1 and proposals[0].content == source.text
    assert proposals[0].actor == "owner" and proposals[0].metadata["subject_id"] == "u"
    assert proposals[0].proposed_state.value == "candidate"
    assert proposals[0].metadata["source_clause"]["text"] == "I have not bought one."
    assert not proposals[0].metadata["source_clause"]["semantic_support_verified"]


@pytest.mark.parametrize(
    "changes",
    [
        {"clause": "Lee has not bought one."},
        {"evidence_id": "other"},
        {"clause": " "},
        {"subject": "contact"},
        {"content": "invented summary"},
    ],
)
async def test_unbound_or_model_owned_content_identity_is_rejected(changes):
    with pytest.raises(ValueError):
        await SourceClausePersonalMemoryAnalyzer(Model(**changes)).analyze(
            PersonalMemoryAnalysisRequest(
                scope=MemoryScope(user_id="u", agent_id="a"), messages=[message()]
            )
        )


async def test_oversize_source_stops_before_model_without_truncation():
    model = Model()
    with pytest.raises(ValueError, match="no truncation"):
        await SourceClausePersonalMemoryAnalyzer(model, max_source_chars=5).analyze(
            PersonalMemoryAnalysisRequest(
                scope=MemoryScope(user_id="u", agent_id="a"), messages=[message()]
            )
        )
    assert not model.requests


async def test_contact_identity_comes_from_source_sender():
    source = message().model_copy(update={"actor": "contact", "sender_id": "peer-9"})
    result = await PersonalMemoryExtractor(
        SourceClausePersonalMemoryAnalyzer(Model()),
        PersonalMemoryExtractorConfig(owner_target_scope="conversation"),
    ).process(MemoryScope(user_id="u", agent_id="a"), source)
    assert (
        result[0].metadata["subject_id"] == "peer-9"
        and result[0].content == source.text
    )


async def test_full_workflow_preserves_source_context_and_rebuilds_from_cache(tmp_path):
    from benchmarks.personal_memory_lifecycle_probe import exercise, sha
    from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel

    data = {
        "cases": [
            {
                "id": "fresh",
                "batches": [[message().model_dump(mode="json")]],
                "queries": [{"id": "current", "temporal_view": "current"}],
            }
        ]
    }
    ledger = DurableCallLedger(
        tmp_path / "ledger", budget_id="source-clause-test", max_calls=1
    )
    try:
        model = Model()
        cached = PilotStructuredModel(
            model, ledger=ledger, cache_dir=tmp_path / "cache"
        )
        first = await exercise(
            data,
            tmp_path / "first",
            cached,
            analyzer=SourceClausePersonalMemoryAnalyzer(cached),
        )
        forbidden = Model(clause="unbound")
        replay = PilotStructuredModel(
            forbidden, ledger=ledger, cache_dir=tmp_path / "cache", cache_only=True
        )
        second = await exercise(
            data,
            tmp_path / "second",
            replay,
            analyzer=SourceClausePersonalMemoryAnalyzer(replay),
        )
        assert first["status"] == second["status"] == "complete"
        assert first["rows"][0]["views"] == second["rows"][0]["views"]
        assert first["rows"][0]["projection"][0]["content"] == message().text
        assert not forbidden.requests and ledger.report()["attempts_reserved"] == 1
        assert sha(first["rows"][0]["observations"]) == sha(
            second["rows"][0]["observations"]
        )
    finally:
        ledger.close()


async def test_bad_clause_stops_workflow_before_derived_writes(tmp_path):
    from benchmarks.personal_memory_lifecycle_probe import exercise

    model = Model(clause="invented")
    result = await exercise(
        {
            "cases": [
                {
                    "id": "bad",
                    "batches": [[message().model_dump(mode="json")]],
                    "queries": [],
                }
            ]
        },
        tmp_path / "state",
        model,
        analyzer=SourceClausePersonalMemoryAnalyzer(model),
    )
    assert result["status"] == "stopped" and len(model.requests) == 1
    assert result["rows"][0]["projection"] == []

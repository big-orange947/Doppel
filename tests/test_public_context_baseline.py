"""Synthetic sources; production Store/context guards, no network/quality claims."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.public_context_baseline import (
    RawHistoryHost,
    score_evidence,
    select_diagnostic_cases,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_pilot import build_manifest
from doppel_memory.models import (
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    MemoryState,
    RecallResult,
)
from doppel_memory.sqlite_store import SQLiteStore
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope


def sample(i: int = 0) -> dict:
    return {
        "question_id": f"synthetic-{i}",
        "question_type": "multi-session",
        "question": "not used to ingest",
        "answer": "GOLD_SECRET",
        "question_date": "2024/01/03 12:00",
        "answer_session_ids": ["same-id"],
        "haystack_session_ids": ["same-id", "same-id"],
        "haystack_dates": ["2024/01/02 12:00", "2024/01/01 12:00"],
        "haystack_sessions": [
            [
                {"role": "user", "content": f" raw {i} source ", "has_answer": True},
                {
                    "role": "assistant",
                    "content": " historical reply ",
                    "has_answer": True,
                },
            ],
            [
                {"role": "user", "content": "", "has_answer": False},
                {
                    "role": "user",
                    "content": "Second session source",
                    "has_answer": True,
                },
            ],
        ],
    }


class Candidates:
    def __init__(self, items: list[RecallResult]) -> None:
        self.items = items

    async def search(self, store, query, scopes, *, filters=None, limit=10):
        assert filters.states == {MemoryState.CONFIRMED}
        return self.items


async def setup(tmp_path: Path):
    store = SQLiteStore(tmp_path / "raw.sqlite3")
    host = RawHistoryHost(store)
    prepared = prepare_case(sample(), dataset_namespace="synthetic")
    scope = memory_scope("run", prepared.runtime.user_id)
    records = await host.ingest(prepared.runtime, scope, max_messages=1)
    candidates = [
        RecallResult(
            scope=scope,
            memory_id=r.memory_id,
            fact="POISONED_CANDIDATE_TEXT",
            actor="owner",
            authority=FactAuthority.HUMAN_SELF,
            similarity=0.9,
        )
        for r in records
    ]
    return store, host, prepared, scope, records, candidates


@pytest.mark.asyncio
async def test_assistant_raw_attribution_provenance_blank_turn_mapping(
    tmp_path: Path,
) -> None:
    store, host, prepared, scope, records, candidates = await setup(tmp_path)
    try:
        result = await AttributedContextRetriever(
            store,
            strategy=Candidates(candidates),
            resolve_event=host.resolve_event,
        ).search(scope, "natural query")
        assert [s.text for s in result.snippets] == [
            " raw 0 source ",
            " historical reply ",
            "Second session source",
        ]
        assistant = result.snippets[1]
        assert (
            assistant.role == "assistant"
            and assistant.authority == FactAuthority.AGENT_OUTPUT
        )
        assert assistant.channel == "historical-dialogue-context"
        assert host.retrieved_positions(result.snippets) == [(0, 0), (0, 1), (1, 1)]
        assert result.revalidated == 3 and not result.rejected
        assert len(records) == 3
        assert (
            records[0].created_at > records[2].created_at
        )  # Original order, not sorted.
        assert len({r.source_event_id for r in records}) == 3
        assert "GOLD_SECRET" not in result.model_dump_json()
        replay = await host.ingest(prepared.runtime, scope, max_messages=1)
        assert [r.memory_id for r in replay] == [r.memory_id for r in records]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_inactive_duplicate_orphan_and_unresolved_provenance(
    tmp_path: Path,
) -> None:
    store, host, _, scope, records, candidates = await setup(tmp_path)
    try:
        await store.transition(scope, records[0].memory_id, MemoryState.EXPIRED)
        host.sources.pop((scope.scope_key, records[2].source_event_id))
        extra = RecallResult(scope=scope, memory_id="orphan", fact="bad")
        result = await AttributedContextRetriever(
            store,
            strategy=Candidates([*candidates, candidates[1], extra]),
            resolve_event=host.resolve_event,
        ).search(scope, "natural query")
        assert len(result.snippets) == 1 and result.snippets[0].role == "assistant"
        assert result.rejected == {
            "inactive_or_unconfirmed": 1,
            "unresolved_provenance": 1,
            "duplicate": 1,
            "missing_store_record": 1,
        }
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cross_scope_candidates_fail_closed(tmp_path: Path) -> None:
    store, host, _, scope, _, candidates = await setup(tmp_path)
    try:
        candidates[0].scope = MemoryScope(user_id="other-owner", agent_id="agent")
        with pytest.raises(MemoryIsolationError, match="escaped"):
            await AttributedContextRetriever(
                store,
                strategy=Candidates(candidates),
                resolve_event=host.resolve_event,
            ).search(scope, "natural query")
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_reranker_cannot_invent_a_hit_or_poison_source_text(
    tmp_path: Path,
) -> None:
    store, host, _, scope, _, candidates = await setup(tmp_path)

    class Reranker:
        invent = False

        async def rerank(self, query, items, *, limit):
            return [
                items[1].model_copy(
                    update={
                        "fact": "poison",
                        "memory_id": "invented" if self.invent else items[1].memory_id,
                    }
                )
            ]

    try:
        reranker = Reranker()
        retriever = AttributedContextRetriever(
            store,
            strategy=Candidates(candidates),
            resolve_event=host.resolve_event,
            reranker=reranker,
        )
        assert (await retriever.search(scope, "query")).snippets[
            0
        ].text == " historical reply "
        reranker.invent = True
        with pytest.raises(ValueError, match="noncandidate"):
            await retriever.search(scope, "query")
    finally:
        await store.close()


def test_scoring_counts_occurrences_and_complete_coverage_separately() -> None:
    scoring = prepare_case(sample(), dataset_namespace="synthetic").scoring
    partial = score_evidence(scoring, [(0, 0), (0, 0), (0, 1)])
    assert partial["annotated_turn_recall"] == 2 / 3
    assert partial["annotated_session_recall"] == 0.5
    assert partial["all_annotated_sessions_covered"] is False
    assert (
        score_evidence(scoring, [(0, 1), (1, 1)])["all_annotated_sessions_covered"]
        is True
    )
    unlabeled = deepcopy(sample())
    unlabeled["answer_session_ids"] = []
    for session in unlabeled["haystack_sessions"]:
        for turn in session:
            turn["has_answer"] = False
    empty = score_evidence(
        prepare_case(unlabeled, dataset_namespace="synthetic").scoring, [(0, 0)]
    )
    assert empty["annotated_turn_recall"] is None
    assert empty["all_annotated_sessions_covered"] is None


def test_manifest_validation_never_runs_reserved_or_replaces_cases() -> None:
    data = [sample(i) for i in range(4)]
    manifest = build_manifest(
        data,
        dataset_namespace="synthetic",
        run_namespace="run",
        source_sha256="a" * 64,
        diagnostic_count=2,
        reserved_count=2,
    )
    selected = select_diagnostic_cases(data, manifest, source_sha256="a" * 64)
    assert {s.case_id for _, s in selected} == {
        row["case_id"] for row in manifest["cases"] if row["partition"] == "diagnostic"
    }
    with pytest.raises(ValueError, match="integrity"):
        select_diagnostic_cases(data, manifest, source_sha256="b" * 64)
    tampered = deepcopy(manifest)
    tampered["cases"][0]["partition"] = "reserved-not-run"
    with pytest.raises(ValueError, match="integrity"):
        select_diagnostic_cases(data, tampered, source_sha256="a" * 64)

"""Real SQLite + production components; fake models/indexes, not quality scores."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.public_memory_ingestion import audit_stored_records
from doppel_memory.consolidation import DeterministicMemoryConsolidator
from doppel_memory.indexing import (
    IndexEntry,
    IndexEntryPage,
    IndexOperationResult,
    IndexOperationStatus,
    memory_index_fingerprint,
)
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisDiagnostics,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    ReferencePersonalMemoryAnalyzer,
    StructuredGenerationRequest,
)
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.query import (
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryEngine,
    ReferencePersonalMemoryQueryPlannerV2,
)
from doppel_memory.sqlite_store import SQLiteStore
from integrations.aml.contract import (
    AddRequest,
    WriteConflict,
    WriteNotReady,
    event_ids,
    memory_scope,
)
from integrations.aml.ingestion import DurableTextualIngestor, IngestionFailure


class ScriptedModel:
    name = "synthetic-model-no-network"
    version = "1"

    def __init__(self) -> None:
        self.requests: list[StructuredGenerationRequest] = []
        self.bad_evidence = False
        self.bad_subject = False
        self.block: asyncio.Event | None = None
        self.started = asyncio.Event()

    async def generate(self, request: StructuredGenerationRequest) -> dict:
        self.requests.append(request)
        self.started.set()
        if self.block is not None:
            await self.block.wait()
        if "messages" in request.input:
            return {
                "memories": [
                    {
                        "content": message["text"],
                        "subject": Actor.OWNER
                        if self.bad_subject
                        else message["actor"],
                        "evidence_ids": [
                            "unknown-source"
                            if self.bad_evidence
                            else message["evidence_id"]
                        ],
                        "confidence": 1,
                        "temporal_status": "current",
                    }
                    for message in request.input["messages"]
                ]
            }
        return {
            "schema_version": 2,
            "operation": "lookup",
            "temporal_view": "unbounded",
            "search_text": request.input["query"],
            "confidence": 1,
        }


class MemoryIndex:
    identity = "fake-index-for-contracts-only:v1"

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], IndexEntry] = {}
        self.fail = False

    async def inspect(self, scope: MemoryScope, memory_id: str) -> IndexEntry | None:
        return self.entries.get((scope.scope_key, memory_id))

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult:
        if self.fail:
            raise RuntimeError("DO_NOT_EXPOSE_PROVIDER_OR_KEY")
        fingerprint = memory_index_fingerprint(record)
        self.entries[(record.scope.scope_key, record.memory_id)] = IndexEntry(
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=fingerprint,
            source_version=record.version,
        )
        return IndexOperationResult(
            index_identity=self.identity,
            status=IndexOperationStatus.INDEXED,
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=fingerprint,
            source_version=record.version,
        )

    async def delete(self, scope: MemoryScope, memory_id: str) -> IndexOperationResult:
        removed = self.entries.pop((scope.scope_key, memory_id), None)
        return IndexOperationResult(
            index_identity=self.identity,
            status=IndexOperationStatus.DELETED
            if removed
            else IndexOperationStatus.MISSING,
            memory_id=memory_id,
            scope_key=scope.scope_key,
        )

    async def scan_entries(
        self,
        scope: MemoryScope,
        *,
        cursor: str = "",
        limit: int = 100,
    ) -> IndexEntryPage:
        rows = sorted(
            (
                entry
                for (key, _), entry in self.entries.items()
                if key == scope.scope_key and entry.memory_id > cursor
            ),
            key=lambda entry: entry.memory_id,
        )
        chosen = rows[:limit]
        return IndexEntryPage(
            entries=chosen,
            has_more=len(rows) > limit,
            next_cursor=chosen[-1].memory_id if chosen else cursor,
        )


def request(**changes: object) -> AddRequest:
    data = {
        "user_id": "synthetic-owner",
        "request_id": "chunk-1",
        "session_id": "session-a",
        "messages": [
            {
                "role": "user",
                "content": " I like astronomy ",
                "timestamp": 1704067200000,
            },
            {
                "role": "assistant",
                "content": "An assistant's suggestion",
                "timestamp": 1704067200000,
            },
        ],
    }
    data.update(changes)
    return AddRequest.model_validate(data)


def host(
    directory: Path,
    store: SQLiteStore,
    model: ScriptedModel,
    index: MemoryIndex,
    *,
    config: PersonalMemoryMinerConfig | None = None,
    max_pages: int = 1_000,
) -> DurableTextualIngestor:
    miner = PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzer(model),
        config
        or PersonalMemoryMinerConfig(
            allowed_source_actors={Actor.OWNER, Actor.AGENT},
            proposed_state=MemoryState.CONFIRMED,
        ),
    )
    return DurableTextualIngestor(
        store,
        journal_path=directory / "journal.sqlite3",
        miner=miner,
        consolidator=DeterministicMemoryConsolidator(),
        index_writers=[index],
        role_actors={"user": Actor.OWNER, "assistant": Actor.AGENT},
        max_index_pages=max_pages,
    )


async def test_production_ingestion_and_natural_planner_boundary(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        completion = await ingestor.ingest(scope, source)
        assert completion.completed and completion.raw_event_count == 2
        assert completion.proposal_count == 2
        assert completion.configured_index_count == 1
        assert len(model.requests) == 1
        for identity in event_ids(scope, source):
            assert await ingestor.resolve_event(scope, identity) is not None
        raw_owner = await ingestor.resolve_event(scope, event_ids(scope, source)[0])
        assert raw_owner is not None and raw_owner.authority == FactAuthority.HUMAN_SELF
        assert raw_owner.metadata["raw"]["source_text"] == " I like astronomy "
        raw_assistant = await ingestor.resolve_event(scope, event_ids(scope, source)[1])
        assert (
            raw_assistant is not None
            and raw_assistant.authority == FactAuthority.AGENT_OUTPUT
        )
        engine = PersonalMemoryQueryEngine(
            store, PersonalMemoryQueryConfig(minimum_lexical_score=0.05)
        )
        result = await engine.query(
            ReferencePersonalMemoryQueryPlannerV2(model),
            "astronomy",
            [scope],
            now=datetime(2024, 1, 5, tzinfo=UTC),
        )
        assert len(model.requests) == 2
        assert model.requests[1].input["query"] == "astronomy"
        assert "messages" not in model.requests[1].input
        assert len(result.hits) == 1
        assert result.hits[0].record.authority == FactAuthority.HUMAN_SELF
        other = memory_scope("local-test", "other-owner")
        assert await ingestor.resolve_event(other, event_ids(scope, source)[0]) is None
        assert not (
            await engine.query(
                ReferencePersonalMemoryQueryPlannerV2(model),
                "astronomy",
                [other],
                now=datetime(2024, 1, 5, tzinfo=UTC),
            )
        ).hits
    finally:
        ingestor.close()
        await store.close()


async def test_restart_and_changed_payload_conflict_before_model(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    first, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, first, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    expected = await ingestor.ingest(scope, source)
    ingestor.close()
    await store.close()
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model = ScriptedModel()
    ingestor = host(tmp_path, store, model, index)
    try:
        index.entries.clear()  # Index loss must be repaired on an identical replay.
        assert await ingestor.ingest(scope, source) == expected
        assert len(index.entries) == 4
        assert not model.requests
        with pytest.raises(WriteConflict):
            await ingestor.ingest(
                scope, source.model_copy(update={"session_id": "changed"})
            )
        assert not model.requests
        assert len((await store.scan(scope, limit=100)).records) == 4
    finally:
        ingestor.close()
        await store.close()


async def test_index_failure_and_cancelled_write_resume_without_reextracting(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    index.fail = True
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    with pytest.raises(IngestionFailure) as error:
        await ingestor.ingest(scope, source)
    assert "DO_NOT_EXPOSE" not in str(error.value)
    assert len(model.requests) == 1
    ingestor.close()
    await store.close()
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    second = ScriptedModel()
    index.fail = False
    ingestor = host(tmp_path, store, second, index)
    try:
        assert (await ingestor.ingest(scope, source)).completed
        assert not second.requests
        assert len((await store.scan(scope, limit=100)).records) == 4
    finally:
        ingestor.close()
        await store.close()


async def test_completed_replay_allowed_while_later_chunk_is_pending(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    first = request()
    second = first.model_copy(update={"request_id": "chunk-2"})
    third = first.model_copy(update={"request_id": "chunk-3"})
    scope = memory_scope("local-test", first.user_id)
    try:
        await ingestor.ingest(scope, first)
        model.bad_evidence = True
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, second)
        calls = len(model.requests)
        assert (await ingestor.ingest(scope, first)).completed
        assert len(model.requests) == calls
        with pytest.raises(WriteNotReady):
            await ingestor.ingest(scope, third)
        assert len(model.requests) == calls
        with pytest.raises(WriteConflict):
            await ingestor.ingest(
                scope, first.model_copy(update={"session_id": "changed"})
            )
        assert len(model.requests) == calls
    finally:
        ingestor.close()
        await store.close()


async def test_unknown_evidence_is_not_persisted_as_a_fact(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    model.bad_evidence = True
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, source)
        assert len((await store.scan(scope, limit=100)).records) == 2
        assert not (
            await store.scan(scope, filters=MemoryFilter(tags={"personal-memory"}))
        ).records
        assert not index.entries
    finally:
        ingestor.close()
        await store.close()


async def test_content_free_audit_persists_and_replays_without_double_counting(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    diagnostics = PersonalMemoryAnalysisDiagnostics(
        total_drafts=2, valid_drafts=2, invalid_drafts=0
    )
    try:
        with pytest.raises(WriteConflict):
            ingestor.record_analysis_diagnostics(scope, source, diagnostics)
        await ingestor.ingest(scope, source)
        missing = ingestor.audit_report()
        assert missing["chunks_without_analysis_observation"] == 1
        assert missing["chunks"][0]["analysis_diagnostics"] is None
        ingestor.record_analysis_diagnostics(scope, source, diagnostics)
        ingestor.record_analysis_diagnostics(scope, source, diagnostics)
        report = ingestor.audit_report()
        assert report["chunk_count"] == report["completed_chunks"] == 1
        row = report["chunks"][0]
        assert row["raw_events"] == row["proposals"] == 2
        records = await audit_stored_records(
            [SimpleNamespace(user_id=source.user_id)],
            {"run_namespace": "local-test"},
            ingestor,
        )
        assert (
            records["raw_records"] == records["derived_records_including_inactive"] == 2
        )
        assert records["provenance_checks"] == 4 and records["provenance_failures"] == 0
        assert records["semantic_truth_verified"] is False
        assert row["analysis_diagnostics"]["valid_drafts"] == 2
        assert report["chunks_without_analysis_observation"] == 0
        assert "astronomy" not in json.dumps(
            report
        ) and "assistant's" not in json.dumps(report)
        assert row["proposal_diagnostics"] == {
            "valid_drafts": 2,
            "low_confidence_drafts": 0,
            "duplicate_drafts": 0,
        }
        with pytest.raises(WriteConflict):
            ingestor.record_analysis_diagnostics(
                scope, source.model_copy(update={"session_id": "changed"}), diagnostics
            )
        with pytest.raises(ValueError, match="reconcile"):
            ingestor.record_analysis_diagnostics(
                scope, source, diagnostics.model_copy(update={"total_drafts": 3})
            )
    finally:
        ingestor.close()
    restarted = host(tmp_path, store, ScriptedModel(), index)
    try:
        assert restarted.audit_report() == report
        await restarted.ingest(scope, source)
        assert restarted.audit_report() == report
    finally:
        restarted.close()
        await store.close()


async def test_failed_evidence_binding_has_observation_but_no_proposal_plan(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    model.bad_evidence = True
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, source)
        ingestor.record_analysis_diagnostics(
            scope,
            source,
            PersonalMemoryAnalysisDiagnostics(
                total_drafts=2, valid_drafts=2, invalid_drafts=0
            ),
        )
        report = ingestor.audit_report()
        row = report["chunks"][0]
        assert row["raw_stage_persisted"] and row["raw_events"] == 2
        assert not row["proposal_stage_persisted"] and row["proposals"] is None
        assert row["analysis_diagnostics"]["valid_drafts"] == 2
        assert row["proposal_diagnostics"] is None
        assert not row["completed"] and report["completed_chunks"] == 0
        assert not row["consolidation_done"] and not index.entries
    finally:
        ingestor.close()
        await store.close()


async def test_live_analyzer_observation_reconciles_invalid_low_confidence_duplicates(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    index = MemoryIndex()
    source = request()
    scope = memory_scope("local-test", source.user_id)

    class DraftModel:
        name, version = "fake-diagnostic-model", "1"

        async def generate(self, request: StructuredGenerationRequest) -> dict:
            valid = {
                "content": "An attributed preference",
                "subject": "owner",
                "evidence_ids": [request.input["messages"][0]["evidence_id"]],
            }
            return {
                "memories": [
                    valid,
                    valid,
                    {**valid, "confidence": 0.1},
                    {"invalid": True},
                ]
            }

    def observer(diagnostics: PersonalMemoryAnalysisDiagnostics) -> None:
        ingestor.record_analysis_diagnostics(scope, source, diagnostics)

    ingestor = DurableTextualIngestor(
        store,
        journal_path=tmp_path / "journal.sqlite3",
        miner=PersonalMemoryMiner(
            ReferencePersonalMemoryAnalyzer(
                DraftModel(), diagnostics_observer=observer
            ),
            PersonalMemoryMinerConfig(
                allowed_source_actors={Actor.OWNER, Actor.AGENT},
                proposed_state=MemoryState.CONFIRMED,
            ),
        ),
        consolidator=DeterministicMemoryConsolidator(),
        index_writers=[index],
        role_actors={"user": Actor.OWNER, "assistant": Actor.AGENT},
    )
    try:
        await ingestor.ingest(scope, source)
        row = ingestor.audit_report()["chunks"][0]
        assert row["analysis_diagnostics"]["total_drafts"] == 4
        assert row["analysis_diagnostics"]["valid_drafts"] == 3
        assert row["analysis_diagnostics"]["invalid_drafts"] == 1
        assert row["proposal_diagnostics"] == {
            "valid_drafts": 3,
            "low_confidence_drafts": 1,
            "duplicate_drafts": 1,
        }
        assert row["proposals"] == 1 and row["completed"]
    finally:
        ingestor.close()
        await store.close()


async def test_store_audit_classifies_conflict_as_governance_not_owner_fact(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    source = request()
    scope = memory_scope("local-test", source.user_id)

    class ConflictingModel:
        name, version = "fake-conflict-model", "1"

        async def generate(self, request: StructuredGenerationRequest) -> dict:
            message = request.input["messages"][0]
            return {
                "memories": [
                    {
                        "content": message["text"],
                        "subject": "owner",
                        "memory_type": "state",
                        "topic_key": "synthetic.slot",
                        "temporal_status": "current",
                        "evidence_ids": [message["evidence_id"]],
                    }
                ]
            }

    ingestor = DurableTextualIngestor(
        store,
        journal_path=tmp_path / "journal.sqlite3",
        miner=PersonalMemoryMiner(
            ReferencePersonalMemoryAnalyzer(ConflictingModel()),
            PersonalMemoryMinerConfig(
                allowed_source_actors={Actor.OWNER, Actor.AGENT},
                proposed_state=MemoryState.CONFIRMED,
            ),
        ),
        consolidator=DeterministicMemoryConsolidator(),
        index_writers=[MemoryIndex()],
        role_actors={"user": Actor.OWNER, "assistant": Actor.AGENT},
    )
    try:
        await ingestor.ingest(scope, source)
        other = source.model_copy(
            update={
                "request_id": "other-claim",
                "messages": [
                    source.messages[0].model_copy(
                        update={"content": "An incompatible slot value"}
                    )
                ],
            }
        )
        await ingestor.ingest(scope, other)
        report = await audit_stored_records(
            [SimpleNamespace(user_id=source.user_id)],
            {"run_namespace": "local-test"},
            ingestor,
        )
        assert report["raw_records"] == 3
        assert report["derived_records_including_inactive"] == 2
        assert report["governance_records"] == 1
        assert report["provenance_checks"] == 7 and report["provenance_failures"] == 0
        assert report["semantic_truth_verified"] is False
    finally:
        ingestor.close()
        await store.close()


async def test_scope_wide_consolidation_and_inactive_index_cleanup(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        await ingestor.ingest(scope, source)
        second = source.model_copy(
            update={"request_id": "chunk-2", "session_id": "session-b"}
        )
        completion = await ingestor.ingest(scope, second)
        assert completion.consolidation_action_count == 2
        page = await store.scan(
            scope, filters=MemoryFilter(include_inactive=True), limit=100
        )
        inactive = [r for r in page.records if r.state == MemoryState.SUPERSEDED]
        assert len(inactive) == 4
        assert all(
            (scope.scope_key, r.memory_id) not in index.entries for r in inactive
        )
        owner = [
            r
            for r in page.records
            if r.actor == Actor.OWNER
            and r.state == MemoryState.CONFIRMED
            and "personal-memory" in r.tags
        ]
        assert len(owner) == 1 and len(owner[0].metadata["evidence"]) == 2
        for bound in owner[0].metadata["evidence"]:
            assert await ingestor.resolve_event(scope, bound["evidence_id"]) is not None
    finally:
        ingestor.close()
        await store.close()


async def test_competing_instance_and_cancel_release_coordinator(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, other_model, index = ScriptedModel(), ScriptedModel(), MemoryIndex()
    model.block = asyncio.Event()
    first = host(tmp_path, store, model, index)
    second = host(tmp_path, store, other_model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    task = asyncio.create_task(first.ingest(scope, source))
    try:
        await asyncio.wait_for(model.started.wait(), timeout=5)
        with pytest.raises(WriteNotReady):
            await second.ingest(scope, source)
        assert not other_model.requests
        with pytest.raises(IngestionFailure, match="active"):
            first.close()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await second.ingest(scope, source)).completed
        assert len(other_model.requests) == 1
    finally:
        if not task.done():
            task.cancel()
        first.close()
        second.close()
        await store.close()


@pytest.mark.parametrize(
    "failure", ["missing-time", "range", "role-omitted", "too-large", "page-bound"]
)
async def test_hard_bounds_and_no_wall_clock_fallback(
    tmp_path: Path, failure: str
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    config = None
    source = request()
    if failure == "missing-time":
        source.messages[0] = source.messages[0].model_copy(update={"timestamp": None})
    elif failure == "range":
        source.messages[0] = source.messages[0].model_copy(update={"timestamp": 10**20})
    elif failure == "role-omitted":
        config = PersonalMemoryMinerConfig()
    elif failure == "too-large":
        config = PersonalMemoryMinerConfig(
            allowed_source_actors={Actor.OWNER, Actor.AGENT}, max_messages=1
        )
    ingestor = host(
        tmp_path,
        store,
        model,
        index,
        config=config,
        max_pages=1 if failure == "page-bound" else 1_000,
    )
    scope = memory_scope("local-test", source.user_id)
    try:
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, source)
        assert len(model.requests) == (1 if failure == "page-bound" else 0)
    finally:
        ingestor.close()
        await store.close()


async def test_raw_store_deletion_is_not_silently_repaired_as_history(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        await ingestor.ingest(scope, source)
        raw = await ingestor.resolve_event(scope, event_ids(scope, source)[0])
        assert raw is not None
        await store.forget(scope, raw.memory_id, hard=True)
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, source)
        assert len(model.requests) == 1
    finally:
        ingestor.close()
        await store.close()


async def test_scope_batched_completed_validation_reconciles_once(
    tmp_path, monkeypatch
):
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    first, second = request(), request(request_id="chunk-2")
    scope = memory_scope("local-test", first.user_id)
    try:
        await ingestor.ingest(scope, first)
        await ingestor.ingest(scope, second)
        calls = len(model.requests)
        reconcile = ingestor._indexes
        scopes = []

        async def count_reconcile(value):
            scopes.append(value.scope_key)
            await reconcile(value)

        monkeypatch.setattr(ingestor, "_indexes", count_reconcile)
        index.entries.clear()
        assert await ingestor.revalidate_completed(scope, [first, second]) == 2
        assert scopes == [scope.scope_key] and index.entries
        assert len(model.requests) == calls
        with pytest.raises(IngestionFailure):
            await ingestor.revalidate_completed(
                scope, [request(request_id="not-completed")]
            )
        with pytest.raises(IngestionFailure):
            await ingestor.revalidate_completed(scope, [first, first])
        raw = await ingestor.resolve_event(scope, event_ids(scope, first)[0])
        assert raw is not None
        await store.forget(scope, raw.memory_id, hard=True)
        with pytest.raises(IngestionFailure):
            await ingestor.revalidate_completed(scope, [first, second])
        assert len(model.requests) == calls
    finally:
        ingestor.close()
        await store.close()


async def test_journal_profile_and_file_identity_are_frozen(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    ingestor.close()
    model.version = "different-profile"
    with pytest.raises(WriteConflict):
        host(tmp_path, store, model, index)
    model.version = "1"
    miner = PersonalMemoryMiner(ReferencePersonalMemoryAnalyzer(model))
    with pytest.raises(ValueError, match="separate"):
        DurableTextualIngestor(
            store,
            journal_path=Path(store.database),
            miner=miner,
            consolidator=DeterministicMemoryConsolidator(),
            index_writers=[index],
            role_actors={"user": Actor.OWNER, "assistant": Actor.AGENT},
        )
    assert not model.requests
    await store.close()


async def test_completed_journal_does_not_contain_query_or_gold_fields(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    try:
        await ingestor.ingest(memory_scope("local-test", source.user_id), source)
        with sqlite3.connect(tmp_path / "journal.sqlite3") as connection:
            row = connection.execute(
                "SELECT completion,proposals,events FROM writes"
            ).fetchone()
        assert row is not None and all(row)
        assert "has_answer" not in str(row) and "question_type" not in str(row)
    finally:
        ingestor.close()
        await store.close()


async def test_partial_raw_write_reuses_existing_event_after_restart(
    tmp_path: Path,
) -> None:
    class PartialStore(SQLiteStore):
        calls = 0

        async def write_event(self, scope: MemoryScope, message):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("synthetic interruption")
            return await super().write_event(scope, message)

    store = PartialStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    with pytest.raises(IngestionFailure) as error:
        await ingestor.ingest(scope, source)
    assert error.value.stage == "raw_events"
    assert not model.requests
    assert len((await store.scan(scope, limit=100)).records) == 1
    ingestor.close()
    await store.close()
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    ingestor = host(tmp_path, store, model, index)
    try:
        assert (await ingestor.ingest(scope, source)).completed
        assert len((await store.scan(scope, limit=100)).records) == 4
        assert len(model.requests) == 1
    finally:
        ingestor.close()
        await store.close()


async def test_later_scope_write_waits_for_pending_predecessor(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    index.fail = True
    try:
        with pytest.raises(IngestionFailure):
            await ingestor.ingest(scope, source)
        with pytest.raises(WriteNotReady):
            await ingestor.ingest(
                scope, source.model_copy(update={"request_id": "later"})
            )
        assert len(model.requests) == 1
        index.fail = False
        await ingestor.ingest(scope, source)
        assert (
            await ingestor.ingest(
                scope, source.model_copy(update={"request_id": "later"})
            )
        ).completed
    finally:
        ingestor.close()
        await store.close()


async def test_abrupt_process_death_preserves_plans_and_releases_sqlite_lock(
    tmp_path: Path,
) -> None:
    # The child writes only synthetic test data, then is killed at the index
    # boundary with Store/proposal/consolidation commits already on disk.
    script = """
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_aml_ingestion import host, ScriptedModel, MemoryIndex, request
from doppel_memory.sqlite_store import SQLiteStore
from integrations.aml.contract import memory_scope
class SuspendedIndex(MemoryIndex):
    async def upsert(self, record):
        print('checkpoint-ready', flush=True)
        await asyncio.Event().wait()
async def main():
    path = Path(sys.argv[1])
    store = SQLiteStore(str(path / 'store.sqlite3'))
    ingestor = host(path, store, ScriptedModel(), SuspendedIndex())
    source = request()
    await ingestor.ingest(memory_scope('local-test', source.user_id), source)
asyncio.run(main())
"""
    child = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, "-c", script, str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        assert child.stdout is not None
        with ThreadPoolExecutor(max_workers=1) as reader:
            ready = reader.submit(child.stdout.readline)
            try:
                assert ready.result(timeout=15).strip() == "checkpoint-ready"
            finally:
                child.kill()
                child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        if child.stdout:
            child.stdout.close()
        if child.stderr:
            child.stderr.close()
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    try:
        assert (
            await ingestor.ingest(memory_scope("local-test", source.user_id), source)
        ).completed
        assert not model.requests
    finally:
        ingestor.close()
        await store.close()


async def test_role_binding_is_host_configuration_not_inferred_from_transport(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    miner = PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzer(model),
        PersonalMemoryMinerConfig(allowed_source_actors={Actor.AGENT}),
    )
    ingestor = DurableTextualIngestor(
        store,
        journal_path=tmp_path / "journal.sqlite3",
        miner=miner,
        consolidator=DeterministicMemoryConsolidator(),
        index_writers=[index],
        role_actors={"user": Actor.AGENT, "assistant": Actor.AGENT},
    )
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        await ingestor.ingest(scope, source)
        raw = await ingestor.resolve_event(scope, event_ids(scope, source)[0])
        assert raw is not None and raw.authority == FactAuthority.AGENT_OUTPUT
        assert model.requests[0].input["messages"][0]["actor"] == Actor.AGENT
    finally:
        ingestor.close()
        await store.close()


async def test_mutated_policy_requires_a_new_profile_before_model_calls(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    ingestor.miner.config.allowed_source_actors.clear()
    try:
        with pytest.raises(WriteConflict):
            await ingestor.ingest(
                memory_scope("local-test", request().user_id), request()
            )
        assert not model.requests
    finally:
        ingestor.close()
        await store.close()


def test_extractor_and_miner_fingerprints_are_stable_across_hash_seeds() -> None:
    script = """
import json
from doppel_memory.intelligence import PersonalMemoryExtractorConfig, PersonalMemoryMinerConfig
actors = {'owner', 'agent', 'contact', 'system'}
print(json.dumps([PersonalMemoryExtractorConfig(allowed_source_actors=actors).fingerprint,
                  PersonalMemoryMinerConfig(allowed_source_actors=actors).fingerprint]))
"""
    values = [
        subprocess.check_output(
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).strip()
        for seed in (1, 2, 3)
    ]
    assert len(set(values)) == 1


async def test_assistant_claim_cannot_be_promoted_to_owner_fact(tmp_path: Path) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    model.bad_subject = True
    ingestor = host(tmp_path, store, model, index)
    source = request()
    scope = memory_scope("local-test", source.user_id)
    try:
        with pytest.raises(IngestionFailure) as error:
            await ingestor.ingest(scope, source)
        assert error.value.stage == "extraction"
        assert not (
            await store.scan(scope, filters=MemoryFilter(tags={"personal-memory"}))
        ).records
        assert (
            await ingestor.resolve_event(scope, event_ids(scope, source)[1]) is not None
        )
    finally:
        ingestor.close()
        await store.close()


@pytest.mark.parametrize("all_unsafe", [False, True])
async def test_quarantine_persists_rejection_partition_and_replays_without_model(
    tmp_path: Path,
    all_unsafe: bool,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    model.bad_subject = True
    model.bad_evidence = all_unsafe
    config = PersonalMemoryMinerConfig(
        allowed_source_actors={Actor.OWNER, Actor.AGENT},
        proposed_state=MemoryState.CONFIRMED,
        evidence_error_policy="quarantine",
    )
    source = request()
    scope = memory_scope("local-test", source.user_id)
    ingestor = host(tmp_path, store, model, index, config=config)
    try:
        completion = await ingestor.ingest(scope, source)
        assert completion.completed and completion.raw_event_count == 2
        assert completion.proposal_count == (0 if all_unsafe else 1)
        audit = ingestor.audit_report()
        counts = audit["chunks"][0]["proposal_diagnostics"]
        assert counts["valid_drafts"] == 2
        assert counts["evidence_rejected_drafts"] == (2 if all_unsafe else 1)
        assert counts["evidence_rejection_counts"] == (
            {"unknown_evidence": 2} if all_unsafe else {"subject_source_mismatch": 1}
        )
        derived = (
            await store.scan(scope, filters=MemoryFilter(tags={"personal-memory"}))
        ).records
        assert len(derived) == completion.proposal_count
        assert all(record.authority == FactAuthority.HUMAN_SELF for record in derived)
        for identity in event_ids(scope, source):
            assert await ingestor.resolve_event(scope, identity) is not None
    finally:
        ingestor.close()
    restarted_model = ScriptedModel()
    restarted = host(tmp_path, store, restarted_model, index, config=config)
    try:
        assert await restarted.ingest(scope, source) == completion
        assert restarted.audit_report() == audit
        assert not restarted_model.requests
    finally:
        restarted.close()
        await store.close()


async def test_invalid_model_copy_is_revalidated_without_text_disclosure(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(str(tmp_path / "store.sqlite3"))
    model, index = ScriptedModel(), MemoryIndex()
    ingestor = host(tmp_path, store, model, index)
    source = request()
    source.messages[0] = source.messages[0].model_copy(
        update={"role": "DO_NOT_EXPOSE_INVALID_VALUE"}
    )
    try:
        with pytest.raises(IngestionFailure) as error:
            await ingestor.ingest(memory_scope("local-test", source.user_id), source)
        assert error.value.stage == "input"
        assert "DO_NOT_EXPOSE" not in str(error.value)
        assert not model.requests
    finally:
        ingestor.close()
        await store.close()


async def test_postgresql_composition_identity_without_connecting(
    tmp_path: Path,
) -> None:
    from doppel_memory.postgres_store import PostgreSQLStore

    store = PostgreSQLStore(
        "postgresql://localhost:1/offline-unreachable", schema="pilot"
    )
    model, index = ScriptedModel(), MemoryIndex()
    miner = PersonalMemoryMiner(ReferencePersonalMemoryAnalyzer(model))
    args = {
        "journal_path": tmp_path / "journal.sqlite3",
        "miner": miner,
        "consolidator": DeterministicMemoryConsolidator(),
        "index_writers": [index],
        "role_actors": {"user": Actor.OWNER, "assistant": Actor.AGENT},
    }
    with pytest.raises(ValueError, match="store_identity"):
        DurableTextualIngestor(store, **args)
    ingestor = DurableTextualIngestor(
        store, store_identity="local-pilot-database/schema-pilot", **args
    )
    ingestor.close()
    assert not model.requests
    assert store._pool is None
    await store.close()

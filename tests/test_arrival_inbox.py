"""Synthetic late-arrival recovery; source dates are never rewritten."""

import sqlite3
from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    SQLiteStore,
    StoreHistoryReader,
)
from examples.arrival_inbox import ArrivalInbox, drain_once
from examples.checked_ingest import SourceEventConflictError
from examples.incremental_personal_memory import SQLiteManifestIndex
from examples.personal_memory_runtime import PersonalMemoryWorkflow

SCOPE = MemoryScope(user_id="owner", agent_id="arrival-test")


def message(identity, day=1, **updates):
    return ChatMessage.of(
        "owner",
        f"opaque {identity}",
        datetime(2026, 1, day, tzinfo=UTC),
        message_id=identity,
    ).model_copy(update=updates)


class Analyzer:
    name, version = "test.arrival-script", "1"

    def __init__(self):
        self.calls = []

    async def analyze(self, request):
        self.calls.append([m.identity_key for m in request.messages])
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content=m.text,
                    memory_type="preference",
                    topic_key="opaque.slot",
                    temporal_status="current",
                    revision_kind="correction"
                    if m.identity_key == "new"
                    else "assertion",
                    evidence_ids=[m.identity_key],
                )
                for m in request.messages
            ]
        )


def factory(path, store, analyzer):
    def create(batch):
        return PersonalMemoryWorkflow(
            path / "jobs",
            workflow_key=batch.identity,
            storage_identity=str(path / "memory.sqlite3"),
            store=store,
            scope=batch.scope,
            miner=PersonalMemoryMiner(
                analyzer, PersonalMemoryMinerConfig(owner_target_scope="conversation")
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index=SQLiteManifestIndex(path / "catalog.sqlite3"),
            history=batch.history(),
            history_identity=batch.identity,
        )

    return create


async def test_late_message_is_processed_after_restart_without_changing_source_time(
    tmp_path,
):
    inbox = ArrivalInbox(tmp_path / "arrivals.sqlite3")
    analyzer = Analyzer()
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await inbox.append(SCOPE, message("new", 3))
        assert (
            await drain_once(inbox, SCOPE, store, factory(tmp_path, store, analyzer))
        )["complete"]
        await inbox.append(SCOPE, message("old", 1))
        partial = await drain_once(
            inbox, SCOPE, store, factory(tmp_path, store, analyzer), max_steps=1
        )
        assert not partial["complete"]
    finally:
        await store.close()
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        reopened = ArrivalInbox(tmp_path / "arrivals.sqlite3")
        done = await drain_once(
            reopened, SCOPE, store, factory(tmp_path, store, analyzer)
        )
        assert done["complete"]
        assert analyzer.calls == [["new"], ["old"]]
        rows = (
            await store.scan(
                SCOPE, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        old_event = next(
            row
            for row in rows
            if row.extractor == "ingestor" and row.source_message_id == "old"
        )
        assert old_event.created_at == message("old", 1).at
        client = DoppelClient(store)
        hits = await client.query_personal_memory(
            "opaque", [SCOPE], now=datetime(2026, 1, 5, tzinfo=UTC)
        )
        assert [h.record.content for h in hits.hits] == ["opaque new"]
        assert {
            ref["evidence_id"] for ref in hits.hits[0].record.metadata["evidence"]
        } == {"old", "new"}
        assert (
            await drain_once(reopened, SCOPE, store, factory(tmp_path, store, analyzer))
        )["empty"]
    finally:
        await store.close()


async def test_pending_selection_does_not_expand_when_later_messages_arrive(tmp_path):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    await inbox.append(SCOPE, message("first", 3))
    selected = await inbox.reserve(SCOPE)
    await inbox.append(SCOPE, message("late", 1))
    reopened = ArrivalInbox(tmp_path / "inbox.sqlite3")
    assert await reopened.reserve(SCOPE) == selected
    await reopened.acknowledge(selected)
    next_batch = await reopened.reserve(SCOPE)
    assert [m.identity_key for m in next_batch.messages] == ["late"]
    assert next_batch.window.start < selected.window.start


async def test_duplicate_conflict_and_exact_scope(tmp_path):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    seq = await inbox.append(SCOPE, message("same"))
    assert await inbox.append(SCOPE, message("same", raw={"delivery": 2})) == seq
    with pytest.raises(SourceEventConflictError):
        await inbox.append(SCOPE, message("same", text="different"))
    other = SCOPE.model_copy(update={"user_id": "other"})
    await inbox.append(other, message("same", text="other-owner"))
    assert (await inbox.reserve(SCOPE)).messages[0].text == "opaque same"
    assert (await inbox.reserve(other)).messages[0].text == "other-owner"


async def test_snapshot_cursor_filters_and_detached_messages(tmp_path):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    for identity, day in [("later", 3), ("earlier", 1)]:
        await inbox.append(SCOPE, message(identity, day))
    batch = await inbox.reserve(SCOPE)
    batch.messages[0].text = "cannot-mutate-snapshot"
    reader = batch.history()
    first = await reader.read(limit=1)
    assert first.messages[0].identity_key == "earlier"
    first.messages[0].text = "cannot-mutate-reader"
    assert (await reader.read(limit=1)).messages[0].text == "opaque earlier"
    assert (await reader.read(cursor=first.next_cursor, limit=1)).messages[
        0
    ].identity_key == "later"
    with pytest.raises(ValueError, match="different selection"):
        await reader.read(cursor=first.next_cursor, actors={"contact"})
    assert (await reader.read(actors={"agent"})).messages == []


async def test_ack_failure_replays_completed_workflow_without_new_analysis(
    tmp_path, monkeypatch
):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    await inbox.append(SCOPE, message("new", 3))
    analyzer = Analyzer()
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:

        async def fail(batch):
            raise OSError("synthetic ack failure")

        monkeypatch.setattr(inbox, "acknowledge", fail)
        with pytest.raises(OSError):
            await drain_once(inbox, SCOPE, store, factory(tmp_path, store, analyzer))
        recovered = ArrivalInbox(tmp_path / "inbox.sqlite3")
        assert (
            await drain_once(
                recovered, SCOPE, store, factory(tmp_path, store, analyzer)
            )
        )["complete"]
        assert analyzer.calls == [["new"]]
    finally:
        await store.close()


async def test_equal_timestamp_batches_do_not_share_a_source_time_cursor(tmp_path):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    for identity in ("a", "b", "c"):
        await inbox.append(SCOPE, message(identity))
    ids = []
    for _ in range(3):
        batch = await inbox.reserve(SCOPE, max_messages=1)
        ids.extend(m.identity_key for m in batch.messages)
        await inbox.acknowledge(batch)
    assert ids == ["a", "b", "c"]
    assert await inbox.reserve(SCOPE) is None


def test_demo_restarts_and_late_input_is_not_dropped(tmp_path):
    import json
    import subprocess
    import sys

    command = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "examples.late_arrival",
        "--directory",
        str(tmp_path),
    ]
    first = json.loads(
        subprocess.check_output([*command, "--stage", "current"], encoding="utf-8")
    )
    assert first["progress"]["complete"]
    partial = json.loads(
        subprocess.check_output(
            [*command, "--stage", "late", "--steps", "1"], encoding="utf-8"
        )
    )
    assert not partial["progress"]["complete"]
    final = json.loads(
        subprocess.check_output([*command, "--stage", "late"], encoding="utf-8")
    )
    assert final["progress"]["complete"]
    assert final["current_claims"] == ["更正一下，我现在喜欢深色主题。"]
    assert set(final["evidence_ids"]) == {"theme-1", "theme-2"}
    replay = json.loads(
        subprocess.check_output([*command, "--stage", "late"], encoding="utf-8")
    )
    assert replay["progress"]["empty"]


async def test_source_write_failure_does_not_ack_arrival(tmp_path):
    class FailingStore(SQLiteStore):
        async def write_event(self, *args, **kwargs):
            raise OSError("synthetic source store outage")

    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    await inbox.append(SCOPE, message("new", 3))
    before = await inbox.reserve(SCOPE)
    analyzer = Analyzer()
    store = FailingStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        with pytest.raises(OSError):
            await drain_once(inbox, SCOPE, store, factory(tmp_path, store, analyzer))
        assert analyzer.calls == []
    finally:
        await store.close()
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        assert await inbox.reserve(SCOPE) == before
        assert (
            await drain_once(inbox, SCOPE, store, factory(tmp_path, store, analyzer))
        )["complete"]
        assert analyzer.calls == [["new"]]
    finally:
        await store.close()


@pytest.mark.parametrize("mismatch", ["store_reader", "identity", "payload"])
async def test_actual_history_must_match_reserved_snapshot_before_source_writes(
    tmp_path, mismatch
):
    inbox = ArrivalInbox(tmp_path / "inbox.sqlite3")
    await inbox.append(SCOPE, message("new", 3))
    analyzer = Analyzer()
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    create = factory(tmp_path, store, analyzer)

    def wrong_factory(batch):
        workflow = create(batch)
        if mismatch == "store_reader":
            workflow.history = StoreHistoryReader(store, SCOPE)
        else:
            altered = batch.model_copy(
                update={
                    "identity": "other-batch"
                    if mismatch == "identity"
                    else batch.identity,
                    "payloads": batch.payloads if mismatch == "identity" else (),
                }
            )
            workflow.history = altered.history()
        return workflow

    try:
        with pytest.raises(ValueError, match="snapshot"):
            await drain_once(inbox, SCOPE, store, wrong_factory)
        assert analyzer.calls == []
        assert (await store.scan(SCOPE, limit=100)).records == []
        assert await inbox.reserve(SCOPE) is not None
    finally:
        await store.close()


@pytest.mark.parametrize(
    "operation", ["reserve_new", "reserve_pending", "ack", "duplicate"]
)
async def test_queue_checks_stored_source_integrity_before_trusting_it(
    tmp_path, operation
):
    path = tmp_path / "inbox.sqlite3"
    inbox = ArrivalInbox(path)
    await inbox.append(SCOPE, message("new", 3))
    batch = (
        await inbox.reserve(SCOPE) if operation in {"reserve_pending", "ack"} else None
    )
    with sqlite3.connect(path) as connection:
        if operation == "reserve_new":
            connection.execute(
                "UPDATE arrival_events SET payload=?",
                (message("new", 3, text="changed").model_dump_json(),),
            )
        else:
            connection.execute("UPDATE arrival_events SET fingerprint='broken'")
    with pytest.raises(ValueError, match="integrity"):
        if operation == "ack":
            await inbox.acknowledge(batch)
        elif operation == "duplicate":
            await inbox.append(SCOPE, message("new", 3))
        else:
            await inbox.reserve(SCOPE)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM arrival_batches WHERE complete=1"
            ).fetchone()[0]
            == 0
        )

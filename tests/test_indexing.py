"""Backend-neutral derived-index lifecycle and reconciliation contracts."""

from datetime import UTC, datetime, timedelta

import pytest

from doppel_memory import InMemoryStore, MemoryRecord, MemoryScope, MemoryState
from doppel_memory.indexing import (
    IndexEntry,
    IndexEntryPage,
    IndexMaintainer,
    IndexMaintenanceCheckpoint,
    IndexMaintenancePhase,
    IndexOperationResult,
    IndexOperationStatus,
    IndexWriter,
    memory_index_fingerprint,
)

SCOPE = MemoryScope(user_id="index-user", agent_id="bot")
OTHER_SCOPE = MemoryScope(user_id="other-index-user", agent_id="bot")


class FakeIndexWriter:
    identity = "fake:test-v1"

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], IndexEntry] = {}
        self.fail_on: set[str] = set()

    async def inspect(self, scope: MemoryScope, memory_id: str) -> IndexEntry | None:
        return self.entries.get((scope.scope_key, memory_id))

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult:
        if record.memory_id in self.fail_on:
            raise RuntimeError("synthetic index outage")
        key = (record.scope.scope_key, record.memory_id)
        fingerprint = memory_index_fingerprint(record)
        current = self.entries.get(key)
        status = (
            IndexOperationStatus.SKIPPED
            if current is not None and current.fingerprint == fingerprint
            else IndexOperationStatus.INDEXED
        )
        self.entries[key] = IndexEntry(
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=fingerprint,
            source_version=record.version,
        )
        return IndexOperationResult(
            index_identity=self.identity,
            status=status,
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=fingerprint,
            source_version=record.version,
        )

    async def delete(self, scope: MemoryScope, memory_id: str) -> IndexOperationResult:
        if memory_id in self.fail_on:
            raise RuntimeError("synthetic index outage")
        removed = self.entries.pop((scope.scope_key, memory_id), None)
        return IndexOperationResult(
            index_identity=self.identity,
            status=(
                IndexOperationStatus.DELETED
                if removed is not None
                else IndexOperationStatus.MISSING
            ),
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
        entries = sorted(
            (
                entry
                for (scope_key, _), entry in self.entries.items()
                if scope_key == scope.scope_key and entry.memory_id > cursor
            ),
            key=lambda entry: entry.memory_id,
        )
        selected = entries[:limit]
        return IndexEntryPage(
            entries=selected,
            next_cursor=selected[-1].memory_id if selected else cursor,
            has_more=len(entries) > limit,
        )


def _record(memory_id: str, offset: int = 0) -> MemoryRecord:
    at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=offset)
    return MemoryRecord(
        memory_id=memory_id,
        scope=SCOPE,
        content=f"memory {memory_id}",
        created_at=at,
        updated_at=at,
    )


def test_memory_index_fingerprint_is_canonical_and_lifecycle_sensitive() -> None:
    first = _record("fingerprint").model_copy(
        update={"metadata": {"outer": {"b": 2, "a": 1}}}
    )
    reordered = _record("fingerprint").model_copy(
        update={"metadata": {"outer": {"a": 1, "b": 2}}}
    )
    transitioned = first.model_copy(update={"state": MemoryState.EXPIRED, "version": 2})

    assert memory_index_fingerprint(first) == memory_index_fingerprint(reordered)
    assert memory_index_fingerprint(first) != memory_index_fingerprint(transitioned)


async def test_reconciler_repairs_stale_missing_inactive_and_orphan_entries() -> None:
    store = InMemoryStore()
    writer = FakeIndexWriter()
    assert isinstance(writer, IndexWriter)
    for offset, memory_id in enumerate(("a", "b", "c")):
        assert (await store.put(_record(memory_id, offset))).accepted
    await store.transition(SCOPE, "c", MemoryState.EXPIRED)

    writer.entries[(SCOPE.scope_key, "a")] = IndexEntry(
        memory_id="a",
        scope_key=SCOPE.scope_key,
        fingerprint="stale",
        source_version=1,
    )
    writer.entries[(SCOPE.scope_key, "orphan")] = IndexEntry(
        memory_id="orphan",
        scope_key=SCOPE.scope_key,
        fingerprint="orphan",
        source_version=1,
    )
    writer.entries[(OTHER_SCOPE.scope_key, "untouched")] = IndexEntry(
        memory_id="untouched",
        scope_key=OTHER_SCOPE.scope_key,
        fingerprint="other",
        source_version=1,
    )

    maintainer = IndexMaintainer(store, writer)
    checkpoint = None
    reports = []
    while not reports or not reports[-1].complete:
        report = await maintainer.reconcile(SCOPE, checkpoint=checkpoint, page_size=2)
        assert report.ok
        assert report.committable_checkpoint is not None
        reports.append(report)
        checkpoint = report.committable_checkpoint

    assert [report.phase for report in reports] == [
        IndexMaintenancePhase.RECORDS,
        IndexMaintenancePhase.RECORDS,
        IndexMaintenancePhase.ENTRIES,
        IndexMaintenancePhase.ENTRIES,
    ]
    assert checkpoint is not None
    assert checkpoint.phase == IndexMaintenancePhase.RECORDS
    assert checkpoint.cursor == ""
    assert checkpoint.cycle == 1
    assert set(writer.entries) == {
        (SCOPE.scope_key, "a"),
        (SCOPE.scope_key, "b"),
        (OTHER_SCOPE.scope_key, "untouched"),
    }
    assert writer.entries[(SCOPE.scope_key, "a")].fingerprint == (
        memory_index_fingerprint(await store.get(SCOPE, "a"))  # type: ignore[arg-type]
    )
    assert sum(report.indexed for report in reports) == 2
    assert sum(report.deleted for report in reports) == 1


async def test_failure_does_not_release_checkpoint_and_is_replayable() -> None:
    store = InMemoryStore()
    writer = FakeIndexWriter()
    assert (await store.put(_record("broken"))).accepted
    writer.fail_on.add("broken")
    maintainer = IndexMaintainer(store, writer)

    failed = await maintainer.reconcile(SCOPE)

    assert not failed.ok
    assert failed.committable_checkpoint is None
    assert failed.failures[0].memory_id == "broken"
    assert failed.failures[0].error_type == "RuntimeError"

    writer.fail_on.clear()
    retried = await maintainer.reconcile(SCOPE)
    assert retried.ok
    assert retried.indexed == 1
    assert retried.committable_checkpoint is not None


async def test_catalog_cursor_contract_violation_is_reported_without_progress() -> None:
    class StuckCatalog(FakeIndexWriter):
        async def scan_entries(
            self,
            scope: MemoryScope,
            *,
            cursor: str = "",
            limit: int = 100,
        ) -> IndexEntryPage:
            return IndexEntryPage(next_cursor=cursor, has_more=True)

    maintainer = IndexMaintainer(InMemoryStore(), StuckCatalog())
    report = await maintainer.reconcile(
        SCOPE,
        checkpoint=IndexMaintenanceCheckpoint(
            index_identity=StuckCatalog.identity,
            scope_key=SCOPE.scope_key,
            phase=IndexMaintenancePhase.ENTRIES,
        ),
    )

    assert not report.ok
    assert report.committable_checkpoint is None
    assert report.failures[0].stage == "scan_entries"
    assert "advance" in report.failures[0].message


def test_checkpoint_is_bound_to_index_scope_and_schema() -> None:
    maintainer = IndexMaintainer(InMemoryStore(), FakeIndexWriter())

    with pytest.raises(ValueError, match="another index"):
        maintainer._bind_checkpoint(
            SCOPE, IndexMaintenanceCheckpoint(index_identity="different")
        )
    with pytest.raises(ValueError, match="another scope"):
        maintainer._bind_checkpoint(
            SCOPE, IndexMaintenanceCheckpoint(scope_key=OTHER_SCOPE.scope_key)
        )
    with pytest.raises(ValueError, match="schema"):
        maintainer._bind_checkpoint(
            SCOPE, IndexMaintenanceCheckpoint.model_construct(schema_version=2)
        )


def test_report_rejects_inconsistent_counts() -> None:
    from doppel_memory.indexing import IndexMaintenanceReport

    with pytest.raises(ValueError, match="counts"):
        IndexMaintenanceReport(
            index_identity="fake",
            scope_key=SCOPE.scope_key,
            phase=IndexMaintenancePhase.RECORDS,
            scanned=1,
            indexed=0,
            skipped=0,
            deleted=0,
            missing=0,
            failed=0,
        )

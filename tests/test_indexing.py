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


@pytest.mark.parametrize("change", ["expire", "restore", "hard_delete", "correct"])
async def test_records_phase_reloads_after_page_snapshot(change) -> None:
    class ChangingStore(InMemoryStore):
        async def scan(self, scope, **kwargs):
            page = await super().scan(scope, **kwargs)
            if change == "hard_delete":
                await self.forget(scope, "a", hard=True)
            elif change == "correct":
                self._records["a"] = self._records["a"].model_copy(
                    update={"content": "corrected", "version": 2}
                )
            else:
                await self.transition(
                    scope,
                    "a",
                    (
                        MemoryState.EXPIRED
                        if change == "expire"
                        else MemoryState.CONFIRMED
                    ),
                )
            return page

    store, writer = ChangingStore(), FakeIndexWriter()
    await store.put(
        _record("a").model_copy(
            update={
                "state": MemoryState.EXPIRED
                if change == "restore"
                else MemoryState.CONFIRMED
            }
        )
    )
    report = await IndexMaintainer(store, writer).reconcile(SCOPE)
    assert report.ok
    latest = await store.get(SCOPE, "a")
    indexed = await writer.inspect(SCOPE, "a")
    if change in {"expire", "hard_delete"}:
        assert indexed is None
    else:
        assert latest and indexed
        assert indexed.fingerprint == memory_index_fingerprint(latest)


@pytest.mark.parametrize("phase", list(IndexMaintenancePhase))
@pytest.mark.parametrize("change", ["expire", "hard_delete", "correct"])
async def test_change_during_upsert_blocks_progress_then_replays(phase, change) -> None:
    store = InMemoryStore()
    await store.put(_record("a"))

    class RacingWriter(FakeIndexWriter):
        race = True

        async def upsert(self, record):
            result = await super().upsert(record)
            if self.race:
                self.race = False
                if change == "hard_delete":
                    await store.forget(SCOPE, "a", hard=True)
                elif change == "correct":
                    store._records["a"] = store._records["a"].model_copy(
                        update={"content": "corrected", "version": 2}
                    )
                else:
                    await store.transition(SCOPE, "a", MemoryState.EXPIRED)
            return result

    writer = RacingWriter()
    writer.entries[(SCOPE.scope_key, "a")] = IndexEntry(
        memory_id="a", scope_key=SCOPE.scope_key, fingerprint="stale", source_version=1
    )
    checkpoint = IndexMaintenanceCheckpoint(phase=phase)
    failed = await IndexMaintainer(store, writer).reconcile(
        SCOPE, checkpoint=checkpoint
    )
    assert not failed.ok
    assert failed.committable_checkpoint is None
    assert "changed during" in failed.failures[0].message
    # Recreate the runner and deserialize host-persisted progress, like a restart.
    retry = await IndexMaintainer(store, writer).reconcile(
        SCOPE,
        checkpoint=IndexMaintenanceCheckpoint.model_validate_json(
            checkpoint.model_dump_json()
        ),
    )
    assert retry.ok and retry.committable_checkpoint
    # A hard-deleted Store record disappears from the records scan. Its orphan
    # is found by the catalog phase, so finish the bounded cycle after restart.
    while not retry.complete:
        retry = await IndexMaintainer(store, writer).reconcile(
            SCOPE, checkpoint=retry.committable_checkpoint
        )
        assert retry.ok and retry.committable_checkpoint
    indexed = await writer.inspect(SCOPE, "a")
    if change != "correct":
        assert indexed is None
    else:
        assert indexed.fingerprint == memory_index_fingerprint(
            await store.get(SCOPE, "a")
        )


@pytest.mark.parametrize("phase", list(IndexMaintenancePhase))
async def test_restore_during_delete_blocks_progress_and_recovers(phase) -> None:
    store = InMemoryStore()
    await store.put(_record("a"))
    await store.transition(SCOPE, "a", MemoryState.EXPIRED)

    class RestoringWriter(FakeIndexWriter):
        async def delete(self, scope, memory_id):
            result = await super().delete(scope, memory_id)
            await store.transition(scope, memory_id, MemoryState.CONFIRMED)
            return result

    writer = RestoringWriter()
    writer.entries[(SCOPE.scope_key, "a")] = IndexEntry(
        memory_id="a", scope_key=SCOPE.scope_key, fingerprint="stale", source_version=1
    )
    checkpoint = IndexMaintenanceCheckpoint(phase=phase)
    report = await IndexMaintainer(store, writer).reconcile(
        SCOPE, checkpoint=checkpoint
    )
    assert not report.ok and report.committable_checkpoint is None
    # A deleted catalog entry cannot be rediscovered in the entries phase. The
    # next records cycle must rebuild it; don't promise an atomic full snapshot.
    retry = await IndexMaintainer(store, writer).reconcile(SCOPE)
    assert retry.ok
    assert await writer.inspect(SCOPE, "a") is not None


@pytest.mark.parametrize("fault", ["foreign", "duplicate", "blank_id", "reset_cursor"])
async def test_invalid_store_page_fails_before_index_mutation(fault) -> None:
    from doppel_memory.models import MemoryPage

    class InvalidStore(InMemoryStore):
        async def scan(self, scope, **kwargs):
            record = _record("a")
            if fault == "foreign":
                record = record.model_copy(update={"scope": OTHER_SCOPE})
            if fault == "blank_id":
                record = record.model_copy(update={"memory_id": ""})
            return MemoryPage(
                records=[record, record] if fault == "duplicate" else [record],
                has_more=fault == "reset_cursor",
                next_cursor="",
            )

    writer = FakeIndexWriter()
    report = await IndexMaintainer(InvalidStore(), writer).reconcile(
        SCOPE, checkpoint=IndexMaintenanceCheckpoint(cursor="previous")
    )
    assert not report.ok and report.committable_checkpoint is None
    assert report.failures[0].stage == "scan_records"
    assert writer.entries == {}


@pytest.mark.parametrize("phase", list(IndexMaintenancePhase))
@pytest.mark.parametrize("fault", ["scope", "id"])
async def test_invalid_store_get_is_rejected_before_mutation(phase, fault) -> None:
    class InvalidStore(InMemoryStore):
        async def get(self, scope, memory_id):
            return _record(memory_id).model_copy(
                update=(
                    {"scope": OTHER_SCOPE}
                    if fault == "scope"
                    else {"memory_id": "wrong"}
                )
            )

    store, writer = InvalidStore(), FakeIndexWriter()
    await store.put(_record("a"))
    writer.entries[(SCOPE.scope_key, "a")] = IndexEntry(
        memory_id="a", scope_key=SCOPE.scope_key, fingerprint="stale", source_version=1
    )
    before = dict(writer.entries)
    report = await IndexMaintainer(store, writer).reconcile(
        SCOPE, checkpoint=IndexMaintenanceCheckpoint(phase=phase)
    )
    assert not report.ok and report.committable_checkpoint is None
    assert writer.entries == before


@pytest.mark.parametrize("fault", ["fingerprint", "source_version", "status"])
async def test_incorrect_upsert_acknowledgement_does_not_advance(fault) -> None:
    class BadReceiptWriter(FakeIndexWriter):
        async def upsert(self, record):
            result = await super().upsert(record)
            return result.model_copy(
                update={
                    fault: {
                        "fingerprint": "wrong",
                        "source_version": 999,
                        "status": IndexOperationStatus.MISSING,
                    }[fault]
                }
            )

    store = InMemoryStore()
    await store.put(_record("a"))
    report = await IndexMaintainer(store, BadReceiptWriter()).reconcile(SCOPE)
    assert not report.ok and report.committable_checkpoint is None


async def test_sqlite_restart_resumes_failed_page_and_lifecycle(tmp_path) -> None:
    from doppel_memory import SQLiteStore

    database = str(tmp_path / "memory.sqlite3")
    checkpoint_file = tmp_path / "checkpoint.json"
    catalog_file = tmp_path / "catalog.json"
    import json

    store, writer = SQLiteStore(database=database), FakeIndexWriter()
    initial = IndexMaintenanceCheckpoint()
    checkpoint_file.write_text(initial.model_dump_json(), encoding="utf-8")
    try:
        await store.put(_record("a"))
        await store.put(_record("b", 1))
        writer.fail_on.add("b")
        report = await IndexMaintainer(store, writer).reconcile(SCOPE)
        assert not report.ok and report.indexed == 1
        assert report.committable_checkpoint is None
        # The host keeps its old checkpoint. Successful side effects survive.
        catalog_file.write_text(
            json.dumps([entry.model_dump() for entry in writer.entries.values()]),
            encoding="utf-8",
        )
    finally:
        await store.close()

    reopened, recovered = SQLiteStore(database=database), FakeIndexWriter()
    recovered.entries = {
        (entry.scope_key, entry.memory_id): entry
        for entry in [
            IndexEntry.model_validate(item)
            for item in json.loads(catalog_file.read_text(encoding="utf-8"))
        ]
    }
    checkpoint = IndexMaintenanceCheckpoint.model_validate_json(
        checkpoint_file.read_text(encoding="utf-8")
    )
    try:
        for state in [
            None,
            MemoryState.EXPIRED,
            MemoryState.CONFIRMED,
            MemoryState.SUPERSEDED,
        ]:
            if state is not None:
                await reopened.transition(SCOPE, "a", state)
            while True:
                result = await IndexMaintainer(reopened, recovered).reconcile(
                    SCOPE, checkpoint=checkpoint, page_size=1
                )
                assert result.ok and result.committable_checkpoint
                checkpoint = result.committable_checkpoint
                checkpoint_file.write_text(
                    checkpoint.model_dump_json(), encoding="utf-8"
                )
                if result.complete:
                    break
            entry = await recovered.inspect(SCOPE, "a")
            if state in {MemoryState.EXPIRED, MemoryState.SUPERSEDED}:
                assert entry is None
            else:
                assert entry and entry.fingerprint == memory_index_fingerprint(
                    await reopened.get(SCOPE, "a")
                )
            assert await recovered.inspect(SCOPE, "b") is not None
    finally:
        await reopened.close()


async def test_incorrect_delete_acknowledgement_does_not_advance() -> None:
    class BadReceiptWriter(FakeIndexWriter):
        async def delete(self, scope, memory_id):
            result = await super().delete(scope, memory_id)
            return result.model_copy(update={"status": IndexOperationStatus.SKIPPED})

    store = InMemoryStore()
    await store.put(_record("a").model_copy(update={"state": MemoryState.EXPIRED}))
    report = await IndexMaintainer(store, BadReceiptWriter()).reconcile(SCOPE)
    assert not report.ok and report.committable_checkpoint is None

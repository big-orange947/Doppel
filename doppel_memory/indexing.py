"""Lifecycle maintenance for derived semantic indexes.

Core ``MemoryStore`` records remain authoritative.  This module defines the small
write/catalog surface a derived index must expose and a resumable reconciler that
repairs missing, stale, inactive, and orphaned index entries one exact scope at a
time.  Retrieval remains a separate concern described by ``SemanticIndex``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
)
from doppel_memory.store import MemoryStore

INDEX_MAINTENANCE_SCHEMA_VERSION = 1


def memory_index_fingerprint(record: MemoryRecord) -> str:
    """Return a stable digest of every authoritative field visible to an index."""

    payload = json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class IndexOperationStatus(StrEnum):
    """Outcome of one idempotent derived-index mutation."""

    INDEXED = "indexed"
    SKIPPED = "skipped"
    DELETED = "deleted"
    MISSING = "missing"


class IndexEntry(BaseModel):
    """Catalog metadata for one derived representation of a core record."""

    memory_id: str
    scope_key: str
    fingerprint: str
    source_version: int = Field(ge=1)


class IndexEntryPage(BaseModel):
    entries: list[IndexEntry] = Field(default_factory=list)
    next_cursor: str = ""
    has_more: bool = False


class IndexOperationResult(BaseModel):
    index_identity: str
    status: IndexOperationStatus
    memory_id: str
    scope_key: str
    fingerprint: str = ""
    source_version: int | None = Field(default=None, ge=1)


@runtime_checkable
class IndexWriter(Protocol):
    """Idempotent mutation and exact-scope catalog contract for a derived index."""

    @property
    def identity(self) -> str: ...

    async def inspect(
        self, scope: MemoryScope, memory_id: str
    ) -> IndexEntry | None: ...

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult: ...

    async def delete(
        self, scope: MemoryScope, memory_id: str
    ) -> IndexOperationResult: ...

    async def scan_entries(
        self,
        scope: MemoryScope,
        *,
        cursor: str = "",
        limit: int = 100,
    ) -> IndexEntryPage: ...


class IndexMaintenancePhase(StrEnum):
    RECORDS = "records"
    ENTRIES = "entries"


class IndexMaintenanceCheckpoint(BaseModel):
    """Host-persisted progress for one index and one exact scope."""

    schema_version: int = INDEX_MAINTENANCE_SCHEMA_VERSION
    index_identity: str = ""
    scope_key: str = ""
    phase: IndexMaintenancePhase = IndexMaintenancePhase.RECORDS
    cursor: str = ""
    cycle: int = Field(default=0, ge=0)


class IndexMaintenanceFailure(BaseModel):
    memory_id: str = ""
    stage: str
    error_type: str
    message: str


class IndexMaintenanceReport(BaseModel):
    """Result of one bounded reconciliation page."""

    schema_version: int = INDEX_MAINTENANCE_SCHEMA_VERSION
    index_identity: str
    scope_key: str
    phase: IndexMaintenancePhase
    scanned: int = Field(ge=0)
    indexed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    deleted: int = Field(ge=0)
    missing: int = Field(ge=0)
    failed: int = Field(ge=0)
    complete: bool = False
    committable_checkpoint: IndexMaintenanceCheckpoint | None = None
    failures: list[IndexMaintenanceFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_counts(self) -> IndexMaintenanceReport:
        completed = self.indexed + self.skipped + self.deleted + self.missing
        if completed + self.failed != self.scanned:
            raise ValueError("index maintenance counts must equal scanned")
        if self.failed != len(self.failures):
            raise ValueError("index maintenance failures must match failed count")
        if self.failed and self.committable_checkpoint is not None:
            raise ValueError("failed index maintenance cannot advance its checkpoint")
        return self

    @property
    def ok(self) -> bool:
        return self.failed == 0


class IndexMaintainer:
    """Reconcile one derived index against an authoritative ``MemoryStore``.

    The records phase indexes active records and removes inactive ones.  The entries
    phase walks the index catalog to remove hard-deleted orphans and repair anything
    that changed after the records phase.  A page with failures never releases a new
    checkpoint; successful mutations are safe to replay because ``IndexWriter`` is
    idempotent.
    """

    def __init__(self, store: MemoryStore, writer: IndexWriter) -> None:
        identity = str(getattr(writer, "identity", "") or "").strip()
        if not identity:
            raise ValueError("index writer identity is required")
        self._store = store
        self._writer = writer
        self._identity = identity

    async def reconcile(
        self,
        scope: MemoryScope,
        *,
        checkpoint: IndexMaintenanceCheckpoint | None = None,
        page_size: int = 100,
    ) -> IndexMaintenanceReport:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        bound = self._bind_checkpoint(scope, checkpoint)
        if bound.phase == IndexMaintenancePhase.RECORDS:
            return await self._reconcile_records(scope, bound, page_size)
        return await self._reconcile_entries(scope, bound, page_size)

    def _bind_checkpoint(
        self,
        scope: MemoryScope,
        checkpoint: IndexMaintenanceCheckpoint | None,
    ) -> IndexMaintenanceCheckpoint:
        value = checkpoint or IndexMaintenanceCheckpoint()
        if value.schema_version != INDEX_MAINTENANCE_SCHEMA_VERSION:
            raise ValueError(
                "index maintenance checkpoint schema does not match; migrate or reset"
            )
        if value.index_identity and value.index_identity != self._identity:
            raise ValueError("index maintenance checkpoint belongs to another index")
        if value.scope_key and value.scope_key != scope.scope_key:
            raise ValueError("index maintenance checkpoint belongs to another scope")
        return value.model_copy(
            update={
                "index_identity": self._identity,
                "scope_key": scope.scope_key,
            }
        )

    async def _reconcile_records(
        self,
        scope: MemoryScope,
        checkpoint: IndexMaintenanceCheckpoint,
        page_size: int,
    ) -> IndexMaintenanceReport:
        try:
            page = await self._store.scan(
                scope,
                filters=MemoryFilter(include_inactive=True),
                cursor=checkpoint.cursor,
                limit=page_size,
            )
            if len(page.records) > page_size:
                raise ValueError("Store scan returned more records than requested")
            if page.has_more and (
                not page.next_cursor or page.next_cursor == checkpoint.cursor
            ):
                raise ValueError("Store scan did not advance a non-final cursor")
            identities = []
            for record in page.records:
                self._validate_record(record, scope, record.memory_id)
                identities.append(record.memory_id)
            if len(identities) != len(set(identities)):
                raise ValueError("Store scan returned duplicate records")
        except Exception as exc:  # noqa: BLE001 - maintenance is a report boundary
            return self._report(
                scope,
                IndexMaintenancePhase.RECORDS,
                [],
                [_maintenance_failure("", "scan_records", exc)],
                complete=False,
                checkpoint=None,
            )
        operations = []
        failures: list[IndexMaintenanceFailure] = []
        for record in page.records:
            try:
                operation = await self._reconcile_record(scope, record.memory_id)
                operations.append(operation)
            except Exception as exc:  # noqa: BLE001 - maintenance is a report boundary
                failures.append(_maintenance_failure(record.memory_id, "record", exc))

        next_checkpoint = None
        complete = False
        if not failures:
            if page.has_more:
                next_checkpoint = checkpoint.model_copy(
                    update={"cursor": page.next_cursor}
                )
            else:
                next_checkpoint = checkpoint.model_copy(
                    update={
                        "phase": IndexMaintenancePhase.ENTRIES,
                        "cursor": "",
                    }
                )
        return self._report(
            scope,
            IndexMaintenancePhase.RECORDS,
            operations,
            failures,
            complete=complete,
            checkpoint=next_checkpoint,
        )

    async def _reconcile_entries(
        self,
        scope: MemoryScope,
        checkpoint: IndexMaintenanceCheckpoint,
        page_size: int,
    ) -> IndexMaintenanceReport:
        try:
            page = await self._writer.scan_entries(
                scope, cursor=checkpoint.cursor, limit=page_size
            )
            if len(page.entries) > page_size:
                raise ValueError("index catalog returned more entries than requested")
            if page.has_more and (
                not page.next_cursor or page.next_cursor == checkpoint.cursor
            ):
                raise ValueError("index catalog did not advance a non-final cursor")
            if any(
                entry.scope_key != scope.scope_key or not entry.memory_id
                for entry in page.entries
            ):
                raise ValueError("index catalog returned invalid exact-scope identity")
            identities = [(entry.scope_key, entry.memory_id) for entry in page.entries]
            if len(identities) != len(set(identities)):
                raise ValueError("index catalog returned duplicate entries")
        except Exception as exc:  # noqa: BLE001 - maintenance is a report boundary
            return self._report(
                scope,
                IndexMaintenancePhase.ENTRIES,
                [],
                [_maintenance_failure("", "scan_entries", exc)],
                complete=False,
                checkpoint=None,
            )
        operations: list[IndexOperationResult] = []
        failures: list[IndexMaintenanceFailure] = []
        for entry in page.entries:
            try:
                operation = await self._reconcile_record(
                    scope, entry.memory_id, entry=entry
                )
                operations.append(operation)
            except Exception as exc:  # noqa: BLE001 - maintenance is a report boundary
                failures.append(_maintenance_failure(entry.memory_id, "entry", exc))

        next_checkpoint = None
        complete = False
        if not failures:
            if page.has_more:
                next_checkpoint = checkpoint.model_copy(
                    update={"cursor": page.next_cursor}
                )
            else:
                complete = True
                next_checkpoint = checkpoint.model_copy(
                    update={
                        "phase": IndexMaintenancePhase.RECORDS,
                        "cursor": "",
                        "cycle": checkpoint.cycle + 1,
                    }
                )
        return self._report(
            scope,
            IndexMaintenancePhase.ENTRIES,
            operations,
            failures,
            complete=complete,
            checkpoint=next_checkpoint,
        )

    @staticmethod
    def _validate_record(
        record: MemoryRecord, scope: MemoryScope, memory_id: str
    ) -> None:
        if not memory_id or record.memory_id != memory_id:
            raise ValueError("Store returned a missing or different memory identity")
        if record.scope.scope_key != scope.scope_key:
            raise ValueError("Store returned a record outside exact scope")

    async def _reconcile_record(
        self, scope: MemoryScope, memory_id: str, *, entry: IndexEntry | None = None
    ) -> IndexOperationResult:
        # Page snapshots can already be stale while earlier writes are awaited.
        record = await self._store.get(scope, memory_id)
        if record is not None:
            self._validate_record(record, scope, memory_id)
            record = record.model_copy(deep=True)
        active = record is not None and record.state in ACTIVE_MEMORY_STATES
        fingerprint = memory_index_fingerprint(record) if record is not None else ""
        if not active or record is None:
            operation = await self._writer.delete(scope, memory_id)
        elif entry is not None and entry.fingerprint == fingerprint:
            operation = IndexOperationResult(
                index_identity=self._identity,
                status=IndexOperationStatus.SKIPPED,
                memory_id=memory_id,
                scope_key=scope.scope_key,
                fingerprint=fingerprint,
                source_version=record.version,
            )
        else:
            # Give adapters a copy: in-place mutation must not alter our baseline.
            operation = await self._writer.upsert(record.model_copy(deep=True))
        self._validate_operation(operation, scope, memory_id)
        if active and record is not None:
            if operation.status not in {
                IndexOperationStatus.INDEXED,
                IndexOperationStatus.SKIPPED,
            }:
                raise ValueError("active record requires an upsert acknowledgement")
            if (
                operation.fingerprint != fingerprint
                or operation.source_version != record.version
            ):
                raise ValueError("index acknowledgement does not match source snapshot")
        elif operation.status not in {
            IndexOperationStatus.DELETED,
            IndexOperationStatus.MISSING,
        }:
            raise ValueError(
                "inactive or absent record requires a delete acknowledgement"
            )

        # Detect transitions during remote writes without retrying inside a page.
        # There is still no distributed snapshot/lock; later changes need another
        # cycle, and retrieval must always revalidate the authoritative Store.
        latest = await self._store.get(scope, memory_id)
        if latest is not None:
            self._validate_record(latest, scope, memory_id)
        if active:
            if latest is None or memory_index_fingerprint(latest) != fingerprint:
                raise ValueError("source changed during index maintenance; replay page")
        elif latest is not None and latest.state in ACTIVE_MEMORY_STATES:
            raise ValueError("source became active during index deletion; replay page")
        return operation

    def _validate_operation(
        self,
        operation: IndexOperationResult,
        scope: MemoryScope,
        memory_id: str,
    ) -> None:
        if operation.index_identity != self._identity:
            raise ValueError("index writer returned a result for another index")
        if operation.scope_key != scope.scope_key:
            raise ValueError("index writer returned a result outside exact scope")
        if operation.memory_id != memory_id:
            raise ValueError("index writer returned a result for another memory")

    def _report(
        self,
        scope: MemoryScope,
        phase: IndexMaintenancePhase,
        operations: Sequence[IndexOperationResult],
        failures: list[IndexMaintenanceFailure],
        *,
        complete: bool,
        checkpoint: IndexMaintenanceCheckpoint | None,
    ) -> IndexMaintenanceReport:
        counts = {status: 0 for status in IndexOperationStatus}
        for operation in operations:
            counts[operation.status] += 1
        return IndexMaintenanceReport(
            index_identity=self._identity,
            scope_key=scope.scope_key,
            phase=phase,
            scanned=len(operations) + len(failures),
            indexed=counts[IndexOperationStatus.INDEXED],
            skipped=counts[IndexOperationStatus.SKIPPED],
            deleted=counts[IndexOperationStatus.DELETED],
            missing=counts[IndexOperationStatus.MISSING],
            failed=len(failures),
            complete=complete,
            committable_checkpoint=checkpoint if not failures else None,
            failures=failures,
        )


def _maintenance_failure(
    memory_id: str, stage: str, exc: Exception
) -> IndexMaintenanceFailure:
    return IndexMaintenanceFailure(
        memory_id=memory_id,
        stage=stage,
        error_type=type(exc).__name__,
        message=str(exc),
    )

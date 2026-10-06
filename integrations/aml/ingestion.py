"""Durable local ingestion composition, not an AML HTTP service or Search backend.

Owns host checkpoints around the production Miner, ProposalWriter, consolidation
and index-maintenance protocols. Providers/indexes are injected; importing this
module never loads a model, opens a network connection or reads credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from doppel_memory.batch import (
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskContext,
    GuardedHistoryReader,
    HistoryPage,
    HistoryWindow,
    StoreMemoryReader,
)
from doppel_memory.consolidation import (
    ConsolidationConfig,
    ConsolidationPlan,
    ConsolidationRunner,
    MemoryConsolidator,
)
from doppel_memory.indexing import IndexMaintainer, IndexWriter
from doppel_memory.intelligence import PersonalMemoryMiner
from doppel_memory.models import (
    Actor,
    ChatMessage,
    MemoryRecord,
    MemoryScope,
    WriteStatus,
)
from doppel_memory.processing import ProposalWriter
from doppel_memory.sqlite_store import SQLiteStore
from doppel_memory.store import MemoryStore
from integrations.aml.contract import (
    AddRequest,
    BoundaryError,
    WriteConflict,
    WriteNotReady,
    event_ids,
    payload_fingerprint,
    write_key,
)


class IngestionFailure(BoundaryError):
    """Redacted failure; a pending journal is retained for repair/replay."""

    def __init__(self, message: str, *, stage: str = "") -> None:
        super().__init__(message)
        self.stage = stage


class IngestionCompletion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    write_key: str
    scope_key: str
    payload_fingerprint: str
    raw_event_count: int
    proposal_count: int
    consolidation_action_count: int
    configured_index_count: int
    # This is stage completion, deliberately NOT an AML searchable WriteReceipt.
    completed: bool = True


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class _ChunkHistory:
    """Read a bounded arrival-ordered chunk, retaining explicit source timestamps."""

    def __init__(self, scope: MemoryScope, messages: Sequence[ChatMessage]) -> None:
        self.scope = scope
        self.messages = tuple(messages)

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage:
        selected = [
            message
            for message in self.messages
            if (actors is None or message.actor in actors)
            and (time_from is None or message.at >= time_from)
            and (time_to is None or message.at <= time_to)
        ]
        start = int(cursor or "0")
        page = selected[start : start + limit]
        end = start + len(page)
        return HistoryPage(
            messages=page, next_cursor=str(end), has_more=end < len(selected)
        )


class DurableTextualIngestor:
    """SQLite host journal, single-writer across cooperating local processes.

    Each stage commits separately. A separate SQLite coordinator transaction
    prevents interleaved scope-wide consolidation; OS locks release on process
    death, while journal commits survive. A competing instance fails before model
    calls rather than waiting synchronously. This is not a distributed lease or
    protection against unrelated code writing directly to the Store.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        journal_path: Path,
        miner: PersonalMemoryMiner,
        consolidator: MemoryConsolidator,
        index_writers: Sequence[IndexWriter],
        role_actors: Mapping[str, str],
        store_identity: str = "",
        consolidation_config: ConsolidationConfig | None = None,
        max_index_pages: int = 1_000,
    ) -> None:
        if str(journal_path) == ":memory:":
            raise ValueError("durable ingestion requires file-backed databases")
        if not store.capabilities.transactions or not store.capabilities.pagination:
            raise ValueError("ingestion requires transactional, paginated storage")
        store_path = (
            Path(store.database).resolve() if isinstance(store, SQLiteStore) else None
        )
        if isinstance(store, SQLiteStore):
            if store.database == ":memory:":
                raise ValueError("durable ingestion requires file-backed databases")
            store_identity = "sqlite:" + str(store_path)
        if not store_identity.strip():
            raise ValueError(
                "non-SQLite Store requires a trusted durable store_identity"
            )
        self.store_identity = store_identity
        if not index_writers:
            raise ValueError("configure at least one real index writer")
        if set(role_actors) != {"user", "assistant"} or not set(
            role_actors.values()
        ).issubset({Actor.OWNER, Actor.AGENT, Actor.SYSTEM}):
            raise ValueError("configure both transport-role actors explicitly")
        self._actors = dict(role_actors)
        if type(max_index_pages) is not int or max_index_pages < 1:
            raise ValueError("max_index_pages must be positive")
        self.store = store
        self.miner = miner
        self.consolidator = consolidator
        self.writers = tuple(index_writers)
        self.config = consolidation_config or ConsolidationConfig()
        self.max_index_pages = max_index_pages
        path = journal_path.resolve()
        coordinator_path = path.with_name(path.name + ".coordinator.sqlite3")
        if store_path in {path, coordinator_path}:
            raise ValueError("Store, journal and coordinator must be separate files")
        if len({writer.identity for writer in self.writers}) != len(self.writers):
            raise ValueError("index writer identities must be unique")
        profile = {
            "schema": 1,
            "store": self.store_identity,
            "miner": miner.checkpoint_key,
            "consolidator": [consolidator.name, consolidator.version],
            "consolidator_policy": self._consolidator_policy_fingerprint(),
            "consolidation_config": self.config.fingerprint,
            "indexes": [writer.identity for writer in self.writers],
            "raw_role_policy": self._actors,
        }
        self.profile_fingerprint = hashlib.sha256(_json(profile).encode()).hexdigest()
        self._bound_components = self._component_identity()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._journal = sqlite3.connect(path, isolation_level=None)
        self._journal.row_factory = sqlite3.Row
        self._journal.execute("PRAGMA journal_mode=WAL")
        self._journal.execute("PRAGMA synchronous=FULL")
        self._journal.executescript(
            """CREATE TABLE IF NOT EXISTS host_profile (id INTEGER PRIMARY KEY, fingerprint TEXT);
            CREATE TABLE IF NOT EXISTS writes (
                key TEXT PRIMARY KEY, payload TEXT NOT NULL, scope TEXT NOT NULL,
                events TEXT, proposals TEXT, consolidation TEXT, consolidation_done INTEGER DEFAULT 0,
                completion TEXT
            );
            CREATE TABLE IF NOT EXISTS sources (
                scope TEXT NOT NULL, event TEXT NOT NULL, memory TEXT NOT NULL,
                PRIMARY KEY(scope, event)
            );"""
        )
        self._coordinator = sqlite3.connect(coordinator_path, timeout=0)
        self._coordinator.execute("CREATE TABLE IF NOT EXISTS writer_lock (id INTEGER)")
        self._coordinator.commit()
        self._lock = asyncio.Lock()
        self._closed = False
        try:
            with self._exclusive():
                self._journal.execute(
                    "INSERT OR IGNORE INTO host_profile VALUES (1, ?)",
                    (self.profile_fingerprint,),
                )
                bound = self._journal.execute(
                    "SELECT fingerprint FROM host_profile WHERE id=1"
                ).fetchone()
                if bound[0] != self.profile_fingerprint:
                    raise WriteConflict("journal belongs to a different host profile")
        except BaseException:
            self._journal.close()
            self._coordinator.close()
            raise

    @contextmanager
    def _exclusive(self) -> Iterator[None]:
        try:
            self._coordinator.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            raise WriteNotReady("another local ingestion writer is active") from None
        try:
            yield
        finally:
            self._coordinator.rollback()

    def _save(self, key: str, field: str, value: object) -> None:
        if field not in {"events", "proposals", "consolidation", "completion"}:
            raise ValueError("unknown journal stage")
        self._journal.execute(
            f"UPDATE writes SET {field}=? WHERE key=?", (_json(value), key)
        )

    def _component_identity(self) -> tuple[object, ...]:
        return (
            self.store_identity,
            self.miner.checkpoint_key,
            self.consolidator.name,
            self.consolidator.version,
            self._consolidator_policy_fingerprint(),
            self.config.fingerprint,
            tuple(writer.identity for writer in self.writers),
            tuple(sorted(self._actors.items())),
        )

    def _consolidator_policy_fingerprint(self) -> str:
        return str(
            getattr(getattr(self.consolidator, "config", None), "fingerprint", "")
        )

    async def ingest(
        self, scope: MemoryScope, request: AddRequest
    ) -> IngestionCompletion:
        """No query, gold annotation, benchmark category or source-map input."""
        if self._closed:
            raise IngestionFailure("ingestor is closed")
        if self._component_identity() != self._bound_components:
            raise WriteConflict("host components changed after journal binding")
        try:
            snapshot = AddRequest.model_validate(request.model_dump(warnings=False))
        except ValidationError:
            raise IngestionFailure("invalid textual request", stage="input") from None
        if not scope.is_user_scope:
            raise IngestionFailure("textual ingestion requires an exact user scope")
        messages = self._messages(scope, snapshot)
        if len(messages) > self.miner.config.max_messages:
            raise IngestionFailure("chunk exceeds Miner bound; split before ingestion")
        if not {message.actor for message in messages}.issubset(
            self.miner.config.allowed_source_actors
        ):
            raise IngestionFailure("Miner policy would omit a historical source role")
        key = write_key(scope, snapshot)
        fingerprint = payload_fingerprint(snapshot)
        async with self._lock:
            with self._exclusive():
                pending = self._journal.execute(
                    "SELECT key FROM writes WHERE scope=? AND completion IS NULL AND key<>? LIMIT 1",
                    (scope.scope_key, key),
                ).fetchone()
                if pending is not None:
                    raise WriteNotReady(
                        "resume the pending scope write before a later chunk"
                    )
                self._journal.execute(
                    "INSERT OR IGNORE INTO writes(key,payload,scope) VALUES (?,?,?)",
                    (key, fingerprint, scope.scope_key),
                )
                row = self._journal.execute(
                    "SELECT * FROM writes WHERE key=?", (key,)
                ).fetchone()
                if row["payload"] != fingerprint or row["scope"] != scope.scope_key:
                    raise WriteConflict("request identity reused with changed payload")
                stage = "raw_events"
                try:
                    await self._events(scope, messages, key, row)
                    if row["completion"] is not None:
                        # Replays revalidate provenance and repair derived indexes.
                        stage = "indexes"
                        await self._indexes(scope)
                        return IngestionCompletion.model_validate_json(
                            row["completion"]
                        )
                    stage = "extraction"
                    proposals = await self._proposals(scope, messages, key, row)
                    stage = "proposal_writes"
                    written = await ProposalWriter(self.store).write_batch(
                        proposals.proposals, allowed_scopes=[scope]
                    )
                    if written.errors or any(
                        value.status
                        not in {
                            WriteStatus.CREATED,
                            WriteStatus.UPDATED,
                            WriteStatus.DUPLICATE,
                        }
                        for value in written.write_results
                    ):
                        raise IngestionFailure("proposal persistence did not complete")
                    if len(written.write_results) != len(proposals.proposals):
                        raise IngestionFailure(
                            "proposal persistence accounting mismatch"
                        )
                    for proposal, value in zip(
                        proposals.proposals, written.write_results, strict=True
                    ):
                        if (
                            value.record is None
                            or await self.store.get(scope, value.memory_id) is None
                        ):
                            raise IngestionFailure(
                                "derived record is missing from Store"
                            )
                        if (
                            value.record.scope.scope_key != scope.scope_key
                            or value.record.content != proposal.content
                            or value.record.idempotency_key != proposal.idempotency_key
                            or value.record.actor != proposal.actor
                            or value.record.authority != proposal.authority
                            or value.record.source_event_id != proposal.source_event_id
                        ):
                            raise IngestionFailure(
                                "derived record replay identity mismatch"
                            )
                    stage = "consolidation"
                    plan = await self._consolidate(scope, key, row)
                    stage = "indexes"
                    await self._indexes(scope)
                    completion = IngestionCompletion(
                        write_key=key,
                        scope_key=scope.scope_key,
                        payload_fingerprint=fingerprint,
                        raw_event_count=len(messages),
                        proposal_count=len(proposals.proposals),
                        consolidation_action_count=len(plan.actions),
                        configured_index_count=len(self.writers),
                    )
                    self._save(key, "completion", completion.model_dump(mode="json"))
                    return completion
                except Exception:  # noqa: BLE001 - redacted plugin boundary
                    # Never interpolate plugin exception text (may contain keys/text).
                    raise IngestionFailure(
                        "ingestion stage failed; journal retained", stage=stage
                    ) from None

    def _messages(self, scope: MemoryScope, request: AddRequest) -> list[ChatMessage]:
        messages = []
        for identity, turn_index, message in zip(
            event_ids(scope, request),
            range(len(request.messages)),
            request.messages,
            strict=True,
        ):
            if message.timestamp is None:
                raise IngestionFailure(
                    "source timestamp required; no wall-clock fallback"
                )
            try:
                at = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
                    milliseconds=message.timestamp
                )
            except OverflowError:
                raise IngestionFailure("source timestamp out of range") from None
            actor = self._actors[message.role]
            messages.append(
                ChatMessage(
                    actor=actor,
                    text=message.content,
                    at=at,
                    event_id=identity,
                    sender_id=(
                        scope.user_id
                        if actor == Actor.OWNER
                        else scope.agent_id
                        if actor == Actor.AGENT
                        else ""
                    ),
                    raw={
                        "source_text": message.content,
                        "transport_role": message.role,
                        "session_id": request.session_id,
                        "turn_index": turn_index,
                    },
                )
            )
        return messages

    async def _events(
        self,
        scope: MemoryScope,
        messages: list[ChatMessage],
        key: str,
        row: sqlite3.Row,
    ) -> None:
        stored_ids = json.loads(row["events"]) if row["events"] is not None else None
        if stored_ids is not None and len(stored_ids) != len(messages):
            raise IngestionFailure("raw event journal length mismatch")
        memory_ids = []
        for index, message in enumerate(messages):
            if stored_ids is None:
                result = await self.store.write_event(scope, message)
                if (
                    result.status
                    not in {
                        WriteStatus.CREATED,
                        WriteStatus.UPDATED,
                        WriteStatus.DUPLICATE,
                    }
                    or result.record is None
                ):
                    raise IngestionFailure("raw event persistence did not complete")
                memory_id = result.memory_id
            else:
                memory_id = stored_ids[index]
            record = await self.store.get(scope, memory_id)
            if record is None or (
                record.scope.scope_key != scope.scope_key
                or record.source_event_id != message.event_id
                or record.content != message.text
                or record.actor != message.actor
                or record.authority != message.fact_authority
                or record.created_at != message.at
                or record.metadata.get("raw") != message.raw
            ):
                raise IngestionFailure("raw event Store revalidation failed")
            self._journal.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?)",
                (scope.scope_key, message.event_id, memory_id),
            )
            mapped = self._journal.execute(
                "SELECT memory FROM sources WHERE scope=? AND event=?",
                (scope.scope_key, message.event_id),
            ).fetchone()
            if mapped[0] != memory_id:
                raise IngestionFailure("source-to-record mapping conflict")
            memory_ids.append(memory_id)
        self._save(key, "events", memory_ids)

    async def _proposals(
        self,
        scope: MemoryScope,
        messages: list[ChatMessage],
        key: str,
        row: sqlite3.Row,
    ) -> BatchProposalPlan:
        if row["proposals"] is not None:
            return BatchProposalPlan.model_validate_json(row["proposals"])
        context = BatchTaskContext(
            run_id=key,
            scope=scope,
            window=HistoryWindow(
                start=min(m.at for m in messages), end=max(m.at for m in messages)
            ),
            checkpoint=BatchCheckpoint(),
            history=GuardedHistoryReader(_ChunkHistory(scope, messages)),
            memories=StoreMemoryReader(self.store, [scope]),
        )
        plan = await self.miner.propose(context)
        if plan.next_checkpoint is None or plan.next_checkpoint.metadata.get(
            "truncated"
        ):
            raise IngestionFailure("Miner did not cover the complete chunk")
        if plan.next_checkpoint.metadata.get("eligible_messages") != len(messages):
            raise IngestionFailure("Miner omitted input messages")
        self._save(key, "proposals", plan.model_dump(mode="json"))
        return plan

    async def _consolidate(
        self, scope: MemoryScope, key: str, row: sqlite3.Row
    ) -> ConsolidationPlan:
        runner = ConsolidationRunner(self.store, self.config)
        if row["consolidation"] is None:
            plan = await runner.plan_once(self.consolidator, scope, run_id=key)
            self._save(key, "consolidation", plan.model_dump(mode="json"))
        else:
            plan = ConsolidationPlan.model_validate_json(row["consolidation"])
        if not row["consolidation_done"]:
            result = await runner.execute(plan)
            if result.committable_checkpoint is None:
                raise IngestionFailure("consolidation did not complete")
            self._journal.execute(
                "UPDATE writes SET consolidation_done=1 WHERE key=?", (key,)
            )
        return plan

    async def _indexes(self, scope: MemoryScope) -> None:
        for writer in self.writers:
            maintainer = IndexMaintainer(self.store, writer)
            checkpoint = None
            for _ in range(self.max_index_pages):
                report = await maintainer.reconcile(scope, checkpoint=checkpoint)
                if not report.ok or report.committable_checkpoint is None:
                    raise IngestionFailure("configured index did not complete")
                if report.complete:
                    break
                if report.committable_checkpoint == checkpoint:
                    raise IngestionFailure("index checkpoint did not advance")
                checkpoint = report.committable_checkpoint
            else:
                raise IngestionFailure("index reconciliation exceeded page bound")

    async def resolve_event(
        self, scope: MemoryScope, evidence_id: str
    ) -> MemoryRecord | None:
        if self._closed:
            raise IngestionFailure("ingestor is closed")
        row = self._journal.execute(
            "SELECT memory FROM sources WHERE scope=? AND event=?",
            (scope.scope_key, evidence_id),
        ).fetchone()
        if row is None:
            return None
        record = await self.store.get(scope, row[0])
        if record is None or record.source_event_id != evidence_id:
            raise IngestionFailure("evidence provenance Store revalidation failed")
        return record

    def close(self) -> None:
        """Close host journal only; callers own Store/provider/index lifetimes."""
        if self._closed:
            return
        if self._lock.locked():
            raise IngestionFailure("cannot close an active ingestor")
        self._journal.close()
        self._coordinator.close()
        self._closed = True

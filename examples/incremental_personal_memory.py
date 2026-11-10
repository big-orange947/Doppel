"""Offline workflow demo with a fixture analyzer and a catalog-only test index.

python -m examples.incremental_personal_memory --steps 1
python -m examples.incremental_personal_memory
No LLM, embeddings or graph; this demonstrates recovery, not extraction quality.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    HistoryWindow,
    IndexEntry,
    IndexEntryPage,
    IndexOperationResult,
    IndexOperationStatus,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    memory_index_fingerprint,
)
from examples.checked_ingest import ingest_checked
from examples.personal_memory_runtime import PersonalMemoryWorkflow


class SQLiteManifestIndex:
    """Durable lifecycle catalog only: no vectors, graph or semantic search."""

    identity = "example.sqlite-manifest.v1"

    def __init__(self, database: Path) -> None:
        self.database = database
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS entries (scope TEXT, id TEXT, payload TEXT, PRIMARY KEY(scope, id))"
            )

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult:
        entry = IndexEntry(
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=memory_index_fingerprint(record),
            source_version=record.version,
        )
        with sqlite3.connect(self.database) as connection:
            previous = connection.execute(
                "SELECT payload FROM entries WHERE scope=? AND id=?",
                (entry.scope_key, entry.memory_id),
            ).fetchone()
            connection.execute(
                "INSERT INTO entries VALUES(?,?,?) ON CONFLICT(scope,id) DO UPDATE SET payload=excluded.payload",
                (entry.scope_key, entry.memory_id, entry.model_dump_json()),
            )
        return IndexOperationResult(
            index_identity=self.identity,
            status=IndexOperationStatus.SKIPPED
            if previous and IndexEntry.model_validate_json(previous[0]) == entry
            else IndexOperationStatus.INDEXED,
            **entry.model_dump(),
        )

    async def delete(self, scope: MemoryScope, memory_id: str) -> IndexOperationResult:
        with sqlite3.connect(self.database) as connection:
            cursor = connection.execute(
                "DELETE FROM entries WHERE scope=? AND id=?",
                (scope.scope_key, memory_id),
            )
        return IndexOperationResult(
            index_identity=self.identity,
            status=IndexOperationStatus.DELETED
            if cursor.rowcount
            else IndexOperationStatus.MISSING,
            memory_id=memory_id,
            scope_key=scope.scope_key,
        )

    async def inspect(self, scope: MemoryScope, memory_id: str) -> IndexEntry | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT payload FROM entries WHERE scope=? AND id=?",
                (scope.scope_key, memory_id),
            ).fetchone()
        return IndexEntry.model_validate_json(row[0]) if row else None

    async def scan_entries(
        self, scope: MemoryScope, *, cursor: str = "", limit: int = 100
    ) -> IndexEntryPage:
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                "SELECT payload FROM entries WHERE scope=? AND id>? ORDER BY id LIMIT ?",
                (scope.scope_key, cursor, limit + 1),
            ).fetchall()
        entries = [IndexEntry.model_validate_json(row[0]) for row in rows[:limit]]
        return IndexEntryPage(
            entries=entries,
            next_cursor=entries[-1].memory_id if entries else cursor,
            has_more=len(rows) > limit,
        )


class FixtureAnalyzer:
    """Known synthetic outputs; never used as a natural-language extractor."""

    name, version = "example.fixture-analyzer", "1"

    async def analyze(self, request):
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content=message.text,
                    memory_type="preference",
                    topic_key="display.theme",
                    temporal_status="current",
                    revision_kind="correction"
                    if message.message_id == "theme-2"
                    else "assertion",
                    evidence_ids=[message.identity_key],
                )
                for message in request.messages
            ]
        )


async def run(directory: Path, steps: int) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    memory = DoppelClient(backend="sqlite", database=str(directory / "memory.sqlite3"))
    scope = MemoryScope(user_id="example-owner", agent_id="personal-agent")
    try:
        for identity, text, at in [
            ("theme-1", "我喜欢浅色主题。", "2026-11-01T09:00:00Z"),
            ("theme-2", "更正一下，我现在喜欢深色主题。", "2026-11-02T09:00:00Z"),
        ]:
            result = await ingest_checked(
                memory.store,
                scope,
                ChatMessage.of("owner", text, at, message_id=identity),
            )
            if result.record is None:
                raise RuntimeError("raw source write failed")
        index = SQLiteManifestIndex(directory / "catalog.sqlite3")
        workflow = PersonalMemoryWorkflow(
            directory / "jobs",
            workflow_key="offline-demo-v1",
            storage_identity=str((directory / "memory.sqlite3").resolve()),
            store=memory.store,
            scope=scope,
            miner=PersonalMemoryMiner(
                FixtureAnalyzer(),
                PersonalMemoryMinerConfig(owner_target_scope="conversation"),
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index=index,
            index_page_size=2,
        )
        window = HistoryWindow(
            start=datetime.fromisoformat("2026-11-01T00:00:00+00:00"),
            end=datetime.fromisoformat("2026-11-03T00:00:00+00:00"),
        )
        progress = []
        for _ in range(steps):
            result = await workflow.step(window)
            progress.append(result)
            if not result["ok"] or result["complete"]:
                break
        active = await memory.store.scan(
            scope, filters=MemoryFilter(tags={"personal-memory"}), limit=100
        )
        recalled = await memory.query_personal_memory(
            "主题", [scope], now=datetime.fromisoformat("2026-11-03T00:00:00+00:00")
        )
        return {
            "progress": progress,
            "active_memories": [record.content for record in active.records],
            "states": [record.state.value for record in active.records],
            "query_hits": [
                {
                    "content": hit.record.content,
                    "state": hit.record.state.value,
                    "authority": hit.record.authority.value,
                    "evidence_ids": [
                        ref["evidence_id"]
                        for ref in hit.record.metadata.get("evidence", [])
                    ],
                }
                for hit in recalled.hits
            ],
            "index_kind": "catalog-only-test-double",
            "paid_calls": 0,
        }
    finally:
        await memory.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path("data/examples/incremental-memory")
    )
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.steps <= 1000:
        parser.error("steps must be between 1 and 1000")
    result = asyncio.run(run(args.directory, args.steps))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["progress"][-1]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

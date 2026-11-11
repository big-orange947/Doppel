"""Offline arrival/backfill demo: current, then an older source, then recovery."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    MemoryScope,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PersonalMemoryQueryDraftV2,
)
from examples.arrival_inbox import ArrivalInbox, drain_once
from examples.incremental_personal_memory import FixtureAnalyzer, SQLiteManifestIndex
from examples.personal_memory import StructuredQueryPlanner
from examples.personal_memory_runtime import PersonalMemoryWorkflow


async def run(directory, stage, steps):
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "memory.sqlite3"
    client = DoppelClient(backend="sqlite", database=str(database))
    scope = MemoryScope(user_id="synthetic-owner", agent_id="arrival-demo")
    inbox = ArrivalInbox(directory / "inbox.sqlite3")
    try:
        message = ChatMessage.of(
            "owner",
            "更正一下，我现在喜欢深色主题。"
            if stage == "current"
            else "我喜欢浅色主题。",
            "2026-11-02T09:00:00Z" if stage == "current" else "2026-11-01T09:00:00Z",
            message_id="theme-2" if stage == "current" else "theme-1",
        )
        await inbox.append(scope, message)

        def create(batch):
            return PersonalMemoryWorkflow(
                directory / "jobs",
                workflow_key=batch.identity,
                storage_identity=str(database.resolve()),
                store=client.store,
                scope=scope,
                miner=PersonalMemoryMiner(
                    FixtureAnalyzer(),
                    PersonalMemoryMinerConfig(owner_target_scope="conversation"),
                ),
                consolidator=DeterministicMemoryConsolidator(),
                index=SQLiteManifestIndex(directory / "catalog.sqlite3"),
                history=batch.history(),
                history_identity=batch.identity,
            )

        progress = await drain_once(inbox, scope, client.store, create, max_steps=steps)
        result = await client.query_personal_memory(
            "主题",
            [scope],
            now=datetime(2026, 11, 3, tzinfo=UTC),
            planner=StructuredQueryPlanner(
                PersonalMemoryQueryDraftV2(search_text="主题", temporal_view="current")
            ),
        )
        return {
            "progress": progress,
            "current_claims": [hit.record.content for hit in result.hits],
            "evidence_ids": [
                ref["evidence_id"]
                for hit in result.hits
                for ref in hit.record.metadata.get("evidence", [])
            ],
            "llm_calls": 0,
            "analyzer": "fixture",
            "index": "catalog-only",
        }
    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path("data/examples/late-arrival")
    )
    parser.add_argument("--stage", choices=["current", "late"], required=True)
    parser.add_argument("--steps", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.steps <= 1000:
        parser.error("steps must be 1..1000")
    result = asyncio.run(run(args.directory, args.stage, args.steps))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["progress"].get("ok") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

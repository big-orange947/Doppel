"""Persistent, host-structured personal memory; no network or automatic extraction.

Run: python -m examples.personal_memory
The dedicated example database is retained. Repeating the command is idempotent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from doppel_memory import (
    Actor,
    ChatMessage,
    DoppelClient,
    FactAuthority,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryRequest,
    WriteStatus,
)


class StructuredQueryPlanner:
    """Adapt trusted UI/tool fields to the Planner protocol, without parsing text.

    A real host may instead select ReferencePersonalMemoryQueryPlannerV2 with its
    own model. Scope authorization still belongs to the host, never the planner.
    """

    name = "example.structured-query"
    version = "1"

    def __init__(self, draft: PersonalMemoryQueryDraftV2) -> None:
        self.draft = draft.model_copy(deep=True)

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraftV2:
        return self.draft.model_copy(deep=True)


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def run(database: Path) -> dict:
    database.parent.mkdir(parents=True, exist_ok=True)
    conversation = MemoryScope(
        user_id="example-owner",
        agent_id="personal-agent",
        platform="example",
        chat_type="private",
        chat_id="conversation-a",
    )
    other_conversation = conversation.model_copy(update={"chat_id": "conversation-b"})
    now = timestamp("2026-11-01T00:00:00+00:00")
    messages = [
        ChatMessage.of(
            Actor.OWNER,
            "我的工作地点在上海。",
            "2026-01-01T00:00:00+00:00",
            message_id="workplace-before",
            sender_id=conversation.user_id,
        ),
        ChatMessage.of(
            Actor.OWNER,
            "从六月一日起，我的工作地点改为杭州。",
            "2026-06-01T00:00:00+00:00",
            message_id="workplace-after",
            sender_id=conversation.user_id,
        ),
    ]
    memory = DoppelClient(backend="sqlite", database=str(database))
    try:
        # Raw evidence is durable before host-reviewed claims are imported.
        # put() is the trusted low-level API: it does not validate extraction or
        # infer/confirm these facts. Unreviewed model output must use proposals.
        for index, message in enumerate(messages):
            source = await memory.ingest(conversation, message)
            if source.record is None:
                raise RuntimeError("source write failed")
            historical = index == 0
            result = await memory.put(
                MemoryRecord(
                    scope=conversation,
                    kind=MemoryKind.FACT,
                    content="工作地点在上海" if historical else "工作地点在杭州",
                    actor=Actor.OWNER,
                    authority=FactAuthority.HUMAN_SELF,
                    state=MemoryState.CONFIRMED,
                    tags=["personal-memory", "profile"],
                    source_message_id=message.message_id,
                    extractor="example.host-reviewed-import.v1",
                    created_at=message.at,
                    updated_at=message.at,
                    metadata={
                        "personal_memory_type": "profile",
                        "subject": Actor.OWNER,
                        "subject_id": conversation.user_id,
                        "topic_key": "workplace",
                        "temporal_status": "historical" if historical else "current",
                        "valid_from": message.at.isoformat(),
                        "valid_to": "2026-05-31T23:59:59+00:00" if historical else None,
                        "evidence": [
                            {
                                "evidence_id": message.message_id,
                                "source_memory_id": source.record.memory_id,
                            }
                        ],
                    },
                ),
                idempotency_key=f"example:reviewed:{message.identity_key}:v1",
            )
            if result.status not in {WriteStatus.CREATED, WriteStatus.DUPLICATE}:
                raise RuntimeError("reviewed claim write failed")
    finally:
        await memory.close()

    # New client/connection reads the persisted data, without importing it again.
    reopened = DoppelClient(backend="sqlite", database=str(database))
    try:
        report = {"database": str(database.resolve()), "queries": {}}
        requests = [
            ("current", [conversation], "current", None),
            ("as_of", [conversation], "as_of", timestamp("2026-03-01T00:00:00+00:00")),
            ("conversation_b_only", [other_conversation], "current", None),
            # The host explicitly authorizes conversation A for this request.
            # Knowing a scope ID is not authorization; authenticate before here.
            (
                "host_authorized_cross_conversation",
                [other_conversation, conversation],
                "current",
                None,
            ),
        ]
        for label, scopes, view, as_of in requests:
            result = await reopened.query_personal_memory(
                "工作地点",
                scopes,
                now=now,
                planner=StructuredQueryPlanner(
                    PersonalMemoryQueryDraftV2(
                        search_text="工作地点",
                        temporal_view=view,
                        as_of=as_of,
                    )
                ),
            )
            hits = []
            for hit in result.hits:
                record = hit.record
                evidence = []
                for ref in record.metadata.get("evidence", []):
                    source = await reopened.store.get(
                        record.scope, ref["source_memory_id"]
                    )
                    if source is None or source.source_message_id != ref["evidence_id"]:
                        raise RuntimeError(
                            "persisted source reference cannot be resolved"
                        )
                    evidence.append(
                        {"message_id": ref["evidence_id"], "content": source.content}
                    )
                hits.append(
                    {
                        "memory_id": record.memory_id,
                        "content": record.content,
                        "actor": record.actor,
                        "authority": record.authority.value,
                        "temporal_status": record.metadata["temporal_status"],
                        "valid_from": record.metadata["valid_from"],
                        "valid_to": record.metadata["valid_to"],
                        "evidence": evidence,
                    }
                )
            report["queries"][label] = {"complete": result.complete, "hits": hits}
        return report
    finally:
        await reopened.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=Path("data/examples/personal-memory.sqlite3")
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.database)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

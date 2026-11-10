"""Multi-window synthetic replay: roles, correction, restart, index and queries."""

from datetime import UTC, datetime

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    HistoryWindow,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    SQLiteStore,
)
from examples.checked_ingest import ingest_checked
from examples.incremental_personal_memory import SQLiteManifestIndex
from examples.personal_memory_runtime import PersonalMemoryWorkflow


class ScriptedAnalyzer:
    name, version = "test.synthetic-timeline", "1"

    def __init__(self):
        self.batches = []

    async def analyze(self, request):
        self.batches.append([message.identity_key for message in request.messages])
        scripts = {
            "owner-1": ("owner", "opaque value-v1", "assertion"),
            "owner-2": ("owner", "opaque value-v2", "correction"),
            "peer-1": ("contact", "opaque peer preference", "assertion"),
        }
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    subject=scripts[message.identity_key][0],
                    content=scripts[message.identity_key][1],
                    revision_kind=scripts[message.identity_key][2],
                    memory_type="preference",
                    temporal_status="current",
                    topic_key="opaque.slot",
                    evidence_ids=[message.identity_key],
                )
                for message in request.messages
            ]
        )


async def test_two_windows_restart_correction_and_role_isolation(tmp_path):
    scope = MemoryScope(user_id="owner", agent_id="test")
    database = str(tmp_path / "memory.sqlite3")
    analyzer = ScriptedAnalyzer()

    def job(store):
        return PersonalMemoryWorkflow(
            tmp_path / "journal",
            workflow_key="synthetic",
            storage_identity=database,
            store=store,
            scope=scope,
            miner=PersonalMemoryMiner(
                analyzer, PersonalMemoryMinerConfig(owner_target_scope="conversation")
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index=SQLiteManifestIndex(tmp_path / "index.sqlite3"),
            index_page_size=2,
        )

    async def finish(workflow, window):
        for _ in range(100):
            result = await workflow.step(window)
            assert result["ok"], result
            if result["complete"]:
                return
        raise AssertionError("workflow did not finish")

    first_window = HistoryWindow(
        start=datetime(2026, 1, 1, tzinfo=UTC), end=datetime(2026, 1, 2, tzinfo=UTC)
    )
    second_window = HistoryWindow(
        start=datetime(2026, 1, 3, tzinfo=UTC), end=datetime(2026, 1, 4, tzinfo=UTC)
    )
    store = SQLiteStore(database=database)
    try:
        for identity, actor, sender, content in [
            ("owner-1", "owner", "owner", "opaque value-v1"),
            ("peer-1", "contact", "peer-a", "opaque peer preference"),
            ("agent-1", "agent", "bot", "opaque fabricated owner assertion"),
        ]:
            await ingest_checked(
                store,
                scope,
                ChatMessage.of(
                    actor,
                    content,
                    "2026-01-01T12:00:00Z",
                    message_id=identity,
                    sender_id=sender,
                ),
            )
        assert (await job(store).step(first_window))["next_stage"] == "consolidation"
    finally:
        await store.close()

    store = SQLiteStore(database=database)
    client = DoppelClient(store)
    try:
        await finish(job(store), first_window)
        for identity, actor, content in [
            ("owner-2", "owner", "opaque value-v2"),
            ("agent-2", "agent", "opaque another fabricated assertion"),
        ]:
            await ingest_checked(
                store,
                scope,
                ChatMessage.of(
                    actor,
                    content,
                    "2026-01-03T12:00:00Z",
                    message_id=identity,
                    sender_id="owner" if actor == "owner" else "bot",
                ),
            )
        other_scope = scope.model_copy(update={"user_id": "other-owner"})
        await ingest_checked(
            store,
            other_scope,
            ChatMessage.of(
                "owner", "opaque foreign", "2026-01-03T12:00:00Z", message_id="owner-2"
            ),
        )
        await finish(job(store), second_window)
        assert len(analyzer.batches) == 2
        assert set(analyzer.batches[0]) == {"owner-1", "peer-1"}
        assert analyzer.batches[1] == ["owner-2"]
        all_rows = (
            await store.scan(
                scope, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        personal = [row for row in all_rows if "personal-memory" in row.tags]
        assert all(row.actor != "agent" for row in personal)
        contact = [row for row in personal if row.actor == "contact"]
        assert len(contact) == 1 and contact[0].metadata["subject_id"] == "peer-a"
        index = SQLiteManifestIndex(tmp_path / "index.sqlite3")
        for row in all_rows:
            entry = await index.inspect(scope, row.memory_id)
            assert (entry is not None) == (
                row.state.value in {"candidate", "confirmed"}
            )
        hits = await client.query_personal_memory(
            "opaque", [scope], now=datetime(2026, 1, 4, tzinfo=UTC)
        )
        assert [hit.record.content for hit in hits.hits] == ["opaque value-v2"]
        assert hits.hits[0].record.state.value == "candidate"
        assert {
            ref["evidence_id"] for ref in hits.hits[0].record.metadata["evidence"]
        } == {"owner-1", "owner-2"}
        await finish(job(store), second_window)
        assert len(analyzer.batches) == 2
    finally:
        await client.close()

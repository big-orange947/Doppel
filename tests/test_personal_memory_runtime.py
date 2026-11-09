"""Crash/replay checks for the host recipe, with real SQLite and no external API."""

from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    HistoryWindow,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    SQLiteStore,
)
from examples.incremental_personal_memory import FixtureAnalyzer, SQLiteManifestIndex
from examples.personal_memory_runtime import PersonalMemoryWorkflow, WorkflowState

SCOPE = MemoryScope(user_id="runtime-owner", agent_id="test")
WINDOW = HistoryWindow(
    start=datetime(2026, 11, 1, tzinfo=UTC), end=datetime(2026, 11, 3, tzinfo=UTC)
)


class CountingAnalyzer(FixtureAnalyzer):
    calls = 0

    async def analyze(self, request):
        self.calls += 1
        return await super().analyze(request)


def workflow(tmp_path, store, analyzer=None, **kwargs):
    return PersonalMemoryWorkflow(
        tmp_path / "jobs",
        workflow_key="test",
        store=store,
        scope=SCOPE,
        miner=PersonalMemoryMiner(
            analyzer or FixtureAnalyzer(),
            PersonalMemoryMinerConfig(owner_target_scope="conversation"),
        ),
        consolidator=kwargs.pop("consolidator", DeterministicMemoryConsolidator()),
        index=kwargs.pop("index", SQLiteManifestIndex(tmp_path / "index.sqlite3")),
        index_page_size=1,
        **kwargs,
    )


async def ingest(store, *, second=True):
    for identity, content, at in [
        ("theme-1", "我喜欢浅色主题。", "2026-11-01T09:00:00Z"),
        ("theme-2", "更正一下，我现在喜欢深色主题。", "2026-11-02T09:00:00Z"),
    ][: 2 if second else 1]:
        assert (
            await store.write_event(
                SCOPE, ChatMessage.of("owner", content, at, message_id=identity)
            )
        ).record


async def finish(job, window=WINDOW):
    for _ in range(100):
        result = await job.step(window)
        assert result["ok"], result
        if result["complete"]:
            return
    pytest.fail("bounded workflow did not complete")


async def test_partial_proposal_writes_resume_saved_plan_without_reanalysis(tmp_path):
    class PartialStore(SQLiteStore):
        personal_writes = 0

        async def put(self, record, **kwargs):
            if "personal-memory" in record.tags:
                self.personal_writes += 1
                if self.personal_writes == 2:
                    raise RuntimeError("synthetic write outage")
            return await super().put(record, **kwargs)

    store = PartialStore(database=str(tmp_path / "memory.sqlite3"))
    analyzer = CountingAnalyzer()
    try:
        await ingest(store)
        job = workflow(tmp_path, store, analyzer)
        failed = await job.step(WINDOW)
        assert not failed["ok"]
        saved = WorkflowState.model_validate_json(job.path.read_text(encoding="utf-8"))
        assert saved.pending_batch and saved.batch_checkpoint is None
        assert analyzer.calls == 1
        assert (
            len(
                (
                    await store.scan(
                        SCOPE, filters=MemoryFilter(tags={"personal-memory"})
                    )
                ).records
            )
            == 1
        )
    finally:
        await store.close()

    reopened = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        job = workflow(tmp_path, reopened, analyzer)
        await finish(job)
        assert analyzer.calls == 1
        active = await reopened.scan(
            SCOPE, filters=MemoryFilter(tags={"personal-memory"})
        )
        assert [record.content for record in active.records] == [
            "更正一下，我现在喜欢深色主题。"
        ]
        assert all(record.state.value == "candidate" for record in active.records)
        all_rows = await reopened.scan(
            SCOPE, filters=MemoryFilter(include_inactive=True)
        )
        before = [(record.memory_id, record.version) for record in all_rows.records]
        await finish(job)
        assert before == [
            (record.memory_id, record.version)
            for record in (
                await reopened.scan(SCOPE, filters=MemoryFilter(include_inactive=True))
            ).records
        ]
    finally:
        await reopened.close()


async def test_saved_consolidation_plan_recovers_partial_transition(tmp_path):
    class PartialStore(SQLiteStore):
        transitions = 0

        async def transition(self, *args, **kwargs):
            self.transitions += 1
            if self.transitions == 2:
                from doppel_memory import MemoryStateConflictError

                raise MemoryStateConflictError("synthetic conflict")
            return await super().transition(*args, **kwargs)

    class CountingConsolidator(DeterministicMemoryConsolidator):
        calls = 0

        async def consolidate(self, input):
            self.calls += 1
            return await super().consolidate(input)

    consolidator = CountingConsolidator()
    store = PartialStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await ingest(store)
        job = workflow(tmp_path, store, consolidator=consolidator)
        assert (await job.step(WINDOW))["ok"]
        assert not (await job.step(WINDOW))["ok"]
        saved = WorkflowState.model_validate_json(job.path.read_text(encoding="utf-8"))
        assert saved.pending_consolidation and saved.consolidation_checkpoint is None
    finally:
        await store.close()
    reopened = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await finish(workflow(tmp_path, reopened, consolidator=consolidator))
        assert consolidator.calls == 1
        active = await reopened.scan(
            SCOPE, filters=MemoryFilter(tags={"personal-memory"})
        )
        assert len(active.records) == 1
    finally:
        await reopened.close()


async def test_index_outage_keeps_checkpoint_and_survives_restart(tmp_path):
    class BrokenIndex(SQLiteManifestIndex):
        async def upsert(self, record):
            raise RuntimeError("synthetic index outage")

    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await ingest(store)
        job = workflow(tmp_path, store, index=BrokenIndex(tmp_path / "index.sqlite3"))
        assert (await job.step(WINDOW))["ok"]
        assert (await job.step(WINDOW))["ok"]
        for _ in range(20):
            before = WorkflowState.model_validate_json(
                job.path.read_text(encoding="utf-8")
            )
            if not (await job.step(WINDOW))["ok"]:
                break
        else:
            pytest.fail("expected an active-record indexing failure")
        saved = WorkflowState.model_validate_json(job.path.read_text(encoding="utf-8"))
        assert saved.stage == "index"
        assert saved.index_checkpoint == before.index_checkpoint
    finally:
        await store.close()
    reopened = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await finish(workflow(tmp_path, reopened))
    finally:
        await reopened.close()


async def test_checkpoint_save_failure_replays_committed_consolidation(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await ingest(store)
        job = workflow(tmp_path, store)
        await job.step(WINDOW)
        original_save = job._save

        async def fail_final_save(state):
            if state.stage == "index":
                raise OSError("synthetic checkpoint disk failure")
            await original_save(state)

        job._save = fail_final_save
        with pytest.raises(OSError, match="checkpoint disk"):
            await job.step(WINDOW)
        saved = WorkflowState.model_validate_json(job.path.read_text(encoding="utf-8"))
        assert saved.stage == "consolidation" and saved.pending_consolidation
        before = (
            await store.scan(SCOPE, filters=MemoryFilter(include_inactive=True))
        ).records
    finally:
        await store.close()
    reopened = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await finish(workflow(tmp_path, reopened))
        after = (
            await reopened.scan(SCOPE, filters=MemoryFilter(include_inactive=True))
        ).records
        assert [(r.memory_id, r.version) for r in before] == [
            (r.memory_id, r.version) for r in after
        ]
    finally:
        await reopened.close()


async def test_bounded_miner_pages_finish_before_consolidation(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    analyzer = CountingAnalyzer()
    try:
        await ingest(store)
        job = workflow(tmp_path, store, analyzer)
        job.miner = PersonalMemoryMiner(
            analyzer,
            PersonalMemoryMinerConfig(
                owner_target_scope="conversation", page_size=1, max_messages=1
            ),
        )
        # Bind the new config before any journal is created.
        job = PersonalMemoryWorkflow(
            tmp_path / "bounded",
            workflow_key="bounded",
            store=store,
            scope=SCOPE,
            miner=job.miner,
            consolidator=DeterministicMemoryConsolidator(),
            index=SQLiteManifestIndex(tmp_path / "index.sqlite3"),
        )
        first = await job.step(WINDOW)
        assert first["next_stage"] == "batch"
        second = await job.step(WINDOW)
        assert second["next_stage"] == "consolidation"
        assert analyzer.calls == 2
        await finish(job)
    finally:
        await store.close()


async def test_window_change_and_corrupt_journal_fail_closed(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await ingest(store)
        job = workflow(tmp_path, store)
        await job.step(WINDOW)
        original = job.path.read_bytes()
        other_window = HistoryWindow(
            start=WINDOW.start, end=datetime(2026, 11, 4, tzinfo=UTC)
        )
        with pytest.raises(ValueError, match="pending window"):
            await job.step(other_window)
        assert job.path.read_bytes() == original
        job.path.write_text("{corrupt", encoding="utf-8")
        with pytest.raises(ValueError):
            await job.step(WINDOW)
        assert job.path.read_text(encoding="utf-8") == "{corrupt"
    finally:
        await store.close()


async def test_next_window_only_analyzes_new_messages(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    analyzer = CountingAnalyzer()
    try:
        await ingest(store)
        job = workflow(tmp_path, store, analyzer)
        await finish(job)
        assert analyzer.calls == 1
        await store.write_event(
            SCOPE,
            ChatMessage.of(
                "owner", "还有一条新偏好。", "2026-11-04T09:00:00Z", message_id="later"
            ),
        )
        later = HistoryWindow(
            start=datetime(2026, 11, 4, tzinfo=UTC),
            end=datetime(2026, 11, 5, tzinfo=UTC),
        )
        await finish(job, later)
        assert analyzer.calls == 2
        saved = WorkflowState.model_validate_json(job.path.read_text(encoding="utf-8"))
        assert saved.batch_checkpoint.metadata["eligible_messages"] == 1
    finally:
        await store.close()


@pytest.mark.parametrize("change", ["model", "index"])
async def test_configuration_drift_is_rejected_before_work(tmp_path, change):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        await ingest(store)
        job = workflow(tmp_path, store)
        await job.step(WINDOW)
        analyzer = CountingAnalyzer()
        index = SQLiteManifestIndex(tmp_path / "index.sqlite3")
        if change == "model":
            analyzer.version = "changed"
        else:
            index.identity = "changed"
        with pytest.raises(ValueError, match="configuration changed"):
            await workflow(tmp_path, store, analyzer, index=index).step(WINDOW)
        assert analyzer.calls == 0
    finally:
        await store.close()


def test_cli_resumes_across_two_processes_and_returns_attributed_evidence(tmp_path):
    import json
    import subprocess
    import sys

    command = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "examples.incremental_personal_memory",
        "--directory",
        str(tmp_path),
    ]
    first = json.loads(
        subprocess.check_output([*command, "--steps", "1"], encoding="utf-8")
    )
    assert first["progress"][-1]["next_stage"] == "consolidation"
    second = json.loads(subprocess.check_output(command, encoding="utf-8"))
    assert second["progress"][0]["stage"] == "consolidation"
    assert second["progress"][-1]["complete"]
    assert second["active_memories"] == ["更正一下，我现在喜欢深色主题。"]
    assert len(second["query_hits"]) == 1
    hit = second["query_hits"][0]
    assert hit["state"] == "candidate" and hit["authority"] == "human_self"
    assert set(hit["evidence_ids"]) == {"theme-1", "theme-2"}
    third = json.loads(subprocess.check_output(command, encoding="utf-8"))
    assert third["progress"] == [{"ok": True, "stage": "complete", "complete": True}]
    assert third["query_hits"] == second["query_hits"]

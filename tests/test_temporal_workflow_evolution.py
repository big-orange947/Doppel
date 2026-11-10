"""Synthetic lifecycle scenarios through the actual resumable host recipe."""

from datetime import UTC, datetime

import pytest

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DeterministicMemoryGovernancePolicy,
    DoppelClient,
    HistoryWindow,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PersonalMemoryQueryDraftV2,
    SQLiteStore,
)
from examples.checked_ingest import ingest_checked
from examples.incremental_personal_memory import SQLiteManifestIndex
from examples.personal_memory_runtime import PersonalMemoryWorkflow, WorkflowState

SCOPE = MemoryScope(user_id="owner", agent_id="test")


def at(day, hour=0):
    return datetime(2026, 1, day, hour, tzinfo=UTC)


class Script:
    name, version = "test.evolution-fixtures", "1"

    def __init__(self, drafts):
        self.drafts, self.calls = drafts, 0

    async def analyze(self, request):
        self.calls += 1
        return PersonalMemoryAnalysis(
            memories=[self.drafts[message.identity_key] for message in request.messages]
        )


def draft(
    identity, content, *, memory_type="state", temporal_status="current", **fields
):
    return PersonalMemoryDraft(
        content=content,
        memory_type=memory_type,
        temporal_status=temporal_status,
        topic_key="opaque.slot",
        evidence_ids=[identity],
        **fields,
    )


def job(path, store, analyzer, *, governance=False, policy=None):
    return PersonalMemoryWorkflow(
        path / "jobs",
        workflow_key="evolution",
        storage_identity=str(path / "memory.sqlite3"),
        store=store,
        scope=SCOPE,
        miner=PersonalMemoryMiner(
            analyzer, PersonalMemoryMinerConfig(owner_target_scope="conversation")
        ),
        consolidator=DeterministicMemoryConsolidator(),
        governance_policy=policy
        or (DeterministicMemoryGovernancePolicy() if governance else None),
        index=SQLiteManifestIndex(path / "index.sqlite3"),
        index_page_size=2,
    )


async def run_window(path, analyzer, day, identities, *, governance=False):
    store = SQLiteStore(database=str(path / "memory.sqlite3"))
    try:
        for identity in identities:
            await ingest_checked(
                store,
                SCOPE,
                ChatMessage.of(
                    "owner",
                    analyzer.drafts[identity].content,
                    at(day, 12),
                    message_id=identity,
                ),
            )
        window = HistoryWindow(start=at(day), end=at(day + 1, 12))
        workflow = job(path, store, analyzer, governance=governance)
        for _ in range(100):
            result = await workflow.step(window)
            assert result["ok"], result
            if result["complete"]:
                break
        else:
            pytest.fail("workflow did not finish")
        # Every window reopens the Store and recreates the directory adapter.
        index = SQLiteManifestIndex(path / "index.sqlite3")
        rows = (
            await store.scan(
                SCOPE, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        for row in rows:
            assert (await index.inspect(SCOPE, row.memory_id) is not None) == (
                row.state.value in {"candidate", "confirmed"}
            )
        return rows, workflow.path
    finally:
        await store.close()


class Planner:
    name, version = "test.explicit-time-fields", "1"

    def __init__(self, **fields):
        self.draft = PersonalMemoryQueryDraftV2(**fields)

    async def plan(self, request):
        return self.draft


async def query(path, now, **fields):
    client = DoppelClient(backend="sqlite", database=str(path / "memory.sqlite3"))
    try:
        return await client.query_personal_memory(
            "opaque", [SCOPE], planner=Planner(**fields), now=now
        )
    finally:
        await client.close()


@pytest.mark.parametrize(
    "memory_type,status,revision",
    [
        ("plan", "planned", "retraction"),
        ("state", "current", "retraction"),
        ("preference", "current", "correction"),
    ],
)
async def test_cancellation_and_retraction_preserve_history_without_current_claim(
    tmp_path, memory_type, status, revision
):
    analyzer = Script(
        {
            "initial": draft(
                "initial",
                "opaque initial",
                memory_type=memory_type,
                temporal_status=status,
            ),
            "withdrawn": draft(
                "withdrawn",
                "opaque withdrawn",
                memory_type=memory_type,
                temporal_status="historical",
                revision_kind=revision,
            ),
        }
    )
    await run_window(tmp_path, analyzer, 1, ["initial"])
    rows, _ = await run_window(tmp_path, analyzer, 3, ["withdrawn"])
    assert analyzer.calls == 2
    result = await query(
        tmp_path,
        at(5),
        temporal_view="planned" if status == "planned" else "current",
        search_text="opaque",
    )
    assert result.hits == []
    historical = await query(
        tmp_path, at(5), temporal_view="prior", search_text="opaque"
    )
    assert [hit.record.content for hit in historical.hits] == ["opaque withdrawn"]
    assert {
        ref["evidence_id"] for ref in historical.hits[0].record.metadata["evidence"]
    } == {"initial", "withdrawn"}
    count = await query(
        tmp_path,
        at(5),
        operation="count",
        temporal_view="prior",
        memory_types=["episode"],
    )
    assert count.count.status == "exact" and count.count.value == 0
    assert all(row.metadata.get("personal_memory_type") != "episode" for row in rows)


async def test_three_revisions_across_reopens_keep_latest_and_all_evidence(tmp_path):
    analyzer = Script(
        {
            str(i): draft(
                str(i),
                f"opaque value-{i}",
                revision_kind="assertion" if i == 1 else "correction",
            )
            for i in range(1, 4)
        }
    )
    for day, identity in [(1, "1"), (3, "2"), (5, "3")]:
        await run_window(tmp_path, analyzer, day, [identity])
        result = await query(
            tmp_path, at(day + 2), temporal_view="current", search_text="opaque"
        )
        assert [hit.record.content for hit in result.hits] == [
            f"opaque value-{identity}"
        ]
        assert {
            ref["evidence_id"] for ref in result.hits[0].record.metadata["evidence"]
        } == {str(i) for i in range(1, int(identity) + 1)}
    assert analyzer.calls == 3


async def test_empty_later_window_archives_expired_temporary_state(tmp_path):
    analyzer = Script(
        {
            "base": PersonalMemoryDraft(
                content="opaque baseline",
                memory_type="fact",
                temporal_status="timeless",
                topic_key="opaque.base",
                evidence_ids=["base"],
            ),
            "temporary": draft(
                "temporary",
                "opaque temporary",
                valid_from=at(1, 12),
                valid_to=at(2, 12),
            ),
        }
    )
    _, path = await run_window(
        tmp_path, analyzer, 1, ["base", "temporary"], governance=True
    )
    before = await query(
        tmp_path, at(2, 12), temporal_view="current", search_text="opaque"
    )
    assert {hit.record.content for hit in before.hits} == {
        "opaque baseline",
        "opaque temporary",
    }
    rows, _ = await run_window(tmp_path, analyzer, 3, [], governance=True)
    assert analyzer.calls == 1  # an empty history page must not invoke the model
    after = await query(tmp_path, at(5), temporal_view="current", search_text="opaque")
    assert [hit.record.content for hit in after.hits] == ["opaque baseline"]
    archives = [row for row in rows if "governance-archive" in row.tags]
    assert len(archives) == 1 and archives[0].state.value == "expired"
    assert archives[0].metadata["valid_to"] == at(2, 12).isoformat()
    snapshot = WorkflowState.model_validate_json(path.read_text(encoding="utf-8"))
    assert snapshot.governance_checkpoint.cycle == 2
    historical = await query(
        tmp_path, at(5), temporal_view="as_of", as_of=at(2), search_text="opaque"
    )
    assert "opaque temporary" in {hit.record.content for hit in historical.hits}
    assert all(
        hit.candidate_evidence.as_of_match == "validity_match"
        for hit in historical.hits
        if hit.record.content == "opaque temporary"
    )


@pytest.mark.parametrize("failure", ["transition", "checkpoint_save"])
async def test_governance_partial_execution_resumes_original_plan(tmp_path, failure):
    from doppel_memory import MemoryStateConflictError

    class PartialStore(SQLiteStore):
        async def transition(self, *args, **kwargs):
            if failure == "transition":
                raise MemoryStateConflictError("synthetic transition outage")
            return await super().transition(*args, **kwargs)

    class Policy(DeterministicMemoryGovernancePolicy):
        calls = 0

        async def evaluate(self, input):
            self.calls += 1
            return await super().evaluate(input)

    analyzer = Script(
        {"t": draft("t", "opaque ended", valid_from=at(1, 12), valid_to=at(1, 18))}
    )
    window = HistoryWindow(start=at(1), end=at(2))
    store = PartialStore(database=str(tmp_path / "memory.sqlite3"))
    original_policy = Policy()
    try:
        await ingest_checked(
            store,
            SCOPE,
            ChatMessage.of("owner", "opaque ended", at(1, 12), message_id="t"),
        )
        workflow = job(tmp_path, store, analyzer, policy=original_policy)
        assert (await workflow.step(window))["next_stage"] == "consolidation"
        assert (await workflow.step(window))["next_stage"] == "governance"
        save = workflow._save

        async def fail_after_execute(state):
            if state.stage == "index":
                raise OSError("synthetic checkpoint disk error")
            await save(state)

        if failure == "checkpoint_save":
            workflow._save = fail_after_execute
            with pytest.raises(OSError):
                await workflow.step(window)
        else:
            assert not (await workflow.step(window))["ok"]
        saved = WorkflowState.model_validate_json(
            workflow.path.read_text(encoding="utf-8")
        )
        assert saved.stage == "governance" and saved.pending_governance
        assert saved.governance_checkpoint is None
        assert saved.pending_governance.evaluated_at == window.end
        assert original_policy.calls == 1
    finally:
        await store.close()
    reopened = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    restored_policy = Policy()
    try:
        workflow = job(tmp_path, reopened, analyzer, policy=restored_policy)
        for _ in range(100):
            report = await workflow.step(window)
            assert report["ok"]
            if report["complete"]:
                break
        else:
            pytest.fail("recovery did not finish")
        assert restored_policy.calls == 0
        rows = (
            await reopened.scan(
                SCOPE, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        assert len([row for row in rows if "governance-archive" in row.tags]) == 1
        assert analyzer.calls == 1
    finally:
        await reopened.close()


async def test_governance_opt_in_cannot_reuse_disabled_job(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        analyzer = Script({})
        window = HistoryWindow(start=at(1), end=at(2))
        disabled = job(tmp_path, store, analyzer)
        await disabled.step(window)
        before = disabled.path.read_bytes()
        assert b'"pending_governance"' not in before
        with pytest.raises(ValueError, match="configuration changed"):
            await job(tmp_path, store, analyzer, governance=True).step(window)
        assert disabled.path.read_bytes() == before
    finally:
        await store.close()

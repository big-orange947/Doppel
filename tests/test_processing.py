"""Contract tests for the backend-neutral proposal pipeline."""

from __future__ import annotations

from collections.abc import Sequence

from doppel_memory import (
    Actor,
    ChatMessage,
    DoppelClient,
    EventProcessor,
    InMemoryStore,
    MemoryKind,
    MemoryPipeline,
    MemoryProposal,
    MemoryScope,
    MemoryState,
    ProcessorHooks,
    WriteStatus,
)

SCOPE = MemoryScope(
    user_id="u1",
    agent_id="agent",
    platform="qq",
    chat_type="private",
    chat_id="c1",
)
MESSAGE = ChatMessage.of(
    Actor.OWNER,
    "我偏好简短回复",
    "2026-08-26T12:00:00+08:00",
    event_id="e1",
    message_id="m1",
)


async def test_event_processor_proposes_complete_provenance() -> None:
    proposal = (await EventProcessor().process(SCOPE, MESSAGE))[0]
    assert proposal.kind == MemoryKind.EVENT
    assert proposal.scope == SCOPE
    assert proposal.proposed_state is MemoryState.CONFIRMED
    assert proposal.idempotency_key == "event:m1"
    assert proposal.source_event_id == "e1"
    assert proposal.source_message_id == "m1"
    assert proposal.processor == "event"
    assert proposal.created_at.isoformat() == "2026-08-26T04:00:00+00:00"

    record = proposal.to_record()
    assert record.extractor == "event"
    assert record.metadata["confidence"] == 1.0
    assert record.metadata["processor_version"] == "1"


async def test_client_process_defaults_to_idempotent_event_processor() -> None:
    client = DoppelClient(backend="memory")
    first = await client.process(SCOPE, MESSAGE)
    second = await client.process(SCOPE, MESSAGE)

    assert first.accepted_count == 1
    assert first.write_results[0].status is WriteStatus.CREATED
    assert second.accepted_count == 0
    assert second.write_results[0].status is WriteStatus.DUPLICATE
    assert len(await client.recall("简短", [SCOPE])) == 1


class FactProcessor:
    name = "test.fact"
    version = "1"

    def __init__(self, target: MemoryScope = SCOPE) -> None:
        self.target = target

    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]:
        return [
            MemoryProposal(
                scope=self.target,
                kind=MemoryKind.FACT,
                content="偏好简短回复",
                actor=message.actor,
                idempotency_key="fact:short-replies",
                source_message_id=message.message_id,
                processor=self.name,
                processor_version=self.version,
                derived_chain=["message:m1"],
            )
        ]


class ConfirmPolicy:
    async def evaluate(
        self, proposal: MemoryProposal, message: ChatMessage
    ) -> MemoryProposal:
        return proposal.model_copy(
            update={"proposed_state": MemoryState.CONFIRMED}, deep=True
        )


class RejectPolicy:
    async def evaluate(self, proposal: MemoryProposal, message: ChatMessage) -> None:
        return None


class InvalidPolicy:
    async def evaluate(
        self, proposal: MemoryProposal, message: ChatMessage
    ) -> MemoryProposal:
        return proposal.model_copy(update={"scope": "not-a-scope"})


async def test_policy_can_confirm_or_reject_without_processor_store_access() -> None:
    confirmed_store = InMemoryStore()
    confirmed = await MemoryPipeline(
        confirmed_store, [FactProcessor()], policy=ConfirmPolicy()
    ).run(SCOPE, MESSAGE)
    assert confirmed.accepted_count == 1
    assert confirmed.proposals[0].proposed_state is MemoryState.CONFIRMED

    rejected_store = InMemoryStore()
    rejected = await MemoryPipeline(
        rejected_store, [FactProcessor()], policy=RejectPolicy()
    ).run(SCOPE, MESSAGE)
    assert rejected.write_results[0].status is WriteStatus.SKIPPED
    assert rejected.write_results[0].error_code == "policy_rejected"
    assert await rejected_store.search("简短", [SCOPE]) == []

    invalid = await MemoryPipeline(
        InMemoryStore(), [FactProcessor()], policy=InvalidPolicy()
    ).run(SCOPE, MESSAGE)
    assert invalid.write_results[0].status is WriteStatus.FAILED
    assert invalid.write_results[0].error_code == "proposal_evaluation_failed"
    assert invalid.errors[0].stage == "evaluate"


async def test_pipeline_requires_explicit_permission_for_target_scope() -> None:
    user_scope = SCOPE.user_scope()
    store = InMemoryStore()
    pipeline = MemoryPipeline(store, [FactProcessor(user_scope)])

    blocked = await pipeline.run(SCOPE, MESSAGE)
    assert blocked.failed_count == 1
    assert blocked.write_results[0].error_code == "scope_not_allowed"
    assert blocked.errors[0].stage == "validate"
    assert await store.search("简短", [user_scope]) == []

    allowed = await pipeline.run(SCOPE, MESSAGE, allowed_scopes=[user_scope])
    assert allowed.accepted_count == 1
    assert len(await store.search("简短", [user_scope])) == 1


class DuplicateProcessor(FactProcessor):
    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]:
        proposal = (await super().process(scope, message))[0]
        return [proposal, proposal.model_copy(deep=True)]


async def test_pipeline_deduplicates_proposals_within_one_run() -> None:
    result = await MemoryPipeline(InMemoryStore(), [DuplicateProcessor()]).run(
        SCOPE, MESSAGE
    )
    assert [item.status for item in result.write_results] == [
        WriteStatus.CREATED,
        WriteStatus.SKIPPED,
    ]
    assert result.write_results[1].error_code == "duplicate_proposal"


class BrokenProcessor:
    name = "broken"
    version = "1"

    async def process(
        self, scope: MemoryScope, message: ChatMessage
    ) -> Sequence[MemoryProposal]:
        raise RuntimeError("processor unavailable")


class RecordingHooks(ProcessorHooks):
    def __init__(self) -> None:
        self.events: list[str] = []

    async def before_process(self, scope: MemoryScope, message: ChatMessage) -> None:
        self.events.append("before_process")

    async def after_proposal(
        self, proposal: MemoryProposal, message: ChatMessage
    ) -> None:
        self.events.append("after_proposal")

    async def before_write(self, proposal, record) -> None:
        self.events.append("before_write")

    async def after_write(self, proposal, result) -> None:
        self.events.append("after_write")

    async def on_error(self, stage, error, *, processor="", proposal=None) -> None:
        self.events.append(f"on_error:{stage}:{processor}")


async def test_processor_errors_are_visible_and_other_processors_continue() -> None:
    hooks = RecordingHooks()
    result = await MemoryPipeline(
        InMemoryStore(), [BrokenProcessor(), FactProcessor()], hooks=hooks
    ).run(SCOPE, MESSAGE)

    assert result.accepted_count == 1
    assert result.errors[0].processor == "broken"
    assert result.errors[0].error_type == "RuntimeError"
    assert hooks.events == [
        "before_process",
        "on_error:process:broken",
        "after_proposal",
        "before_write",
        "after_write",
    ]


class FailingAfterWriteHooks(ProcessorHooks):
    async def after_write(self, proposal, result) -> None:
        raise RuntimeError("observer unavailable")


async def test_after_write_failure_does_not_relabel_successful_persistence() -> None:
    store = InMemoryStore()
    result = await MemoryPipeline(
        store, [FactProcessor()], hooks=FailingAfterWriteHooks()
    ).run(SCOPE, MESSAGE)

    assert len(result.proposals) == len(result.write_results) == 1
    assert result.write_results[0].status is WriteStatus.CREATED
    assert result.accepted_count == 1
    assert result.errors[0].stage == "after_write"
    assert len(await store.search("简短", [SCOPE])) == 1


async def test_explicit_empty_processor_list_is_a_noop() -> None:
    client = DoppelClient(backend="memory")
    result = await client.process(SCOPE, MESSAGE, processors=[])
    assert result.proposals == []
    assert result.write_results == []
    assert await client.recall("简短", [SCOPE]) == []

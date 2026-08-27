"""Evidence, role, scope, and batch guards for personal-memory intelligence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from doppel_memory import (
    Actor,
    ChatMessage,
    DoppelClient,
    FactAuthority,
    HistoryWindow,
    InMemoryStore,
    MemoryScope,
    MemoryState,
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryDraft,
    PersonalMemoryEvidenceError,
    PersonalMemoryExtractor,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    ReferencePersonalMemoryAnalyzer,
    StructuredGenerationRequest,
    WriteStatus,
)

SCOPE = MemoryScope(
    user_id="owner-1",
    agent_id="personal-agent",
    platform="qq",
    chat_type="private",
    chat_id="contact-1",
)


def _message(
    identity: str,
    text: str,
    *,
    actor: str = Actor.OWNER,
    sender_id: str = "owner-1",
    day: int = 1,
) -> ChatMessage:
    return ChatMessage(
        actor=actor,
        text=text,
        at=datetime(2026, 1, day, tzinfo=UTC),
        event_id=f"event-{identity}",
        message_id=identity,
        sender_id=sender_id,
    )


class StubAnalyzer:
    name = "tests.stub-personal-memory"
    version = "1"

    def __init__(self, memories: list[dict[str, Any]]) -> None:
        self.memories = memories
        self.requests: list[PersonalMemoryAnalysisRequest] = []

    async def analyze(
        self, request: PersonalMemoryAnalysisRequest
    ) -> PersonalMemoryAnalysis:
        self.requests.append(request)
        return PersonalMemoryAnalysis(memories=self.memories)


class StubStructuredModel:
    name = "tests.structured-model"
    version = "1"

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.requests: list[StructuredGenerationRequest] = []

    async def generate(self, request: StructuredGenerationRequest):
        self.requests.append(request)
        return self.result


@pytest.mark.asyncio
async def test_online_owner_memory_is_evidence_bound_and_user_scoped() -> None:
    message = _message("owner-pref", "我吃火锅不喜欢香菜。")
    analyzer = StubAnalyzer(
        [
            {
                "content": "用户吃火锅时不喜欢香菜。",
                "memory_type": "preference",
                "subject": "owner",
                "confidence": 0.96,
                "evidence_ids": [message.identity_key],
            }
        ]
    )
    extractor = PersonalMemoryExtractor(analyzer)

    (proposal,) = await extractor.process(SCOPE, message)

    assert proposal.scope == SCOPE.user_scope()
    assert proposal.actor == Actor.OWNER
    assert proposal.authority is FactAuthority.HUMAN_SELF
    assert proposal.proposed_state is MemoryState.CANDIDATE
    assert proposal.source_message_id == "owner-pref"
    assert proposal.source_event_id == "event-owner-pref"
    assert proposal.derived_chain == ["event:owner-pref"]
    assert proposal.tags[:2] == ["personal-memory", "preference"]
    assert proposal.metadata["subject_id"] == "owner-1"
    assert proposal.metadata["source_scope_key"] == SCOPE.scope_key
    assert proposal.metadata["evidence"] == [
        {
            "evidence_id": "owner-pref",
            "message_id": "owner-pref",
            "event_id": "event-owner-pref",
            "actor": "owner",
            "sender_id": "owner-1",
            "at": "2026-01-01T00:00:00+00:00",
        }
    ]
    assert proposal.idempotency_key.startswith("personal-memory:")


@pytest.mark.asyncio
async def test_user_scope_write_still_requires_explicit_pipeline_authorization() -> (
    None
):
    message = _message("owner-work", "我目前在上海做后端开发。")
    extractor = PersonalMemoryExtractor(
        StubAnalyzer(
            [
                {
                    "content": "用户目前在上海从事后端开发。",
                    "memory_type": "state",
                    "temporal_status": "current",
                    "evidence_ids": [message.identity_key],
                }
            ]
        )
    )
    client = DoppelClient(InMemoryStore())

    denied = await client.process(SCOPE, message, processors=[extractor])
    assert denied.write_results[0].error_code == "scope_not_allowed"

    accepted = await client.process(
        SCOPE,
        message,
        processors=[extractor],
        allowed_scopes=[SCOPE.user_scope()],
    )
    assert accepted.write_results[0].status is WriteStatus.CREATED
    stored = accepted.write_results[0].record
    assert stored is not None
    assert stored.scope == SCOPE.user_scope()
    assert stored.state is MemoryState.CANDIDATE
    assert stored.metadata["temporal_status"] == "current"


@pytest.mark.asyncio
async def test_contact_memory_remains_conversation_scoped() -> None:
    message = _message(
        "contact-health",
        "我对花生过敏。",
        actor=Actor.CONTACT,
        sender_id="contact-1",
    )
    extractor = PersonalMemoryExtractor(
        StubAnalyzer(
            [
                {
                    "content": "联系人对花生过敏。",
                    "memory_type": "fact",
                    "subject": "contact",
                    "evidence_ids": [message.identity_key],
                }
            ]
        )
    )

    (proposal,) = await extractor.process(SCOPE, message)

    assert proposal.scope == SCOPE
    assert proposal.actor == Actor.CONTACT
    assert proposal.authority is FactAuthority.PEER_STATEMENT
    assert proposal.metadata["subject_id"] == "contact-1"


@pytest.mark.asyncio
async def test_contact_subject_requires_one_trusted_sender_identity() -> None:
    extractor = PersonalMemoryExtractor(
        StubAnalyzer(
            [
                {
                    "content": "联系人对花生过敏。",
                    "subject": "contact",
                    "evidence_ids": ["contact-without-sender"],
                }
            ]
        )
    )
    message = _message(
        "contact-without-sender",
        "我对花生过敏。",
        actor=Actor.CONTACT,
        sender_id="",
    )

    with pytest.raises(PersonalMemoryEvidenceError, match="trusted evidence sender_id"):
        await extractor.process(SCOPE, message)


@pytest.mark.asyncio
async def test_agent_output_is_not_sent_to_the_analyzer_by_default() -> None:
    analyzer = StubAnalyzer(
        [
            {
                "content": "用户应当吃素。",
                "evidence_ids": ["agent-advice"],
            }
        ]
    )
    extractor = PersonalMemoryExtractor(analyzer)

    proposals = await extractor.process(
        SCOPE,
        _message(
            "agent-advice",
            "你可以尝试素食。",
            actor=Actor.AGENT,
            sender_id="personal-agent",
        ),
    )

    assert proposals == []
    assert analyzer.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("draft", "error"),
    [
        (
            {
                "content": "无来源记忆",
                "evidence_ids": ["unknown"],
            },
            "unknown evidence",
        ),
        (
            {
                "content": "把联系人事实写给用户",
                "subject": "contact",
                "evidence_ids": ["owner-fact"],
            },
            "does not match evidence actor",
        ),
        (
            {
                "content": "伪造用户身份",
                "subject_id": "other-user",
                "evidence_ids": ["owner-fact"],
            },
            "trusted scope user_id",
        ),
    ],
)
async def test_untrusted_evidence_subject_and_identity_are_rejected(
    draft: dict[str, Any], error: str
) -> None:
    extractor = PersonalMemoryExtractor(StubAnalyzer([draft]))

    with pytest.raises(PersonalMemoryEvidenceError, match=error):
        await extractor.process(SCOPE, _message("owner-fact", "我是用户。"))


@pytest.mark.asyncio
async def test_confidence_gate_and_batch_duplicate_guard_are_deterministic() -> None:
    base = {
        "content": "用户喜欢绿色。",
        "memory_type": "preference",
        "evidence_ids": ["color"],
    }
    extractor = PersonalMemoryExtractor(
        StubAnalyzer(
            [
                {**base, "confidence": 0.7},
                {**base, "confidence": 0.9},
                {**base, "confidence": 0.9},
            ]
        )
    )

    proposals = await extractor.process(SCOPE, _message("color", "我喜欢绿色。"))

    assert len(proposals) == 1
    assert proposals[0].confidence == 0.9


@pytest.mark.asyncio
async def test_reference_analyzer_supplies_bounded_input_and_schema() -> None:
    model = StubStructuredModel(
        {
            "memories": [
                {
                    "content": "用户不喝咖啡。",
                    "memory_type": "preference",
                    "evidence_ids": ["coffee"],
                }
            ]
        }
    )
    analyzer = ReferencePersonalMemoryAnalyzer(model)
    request = PersonalMemoryAnalysisRequest(
        scope=SCOPE, messages=[_message("coffee", "我不喝咖啡。")]
    )

    analysis = await analyzer.analyze(request)

    assert analysis.memories[0].content == "用户不喝咖啡。"
    generated = model.requests[0]
    assert "Prefer precision" in generated.instructions
    assert "Do not consolidate conflicts" in generated.instructions
    assert generated.input["scope"] == SCOPE.describe()
    assert generated.input["messages"][0]["evidence_id"] == "coffee"
    assert generated.output_schema["title"] == "PersonalMemoryAnalysis"


@pytest.mark.asyncio
async def test_contextual_miner_reads_history_and_binds_multiple_evidence() -> None:
    store = InMemoryStore()
    client = DoppelClient(store)
    first = _message("coffee-1", "我不喝咖啡，会睡不着。", day=1)
    second = _message("coffee-2", "还是给我茶吧，我不喝咖啡。", day=2)
    await client.ingest(SCOPE, first)
    await client.ingest(SCOPE, second)
    analyzer = StubAnalyzer(
        [
            {
                "content": "用户不喝咖啡，因为会影响睡眠。",
                "memory_type": "preference",
                "subject": "owner",
                "confidence": 0.98,
                "evidence_ids": ["coffee-1", "coffee-2"],
            }
        ]
    )
    miner = PersonalMemoryMiner(
        analyzer,
        PersonalMemoryMinerConfig(page_size=1, max_messages=10),
    )

    result = await client.run_batch_task(
        miner,
        SCOPE,
        HistoryWindow(
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        allowed_scopes=[SCOPE.user_scope()],
        run_id="personal-miner-test",
    )

    assert not result.errors
    assert result.history_pages_read == 2
    assert result.history_messages_read == 2
    assert result.write_results[0].status is WriteStatus.CREATED
    assert result.proposals[0].scope == SCOPE.user_scope()
    assert result.proposals[0].derived_chain == [
        "event:coffee-1",
        "event:coffee-2",
    ]
    assert len(result.proposals[0].metadata["evidence"]) == 2
    assert result.committable_checkpoint is not None
    assert result.committable_checkpoint.metadata["eligible_messages"] == 2
    assert result.committable_checkpoint.metadata["truncated"] is False


def test_personal_memory_models_reject_unstable_evidence_and_time() -> None:
    with pytest.raises(ValueError, match="message_id or event_id"):
        PersonalMemoryAnalysisRequest(
            scope=SCOPE,
            messages=[
                ChatMessage(
                    actor=Actor.OWNER,
                    text="没有稳定来源",
                    at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ],
        )
    with pytest.raises(ValueError, match="must be unique"):
        PersonalMemoryDraft(content="重复来源", evidence_ids=["same", "same"])
    with pytest.raises(ValueError, match="must not precede"):
        PersonalMemoryDraft(
            content="无效区间",
            evidence_ids=["time"],
            valid_from=datetime(2026, 1, 2, tzinfo=UTC),
            valid_to=datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        PersonalMemoryDraft.model_validate(
            {
                "content": "模型不能指定作用域",
                "evidence_ids": ["scope"],
                "scope": SCOPE.model_dump(),
            }
        )

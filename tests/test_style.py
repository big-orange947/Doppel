"""StyleMiner closes the owner-history to persona-material loop."""

from __future__ import annotations

from datetime import datetime

import pytest

from doppel_memory import (
    Actor,
    ChatMessage,
    DeterministicStyleAnalyzer,
    DoppelClient,
    HistoryPage,
    HistoryWindow,
    InMemoryStore,
    MemoryFilter,
    MemoryKind,
    MemoryScope,
    StyleMiner,
    StyleMinerConfig,
    StyleProfile,
)

SCOPE = MemoryScope(
    user_id="owner-1",
    agent_id="agent-1",
    platform="qq",
    chat_type="private",
    chat_id="contact-1",
)
WINDOW = HistoryWindow(
    start="2026-08-01T00:00:00Z",
    end="2026-09-01T00:00:00Z",
)


def _message(
    actor: str,
    text: str,
    event_id: str,
    *,
    message_type: str = "message",
) -> ChatMessage:
    index = int(event_id.rsplit("-", maxsplit=1)[-1])
    return ChatMessage.of(
        actor,
        text,
        f"2026-08-{index:02d}T12:00:00Z",
        event_id=event_id,
        message_type=message_type,
    )


class ListHistoryReader:
    """Stable reader that intentionally ignores actor filters for defense testing."""

    def __init__(self, messages: list[ChatMessage]) -> None:
        self._messages = messages

    @property
    def scope(self) -> MemoryScope:
        return SCOPE

    async def read(
        self,
        *,
        cursor: str = "",
        limit: int = 500,
        actors: set[str] | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> HistoryPage:
        del actors, time_from, time_to
        start = int(cursor or 0)
        selected = self._messages[start : start + limit]
        next_cursor = str(start + len(selected)) if selected else cursor
        return HistoryPage(
            messages=selected,
            next_cursor=next_cursor,
            has_more=start + len(selected) < len(self._messages),
        )


def _config(**updates) -> StyleMinerConfig:
    values = {
        "min_messages": 3,
        "page_size": 2,
        "short_message_chars": 5,
        "min_phrase_messages": 2,
        "min_phrase_ratio": 0.5,
        **updates,
    }
    return StyleMinerConfig(**values)


async def test_deterministic_analyzer_reports_transparent_features() -> None:
    messages = [
        _message(Actor.OWNER, "哈哈可以！", "event-1"),
        _message(Actor.OWNER, "哈哈，可以吗？", "event-2"),
        _message(Actor.OWNER, "哈哈\n好的😊", "event-3"),
    ]
    profile = await DeterministicStyleAnalyzer().analyze(messages, config=_config())

    assert profile is not None
    assert profile.message_count == 3
    assert profile.question_ratio == pytest.approx(1 / 3, abs=0.0001)
    assert profile.exclamation_ratio == pytest.approx(1 / 3, abs=0.0001)
    assert profile.emoji_ratio == pytest.approx(1 / 3, abs=0.0001)
    assert profile.multiline_ratio == pytest.approx(1 / 3, abs=0.0001)
    assert profile.terminal_punctuation_ratio == pytest.approx(2 / 3, abs=0.0001)
    assert "哈哈" in profile.common_phrases
    assert profile.summary.startswith("基于 3 条号主文本")
    assert "高频片段" in profile.summary


async def test_analyzer_does_not_invent_a_profile_below_threshold() -> None:
    profile = await DeterministicStyleAnalyzer().analyze(
        [_message(Actor.OWNER, "只有一条", "event-1")],
        config=_config(),
    )
    assert profile is None


async def test_style_miner_filters_text_and_populates_persona_materials() -> None:
    reader = ListHistoryReader(
        [
            _message(Actor.OWNER, "哈哈可以！", "event-1"),
            _message(Actor.CONTACT, "哈哈不应分析", "event-2"),
            _message(Actor.OWNER, "哈哈，可以吗？", "event-3"),
            _message(
                Actor.OWNER,
                "图片里的文字不默认分析",
                "event-4",
                message_type="image",
            ),
            _message(Actor.OWNER, "哈哈\n好的😊", "event-5"),
            _message(Actor.OWNER, "", "event-6", message_type="nudge"),
        ]
    )
    store = InMemoryStore()
    client = DoppelClient(store)
    task = StyleMiner(_config())

    result = await client.run_batch_task(
        task,
        SCOPE,
        WINDOW,
        history=reader,
        run_id="style-run-1",
    )

    assert result.accepted_count == 1
    assert result.history_pages_read == 3
    assert result.history_messages_read == 6
    assert result.committable_checkpoint is not None
    assert result.committable_checkpoint.metadata["messages_seen"] == 6
    assert result.committable_checkpoint.metadata["eligible_messages"] == 3
    proposal = result.proposals[0]
    assert proposal.kind == MemoryKind.STYLE
    assert proposal.scope == SCOPE
    assert proposal.derived_chain == [
        "event:event-1",
        "event:event-3",
        "event:event-5",
    ]

    (stored,) = await store.search(
        "",
        [SCOPE],
        filters=MemoryFilter(kinds={MemoryKind.STYLE}),
    )
    record = await store.get(SCOPE, stored.memory_id)
    assert record is not None
    profile = StyleProfile.model_validate(record.metadata["style_profile"])
    assert profile.message_count == 3
    assert record.extractor == StyleMiner.name

    materials = await client.materials(SCOPE, query="完全不相关的当前问题")
    assert materials.style_summary == profile.summary
    assert all(item.kind != MemoryKind.STYLE for item in materials.events)
    assert any(item["memory_id"] == stored.memory_id for item in materials.provenance)
    assert "号主风格" in materials.render()

    retry = await client.run_batch_task(
        task,
        SCOPE,
        WINDOW,
        checkpoint=result.committable_checkpoint,
        history=reader,
        run_id="style-run-2",
    )
    assert retry.proposals == []
    assert retry.committable_checkpoint is not None
    assert retry.committable_checkpoint.cursor == result.committable_checkpoint.cursor


async def test_user_scope_target_requires_explicit_write_authorization() -> None:
    reader = ListHistoryReader(
        [
            _message(Actor.OWNER, "第一条", "event-1"),
            _message(Actor.OWNER, "第二条", "event-2"),
            _message(Actor.OWNER, "第三条", "event-3"),
        ]
    )
    task = StyleMiner(_config(target_scope="user"))
    client = DoppelClient(InMemoryStore())

    denied = await client.run_batch_task(task, SCOPE, WINDOW, history=reader)
    assert denied.failed_count == 1
    assert denied.write_results[0].error_code == "scope_not_allowed"
    assert denied.committable_checkpoint is None

    user_scope = SCOPE.user_scope()
    accepted = await client.run_batch_task(
        task,
        SCOPE,
        WINDOW,
        history=reader,
        allowed_scopes=[user_scope],
    )
    assert accepted.accepted_count == 1
    assert accepted.proposals[0].scope == user_scope


def test_style_config_identity_changes_with_semantics() -> None:
    base = StyleMiner(_config())
    changed = StyleMiner(_config(short_message_chars=8))
    assert base.checkpoint_key != changed.checkpoint_key
    assert (
        _config(accepted_message_types={"text", "message"}).fingerprint
        == _config(accepted_message_types={"message", "text"}).fingerprint
    )


class InvalidIdentityAnalyzer:
    name = "custom-analyzer"
    version = "1"

    async def analyze(self, messages, *, config):
        del config
        return StyleProfile(
            analyzer="wrong-analyzer",
            analyzer_version=self.version,
            message_count=len(messages),
            character_count=1,
            average_message_length=1,
            median_message_length=1,
            short_message_threshold=12,
            short_message_ratio=1,
            question_ratio=0,
            exclamation_ratio=0,
            emoji_ratio=0,
            multiline_ratio=0,
            terminal_punctuation_ratio=0,
            summary="invalid",
        )


async def test_invalid_custom_analyzer_output_is_a_structured_batch_failure() -> None:
    reader = ListHistoryReader(
        [
            _message(Actor.OWNER, "第一条", "event-1"),
            _message(Actor.OWNER, "第二条", "event-2"),
            _message(Actor.OWNER, "第三条", "event-3"),
        ]
    )
    task = StyleMiner(_config(), analyzer=InvalidIdentityAnalyzer())
    result = await DoppelClient(InMemoryStore()).run_batch_task(
        task, SCOPE, WINDOW, history=reader
    )
    assert result.proposals == []
    assert result.errors[0].stage == "batch_propose"
    assert "identity" in result.errors[0].message
    assert result.committable_checkpoint is None

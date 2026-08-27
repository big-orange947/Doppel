"""StyleProfessor consumption and independent observable-output evaluation."""

from __future__ import annotations

import pytest

from doppel_memory import (
    Actor,
    DoppelClient,
    InMemoryStore,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    StyleProfessor,
    StyleProfessorConfig,
    StyleProfile,
    StyleQualityConfig,
    StyleQualityEvaluator,
)

SCOPE = MemoryScope(
    user_id="owner-1",
    agent_id="agent-1",
    platform="qq",
    chat_type="private",
    chat_id="contact-1",
)


def _profile(**updates) -> StyleProfile:
    values = {
        "analyzer": "test-analyzer",
        "analyzer_version": "1",
        "message_count": 50,
        "character_count": 200,
        "average_message_length": 4,
        "median_message_length": 4,
        "short_message_threshold": 6,
        "short_message_ratio": 1,
        "question_ratio": 0.5,
        "exclamation_ratio": 0,
        "emoji_ratio": 0.5,
        "multiline_ratio": 0,
        "terminal_punctuation_ratio": 1,
        "common_phrases": ["好呀", "收到"],
        "summary": "transparent test profile",
        **updates,
    }
    return StyleProfile(**values)


def test_professor_compiles_deterministic_auditable_guidance() -> None:
    professor = StyleProfessor()

    first = professor.compile(_profile())
    second = professor.compile(_profile())

    assert first == second
    assert first.usable is True
    assert first.professor == professor.name
    assert len(first.prompt) <= professor.config.max_prompt_chars
    assert first.prompt.startswith("[号主表达风格指导]")
    assert "不复制事实、观点或身份" in first.prompt
    assert [item.feature for item in first.directives][:2] == [
        "message_length",
        "terminal_punctuation",
    ]
    assert all(item.evidence for item in first.directives)
    assert all(item.confidence == pytest.approx(0.7071) for item in first.directives)
    assert "好呀" not in first.prompt
    assert first.profile_fingerprint
    assert first.config_fingerprint == professor.config.fingerprint


def test_professor_degrades_safely_for_sparse_profiles() -> None:
    guidance = StyleProfessor().compile(_profile(message_count=3))

    assert guidance.usable is False
    assert guidance.prompt == ""
    assert guidance.directives == []
    assert "3 < 20" in guidance.warnings[0]


def test_phrase_imitation_is_explicit_and_prompt_budget_is_hard() -> None:
    roomy = StyleProfessor(StyleProfessorConfig(include_common_phrases=True)).compile(
        _profile()
    )
    professor = StyleProfessor(
        StyleProfessorConfig(
            include_common_phrases=True,
            max_prompt_chars=240,
        )
    )
    guidance = professor.compile(_profile())

    assert "好呀" in roomy.prompt
    assert any(item.feature == "common_phrases" for item in roomy.directives)
    assert len(guidance.prompt) <= 240
    assert set(guidance.omitted_features)
    assert all(
        directive.feature not in guidance.omitted_features
        for directive in guidance.directives
    )
    assert "lower-priority directives" in guidance.warnings[-1]


async def test_material_builder_loads_profile_and_applies_professor_only_on_request() -> (
    None
):
    store = InMemoryStore()
    profile = _profile()
    await store.put(
        MemoryRecord(
            memory_id="style-1",
            kind=MemoryKind.STYLE,
            scope=SCOPE,
            content=profile.summary,
            actor=Actor.OWNER,
            metadata={"style_profile": profile.model_dump(mode="json")},
        )
    )
    client = DoppelClient(store)

    plain = await client.materials(SCOPE)
    taught = await client.materials(SCOPE, style_professor=StyleProfessor())

    assert plain.style_profile == profile
    assert plain.style_guidance is None
    assert "号主风格：transparent test profile" in plain.render()
    assert taught.style_profile == profile
    assert taught.style_guidance is not None
    assert taught.style_guidance.usable is True
    assert "[号主表达风格指导]" in taught.render()
    assert "transparent test profile" not in taught.render()


def test_quality_evaluator_scores_outputs_without_generator_self_judgment() -> None:
    evaluator = StyleQualityEvaluator()
    matched = ["好呀？😊" if index % 2 == 0 else "收到。" for index in range(20)]
    contrast = [
        "这是一个明显更长的多行回答，和参考的聊天节奏很不一样！\n继续补充！"
        for _ in range(20)
    ]

    matched_report = evaluator.evaluate(_profile(), matched)
    contrast_report = evaluator.evaluate(_profile(), contrast)

    assert matched_report.sufficient_samples is True
    assert matched_report.passed is True
    assert matched_report.aggregate_score > contrast_report.aggregate_score
    assert matched_report.feature_scores["question_ratio"] == 1
    assert matched_report.feature_scores["emoji_ratio"] == 1
    assert "common_phrases" not in matched_report.feature_scores
    assert contrast_report.passed is False


def test_quality_evaluator_marks_small_or_invalid_candidate_sets() -> None:
    evaluator = StyleQualityEvaluator(
        StyleQualityConfig(min_candidate_messages=3, passing_score=0)
    )
    report = evaluator.evaluate(_profile(), ["好呀？😊", ""])

    assert report.candidate_input_count == 2
    assert report.candidate_message_count == 1
    assert report.sufficient_samples is False
    assert report.passed is False
    assert "empty candidate messages" in report.warnings[0]
    with pytest.raises(TypeError, match="strings or ChatMessage"):
        evaluator.evaluate(_profile(), [object()])  # type: ignore[list-item]

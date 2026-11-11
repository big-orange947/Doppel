"""Source isolation is enforced mechanically; semantic verdicts are not proofs."""

from datetime import UTC, datetime

import pytest

from doppel_memory import ChatMessage, MemoryScope
from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryDraft,
)
from doppel_memory.source_grounding import (
    INSTRUCTIONS,
    GroundingReview,
    SourceGroundedPersonalMemoryAnalyzer,
    SourceGroundedPersonalMemoryAnalyzerV2,
    SourceGroundingConfig,
    _hash,
)


def request():
    return PersonalMemoryAnalysisRequest(
        scope=MemoryScope(user_id="owner-id", agent_id="agent-id"),
        messages=[
            ChatMessage.of(
                "owner",
                "I kept my instrument.",
                datetime(2026, 1, 1, tzinfo=UTC),
                message_id="one",
            ),
            ChatMessage.of(
                "contact",
                "I sold my instrument.",
                datetime(2026, 1, 2, tzinfo=UTC),
                message_id="two",
                sender_id="contact-id",
            ),
        ],
    )


class Analyzer:
    name, version = "fixture.analyzer", "1"

    async def analyze(self, bound):
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content=m.text, subject=m.actor, evidence_ids=[m.identity_key]
                )
                for m in bound.messages
            ]
        )


class Reviewer:
    name, version = "fixture.reviewer", "1"

    def __init__(self, *, bad_at=None):
        self.requests, self.bad_at = [], bad_at

    async def generate(self, generation):
        self.requests.append(generation)
        sources = {s["evidence_id"]: s for s in generation.input["sources"]}
        return {
            "decisions": [
                {
                    "draft_index": d["draft_index"],
                    "verdict": "supported",
                    "confidence": 1,
                    "quotes": [
                        {
                            "evidence_id": d["evidence_ids"][0],
                            "text": "not a source quote"
                            if len(self.requests) == self.bad_at
                            else sources[d["evidence_ids"][0]]["text"],
                        }
                    ],
                }
                for d in generation.input["drafts"]
            ]
        }


async def test_v1_request_shape_and_version_binding_remain_compatible():
    model, config = Reviewer(), SourceGroundingConfig()
    wrapped = SourceGroundedPersonalMemoryAnalyzer(Analyzer(), model, config)
    await wrapped.analyze(request())
    expected_version = (
        "1."
        + _hash(
            {
                "analyzer": [Analyzer.name, Analyzer.version],
                "model": [model.name, model.version],
                "config": config.model_dump(),
                "instructions": INSTRUCTIONS,
                "schema": GroundingReview.model_json_schema(),
            }
        )[:16]
    )
    assert wrapped.version == expected_version
    assert len(model.requests) == 1 and model.requests[0].instructions == INSTRUCTIONS
    assert set(model.requests[0].input) == {"drafts", "sources"}
    assert len(model.requests[0].input["drafts"]) == 2


async def test_v2_isolates_sources_and_derives_frames_without_mutating_claims():
    model, reports = Reviewer(), []
    bound = request()
    before = bound.model_copy(deep=True)
    wrapped = SourceGroundedPersonalMemoryAnalyzerV2(
        Analyzer(), model, observer=reports.append
    )
    result = await wrapped.analyze(bound)
    assert len(model.requests) == 2 and wrapped.version.startswith("2.")
    for index, generation in enumerate(model.requests):
        assert len(generation.input["drafts"]) == len(generation.input["sources"]) == 1
        assert generation.input["drafts"][0]["draft_index"] == index
        assert (
            generation.input["sources"][0]["evidence_id"]
            == bound.messages[index].identity_key
        )
        assert (
            generation.input["speaker_frame"][0]["trusted_subject_id"]
            == ["owner-id", "contact-id"][index]
        )
    assert bound == before
    assert [d.content for d in result.memories] == [m.text for m in bound.messages]
    assert all(
        not d.metadata["source_grounding"]["semantic_support_verified"]
        for d in result.memories
    )
    assert reports[0].reviewed_indices == [0, 1]


@pytest.mark.parametrize("actor,expected", [("agent", "agent-id"), ("system", None)])
async def test_other_source_roles_have_host_frame_not_model_identity(actor, expected):
    bound = request()
    bound = bound.model_copy(
        update={
            "messages": [
                bound.messages[0].model_copy(
                    update={"actor": actor, "sender_id": "untrusted-id"}
                )
            ]
        }
    )
    model = Reviewer()
    await SourceGroundedPersonalMemoryAnalyzerV2(Analyzer(), model).analyze(bound)
    assert model.requests[0].input["speaker_frame"][0]["trusted_subject_id"] == expected


@pytest.mark.parametrize("bad_at", [1, 2])
async def test_bad_quote_stops_before_further_calls_and_publishes_no_partial_review(
    bad_at,
):
    model, reports = Reviewer(bad_at=bad_at), []
    with pytest.raises(ValueError, match="bound to original"):
        await SourceGroundedPersonalMemoryAnalyzerV2(
            Analyzer(), model, observer=reports.append
        ).analyze(request())
    assert len(model.requests) == bad_at and not reports


async def test_all_byte_bounds_are_checked_before_any_review_call():
    bound = request()
    bound = bound.model_copy(
        update={
            "messages": [
                bound.messages[0],
                bound.messages[1].model_copy(update={"text": "x" * 20000}),
            ]
        }
    )
    model = Reviewer()
    wrapped = SourceGroundedPersonalMemoryAnalyzerV2(
        Analyzer(), model, SourceGroundingConfig(max_request_bytes=12000)
    )
    short = (await Analyzer().analyze(bound)).memories[0]
    wrapped._generation(bound, {0: short}, {m.identity_key: m for m in bound.messages})
    with pytest.raises(ValueError, match="no truncation"):
        await wrapped.analyze(bound)
    assert not model.requests


async def test_v2_does_not_allow_supported_review_to_bypass_actor_gate():
    from doppel_memory import PersonalMemoryExtractor, PersonalMemoryExtractorConfig
    from doppel_memory.intelligence import PersonalMemoryEvidenceError

    class Wrong(Analyzer):
        async def analyze(self, bound):
            return PersonalMemoryAnalysis(
                memories=[
                    PersonalMemoryDraft(
                        content="The owner did it.",
                        subject="owner",
                        evidence_ids=["one"],
                    )
                ]
            )

    message = request().messages[0].model_copy(update={"actor": "agent"})
    wrapped = SourceGroundedPersonalMemoryAnalyzerV2(Wrong(), Reviewer())
    with pytest.raises(PersonalMemoryEvidenceError):
        await PersonalMemoryExtractor(
            wrapped,
            PersonalMemoryExtractorConfig(
                owner_target_scope="conversation",
                allowed_source_actors={"owner", "agent"},
            ),
        ).process(request().scope, message)

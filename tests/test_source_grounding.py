from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from doppel_memory import ChatMessage, MemoryScope
from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryDraft,
)
from doppel_memory.source_grounding import (
    SourceGroundedPersonalMemoryAnalyzer,
    SourceGroundingConfig,
)


class Analyzer:
    name, version = "synthetic-analyzer", "1"

    async def analyze(self, request):
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content="Owner completed the change.",
                    memory_type="episode",
                    evidence_ids=["source"],
                )
            ]
        )


class Reviewer:
    name, version = "synthetic-reviewer", "1"

    def __init__(self, **changes):
        self.changes, self.requests = changes, []

    async def generate(self, request):
        self.requests.append(request)
        return {
            "decisions": [
                {
                    "draft_index": 0,
                    "verdict": "contradicted",
                    "confidence": 0.95,
                    "quotes": [
                        {
                            "evidence_id": "source",
                            "text": "I decided to make the change today.",
                        }
                    ],
                    **self.changes,
                }
            ]
        }


def request():
    return PersonalMemoryAnalysisRequest(
        scope=MemoryScope(user_id="u", agent_id="a"),
        messages=[
            ChatMessage(
                message_id="source",
                text="I decided to make the change today.",
                actor="owner",
                at=datetime(2025, 2, 3, tzinfo=UTC),
            )
        ],
    )


async def test_high_confidence_quoted_contradiction_is_not_rewritten_or_promoted():
    reports, model = [], Reviewer()
    bound = request()
    original = bound.model_copy(deep=True)
    result = await SourceGroundedPersonalMemoryAnalyzer(
        Analyzer(), model, observer=reports.append
    ).analyze(bound)
    assert not result.memories and bound == original
    assert (
        reports[0].rejected_indices == [0] and not reports[0].semantic_support_verified
    )
    assert set(model.requests[0].input) == {"drafts", "sources"}
    assert (
        "scope" not in model.requests[0].input
        and "question" not in model.requests[0].input
    )


@pytest.mark.parametrize(
    "verdict,confidence", [("supported", 1), ("uncertain", 1), ("contradicted", 0.5)]
)
async def test_preserve_uncertainty_low_confidence_and_supported_without_confirmation(
    verdict, confidence
):
    model = Reviewer(verdict=verdict, confidence=confidence)
    result = await SourceGroundedPersonalMemoryAnalyzer(Analyzer(), model).analyze(
        request()
    )
    assert (
        len(result.memories) == 1
        and result.memories[0].content == "Owner completed the change."
    )
    assert not result.memories[0].metadata["source_grounding"][
        "semantic_support_verified"
    ]
    assert result.memories[0].confidence == 1


@pytest.mark.parametrize(
    "quote",
    [
        {"evidence_id": "other", "text": "I decided to make the change today."},
        {"evidence_id": "source", "text": "I completed the change."},
        {"evidence_id": "source", "text": " "},
    ],
)
async def test_invalid_source_binding_fails_without_repair_or_retry(quote):
    model = Reviewer(quotes=[quote])
    with pytest.raises(ValueError, match="bound to original"):
        await SourceGroundedPersonalMemoryAnalyzer(Analyzer(), model).analyze(request())
    assert len(model.requests) == 1


@pytest.mark.parametrize("kind", ["missing", "duplicate", "extra", "authority"])
async def test_review_requires_exact_coverage_and_cannot_write_authority(kind):
    class Bad(Reviewer):
        async def generate(self, request):
            result = await super().generate(request)
            if kind == "missing":
                result["decisions"] = []
            elif kind == "duplicate":
                result["decisions"] *= 2
            elif kind == "extra":
                result["decisions"][0]["draft_index"] = 99
            else:
                result["decisions"][0]["state"] = "confirmed"
            return result

    with pytest.raises((ValueError, ValidationError)):
        await SourceGroundedPersonalMemoryAnalyzer(Analyzer(), Bad()).analyze(request())


async def test_unknown_evidence_ids_are_left_for_existing_miner_policy():
    class Unknown(Analyzer):
        async def analyze(self, request):
            result = await super().analyze(request)
            return PersonalMemoryAnalysis(
                memories=[
                    result.memories[0].model_copy(update={"evidence_ids": ["unknown"]})
                ]
            )

    model = Reviewer()
    result = await SourceGroundedPersonalMemoryAnalyzer(Unknown(), model).analyze(
        request()
    )
    assert result.memories[0].evidence_ids == ["unknown"] and not model.requests


async def test_byte_limit_is_a_failure_not_truncation_or_new_call():
    r = request()
    r.messages[0] = r.messages[0].model_copy(update={"text": "x" * 5000})
    model = Reviewer()
    with pytest.raises(ValueError, match="no truncation"):
        await SourceGroundedPersonalMemoryAnalyzer(
            Analyzer(), model, SourceGroundingConfig(max_request_bytes=1000)
        ).analyze(r)
    assert not model.requests


async def test_provider_failure_propagates_once_without_fallback():
    class Failing(Reviewer):
        async def generate(self, request):
            self.requests.append(request)
            raise RuntimeError("offline failure")

    model = Failing()
    with pytest.raises(RuntimeError):
        await SourceGroundedPersonalMemoryAnalyzer(Analyzer(), model).analyze(request())
    assert len(model.requests) == 1

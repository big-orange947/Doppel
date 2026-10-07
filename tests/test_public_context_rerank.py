"""No GPU/network: fake scorers and strict production score validation."""

from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from doppel_memory.models import FactAuthority, MemoryScope, RecallResult
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    PersonalMemoryRerankScore,
)


class Provider:
    name, version = "fake-local-only", "1"
    mode = "valid"

    async def rerank(self, request):
        self.request = request
        if self.mode == "error":
            raise ValueError("SECRET_MUST_NOT_SURFACE")
        if self.mode == "duplicate":
            return [
                PersonalMemoryRerankScore(item_id=request.items[0].item_id, score=0.5)
            ] * len(request.items)
        return [
            PersonalMemoryRerankScore(
                item_id=item.item_id, score=(i + 1) / len(request.items)
            )
            for i, item in enumerate(request.items)
        ]


def candidates():
    scope = MemoryScope(user_id="owner", agent_id="agent")
    return [
        RecallResult(
            scope=scope,
            memory_id=f"id-{i}",
            fact=f"text {i}",
            raw_text=f" original {i} ",
            authority=FactAuthority.AGENT_OUTPUT,
        )
        for i in range(2)
    ]


@pytest.mark.asyncio
async def test_reorder_only_content_opaque_ids_and_empty_window() -> None:
    provider = Provider()
    reranker = StrictContextReranker(provider)
    source = candidates()
    result = await reranker.rerank("question", source, limit=2)
    assert [hit.memory_id for hit in result] == ["id-1", "id-0"]
    assert result[0].authority == FactAuthority.AGENT_OUTPUT
    assert result[0].raw_text == source[1].raw_text
    assert [item.content for item in provider.request.items] == [
        "original 0",
        "original 1",
    ]
    assert "owner" not in provider.request.model_dump_json()
    assert reranker.last_summary.status == "completed"
    assert not await reranker.rerank("question", [], limit=2)
    assert reranker.last_summary.status == "not_run"


@pytest.mark.parametrize("mode", ["error", "duplicate"])
@pytest.mark.asyncio
async def test_bad_provider_cannot_masquerade_as_successful_reranking(mode) -> None:
    provider = Provider()
    provider.mode = mode
    with pytest.raises(RuntimeError, match="unavailable") as error:
        await StrictContextReranker(provider).rerank("question", candidates(), limit=2)
    assert "SECRET" not in str(error.value)


@pytest.mark.asyncio
async def test_input_bound_fails_instead_of_silent_base_order() -> None:
    reranker = StrictContextReranker(
        Provider(), PersonalMemoryRerankConfig(max_candidates=1)
    )
    with pytest.raises(RuntimeError, match="limit_exceeded"):
        await reranker.rerank("question", candidates(), limit=2)


@pytest.mark.asyncio
async def test_local_model_reports_truncation_and_single_sigmoid(
    tmp_path: Path,
) -> None:
    class FakeEncoder:
        def tokenizer(self, queries, texts, **kwargs):
            assert kwargs["truncation"] is False
            return {"length": [2, 9]}

        def predict(self, pairs, **kwargs):
            assert kwargs["activation_fn"](123) == 123
            assert pairs == [("question", "short"), ("question", "long")]
            return [0, -1]

    with patch("benchmarks.public_context_rerank.version", return_value="test"):
        provider = LocalContextCrossEncoder(tmp_path, max_length=4)
    provider._model = FakeEncoder()
    scores = await provider.rerank(
        PersonalMemoryRerankRequest(
            question="question",
            items=[
                PersonalMemoryRerankItem(item_id="a", content="short"),
                PersonalMemoryRerankItem(item_id="b", content="long"),
            ],
        )
    )
    assert scores[0].score == 0.5
    assert scores[1].score == pytest.approx(0.268941421)
    assert provider.report()["truncated_pairs"] == 1
    assert provider.report()["pairs_scored"] == 2

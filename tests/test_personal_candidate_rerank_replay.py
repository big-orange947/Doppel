from pathlib import Path

import pytest

from benchmarks.personal_candidate_rerank_replay import run_replay
from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from doppel_memory import RelationRerankScore

DATASET = Path(__file__).resolve().parents[1] / "benchmarks/datasets/personal-relation-ablation-zh-v1.json"


class FakeReranker:
    name = "tests.fake-memory-reranker"
    version = "1"

    def __init__(self, *, invalid: bool = False):
        self.invalid = invalid
        self.requests = []

    async def rerank(self, request):
        self.requests.append(request)
        if self.invalid:
            return []
        return [RelationRerankScore(item_id=item.item_id, score=index / 10)
                for index, item in enumerate(request.items)]


def report(dataset, profile="profile"):
    fixture_ids = [item.memory_id for item in dataset.fixtures[:2]]
    return {
        "dataset": {"fingerprint": dataset.fingerprint},
        "candidate_fusion": "union",
        "cases": [{"query_id": query.query_id, "profile": profile,
                   "hits": fixture_ids, "error": ""}
                  for query in dataset.queries],
    }


@pytest.mark.asyncio
async def test_replay_reorders_only_and_sends_opaque_ids():
    dataset = load_ablation_dataset(DATASET)
    reranker = FakeReranker()
    result = await run_replay(dataset, report(dataset), reranker, profile="profile",
                              external_llm_calls=0)
    mode = result["modes"]["raw_question"]
    assert mode["candidate_set_changed_count"] == 0
    assert all(case["after"] == list(reversed(case["before"]))
               for case in mode["cases"])
    actual_ids = {item.memory_id for item in dataset.fixtures}
    assert all(item.item_id.startswith("item_") and item.item_id not in actual_ids
               for request in reranker.requests for item in request.items)
    assert result["external_llm_calls"] == 0


@pytest.mark.asyncio
async def test_replay_rejects_missing_scores_and_wrong_dataset():
    dataset = load_ablation_dataset(DATASET)
    with pytest.raises(ValueError, match="exactly one score"):
        await run_replay(dataset, report(dataset), FakeReranker(invalid=True),
                         profile="profile")
    wrong = report(dataset)
    wrong["dataset"]["fingerprint"] = "wrong"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        await run_replay(dataset, wrong, FakeReranker(), profile="profile")


@pytest.mark.asyncio
async def test_planner_context_is_an_explicit_separate_arm():
    dataset = load_ablation_dataset(DATASET)
    reranker = FakeReranker()
    drafts = {query.query_id: {"entity_mentions": ["entity"],
                              "relation_hints": ["hint"],
                              "relation_types": ["TYPE"]}
              for query in dataset.queries}
    result = await run_replay(dataset, report(dataset), reranker, profile="profile",
                              drafts=drafts,
                              modes=("raw_question", "planner_context"))
    assert set(result["modes"]) == {"raw_question", "planner_context"}
    assert any("Candidate relation types: TYPE" in request.query_text
               for request in reranker.requests)

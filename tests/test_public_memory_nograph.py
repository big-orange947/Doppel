from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_nograph as runner
from benchmarks.public_memory_answer_comparison import AnswerRow
from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_reader_v2 import build_request
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import MemoryRecord, MemoryScope, RecallResult
from tests.test_public_memory_fresh_query import query_plan


def plan(ordinal=6, profile=runner.PROFILES[0]):
    _, _, cohort, base, _ = query_plan()
    from benchmarks.public_memory_fresh_ingest import prepare_stage
    from tests.test_public_memory_fresh_ingest import SHA, bound

    raw, manifest, bound_cohort = bound()
    cases, _ = prepare_stage(raw, manifest, bound_cohort, source_sha=SHA)
    return runner.make_plan(
        {},
        cohort,
        cases[0],
        ordinal,
        {},
        "corpus",
        {},
        SimpleNamespace(report=lambda: base["reranker"]),
        profile,
    )


@pytest.mark.parametrize("ordinal", runner.ORDINALS)
@pytest.mark.parametrize("profile", runner.PROFILES)
def test_three_calls_per_profile_and_no_graph_gate(ordinal, profile):
    value = plan(ordinal, profile)
    assert sum(x["max_calls"] for x in value["stages"].values()) == 3
    assert set(value["stages"]) == {"reader", "task_judge", "citation_judge"}
    assert (
        value["graph_calls"]
        == value["planner_calls"]
        == value["source_writer_calls"]
        == 0
    )
    assert "graph_snapshot" not in value and "relation_definitions_sha256" not in value
    assert value["retrieval"]["candidate_limit"] == 80
    assert value["retrieval"]["context_byte_limit"] == 24_000
    assert value["profile_execution_order"] == list(
        runner.PROFILES if ordinal % 2 else reversed(runner.PROFILES)
    )
    assert "PRIVATE GOLD" not in str(value)


@pytest.mark.parametrize(
    "ordinal,profile",
    [(5, runner.PROFILES[0]), (11, runner.PROFILES[0]), (6, "full_high_config")],
)
def test_other_experiments_cannot_be_silently_relabelled(ordinal, profile):
    with pytest.raises(ValueError):
        plan(ordinal, profile)


def test_reusing_answer_helper_does_not_show_profile_or_gold_to_reader():
    from benchmarks.public_longmemeval import prepare_case
    from benchmarks.public_memory_fresh_cohort import NAMESPACE
    from tests.test_public_memory_fresh_cohort import dataset

    case = prepare_case(dataset()[0], dataset_namespace=NAMESPACE)
    inputs = []
    for profile in runner.PROFILES:
        row = AnswerRow(
            0, case.scoring.case_id, profile, case.runtime, case.scoring, ()
        )
        inputs.append(build_request(row).model_dump(mode="json"))
    assert inputs[0] == inputs[1]
    assert "PRIVATE GOLD" not in str(inputs)
    assert all(p not in str(inputs) for p in runner.PROFILES)


def test_replay_preserves_original_bytes_and_checks_semantics(tmp_path):
    path = tmp_path / "receipt.json"
    row = {
        "status": "complete",
        "reader": {"answer": "original"},
        "usage": {"calls": 3},
    }
    save(path, row)
    before = path.read_bytes()
    replay = copy.deepcopy(row)
    replay["usage"] = {"calls": 0}
    runner.preserve_row(path, replay, cache_only=True)
    assert path.read_bytes() == before
    replay["reader"]["answer"] = "changed"
    with pytest.raises(ValueError):
        runner.preserve_row(path, replay, cache_only=True)
    assert path.read_bytes() == before
    with pytest.raises(FileExistsError):
        runner.preserve_row(path, row, cache_only=False)


@pytest.mark.asyncio
async def test_hybrid_uses_existing_bm25_and_source_text_not_index_text(monkeypatch):
    scope = MemoryScope(user_id="owner", agent_id="agent")
    other = MemoryScope(user_id="other", agent_id="agent")
    store = InMemoryStore()
    records = {}
    for identity, text in [("one", "rare instrument"), ("two", "unrelated words")]:
        record = MemoryRecord(memory_id=identity, content=text, scope=scope)
        records[identity] = (await store.put(record)).record
    await store.put(
        MemoryRecord(memory_id="foreign", content="rare instrument", scope=other)
    )

    class Vector:
        _store = store

        async def search(self, query, scopes, **kwargs):
            assert scopes == [scope]
            return [
                RecallResult(
                    memory_id=k,
                    scope=scope,
                    fact="UNTRUSTED INDEX TEXT",
                    similarity=0.9,
                )
                for k in ("two", "one")
            ]

    class Reranker:
        last_summary = None

        def __init__(self, provider):
            pass

        async def rerank(self, query, candidates, limit):
            assert candidates[0].memory_id == "one"  # BM25 contributes to RRF.
            assert all(c.fact == records[c.memory_id].content for c in candidates)
            assert all(c.scope == scope for c in candidates)
            return candidates[:limit]

    monkeypatch.setattr(runner, "StrictContextReranker", Reranker)
    monkeypatch.setattr(
        runner,
        "context_item",
        lambda r, *args: {
            "memory_id": r.memory_id,
            "scope_key": r.scope.scope_key,
            "channel": "memory",
            "text": r.content,
        },
    )
    result = await runner.retrieve(
        SimpleNamespace(query=SimpleNamespace(query="rare")),
        scope,
        records,
        {},
        Vector(),
        SimpleNamespace(report=dict),
        plan(),
    )
    assert result["lexical_candidates_returned"] == 1
    assert result["fused_candidates_returned"] == 2
    assert result["context"][0]["memory_id"] == "one"
    assert "foreign" not in str(result)


@pytest.mark.asyncio
async def test_hybrid_never_silently_downgrades_when_vector_fails():
    from doppel_memory.vector import SemanticIndexUnavailableError

    class Vector:
        _store = InMemoryStore()

        async def search(self, *args, **kwargs):
            raise SemanticIndexUnavailableError("test outage")

    with pytest.raises(SemanticIndexUnavailableError):
        await runner.retrieve(
            SimpleNamespace(query=SimpleNamespace(query="generic")),
            MemoryScope(user_id="a", agent_id="b"),
            {"one": SimpleNamespace()},
            {},
            Vector(),
            None,
            plan(),
        )

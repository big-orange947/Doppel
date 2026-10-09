from types import SimpleNamespace

import pytest

pytest.importorskip("graphiti_core")

from benchmarks.public_memory_graph_probe import probe
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import Actor, MemoryRecord, MemoryScope


def fixture():
    scope = MemoryScope(user_id="owner", agent_id="agent")
    other = MemoryScope(user_id="other", agent_id="agent")
    record = MemoryRecord(
        memory_id="memory",
        scope=scope,
        content="Stored source, not a benchmark answer",
        metadata={"subject": Actor.OWNER, "subject_id": "owner"},
    )
    target = {
        "memory_id": record.memory_id,
        "scope_key": scope.scope_key,
        "source_version": record.version,
        "fingerprint": memory_index_fingerprint(record),
        "episode_id": "episode",
    }
    return record, other, {"records": [target]}


class Driver:
    async def execute_query(self, query, **parameters):
        assert "MATCH" in query and "RETURN" in query
        assert parameters["episode"] == "episode"
        return (
            [
                {
                    "edge_id": "edge",
                    "relation_type": "OWNS",
                    "fact": "Source-derived edge fact",
                    "source_name": "Source entity",
                }
            ],
            None,
            None,
        )


class Index:
    def __init__(self, record, defect=""):
        self.record = record
        self.defect = defect
        self.requests = []

    async def search_relations(self, request, scopes, **kwargs):
        self.requests.append(request)
        assert request.query_text == "Source-derived edge fact"
        assert request.entity_mentions == ["Source entity"]
        hit = SimpleNamespace(
            memory_id=self.record.memory_id,
            scope=self.record.scope,
            edge_id="edge",
            episode_ids=[] if self.defect == "provenance" else ["episode"],
        )
        if request.subject_id.endswith(":mismatch"):
            return [hit] if self.defect == "subject" else []
        if scopes != [self.record.scope]:
            return [hit] if self.defect == "scope" else []
        return [] if self.defect == "relation" else [hit]

    async def search_relation_paths(self, request, scopes, **kwargs):
        assert request.steps[0].relation_types == ["OWNS"]
        return (
            []
            if self.defect == "path"
            else [
                SimpleNamespace(
                    scope=self.record.scope,
                    supporting_memory_ids=[self.record.memory_id],
                    hops=[SimpleNamespace(edge_id="edge", episode_ids=["episode"])],
                )
            ]
        )


@pytest.mark.asyncio
async def test_source_probe_is_not_a_natural_query_or_accuracy_measurement():
    record, other, plan = fixture()
    report = await probe(
        Index(record), Driver(), {"memory": record}, plan, [record.scope, other]
    )
    assert report["status"] == "complete"
    assert report["probe_count"] == 1
    assert not report["qa_metrics_available"]
    assert not report["natural_query_performance_measured"]
    assert not report["graph_fact_correctness_measured"]
    assert report["provider_calls"] == report["data_writes"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["provenance", "subject", "scope", "relation", "path"]
)
async def test_bad_provenance_isolation_or_missing_paths_fail(defect):
    record, other, plan = fixture()
    report = await probe(
        Index(record, defect), Driver(), {"memory": record}, plan, [record.scope, other]
    )
    assert report["status"] == "failed"
    assert not report["checks"][0]["ok"]


@pytest.mark.asyncio
async def test_changed_source_fails_before_graph_queries():
    record, other, plan = fixture()
    with pytest.raises(ValueError, match="source differs"):
        await probe(
            Index(record),
            Driver(),
            {"memory": record.model_copy(update={"content": "changed"})},
            plan,
            [record.scope, other],
        )


@pytest.mark.asyncio
async def test_no_rich_edge_is_not_a_success():
    class NoRichEdges:
        async def execute_query(self, *args, **kwargs):
            return [], None, None

    record, other, plan = fixture()
    report = await probe(
        Index(record), NoRichEdges(), {"memory": record}, plan, [record.scope, other]
    )
    assert report["status"] == "failed"
    assert report["probe_count"] == 0

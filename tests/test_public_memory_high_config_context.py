from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from benchmarks.public_memory_graph_schema import (
    schema_request,
    validate_definitions,
)
from benchmarks.public_memory_high_config_context import (
    LocalRelationCrossEncoder,
    pack_channels,
)
from doppel_memory.personal_rerank import PersonalMemoryRerankScore
from doppel_memory.relation import RelationPathExploreQuery, RelationRerankItem


def item(identity, text="literal original"):
    return {"memory_id": identity, "text": text, "role": "assistant"}


def test_ontology_preserved_above_old_limit_and_still_bounded():
    query = RelationPathExploreQuery(
        query_text="query",
        entity_mentions=["entity"],
        subject="owner",
        subject_id="owner",
        allowed_relation_types=[f"TYPE_{i}" for i in range(142)],
    )
    assert len(query.allowed_relation_types) == 142
    with pytest.raises(ValidationError):
        RelationPathExploreQuery(
            query_text="query",
            entity_mentions=["entity"],
            subject="owner",
            subject_id="owner",
            allowed_relation_types=[f"TYPE_{i}" for i in range(513)],
        )


def test_schema_request_names_only_and_exact_name_binding():
    request = schema_request(["OWNS", "STORED_ON"])
    assert request.input == {"relation_names": ["OWNS", "STORED_ON"]}
    definitions = [
        {
            "name": n,
            "description": "generic meaning",
            "source_description": "source role",
            "target_description": "target role",
        }
        for n in ["STORED_ON", "OWNS"]
    ]
    result = validate_definitions(["OWNS", "STORED_ON"], {"definitions": definitions})
    assert [d["name"] for d in result] == ["OWNS", "STORED_ON"]
    for bad in [definitions[:1], definitions + definitions[:1]]:
        with pytest.raises(ValueError):
            validate_definitions(["OWNS", "STORED_ON"], {"definitions": bad})


def test_fixed_channels_preserve_assistant_attribution_and_deduplicate():
    channels = {
        "memory": [item("m1"), item("m2")],
        "raw": [item("r1"), item("r2")],
        "backing": [item("r1"), item("b2")],
    }
    selected, audit = pack_channels(channels, item_limit=4)
    assert [i["memory_id"] for i in selected] == ["m1", "r1", "m2", "r2"]
    assert selected[1]["role"] == "assistant"
    assert any(o["decision"] == "duplicate" for o in audit["observations"])
    assert audit["encoded_bytes"] <= audit["byte_limit"]
    assert audit["text_truncated"] is False


def test_oversized_whole_item_skipped_without_modification():
    large, small = item("large", "x" * 1000), item("small")
    selected, audit = pack_channels({"memory": [large, small]}, byte_limit=200)
    assert selected == [small]
    assert len(large["text"]) == 1000
    assert audit["observations"][0]["decision"] == "byte_budget"


@pytest.mark.asyncio
async def test_relation_adapter_no_type_hints_or_authority_into_scorer():
    requests = []

    class Scorer:
        name, version = "local", "1"

        async def rerank(self, request):
            requests.append(request)
            return [PersonalMemoryRerankScore(item_id="opaque", score=0.8)]

    output = await LocalRelationCrossEncoder(Scorer()).rerank(
        SimpleNamespace(
            query_text="question",
            relation_hints=["private hint"],
            items=[
                RelationRerankItem(item_id="opaque", relation_type="REL", fact="fact")
            ],
        )
    )
    assert requests[0].model_dump() == {
        "question": "question",
        "items": [{"item_id": "opaque", "content": "fact"}],
    }
    assert output[0].score == 0.8

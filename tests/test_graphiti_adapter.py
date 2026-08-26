"""Optional Graphiti adapter construction contract."""

import pytest

pytest.importorskip("graphiti_core")

from graphiti_core import Graphiti

from doppel_memory.graphiti_store import GraphitiMemoryStore
from doppel_memory.models import MemoryScope


async def test_graphiti_029_adapter_constructs_without_connecting() -> None:
    store = GraphitiMemoryStore(llm_api_key="test-key")
    graphiti = store._build_graphiti()
    assert isinstance(graphiti, Graphiti)
    await graphiti.close()


async def test_graphiti_unsupported_lifecycle_is_explicit() -> None:
    store = GraphitiMemoryStore(llm_api_key="test-key")
    scope = MemoryScope(user_id="u", agent_id="bot")
    with pytest.raises(NotImplementedError):
        await store.get(scope, "memory-id")
    with pytest.raises(NotImplementedError):
        await store.forget(scope, "memory-id")

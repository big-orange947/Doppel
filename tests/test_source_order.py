from __future__ import annotations

import pytest

from doppel_memory.models import MemoryScope
from doppel_memory.source_order import ExplicitSourceOrderIndex, SourcePosition


def positions(scope, ordinals=(0, 1, 3), session="session"):
    return [
        SourcePosition(
            scope_key=scope.scope_key,
            session_id=session,
            ordinal=n,
            memory_id=f"m-{n}",
            evidence_id=f"e-{n}",
        )
        for n in ordinals
    ]


@pytest.mark.asyncio
async def test_explicit_gaps_session_scope_and_detached_results():
    scope = MemoryScope(user_id="owner", agent_id="a")
    other = MemoryScope(user_id="other", agent_id="a")
    values = positions(scope)
    index = ExplicitSourceOrderIndex(
        [*values, *positions(other), *positions(scope, (2,), "another-session")]
    )
    anchor = await index.locate(scope, "m-1")
    assert anchor.ordinal == 1
    assert [
        p.ordinal for p in await index.neighbors(scope, anchor, before=1, after=1)
    ] == [0]
    assert (await index.locate(other, "m-1")).scope_key == other.scope_key


@pytest.mark.asyncio
async def test_gap_not_bridged_and_cross_scope_not_read():
    scope = MemoryScope(user_id="owner", agent_id="a")
    other = MemoryScope(user_id="other", agent_id="a")
    index = ExplicitSourceOrderIndex(positions(scope))
    anchor = await index.locate(scope, "m-1")
    nearby = await index.neighbors(scope, anchor, before=1, after=1)
    assert [p.ordinal for p in nearby] == [0]
    assert await index.locate(other, "m-1") is None
    with pytest.raises(ValueError):
        await index.neighbors(other, anchor, before=1, after=1)
    assert (await index.locate(scope, "m-1")) is not anchor


@pytest.mark.parametrize("bad", [True, -1, 1.5])
def test_strict_ordinals(bad):
    with pytest.raises(ValueError):
        SourcePosition(
            scope_key="s", session_id="c", ordinal=bad, memory_id="m", evidence_id="e"
        )


def test_duplicate_source_ids_ordinals_and_bypassed_models_rejected():
    scope = MemoryScope(user_id="owner", agent_id="a")
    value = positions(scope, (0,))[0]
    with pytest.raises(ValueError):
        ExplicitSourceOrderIndex([value, value])
    with pytest.raises(ValueError):
        ExplicitSourceOrderIndex(
            [value, value.model_copy(update={"memory_id": "another"})]
        )
    with pytest.raises(ValueError):
        ExplicitSourceOrderIndex([value.model_copy(update={"ordinal": -1})])

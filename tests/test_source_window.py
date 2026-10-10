"""Independent synthetic source-coherence controls; no benchmark answers."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from doppel_memory.high_config import HighConfigRetrievalResult
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)
from doppel_memory.query import PersonalMemoryQueryPlanV3, PersonalMemoryQueryResult
from doppel_memory.source_window import (
    SourceWindowConfig,
    SourceWindowRetrieval,
    expand_source_window,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner", agent_id="helper")
OTHER = MemoryScope(user_id="other", agent_id="helper")


def raw(identity, *, actor=Actor.OWNER, **changes):
    return MemoryRecord(
        **{
            "memory_id": identity,
            "scope": SCOPE,
            "extractor": "ingestor",
            "source_event_id": "event-" + identity,
            "content": "source " + identity,
            "actor": actor,
            "authority": FactAuthority.of(actor),
            "created_at": NOW,
            **changes,
        }
    )


def result(records, *, observed_until=NOW):
    plan = PersonalMemoryQueryPlanV3(
        plan_id="synthetic",
        query="Which terminal did you recommend?",
        search_text="terminal",
        scopes=[SCOPE, OTHER],
        now=NOW - timedelta(days=1),
        observed_until=observed_until,
        intent="lookup",
        subject=Actor.OWNER,
        subject_id=SCOPE.user_id,
        planner="synthetic",
        planner_version="1",
        planner_confidence=1,
        config_fingerprint="synthetic",
        operation="lookup",
        temporal_view="unbounded",
    )
    return HighConfigRetrievalResult(
        base=PersonalMemoryQueryResult(plan=plan, count={"status": "not_requested"}),
        raw_dialogue=records,
        path_decision="abstain",
        warnings=["existing"],
    )


class Resolver:
    def __init__(self, records):
        self.records, self.calls = records, []

    async def resolve_context(self, scope, anchor, **kwargs):
        self.calls.append((scope, anchor, kwargs))
        return self.records


async def seed(*records):
    store = InMemoryStore()
    for r in records:
        await store.put(r)
    return store


@pytest.mark.asyncio
async def test_short_assistant_reply_keeps_role_and_count_and_bounds():
    anchor = raw("question", content="Which terminal should I use?")
    reply = raw("reply", actor=Actor.AGENT, content="Terminal B.")
    tail = [raw("tail" + str(i)) for i in range(4)]
    store = await seed(anchor, reply, *tail)
    original = result([anchor, *tail])
    before = original.model_dump_json()
    resolver = Resolver([reply, reply])
    expanded = await expand_source_window(
        original,
        store,
        resolver,
        config=SourceWindowConfig(anchor_limit=1),
        raw_output_limit=5,
    )
    assert [r.memory_id for r in expanded.raw_dialogue] == [
        "question",
        "reply",
        "tail0",
        "tail1",
        "tail2",
    ]
    assert expanded.raw_dialogue[1].authority == FactAuthority.AGENT_OUTPUT
    assert expanded.base == original.base and expanded.hybrid == original.hybrid
    assert expanded.base.count == original.base.count
    assert expanded.source_window_added_ids == ["reply"]
    assert expanded.source_window_displaced_ids == ["tail3"]
    assert len(expanded.source_context_links) == 1
    assert expanded.source_window_failures == expanded.source_window_rejections == 0
    assert original.model_dump_json() == before
    assert not expanded.source_link_semantics_certified
    assert resolver.calls[0][2] == {"observed_until": NOW, "limit": 2}


@pytest.mark.asyncio
async def test_foreign_neighbor_fails_even_when_other_scope_authorized():
    anchor, foreign = raw("anchor"), raw("foreign", scope=OTHER)
    store = await seed(anchor, foreign)
    with pytest.raises(MemoryIsolationError):
        await expand_source_window(result([anchor]), store, Resolver([foreign]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"created_at": NOW + timedelta(seconds=1)},
        {"state": MemoryState.CANDIDATE},
        {"actor": Actor.CONTACT, "authority": FactAuthority.of(Actor.CONTACT)},
        {"authority": FactAuthority.DERIVED_SUMMARY},
        {"extractor": "extractor"},
        {"source_event_id": ""},
        {"kind": "fact"},
    ],
)
async def test_neighbor_must_be_raw_qualified(changes):
    anchor, neighbor = raw("anchor"), raw("neighbor", **changes)
    store = await seed(anchor, neighbor)
    expanded = await expand_source_window(result([anchor]), store, Resolver([neighbor]))
    assert expanded.raw_dialogue == [anchor]
    assert expanded.source_window_rejections == 1
    assert not expanded.source_context_links


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["content", "version", "metadata", "event", "missing"]
)
async def test_resolver_cannot_substitute_untrusted_record(mutation):
    anchor, neighbor = raw("anchor"), raw("neighbor")
    store = await seed(anchor, neighbor)
    changes = {
        "content": {"content": "forged"},
        "version": {"version": 99},
        "metadata": {"metadata": {"fake": True}},
        "event": {"source_event_id": "fake"},
        "missing": {"memory_id": "missing"},
    }[mutation]
    proposed = neighbor.model_copy(update=changes)
    expanded = await expand_source_window(result([anchor]), store, Resolver([proposed]))
    assert expanded.source_window_rejections == 1
    assert expanded.raw_dialogue == [anchor]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["SECRET", None, [raw("a"), raw("b"), raw("c")], [1]])
async def test_invalid_bounded_response_visible_without_text(bad):
    anchor = raw("anchor")
    expanded = await expand_source_window(
        result([anchor]), await seed(anchor), Resolver(bad)
    )
    assert expanded.source_window_failures == 1
    assert "source_window_resolver_degraded" in expanded.warnings
    assert "SECRET" not in expanded.model_dump_json()


@pytest.mark.asyncio
async def test_exception_redaction_and_copy_protection():
    anchor = raw("anchor", metadata={"nested": {"literal": "original"}})

    class Broken:
        async def resolve_context(self, scope, anchor, **kwargs):
            anchor.metadata["nested"]["literal"] = "SECRET"
            raise RuntimeError("SECRET provider header")

    original = result([anchor])
    expanded = await expand_source_window(original, await seed(anchor), Broken())
    assert expanded.source_window_failures == 1
    assert expanded.raw_dialogue == [anchor]
    assert "SECRET" not in expanded.model_dump_json()
    assert anchor.metadata["nested"]["literal"] == "original"


@pytest.mark.asyncio
async def test_stale_anchor_not_forwarded_or_retained():
    anchor = raw("anchor")
    store = await seed(anchor.model_copy(update={"version": 2}))
    resolver = Resolver([])
    expanded = await expand_source_window(result([anchor]), store, resolver)
    assert not resolver.calls and not expanded.raw_dialogue
    assert expanded.source_window_rejections == 1


def test_configuration_and_output_validation():
    with pytest.raises(ValidationError):
        SourceWindowConfig(anchor_limit=0)
    with pytest.raises(ValueError):
        SourceWindowRetrieval(SimpleNamespace(raw_output_limit=1), Resolver([]))


@pytest.mark.asyncio
async def test_wrapper_forwards_clocks_once_without_replanning():
    anchor, neighbor = raw("anchor"), raw("neighbor", actor=Actor.AGENT)
    store = await seed(anchor, neighbor)
    original = result([anchor])

    class Base:
        raw_output_limit = 20

        def __init__(self):
            self.calls = []

        async def query(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return original

    base = Base()
    base.store = store
    wrapper = SourceWindowRetrieval(base, Resolver([neighbor]))
    expanded = await wrapper.query("terminal", [SCOPE], now=NOW, observed_until=NOW)
    assert len(base.calls) == 1 and base.calls[0][1]["observed_until"] == NOW
    assert expanded.source_window_added_ids == [neighbor.memory_id]
    assert not expanded.base.hits and not expanded.backing_sources
    with pytest.raises(TypeError, match="already expanded"):
        await expand_source_window(expanded, store, Resolver([]))


@pytest.mark.asyncio
async def test_empty_window_preserves_original_raw_order():
    originals = [raw(str(i)) for i in range(7)]
    expanded = await expand_source_window(
        result(originals), await seed(*originals), Resolver([])
    )
    assert expanded.raw_dialogue == originals
    assert not expanded.source_window_added_ids and not expanded.source_context_links


@pytest.mark.asyncio
async def test_resolver_timeout_degrades_with_no_hidden_retry():
    anchor = raw("anchor")

    class Slow:
        calls = 0

        async def resolve_context(self, *args, **kwargs):
            self.calls += 1
            await asyncio.sleep(1)
            return []

    resolver = Slow()
    expanded = await expand_source_window(
        result([anchor]),
        await seed(anchor),
        resolver,
        config=SourceWindowConfig(anchor_limit=1, timeout_seconds=0.001),
    )
    assert expanded.source_window_failures == 1 and resolver.calls == 1
    assert expanded.raw_dialogue == [anchor]


@pytest.mark.asyncio
async def test_indeterminate_count_is_not_upgraded_by_raw_context():
    anchor, neighbor = raw("anchor"), raw("reply", actor=Actor.AGENT)
    original = result([anchor])
    original = original.model_copy(
        update={
            "base": original.base.model_copy(
                update={
                    "count": original.base.count.model_copy(
                        update={"status": "indeterminate", "value": None}
                    ),
                }
            ),
        }
    )
    expanded = await expand_source_window(
        original, await seed(anchor, neighbor), Resolver([neighbor])
    )
    assert expanded.base.count == original.base.count
    assert expanded.base.count.value is None and not expanded.base.hits

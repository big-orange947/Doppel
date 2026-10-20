from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from doppel_memory import InMemoryStore, MemoryRecord, MemoryScope
from doppel_memory.query import (
    PersonalMemoryQueryDraftV2,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryPlanV2,
)
from doppel_memory.query_feedback import (
    CandidateAwarePersonalMemoryQuery,
    CandidateFeedbackConfig,
    QuantityRoutingDecision,
)

NOW = datetime(2025, 3, 10, tzinfo=UTC)
SCOPE = MemoryScope(user_id="owner", agent_id="agent")


def record(identity, kind="state", **changes):
    data: dict[str, Any] = dict(  # noqa: C408 - keyword overrides for fixtures
        memory_id=identity,
        scope=SCOPE,
        content="The owner reports a total of seven completed units.",
        actor="owner",
        authority="human_self",
        state="candidate",
        created_at=NOW,
        updated_at=NOW,
        tags=["personal-memory"],
        metadata={
            "subject": "owner",
            "subject_id": SCOPE.user_id,
            "personal_memory_type": kind,
            "temporal_status": "historical",
            "event_key": identity if kind == "episode" else "",
            "evidence": [{"evidence_id": "source-" + identity}],
        },
    )
    data.update(changes)
    return MemoryRecord(**data)


class Planner:
    name, version = "synthetic-initial", "1"

    async def plan(self, request):
        return PersonalMemoryQueryDraftV2(
            operation="count",
            memory_types=["episode"],
            temporal_view="interval",
            time_from=NOW - timedelta(days=30),
            time_to=NOW,
        )


class Model:
    name, version = "synthetic-feedback", "1"

    def __init__(self, route="reported_quantity", support=None, confidence=1):
        self.route, self.support, self.confidence = route, support, confidence
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return {
            "route": self.route,
            "supporting_memory_ids": self.support
            if self.support is not None
            else ["total"],
            "confidence": self.confidence,
        }


async def setup(*records):
    store = InMemoryStore()
    for r in records:
        await store.put(r)
    engine = PersonalMemoryQueryEngine(store)
    plan = await engine.plan(
        Planner(), "How many units?", [SCOPE], now=NOW, observed_until=NOW
    )
    assert isinstance(plan, PersonalMemoryQueryPlanV2)
    return store, engine, plan


async def test_reported_total_becomes_lookup_without_counting_its_source_messages():
    r = record("total")
    store, engine, plan = await setup(r)
    before = plan.model_dump()
    model = Model()
    result = await CandidateAwarePersonalMemoryQuery(engine, model).execute(
        plan, trace_limit=50
    )
    assert not result.original.hits
    assert isinstance(result.result.plan, PersonalMemoryQueryPlanV2)
    assert result.applied and result.result.plan.operation == "lookup"
    assert [h.record.memory_id for h in result.result.hits] == ["total"]
    assert (
        result.result.count.status == "not_requested"
        and result.result.count.value is None
    )
    assert plan.model_dump() == before
    assert await store.get(SCOPE, "total") == r
    final = result.result.plan.model_dump()
    for field in (
        "query",
        "scopes",
        "subject",
        "subject_id",
        "now",
        "observed_until",
        "temporal_view",
        "time_from",
        "time_to",
        "topic_keys",
        "temporal_statuses",
        "relation_types",
        "config_fingerprint",
    ):
        assert final[field] == before[field]
    assert model.requests[0].input["candidate_pool_complete_history"] is False


@pytest.mark.parametrize(
    "route,confidence,support",
    [
        ("enumerate", 1, ["total"]),
        ("uncertain", 1, []),
        ("reported_quantity", 0.2, ["total"]),
    ],
)
async def test_preserve_count_on_enumeration_uncertainty_or_low_confidence(
    route, confidence, support
):
    _, engine, plan = await setup(record("total", "episode"))
    result = await CandidateAwarePersonalMemoryQuery(
        engine, Model(route, support, confidence)
    ).execute(plan)
    assert not result.applied and result.result.plan == plan


async def test_feedback_never_receives_other_scope_actor_inactive_or_future_records():
    _, engine, plan = await setup(
        record("total"),
        record("foreign", scope=MemoryScope(user_id="other", agent_id="agent")),
        record("agent", actor="agent", authority="agent_output"),
        record("inactive", state="expired"),
        record("future", created_at=NOW + timedelta(days=1)),
    )
    model = Model()
    result = await CandidateAwarePersonalMemoryQuery(engine, model).execute(plan)
    assert result.supplied_memory_ids == ["total"]
    assert [c["memory_id"] for c in model.requests[0].input["candidates"]] == ["total"]


async def test_unknown_support_fails_without_retry_or_scope_changes():
    _, engine, plan = await setup(record("total"))
    model = Model(support=["not-supplied"])
    with pytest.raises(ValueError, match="unsupplied"):
        await CandidateAwarePersonalMemoryQuery(engine, model).execute(plan)
    assert len(model.requests) == 1


async def test_empty_candidates_skip_provider_and_do_not_claim_absence():
    _, engine, plan = await setup()
    model = Model()
    result = await CandidateAwarePersonalMemoryQuery(engine, model).execute(plan)
    assert not model.requests and not result.applied
    assert not result.candidate_pool_complete_history


async def test_large_whole_item_is_omitted_explicitly_not_truncated():
    _, engine, plan = await setup(record("total", content="x" * 5000))
    model = Model()
    result = await CandidateAwarePersonalMemoryQuery(
        engine, model, CandidateFeedbackConfig(max_candidate_bytes=256)
    ).execute(plan)
    assert result.omitted_hit_count == 1 and not model.requests
    assert result.discovery is not None
    assert result.discovery.hits[0].record.content == "x" * 5000


async def test_forged_initial_plan_is_rejected_before_model_or_widening():
    _, engine, plan = await setup(record("total"))
    model = Model()
    with pytest.raises(ValueError, match="plan_id"):
        await CandidateAwarePersonalMemoryQuery(engine, model).execute(
            plan.model_copy(update={"subject_id": "other"})
        )
    assert not model.requests


async def test_noncount_plan_skips_feedback_entirely():
    _, engine, plan = await setup(record("total"))
    model = Model()
    wrapper = CandidateAwarePersonalMemoryQuery(engine, model)
    lookup = wrapper._lookup(plan)
    result = await wrapper.execute(lookup)
    assert not model.requests and result.discovery is None


async def test_reloads_authoritative_store_after_feedback_instead_of_trusting_snapshot():
    store, engine, plan = await setup(record("total"))

    class ForgetDuringFeedback(Model):
        async def generate(self, request):
            result = await super().generate(request)
            await store.forget(SCOPE, "total", hard=True)
            return result

    result = await CandidateAwarePersonalMemoryQuery(
        engine, ForgetDuringFeedback()
    ).execute(plan)
    assert result.applied and not result.result.hits


async def test_harness_budgeted_live_and_key_free_replay(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from benchmarks import public_memory_quantity_feedback as harness

    _, engine, plan = await setup(record("total"))
    probe = harness.Probe(Model())
    await CandidateAwarePersonalMemoryQuery(engine, probe).execute(plan)
    assert probe.request is not None
    frozen = {
        "plan_fingerprint": "synthetic",
        "requests": [
            {"request_sha256": harness._hash(probe.request.model_dump(mode="json"))}
        ],
    }

    async def prepare():
        return [(1, "synthetic", engine, plan)], frozen

    calls = []

    def factory(cfg, key, observer):
        class Fake(Model):
            async def generate(self, request):
                calls.append(request)
                observer({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
                return await super().generate(request)

        return Fake()

    monkeypatch.setattr(harness, "prepare", prepare)
    monkeypatch.setattr(harness.parent, "_default_provider_factory", factory)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-not-real")
    preflight = tmp_path / "preflight.json"
    harness.save(preflight, {"plan": frozen})
    args = SimpleNamespace(
        execute=True,
        cache_only=False,
        run_dir=tmp_path / "run",
        frozen_preflight=preflight,
    )
    live = await harness.run(args)
    assert live["status"] == "complete" and len(calls) == 1
    assert live["usage"]["attempts_reserved"] == 1
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    args.cache_only = True
    replay = await harness.run(args)
    assert replay == live and len(calls) == 1
    assert all(
        "synthetic-not-real" not in p.read_text(encoding="utf-8")
        for p in tmp_path.rglob("*.json")
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"supporting_memory_ids": []},
        {"supporting_memory_ids": ["a", "a"]},
        {"scopes": ["other"]},
        {"route": "answer"},
    ],
)
def test_routing_contract_cannot_return_unbound_plan_or_answer(updates):
    with pytest.raises(ValidationError):
        QuantityRoutingDecision.model_validate(
            {
                "route": "reported_quantity",
                "supporting_memory_ids": ["a"],
                "confidence": 1,
                **updates,
            }
        )

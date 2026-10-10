from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    PersonalMemoryExtractor,
    PersonalMemoryExtractorConfig,
    ReferencePersonalMemoryAnalyzer,
)
from doppel_memory.models import ChatMessage, MemoryScope
from doppel_memory.transient import TransientMemoryViewBuilder, TransientViewError

SCOPE = MemoryScope(user_id="owner-1", agent_id="agent-1")


def day(n):
    return datetime(2024, 1, n, tzinfo=UTC)


async def fixture(
    *, correction=False, status="current", subject="owner", start=None, end=None
):
    actor = subject
    messages = [
        ChatMessage(
            message_id="a",
            actor=actor,
            sender_id="contact-1" if actor == "contact" else "",
            text="First value.",
            at=day(1),
        ),
        ChatMessage(
            message_id="b",
            actor=actor,
            sender_id="contact-1" if actor == "contact" else "",
            text="Revised value.",
            at=day(3),
        ),
    ]

    class Script:
        name, version = "fixture", "1"

        async def generate(self, request):
            current = request.input["messages"][0]["evidence_id"]
            return {
                "memories": [
                    {
                        "content": "First value" if current == "a" else "Revised value",
                        "subject": subject,
                        "memory_type": "state",
                        "topic_key": "generic.slot",
                        "temporal_status": status,
                        "evidence_ids": [current],
                        "revision_kind": "correction"
                        if correction and current == "b"
                        else "assertion",
                        "valid_from": start,
                        "valid_to": end,
                    }
                ]
            }

    extractor = PersonalMemoryExtractor(
        ReferencePersonalMemoryAnalyzer(Script()),
        PersonalMemoryExtractorConfig(
            owner_target_scope="conversation", allowed_source_actors={actor}
        ),
    )
    proposals = [
        p for message in messages for p in await extractor.process(SCOPE, message)
    ]
    return PersonalMemoryAnalysisRequest(scope=SCOPE, messages=messages), proposals


async def test_no_newest_wins_no_effective_date_invention_or_input_mutation():
    request, proposals = await fixture()
    original = deepcopy((request, proposals))
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(4)
    )
    assert (request, proposals) == original
    assert len(view.claims) == 2
    assert all(
        c.validity_at_reference == "unknown"
        and c.valid_from is None
        and c.valid_to is None
        for c in view.claims
    )
    assert [c.last_observed_at for c in view.claims] == [day(1), day(3)]
    assert all(
        c.temporal_status == "current" and c.state == "candidate" for c in view.claims
    )
    assert len(view.advisory_consolidation) == 1
    decision = view.advisory_consolidation[0]
    assert decision.operation == "conflict" and not decision.canonical_source_memory_id
    assert set(decision.source_memory_ids) == {c.claim_id for c in view.claims}
    assert not view.consolidation_applied and not view.semantic_evidence_verified
    assert view == await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(4)
    )


async def test_explicit_revision_advisory_does_not_remove_old_claim_or_infer_end():
    request, proposals = await fixture(correction=True)
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(4)
    )
    assert view.advisory_consolidation[0].operation == "correct"
    assert len(view.claims) == 2 and view.claims[0].valid_to is None
    assert all(c.state == "candidate" for c in view.claims)


@pytest.mark.parametrize(
    "reference,expected",
    [
        (1, "outside_explicit_bounds"),
        (2, "within_explicit_bounds"),
        (4, "within_explicit_bounds"),
        (5, "outside_explicit_bounds"),
    ],
)
async def test_explicit_interval_inclusive_boundaries_do_not_use_observation_as_validity(
    reference, expected
):
    request, proposals = await fixture(start=day(2), end=day(4))
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(reference), observed_until=day(6)
    )
    assert all(c.validity_at_reference == expected for c in view.claims)
    assert view.claims[0].first_observed_at == day(1)
    assert view.claims[0].valid_from == day(2)


async def test_later_observations_fail_strict_but_remain_explicit_with_authorized_horizon():
    request, proposals = await fixture()
    with pytest.raises(TransientViewError, match="horizon"):
        await TransientMemoryViewBuilder().build(
            request, proposals, reference_time=day(2)
        )
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(2), observed_until=day(3)
    )
    assert [c.observed_after_reference for c in view.claims] == [False, True]
    assert len(view.claims) == 2
    with pytest.raises(TransientViewError):
        await TransientMemoryViewBuilder().build(
            request, proposals, reference_time=day(4), observed_until=day(3)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "scope",
        "state",
        "unknown",
        "duplicate",
        "actor",
        "sender",
        "time",
        "created",
        "authority",
        "subject",
        "subject_id",
        "source_scope",
        "reversed",
        "naive",
    ],
)
async def test_untrusted_binding_fails_closed(mutation):
    request, proposals = await fixture()
    item = proposals[0].model_copy(deep=True)
    if mutation == "scope":
        item.scope = MemoryScope(user_id="other", agent_id="agent-1")
    elif mutation == "state":
        item.proposed_state = "confirmed"
    elif mutation == "unknown":
        item.metadata["evidence"][0]["evidence_id"] = "foreign"
    elif mutation == "duplicate":
        item.metadata["evidence"].append(deepcopy(item.metadata["evidence"][0]))
    elif mutation in {"actor", "sender", "time"}:
        key = {"actor": "actor", "sender": "sender_id", "time": "at"}[mutation]
        item.metadata["evidence"][0][key] = (
            day(2).isoformat() if mutation == "time" else "foreign"
        )
    elif mutation == "created":
        item.created_at = day(2)
    elif mutation == "authority":
        item.authority = "agent_output"
    elif mutation in {"subject", "subject_id", "source_scope"}:
        item.metadata[
            {
                "subject": "subject",
                "subject_id": "subject_id",
                "source_scope": "source_scope_key",
            }[mutation]
        ] = "foreign"
    elif mutation == "reversed":
        item.metadata.update(valid_from=day(3).isoformat(), valid_to=day(1).isoformat())
    else:
        item.metadata["valid_from"] = "2024-01-01T00:00:00"
    with pytest.raises(TransientViewError):
        await TransientMemoryViewBuilder().build(request, [item], reference_time=day(4))


@pytest.mark.parametrize("subject", ["owner", "agent", "contact"])
async def test_source_subject_authority_and_original_message_preserved(subject):
    request, proposals = await fixture(subject=subject)
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(4)
    )
    assert view.claims[0].actor == subject
    assert view.claims[0].evidence[0].text == request.messages[0].text
    assert view.claims[0].evidence[0].authority == proposals[0].authority


async def test_plan_remains_plan_after_date_passes():
    request, proposals = await fixture(status="planned", end=day(3))
    view = await TransientMemoryViewBuilder().build(
        request, proposals, reference_time=day(10)
    )
    assert all(
        c.temporal_status == "planned" and c.state == "candidate" for c in view.claims
    )
    assert all(
        c.validity_at_reference == "outside_explicit_bounds" for c in view.claims
    )


async def test_limits_duplicates_empty_claims_and_timezone_validation():
    request, proposals = await fixture()
    for builder in (
        TransientMemoryViewBuilder(max_messages=1),
        TransientMemoryViewBuilder(max_claims=1),
    ):
        with pytest.raises(TransientViewError, match="limit"):
            await builder.build(request, proposals, reference_time=day(4))
    with pytest.raises(TransientViewError, match="duplicate proposal"):
        await TransientMemoryViewBuilder().build(
            request, [proposals[0], proposals[0]], reference_time=day(4)
        )
    with pytest.raises(TransientViewError, match="timezone"):
        await TransientMemoryViewBuilder().build(
            request, proposals, reference_time=day(4).replace(tzinfo=None)
        )
    view = await TransientMemoryViewBuilder().build(request, [], reference_time=day(4))
    assert not view.claims and not view.advisory_consolidation
    for limit in (0, -1, True):
        with pytest.raises(ValueError):
            TransientMemoryViewBuilder(max_claims=limit)

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from doppel_memory import (
    FactAuthority,
    TransientEvidence,
    TransientMemoryClaim,
    TransientMemoryView,
    TransientViewError,
    group_transient_events,
)

NOW = datetime(2026, 3, 1, tzinfo=UTC)


def claim(
    identity,
    content="An event detail",
    *,
    key="same",
    actor="owner",
    subject_id="owner-one",
    start=None,
):
    return TransientMemoryClaim(
        claim_id=identity,
        content=content,
        actor=actor,
        authority=FactAuthority.of(actor),
        subject=actor,
        subject_id=subject_id,
        confidence=0.9,
        memory_type="episode",
        topic_key="",
        event_key=key,
        revision_kind="assertion",
        temporal_status="historical",
        first_observed_at=NOW,
        last_observed_at=NOW,
        observed_after_reference=False,
        valid_from=start,
        valid_to=None,
        validity_at_reference="unknown",
        evidence=(
            TransientEvidence(
                evidence_id="source-" + identity,
                actor=actor,
                authority=FactAuthority.of(actor),
                sender_id=subject_id,
                observed_at=NOW,
                text="Original " + content,
            ),
        ),
    )


def view(*claims, scope="one-scope"):
    return TransientMemoryView(
        scope_key=scope,
        reference_time=NOW,
        observed_until=NOW,
        claims=claims,
        advisory_consolidation=(),
    )


def test_group_keeps_every_detail_and_source_without_mutation_or_synthesis():
    source = view(claim("a", "Dinner cost 340 yuan"), claim("b", "Tip was 25 yuan"))
    before = deepcopy(source)
    groups = group_transient_events(source)
    assert source == before
    assert len(groups) == 1
    group = groups[0]
    assert {c.content for c in group.claims} == {c.content for c in source.claims}
    assert {e.text for c in group.claims for e in c.evidence} == {
        e.text for c in source.claims for e in c.evidence
    }
    assert group.identity_basis == "shared_declared_event_key"
    assert not group.semantic_identity_verified and not group.consolidation_applied
    assert group == group_transient_events(view(*source.claims[::-1]))[0]


@pytest.mark.parametrize(
    "dimension", ["scope", "actor", "authority", "subject", "subject_id", "event"]
)
def test_group_identity_partitions_trust_namespace(dimension):
    a = claim("a")
    b = claim("b")
    if dimension == "scope":
        assert (
            group_transient_events(view(a, scope="x"))[0].group_id
            != group_transient_events(view(a, scope="y"))[0].group_id
        )
        return
    field, value = {
        "actor": ("actor", "contact"),
        "authority": ("authority", FactAuthority.PEER_STATEMENT),
        "subject": ("subject", "contact"),
        "subject_id": ("subject_id", "other"),
        "event": ("event_key", "other-event"),
    }[dimension]
    b = b.model_copy(update={field: value})
    assert len(group_transient_events(view(a, b))) == 2


def test_unknown_identity_not_guessed_and_non_episodes_stay_in_input():
    a, b = claim("a", key=""), claim("b", key="")
    fact = claim("f").model_copy(update={"memory_type": "fact", "event_key": ""})
    source = view(a, b, fact)
    groups = group_transient_events(source)
    assert len(groups) == 2
    assert all(g.identity_basis == "single_unkeyed_claim" for g in groups)
    assert fact in source.claims


def test_temporal_disagreement_flagged_without_selecting_latest_or_range_union():
    a, b = claim("a", start=NOW), claim("b")
    group = group_transient_events(view(a, b))[0]
    assert not group.temporal_metadata_consistent
    assert group.claims[0].valid_from == NOW and group.claims[1].valid_from is None
    assert not group.semantic_identity_verified


def test_limits_duplicate_identity_and_invalid_limit_fail_closed():
    source = view(claim("a"), claim("b"))
    with pytest.raises(TransientViewError, match="limit"):
        group_transient_events(source, max_claims=1)
    with pytest.raises(TransientViewError, match="duplicate"):
        group_transient_events(view(claim("a"), claim("a")))
    with pytest.raises(ValueError, match="positive integer"):
        group_transient_events(source, max_claims=True)

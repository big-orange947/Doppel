"""Generic draft quarantine: no benchmark questions or model/network calls."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryEvidenceError,
    PersonalMemoryMinerConfig,
    _analysis_to_proposals,
)
from doppel_memory.models import (
    Actor,
    ChatMessage,
    FactAuthority,
    MemoryScope,
    MemoryState,
)

SCOPE = MemoryScope(user_id="synthetic-owner", agent_id="synthetic-agent")


class Analyzer:
    name, version = "synthetic-no-provider", "1"


def message(identity: str, actor: str, sender: str = "") -> ChatMessage:
    return ChatMessage(
        event_id=identity,
        text="Generic source",
        actor=actor,
        sender_id=sender,
        at=datetime(2024, 1, 1, tzinfo=UTC),
    )


MESSAGES = [
    message("owner", Actor.OWNER),
    message("agent", Actor.AGENT),
    message("contact-a", Actor.CONTACT, "speaker-a"),
    message("contact-b", Actor.CONTACT, "speaker-b"),
]


def draft(
    content: str = "Generic claim",
    *,
    subject: str = Actor.OWNER,
    evidence: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "content": content,
        "subject": subject,
        "evidence_ids": evidence or ["owner"],
        **extra,
    }


def convert(drafts, config=None, *, diagnostics=True):
    counts = {} if diagnostics else None
    proposals = _analysis_to_proposals(
        PersonalMemoryAnalysisRequest(scope=SCOPE, messages=MESSAGES),
        PersonalMemoryAnalysis.model_validate({"memories": drafts}),
        analyzer=Analyzer(),
        processor="synthetic-processor",
        processor_version="1",
        config=config
        or PersonalMemoryMinerConfig(
            evidence_error_policy="quarantine",
            allowed_source_actors={Actor.OWNER, Actor.AGENT, Actor.CONTACT},
        ),
        diagnostics=counts,
    )
    return proposals, counts


def test_valid_drafts_survive_without_repairing_or_promoting_unsafe_evidence() -> None:
    owner = draft("Owner evidence only")
    agent = draft(
        "Attributed assistant evidence", subject=Actor.AGENT, evidence=["agent"]
    )
    inputs = [
        owner,
        agent,
        draft("REJECTED_CONTENT_SECRET", evidence=["owner", "agent"]),
        draft("REJECTED_CONTENT_SECRET", evidence=["agent"]),
        draft("REJECTED_CONTENT_SECRET", evidence=["UNKNOWN_REFERENCE_SECRET"]),
        draft("REJECTED_CONTENT_SECRET", subject_id="OTHER_OWNER_SECRET"),
        draft("Low confidence", confidence=0.1),
        owner,
    ]
    before = json.dumps(inputs)
    proposals, counts = convert(inputs)
    assert json.dumps(inputs) == before
    assert [proposal.content for proposal in proposals] == [
        owner["content"],
        agent["content"],
    ]
    assert (
        proposals[0].actor == Actor.OWNER
        and proposals[0].authority == FactAuthority.HUMAN_SELF
    )
    assert (
        proposals[1].actor == Actor.AGENT
        and proposals[1].authority == FactAuthority.AGENT_OUTPUT
    )
    assert all(
        proposal.proposed_state == MemoryState.CANDIDATE for proposal in proposals
    )
    assert proposals[0].derived_chain == ["event:owner"]
    assert proposals[1].derived_chain == ["event:agent"]
    assert counts["valid_drafts"] == 8
    assert counts["evidence_rejected_drafts"] == 4
    assert counts["duplicate_drafts"] == counts["low_confidence_drafts"] == 1
    assert counts["evidence_rejection_counts"] == {
        "mixed_source_actors": 1,
        "subject_source_mismatch": 1,
        "unknown_evidence": 1,
        "untrusted_subject_identity": 1,
    }
    assert {item["analysis_draft_index"] for item in counts["rejected_drafts"]} == {
        2,
        3,
        4,
        5,
    }
    assert "SECRET" not in json.dumps(counts)
    assert (
        counts["valid_drafts"]
        == len(proposals)
        + counts["evidence_rejected_drafts"]
        + counts["duplicate_drafts"]
        + counts["low_confidence_drafts"]
    )


@pytest.mark.parametrize(
    "unsafe, config, reason",
    [
        (draft(evidence=["unknown"]), None, "unknown_evidence"),
        (draft(evidence=["owner", "agent"]), None, "mixed_source_actors"),
        (draft(evidence=["agent"]), None, "subject_source_mismatch"),
        (
            draft(subject=Actor.CONTACT, evidence=["contact-a", "contact-b"]),
            None,
            "untrusted_subject_identity",
        ),
        (
            draft(subject=Actor.CONTACT, evidence=["contact-a"]),
            PersonalMemoryMinerConfig(
                evidence_error_policy="quarantine", allowed_source_actors={Actor.OWNER}
            ),
            "excluded_source_actor",
        ),
    ],
)
def test_all_unsafe_is_an_explicit_empty_plan_not_fabricated_success(
    unsafe, config, reason
) -> None:
    proposals, counts = convert([unsafe], config)
    assert proposals == []
    assert counts["valid_drafts"] == counts["evidence_rejected_drafts"] == 1
    assert counts["evidence_rejection_counts"] == {reason: 1}


def test_default_fail_batch_and_old_fingerprints_unchanged() -> None:
    config = PersonalMemoryMinerConfig(allowed_source_actors={Actor.OWNER, Actor.AGENT})
    assert config.evidence_error_policy == "fail_batch"
    with pytest.raises(PersonalMemoryEvidenceError, match="exactly one source actor"):
        convert([draft(), draft(evidence=["owner", "agent"])], config)
    old_payload = config.model_dump(mode="json")
    old_payload.pop("evidence_error_policy")
    old_payload["allowed_source_actors"] = sorted(old_payload["allowed_source_actors"])
    expected = hashlib.sha256(
        json.dumps(
            old_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    assert config.fingerprint == expected
    quarantine = config.model_copy(update={"evidence_error_policy": "quarantine"})
    assert quarantine.fingerprint != config.fingerprint


def test_quarantine_cannot_disable_subject_gate_drop_accounting_or_hide_bounds() -> (
    None
):
    with pytest.raises(ValueError, match="requires subject"):
        PersonalMemoryMinerConfig(
            evidence_error_policy="quarantine",
            require_subject_matches_source_actor=False,
        )
    copied = PersonalMemoryMinerConfig().model_copy(
        update={
            "evidence_error_policy": "quarantine",
            "require_subject_matches_source_actor": False,
        }
    )
    with pytest.raises(ValueError, match="requires subject"):
        convert([draft()], copied)
    with pytest.raises(ValueError, match="rejection accounting"):
        convert([draft(evidence=["unknown"])], diagnostics=False)
    with pytest.raises(PersonalMemoryEvidenceError, match="maximum"):
        convert(
            [draft(), draft()],
            PersonalMemoryMinerConfig(
                evidence_error_policy="quarantine", max_memories=1
            ),
        )
    with pytest.raises(ValidationError):
        convert([{"invalid_schema": True}])

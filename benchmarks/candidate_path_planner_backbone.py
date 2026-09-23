"""Adapt the existing V7 exact-path Planner into retrieval-only candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import product

from doppel_memory.intelligence import StructuredOutputModel
from doppel_memory.query import PersonalMemoryQueryRequest
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV7
from doppel_memory.query_path_candidate import (
    CandidateRelationGenerationRequest,
    CandidateRelationObservation,
)
from doppel_memory.relation import RelationPathStep
from doppel_memory.relation_path_retrieval import (
    CandidateRelationAtom,
    CandidateRelationTopology,
)


class PlannerBackedCandidatePathGenerator:
    """Use V7 for topology understanding without granting graph authority."""

    name = "doppel.benchmark-planner-backed-candidate-path-generator"
    version = "1"

    def __init__(
        self,
        model: StructuredOutputModel,
        *,
        now: datetime = datetime(2026, 9, 23, tzinfo=UTC),
    ) -> None:
        if now.tzinfo is None:
            raise ValueError("planner-backbone now must include a timezone")
        self._planner = ReferencePersonalMemoryRelationPathPlannerV7(model)
        self._now = now.astimezone(UTC)
        self.version = f"1:{self._planner.version}"

    async def generate(
        self, request: CandidateRelationGenerationRequest
    ) -> CandidateRelationObservation:
        bound = CandidateRelationGenerationRequest.model_validate(request)
        definitions = bound.relation_type_definitions
        draft = await self._planner.plan(
            PersonalMemoryQueryRequest(
                query=bound.query,
                now=self._now,
                calendar_timezone="+08:00",
                default_subject="owner",
                default_subject_id="candidate-path-benchmark-owner",
                available_relation_types=[item.name for item in definitions],
                relation_type_definitions=definitions,
            )
        )
        if draft.path_decision != "execute":
            return CandidateRelationObservation()
        return CandidateRelationObservation(
            topologies=_candidate_topologies_from_steps(
                draft.path_steps, confidence=draft.path_confidence
            )
        )


def _candidate_topologies_from_steps(
    steps: list[RelationPathStep], *, confidence: float
) -> list[CandidateRelationTopology]:
    """Convert trusted ordered directions back to bounded declarative atoms."""

    direction_options = [
        ("outbound", "inbound") if step.direction == "either" else (step.direction,)
        for step in steps
    ]
    topologies: list[CandidateRelationTopology] = []
    for directions in product(*direction_options):
        atoms: list[CandidateRelationAtom] = []
        for index, (step, direction) in enumerate(zip(steps, directions, strict=True)):
            current_ref = "anchor" if index == 0 else f"middle_{index}"
            next_ref = "answer" if index == len(steps) - 1 else f"middle_{index + 1}"
            source_ref, target_ref = (
                (current_ref, next_ref)
                if direction == "outbound"
                else (next_ref, current_ref)
            )
            atoms.append(
                CandidateRelationAtom(
                    relation_types=step.relation_types,
                    source_ref=source_ref,
                    target_ref=target_ref,
                )
            )
        topologies.append(CandidateRelationTopology(atoms=atoms, confidence=confidence))
    return topologies

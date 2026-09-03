"""Post-hoc diagnostics over frozen planner outputs, never runtime query rules.

The review is separate from storage gold: an answerable semantic question need not
uniquely identify the label used by a hidden graph edge. It deliberately does not
produce a replacement pass rate or relax any retrieval gate.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from benchmarks.personal_retrieval_ablation import AblationDataset
from doppel_memory import PersonalMemoryQueryDraft


class TimestampRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum: datetime
    maximum: datetime

    @model_validator(mode="after")
    def _check_range(self) -> TimestampRange:
        if self.minimum.tzinfo is None or self.maximum.tzinfo is None:
            raise ValueError("review timestamps require timezones")
        if self.maximum < self.minimum:
            raise ValueError("review timestamp range is reversed")
        return self

    def accepts(self, value: datetime | None) -> bool:
        return value is not None and self.minimum <= value <= self.maximum


class TemporalAlternative(BaseModel):
    """Exact shape matching; an absent slot requires absence in the actual draft."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    as_of: TimestampRange | None = None
    time_from: TimestampRange | None = None
    time_to: TimestampRange | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> TemporalAlternative:
        if self.as_of and (self.time_from or self.time_to):
            raise ValueError("point and interval expectations are mutually exclusive")
        if not (self.as_of or self.time_from or self.time_to):
            raise ValueError("a temporal review must constrain at least one bound")
        if (
            self.time_from
            and self.time_to
            and self.time_to.maximum < self.time_from.minimum
        ):
            raise ValueError("review interval is reversed")
        return self

    def accepts(self, draft: PersonalMemoryQueryDraft) -> bool:
        return all(
            actual is None if expected is None else expected.accepts(actual)
            for expected, actual in (
                (self.as_of, draft.as_of),
                (self.time_from, draft.time_from),
                (self.time_to, draft.time_to),
            )
        )


class RelationReviewGroup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    query_ids: list[str] = Field(min_length=1)
    policy: Literal["explicit", "underdetermined"]
    expected_types: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_policy(self) -> RelationReviewGroup:
        if self.policy == "explicit" and not self.expected_types:
            raise ValueError("explicit relation review requires expected types")
        if self.policy == "underdetermined" and self.expected_types:
            raise ValueError("underdetermined review must not impose hidden labels")
        if len(self.expected_types) != len(set(self.expected_types)):
            raise ValueError("duplicate expected relation types")
        return self


class TemporalReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    alternatives: list[TemporalAlternative] = Field(min_length=1)
    reason: str = Field(min_length=1)
    retrieval_gold_needs_review: bool = False


class PlannerSemanticReview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: str
    dataset_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["posthoc_diagnostic"]
    publication_ready: Literal[False] = False
    note: str
    relation_groups: list[RelationReviewGroup]
    temporal_reviews: dict[str, TemporalReview] = Field(default_factory=dict)

    def validate_dataset(self, dataset: AblationDataset) -> None:
        if dataset.fingerprint != self.dataset_fingerprint:
            raise ValueError("semantic review dataset fingerprint mismatch")
        ids = {query.query_id for query in dataset.queries}
        reviewed_ids = [
            item for group in self.relation_groups for item in group.query_ids
        ]
        if len(reviewed_ids) != len(set(reviewed_ids)):
            raise ValueError("semantic review repeats a query")
        if set(reviewed_ids).difference(ids) or set(self.temporal_reviews).difference(
            ids
        ):
            raise ValueError("semantic review contains unknown queries")
        allowed = set(dataset.relation_types)
        if any(
            set(group.expected_types).difference(allowed)
            for group in self.relation_groups
        ):
            raise ValueError("semantic review type is outside the host ontology")


def review_planner_report(
    report: dict[str, Any], dataset: AblationDataset, review_path: Path
) -> dict[str, Any]:
    """Read-only diagnostic; never rewrite actual drafts or legacy metrics."""
    payload = review_path.read_bytes()
    review = PlannerSemanticReview.model_validate_json(payload)
    review.validate_dataset(dataset)
    if report["dataset"]["fingerprint"] != dataset.fingerprint:
        raise ValueError("planner report dataset fingerprint mismatch")
    groups = {
        query_id: group
        for group in review.relation_groups
        for query_id in group.query_ids
    }
    rows: list[dict[str, Any]] = []
    for case in report["cases"]:
        group = groups.get(case["query_id"])
        row: dict[str, Any] = {
            "query_id": case["query_id"],
            "partition": case["partition"],
            "relation_assessment": "unreviewed",
            "temporal_assessment": "unreviewed",
            "relation_reason": group.reason if group else "",
        }
        if case.get("error") or case.get("actual") is None:
            row.update(
                relation_assessment="unavailable", temporal_assessment="unavailable"
            )
        else:
            draft = PersonalMemoryQueryDraft.model_validate(case["actual"])
            types = set(draft.relation_types)
            if types.difference(dataset.relation_types):
                row["relation_assessment"] = "ontology_violation"
            elif group is not None:
                if group.policy == "underdetermined":
                    row["relation_assessment"] = (
                        "ambiguous_hard_filter" if types else "conservative_abstention"
                    )
                elif not types:
                    row["relation_assessment"] = "missed_explicit_type"
                else:
                    row["relation_assessment"] = (
                        "correct_explicit_type"
                        if types == set(group.expected_types)
                        else "wrong_explicit_type"
                    )
            temporal = review.temporal_reviews.get(case["query_id"])
            if temporal is not None:
                row["temporal_assessment"] = (
                    "matches_reviewed_shape"
                    if any(item.accepts(draft) for item in temporal.alternatives)
                    else "shape_mismatch"
                )
                row["temporal_reason"] = temporal.reason
                row["retrieval_gold_needs_review"] = (
                    temporal.retrieval_gold_needs_review
                )
        rows.append(row)
    return {
        "version": review.version,
        "status": review.status,
        "publication_ready": review.publication_ready,
        "path": str(review_path.resolve()),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "dataset_fingerprint": review.dataset_fingerprint,
        "note": review.note,
        "legacy_scores_unchanged": True,
        "relation_assessment_counts": dict(
            sorted(Counter(row["relation_assessment"] for row in rows).items())
        ),
        "temporal_assessment_counts": dict(
            sorted(Counter(row["temporal_assessment"] for row in rows).items())
        ),
        "cases": rows,
    }

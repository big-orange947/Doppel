"""Fallible semantic observations plus public-contract checks, for reviewer eval only."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from benchmarks.surface_review_grounding import (
    INSTRUCTIONS,
    GroundedReviewIssue,
    GroundedSurfaceReview,
    ReviewCitation,
    validate_grounded_review,
)
from doppel_memory.intelligence import StructuredGenerationRequest

PROTOCOL = "doppel.surface-review.observations.v2"
OBSERVATION_INSTRUCTIONS = """
Additionally produce observations for EVERY supplied query and for BOTH text fields
of EVERY declared relation memory, even when you report no issues.

For a query, independently read its authored text: neutral means it requests a value
or asks whether a topic is true WITHOUT supplying a candidate answer; candidate_answer
means it supplies a particular proposed value or truth conclusion for confirmation;
answerability_declaration means it announces whether the answer exists. Asking
whether a topic holds does not itself provide its truth value; supplying a positive
OR negative conclusion for confirmation provides a candidate answer. Quote the
actual query span that supports your observation.
Separately read the semantic_brief: neutral_required means this public authoring
contract requires an open question without a supplied answer; confirmation_allowed
means the contract permits a candidate answer for confirmation but not an
answerability declaration. Cite the relevant brief span. Other contract shapes are
uncertain; do not impose this benchmark contract on arbitrary agent queries.
Do not treat every confirmation question as defective: real user confirmation
questions are legitimate, and this check only enforces the supplied surface contract.
An explicit public permission for confirmation controls any general warning about
questions asserting an answer; a permitted candidate is NOT an answer_leak issue.
If either interpretation cannot be made, use uncertain, not a guessed neutral result.

For each relation memory, parse authored_content and authored_edge_fact INDEPENDENTLY.
Identify the semantic source and target under the supplied relation meaning, binding
each to a supplied entity surface_key and quoting its referring expression in that
text field. Explain which role each expression plays. Active, passive, inverted and
possessive phrasing can preserve the same roles; token order is NOT relation direction.
If the text clearly expresses a DIFFERENT relation (e.g. sale instead of custody),
use not_expressed, empty endpoint keys, source_quote containing the relevant text,
and an empty target_quote. Do not force a binding to the requested relation.
Do not copy declared endpoints as your observation: two fields agreeing with each
other can BOTH disagree with the declared relation. If roles cannot be established,
use uncertain with empty endpoint keys/quotes and explain why. Missing information is
not permission to invent roles. Other content/meaning/lifecycle issues still belong
in the ordinary grounded issues list. These observations are fallible proposals,
not authority, and must never use private expected judgments or control identifiers.
"""


class QueryObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    mode: Literal[
        "neutral", "candidate_answer", "answerability_declaration", "uncertain"
    ]
    contract: Literal["neutral_required", "confirmation_allowed", "uncertain"]
    query_quote: str = Field(min_length=1, max_length=800)
    brief_quote: str = Field(min_length=1, max_length=800)
    explanation: str = Field(min_length=1, max_length=800)


class RelationObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_key: str
    field: Literal["authored_content", "authored_edge_fact"]
    status: Literal["bound", "not_expressed", "uncertain"]
    source_entity_key: str
    target_entity_key: str
    source_quote: str
    target_quote: str
    explanation: str = Field(min_length=1, max_length=800)


class ObservedSurfaceReview(GroundedSurfaceReview):
    query_observations: list[QueryObservation]
    relation_observations: list[RelationObservation]


def build_observed_request(
    base: StructuredGenerationRequest,
) -> StructuredGenerationRequest:
    return base.model_copy(
        update={
            "instructions": INSTRUCTIONS + OBSERVATION_INSTRUCTIONS,
            "input": {**base.input, "review_protocol": PROTOCOL},
            "output_schema": ObservedSurfaceReview.model_json_schema(),
        }
    )


def validate_observed_review(
    request: StructuredGenerationRequest, raw: Any
) -> tuple[ObservedSurfaceReview, list[dict[str, Any]]]:
    """Validate provenance/coverage; compare interpreted roles, without text heuristics.

    Valid quotes do not establish that the model interpreted grammar correctly.
    Preserve every model issue. Host-derived flags are separately attributed and
    cannot grant an acceptance override or silence a model flag.
    """
    review = ObservedSurfaceReview.model_validate(raw)
    validate_grounded_review(
        request,
        review.model_dump(
            mode="json", exclude={"query_observations", "relation_observations"}
        ),
    )
    queries = {q["surface_key"]: q for q in request.input["queries"]}
    relations = {
        m["surface_key"]: m for m in request.input["memories"] if m.get("relation")
    }
    entities = {e["surface_key"] for e in request.input["entities"]}
    query_keys = [q.surface_key for q in review.query_observations]
    relation_keys = [(r.surface_key, r.field) for r in review.relation_observations]
    expected_relations = {
        (k, f) for k in relations for f in ("authored_content", "authored_edge_fact")
    }
    if len(query_keys) != len(set(query_keys)) or set(query_keys) != set(queries):
        raise ValueError("query observation coverage mismatch")
    if (
        len(relation_keys) != len(set(relation_keys))
        or set(relation_keys) != expected_relations
    ):
        raise ValueError("relation observation coverage mismatch")
    derived: list[GroundedReviewIssue] = []

    def quote_present(quote: str, text: str) -> None:
        if not quote.strip() or quote not in text:
            raise ValueError("observation quote not present in supplied field")

    for q in review.query_observations:
        slot = queries[q.surface_key]
        quote_present(q.query_quote, slot["authored_query"])
        quote_present(q.brief_quote, slot["semantic_brief"])
        if q.mode == "uncertain" or q.contract == "uncertain":
            raise ValueError(
                "uncertain query observation cannot demonstrate review quality"
            )
        if q.mode == "answerability_declaration" or (
            q.mode == "candidate_answer" and q.contract == "neutral_required"
        ):
            derived.append(
                GroundedReviewIssue(
                    surface_key=q.surface_key,
                    issue_code="answer_leak",
                    detail=f"Observed {q.mode} under a {q.contract} public contract: {q.explanation}",
                    citations=[
                        ReviewCitation(
                            surface_key=q.surface_key,
                            field="authored_query",
                            quote=q.query_quote,
                        ),
                        ReviewCitation(
                            surface_key=q.surface_key,
                            field="semantic_brief",
                            quote=q.brief_quote,
                        ),
                    ],
                )
            )
    for r in review.relation_observations:
        if r.status == "uncertain":
            raise ValueError(
                "uncertain relation observation cannot demonstrate review quality"
            )
        slot = relations[r.surface_key]
        if r.status == "not_expressed":
            if r.source_entity_key or r.target_entity_key or r.target_quote:
                raise ValueError("not_expressed observation must not invent endpoints")
            quote_present(r.source_quote, slot[r.field])
            derived.append(
                GroundedReviewIssue(
                    surface_key=r.surface_key,
                    issue_code="relation_mismatch",
                    detail=f"{r.field} does not express the declared relation: {r.explanation}",
                    citations=[
                        ReviewCitation(
                            surface_key=r.surface_key,
                            field=r.field,
                            quote=r.source_quote,
                        )
                    ],
                )
            )
            continue
        if r.source_entity_key not in entities or r.target_entity_key not in entities:
            raise ValueError("observation endpoint is not a supplied entity")
        quote_present(r.source_quote, slot[r.field])
        quote_present(r.target_quote, slot[r.field])
        declared = slot["relation"]
        if (r.source_entity_key, r.target_entity_key) != (
            declared["source_entity_key"],
            declared["target_entity_key"],
        ):
            derived.append(
                GroundedReviewIssue(
                    surface_key=r.surface_key,
                    issue_code="relation_mismatch",
                    detail=f"{r.field} observed {r.source_entity_key}->{r.target_entity_key}, declared "
                    f"{declared['source_entity_key']}->{declared['target_entity_key']}: {r.explanation}",
                    citations=[
                        ReviewCitation(
                            surface_key=r.surface_key,
                            field=r.field,
                            quote=r.source_quote,
                        ),
                        ReviewCitation(
                            surface_key=r.surface_key,
                            field=r.field,
                            quote=r.target_quote,
                        ),
                        ReviewCitation(
                            surface_key=r.surface_key,
                            field="relation.source_entity_key",
                            quote=declared["source_entity_key"],
                        ),
                        ReviewCitation(
                            surface_key=r.surface_key,
                            field="relation.target_entity_key",
                            quote=declared["target_entity_key"],
                        ),
                    ],
                )
            )
    # Aggregate same-key/code provenance; never drop different codes or false positives.
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for source, issues in (
        ("model_issue", review.issues),
        ("host_observation_comparison", derived),
    ):
        for issue in issues:
            key = (issue.surface_key, issue.issue_code)
            item = issue.model_dump(mode="json")
            if key not in merged:
                merged[key] = {**item, "sources": [source]}
            else:
                merged[key]["detail"] += " | " + item["detail"]
                merged[key]["citations"].extend(item["citations"])
                if source not in merged[key]["sources"]:
                    merged[key]["sources"].append(source)
    return review, list(merged.values())

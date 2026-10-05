"""Author, review, and compile a separately bound pre-retrieval corpus revision."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks import evidence_rich_blind_compile as compile_runner
from benchmarks import evidence_rich_blind_review as review_runner
from benchmarks.build_evidence_rich_blind_manifest import (
    build_manifest as build_original,
)
from benchmarks.build_evidence_rich_blind_manifest_v2 import RELATIONS, build_manifest
from benchmarks.evidence_rich_blind_acquire_v7 import ScopeSurfaceUniquenessRegistry
from benchmarks.evidence_rich_blind_authoring import (
    OwnerAuthoringBatch,
    OwnerSurfaceDraft,
    OwnerSurfaceReview,
    ProjectedOwnerSurfaces,
    build_authoring_request,
    build_review_request,
    project_owner_surfaces,
    split_owner_authoring_batches,
    validate_surface_review,
)
from doppel_memory.intelligence import StructuredGenerationRequest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/doppel"
AUTHORED = DATA / "evidence-rich-blind-v1-revised-authored-surfaces.json"
REVIEW = DATA / "evidence-rich-blind-v1-revised-review.json"
PARENT_AUTHORED = acquire.DEFAULT_OUTPUT
PARENT_REVIEW = review_runner.DEFAULT_OUTPUT
MAX_ATTEMPTS = 6

AUTHORING_INSTRUCTIONS = """Write natural Chinese surfaces for the frozen slots.
Return every opaque surface_key exactly once. Entity names must fit the declared type,
be pairwise distinct within this owner, and preserve required_display_name exactly.
Relation content and edge_fact must both refer to the exact supplied source and target
entity names and express the supplied relation meaning. Do not substitute a merely
similar object. Historical relations must be explicitly historical in both strings.
Questions must ask for the requested value, use the intended object, time and operation,
and never include an answer or assert that the answer is unknown.
You may choose natural synthetic names, places and concrete details left unspecified
by a brief, provided they are consistent with every other slot and do not change the
relation, endpoint, time, operation, number of completed events, or question target.
Memory content and non-empty edge facts must be unique within the owner, including
the supplied previously accepted wording. Cross-owner equality is permitted.
For non-relation memories edge_fact must be empty. Use the nonce only as a variation
seed; never mention the nonce, opaque key, retry, or internal schema in surface text.
When must_change_surface_keys is non-empty, naturally rewrite the colliding surfaces.
Never output scope, identity, authority, lifecycle, evidence labels, answerability,
relation types, validity intervals, or fields outside the surface output schema.
"""

REVIEW_INSTRUCTIONS = """Independently review all supplied Chinese surfaces.
Include every supplied surface_key exactly once in reviewed_surface_keys. Report only
concrete contradictions or operation/endpoint/time/type errors. Do not rewrite text.
The briefs intentionally leave natural synthetic names and some concrete details open:
such choices are allowed when consistent. A specific health fact or travel destination
is not an error merely because a brief permits several choices. Do not report a
synonym or correct paraphrase as drift. Relation meanings supplied in this request are
semantic descriptions: held/kept/in custody can express HELD_BY, and association can
express RELATED_TO without spelling the English code. Check direction and exact named
endpoints. Distinguish current from explicitly expired historical relations; their
coexistence is not a contradiction. Time is assessed against the supplied natural
briefs and temporal_view, not invented assumptions about hidden metadata.
A question must ask for the intended value, not substitute a document or object name
for that value. Questions must not state their answer or whether an answer exists;
do not demand such a statement. Do not infer private labels or retrieval results.
Report concrete inconsistencies using the existing issue codes; acceptable slots still
require coverage. Return only the schema fields, with no rewritten surfaces.
"""


def _meanings() -> dict[str, str]:
    return {key: spec.meaning for key, spec in RELATIONS.items()}


def build_authoring_request_v2(
    batch: OwnerAuthoringBatch,
    *,
    variation_attempt: int = 0,
    must_change_surface_keys: tuple[str, ...] = (),
    inherited_memory_texts: tuple[str, ...] = (),
) -> StructuredGenerationRequest:
    request = build_authoring_request(
        batch,
        variation_attempt=variation_attempt,
        must_change_surface_keys=must_change_surface_keys,
    )
    nonce = hashlib.sha256(
        f"blind-revision-v2:{batch.batch_id}:{variation_attempt}".encode()
    ).hexdigest()[:24]
    return request.model_copy(
        update={
            "instructions": AUTHORING_INSTRUCTIONS,
            "input": {
                **request.input,
                "authoring_nonce": nonce,
                "contract_revision": "pre-retrieval-v2",
                "relation_meanings": _meanings(),
                "previously_accepted_owner_memory_texts": list(inherited_memory_texts),
            },
        }
    )


def build_review_request_v2(
    batch: OwnerAuthoringBatch, draft: OwnerSurfaceDraft
) -> StructuredGenerationRequest:
    request = build_review_request(batch, draft)
    return request.model_copy(
        update={
            "instructions": REVIEW_INSTRUCTIONS,
            "input": {
                **request.input,
                "contract_revision": "pre-retrieval-v2",
                "relation_meanings": _meanings(),
            },
        }
    )


def load_parent_seed(
    authored_path: Path, review_path: Path
) -> tuple[dict[str, ProjectedOwnerSurfaces], dict[str, Any]]:
    """Reuse only byte-identical batches whose complete original review is issue-free."""
    original = build_original()
    authored = review_runner._load_authored_surfaces(authored_path, original)
    compile_runner._validate_authored(original, authored)
    review = json.loads(review_path.read_text("utf-8"))
    if (
        review.get("status") != "reviewed_rejected"
        or review.get("accepted") is not False
        or review.get("review_complete") is not True
        or review.get("retrieval_opened") is not False
        or review.get("auto_rewrite_performed") is not False
        or review.get("manifest_fingerprint") != original.fingerprint
        or review.get("authored_surfaces_sha256") != acquire._sha256(authored_path)
    ):
        raise ValueError(
            "revision requires a complete rejected review bound to the original artifact"
        )
    original_batches = [
        b for o in original.owners for b in split_owner_authoring_batches(o)
    ]
    rows = review.get("batches", [])
    by_id = {row["batch_id"]: row for row in rows}
    if (
        len(by_id) != len(rows)
        or review.get("batch_count") != len(original_batches)
        or set(by_id) != {b.batch_id for b in original_batches}
    ):
        raise ValueError("parent review batch coverage mismatch")
    for batch in original_batches:
        row = by_id[batch.batch_id]
        keys = sorted(
            x.surface_key for x in [*batch.entities, *batch.memories, *batch.queries]
        )
        if (
            row["owner_key"] != batch.owner_key
            or row["reviewed_surface_count"] != len(keys)
            or row["reviewed_surface_keys_sha256"] != acquire._fingerprint(keys)
            or row["issue_count"] != len(row["issues"])
        ):
            raise ValueError("parent review surface coverage mismatch")
        validate_surface_review(
            batch, OwnerSurfaceReview(reviewed_surface_keys=keys, issues=row["issues"])
        )
    if review.get("issue_count") != sum(row["issue_count"] for row in rows):
        raise ValueError("parent review issue accounting mismatch")
    old_by_id = {b.batch_id: b for b in original_batches}
    seeds = {}
    for owner in build_manifest().owners:
        for batch in split_owner_authoring_batches(owner):
            prior = old_by_id.get(batch.batch_id)
            if prior == batch and by_id[batch.batch_id]["issue_count"] == 0:
                seeds[batch.batch_id] = project_owner_surfaces(
                    batch, review_runner._draft_for_batch(batch, authored)
                )
    parents = {
        "authored_sha256": acquire._sha256(authored_path),
        "review_sha256": acquire._sha256(review_path),
        "original_manifest_fingerprint": original.fingerprint,
        "seed_batch_ids": sorted(seeds),
        "original_authoring_calls": authored["acquisition"]["provider_calls"],
        "original_review_calls": review["acquisition"]["provider_calls"],
    }
    return seeds, parents


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    stages = result.add_subparsers(dest="stage", required=True)
    author = stages.add_parser("author", parents=[acquire.parser()], add_help=False)
    author.add_argument("--parent-authored", type=Path, default=PARENT_AUTHORED)
    author.add_argument("--parent-review", type=Path, default=PARENT_REVIEW)
    author.set_defaults(
        cache_dir=DATA / "evidence-rich-blind-v1-revised-authoring-cache",
        progress_output=DATA / "evidence-rich-blind-v1-revised-authoring-progress.json",
        output=AUTHORED,
    )
    review = stages.add_parser(
        "review", parents=[review_runner.parser()], add_help=False
    )
    review.set_defaults(
        authored_surfaces=AUTHORED,
        cache_dir=DATA / "evidence-rich-blind-v1-revised-review-cache",
        progress_output=DATA / "evidence-rich-blind-v1-revised-review-progress.json",
        output=REVIEW,
    )
    compiler = stages.add_parser(
        "compile", parents=[compile_runner.parser()], add_help=False
    )
    compiler.set_defaults(
        authored_surfaces=AUTHORED,
        review=REVIEW,
        output=DATA / "evidence-rich-blind-v1-revised-corpus.json",
        report=DATA / "evidence-rich-blind-v1-revised-compile-report.json",
    )
    return result


async def run(args: argparse.Namespace) -> int:
    if args.stage == "author":
        seeds, parents = load_parent_seed(args.parent_authored, args.parent_review)
        texts_by_owner = {
            batch.owner_key: tuple(seeds[batch.batch_id].memory_content_by_id.values())
            for owner in build_manifest().owners
            for batch in split_owner_authoring_batches(owner)
            if batch.batch_id in seeds
        }

        def request_builder(
            batch: OwnerAuthoringBatch, **kwargs: Any
        ) -> StructuredGenerationRequest:
            return build_authoring_request_v2(
                batch,
                inherited_memory_texts=texts_by_owner.get(batch.owner_key, ()),
                **kwargs,
            )

        return await acquire.run(
            args,
            manifest_factory=build_manifest,
            request_builder=request_builder,
            registry_factory=ScopeSurfaceUniquenessRegistry,
            runner="doppel.evidence-rich-blind-revision-authoring.v2",
            maximum_attempts=MAX_ATTEMPTS,
            seed_batches=seeds,
            parents=parents,
        )
    if args.stage == "review":
        return await review_runner.run(
            args,
            manifest_factory=build_manifest,
            request_builder=build_review_request_v2,
            runner="doppel.evidence-rich-blind-review.v2",
        )
    return compile_runner.run(args, manifest_factory=build_manifest)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

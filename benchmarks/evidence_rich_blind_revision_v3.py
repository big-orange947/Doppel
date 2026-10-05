"""Resume the unopened corpus after diagnosing contradictory authoring briefs."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks import evidence_rich_blind_acquire as acquire
from benchmarks import evidence_rich_blind_revision as v2
from benchmarks.evidence_rich_blind_acquire_v5 import ReadOnlyParentCache
from benchmarks.evidence_rich_blind_acquire_v7 import ScopeSurfaceUniquenessRegistry
from benchmarks.evidence_rich_blind_authoring import (
    BlindCorpusAuthoringManifest,
    OwnerAuthoringBatch,
    OwnerSurfaceDraft,
    ProjectedOwnerSurfaces,
    project_owner_surfaces,
    split_owner_authoring_batches,
)
from benchmarks.relation_planner_quality import PROVIDER_OUTPUT_CACHE_NAMESPACE
from doppel_memory.intelligence import StructuredGenerationRequest

DATA = v2.DATA
DEFAULT_PARENT_CACHE = DATA / "evidence-rich-blind-v1-revised-authoring-cache"
AUTHORED = DATA / "evidence-rich-blind-v1-revised-v3-authored-surfaces.json"
REVIEW = DATA / "evidence-rich-blind-v1-revised-v3-review.json"
RUNNER = "doppel.evidence-rich-blind-revision-authoring.v3"

AUTHORING_INSTRUCTIONS = (
    v2.AUTHORING_INSTRUCTIONS
    + """
First silently allocate one distinct, type-correct name to EVERY entity slot. Different
keys represent different entities, even when their briefs have related roles. A
shared_name_group permits repetition across owners ONLY; within this request its
required_display_name must not be reused for any other key. Different place slots
must use different place names, including residence cities and relation endpoints.
Keep this name table consistent in all memories, edge facts and questions. Before
returning JSON, silently verify the number of unique names equals the entity count,
and verify every relation uses its declared source and target in the right direction.
The previously accepted memory texts are exclusion references, NOT slots to return.
Return ONLY the entities, memories and queries listed in this batch. Do not reuse an
exclusion reference verbatim, and do not copy it into an additional output slot.
Do not output the internal name table, self-audit, or output_contract fields.
"""
)


def build_manifest() -> BlindCorpusAuthoringManifest:
    """Change contradictory prose only; retain all private authority and gold fields."""
    prior = v2.build_manifest()
    owners = []
    for owner in prior.owners:
        memories = []
        for memory in owner.memories:
            if memory.surface_key == "memory-competing-second":
                meaning = v2.RELATIONS[memory.relation_type].meaning
                memory = memory.model_copy(
                    update={
                        "semantic_brief": (
                            f"竞争分支的确切关系为 {memory.source_entity_key} "
                            f"{meaning} {memory.target_entity_key}；正文和边事实必须使用"
                            "这两个端点的同一显示名；不得改指共享别名机构或主要路径终点"
                        )
                    }
                )
            memories.append(memory)
        owners.append(owner.model_copy(update={"memories": memories}))
    return BlindCorpusAuthoringManifest.model_validate(
        {
            **prior.model_dump(mode="json"),
            "version": "1.4.1",
            "suite": "doppel-evidence-rich-blind-zh-v1-revised-v3-host-manifest",
            "owners": [owner.model_dump(mode="json") for owner in owners],
        }
    )


def build_authoring_request(
    batch: OwnerAuthoringBatch, **kwargs: Any
) -> StructuredGenerationRequest:
    request = v2.build_authoring_request_v2(batch, **kwargs)
    nonce = hashlib.sha256(
        f"blind-revision-v3:{batch.batch_id}:{kwargs.get('variation_attempt', 0)}".encode()
    ).hexdigest()[:24]
    return request.model_copy(
        update={
            "instructions": AUTHORING_INSTRUCTIONS,
            "input": {
                **request.input,
                "authoring_nonce": nonce,
                "contract_revision": "pre-retrieval-v3",
                "output_contract": {
                    "entity_count": len(batch.entities),
                    "distinct_entity_name_count": len(batch.entities),
                    "memory_count": len(batch.memories),
                    "query_count": len(batch.queries),
                    "inherited_texts_are_reference_only": True,
                },
            },
        }
    )


def build_review_request(
    batch: OwnerAuthoringBatch, draft: OwnerSurfaceDraft
) -> StructuredGenerationRequest:
    # Same semantic-review instructions as V2, but with the corrected V3 host briefs.
    request = v2.build_review_request_v2(batch, draft)
    return request.model_copy(
        update={"input": {**request.input, "contract_revision": "pre-retrieval-v3"}}
    )


def _surface_compatible(old: OwnerAuthoringBatch, new: OwnerAuthoringBatch) -> bool:
    def without_briefs(batch: OwnerAuthoringBatch) -> dict[str, Any]:
        raw = batch.model_dump(mode="json")
        for kind in ("entities", "memories", "queries"):
            for item in raw[kind]:
                item.pop("semantic_brief")
        return raw

    return without_briefs(old) == without_briefs(new)


def load_parent_seed(
    cache_dir: Path, authored_path: Path, review_path: Path
) -> tuple[dict[str, ProjectedOwnerSurfaces], dict[str, Any]]:
    """Replay the exact V2 attempt history, not later lucky or rewritten candidates."""
    inherited, original_parents = v2.load_parent_seed(authored_path, review_path)
    manifest_path = cache_dir / acquire.MANIFEST_NAME
    state_path = cache_dir / acquire.STATE_NAME
    binding = json.loads(manifest_path.read_text("utf-8"))
    state = json.loads(state_path.read_text("utf-8"))
    old_batches = [
        b for o in v2.build_manifest().owners for b in split_owner_authoring_batches(o)
    ]
    if (
        binding.get("runner") != "doppel.evidence-rich-blind-revision-authoring.v2"
        or binding.get("mode") != "sealed_surface_authoring"
        or binding.get("manifest_fingerprint") != v2.build_manifest().fingerprint
        or binding.get("parents") != original_parents
        or binding.get("seed_batch_count") != len(inherited)
        or binding.get("batch_ids") != [b.batch_id for b in old_batches]
        or binding.get("maximum_attempts_per_batch") != v2.MAX_ATTEMPTS
        or binding.get("memory_batch_size") != acquire.MEMORY_BATCH_SIZE
        or state.get("binding_sha256") != acquire._fingerprint(binding)
        or state.get("batch_count") != len(old_batches)
        or binding.get("retrieval_enabled") is not False
        or binding.get("quality_metrics_available") is not False
    ):
        raise ValueError("V2 parent binding mismatch")
    cache = ReadOnlyParentCache(cache_dir, binding["provider"])
    registry = ScopeSurfaceUniquenessRegistry()
    texts = {}
    for batch in old_batches:
        if batch.batch_id in inherited:
            seed = inherited[batch.batch_id]
            registry.add(batch, seed)
            texts[batch.owner_key] = tuple(seed.memory_content_by_id.values())
    selected = dict(inherited)
    accepted_attempts = {}
    failures: Counter[str] = Counter()
    stopped_at = ""
    for batch in old_batches:
        if batch.batch_id in inherited:
            continue
        change: tuple[str, ...] = ()
        for attempt in range(v2.MAX_ATTEMPTS):
            request = v2.build_authoring_request_v2(
                batch,
                variation_attempt=attempt,
                must_change_surface_keys=change,
                inherited_memory_texts=texts.get(batch.owner_key, ()),
            )
            raw = cache.get(request)
            if raw is None:
                break
            try:
                candidate = project_owner_surfaces(batch, raw)
                nonce = request.input["authoring_nonce"]
                if any(
                    nonce in text
                    for values in candidate.model_dump(mode="json").values()
                    for text in values.values()
                ):
                    raise ValueError("authored surface exposes the variation nonce")
            except ValueError as exc:
                # Only an opaque diagnostic code is persisted, never raw model text.
                code = (
                    "duplicate_entity_name"
                    if str(exc)
                    == "entity display names must be unique within one owner"
                    else "other_surface_validation"
                )
                failures[code] += 1
                change = tuple(
                    sorted(
                        x.surface_key
                        for x in [*batch.entities, *batch.memories, *batch.queries]
                    )
                )
                continue
            change = registry.collisions(batch, candidate)
            if change:
                failures["surface_collision"] += 1
                continue
            registry.add(batch, candidate)
            selected[batch.batch_id] = candidate
            accepted_attempts[batch.batch_id] = attempt + 1
            break
        if batch.batch_id not in selected:
            stopped_at = batch.batch_id
            break
    if (
        accepted_attempts != state.get("accepted_attempts_by_batch")
        or len(selected) != state.get("completed_batch_count")
        or (len(selected) == len(old_batches)) != state.get("complete")
        or stopped_at != state.get("last_invocation", {}).get("stopped_at_batch_id")
    ):
        raise ValueError("V2 parent replay does not match recorded progress")
    new_batches = {
        b.batch_id: b
        for owner in build_manifest().owners
        for b in split_owner_authoring_batches(owner)
    }
    for batch in old_batches:
        if batch.batch_id in selected and not _surface_compatible(
            batch, new_batches[batch.batch_id]
        ):
            raise ValueError("V3 seed changes private authority or structural fields")
    files = sorted((cache_dir / PROVIDER_OUTPUT_CACHE_NAMESPACE).glob("*/*.json"))
    if cache.hits != len(files):
        raise ValueError("V2 parent replay left unexplained provider cache entries")
    snapshot = {
        "runner": binding["runner"],
        "manifest_sha256": acquire._sha256(manifest_path),
        "state_sha256": acquire._sha256(state_path),
        "manifest_fingerprint": binding["manifest_fingerprint"],
        "provider_cache_entry_count": len(files),
        "provider_cache_sha256": acquire._fingerprint(
            [(p.relative_to(cache_dir).as_posix(), acquire._sha256(p)) for p in files]
        ),
        "provider_calls": state["provider_calls"],
        "usage": state["usage"],
        "accepted_attempts_by_batch": accepted_attempts,
        "replayed_failure_counts": dict(sorted(failures.items())),
        "seed_batch_ids": sorted(selected),
        "seed_semantic_review_pending": True,
    }
    return selected, {"original": original_parents, "revision_v2": snapshot}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    stages = result.add_subparsers(dest="stage", required=True)
    author = stages.add_parser("author", parents=[acquire.parser()], add_help=False)
    author.add_argument("--parent-authored", type=Path, default=v2.PARENT_AUTHORED)
    author.add_argument("--parent-review", type=Path, default=v2.PARENT_REVIEW)
    review = stages.add_parser(
        "review", parents=[v2.review_runner.parser()], add_help=False
    )
    compiler = stages.add_parser(
        "compile", parents=[v2.compile_runner.parser()], add_help=False
    )
    author.add_argument("--parent-cache-dir", type=Path, default=DEFAULT_PARENT_CACHE)
    author.set_defaults(
        cache_dir=DATA / "evidence-rich-blind-v1-revised-v3-authoring-cache",
        progress_output=DATA
        / "evidence-rich-blind-v1-revised-v3-authoring-progress.json",
        output=AUTHORED,
    )
    review.set_defaults(
        authored_surfaces=AUTHORED,
        cache_dir=DATA / "evidence-rich-blind-v1-revised-v3-review-cache",
        progress_output=DATA / "evidence-rich-blind-v1-revised-v3-review-progress.json",
        output=REVIEW,
    )
    compiler.set_defaults(
        authored_surfaces=AUTHORED,
        review=REVIEW,
        output=DATA / "evidence-rich-blind-v1-revised-v3-corpus.json",
        report=DATA / "evidence-rich-blind-v1-revised-v3-compile-report.json",
    )
    return result


async def run(args: argparse.Namespace) -> int:
    if args.stage == "author":
        seeds, parents = load_parent_seed(
            args.parent_cache_dir, args.parent_authored, args.parent_review
        )
        texts_by_owner = {}
        for owner in build_manifest().owners:
            texts_by_owner[owner.owner_key] = tuple(
                text
                for b in split_owner_authoring_batches(owner)
                if b.batch_id in seeds
                for text in seeds[b.batch_id].memory_content_by_id.values()
            )

        def builder(
            batch: OwnerAuthoringBatch, **kwargs: Any
        ) -> StructuredGenerationRequest:
            return build_authoring_request(
                batch, inherited_memory_texts=texts_by_owner[batch.owner_key], **kwargs
            )

        return await acquire.run(
            args,
            manifest_factory=build_manifest,
            request_builder=builder,
            registry_factory=ScopeSurfaceUniquenessRegistry,
            runner=RUNNER,
            maximum_attempts=v2.MAX_ATTEMPTS,
            seed_batches=seeds,
            parents=parents,
        )
    if args.stage == "review":
        return await v2.review_runner.run(
            args,
            manifest_factory=build_manifest,
            request_builder=build_review_request,
            runner="doppel.evidence-rich-blind-review.v3",
        )
    return v2.compile_runner.run(args, manifest_factory=build_manifest)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

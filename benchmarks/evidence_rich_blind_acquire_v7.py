"""Continue blind authoring with scope-local evidence uniqueness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import benchmarks.evidence_rich_blind_acquire as v4
import benchmarks.evidence_rich_blind_acquire_v5 as v5
import benchmarks.evidence_rich_blind_acquire_v6 as v6
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    OwnerAuthoringBatch,
    ProjectedOwnerSurfaces,
    build_authoring_request,
    build_authoring_request_v5,
    build_authoring_request_v6,
    project_owner_surfaces,
    split_owner_authoring_batches,
)
from benchmarks.relation_planner_quality import (
    PROVIDER_OUTPUT_CACHE_NAMESPACE,
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_V4_CACHE = v4.DEFAULT_CACHE
DEFAULT_V5_CACHE = v5.DEFAULT_CACHE
DEFAULT_V6_CACHE = v6.DEFAULT_CACHE
DEFAULT_CACHE = ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v7-cache"
DEFAULT_PROGRESS = ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v7-progress.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-authored-surfaces.json"
RUNNER = "doppel.evidence-rich-blind-authoring.v7"
MEMORY_BATCH_SIZE = v4.MEMORY_BATCH_SIZE
MAX_AUTHORING_ATTEMPTS = v6.MAX_AUTHORING_ATTEMPTS


class ScopeSurfaceUniquenessRegistry:
    """Reject evidence repetition inside one owner while preserving isolation pressure."""

    def __init__(self) -> None:
        self._memory_contents: defaultdict[str, set[str]] = defaultdict(set)
        self._edge_facts: defaultdict[str, set[str]] = defaultdict(set)

    def collisions(
        self, batch: OwnerAuthoringBatch, surfaces: ProjectedOwnerSurfaces
    ) -> tuple[str, ...]:
        collisions: set[str] = set()
        local_memories = set(self._memory_contents[batch.scope])
        local_edges = set(self._edge_facts[batch.scope])
        for memory in batch.memories:
            content = surfaces.memory_content_by_id[memory.memory_id]
            if content in local_memories:
                collisions.add(memory.surface_key)
            local_memories.add(content)
            edge_fact = surfaces.edge_fact_by_memory_id[memory.memory_id]
            if edge_fact:
                if edge_fact in local_edges:
                    collisions.add(memory.surface_key)
                local_edges.add(edge_fact)
        return tuple(sorted(collisions))

    def add(
        self, batch: OwnerAuthoringBatch, surfaces: ProjectedOwnerSurfaces
    ) -> None:
        collisions = self.collisions(batch, surfaces)
        if collisions:
            raise ValueError(f"cannot register duplicate surfaces: {list(collisions)}")
        for memory in batch.memories:
            self._memory_contents[batch.scope].add(
                surfaces.memory_content_by_id[memory.memory_id]
            )
            edge_fact = surfaces.edge_fact_by_memory_id[memory.memory_id]
            if edge_fact:
                self._edge_facts[batch.scope].add(edge_fact)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live-authoring", action="store_true")
    result.add_argument("--v4-cache-dir", type=Path, default=DEFAULT_V4_CACHE)
    result.add_argument("--v5-cache-dir", type=Path, default=DEFAULT_V5_CACHE)
    result.add_argument("--v6-cache-dir", type=Path, default=DEFAULT_V6_CACHE)
    result.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    result.add_argument("--progress-output", type=Path, default=DEFAULT_PROGRESS)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--max-new-calls", type=int, default=0)
    result.add_argument(
        "--model", default=os.environ.get("DOPPEL_MODEL", "deepseek-v4-flash")
    )
    result.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    result.add_argument(
        "--schema-mode",
        choices=("json_object", "json_schema"),
        default=os.environ.get("DOPPEL_SCHEMA_MODE", "json_object"),
    )
    result.add_argument("--max-completion-tokens", type=int, default=8192)
    result.add_argument("--timeout-seconds", type=float, default=120.0)
    return result


async def run(args: argparse.Namespace) -> int:
    if args.max_new_calls < 0:
        raise ValueError("max-new-calls must not be negative")
    manifest = build_manifest()
    batches = [
        batch
        for owner in manifest.owners
        for batch in split_owner_authoring_batches(
            owner, memory_batch_size=MEMORY_BATCH_SIZE
        )
    ]
    v4_manifest, _, v4_snapshot = v5._load_parent(
        args.v4_cache_dir, manifest.fingerprint, batches
    )
    v5_manifest, _, v5_snapshot = v6._load_v5_parent(
        args.v5_cache_dir,
        manifest_fingerprint=manifest.fingerprint,
        batches=batches,
        v4_snapshot=v4_snapshot,
    )
    v6_manifest, v6_state, v6_snapshot = _load_v6_parent(
        args.v6_cache_dir,
        manifest_fingerprint=manifest.fingerprint,
        batches=batches,
        earlier_parents={"v4": v4_snapshot, "v5": v5_snapshot},
    )
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
        timeout_seconds=args.timeout_seconds,
    )
    for parent_manifest in (v4_manifest, v5_manifest, v6_manifest):
        v5._require_parent_config(parent_manifest, config)
    parents = {"v4": v4_snapshot, "v5": v5_snapshot, "v6": v6_snapshot}
    plan = {
        "runner": RUNNER,
        "mode": "live_authoring" if args.live_authoring else "dry_run",
        "manifest_fingerprint": manifest.fingerprint,
        "owner_count": len(manifest.owners),
        "batch_count": len(batches),
        "memory_batch_size": MEMORY_BATCH_SIZE,
        "maximum_attempts_per_batch": MAX_AUTHORING_ATTEMPTS,
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "provider_retries": 0,
        "evidence_uniqueness": "scope_local",
        "retrieval_enabled": False,
        "quality_metrics_available": False,
        "implementation_commit": v4._git_commit_hash(),
        "parents": parents,
    }
    if not args.live_authoring:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists():
        raise ValueError("completed authoring output already exists")
    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key and args.max_new_calls > 0:
        raise RuntimeError("DOPPEL_API_KEY is required for new provider calls")

    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        config,
        api_key=key or "cache-only-no-network",
        usage_observer=usage.observe,
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_new_calls)
    current = CachedStructuredOutputModel(budget, args.cache_dir)
    parent_v4 = v5.ReadOnlyParentCache(args.v4_cache_dir, v4_manifest["provider"])
    parent_v5 = v5.ReadOnlyParentCache(args.v5_cache_dir, v5_manifest["provider"])
    parent_v6 = v5.ReadOnlyParentCache(args.v6_cache_dir, v6_manifest["provider"])
    binding_plan = dict(plan)
    binding_plan.pop("maximum_new_calls_this_invocation")
    binding = {
        **binding_plan,
        "mode": "sealed_surface_authoring_continuation",
        "batch_ids": [batch.batch_id for batch in batches],
        "provider": {"name": current.name, "version": current.version},
    }
    manifest_path = args.cache_dir / v4.MANIFEST_NAME
    state_path = args.cache_dir / v4.STATE_NAME
    v4._bind_manifest(manifest_path, binding)
    prior_state = v4._load_state(state_path)
    if prior_state and prior_state.get("parents_sha256") != v4._fingerprint(parents):
        raise ValueError("V7 state is bound to different parent provider caches")

    completed: list[str] = []
    accepted_attempts: dict[str, int] = {}
    projected_by_owner: defaultdict[str, list[ProjectedOwnerSurfaces]] = defaultdict(
        list
    )
    registry = ScopeSurfaceUniquenessRegistry()
    collision_attempts = 0
    validation_rejection_attempts = 0
    stopped_reason = ""
    stopped_at = ""
    try:
        for batch in batches:
            must_change: tuple[str, ...] = ()
            accepted: ProjectedOwnerSurfaces | None = None
            for attempt in range(MAX_AUTHORING_ATTEMPTS):
                try:
                    candidate = await _candidate(
                        batch,
                        attempt=attempt,
                        must_change=must_change,
                        parent_v4=parent_v4,
                        parent_v5=parent_v5,
                        parent_v6=parent_v6,
                        current=current,
                    )
                except v5.ParentCacheIntegrityError:
                    raise
                except PlannerCallBudgetExceeded:
                    stopped_reason = "budget_exhausted"
                    stopped_at = batch.batch_id
                    break
                except ValueError:
                    validation_rejection_attempts += 1
                    must_change = tuple(
                        sorted(
                            item.surface_key
                            for item in [
                                *batch.entities,
                                *batch.memories,
                                *batch.queries,
                            ]
                        )
                    )
                    continue
                except Exception as exc:  # noqa: BLE001 - provider details stay private
                    stopped_reason = type(exc).__name__
                    stopped_at = batch.batch_id
                    break
                must_change = registry.collisions(batch, candidate)
                if must_change:
                    collision_attempts += 1
                    continue
                registry.add(batch, candidate)
                accepted = candidate
                accepted_attempts[batch.batch_id] = attempt + 1
                break
            if stopped_reason:
                break
            if accepted is None:
                stopped_reason = "SurfaceGenerationExhausted"
                stopped_at = batch.batch_id
                break
            projected_by_owner[batch.owner_key].append(accepted)
            completed.append(batch.batch_id)
    finally:
        await provider.aclose()

    baseline_usage = prior_state.get("usage", v6_state.get("usage", {}))
    baseline_calls = int(
        prior_state.get("provider_calls", v6_state.get("provider_calls", 0))
    )
    cumulative_usage = v4._merge_usage(baseline_usage, usage.report())
    cumulative_calls = baseline_calls + budget.calls
    complete = len(completed) == len(batches) and not stopped_reason
    last_invocation = {
        "provider_calls": budget.calls,
        "v4_cache_hits": parent_v4.hits,
        "v4_cache_misses": parent_v4.misses,
        "v4_invalid_cache_entries": parent_v4.invalid_entries,
        "v5_cache_hits": parent_v5.hits,
        "v5_cache_misses": parent_v5.misses,
        "v5_invalid_cache_entries": parent_v5.invalid_entries,
        "v6_cache_hits": parent_v6.hits,
        "v6_cache_misses": parent_v6.misses,
        "v6_invalid_cache_entries": parent_v6.invalid_entries,
        "v7_cache_hits": current.hits,
        "v7_cache_misses": current.misses,
        "v7_invalid_cache_entries": current.invalid_entries_ignored,
        "surface_collision_attempts": collision_attempts,
        "surface_validation_rejection_attempts": validation_rejection_attempts,
        "stopped_reason": stopped_reason,
        "stopped_at_batch_id": stopped_at,
    }
    state = {
        "state_schema_version": 4,
        "binding_sha256": v4._fingerprint(binding),
        "parents_sha256": v4._fingerprint(parents),
        "updated_at": datetime.now(UTC).isoformat(),
        "complete": complete,
        "completed_batch_count": len(completed),
        "batch_count": len(batches),
        "provider_calls": cumulative_calls,
        "usage": cumulative_usage,
        "last_invocation": last_invocation,
        "accepted_attempts_by_batch": accepted_attempts,
    }
    v4._write_json(state_path, state)
    progress = {
        "runner": RUNNER,
        "status": "complete" if complete else "incomplete",
        "manifest_fingerprint": manifest.fingerprint,
        "implementation_commit": plan["implementation_commit"],
        "parents": parents,
        "evidence_uniqueness": "scope_local",
        "completed_batch_count": len(completed),
        "batch_count": len(batches),
        "provider_calls_cumulative": cumulative_calls,
        "usage_cumulative": cumulative_usage,
        "accepted_attempts_by_batch": accepted_attempts,
        "last_invocation": last_invocation,
        "surfaces_available": complete,
        "quality_metrics_available": False,
    }
    v4._write_json(args.progress_output, progress)
    if not complete:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return 0

    owners = [
        v4._merge_owner_surfaces(
            owner.owner_key, projected_by_owner[owner.owner_key]
        )
        for owner in manifest.owners
    ]
    output = {
        "runner": RUNNER,
        "status": "authored_unreviewed",
        "manifest_fingerprint": manifest.fingerprint,
        "implementation_commit": plan["implementation_commit"],
        "binding_sha256": v4._fingerprint(binding),
        "parents": parents,
        "evidence_uniqueness": "scope_local",
        "owner_count": len(owners),
        "owners": owners,
        "acquisition": state,
        "review_complete": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    v4._validate_complete_output(manifest, output)
    v4._write_json(args.output, output)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {v4._sha256(args.output)}")
    print(json.dumps(progress, ensure_ascii=False, sort_keys=True))
    return 0


async def _candidate(
    batch: OwnerAuthoringBatch,
    *,
    attempt: int,
    must_change: tuple[str, ...],
    parent_v4: v5.ReadOnlyParentCache,
    parent_v5: v5.ReadOnlyParentCache,
    parent_v6: v5.ReadOnlyParentCache,
    current: CachedStructuredOutputModel,
) -> ProjectedOwnerSurfaces:
    raw: dict[str, Any] | None = None
    if attempt < v4.MAX_AUTHORING_ATTEMPTS:
        raw = parent_v4.get(
            build_authoring_request(
                batch,
                variation_attempt=attempt,
                must_change_surface_keys=must_change,
            )
        )
    if raw is None and attempt < v5.MAX_AUTHORING_ATTEMPTS:
        raw = parent_v5.get(
            build_authoring_request_v5(
                batch,
                variation_attempt=attempt,
                must_change_surface_keys=must_change,
            )
        )
    if raw is None:
        raw = parent_v6.get(
            build_authoring_request_v6(
                batch,
                variation_attempt=attempt,
                must_change_surface_keys=must_change,
            )
        )
    if raw is not None:
        return project_owner_surfaces(batch, raw)
    request = build_authoring_request_v6(
        batch,
        variation_attempt=attempt,
        must_change_surface_keys=must_change,
    )
    generated = await current.generate(request)
    if isinstance(generated, BaseModel):
        generated = generated.model_dump(mode="json", warnings=False)
    return project_owner_surfaces(batch, generated)


def _load_v6_parent(
    cache_dir: Path,
    *,
    manifest_fingerprint: str,
    batches: list[OwnerAuthoringBatch],
    earlier_parents: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = cache_dir / v4.MANIFEST_NAME
    state_path = cache_dir / v4.STATE_NAME
    if not manifest_path.is_file() or not state_path.is_file():
        raise ValueError("V7 requires the V6 acquisition manifest and state")
    parent_manifest = json.loads(manifest_path.read_text("utf-8"))
    parent_state = json.loads(state_path.read_text("utf-8"))
    if parent_manifest.get("runner") != v6.RUNNER:
        raise ValueError("third parent acquisition runner is not V6")
    if parent_manifest.get("manifest_fingerprint") != manifest_fingerprint:
        raise ValueError("V6 parent manifest fingerprint mismatch")
    if parent_manifest.get("batch_ids") != [batch.batch_id for batch in batches]:
        raise ValueError("V6 parent batch order mismatch")
    if parent_manifest.get("parents") != earlier_parents:
        raise ValueError("V6 parent is not bound to the selected V4/V5 caches")
    if not isinstance(parent_manifest.get("provider"), dict):
        raise TypeError("V6 parent provider identity is missing")
    provider_files = sorted(
        (cache_dir / PROVIDER_OUTPUT_CACHE_NAMESPACE).glob("*/*.json")
    )
    inventory = [
        {"path": path.relative_to(cache_dir).as_posix(), "sha256": v4._sha256(path)}
        for path in provider_files
    ]
    prior_calls = int(earlier_parents["v5"]["provider_calls_cumulative"])
    cumulative_calls = int(parent_state.get("provider_calls", 0))
    new_calls = cumulative_calls - prior_calls
    snapshot = {
        "runner": v6.RUNNER,
        "manifest_sha256": v4._sha256(manifest_path),
        "provider_cache_entry_count": len(inventory),
        "provider_cache_sha256": v4._fingerprint(inventory),
        "new_provider_calls": new_calls,
        "provider_calls_cumulative": cumulative_calls,
        "completed_batch_count": int(parent_state.get("completed_batch_count", 0)),
    }
    if new_calls != len(inventory):
        raise ValueError("V6 new provider call count does not match cache inventory")
    return parent_manifest, parent_state, snapshot


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

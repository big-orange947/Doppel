"""Budgeted, resumable surface authoring for the blind evidence-rich corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    MAX_AUTHORING_ATTEMPTS,
    OwnerAuthoringBatch,
    ProjectedOwnerSurfaces,
    author_owner_surfaces,
    split_owner_authoring_batches,
)
from benchmarks.relation_planner_quality import (
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
DEFAULT_CACHE = ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v4-cache"
DEFAULT_PROGRESS = (
    ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v4-progress.json"
)
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-authored-surfaces.json"
MANIFEST_NAME = "acquisition-manifest.json"
STATE_NAME = "acquisition-state.json"
RUNNER = "doppel.evidence-rich-blind-authoring.v4"
MEMORY_BATCH_SIZE = 96


class SurfaceUniquenessRegistry:
    """Reject repeated evidence text without outlawing realistic scope collisions."""

    def __init__(self) -> None:
        self._memory_contents: set[str] = set()
        self._edge_facts: set[str] = set()

    def collisions(
        self, batch: OwnerAuthoringBatch, surfaces: ProjectedOwnerSurfaces
    ) -> tuple[str, ...]:
        collisions: set[str] = set()
        local_memories = set(self._memory_contents)
        local_edges = set(self._edge_facts)
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
            self._memory_contents.add(surfaces.memory_content_by_id[memory.memory_id])
            edge_fact = surfaces.edge_fact_by_memory_id[memory.memory_id]
            if edge_fact:
                self._edge_facts.add(edge_fact)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live-authoring", action="store_true")
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
    plan = {
        "runner": RUNNER,
        "mode": "live_authoring" if args.live_authoring else "dry_run",
        "manifest_fingerprint": manifest.fingerprint,
        "owner_count": len(manifest.owners),
        "batch_count": len(batches),
        "memory_batch_size": MEMORY_BATCH_SIZE,
        "nominal_uncached_calls": len(batches),
        "maximum_total_uncached_calls": len(batches) * MAX_AUTHORING_ATTEMPTS,
        "maximum_attempts_per_batch": MAX_AUTHORING_ATTEMPTS,
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "provider_retries": 0,
        "retrieval_enabled": False,
        "quality_metrics_available": False,
        "implementation_commit": _git_commit_hash(),
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
    cached = CachedStructuredOutputModel(budget, args.cache_dir)
    binding_plan = dict(plan)
    binding_plan.pop("maximum_new_calls_this_invocation")
    binding = {
        **binding_plan,
        "mode": "sealed_surface_authoring",
        "batch_ids": [batch.batch_id for batch in batches],
        "provider": {"name": cached.name, "version": cached.version},
    }
    manifest_path = args.cache_dir / MANIFEST_NAME
    state_path = args.cache_dir / STATE_NAME
    _bind_manifest(manifest_path, binding)
    prior_state = _load_state(state_path)
    completed: list[str] = []
    accepted_attempts: dict[str, int] = {}
    projected_by_owner: defaultdict[str, list[ProjectedOwnerSurfaces]] = defaultdict(
        list
    )
    registry = SurfaceUniquenessRegistry()
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
                    candidate = await author_owner_surfaces(
                        batch,
                        cached,
                        variation_attempt=attempt,
                        must_change_surface_keys=must_change,
                    )
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

    cumulative_usage = _merge_usage(prior_state.get("usage", {}), usage.report())
    cumulative_calls = int(prior_state.get("provider_calls", 0)) + budget.calls
    complete = len(completed) == len(batches) and not stopped_reason
    state = {
        "state_schema_version": 1,
        "binding_sha256": _fingerprint(binding),
        "updated_at": datetime.now(UTC).isoformat(),
        "complete": complete,
        "completed_batch_count": len(completed),
        "batch_count": len(batches),
        "provider_calls": cumulative_calls,
        "usage": cumulative_usage,
        "last_invocation": {
            "provider_calls": budget.calls,
            "cache_hits": cached.hits,
            "cache_misses": cached.misses,
            "invalid_cache_entries": cached.invalid_entries_ignored,
            "surface_collision_attempts": collision_attempts,
            "surface_validation_rejection_attempts": validation_rejection_attempts,
            "stopped_reason": stopped_reason,
            "stopped_at_batch_id": stopped_at,
        },
        "accepted_attempts_by_batch": accepted_attempts,
    }
    _write_json(state_path, state)
    progress = {
        "runner": RUNNER,
        "status": "complete" if complete else "incomplete",
        "manifest_fingerprint": manifest.fingerprint,
        "implementation_commit": plan["implementation_commit"],
        "completed_batch_count": len(completed),
        "batch_count": len(batches),
        "provider_calls_cumulative": cumulative_calls,
        "usage_cumulative": cumulative_usage,
        "accepted_attempts_by_batch": accepted_attempts,
        "last_invocation": state["last_invocation"],
        "surfaces_available": complete,
        "quality_metrics_available": False,
    }
    _write_json(args.progress_output, progress)
    if not complete:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return 0

    owners = [
        _merge_owner_surfaces(owner.owner_key, projected_by_owner[owner.owner_key])
        for owner in manifest.owners
    ]
    output = {
        "runner": RUNNER,
        "status": "authored_unreviewed",
        "manifest_fingerprint": manifest.fingerprint,
        "implementation_commit": plan["implementation_commit"],
        "binding_sha256": _fingerprint(binding),
        "owner_count": len(owners),
        "owners": owners,
        "acquisition": state,
        "review_complete": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _validate_complete_output(manifest, output)
    _write_json(args.output, output)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {_sha256(args.output)}")
    print(json.dumps(progress, ensure_ascii=False, sort_keys=True))
    return 0


def _merge_owner_surfaces(
    owner_key: str, parts: list[ProjectedOwnerSurfaces]
) -> dict[str, Any]:
    fields = (
        "entity_names_by_id",
        "memory_content_by_id",
        "edge_fact_by_memory_id",
        "query_text_by_case_id",
    )
    merged: dict[str, Any] = {"owner_key": owner_key}
    for field in fields:
        target: dict[str, str] = {}
        for part in parts:
            source = getattr(part, field)
            overlap = set(target).intersection(source)
            if overlap:
                raise ValueError(f"duplicate projected surface IDs: {sorted(overlap)}")
            target.update(source)
        merged[field] = target
    return merged


def _validate_complete_output(manifest: Any, output: dict[str, Any]) -> None:
    owners = {item["owner_key"]: item for item in output["owners"]}
    if set(owners) != {owner.owner_key for owner in manifest.owners}:
        raise ValueError("authored output owner set mismatch")
    for owner in manifest.owners:
        actual = owners[owner.owner_key]
        expected = {
            "entity_names_by_id": {item.entity_id for item in owner.entities},
            "memory_content_by_id": {item.memory_id for item in owner.memories},
            "edge_fact_by_memory_id": {item.memory_id for item in owner.memories},
            "query_text_by_case_id": {item.case_id for item in owner.queries},
        }
        for field, keys in expected.items():
            if set(actual[field]) != keys:
                raise ValueError(f"authored output {field} is incomplete")


def _bind_manifest(path: Path, binding: dict[str, Any]) -> None:
    if path.exists():
        existing = json.loads(path.read_text("utf-8"))
        if existing != binding:
            raise ValueError("authoring manifest does not match current binding")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    unexpected = [item for item in path.parent.iterdir() if item.name != path.name]
    if unexpected:
        raise ValueError("new sealed authoring requires an empty cache directory")
    _write_json(path, binding)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("authoring state must be an object")
    return raw


def _merge_usage(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, int]:
    names = set(previous).union(current)
    return {
        name: int(previous.get(name, 0)) + int(current.get(name, 0))
        for name in sorted(names)
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    os.replace(temporary, path)


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit_hash() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

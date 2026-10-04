"""Continue sealed blind-corpus authoring from an immutable V4 cache."""

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
from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_authoring import (
    MAX_AUTHORING_ATTEMPTS as V4_MAX_AUTHORING_ATTEMPTS,
)
from benchmarks.evidence_rich_blind_authoring import (
    OwnerAuthoringBatch,
    ProjectedOwnerSurfaces,
    build_authoring_request,
    build_authoring_request_v5,
    project_owner_surfaces,
    split_owner_authoring_batches,
)
from benchmarks.relation_planner_quality import (
    PROVIDER_OUTPUT_CACHE_FORMAT_VERSION,
    PROVIDER_OUTPUT_CACHE_NAMESPACE,
    PROVIDER_OUTPUT_CACHE_SCHEMA,
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)

ROOT = Path(__file__).resolve().parents[1]
PARENT_RUNNER = v4.RUNNER
DEFAULT_PARENT_CACHE = v4.DEFAULT_CACHE
DEFAULT_CACHE = ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v5-cache"
DEFAULT_PROGRESS = ROOT / "data/doppel/evidence-rich-blind-v1-authoring-v5-progress.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-authored-surfaces.json"
RUNNER = "doppel.evidence-rich-blind-authoring.v5"
MEMORY_BATCH_SIZE = v4.MEMORY_BATCH_SIZE
MAX_AUTHORING_ATTEMPTS = 6


class ParentCacheIntegrityError(RuntimeError):
    """The immutable V4 parent cache failed envelope validation."""


class ReadOnlyParentCache:
    """Validate and replay V4 provider envelopes without writing to their directory."""

    def __init__(self, cache_dir: Path, model: dict[str, str]) -> None:
        self.cache_dir = cache_dir
        self.model = model
        self.hits = 0
        self.misses = 0
        self.invalid_entries = 0

    def get(self, request: StructuredGenerationRequest) -> dict[str, Any] | None:
        path = self._path(request)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            envelope = json.loads(path.read_text("utf-8"))
            output = self._validate(envelope, request)
        except (OSError, TypeError, ValueError) as exc:
            self.invalid_entries += 1
            raise ParentCacheIntegrityError(
                "V4 parent provider cache failed integrity validation"
            ) from exc
        self.hits += 1
        return output

    def _path(self, request: StructuredGenerationRequest) -> Path:
        payload = {
            "cache_schema": PROVIDER_OUTPUT_CACHE_SCHEMA,
            "format_version": PROVIDER_OUTPUT_CACHE_FORMAT_VERSION,
            "model": self.model,
            "request": request.model_dump(mode="json"),
        }
        digest = v4._fingerprint(payload)
        return (
            self.cache_dir
            / PROVIDER_OUTPUT_CACHE_NAMESPACE
            / digest[:2]
            / f"{digest}.json"
        )

    def _validate(
        self, envelope: Any, request: StructuredGenerationRequest
    ) -> dict[str, Any]:
        if not isinstance(envelope, dict):
            raise TypeError("parent provider cache envelope must be an object")
        expected = {
            "cache_schema": PROVIDER_OUTPUT_CACHE_SCHEMA,
            "format_version": PROVIDER_OUTPUT_CACHE_FORMAT_VERSION,
            "model": self.model,
            "request_fingerprint": v4._fingerprint(request.model_dump(mode="json")),
        }
        for key, value in expected.items():
            if envelope.get(key) != value:
                raise ValueError(f"parent provider cache {key} mismatch")
        output = envelope.get("output")
        if not isinstance(output, dict):
            raise TypeError("parent provider cache output must be an object")
        return output


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live-authoring", action="store_true")
    result.add_argument("--parent-cache-dir", type=Path, default=DEFAULT_PARENT_CACHE)
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
    parent_manifest, parent_state, parent_snapshot = _load_parent(
        args.parent_cache_dir, manifest.fingerprint, batches
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
    _require_parent_config(parent_manifest, config)
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
        "retrieval_enabled": False,
        "quality_metrics_available": False,
        "implementation_commit": v4._git_commit_hash(),
        "parent": parent_snapshot,
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
    parent = ReadOnlyParentCache(args.parent_cache_dir, parent_manifest["provider"])
    binding_plan = dict(plan)
    binding_plan.pop("maximum_new_calls_this_invocation")
    binding = {
        **binding_plan,
        "mode": "sealed_surface_authoring_continuation",
        "batch_ids": [batch.batch_id for batch in batches],
        "provider": {"name": cached.name, "version": cached.version},
    }
    manifest_path = args.cache_dir / v4.MANIFEST_NAME
    state_path = args.cache_dir / v4.STATE_NAME
    v4._bind_manifest(manifest_path, binding)
    prior_state = v4._load_state(state_path)
    if prior_state and prior_state.get("parent_provider_cache_sha256") != parent_snapshot[
        "provider_cache_sha256"
    ]:
        raise ValueError("V5 state is bound to a different V4 provider cache")

    completed: list[str] = []
    accepted_attempts: dict[str, int] = {}
    projected_by_owner: defaultdict[str, list[ProjectedOwnerSurfaces]] = defaultdict(
        list
    )
    registry = v4.SurfaceUniquenessRegistry()
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
                        parent=parent,
                        current=cached,
                    )
                except ParentCacheIntegrityError:
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

    baseline_usage = prior_state.get("usage", parent_state.get("usage", {}))
    baseline_calls = int(
        prior_state.get("provider_calls", parent_state.get("provider_calls", 0))
    )
    cumulative_usage = v4._merge_usage(baseline_usage, usage.report())
    cumulative_calls = baseline_calls + budget.calls
    complete = len(completed) == len(batches) and not stopped_reason
    last_invocation = {
        "provider_calls": budget.calls,
        "parent_cache_hits": parent.hits,
        "parent_cache_misses": parent.misses,
        "parent_invalid_cache_entries": parent.invalid_entries,
        "continuation_cache_hits": cached.hits,
        "continuation_cache_misses": cached.misses,
        "continuation_invalid_cache_entries": cached.invalid_entries_ignored,
        "surface_collision_attempts": collision_attempts,
        "surface_validation_rejection_attempts": validation_rejection_attempts,
        "stopped_reason": stopped_reason,
        "stopped_at_batch_id": stopped_at,
    }
    state = {
        "state_schema_version": 2,
        "binding_sha256": v4._fingerprint(binding),
        "parent_provider_cache_sha256": parent_snapshot["provider_cache_sha256"],
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
        "parent": parent_snapshot,
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
        "parent": parent_snapshot,
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
    parent: ReadOnlyParentCache,
    current: CachedStructuredOutputModel,
) -> ProjectedOwnerSurfaces:
    if attempt < V4_MAX_AUTHORING_ATTEMPTS:
        legacy_request = build_authoring_request(
            batch,
            variation_attempt=attempt,
            must_change_surface_keys=must_change,
        )
        raw = parent.get(legacy_request)
        if raw is not None:
            return project_owner_surfaces(batch, raw)
    request = build_authoring_request_v5(
        batch,
        variation_attempt=attempt,
        must_change_surface_keys=must_change,
    )
    raw = await current.generate(request)
    if isinstance(raw, BaseModel):
        raw = raw.model_dump(mode="json", warnings=False)
    return project_owner_surfaces(batch, raw)


def _load_parent(
    cache_dir: Path, manifest_fingerprint: str, batches: list[OwnerAuthoringBatch]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest_path = cache_dir / v4.MANIFEST_NAME
    state_path = cache_dir / v4.STATE_NAME
    if not manifest_path.is_file() or not state_path.is_file():
        raise ValueError("V5 requires the V4 acquisition manifest and state")
    parent_manifest = json.loads(manifest_path.read_text("utf-8"))
    parent_state = json.loads(state_path.read_text("utf-8"))
    expected_batch_ids = [batch.batch_id for batch in batches]
    if parent_manifest.get("runner") != PARENT_RUNNER:
        raise ValueError("parent acquisition runner is not V4")
    if parent_manifest.get("manifest_fingerprint") != manifest_fingerprint:
        raise ValueError("parent acquisition manifest fingerprint mismatch")
    if parent_manifest.get("batch_ids") != expected_batch_ids:
        raise ValueError("parent acquisition batch order mismatch")
    if not isinstance(parent_manifest.get("provider"), dict):
        raise TypeError("parent acquisition provider identity is missing")
    provider_files = sorted(
        (cache_dir / PROVIDER_OUTPUT_CACHE_NAMESPACE).glob("*/*.json")
    )
    inventory = [
        {"path": path.relative_to(cache_dir).as_posix(), "sha256": v4._sha256(path)}
        for path in provider_files
    ]
    snapshot = {
        "runner": PARENT_RUNNER,
        "manifest_sha256": v4._sha256(manifest_path),
        "provider_cache_entry_count": len(inventory),
        "provider_cache_sha256": v4._fingerprint(inventory),
        "provider_calls": int(parent_state.get("provider_calls", 0)),
        "completed_batch_count": int(parent_state.get("completed_batch_count", 0)),
    }
    if snapshot["provider_calls"] != len(inventory):
        raise ValueError("parent provider call count does not match cache inventory")
    return parent_manifest, parent_state, snapshot


def _require_parent_config(
    parent_manifest: dict[str, Any], config: OpenAICompatibleStructuredOutputConfig
) -> None:
    expected = {
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
    }
    mismatch = {
        key: (parent_manifest.get(key), value)
        for key, value in expected.items()
        if parent_manifest.get(key) != value
    }
    if mismatch:
        raise ValueError(f"V5 provider configuration differs from V4: {mismatch}")


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())

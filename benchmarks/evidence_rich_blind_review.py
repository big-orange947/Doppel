"""Budgeted independent semantic review for blind-corpus authored surfaces."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmarks.build_evidence_rich_blind_manifest import build_manifest
from benchmarks.evidence_rich_blind_acquire import (
    DEFAULT_OUTPUT as DEFAULT_AUTHORED_SURFACES,
)
from benchmarks.evidence_rich_blind_acquire import (
    MEMORY_BATCH_SIZE,
)
from benchmarks.evidence_rich_blind_authoring import (
    AuthoredEntitySurface,
    AuthoredMemorySurface,
    AuthoredQuerySurface,
    OwnerAuthoringBatch,
    OwnerSurfaceDraft,
    review_owner_surfaces,
    split_owner_authoring_batches,
    validate_surface_review,
)
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
    StructuredOutputProviderError,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data/doppel/evidence-rich-blind-v1-review-cache"
DEFAULT_PROGRESS = ROOT / "data/doppel/evidence-rich-blind-v1-review-progress.json"
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-rich-blind-v1-review.json"
MANIFEST_NAME = "review-manifest.json"
STATE_NAME = "review-state.json"
RUNNER = "doppel.evidence-rich-blind-review.v1"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live-review", action="store_true")
    result.add_argument(
        "--authored-surfaces", type=Path, default=DEFAULT_AUTHORED_SURFACES
    )
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
    result.add_argument("--max-completion-tokens", type=int, default=4096)
    result.add_argument("--timeout-seconds", type=float, default=120.0)
    return result


async def run(
    args: argparse.Namespace,
    *,
    manifest_factory: Callable[[], Any] = build_manifest,
    request_builder: Callable[..., StructuredGenerationRequest] | None = None,
    runner: str = RUNNER,
) -> int:
    if args.max_new_calls < 0:
        raise ValueError("max-new-calls must not be negative")
    manifest = manifest_factory()
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
        "runner": runner,
        "mode": "live_review" if args.live_review else "dry_run",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_path": str(args.authored_surfaces.resolve()),
        "authored_surfaces_available": args.authored_surfaces.is_file(),
        "owner_count": len(manifest.owners),
        "batch_count": len(batches),
        "maximum_total_uncached_calls": len(batches),
        "maximum_new_calls_this_invocation": args.max_new_calls,
        "model": config.model,
        "base_url": config.base_url,
        "schema_mode": config.schema_mode,
        "max_completion_tokens": config.max_completion_tokens,
        "temperature": config.temperature,
        "thinking": config.thinking,
        "provider_retries": 0,
        "auto_rewrite_enabled": False,
        "retrieval_enabled": False,
        "quality_metrics_available": False,
        "implementation_commit": _git_commit_hash(),
    }
    if not args.live_review:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.output.exists():
        raise ValueError("completed first review output already exists")
    authored = _load_authored_surfaces(args.authored_surfaces, manifest)
    authored_sha256 = _sha256(args.authored_surfaces)
    drafts = {batch.batch_id: _draft_for_batch(batch, authored) for batch in batches}
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
    binding_plan.pop("authored_surfaces_path")
    binding = {
        **binding_plan,
        "mode": "sealed_independent_review",
        "authored_surfaces_sha256": authored_sha256,
        "batch_ids": [batch.batch_id for batch in batches],
        "provider": {"name": cached.name, "version": cached.version},
    }
    manifest_path = args.cache_dir / MANIFEST_NAME
    state_path = args.cache_dir / STATE_NAME
    _bind_manifest(manifest_path, binding)
    prior_state = _load_state(state_path)
    completed: list[str] = []
    stopped_reason = ""
    stopped_at = ""
    provider_error: dict[str, Any] = {}

    async def review_batch(batch: OwnerAuthoringBatch, model: Any) -> Any:
        if request_builder is None:
            return await review_owner_surfaces(batch, drafts[batch.batch_id], model)
        raw = await model.generate(request_builder(batch, drafts[batch.batch_id]))
        return validate_surface_review(batch, raw)

    try:
        for batch in batches:
            try:
                await review_batch(batch, cached)
            except PlannerCallBudgetExceeded:
                stopped_reason = "budget_exhausted"
                stopped_at = batch.batch_id
                break
            except StructuredOutputProviderError as exc:
                stopped_reason = type(exc).__name__
                stopped_at = batch.batch_id
                provider_error = {
                    "code": exc.code,
                    "http_status": exc.status_code,
                    "retryable": exc.retryable,
                }
                break
            except Exception as exc:  # noqa: BLE001 - redact provider details
                stopped_reason = type(exc).__name__
                stopped_at = batch.batch_id
                break
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
            "stopped_reason": stopped_reason,
            "stopped_at_batch_id": stopped_at,
        },
    }
    if provider_error:
        state["last_invocation"]["provider_error"] = provider_error
    _write_json(state_path, state)
    progress = {
        "runner": runner,
        "status": "complete" if complete else "incomplete",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": authored_sha256,
        "implementation_commit": plan["implementation_commit"],
        "completed_batch_count": len(completed),
        "batch_count": len(batches),
        "provider_calls_cumulative": cumulative_calls,
        "usage_cumulative": cumulative_usage,
        "last_invocation": state["last_invocation"],
        "review_available": complete,
        "retrieval_opened": False,
        "quality_metrics_available": False,
    }
    _write_json(args.progress_output, progress)
    if not complete:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
        return 0

    replay_budget = StructuredOutputCallBudget(provider, max_calls=0)
    replay_cache = CachedStructuredOutputModel(replay_budget, args.cache_dir)
    reports: list[dict[str, Any]] = []
    for batch in batches:
        review = await review_batch(batch, replay_cache)
        reports.append(
            {
                "batch_id": batch.batch_id,
                "owner_key": batch.owner_key,
                "reviewed_surface_count": len(review.reviewed_surface_keys),
                "reviewed_surface_keys_sha256": _fingerprint(
                    sorted(review.reviewed_surface_keys)
                ),
                "issue_count": len(review.issues),
                "issues": [item.model_dump(mode="json") for item in review.issues],
            }
        )
    issue_count = sum(item["issue_count"] for item in reports)
    accepted = issue_count == 0
    output = {
        "runner": runner,
        "status": "reviewed_accepted" if accepted else "reviewed_rejected",
        "manifest_fingerprint": manifest.fingerprint,
        "authored_surfaces_sha256": authored_sha256,
        "implementation_commit": plan["implementation_commit"],
        "binding_sha256": _fingerprint(binding),
        "review_complete": True,
        "accepted": accepted,
        "issue_count": issue_count,
        "batch_count": len(reports),
        "batches": reports,
        "acquisition": state,
        "auto_rewrite_performed": False,
        "retrieval_opened": False,
        "quality_metrics_available": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    _write_json(args.output, output)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {_sha256(args.output)}")
    print(json.dumps({"accepted": accepted, "issue_count": issue_count}))
    return 0 if accepted else 1


def _load_authored_surfaces(path: Path, manifest: Any) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError("authored surface artifact is required for live review")
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("authored surface artifact must be an object")
    if raw.get("status") != "authored_unreviewed":
        raise ValueError("review requires the first authored_unreviewed artifact")
    if raw.get("manifest_fingerprint") != manifest.fingerprint:
        raise ValueError("authored surface manifest fingerprint mismatch")
    if raw.get("review_complete") is not False:
        raise ValueError("authored surface review state must be false")
    if raw.get("retrieval_opened") is not False:
        raise ValueError("authored surfaces must precede retrieval")
    owners = raw.get("owners")
    if not isinstance(owners, list):
        raise TypeError("authored surfaces require an owner list")
    actual = {str(item.get("owner_key")): item for item in owners}
    if len(actual) != len(owners) or set(actual) != {
        owner.owner_key for owner in manifest.owners
    }:
        raise ValueError("authored surface owner set mismatch")
    for owner in manifest.owners:
        item = actual[owner.owner_key]
        expected = {
            "entity_names_by_id": {entity.entity_id for entity in owner.entities},
            "memory_content_by_id": {memory.memory_id for memory in owner.memories},
            "edge_fact_by_memory_id": {memory.memory_id for memory in owner.memories},
            "query_text_by_case_id": {query.case_id for query in owner.queries},
        }
        for field, keys in expected.items():
            values = item.get(field)
            if not isinstance(values, dict) or set(values) != keys:
                raise ValueError(f"authored surface {field} set mismatch")
            if field != "edge_fact_by_memory_id" and any(
                not str(value or "").strip() for value in values.values()
            ):
                raise ValueError(f"authored surface {field} contains empty text")
    return raw


def _draft_for_batch(
    batch: OwnerAuthoringBatch, authored: dict[str, Any]
) -> OwnerSurfaceDraft:
    owner = next(
        item for item in authored["owners"] if item["owner_key"] == batch.owner_key
    )
    draft = OwnerSurfaceDraft(
        entities=[
            AuthoredEntitySurface(
                surface_key=item.surface_key,
                name=owner["entity_names_by_id"][item.entity_id],
            )
            for item in batch.entities
        ],
        memories=[
            AuthoredMemorySurface(
                surface_key=item.surface_key,
                content=owner["memory_content_by_id"][item.memory_id],
                edge_fact=owner["edge_fact_by_memory_id"][item.memory_id],
            )
            for item in batch.memories
        ],
        queries=[
            AuthoredQuerySurface(
                surface_key=item.surface_key,
                query=owner["query_text_by_case_id"][item.case_id],
            )
            for item in batch.queries
        ],
    )
    # The review request builder revalidates exact coverage and relation edge shape.
    return draft


def _bind_manifest(path: Path, binding: dict[str, Any]) -> None:
    if path.exists():
        existing = json.loads(path.read_text("utf-8"))
        if existing != binding:
            raise ValueError("review manifest does not match current binding")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    unexpected = [item for item in path.parent.iterdir() if item.name != path.name]
    if unexpected:
        raise ValueError("new sealed review requires an empty cache directory")
    _write_json(path, binding)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("review state must be an object")
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

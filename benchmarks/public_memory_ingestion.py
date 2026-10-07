"""Bounded real extraction/Store/vector pilot; not retrieval, QA or AML scores.

Default is a zero-provider/database preflight. Live execution requires explicit
endpoint/model/key-env configuration. Raw source order, both roles and all chunks
are fixed before any response. A partial prefix never counts as a complete history.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_longmemeval import RuntimeCase
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.consolidation import DeterministicMemoryConsolidator
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisDiagnostics,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    ReferencePersonalMemoryAnalyzer,
)
from doppel_memory.models import (
    Actor,
    FactAuthority,
    MemoryFilter,
    MemoryScope,
    MemoryState,
)
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig
from integrations.aml.contract import AddRequest, event_ids, memory_scope, write_key
from integrations.aml.ingestion import DurableTextualIngestor, IngestionFailure


def miner_config(max_messages: int) -> PersonalMemoryMinerConfig:
    return PersonalMemoryMinerConfig(
        allowed_source_actors={Actor.OWNER, Actor.AGENT},
        require_subject_matches_source_actor=True,
        proposed_state=MemoryState.CONFIRMED,
        minimum_confidence=0.75,
        max_memories=100,
        max_messages=max_messages,
    )


def build_ingestion_plan(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    config: OpenAICompatibleStructuredOutputConfig,
    *,
    max_calls: int,
) -> dict[str, Any]:
    """History/transport projection only; accepts neither gold nor query fields."""
    if not cases or type(max_calls) is not int or max_calls < 1:
        raise ValueError("nonempty histories and positive call bound required")
    rows = []
    for case in cases:
        scope = memory_scope(manifest["run_namespace"], case.user_id)
        for chunk in case.ingestion_chunks(max_messages=manifest["max_messages"]):
            rows.append(
                {
                    "user_id": case.user_id,
                    "request_id": chunk.request.request_id,
                    "write_key": write_key(scope, chunk.request),
                    "scope_key": scope.scope_key,
                    "source_session_index": chunk.source_session_index,
                    "source_turn_indices": list(chunk.source_turn_indices),
                    "event_ids": list(event_ids(scope, chunk.request)),
                    "roles": [message.role for message in chunk.request.messages],
                    "payload_sha256": _hash(chunk.request.model_dump(mode="json")),
                    "message_count": len(chunk.request.messages),
                }
            )
    plan = {
        "schema_version": 1,
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "source_sha256": manifest["source_sha256"],
        "run_namespace": manifest["run_namespace"],
        "scope_count": len(cases),
        "total_chunks": len(rows),
        "total_messages": sum(row["message_count"] for row in rows),
        "chunks": rows,
        "provider_config": config.model_dump(mode="json"),
        "miner_config": miner_config(manifest["max_messages"]).model_dump(mode="json"),
        "max_calls": max_calls,
        "temporal_policy": manifest["temporal_policy"],
        "graph_configured": False,
        "analyzer": [
            ReferencePersonalMemoryAnalyzer.name,
            ReferencePersonalMemoryAnalyzer.version,
        ],
        "miner": [PersonalMemoryMiner.name, PersonalMemoryMiner.version],
        "consolidator": [
            DeterministicMemoryConsolidator.name,
            DeterministicMemoryConsolidator.version,
        ],
        "embedding": {
            "name": _LocalEmbeddingProvider().name,
            "version": _LocalEmbeddingProvider().version,
            "dimensions": _LocalEmbeddingProvider().dimensions,
        },
        "host_acceptance_policy": "confirm-attributed-proposals-with-core-evidence-gates",
    }
    # Set serialization order must be stable across processes.
    plan["miner_config"]["allowed_source_actors"] = sorted(
        plan["miner_config"]["allowed_source_actors"]
    )
    return {**plan, "plan_fingerprint": _hash(plan)}


def _bind_json(path: Path, value: Mapping[str, Any]) -> None:
    """Preserve and reject incompatible runs; never overwrite a prior binding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != dict(value):
            raise ValueError("run directory belongs to a different plan") from None


def ingestion_execution_metadata() -> dict[str, Any]:
    metadata = execution_metadata()
    root = Path(__file__).resolve().parents[1]
    metadata["composition_source_sha256"] = {
        str(file.relative_to(root).as_posix()): hashlib.sha256(
            file.read_bytes()
        ).hexdigest()
        for file in (
            Path(__file__).resolve(),
            root / "benchmarks/public_memory_runtime.py",
            root / "integrations/aml/ingestion.py",
        )
    }
    return metadata


def preflight_report(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "runner": "doppel.public-memory-ingestion.v1",
        "mode": "preflight-no-provider-no-database",
        "status": "ready-for-bounded-live-ingestion",
        "execution_metadata": ingestion_execution_metadata(),
        "plan": dict(plan),
        "llm_calls_this_invocation": 0,
        "provider_tokens_this_invocation": 0,
        "quality_metrics_available": False,
        "retrieval_executed": False,
        "reader_executed": False,
        "publication_ready": False,
        "aml_academic_model_compliant": False,
        "reserved_histories_executed": False,
    }


async def ingest_histories(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    *,
    host: DurableTextualIngestor,
    max_new_chunks: int,
    before_ingest: Callable[[MemoryScope, AddRequest], None] | None = None,
) -> dict[str, Any]:
    """Stop at the first failure; later chunks cannot hide a failed predecessor."""
    if type(max_new_chunks) is not int or max_new_chunks < 0:
        raise ValueError("max_new_chunks must be nonnegative")
    completed_keys = {
        row["write_key"] for row in host.audit_report()["chunks"] if row["completed"]
    }
    attempted = completed = replayed = 0
    stopped: dict[str, Any] = {}
    planned_keys = []
    for case in cases:
        scope = memory_scope(manifest["run_namespace"], case.user_id)
        for chunk in case.ingestion_chunks(max_messages=manifest["max_messages"]):
            planned_keys.append(write_key(scope, chunk.request))
    if not planned_keys or len(set(planned_keys)) != len(planned_keys):
        raise ValueError("ingestion requires nonempty unique planned chunks")
    if not {row["write_key"] for row in host.audit_report()["chunks"]} <= set(
        planned_keys
    ):
        raise ValueError("journal contains chunks outside the bound history plan")
    ordinals = {key: index + 1 for index, key in enumerate(planned_keys)}
    for case in cases:
        scope = memory_scope(manifest["run_namespace"], case.user_id)
        for chunk in case.ingestion_chunks(max_messages=manifest["max_messages"]):
            key = write_key(scope, chunk.request)
            is_replay = key in completed_keys
            if not is_replay and attempted >= max_new_chunks:
                stopped = {"reason": "invocation-chunk-bound", "write_key": key}
                break
            if not is_replay:
                attempted += 1
            try:
                if before_ingest is not None:
                    before_ingest(scope, chunk.request)
                await host.ingest(scope, chunk.request)
            except IngestionFailure as exc:
                stopped = {
                    "reason": "ingestion-stage-failed",
                    "stage": exc.stage,
                    "code": exc.reason,
                    "write_key": key,
                }
                break
            except Exception:  # noqa: BLE001 - redact plugins, database and key errors
                stopped = {"reason": "ingestion-failed", "write_key": key}
                break
            completed += not is_replay
            replayed += is_replay
            print(
                f"chunk {ordinals[key]}/{len(planned_keys)}: completed",
                flush=True,
            )
        if stopped:
            break
    audit = host.audit_report()
    journal_keys = {row["write_key"] for row in audit["chunks"]}
    if not journal_keys <= set(planned_keys):
        raise ValueError("journal contains chunks outside the bound history plan")
    complete_keys = {row["write_key"] for row in audit["chunks"] if row["completed"]}
    full = complete_keys == set(planned_keys)
    return {
        "status": "complete"
        if full
        else "failed"
        if stopped.get("stage") is not None
        or stopped.get("reason") == "ingestion-failed"
        else "partial",
        "all_histories_ingested": full,
        "planned_chunks": len(planned_keys),
        "new_chunks_attempted": attempted,
        "new_chunks_completed": completed,
        "completed_chunks_replayed": replayed,
        "stopped": stopped,
        "audit": audit,
    }


async def audit_stored_records(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    host: DurableTextualIngestor,
) -> dict[str, Any]:
    """Inspect actual Store identities/provenance, not semantic truth or relevance."""
    raw = derived = governance = checks = failures = 0
    states: dict[str, int] = {}
    actors: dict[str, int] = {}
    for case in cases:
        scope = memory_scope(manifest["run_namespace"], case.user_id)
        cursor = ""
        seen: set[str] = set()
        for _ in range(1000):
            page = await host.store.scan(
                scope,
                filters=MemoryFilter(include_inactive=True),
                cursor=cursor,
                limit=200,
            )
            for record in page.records:
                if (
                    record.scope.scope_key != scope.scope_key
                    or record.memory_id in seen
                ):
                    raise ValueError("Store audit scope/identity failure")
                seen.add(record.memory_id)
                states[record.state] = states.get(record.state, 0) + 1
                actors[record.actor] = actors.get(record.actor, 0) + 1
                if record.extractor == "ingestor":
                    raw += 1
                    source = await host.resolve_event(scope, record.source_event_id)
                    checks += 1
                    failures += source is None or source.memory_id != record.memory_id
                elif "personal-memory" in record.tags:
                    derived += 1
                    evidence = record.metadata.get("evidence")
                    if not isinstance(evidence, list) or not evidence:
                        failures += 1
                        continue
                    for item in evidence:
                        if not isinstance(item, dict) or not isinstance(
                            item.get("evidence_id"), str
                        ):
                            failures += 1
                            continue
                        source = await host.resolve_event(scope, item["evidence_id"])
                        checks += 1
                        failures += source is None or (
                            source.actor != record.actor
                            or source.authority != record.authority
                            or source.scope.scope_key != scope.scope_key
                        )
                elif (
                    record.kind == "memory_conflict"
                    and "memory-conflict" in record.tags
                ):
                    governance += 1
                    conflict = record.metadata.get("conflict")
                    sources = (
                        conflict.get("source_memories")
                        if isinstance(conflict, dict)
                        else None
                    )
                    if (
                        record.authority != FactAuthority.DERIVED_SUMMARY
                        or not isinstance(sources, list)
                        or len(sources) < 2
                    ):
                        failures += 1
                        continue
                    for item in sources:
                        if not isinstance(item, dict) or not isinstance(
                            item.get("memory_id"), str
                        ):
                            failures += 1
                            continue
                        source = await host.store.get(scope, item["memory_id"])
                        checks += 1
                        failures += source is None or (
                            source.scope.scope_key != scope.scope_key
                            or source.actor != record.actor
                            or "personal-memory" not in source.tags
                        )
                else:
                    raise ValueError("Store audit found an unclassified record")
            if not page.has_more:
                break
            if not page.next_cursor or page.next_cursor == cursor:
                raise ValueError("Store audit cursor did not advance")
            cursor = page.next_cursor
        else:
            raise ValueError("Store audit page bound exceeded")
    return {
        "raw_records": raw,
        "derived_records_including_inactive": derived,
        "governance_records": governance,
        "state_counts": states,
        "actor_counts": actors,
        "provenance_checks": checks,
        "provenance_failures": failures,
        "semantic_truth_verified": False,
    }


async def run_live(
    cases: Sequence[RuntimeCase],
    manifest: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    dsn: str,
    api_key: str,
    max_new_chunks: int,
    embedding_cache_dir: Path | None,
    cache_only: bool = False,
) -> dict[str, Any]:
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        plan["provider_config"]
    )
    if build_ingestion_plan(
        cases, manifest, config, max_calls=plan["max_calls"]
    ) != dict(plan):
        raise ValueError("live histories/configuration differ from the bound plan")
    _bind_json(run_dir / "plan.json", plan)
    ledger = DurableCallLedger(
        run_dir / "usage.sqlite3",
        budget_id="extraction-v1:" + plan["plan_fingerprint"],
        max_calls=plan["max_calls"],
    )
    before_usage = ledger.report()
    before = before_usage["attempts_reserved"]
    provider = OpenAICompatibleStructuredOutputModel(
        config, api_key=api_key, usage_observer=ledger.observe_usage
    )
    store = PostgreSQLStore(
        dsn, schema="public_memory_" + plan["plan_fingerprint"][:12], create_schema=True
    )
    host: DurableTextualIngestor | None = None
    report: dict[str, Any] = {}
    try:
        model = PilotStructuredModel(
            provider,
            ledger=ledger,
            cache_dir=run_dir / "provider-cache",
            cache_only=cache_only or max_new_chunks == 0,
        )
        embedding = _LocalEmbeddingProvider(cache_dir=embedding_cache_dir)
        index = PostgreSQLVectorIndex(
            store, embedding, VectorIndexConfig(create_extension=True)
        )
        active: tuple[MemoryScope, AddRequest] | None = None

        def observe(diagnostics: PersonalMemoryAnalysisDiagnostics) -> None:
            if host is None or active is None:
                raise ValueError("analysis diagnostics have no current chunk")
            host.record_analysis_diagnostics(*active, diagnostics)

        parsed = urlsplit(dsn)
        store_identity = "public-pilot-pg:" + _hash(
            [parsed.hostname, parsed.port, parsed.path, store.schema]
        )
        host = DurableTextualIngestor(
            store,
            journal_path=run_dir / "ingestion.sqlite3",
            miner=PersonalMemoryMiner(
                ReferencePersonalMemoryAnalyzer(model, diagnostics_observer=observe),
                miner_config(manifest["max_messages"]),
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index_writers=[index],
            role_actors={"user": Actor.OWNER, "assistant": Actor.AGENT},
            store_identity=store_identity,
        )

        def bind_chunk(scope: MemoryScope, request: AddRequest) -> None:
            nonlocal active
            active = (scope, request)

        report = await ingest_histories(
            cases,
            manifest,
            host=host,
            max_new_chunks=max_new_chunks,
            before_ingest=bind_chunk,
        )
        active = None
        record_audit = await audit_stored_records(cases, manifest, host)
        if record_audit["provenance_failures"]:
            report["status"] = "failed"
            report["stopped"] = {"reason": "store-provenance-audit-failed"}
        after_usage = ledger.report()
        new_calls = after_usage["attempts_reserved"] - before
        observed_tokens = (
            (after_usage["reported_tokens"] or {}).get("total_tokens", 0)
            - (before_usage["reported_tokens"] or {}).get("total_tokens", 0)
            if after_usage["calls_with_complete_usage"]
            - before_usage["calls_with_complete_usage"]
            == new_calls
            else None
        )
        return {
            **preflight_report(plan),
            **report,
            "mode": "live-model-postgresql-local-vector",
            "provider_tokens_this_invocation": observed_tokens,
            "llm_calls_this_invocation": new_calls,
            "usage_cumulative": model.report(),
            "postgres_schema": store.schema,
            "embedding": {
                "name": embedding.name,
                "version": embedding.version,
                "dimensions": embedding.dimensions,
            },
            "graph_configured": False,
            "cache_only": cache_only or max_new_chunks == 0,
            "store_record_audit": record_audit,
            "secrets_persisted": False,
        }
    except Exception:  # noqa: BLE001 - no provider/DSN text in reports or traceback
        return {
            **preflight_report(plan),
            **report,
            "mode": "live-model-postgresql-local-vector",
            "status": "failed",
            "all_histories_ingested": False,
            "stopped": {"reason": "composition-or-audit-failed"},
            "ingestion_stop_before_audit": report.get("stopped"),
            "llm_calls_this_invocation": ledger.report()["attempts_reserved"] - before,
            "provider_tokens_this_invocation": None,
            "usage_cumulative": {"ledger": ledger.report()},
            "postgres_schema": store.schema,
        }
    finally:
        if host is not None:
            host.close()
        await store.close()
        await provider.aclose()
        ledger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--run-dir", type=Path, default=Path("data/doppel/public-memory-ingestion-v1")
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="resume/revalidate using existing outputs; no API key or network model call",
    )
    parser.add_argument("--max-new-chunks", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=147)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--schema-mode", choices=("json_object", "json_schema"), default="json_object"
    )
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--api-key-env", default="DOPPEL_API_KEY")
    parser.add_argument("--dsn-env", default="DOPPEL_PUBLIC_PILOT_PG_DSN")
    parser.add_argument("--embedding-cache-dir", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() in {
        args.dataset.resolve(),
        args.manifest.resolve(),
    }:
        raise FileExistsError(
            "choose a new report path; never overwrite source or results"
        )
    if args.max_new_chunks < 0:
        raise ValueError(
            "max-new-chunks must be nonnegative; zero only replays completed chunks"
        )
    data = args.dataset.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = select_diagnostic_cases(
        json.loads(data), manifest, source_sha256=hashlib.sha256(data).hexdigest()
    )
    # Scoring labels do not enter the ingestion composition.
    cases = [runtime for runtime, _scoring in selected]
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_output_tokens,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
        timeout_seconds=120,
    )
    plan = build_ingestion_plan(cases, manifest, config, max_calls=args.max_calls)
    if not args.live:
        report = preflight_report(plan)
    else:
        key = (
            os.environ.get(args.api_key_env, "")
            if args.max_new_chunks and not args.cache_only
            else ""
        )
        dsn = os.environ.get(args.dsn_env, "")
        if not dsn or (args.max_new_chunks and not args.cache_only and not key):
            raise ValueError(
                "live requires key and diagnostic DSN in named environment variables"
            )
        report = asyncio.run(
            run_live(
                cases,
                manifest,
                plan,
                run_dir=args.run_dir,
                dsn=dsn,
                api_key=key,
                max_new_chunks=args.max_new_chunks,
                embedding_cache_dir=args.embedding_cache_dir,
                cache_only=args.cache_only,
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"output: {args.output.resolve()}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "quality_metrics_available": False,
                "llm_calls_this_invocation": report["llm_calls_this_invocation"],
            }
        )
    )
    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

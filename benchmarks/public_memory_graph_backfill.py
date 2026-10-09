"""Bounded, resumable Graphiti projection of already committed personal memories.

No benchmark questions, answers, evidence labels, re-extraction or fixture edges.
Graphiti writes are explicit; Store and vectors are never changed. Successful
episodes are retained. The provider uses the existing durable budget/cache.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from graphiti_core.embedder.client import EmbedderClient

from benchmarks.evidence_rich_blind_diagnostic import local_credentials
from benchmarks.graphiti_runtime import DurableGraphitiLLMClient, GraphitiChatTransport
from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import config, local_diagnostic_dsn, save
from benchmarks.public_memory_high_config_preflight import bound_scopes
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import (
    DurableCallLedger,
    PilotRuntimeError,
    PilotStructuredModel,
)
from doppel_memory.graphiti_store import (
    GRAPHITI_FALLBACK_EDGE_NAME,
    GRAPHITI_PROJECTION_VERSION,
    GraphitiSemanticIndex,
    NoOpCrossEncoder,
    _graphiti_episode_id,
)
from doppel_memory.indexing import memory_index_fingerprint
from doppel_memory.models import Actor, FactAuthority, MemoryRecord, MemoryState
from doppel_memory.postgres_store import PostgreSQLStore


def build_plan(
    records, scopes, ingestion, *, max_records: int, max_calls: int, parent=None
) -> dict:
    if not 1 <= max_records <= 10_000 or not 1 <= max_calls <= 100_000:
        raise ValueError("invalid graph backfill bounds")
    if (
        not ingestion.get("all_histories_ingested")
        or ingestion.get("status") != "complete"
    ):
        raise ValueError("graph backfill requires completed ingestion")
    eligible = []
    for scope in scopes:
        for record in sorted(
            records.values(), key=lambda r: (r.created_at, r.memory_id)
        ):
            if (
                record.scope.scope_key != scope.scope_key
                or "personal-memory" not in record.tags
            ):
                continue
            if record.state != MemoryState.CONFIRMED:
                continue
            subject = record.metadata.get("subject")
            subject_id = (
                record.scope.user_id
                if subject == Actor.OWNER
                else record.scope.agent_id
            )
            if (
                subject not in {Actor.OWNER, Actor.AGENT}
                or record.actor != subject
                or record.authority != FactAuthority.of(subject)
                or record.metadata.get("subject_id") != subject_id
                or not record.metadata.get("evidence")
            ):
                raise ValueError("eligible memory identity/provenance is invalid")
            eligible.append(record)
    selected = eligible[:max_records]
    if not selected:
        raise ValueError("no eligible graph records")
    if parent and (
        parent["corpus_sha256"]
        != _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        or parent["postgres_schema"] != ingestion["postgres_schema"]
        or parent["target_fingerprints"]
        != [memory_index_fingerprint(r) for r in selected]
        or max_calls > parent["remaining_attempts"]
    ):
        raise ValueError(
            "continuation must retain exact sources and remaining attempt ceiling"
        )
    value = {
        "runner": "doppel.public-memory-graph-backfill.v1",
        "ingestion_plan_fingerprint": ingestion["plan"]["plan_fingerprint"],
        "corpus_sha256": _hash(
            {k: r.model_dump(mode="json") for k, r in records.items()}
        ),
        "postgres_schema": ingestion["postgres_schema"],
        "selection": "ingestion-scope-order/created_at/memory_id/confirmed-personal-memories",
        "eligible_records": len(eligible),
        "selected_records": len(selected),
        "max_records": max_records,
        "max_calls": max_calls,
        "provider": config(8192).model_dump(mode="json"),
        "embedding": ingestion["embedding"],
        "projection_version": GRAPHITI_PROJECTION_VERSION,
        "max_request_bytes": 500_000,
        "max_total_request_bytes": 8_000_000,
        "records": [
            {
                "memory_id": r.memory_id,
                "scope_key": r.scope.scope_key,
                "fingerprint": memory_index_fingerprint(r),
                "source_version": r.version,
                "episode_id": _graphiti_episode_id(r.scope, r.memory_id),
            }
            for r in selected
        ],
        "implementation_sha256": {
            str(p.relative_to(Path(__file__).parents[1])).replace(
                "\\", "/"
            ): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(__file__).with_name("graphiti_runtime.py"),
                Path(__file__).parents[1] / "doppel_memory/graphiti_store.py",
            )
        },
    }
    if parent:
        value["parent"] = parent
    value["plan_fingerprint"] = _hash(value)
    return value


def parent_binding(report_path: Path, run_dir: Path) -> dict:
    """Bind an immutable parent receipt/cache; never reopen its writable ledger."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = report["plan"]
    payload = {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    usage = report["usage"]["ledger"]
    if (
        report["status"] not in {"partial", "complete"}
        or "parent" in plan
        or _hash(payload) != plan["plan_fingerprint"]
        or json.loads((run_dir / "plan.json").read_text(encoding="utf-8")) != plan
        or usage["budget_id"] != plan["plan_fingerprint"]
        or usage["attempt_status_counts"]["reserved"]
        or not report["corpus_unchanged"]
    ):
        raise ValueError("settled matching parent graph run required")
    with sqlite3.connect(
        (run_dir / "provider.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
    ) as db:
        count, size = db.execute(
            "SELECT count(*),coalesce(sum(request_bytes),0) FROM pilot_calls WHERE budget_id=?",
            (plan["plan_fingerprint"],),
        ).fetchone()
        states = dict(
            db.execute(
                "SELECT status,count(*) FROM pilot_calls WHERE budget_id=? GROUP BY status",
                (plan["plan_fingerprint"],),
            ).fetchall()
        )
    if (
        count != usage["attempts_reserved"]
        or size != usage["canonical_request_bytes"]
        or any(states.get(s, 0) != n for s, n in usage["attempt_status_counts"].items())
    ):
        raise ValueError("parent ledger changed since receipt")
    cache = run_dir / "cache"
    files = sorted(cache.rglob("*.json"))
    if not files:
        raise ValueError("parent cache unavailable")
    return {
        "plan_fingerprint": plan["plan_fingerprint"],
        "receipt_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "cache_sha256": _hash(
            {
                p.relative_to(cache).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in files
            }
        ),
        "cache_entry_count": len(files),
        "corpus_sha256": plan["corpus_sha256"],
        "postgres_schema": plan["postgres_schema"],
        "target_fingerprints": [r["fingerprint"] for r in plan["records"]],
        "attempts_spent": count,
        "remaining_attempts": plan["max_calls"] - count,
        "max_calls": plan["max_calls"],
        "usage": usage,
    }


def failure_details(error: Exception) -> dict:
    """Preserve chain types and allowlisted budget reasons, never exception text."""
    budget_codes = {
        "per-call canonical request byte budget exhausted": "per_request_bytes",
        "total canonical request byte budget exhausted": "total_request_bytes",
        "durable provider attempt budget exhausted": "attempts",
    }
    chain = []
    seen = set()
    budget_reason = None
    current = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(type(current).__name__)
        if isinstance(current, PilotRuntimeError):
            budget_reason = budget_codes.get(str(current), budget_reason)
        current = current.__cause__ or current.__context__
    return {"failure_chain_types": chain, "budget_stop_reason": budget_reason}


@contextmanager
def writer_lock(path: Path):
    """OS lock released on process death, unlike stale PID/lock-file leases."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class LocalGraphEmbedder(EmbedderClient):
    """Use the same existing local document-embedding profile as the corpus."""

    def __init__(self, provider) -> None:
        from graphiti_core.embedder.client import EmbedderConfig

        self.provider = provider
        self.config = EmbedderConfig(embedding_dim=provider.dimensions)

    async def create(self, input_data):
        values = [input_data] if isinstance(input_data, str) else input_data
        return list((await self.provider.embed(values))[0])

    async def create_batch(self, input_data_list):
        return [list(value) for value in await self.provider.embed(input_data_list)]


async def inspect_projection(graph, index, record: MemoryRecord) -> dict:
    entry = await index.inspect(record.scope, record.memory_id)
    expected = memory_index_fingerprint(record)
    match = bool(
        entry
        and entry.fingerprint == expected
        and entry.source_version == record.version
    )
    episode = _graphiti_episode_id(record.scope, record.memory_id)
    result, _, _ = await graph.driver.execute_query(
        "MATCH (e:Episodic {uuid:$episode, group_id:$scope}) "
        "OPTIONAL MATCH ()-[r:RELATES_TO]->() "
        "WHERE r.group_id=$scope AND $episode IN coalesce(r.episodes,[]) "
        "RETURN size(coalesce(e.entity_edges,[])) AS listed_edges, count(r) AS edges, "
        "sum(CASE WHEN r.name <> $fallback THEN 1 ELSE 0 END) AS rich_edges",
        episode=episode,
        scope=record.scope.scope_key,
        fallback=GRAPHITI_FALLBACK_EDGE_NAME,
    )
    row = (
        dict(result[0]) if result else {"edges": 0, "listed_edges": 0, "rich_edges": 0}
    )
    return {
        "memory_id": record.memory_id,
        "metadata_matches_store": match,
        **row,
        "complete": match and row["edges"] > 0 and row["listed_edges"] > 0,
    }


async def execute(
    store, records, plan, *, run_dir, api_key, cache_dir, parent_cache=None
) -> dict:
    from graphiti_core import Graphiti

    os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"

    _, password, _ = local_credentials()
    ledger = DurableCallLedger(
        run_dir / "provider.sqlite3",
        budget_id=plan["plan_fingerprint"],
        max_calls=plan["max_calls"],
        max_request_bytes=plan["max_request_bytes"],
        max_total_request_bytes=plan["max_total_request_bytes"],
    )
    transport = GraphitiChatTransport(
        config(8192),
        api_key=api_key,
        usage_observer=ledger.observe_usage,
    )
    model = PilotStructuredModel(
        transport,
        ledger=ledger,
        cache_dir=run_dir / "cache",
        read_only_cache_dirs=[parent_cache] if parent_cache else (),
    )
    llm = DurableGraphitiLLMClient(model, output_cap=8192)
    provider = _LocalEmbeddingProvider(cache_dir=cache_dir)
    if {
        "name": provider.name,
        "version": provider.version,
        "dimensions": provider.dimensions,
    } != plan["embedding"]:
        raise ValueError("graph embedding identity differs from corpus")
    graph = Graphiti(
        uri="bolt://127.0.0.1:7687",
        user="neo4j",
        password=password,
        llm_client=llm,
        embedder=LocalGraphEmbedder(provider),
        cross_encoder=NoOpCrossEncoder(),
        max_coroutines=1,
    )
    index = GraphitiSemanticIndex(store, graphiti_client=graph)
    journal = sqlite3.connect(run_dir / "index.sqlite3", isolation_level=None)
    journal.execute("PRAGMA journal_mode=WAL")
    journal.execute("PRAGMA synchronous=FULL")
    journal.execute(
        "CREATE TABLE IF NOT EXISTS entries (memory TEXT PRIMARY KEY, fingerprint TEXT, status TEXT)"
    )
    checks = []
    failure = None
    details = {"failure_chain_types": [], "budget_stop_reason": None}
    repairs = 0
    writes = 0
    try:
        for target in plan["records"]:
            record = records[target["memory_id"]]
            if await store.get(record.scope, record.memory_id) != record:
                raise ValueError("authoritative memory changed before graph indexing")
            old = journal.execute(
                "SELECT fingerprint,status FROM entries WHERE memory=?",
                (record.memory_id,),
            ).fetchone()
            before = await inspect_projection(graph, index, record)
            if old and old[0] != target["fingerprint"]:
                raise ValueError("graph checkpoint fingerprint mismatch")
            if old and old[1] == "complete" and not before["complete"]:
                raise ValueError(
                    "completed graph projection changed; do not silently repair"
                )
            if not before["complete"]:
                # Only repair this run's previously started deterministic slot.
                entry = await index.inspect(record.scope, record.memory_id)
                if entry is not None:
                    if not old or entry.fingerprint != target["fingerprint"]:
                        raise ValueError(
                            "refusing to replace an unowned graph projection"
                        )
                    await index.delete(record.scope, record.memory_id)
                    repairs += 1
                journal.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?,?,?)",
                    (record.memory_id, target["fingerprint"], "started"),
                )
                await index.index_record(record)
                writes += 1
            check = await inspect_projection(graph, index, record)
            if not check["complete"]:
                raise ValueError("graph projection completion/provenance audit failed")
            journal.execute(
                "INSERT OR REPLACE INTO entries VALUES (?,?,?)",
                (record.memory_id, target["fingerprint"], "complete"),
            )
            checks.append(check)
            print(
                f"graph-index {len(checks)}/{len(plan['records'])}: verified",
                flush=True,
            )
    except Exception as error:  # noqa: BLE001 - never persist provider/credential text
        failure = type(error).__name__
        details = failure_details(error)
    finally:
        await graph.close()
        journal.close()
    usage = model.report()
    ledger.close()
    return {
        "status": "complete" if failure is None else "partial",
        "failure_type": failure,
        **details,
        "completed_records": len(checks),
        "checks": checks,
        "rich_edges": sum(c["rich_edges"] for c in checks),
        "index_writes_this_invocation": writes,
        "incomplete_owned_slot_repairs": repairs,
        "usage": usage,
        "successful_graph_data_retained": True,
        "full_corpus_graph_coverage_certified": len(plan["records"])
        == plan["eligible_records"]
        and failure is None,
    }


async def run(args) -> dict:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ingestion = json.loads(args.ingestion_report.read_text(encoding="utf-8"))
    if ingestion["plan"]["manifest_fingerprint"] != manifest["manifest_fingerprint"]:
        raise ValueError("manifest differs from ingestion")
    scopes = bound_scopes(manifest, ingestion)
    store = PostgreSQLStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    try:
        records = await inventory(store, scopes)
        parent_run = getattr(args, "parent_run_dir", None)
        parent_report = getattr(args, "parent_report", None)
        if bool(parent_run) != bool(parent_report):
            raise ValueError("parent run and receipt must be supplied together")
        if parent_run and parent_run.resolve() == args.run_dir.resolve():
            raise ValueError("continuation requires a new run directory")
        parent = None
        if parent_run is not None and parent_report is not None:
            parent = parent_binding(parent_report, parent_run)
        plan = build_plan(
            records,
            scopes,
            ingestion,
            max_records=args.max_records,
            max_calls=args.max_calls,
            parent=parent,
        )
        report = {
            "runner": plan["runner"],
            "status": "ready",
            "plan": plan,
            "qa_metrics_available": False,
            "publication_ready": False,
            "store_or_vector_writes": 0,
            "reserved_histories_executed": False,
            "execution_metadata": execution_metadata(),
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
                != plan
            ):
                raise ValueError("live requires unchanged frozen graph preflight")
            key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if not key:
                raise ValueError("API key environment variable absent")
            with writer_lock(args.run_dir / "writer.lock"):
                _bind_json(args.run_dir / "plan.json", plan)
                report.update(
                    await execute(
                        store,
                        records,
                        plan,
                        run_dir=args.run_dir,
                        api_key=key,
                        cache_dir=args.embedding_cache_dir,
                        parent_cache=parent_run / "cache" if parent_run else None,
                    )
                )
                if parent:
                    assert parent_report is not None and parent_run is not None
                    if parent_binding(parent_report, parent_run) != parent:
                        raise ValueError(
                            "parent receipt/ledger/cache changed during continuation"
                        )
                    report["parent_unchanged"] = True
                    old_usage = parent["usage"]
                    new_usage = report["usage"]["ledger"]
                    report["aggregate_usage"] = {
                        "budget_ids": [old_usage["budget_id"], new_usage["budget_id"]],
                        "attempts_reserved": old_usage["attempts_reserved"]
                        + new_usage["attempts_reserved"],
                        "root_attempt_ceiling": parent["max_calls"],
                        "within_root_attempt_ceiling": old_usage["attempts_reserved"]
                        + new_usage["attempts_reserved"]
                        <= parent["max_calls"],
                        "reported_tokens": {
                            k: (old_usage["reported_tokens"] or {}).get(k, 0)
                            + (new_usage["reported_tokens"] or {}).get(k, 0)
                            for k in set(old_usage["reported_tokens"] or {})
                            | set(new_usage["reported_tokens"] or {})
                        },
                        "calls_without_usage": old_usage["calls_without_usage"]
                        + new_usage["calls_without_usage"],
                        "canonical_request_bytes": old_usage["canonical_request_bytes"]
                        + new_usage["canonical_request_bytes"],
                        "token_accounting_complete": old_usage[
                            "token_accounting_complete"
                        ]
                        and new_usage["token_accounting_complete"],
                    }
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()})
            == plan["corpus_sha256"]
        )
        if not report["corpus_unchanged"]:
            report["status"] = "failed"
        return report
    finally:
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "ingestion-report", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--parent-report", type=Path)
    parser.add_argument("--parent-run-dir", type=Path)
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--max-records", type=int, default=3)
    parser.add_argument("--max-calls", type=int, default=48)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve prior output")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "completed_records": report.get("completed_records", 0),
                "rich_edges": report.get("rich_edges", 0),
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

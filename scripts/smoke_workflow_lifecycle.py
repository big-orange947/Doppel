"""Synthetic lifecycle integration; explicit PG opt-in, no paid provider calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DeterministicMemoryGovernancePolicy,
    DoppelClient,
    HistoryWindow,
    MemoryFilter,
    MemoryScope,
    PersonalMemoryAnalysis,
    PersonalMemoryDraft,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PersonalMemoryQueryDraftV2,
    PostgreSQLStore,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
    memory_index_fingerprint,
)
from examples.checked_ingest import ingest_checked
from examples.personal_memory_runtime import PersonalMemoryWorkflow, WorkflowState
from scripts.smoke_personal_workflow import OfflineSentenceEmbedding, storage_identity

CASES = ("cancel", "retract", "revise", "temporary")


def at(day, hour=0):
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def drafts(case, day):
    key = f"{case}-{day}"
    if case == "temporary":
        return (
            []
            if day != 1
            else [
                PersonalMemoryDraft(
                    content="opaque stable",
                    memory_type="fact",
                    temporal_status="timeless",
                    topic_key="opaque.base",
                    evidence_ids=["base"],
                ),
                PersonalMemoryDraft(
                    content="opaque temporary",
                    memory_type="state",
                    temporal_status="current",
                    topic_key="opaque.slot",
                    evidence_ids=[key],
                    valid_from=at(1, 12),
                    valid_to=at(2, 12),
                ),
            ]
        )
    if day == 5 and case != "revise":
        return []
    return [
        PersonalMemoryDraft(
            content=f"opaque {case} value-{day}",
            memory_type="plan" if case == "cancel" else "state",
            temporal_status=("planned" if case == "cancel" else "current")
            if day == 1
            else "current"
            if case == "revise"
            else "historical",
            revision_kind="assertion"
            if day == 1
            else "correction"
            if case == "revise"
            else "retraction",
            topic_key="opaque.slot",
            evidence_ids=[key],
        )
    ]


class ScriptedAnalyzer:
    name, version = "smoke.synthetic-lifecycle", "1"

    def __init__(self):
        self.calls = 0
        self.script = {
            draft.evidence_ids[0]: draft
            for case in CASES
            for day in (1, 3, 5)
            for draft in drafts(case, day)
        }

    async def analyze(self, request):
        self.calls += 1
        return PersonalMemoryAnalysis(
            memories=[self.script[message.identity_key] for message in request.messages]
        )


class InterruptIndex:
    """Synthetic IndexWriter-boundary outage; not a claimed PG network failure."""

    def __init__(self, delegate):
        self.delegate, self.identity = delegate, delegate.identity
        self.failed_operations = 0

    async def upsert(self, record):
        self.failed_operations += 1
        raise ConnectionError("synthetic index interruption")

    async def delete(self, scope, memory_id):
        self.failed_operations += 1
        raise ConnectionError("synthetic index interruption")

    async def scan_entries(self, scope, **kwargs):
        return await self.delegate.scan_entries(scope, **kwargs)

    async def inspect(self, scope, memory_id):
        return await self.delegate.inspect(scope, memory_id)


class Planner:
    name, version = "smoke.explicit-current", "1"

    async def plan(self, request):
        return PersonalMemoryQueryDraftV2(search_text="opaque", temporal_view="current")


async def exercise(stage, directory, store, index, storage_key):
    day = 1 if stage == "seed" else 3 if stage in {"interrupt", "resume"} else 5
    window = HistoryWindow(start=at(day), end=at(day + 1, 12))
    analyzer = ScriptedAnalyzer()
    reports, fingerprints, checks = [], [], 0
    client = DoppelClient(store)
    for case in CASES:
        scope = MemoryScope(user_id=f"synthetic-{case}", agent_id="lifecycle")
        writer = (
            InterruptIndex(index)
            if stage == "interrupt" and case == "temporary"
            else index
        )
        workflow = PersonalMemoryWorkflow(
            directory,
            workflow_key=f"lifecycle-{case}-v1",
            storage_identity=storage_key,
            store=store,
            scope=scope,
            miner=PersonalMemoryMiner(
                analyzer, PersonalMemoryMinerConfig(owner_target_scope="conversation")
            ),
            consolidator=DeterministicMemoryConsolidator(),
            governance_policy=DeterministicMemoryGovernancePolicy(),
            index=writer,
            index_page_size=2,
        )
        saved = (
            WorkflowState.model_validate_json(workflow.path.read_text(encoding="utf-8"))
            if workflow.path.exists()
            else None
        )
        expected_day = {"interrupt": 1, "resume": 3, "update": 3, "replay": 5}.get(
            stage
        )
        if stage == "seed":
            if saved is not None:
                raise ValueError("seed requires new journals")
        elif (
            saved is None
            or saved.window.start != at(expected_day)
            or (
                saved.stage
                != (
                    "index" if stage == "resume" and case == "temporary" else "complete"
                )
            )
        ):
            raise ValueError(
                "unexpected saved lifecycle stage; inspect rather than reset"
            )
        for draft in drafts(case, day):
            await ingest_checked(
                store,
                scope,
                ChatMessage.of(
                    "owner",
                    draft.content,
                    at(day, 12),
                    message_id=draft.evidence_ids[0],
                ),
            )
        progress = []
        for _ in range(100):
            result = await workflow.step(window)
            progress.append(result)
            if not result["ok"] or result["complete"]:
                break
        else:
            raise RuntimeError("lifecycle step bound exceeded")
        interrupted = isinstance(writer, InterruptIndex)
        if interrupted:
            if (
                result["ok"]
                or result["stage"] != "index"
                or not writer.failed_operations
            ):
                raise RuntimeError("expected index interruption was not exercised")
        elif not result["ok"] or not result["complete"]:
            raise RuntimeError("lifecycle run failed")
        hits = await client.query_personal_memory(
            "opaque", [scope], planner=Planner(), now=window.end, semantic_index=index
        )
        expected = (
            {"opaque stable", "opaque temporary"}
            if case == "temporary" and day == 1
            else {"opaque stable"}
            if case == "temporary"
            else set()
            if day != 1 and case in {"cancel", "retract"}
            else set()
            if case == "cancel"
            else {f"opaque {case} value-{day}"}
        )
        if {hit.record.content for hit in hits.hits} != expected or any(
            hit.record.scope != scope for hit in hits.hits
        ):
            raise RuntimeError(
                "current synthetic evidence differs from expected lifecycle"
            )
        rows = (
            await store.scan(
                scope, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        stale = 0
        for record in rows:
            entry = await index.inspect(scope, record.memory_id)
            active = record.state.value in {"candidate", "confirmed"}
            if interrupted:
                stale += int(entry is not None and not active)
            elif (
                active
                and (
                    entry is None
                    or entry.fingerprint != memory_index_fingerprint(record)
                )
            ) or (not active and entry is not None):
                raise RuntimeError("lifecycle manifest mismatch")
            fingerprints.append(
                (scope.scope_key, record.memory_id, memory_index_fingerprint(record))
            )
            checks += 1
        if interrupted and not stale:
            raise RuntimeError("no stale inactive vector remained for guard validation")
        reports.append(
            {
                "case": case,
                "interrupted": interrupted,
                "complete": result["complete"],
                "current_hits": len(hits.hits),
                "records": len(rows),
                "stale_inactive_entries": stale,
            }
        )
    return {
        "stage": stage,
        "passed": True,
        "complete": stage != "interrupt",
        "cases": reports,
        "analyzer_calls": analyzer.calls,
        "manifest_checks": checks,
        "store_digest": hashlib.sha256(
            json.dumps(sorted(fingerprints)).encode()
        ).hexdigest(),
        "paid_calls": 0,
        "quality_score_available": False,
        "fixtures_retained": True,
    }


async def run(args):
    dsn = os.environ.get("DOPPEL_WORKFLOW_PG_DSN", "")
    key = storage_identity(dsn, args.schema)
    if not args.schema.startswith("doppel_lifecycle_"):
        raise ValueError("dedicated doppel_lifecycle_ schema required")
    store = PostgreSQLStore(dsn, schema=args.schema, create_schema=True)
    try:
        driver = importlib.import_module("asyncpg")
        connection = await driver.connect(dsn)
        try:
            exists = bool(
                await connection.fetchval(
                    "SELECT 1 FROM pg_namespace WHERE nspname=$1", args.schema
                )
            )
            if args.stage == "seed" and (exists or args.directory.exists()):
                raise ValueError("seed requires absent schema and directory")
            if args.stage != "seed" and (not exists or not args.directory.is_dir()):
                raise ValueError("resume requires existing schema and journals")
        finally:
            await connection.close()
        provider = await asyncio.to_thread(
            OfflineSentenceEmbedding, args.embedding_model_path
        )
        index = PostgreSQLVectorIndex(
            store, provider, VectorIndexConfig(create_extension=True)
        )
        await index.initialize()
        report = await exercise(args.stage, args.directory, store, index, key)
        report.update(
            embedding_calls=provider.calls,
            index=index.identity,
            schema=args.schema,
            runner="doppel.lifecycle-pg.v1",
        )
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-pg", action="store_true")
    parser.add_argument(
        "--stage",
        choices=["seed", "interrupt", "resume", "update", "replay"],
        required=True,
    )
    parser.add_argument("--schema", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--embedding-model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.live_pg or args.output.exists():
        parser.error("--live-pg and new receipt path required")
    try:
        report = asyncio.run(run(args))
    except Exception as exc:  # noqa: BLE001 - no DSN/provider bodies in receipts
        report = {
            "passed": False,
            "stage": args.stage,
            "error_type": type(exc).__name__,
            "paid_calls": 0,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

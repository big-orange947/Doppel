"""Five-call synthetic extraction/lifecycle diagnostic; no Reader/Judge or tuning."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    MemoryFilter,
    MemoryScope,
    OpenAICompatibleStructuredOutputConfig,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PersonalMemoryQueryDraftV2,
    ReferencePersonalMemoryAnalyzer,
    memory_index_fingerprint,
)
from examples.arrival_inbox import ArrivalInbox, drain_once
from examples.incremental_personal_memory import SQLiteManifestIndex
from examples.personal_memory import StructuredQueryPlanner
from examples.personal_memory_runtime import PersonalMemoryWorkflow

RUNNER = "doppel.personal-memory-lifecycle-probe.v1"
DATASET = Path(__file__).parent / "datasets/personal-memory-lifecycle-probe-v1.json"
ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 10, tzinfo=UTC)


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def prepare(dataset, config):
    if dataset["schema"] != RUNNER or len(dataset["cases"]) != 4:
        raise ValueError("four frozen diagnostic cases required")
    ids = set()
    for case in dataset["cases"]:
        if case["id"] in ids or not case["rubric"].strip() or not case["batches"]:
            raise ValueError("unique cases and rubrics required")
        ids.add(case["id"])
        messages = [
            ChatMessage.model_validate(m) for batch in case["batches"] for m in batch
        ]
        if len({m.identity_key for m in messages}) != len(messages) or any(
            not m.identity_key for m in messages
        ):
            raise ValueError("unique stable source identities required")
        for query in case["queries"]:
            draft = PersonalMemoryQueryDraftV2.model_validate(
                {k: v for k, v in query.items() if k != "id"}
            )
            if draft.subject == "contact" and draft.subject_id not in case.get(
                "allowed_subject_ids", []
            ):
                raise ValueError("explicit host contact authorization required")
    calls = sum(len(c["batches"]) for c in dataset["cases"])
    if calls != 5:
        raise ValueError("five bounded extraction windows required")
    files = [
        "benchmarks/personal_memory_lifecycle_probe.py",
        "examples/personal_memory_runtime.py",
        "examples/arrival_inbox.py",
        "examples/checked_ingest.py",
        "benchmarks/public_memory_runtime.py",
        "benchmarks/aml_evidence_representation.py",
        "benchmarks/relation_planner_quality.py",
        "benchmarks/public_memory_ingestion.py",
        "examples/incremental_personal_memory.py",
        "examples/personal_memory.py",
    ]
    files += [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "doppel_memory").rglob("*.py"))
    ]
    plan = {
        "runner": RUNNER,
        "dataset_sha256": sha(dataset),
        "provider": config.model_dump(mode="json"),
        "analyzer": "default-reference-v8",
        "miner_config": PersonalMemoryMinerConfig(
            owner_target_scope="conversation"
        ).fingerprint,
        "max_calls": calls,
        "reader_calls": 0,
        "judge_calls": 0,
        "source_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files
        },
        "failure_policy": "stop; preserve failure, no retry/repair or rubric change",
        "index": "catalog-only; no semantic retrieval",
        "review": "manual, non-independent, no aggregate quality score",
        "publication_ready": False,
    }
    return {**plan, "fingerprint": sha(plan)}


def projection(record):
    return {
        "content": record.content,
        "actor": record.actor,
        "authority": record.authority.value,
        "state": record.state.value,
        "metadata": {
            key: record.metadata.get(key)
            for key in (
                "personal_memory_type",
                "topic_key",
                "subject",
                "subject_id",
                "temporal_status",
                "revision_kind",
                "valid_from",
                "valid_to",
            )
        },
        "evidence_ids": sorted(
            ref["evidence_id"] for ref in record.metadata.get("evidence", [])
        ),
    }


class ObservingAnalyzer:
    def __init__(self, model):
        self.diagnostics, self.observations = [], []
        self.delegate = ReferencePersonalMemoryAnalyzer(
            model,
            diagnostics_observer=lambda d: self.diagnostics.append(
                d.model_dump(mode="json")
            ),
        )
        self.name, self.version = self.delegate.name, self.delegate.version

    async def analyze(self, request):
        result = await self.delegate.analyze(request)
        self.observations.append(
            {
                "input_evidence_ids": [m.identity_key for m in request.messages],
                "analysis": result.model_dump(mode="json"),
            }
        )
        return result


async def exercise(dataset, directory, model):
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "memory.sqlite3"
    client = DoppelClient(backend="sqlite", database=str(database))
    inbox = ArrivalInbox(directory / "inbox.sqlite3")
    index = SQLiteManifestIndex(directory / "catalog.sqlite3")
    analyzer = ObservingAnalyzer(model)
    rows, stopped = [], None
    try:
        for case in dataset["cases"]:
            scope = MemoryScope(
                user_id=case["id"], agent_id="synthetic-lifecycle-probe"
            )

            def factory(batch, scope=scope):
                return PersonalMemoryWorkflow(
                    directory / "jobs",
                    workflow_key=batch.identity,
                    storage_identity=str(database.resolve()),
                    store=client.store,
                    scope=scope,
                    miner=PersonalMemoryMiner(
                        analyzer,
                        PersonalMemoryMinerConfig(owner_target_scope="conversation"),
                    ),
                    consolidator=DeterministicMemoryConsolidator(),
                    index=index,
                    history=batch.history(),
                    history_identity=batch.identity,
                )

            for number, batch in enumerate(case["batches"], 1):
                start = len(analyzer.observations)
                diagnostics_start = len(analyzer.diagnostics)
                row = {"case_id": case["id"], "batch": number, "status": "failed"}
                try:
                    for raw in batch:
                        await inbox.append(scope, ChatMessage.model_validate(raw))
                    progress = await drain_once(inbox, scope, client.store, factory)
                    row["progress"] = progress
                    records = (
                        await client.store.scan(
                            scope,
                            filters=MemoryFilter(include_inactive=True),
                            limit=100,
                        )
                    ).records
                    if len(records) >= 100:
                        raise RuntimeError("audit bound reached")
                    row["records"] = [r.model_dump(mode="json") for r in records]
                    row["projection"] = sorted(
                        (projection(r) for r in records if r.extractor != "ingestor"),
                        key=sha,
                    )
                    row["observations"] = analyzer.observations[start:]
                    row["schema_diagnostics"] = analyzer.diagnostics[diagnostics_start:]
                    if not progress.get("ok") or not progress["complete"]:
                        raise RuntimeError(
                            "workflow did not complete; preserved report"
                        )
                    for r in records:
                        entry = await index.inspect(scope, r.memory_id)
                        active = r.state.value in {"candidate", "confirmed"}
                        if (entry is not None) != active or (
                            entry is not None
                            and entry.fingerprint != memory_index_fingerprint(r)
                        ):
                            raise RuntimeError("catalog mismatch")
                    views = {}
                    for q in case["queries"]:
                        draft = PersonalMemoryQueryDraftV2.model_validate(
                            {k: v for k, v in q.items() if k != "id"}
                        )
                        result = await client.query_personal_memory(
                            "诊断视图",
                            [scope],
                            now=NOW,
                            planner=StructuredQueryPlanner(draft),
                            allowed_subject_ids=case.get("allowed_subject_ids", []),
                        )
                        views[q["id"]] = {
                            "hits": [projection(h.record) for h in result.hits],
                            "candidate_evidence": [
                                h.candidate_evidence.model_dump(mode="json")
                                for h in result.hits
                            ],
                            "warnings": result.warnings,
                        }
                    row.update(status="complete", views=views)
                except Exception as exc:  # noqa: BLE001 - preserve stage artifacts, redact exception bodies
                    row["error_type"] = type(exc).__name__
                    row["observations"] = analyzer.observations[start:]
                    row["schema_diagnostics"] = analyzer.diagnostics[diagnostics_start:]
                    stopped = {
                        "case_id": case["id"],
                        "batch": number,
                        "error_type": type(exc).__name__,
                    }
                rows.append(row)
                print(f"{case['id']} batch {number}: {row['status']}", flush=True)
                if stopped:
                    break
            if stopped:
                break
        return {
            "status": "stopped" if stopped else "complete",
            "rows": rows,
            "stopped": stopped,
        }
    finally:
        await client.close()


async def run(args):
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=2048,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        temperature=0,
    )
    plan = prepare(dataset, config)
    report = {
        "runner": RUNNER,
        "plan": plan,
        "status": "ready",
        "quality_score_available": False,
    }
    if not args.live:
        return report
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"] != plan
    ):
        raise ValueError("unchanged frozen preflight required")
    key = (
        "cache-only-unused"
        if args.cache_only
        else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    )
    if not key:
        raise ValueError("DEEPSEEK_API_KEY required")
    _bind_json(args.run_dir / "plan.json", plan)
    ledger = DurableCallLedger(
        args.run_dir / "calls.sqlite3",
        budget_id=plan["fingerprint"],
        max_calls=5,
        max_request_bytes=100_000,
        max_total_request_bytes=500_000,
    )
    provider = ObservedProvider(
        config, key, ledger.observe_usage, args.run_dir / "provider-receipts"
    )
    model = PilotStructuredModel(
        provider,
        ledger=ledger,
        cache_dir=args.run_dir / "cache",
        cache_only=args.cache_only,
    )
    try:
        before = ledger.report()["attempts_reserved"]
        report.update(await exercise(dataset, args.state_dir, model))
        report["usage"] = model.report()
        report["new_calls"] = ledger.report()["attempts_reserved"] - before
        report["semantic_digest"] = sha(
            [
                {
                    k: r.get(k)
                    for k in (
                        "case_id",
                        "batch",
                        "status",
                        "projection",
                        "views",
                        "observations",
                    )
                }
                for r in report["rows"]
            ]
        )
        return report
    finally:
        await provider.aclose()
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("new output path required; cache-only requires live execution")
    report = asyncio.run(run(args))
    _bind_json(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "rows": len(report.get("rows", [])),
                "new_calls": report.get("new_calls", 0),
            }
        )
    )
    raise SystemExit(0 if report["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

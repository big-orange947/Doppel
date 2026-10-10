"""Paired source-window diagnostic on immutable opened high-config receipts.

Reuses each original retrieval result, adds source-only linked raw context and
reruns unchanged Reader/task/citation stages. Not an end-to-end rerun or blind
score. No new planner, embeddings, reranking, graph writes or answer-based links.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.public_context_baseline import (
    execution_metadata,
    score_evidence,
    select_diagnostic_cases,
)
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_comparison import check_raw, inventory, load_bindings
from benchmarks.public_memory_expansion import (
    PrimaryOutput,
    config,
    local_diagnostic_dsn,
    primary_checks,
    primary_request,
    save,
)
from benchmarks.public_memory_graph_schema import snapshot
from benchmarks.public_memory_high_config_context import prepare_context
from benchmarks.public_memory_high_config_first import (
    STAGES,
    ReadOnlyStore,
    persisted_generation,
    reader_request,
)
from benchmarks.public_memory_high_config_preflight import bound_scopes
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.high_config import HighConfigRetrievalResult
from doppel_memory.models import MemoryIsolationError
from doppel_memory.source_window import SourceWindowConfig, expand_source_window

RUNNER = "doppel.public-memory-paired-source-window.v1"
ORDINALS = (5, 6, 7, 8)


class JournalContextResolver:
    """Original source-session turn neighbors, never chunk-local adjacency.

    Public benchmark dialogues have explicit one-to-one user/assistant turns.
    This adapter is not a group-chat policy. Original positions are journal-
    validated source order, not scoring/evidence annotations or semantic labels.
    """

    def __init__(self, store, sources):
        self.store, self.sources = store, sources
        self.positions = {}
        for (scope, event), source in sources.items():
            identity = (scope, *source.position)
            if identity in self.positions:
                raise ValueError("source position collision")
            self.positions[identity] = (event, source)

    async def resolve_context(self, scope, anchor, *, observed_until, limit):
        if anchor.scope != scope:
            raise MemoryIsolationError("journal anchor scope mismatch")
        source = self.sources.get((scope.scope_key, anchor.source_event_id))
        if source is None:
            raise ValueError("journal anchor absent")
        check_raw(anchor, source, anchor.source_event_id)
        session, turn = source.position
        neighbors = []
        # Fixed +/- one, preceding then following; no query/gold or role guessing.
        for offset in (-1, 1):
            entry = self.positions.get((scope.scope_key, session, turn + offset))
            if entry is None:
                continue
            event, neighbor = entry
            record = await self.store.get(scope, neighbor.memory_id)
            if record is None:
                raise ValueError("journal neighbor Store absent")
            if record.scope != scope:
                raise MemoryIsolationError("journal neighbor scope mismatch")
            check_raw(record, neighbor, event)
            neighbors.append(record)
        return neighbors[:limit]


def validate_parent(parent):
    if (
        parent.get("runner") != "doppel.public-memory-consecutive-high-config-query.v3"
        or parent.get("status") != "complete"
        or parent.get("scope_ordinal") not in ORDINALS
        or parent.get("clock_policy") != "provided-history-v1"
        or not all(
            parent.get(k) is True
            for k in ("corpus_unchanged", "vectors_unchanged", "graph_unchanged")
        )
    ):
        raise ValueError(
            "immutable opened parent with verified read-only integrity required"
        )
    plan = parent["plan"]
    if (
        _hash({k: v for k, v in plan.items() if k != "plan_fingerprint"})
        != plan["plan_fingerprint"]
    ):
        raise ValueError("parent plan identity mismatch")
    for name, digest in plan["source_sha256"].items():
        file = Path(name)
        # Some parent scope hashes use basename keys; resolve their explicit module.
        if not file.exists():
            file = Path("benchmarks") / name
        if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError("parent frozen implementation changed")


def build_plan(parent, bindings):
    files = [
        Path(__file__),
        Path("doppel_memory/source_window.py"),
        Path("benchmarks/public_memory_runtime.py"),
    ]
    plan = {
        "runner": RUNNER,
        "binding": bindings,
        "parent_plan_fingerprint": parent["plan"]["plan_fingerprint"],
        "scope_ordinal": parent["scope_ordinal"],
        "fixed_cohort": list(ORDINALS),
        "selection": "opened-consecutive-5-through-8-no-success-selection",
        "retrieval": "immutable-parent-checkpoint-no-planner-or-reranker-rerun",
        "source_window": SourceWindowConfig().model_dump(mode="json"),
        "link_policy": "original-source-session-turn-plus-minus-one-v1",
        "raw_output_limit": parent["plan"]["raw_output_limit"],
        "item_limit": parent["plan"]["item_limit"],
        "context_byte_limit": parent["plan"]["context_byte_limit"],
        "parent_source_sha256": parent["plan"]["source_sha256"],
        "source_sha256": {
            str(p).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "stages": {k: parent["plan"]["stages"][k] for k in STAGES if k != "planner"},
        "publication_ready": False,
        "graph_uplift_demonstrated": False,
        "aml_academic_model_compliant": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def answer(args, plan, row, expanded):
    _bind_json(args.run_dir / "plan.json", plan)
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("key environment absent")
    ledgers, models = {}, {}
    output = {}
    try:
        for stage, (calls, tokens) in STAGES.items():
            if stage == "planner":
                continue
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite3"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=calls,
                max_request_bytes=500_000,
                max_total_request_bytes=calls * 500_000,
            )
            ledgers[stage] = ledger
            models[stage] = PilotStructuredModel(
                _default_provider_factory(config(tokens), key, ledger.observe_usage),
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        reader = await persisted_generation(
            models["reader"],
            reader_request(row, expanded),
            ReaderV2Output,
            args.run_dir / "reader-output.json",
        )
        output.update(
            reader=reader.model_dump(mode="json"),
            reader_checks=structural_check(row, reader),
        )
        grade = await persisted_generation(
            models["task_judge"],
            task_request(row.runtime.query.query, row.scoring.answer, reader.answer),
            Grade,
            args.run_dir / "task-output.json",
        )
        citation = await persisted_generation(
            models["citation_judge"],
            primary_request(row, reader),
            PrimaryOutput,
            args.run_dir / "citation-output.json",
        )
        output.update(
            task_grade=grade.model_dump(mode="json"),
            citation_grade=citation.model_dump(mode="json"),
            citation_checks=primary_checks(row, citation),
            status="complete",
        )
    except Exception as error:  # noqa: BLE001 - sanitized provider boundary
        output.update(status="failed", failure_type=type(error).__name__)
    finally:
        output["usage"] = {k: m.report() for k, m in models.items()}
        for ledger in ledgers.values():
            ledger.close()
    return output


async def run(args):
    paths = {
        k: getattr(args, k) for k in ("receipt", "dataset", "manifest", "ingestion")
    }
    content = {k: p.read_bytes() for k, p in paths.items()}
    bindings = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    parent, manifest, ingestion = (
        json.loads(content[k]) for k in ("receipt", "manifest", "ingestion")
    )
    validate_parent(parent)
    for key in ("dataset", "manifest", "ingestion"):
        if parent["plan"]["binding"][key] != bindings[key]:
            raise ValueError("parent source binding changed")
    cases = select_diagnostic_cases(
        json.loads(content["dataset"]), manifest, source_sha256=bindings["dataset"]
    )
    sources = load_bindings(
        [c[0] for c in cases], manifest, ingestion, args.ingestion_dir
    )
    bindings["source_journal"] = hashlib.sha256(
        (args.ingestion_dir / "ingestion.sqlite3").read_bytes()
    ).hexdigest()
    if bindings["source_journal"] != parent["plan"]["binding"]["source_journal"]:
        raise ValueError("source journal changed")
    ordinal = parent["scope_ordinal"]
    runtime, scoring = cases[ordinal - 1]
    if (
        parent["case_id"] != scoring.case_id
        or parent["question"] != runtime.query.query
    ):
        raise ValueError("parent question/runtime mismatch")
    plan = build_plan(parent, bindings)
    scopes = bound_scopes(manifest, ingestion)
    scope = scopes[ordinal - 1]
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"),
        schema=ingestion["postgres_schema"],
    )
    try:
        records = await inventory(store, scopes)
        before = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
        if (
            before != parent["plan"]["corpus_sha256"]
            or await snapshot(scope.scope_key) != parent["plan"]["graph_snapshot"]
        ):
            raise ValueError("parent source/graph snapshot changed")
        original = HighConfigRetrievalResult.model_validate(parent["retrieval"])
        if original.base.plan.scopes != [scope]:
            raise MemoryIsolationError("parent plan scope differs from bound history")
        original_context, original_packing = prepare_context(original, records, sources)
        if (
            original_context != parent["context"]
            or original_packing != parent["packing"]
        ):
            raise ValueError("parent context cannot be reproduced from bound sources")
        expanded = await expand_source_window(
            original, store, JournalContextResolver(store, sources)
        )
        context, packing = prepare_context(expanded, records, sources)
        row = AnswerRow(
            0,
            scoring.case_id,
            "personal-high-config-source-window-v1",
            runtime,
            scoring,
            tuple(context),
        )
        positions = [
            sources[(scope.scope_key, event)].position
            for item in context
            for event in item["source_events"]
        ]
        report = {
            "runner": RUNNER,
            "status": "ready",
            "plan": plan,
            "scope_ordinal": ordinal,
            "case_id": scoring.case_id,
            "question": runtime.query.query,
            "context": context,
            "packing": packing,
            "retrieval": expanded.model_dump(mode="json"),
            "evidence_score": score_evidence(scoring, positions),
            "baseline_task_grade": parent["task_grade"],
            "baseline_evidence_score": parent["evidence_score"],
            "baseline_context_ids": [i["memory_id"] for i in parent["context"]],
            "planner_calls": 0,
            "reranker_calls": 0,
            "record_or_index_writes": 0,
            "publication_ready": False,
            "judgments_independently_verified": False,
        }
        if args.live:
            if (
                not args.frozen_preflight
                or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
                != plan
            ):
                raise ValueError("unchanged committed preflight required")
            report.update(await answer(args, plan, row, expanded))
        after = await inventory(store, scopes)
        report["corpus_unchanged"] = (
            _hash({k: r.model_dump(mode="json") for k, r in after.items()}) == before
        )
        report["graph_unchanged"] = (
            await snapshot(scope.scope_key) == parent["plan"]["graph_snapshot"]
        )
        if not report["corpus_unchanged"] or not report["graph_unchanged"]:
            report["status"] = "integrity_failed"
        report["execution_metadata"] = execution_metadata()
        return report
    finally:
        await store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "receipt",
        "dataset",
        "manifest",
        "ingestion",
        "ingestion-dir",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve output; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps(
            {
                k: report.get(k)
                for k in ("status", "scope_ordinal", "task_grade", "failure_type")
            }
        )
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

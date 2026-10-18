"""Eight opened cases: identical raw evidence with/without core structured view.

Question-independent Analyzer V10 -> real miner gates -> transient view ->
ephemeral candidate Store -> Planner V2 / QueryEngine. No production writes,
new retrieval, eager graph, gold-driven extraction, retries or default changes.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from pydantic import RootModel

from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_lazy_diagnostic import (
    EvidenceWindow,
    NoMemoryAccess,
    messages,
    miner_config,
)
from benchmarks.public_memory_passage_diagnostic import reader_request
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_task_accuracy import Grade
from benchmarks.public_memory_task_accuracy import request as task_request
from doppel_memory.batch import BatchCheckpoint, BatchTaskContext, HistoryWindow
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzerV10,
)
from doppel_memory.models import MemoryState
from doppel_memory.query import (
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryRequest,
    ReferencePersonalMemoryQueryPlannerV2,
)
from doppel_memory.transient import TransientMemoryViewBuilder, group_transient_events
from integrations.aml.contract import memory_scope

RUNNER = "doppel.opened-structured-pair.v1"
ROOT = Path("data/doppel")
FILES = {
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "thirty": ROOT / "uniform-qa-11-40-prepare-live-v1.json",
    "twenty": ROOT / "uniform-qa-completion-prepare-live-v1.json",
}
QUOTAS = {
    "temporal-reasoning": 3,
    "multi-session": 3,
    "knowledge-update": 1,
    "abstention": 1,
}
ARMS = ("raw", "structured")
STAGES = {
    "analyzer": (8, 8192),
    "planner": (8, 2048),
    "reader": (16, 2048),
    "judge": (16, 1024),
}
MAX_BYTES = 110_000
MAX_VIEW_BYTES = 40_000
SOURCES = (
    __file__,
    "benchmarks/public_memory_lazy_diagnostic.py",
    "benchmarks/public_memory_passage_diagnostic.py",
    "benchmarks/public_memory_reader_v2.py",
    "benchmarks/public_memory_task_accuracy.py",
    "benchmarks/public_memory_runtime.py",
    "benchmarks/public_memory_high_config_first.py",
    "benchmarks/public_memory_answer_comparison.py",
    "benchmarks/public_memory_expansion.py",
    "benchmarks/public_longmemeval.py",
    "doppel_memory/intelligence.py",
    "doppel_memory/query.py",
    "doppel_memory/transient.py",
    "doppel_memory/consolidation.py",
    "doppel_memory/in_memory_store.py",
)


class JsonObject(RootModel[dict]):
    pass


class Probe:
    name, version = "request-probe", "1"

    async def generate(self, request):
        self.request = request
        return {"memories": []} if "messages" in request.input else {}


class BoundModel:
    """Freeze a generated request before sending; preserve interrupted attempts."""

    def __init__(self, model, path, expected):
        self.model, self.path, self.expected = model, path, expected
        self.name, self.version = model.name, model.version

    async def generate(self, request):
        if _hash(request.model_dump(mode="json")) != self.expected:
            raise ValueError("frozen request changed")
        return (
            await persisted_generation(self.model, request, JsonObject, self.path)
        ).root


def choose_cases(dataset, manifest):
    """Only parent order, public type and negative label; never old QA scores."""
    by_id = {r["question_id"]: r for r in dataset}
    if len(by_id) != len(dataset):
        raise ValueError("duplicate dataset identity")
    counts, selected = dict.fromkeys(QUOTAS, 0), []
    diagnostic = [r for r in manifest["cases"] if r["partition"] == "diagnostic"]
    reserved = {
        r["history_group"] for r in manifest["cases"] if r["partition"] != "diagnostic"
    }
    for ordinal, meta in enumerate(diagnostic, 1):
        source = by_id[meta["case_id"]]
        category = (
            "abstention"
            if meta["case_id"].endswith("_abs")
            else source["question_type"]
        )
        if category not in counts or counts[category] >= QUOTAS[category]:
            continue
        if meta["history_group"] in reserved:
            raise ValueError("reserved history overlap")
        counts[category] += 1
        selected.append((ordinal, meta, source))
    if counts != QUOTAS:
        raise ValueError("fixed quota unavailable; no replacements")
    return selected


def load_rows():
    raw = {k: p.read_bytes() for k, p in FILES.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()}
    data = {k: json.loads(v) for k, v in raw.items()}
    parent = data["manifest"]
    if parent["source_sha256"] != binding["dataset"] or parent[
        "manifest_fingerprint"
    ] != _hash({k: v for k, v in parent.items() if k != "manifest_fingerprint"}):
        raise ValueError("dataset/manifest binding changed")
    contexts = {}
    for key in ("thirty", "twenty"):
        report = data[key]
        if report["status"] != "complete" or report["plan"][
            "plan_fingerprint"
        ] != _hash(
            {k: v for k, v in report["plan"].items() if k != "plan_fingerprint"}
        ):
            raise ValueError("complete frozen preparation required")
        for entry in report["rows"]:
            if entry["case_id"] in contexts:
                raise ValueError("overlapping context sources")
            contexts[entry["case_id"]] = (
                entry,
                report["plan"]["groups"][entry["group"]],
            )
    rows = []
    for ordinal, meta, source in choose_cases(data["dataset"], parent):
        case = prepare_case(source, dataset_namespace=parent["dataset_namespace"])
        entry, group = contexts[meta["case_id"]]
        row = AnswerRow(
            len(rows),
            meta["case_id"],
            RUNNER,
            case.runtime,
            case.scoring,
            tuple(entry["context"]),
        )
        scope = memory_scope(group["manifest"]["run_namespace"], case.runtime.user_id)
        if entry["ordinal"] != ordinal or {i["scope_key"] for i in row.context} != {
            scope.scope_key
        }:
            raise ValueError("exact original scope required")
        request = reader_request(row)
        if _hash(request.model_dump(mode="json")) != entry["reader_request_sha256"]:
            raise ValueError("original Reader request changed")
        messages(row)  # raw text, actor, authority and time revalidated against source
        rows.append((ordinal, row, scope))
    return rows, binding


def batch_context(row, scope):
    source = messages(row)
    return BatchTaskContext(
        run_id=RUNNER + ":" + row.case_id,
        scope=scope,
        window=HistoryWindow(start=source[0].at, end=source[-1].at),
        checkpoint=BatchCheckpoint(),
        history=EvidenceWindow(scope, source),
        memories=NoMemoryAccess(),
    )


def query_input(row, scope):
    return PersonalMemoryQueryRequest(
        query=row.runtime.query.query,
        now=row.runtime.query.reference_time,
        default_subject_id=scope.user_id,
    )


async def requests_for(row, scope):
    analyzer, planner = Probe(), Probe()
    await ReferencePersonalMemoryAnalyzerV10(analyzer).analyze(
        PersonalMemoryAnalysisRequest(scope=scope, messages=list(messages(row)))
    )
    await ReferencePersonalMemoryQueryPlannerV2(planner).plan(query_input(row, scope))
    return {
        "analyzer": analyzer.request,
        "planner": planner.request,
        "raw": reader_request(row),
    }


async def make_plan(rows, binding):
    requests = {row.case_id: await requests_for(row, scope) for _, row, scope in rows}
    plan = {
        "runner": RUNNER,
        "input_sha256": binding,
        "source_sha256": {
            str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in SOURCES
        },
        "cases": [
            {
                "ordinal": n,
                "case_id": r.case_id,
                "context_sha256": _hash(r.context),
                "scope": s.model_dump(mode="json"),
            }
            for n, r, s in rows
        ],
        "selection": "first in frozen parent diagnostic order; 3 temporal,3 multi-session,1 update,1 abstention; no outcome selection",
        "stages": {
            k: {"max_calls": count, "config": config(tokens).model_dump(mode="json")}
            for k, (count, tokens) in STAGES.items()
        },
        "requests": {
            case: {k: _hash(v.model_dump(mode="json")) for k, v in reqs.items()}
            for case, reqs in requests.items()
        },
        "request_bytes": {
            case: {k: len(v.model_dump_json().encode()) for k, v in reqs.items()}
            for case, reqs in requests.items()
        },
        "miner": {
            "base": "existing miner_config; only max_memories bounded to40",
            "max_memories": 40,
        },
        "arms": list(ARMS),
        "arm_order": "alternating by cohort index; each case shares one analysis and one plan",
        "observation_policy": "provided history; question clock retained; horizon=max(question clock, supplied observations); not causal replay",
        "view_policy": "unverified candidate interpretations; source subset incomplete; no global exact count; no source deletion; Reader prompt/schema unchanged",
        "compute_limitation": "structured arm has extra LLM computation and up to40000 extra UTF8 bytes; not token-budget matched",
        "query_config": "production defaults; no semantic/relation index in transient Store; raw fallback always preserved",
        "max_request_bytes": MAX_BYTES,
        "max_view_bytes": MAX_VIEW_BYTES,
        "new_call_cap": 48,
        "opened_diagnostic_not_blind": True,
        "publication_ready": False,
    }
    if any(
        n > MAX_BYTES for req in plan["request_bytes"].values() for n in req.values()
    ):
        raise ValueError("preflight request exceeds bound")
    return {**plan, "plan_fingerprint": _hash(plan)}


def export_view(view, result):
    """Keep all candidates; engine selection is an index, not an evidence gate."""
    claims = []
    for claim in view.claims:
        body = claim.model_dump(mode="json")
        body["evidence"] = [
            {k: e[k] for k in ("evidence_id", "actor", "authority", "observed_at")}
            for e in body["evidence"]
        ]
        claims.append(body)
    value = {
        "format": RUNNER,
        "interpretation_only": True,
        "semantic_evidence_verified": False,
        "source_subset_complete_history": False,
        "guidance": "Optional candidate interpretations, not additional evidence or confirmed facts. Check original raw items; unknown validity is not false. An omitted or filtered claim does not imply no answer. Cite only original context memory_ids. Event grouping is advisory, not a verified count.",
        "reference_time": view.reference_time.isoformat(),
        "observed_until": view.observed_until.isoformat(),
        "claims": claims,
        "event_groups": [
            {
                "claim_ids": [c.claim_id for c in g.claims],
                "event_key": g.event_key,
                "identity_basis": g.identity_basis,
                "semantic_identity_verified": False,
                "temporal_metadata_consistent": g.temporal_metadata_consistent,
            }
            for g in group_transient_events(view)
        ],
        "query": {
            "plan": result.plan.model_dump(mode="json"),
            "selected_claim_ids": [h.record.memory_id for h in result.hits],
            "warnings": result.warnings,
            "candidate_subset_scan_complete": result.complete,
            "whole_history_count": {
                "status": "indeterminate",
                "value": None,
                "reason": "retrieved source subset is not a complete history; no exact total authorized",
            },
        },
    }
    if (
        len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())
        > MAX_VIEW_BYTES
    ):
        raise ValueError("view exceeds frozen bound; no truncation")
    return value


def augmented_request(row, view):
    base = reader_request(row)
    request = base.model_copy(
        update={"input": {**base.input, "optional_structured_memory_view": view}}
    )
    if len(request.model_dump_json().encode()) > MAX_BYTES:
        raise ValueError("Reader request exceeds bound")
    return request


async def structured_view(row, scope, analyzer_model, planner_model):
    diagnostics = []
    miner = PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzerV10(
            analyzer_model, diagnostics_observer=diagnostics.append
        ),
        miner_config(len(messages(row))).model_copy(update={"max_memories": 40}),
    )
    proposals = await miner.propose(batch_context(row, scope))
    horizon = max(row.runtime.query.reference_time, *(m.at for m in messages(row)))
    view = await TransientMemoryViewBuilder().build(
        PersonalMemoryAnalysisRequest(scope=scope, messages=list(messages(row))),
        proposals.proposals,
        reference_time=row.runtime.query.reference_time,
        observed_until=horizon,
    )
    store = InMemoryStore()
    for proposal, claim in zip(proposals.proposals, view.claims, strict=True):
        record = proposal.to_record().model_copy(update={"memory_id": claim.claim_id})
        if record.state != MemoryState.CANDIDATE:
            raise ValueError("candidate promotion forbidden")
        written = await store.put(record)
        if not written.accepted:
            raise ValueError("ephemeral write failed")
    engine = PersonalMemoryQueryEngine(store)
    plan = await engine.plan(
        ReferencePersonalMemoryQueryPlannerV2(planner_model),
        row.runtime.query.query,
        [scope],
        now=row.runtime.query.reference_time,
        observed_until=horizon,
    )
    result = await engine.execute(plan, trace_limit=40)
    return export_view(view, result), {
        "transient_view": view.model_dump(mode="json"),
        "engine_result": result.model_dump(mode="json"),
        "parser_diagnostics": [
            d.model_dump(mode="json") if hasattr(d, "model_dump") else d
            for d in diagnostics
        ],
        "miner_checkpoint": proposals.next_checkpoint.model_dump(mode="json")
        if proposals.next_checkpoint
        else None,
        "production_writes": 0,
    }


def summarize(rows):
    result = {}
    for arm in ARMS:
        done = [r for r in rows if r.get("arms", {}).get(arm, {}).get("grade")]
        result[arm] = {
            "completed": len(done),
            "correct": sum(r["arms"][arm]["grade"]["answer_correct"] for r in done),
        }
    paired = [
        r for r in rows if all(r.get("arms", {}).get(a, {}).get("grade") for a in ARMS)
    ]
    result["paired"] = {
        "completed": len(paired),
        "gains": sum(
            not r["arms"]["raw"]["grade"]["answer_correct"]
            and r["arms"]["structured"]["grade"]["answer_correct"]
            for r in paired
        ),
        "regressions": sum(
            r["arms"]["raw"]["grade"]["answer_correct"]
            and not r["arms"]["structured"]["grade"]["answer_correct"]
            for r in paired
        ),
    }
    return result


async def execute(args, rows, plan):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("provider key absent")
    ledgers, models, results = {}, {}, []
    failure, current, stage = None, None, "initialization"
    try:
        for name, (count, tokens) in STAGES.items():
            ledger = DurableCallLedger(
                args.run_dir / "usage.sqlite3",
                budget_id=plan["plan_fingerprint"] + ":" + name,
                max_calls=count,
                max_request_bytes=MAX_BYTES,
                max_total_request_bytes=count * MAX_BYTES,
            )
            ledgers[name] = ledger
            if ledger.report()["attempts_reserved"] and not args.cache_only:
                raise ValueError("preserve previous attempts; cache-only replay only")
            provider = _default_provider_factory(
                config(tokens), key, ledger.observe_usage
            )
            models[name] = PilotStructuredModel(
                provider,
                ledger=ledger,
                cache_dir=args.run_dir / name,
                cache_only=args.cache_only,
            )
        for i, (ordinal, row, scope) in enumerate(rows):
            current, stage = row.case_id, "structured-view"
            entry = {
                "ordinal": ordinal,
                "case_id": current,
                "question_type": row.scoring.category,
                "abstention_label": row.scoring.abstention,
                "arms": {},
            }
            results.append(entry)

            def bound(name, i=i, current=current):
                return BoundModel(
                    models[name],
                    args.run_dir / "receipts" / f"{i}-{name}.json",
                    plan["requests"][current][name],
                )

            view, audit = await structured_view(
                row, scope, bound("analyzer"), bound("planner")
            )
            entry["audit"] = audit
            requests = {
                "raw": reader_request(row),
                "structured": augmented_request(row, view),
            }
            # Immutable dynamic binding is saved BEFORE either paid Reader call.
            frozen = {a: _hash(r.model_dump(mode="json")) for a, r in requests.items()}
            dynamic_path = args.run_dir / f"dynamic-{i}.json"
            dynamic = {"case_id": current, "requests": frozen, "view": view}
            if dynamic_path.exists():
                if json.loads(dynamic_path.read_bytes()) != dynamic:
                    raise ValueError("dynamic frozen request changed")
            else:
                save(dynamic_path, dynamic)
            for arm in ARMS if i % 2 == 0 else tuple(reversed(ARMS)):
                stage = arm + ":reader"
                request = requests[arm]
                output = ReaderV2Output.model_validate(
                    await BoundModel(
                        models["reader"],
                        args.run_dir / "receipts" / f"{i}-{arm}-reader.json",
                        frozen[arm],
                    ).generate(request)
                )
                checks = structural_check(row, output)
                if not checks["structurally_valid"]:
                    raise ValueError("invalid Reader citations/structure")
                stage = arm + ":judge"
                judged = task_request(
                    row.runtime.query.query, row.scoring.answer, output.answer
                )
                grade = Grade.model_validate(
                    await BoundModel(
                        models["judge"],
                        args.run_dir / "receipts" / f"{i}-{arm}-judge.json",
                        _hash(judged.model_dump(mode="json")),
                    ).generate(judged)
                )
                entry["arms"][arm] = {
                    "reader_request_sha256": frozen[arm],
                    "request_bytes": len(request.model_dump_json().encode()),
                    "reader_output": output.model_dump(mode="json"),
                    "checks": checks,
                    "grade": grade.model_dump(mode="json"),
                }
            if not args.cache_only:
                save(args.run_dir / f"case-{i}.json", entry)
            print(
                f"paired {i + 1}/8 (ordinal {ordinal}): {summarize(results)}",
                flush=True,
            )
        status = "complete"
    except Exception as exc:  # noqa: BLE001 - no provider/key exception text
        status, failure = "failed", type(exc).__name__
    report = {
        "status": status,
        "rows": results,
        "summary": summarize(results),
        "failure_class": failure,
        "stopped_case": current if failure else None,
        "stopped_stage": stage if failure else None,
        "usage": {n: l.report() for n, l in ledgers.items()},
    }
    for ledger in ledgers.values():
        ledger.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.execute):
        parser.error("fresh output required; cache-only requires execute")
    rows, binding = load_rows()
    plan = asyncio.run(make_plan(rows, binding))
    result = {"runner": RUNNER, "status": "ready", "plan": plan}
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        result.update(asyncio.run(execute(args, rows, plan)))
    save(args.output, result)
    print(
        json.dumps({"status": result["status"], "summary": result.get("summary", {})})
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

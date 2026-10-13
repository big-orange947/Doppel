"""Five opened source-order cases: fixed raw/proposals with versus without time view.

No outcome selection, new retrieval/graph, production writes or live Judge.
All previous frozen runners/artifacts remain unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.public_context_baseline import (
    execution_metadata,
    select_diagnostic_cases,
)
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_lazy_diagnostic import (
    MAX_BYTES,
    ReceiptedAnalyzerModel,
    analyzer_request,
    messages,
    miner_config,
    project_proposals,
    reader_request,
    task_context,
)
from benchmarks.public_memory_oracle_diagnostic import balance
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_quality_50 import build_plan as quality_plan
from benchmarks.public_memory_quality_50 import prepare_batches
from benchmarks.public_memory_reader_v2 import ReaderV2Output, structural_check
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.public_memory_transient_view import ARMS, DECODER, compact_view
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzer,
)
from doppel_memory.transient import TransientMemoryViewBuilder

RUNNER = "doppel.public-memory-transient-cohort.v1"
QUOTAS = {"temporal-reasoning": 2, "knowledge-update": 2, "abstention": 1}


def select_ids(source, manifest, excluded, protected):
    allowed = {
        r["case_id"] for r in manifest["cases"] if r["partition"] == "diagnostic"
    }
    blocked = (
        set(excluded)
        | set(protected)
        | {r["case_id"] for r in manifest["cases"] if r["partition"] == "reserved"}
    )
    if len({r["question_id"] for r in source}) != len(source):
        raise ValueError("duplicate source case IDs")
    counts, chosen = dict.fromkeys(QUOTAS, 0), []
    for row in source:
        identity = row["question_id"]
        category = "abstention" if identity.endswith("_abs") else row["question_type"]
        if (
            identity in allowed
            and identity not in blocked
            and category in QUOTAS
            and counts[category] < QUOTAS[category]
        ):
            chosen.append(identity)
            counts[category] += 1
    if counts != QUOTAS:
        raise ValueError(
            "fixed category quotas unavailable; no replacement or resampling"
        )
    return chosen


def load_rows(args):
    contents = {
        k: getattr(args, k).read_bytes()
        for k in ("source", "manifest", "comparison", "quality", "previous")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    data = {k: json.loads(v) for k, v in contents.items()}
    protected = set()
    for path in args.prior_manifest:
        raw = path.read_bytes()
        prior = json.loads(raw)
        if prior["source_sha256"] != binding["source"] or prior[
            "manifest_fingerprint"
        ] != _hash({k: v for k, v in prior.items() if k != "manifest_fingerprint"}):
            raise ValueError("reserved source/manifest changed")
        binding[str(path)] = hashlib.sha256(raw).hexdigest()
        protected.update(
            r["case_id"] for r in prior["cases"] if r["partition"] == "reserved"
        )
    previous = data["previous"]
    if (
        previous.get("runner") != "doppel.public-memory-transient-view-diagnostic.v1"
        or previous.get("status") != "complete"
    ):
        raise ValueError("completed previous cohort required for exclusion")
    excluded = {r["case_id"] for r in previous["rows"]}
    if len(excluded) != 2:
        raise ValueError("two prior cases must remain excluded")
    cases = select_diagnostic_cases(
        data["source"], data["manifest"], source_sha256=binding["source"]
    )
    batches = prepare_batches(cases, data["manifest"], data["comparison"])
    parent = data["quality"]
    if (
        parent.get("status") != "complete"
        or parent.get("runner") != "doppel.public-memory-quality-50.v1"
        or parent["plan"]["input_sha256"]
        != {
            "dataset": binding["source"],
            "manifest": binding["manifest"],
            "comparison": binding["comparison"],
        }
        or quality_plan(batches, parent["plan"]["input_sha256"]) != parent["plan"]
    ):
        raise ValueError("unchanged complete fifty-case QA source binding required")
    # Validate every old stage identity/request hash; never consume its answer or
    # score for selection. Original contexts are rebuilt from the bound comparison.
    for actual, frozen in zip(
        parent["batches"], parent["plan"]["batch_rows"], strict=True
    ):
        if len(actual["rows"]) != len(frozen["identities"]):
            raise ValueError("incomplete prior QA batch")
        for r, identity, sha in zip(
            actual["rows"], frozen["identities"], frozen["reader_requests"], strict=True
        ):
            if [r["index"], r["case_id"], r["profile"]] != list(identity) or r[
                "reader"
            ]["request_sha256"] != sha:
                raise ValueError("prior QA identity/request changed")
    ids = select_ids(data["source"], data["manifest"], excluded, protected)
    by_id = {
        r.case_id: r
        for batch in batches
        for r in batch
        if r.profile == "raw_vector_reranked"
    }
    rows = [replace(by_id[i], index=n) for n, i in enumerate(ids)]
    for row in rows:
        messages(row)  # original raw text, actor/authority/time/source binding
    return rows, binding


def paired_requests(row, proposals, view):
    base = reader_request(row, proposals)
    result = {}
    for arm in ARMS:
        request = base.model_copy(
            update={
                "instructions": base.instructions + DECODER,
                "input": {
                    **base.input,
                    "temporal_view": compact_view(view) if arm == ARMS[1] else None,
                },
            }
        )
        if len(request.model_dump_json().encode()) > MAX_BYTES:
            raise ValueError("dynamic Reader input too large; no truncation")
        result[arm] = request
    return result


async def build_plan(rows, bindings):
    requests = {r.case_id: await analyzer_request(r) for r in rows}
    if len(rows) != 5 or len({r.case_id for r in rows}) != 5:
        raise ValueError("five unique cases required")
    counts = {
        category: sum(
            ("abstention" if r.case_id.endswith("_abs") else r.scoring.category)
            == category
            for r in rows
        )
        for category in QUOTAS
    }
    if counts != QUOTAS:
        raise ValueError("five-case category quotas changed")
    if any(len(r.model_dump_json().encode()) > MAX_BYTES for r in requests.values()):
        raise ValueError("analyzer request too large; no truncation")
    root = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__),
        *[
            root / p
            for p in (
                "benchmarks/public_memory_lazy_diagnostic.py",
                "benchmarks/public_memory_transient_view.py",
                "benchmarks/aml_evidence_representation.py",
                "benchmarks/public_memory_quality_50.py",
                "benchmarks/public_memory_reader_v2.py",
                "benchmarks/public_memory_expansion.py",
                "benchmarks/public_memory_runtime.py",
                "benchmarks/public_memory_high_config_first.py",
                "benchmarks/public_context_baseline.py",
                "benchmarks/public_memory_response_policy.py",
                "doppel_memory/intelligence.py",
                "doppel_memory/consolidation.py",
                "doppel_memory/transient.py",
            )
        ],
    ]
    plan = {
        "runner": RUNNER,
        "bindings": bindings,
        "case_ids": [r.case_id for r in rows],
        "selection": "original source order; opened-only; 2 temporal/2 update/1 _abs; exclude prior two and all reserved; no score selection",
        "quotas": QUOTAS,
        "arms": list(ARMS),
        "categories": [
            "abstention" if r.case_id.endswith("_abs") else r.scoring.category
            for r in rows
        ],
        "source_context_sha256": {r.case_id: _hash(r.context) for r in rows},
        "source_items": {r.case_id: len(r.context) for r in rows},
        "analyzer_requests": {
            k: _hash(v.model_dump(mode="json")) for k, v in requests.items()
        },
        "analyzer_request_bytes": {
            k: len(v.model_dump_json().encode()) for k, v in requests.items()
        },
        "observations_after_reference": {
            r.case_id: sum(m.at > r.runtime.query.reference_time for m in messages(r))
            for r in rows
        },
        "analyzer_config": config(4096).model_dump(mode="json"),
        "reader_config": config(1024).model_dump(mode="json"),
        "miner_fingerprints": {
            r.case_id: miner_config(len(messages(r))).fingerprint for r in rows
        },
        "max_analyzer_calls": 5,
        "max_reader_calls": 10,
        "max_judge_calls": 0,
        "max_new_calls": 15,
        "max_request_bytes": MAX_BYTES,
        "balance_stop_cny": 1,
        "dynamic_reader_requests": "freeze generation rule, receipt each actual request before call; derived from actual gated proposals only",
        "arm_order": "alternate order per case after one shared analysis; same schema/common decoder/source order",
        "observation_policy": "provided-history-v1; explicit horizon; not causal replay",
        "contrast": "same raw and proposals, added unapplied time index and length; not independent/official/AML; no default promotion",
        "failure_policy": "single attempt; fail-stop; retain failure/partial rows; no retry/repair/resampling",
        "core_runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "source_sha256": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "publication_ready": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def execute(args, rows, plan, *, provider_factory=None, balance_reader=balance):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("DEEPSEEK_API_KEY missing")
    _bind_json(args.run_dir / "plan.json", plan)
    initial, final = None, None
    if not args.cache_only:
        current = await balance_reader(key)
        start = args.run_dir / "balance-start.json"
        if not start.exists():
            save(start, {"initial_cny": current})
        initial = json.loads(start.read_bytes())["initial_cny"]
    ledgers, providers, models = {}, {}, {}
    outcomes, stopped = [], ""
    try:
        for stage, tokens, cap in (("analyzer", 4096, 5), ("reader", 1024, 10)):
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=cap,
                max_request_bytes=MAX_BYTES,
                max_total_request_bytes=MAX_BYTES * cap,
            )
            ledgers[stage] = ledger
            provider = (
                provider_factory(config(tokens), key, ledger.observe_usage)
                if provider_factory
                else ObservedProvider(
                    config(tokens),
                    key,
                    ledger.observe_usage,
                    args.run_dir / "model-receipts" / stage,
                )
            )
            providers[stage] = provider
            models[stage] = PilotStructuredModel(
                provider,
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        for index, row in enumerate(rows):
            result = {"case_id": row.case_id, "status": "failed", "arms": {}}
            stage = "analyzer"
            try:
                if not args.cache_only:
                    final = await balance_reader(key)
                    if final <= 0 or initial - final >= plan["balance_stop_cny"]:
                        raise ValueError("observed balance stop")
                diagnostics = []
                model = ReceiptedAnalyzerModel(
                    models["analyzer"],
                    args.run_dir / "receipts" / (row.case_id + "-analysis.json"),
                    plan["analyzer_requests"][row.case_id],
                )
                analyzer = ReferencePersonalMemoryAnalyzer(
                    model,
                    diagnostics_observer=lambda d, sink=diagnostics: sink.append(
                        d.model_dump(mode="json")
                    ),
                )
                task = task_context(row)
                generated = await PersonalMemoryMiner(
                    analyzer, miner_config(len(messages(row)))
                ).propose(task)
                if (
                    generated.next_checkpoint is None
                    or generated.next_checkpoint.metadata["truncated"]
                ):
                    raise ValueError("incomplete source window")
                proposals = project_proposals(row, generated.proposals)
                view = await TransientMemoryViewBuilder().build(
                    PersonalMemoryAnalysisRequest(
                        scope=task.scope, messages=list(messages(row))
                    ),
                    generated.proposals,
                    reference_time=row.runtime.query.reference_time,
                    observed_until=max(
                        row.runtime.query.reference_time, *(m.at for m in messages(row))
                    ),
                )
                result["analysis"] = {
                    "proposals": proposals,
                    "schema_diagnostics": diagnostics,
                    "checkpoint": generated.next_checkpoint.model_dump(mode="json"),
                }
                result["view"] = view.model_dump(mode="json")
                requests = paired_requests(row, proposals, view)
                print(f"{row.case_id} analysis: complete", flush=True)
                for arm in ARMS if index % 2 == 0 else ARMS[::-1]:
                    stage = arm
                    if not args.cache_only:
                        final = await balance_reader(key)
                        if final <= 0 or initial - final >= plan["balance_stop_cny"]:
                            raise ValueError("observed balance stop")
                    request = requests[arm]
                    output = await persisted_generation(
                        models["reader"],
                        request,
                        ReaderV2Output,
                        args.run_dir / "receipts" / (row.case_id + "-" + arm + ".json"),
                    )
                    checks = structural_check(row, output)
                    result["arms"][arm] = {
                        "output": output.model_dump(mode="json"),
                        "checks": checks,
                        "request_sha256": _hash(request.model_dump(mode="json")),
                        "request_bytes": len(request.model_dump_json().encode()),
                    }
                    if not checks["structurally_valid"]:
                        raise ValueError("invalid citation or derivation")
                    print(f"{row.case_id} {arm}: complete", flush=True)
                result["status"] = "complete"
            except Exception as error:  # noqa: BLE001 - no provider/credential/source exception text
                result.update(failure_type=type(error).__name__, failure_stage=stage)
                stopped = "preserved_failure_no_retry"
            outcomes.append(result)
            if stopped:
                break
        if not args.cache_only:
            try:
                final = await balance_reader(key)
            except Exception:  # noqa: BLE001 - unobserved balance stays unknown
                final = None
        return {
            "status": "complete" if len(outcomes) == 5 and not stopped else "stopped",
            "rows": outcomes,
            "stopped_reason": stopped,
            "usage": {s: m.report() for s, m in models.items()},
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": final,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()
        for provider in providers.values():
            if hasattr(provider, "aclose"):
                await provider.aclose()


async def run(args):
    rows, binding = load_rows(args)
    plan = await build_plan(rows, binding)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "record_or_index_writes": 0,
        "retrieval_rerun": False,
        "reserved_histories_executed": False,
        "publication_ready": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source",
        "manifest",
        "comparison",
        "quality",
        "previous",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(
        json.dumps({"status": report["status"], "case_ids": report["plan"]["case_ids"]})
    )
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

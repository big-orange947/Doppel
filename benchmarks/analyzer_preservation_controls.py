"""Small paired V8/V9 extraction controls, no task Reader, Judge or corpus tuning."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_lazy_diagnostic import (
    EvidenceWindow,
    NoMemoryAccess,
    ProbeModel,
    ReceiptedAnalyzerModel,
    miner_config,
)
from benchmarks.public_memory_oracle_diagnostic import balance
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.batch import BatchCheckpoint, BatchTaskContext, HistoryWindow
from doppel_memory.intelligence import (
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzer,
    ReferencePersonalMemoryAnalyzerV9,
)
from doppel_memory.models import ChatMessage, MemoryScope

RUNNER = "doppel.analyzer-preservation-controls.v1"
PROFILES = {
    "v8": ReferencePersonalMemoryAnalyzer,
    "v9": ReferencePersonalMemoryAnalyzerV9,
}
DEFAULT_CONTROLS = (
    Path(__file__).parent / "datasets/analyzer-preservation-controls-v1.json"
)
MAX_BYTES = 100_000


def contexts(dataset, *, runner=RUNNER):
    if dataset.get("schema") != runner or len(dataset["cases"]) != 8:
        raise ValueError("eight frozen controls required")
    result = {}
    for case in dataset["cases"]:
        if case["id"] in result or not case["rubric"].strip():
            raise ValueError("unique controls and frozen rubric required")
        scope = MemoryScope(user_id=case["id"], agent_id="preservation-controls-agent")
        messages = tuple(
            sorted(
                (
                    ChatMessage(
                        message_id=m["id"],
                        actor=m["actor"],
                        text=m["text"],
                        at=datetime.fromisoformat(m["at"]),
                        sender_id=scope.user_id
                        if m["actor"] == "owner"
                        else "historical-agent",
                    )
                    for m in case["messages"]
                ),
                key=lambda m: (m.at, m.identity_key),
            )
        )
        if (
            not messages
            or len({m.identity_key for m in messages}) != len(messages)
            or any(m.actor not in {"owner", "agent"} or not m.text for m in messages)
        ):
            raise ValueError("explicit unique owner/agent source bindings required")
        result[case["id"]] = BatchTaskContext(
            run_id=runner + ":" + case["id"],
            scope=scope,
            window=HistoryWindow(start=messages[0].at, end=messages[-1].at),
            checkpoint=BatchCheckpoint(),
            history=EvidenceWindow(scope, messages),
            memories=NoMemoryAccess(),
        )
    return result


async def prepare(dataset_bytes, *, runner=RUNNER, profiles=None, source_files=()):
    profiles = PROFILES if profiles is None else profiles
    if len(profiles) != 2:
        raise ValueError("two paired profiles required")
    dataset = json.loads(dataset_bytes)
    bound = contexts(dataset, runner=runner)
    requests = {}
    for identity, context in bound.items():
        for profile, cls in profiles.items():
            probe = ProbeModel()
            await PersonalMemoryMiner(
                cls(probe), miner_config(len(context.history.source))
            ).propose(context)
            requests[identity, profile] = probe.request
        a, b = [requests[identity, p] for p in profiles]
        if a.input != b.input or a.output_schema != b.output_schema:
            raise ValueError("only instructions/analyzer identity may change")
    root = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__),
        *source_files,
        *[
            root / p
            for p in (
                "doppel_memory/intelligence.py",
                "benchmarks/aml_evidence_representation.py",
                "benchmarks/public_memory_runtime.py",
                "benchmarks/public_memory_lazy_diagnostic.py",
                "benchmarks/public_memory_high_config_first.py",
                "benchmarks/public_memory_expansion.py",
            )
        ],
    ]
    order = [
        [identity, p]
        for n, identity in enumerate(bound)
        for p in (tuple(profiles) if n % 2 == 0 else tuple(profiles)[::-1])
    ]
    plan = {
        "runner": runner,
        "controls_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "execution_order": order,
        "provider_config": config(2048).model_dump(mode="json"),
        "analyzer_versions": {p: cls.version for p, cls in profiles.items()},
        "request_sha256": {
            c + ":" + p: _hash(requests[c, p].model_dump(mode="json")) for c, p in order
        },
        "request_bytes": {
            c + ":" + p: len(requests[c, p].model_dump_json().encode())
            for c, p in order
        },
        "max_analyzer_calls": 16,
        "max_reader_calls": 0,
        "max_judge_calls": 0,
        "max_request_bytes": MAX_BYTES,
        "balance_stop_cny": 1,
        "default_v8_changed": False,
        "contrast": "same evidence/schema/model/gates; generic compatible-only preservation prompt/identity",
        "failure_policy": "single attempt; fail-stop; retain failures; no retry/repair/rubric change",
        "review": "manual frozen rubrics; source/output quotes; non-independent; provenance not semantics",
        "core_runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "source_sha256": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "publication_ready": False,
        "old_task_cases_executed": False,
    }
    if any(size > MAX_BYTES for size in plan["request_bytes"].values()):
        raise ValueError("oversize control; no truncation")
    plan["plan_fingerprint"] = _hash(plan)
    return bound, requests, plan


async def execute(
    args, bound, plan, *, provider_factory=None, balance_reader=balance, profiles=None
):
    profiles = PROFILES if profiles is None else profiles
    if plan["analyzer_versions"] != {p: cls.version for p, cls in profiles.items()}:
        raise ValueError("frozen analyzer profiles mismatch")
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
    ledger = DurableCallLedger(
        args.run_dir / "analyzer.sqlite",
        budget_id=plan["plan_fingerprint"],
        max_calls=16,
        max_request_bytes=MAX_BYTES,
        max_total_request_bytes=MAX_BYTES * 16,
    )
    provider = (
        provider_factory(config(2048), key, ledger.observe_usage)
        if provider_factory
        else ObservedProvider(
            config(2048), key, ledger.observe_usage, args.run_dir / "model-receipts"
        )
    )
    model = PilotStructuredModel(
        provider,
        ledger=ledger,
        cache_dir=args.run_dir / "analyzer",
        cache_only=args.cache_only,
    )
    rows, stopped = [], ""
    try:
        for identity, profile in plan["execution_order"]:
            result = {"case_id": identity, "profile": profile, "status": "failed"}
            try:
                if not args.cache_only:
                    final = await balance_reader(key)
                    if final <= 0 or initial - final >= plan["balance_stop_cny"]:
                        raise ValueError("observed balance stop")
                context = bound[identity]
                diagnostics = []
                receipt_model = ReceiptedAnalyzerModel(
                    model,
                    args.run_dir / "receipts" / (identity + "-" + profile + ".json"),
                    plan["request_sha256"][identity + ":" + profile],
                )
                analyzer = profiles[profile](
                    receipt_model,
                    diagnostics_observer=lambda d, sink=diagnostics: sink.append(
                        d.model_dump(mode="json")
                    ),
                )
                generated = await PersonalMemoryMiner(
                    analyzer, miner_config(len(context.history.source))
                ).propose(context)
                if (
                    generated.next_checkpoint is None
                    or generated.next_checkpoint.metadata["truncated"]
                ):
                    raise ValueError("incomplete control window")
                result.update(
                    status="complete",
                    proposals=[p.model_dump(mode="json") for p in generated.proposals],
                    schema_diagnostics=diagnostics,
                    checkpoint=generated.next_checkpoint.model_dump(mode="json"),
                    analyzer_version=analyzer.version,
                )
            except Exception as error:  # noqa: BLE001 - no provider/credential/source exception text
                result["failure_type"] = type(error).__name__
                stopped = "preserved_failure_no_retry"
            rows.append(result)
            print(f"{identity} {profile}: {result['status']}", flush=True)
            if stopped:
                break
        if not args.cache_only:
            try:
                final = await balance_reader(key)
            except Exception:  # noqa: BLE001 - accounting uncertainty remains explicit
                final = None
        return {
            "status": "complete" if len(rows) == 16 and not stopped else "stopped",
            "rows": rows,
            "stopped_reason": stopped,
            "usage": model.report(),
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": final,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        ledger.close()
        if hasattr(provider, "aclose"):
            await provider.aclose()


async def run(args):
    data = args.controls.read_bytes()
    bound, _requests, plan = await prepare(data)
    result = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "record_or_index_writes": 0,
        "publication_ready": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        result.update(await execute(args, bound, plan))
    result["execution_metadata"] = execution_metadata()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    for name in ("run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve outputs; cache-only requires live")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(json.dumps({"status": result["status"], "rows": len(result.get("rows", []))}))
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

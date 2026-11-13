"""Independent candidate arm after the original paired run stopped; no retry."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.personal_memory_lifecycle_probe import exercise, sha
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from benchmarks.source_clause_probe import DATASET, ROOT
from doppel_memory import OpenAICompatibleStructuredOutputConfig
from doppel_memory.source_clauses import SourceClausePersonalMemoryAnalyzer


async def run(args):
    parent = Path("data/doppel/source-clause-probe-v1-live.json")
    prior = json.loads(parent.read_text(encoding="utf-8"))
    if prior["status"] != "stopped" or prior["new_calls"] != 2:
        raise ValueError("expected retained two-attempt parent")
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        prior["plan"]["provider"]
    )
    files = sorted((ROOT / "doppel_memory").rglob("*.py")) + [
        Path(__file__),
        ROOT / "benchmarks/source_clause_probe.py",
        ROOT / "benchmarks/personal_memory_lifecycle_probe.py",
    ]
    plan = {
        "runner": "doppel.source-clause-followup.v1",
        "parent_sha256": hashlib.sha256(parent.read_bytes()).hexdigest(),
        "parent_attempts": 2,
        "max_new_attempts": 3,
        "dataset_sha256": sha(data),
        "provider": config.model_dump(mode="json"),
        "source_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "policy": "candidate-only independent arm; no original request retry, no rubric/prompt change; fail stop",
    }
    plan["fingerprint"] = sha(plan)
    report = {"plan": plan, "status": "ready", "quality_score_available": False}
    if not args.live:
        return report
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"] != plan
    ):
        raise ValueError("matching preflight required")
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
        max_calls=3,
        max_request_bytes=100000,
        max_total_request_bytes=300000,
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
        if before and not args.cache_only:
            raise ValueError("prior attempts retained; cache-only required")
        report.update(
            await exercise(
                data,
                args.state_dir,
                model,
                analyzer=SourceClausePersonalMemoryAnalyzer(model),
            )
        )
        report.update(
            usage=model.report(),
            new_calls=ledger.report()["attempts_reserved"] - before,
        )
        return report
    finally:
        await provider.aclose()
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["run-dir", "state-dir", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("new output required; cache-only requires live")
    result = asyncio.run(run(args))
    _bind_json(args.output, result)
    print(
        json.dumps(
            {"status": result["status"], "new_calls": result.get("new_calls", 0)}
        )
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

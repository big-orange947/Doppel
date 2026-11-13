"""Small paired source-preserving extraction through actual SQLite workflow."""

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
from doppel_memory import OpenAICompatibleStructuredOutputConfig
from doppel_memory.source_clauses import SourceClausePersonalMemoryAnalyzer

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(__file__).parent / "datasets/source-clause-probe-v1.json"


async def run(args):
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    config = OpenAICompatibleStructuredOutputConfig(
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=2048,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        temperature=0,
    )
    files = sorted((ROOT / "doppel_memory").rglob("*.py")) + [
        Path(__file__),
        ROOT / "benchmarks/personal_memory_lifecycle_probe.py",
        ROOT / "benchmarks/public_memory_runtime.py",
        ROOT / "benchmarks/aml_evidence_representation.py",
        ROOT / "examples/arrival_inbox.py",
        ROOT / "examples/personal_memory_runtime.py",
    ]
    plan = {
        "runner": "doppel.source-clause-probe.v1",
        "dataset_sha256": sha(data),
        "provider": config.model_dump(mode="json"),
        "max_calls": 6,
        "profiles": ["default", "source_clause"],
        "source_sha256": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "review": "manual non-independent; content retention is not semantic truth",
        "publication_ready": False,
    }
    plan["fingerprint"] = sha(plan)
    result = {"plan": plan, "status": "ready", "quality_score_available": False}
    if not args.live:
        return result
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
        max_calls=6,
        max_request_bytes=100000,
        max_total_request_bytes=600000,
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
            raise ValueError("prior attempts preserved; use cache-only")
        profiles = {}
        for profile in plan["profiles"]:
            profiles[profile] = await exercise(
                data,
                args.state_dir / profile,
                model,
                analyzer=SourceClausePersonalMemoryAnalyzer(model)
                if profile == "source_clause"
                else None,
            )
            if profiles[profile]["status"] != "complete":
                break
        result.update(
            status="complete"
            if len(profiles) == 2
            and all(r["status"] == "complete" for r in profiles.values())
            else "stopped",
            profiles=profiles,
            usage=model.report(),
            new_calls=ledger.report()["attempts_reserved"] - before,
        )
        return result
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
        parser.error("new output required; cache-only requires live execution")
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

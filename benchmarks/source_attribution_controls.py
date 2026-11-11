"""Prospective V1/V2 source-review controls; no extraction, QA or Store writes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory import (
    ChatMessage,
    MemoryScope,
    OpenAICompatibleStructuredOutputConfig,
)
from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
)
from doppel_memory.source_grounding import (
    SourceGroundedPersonalMemoryAnalyzer,
    SourceGroundedPersonalMemoryAnalyzerV2,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path(__file__).parent / "datasets/source-attribution-controls-v1.json"
RUNNER = "doppel.source-attribution-controls.v1"
PROFILES = {
    "v1": SourceGroundedPersonalMemoryAnalyzer,
    "v2": SourceGroundedPersonalMemoryAnalyzerV2,
}


def sha(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


class StaticAnalyzer:
    name, version = "synthetic.source-attribution-drafts", "1"

    def __init__(self, case):
        self.analysis = PersonalMemoryAnalysis.model_validate(
            {"memories": case["drafts"]}
        )

    async def analyze(self, request):
        return self.analysis.model_copy(deep=True)


class Probe:
    name, version = "offline.request-probe", "1"

    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request.model_dump(mode="json"))
        sources = {s["evidence_id"]: s["text"] for s in request.input["sources"]}
        return {
            "decisions": [
                {
                    "draft_index": d["draft_index"],
                    "verdict": "uncertain",
                    "confidence": 0,
                    "quotes": [
                        {
                            "evidence_id": d["evidence_ids"][0],
                            "text": sources[d["evidence_ids"][0]],
                        }
                    ],
                }
                for d in request.input["drafts"]
            ]
        }


async def apply(case, profile, model):
    request = PersonalMemoryAnalysisRequest(
        scope=MemoryScope(user_id="synthetic-owner", agent_id="synthetic-agent"),
        messages=[ChatMessage.model_validate(m) for m in case["messages"]],
    )
    reports = []
    result = await PROFILES[profile](
        StaticAnalyzer(case), model, observer=reports.append
    ).analyze(request)
    return {
        "report": reports[0].model_dump(mode="json"),
        "contents": [d.content for d in result.memories],
    }


async def prepare(dataset, config):
    if (
        dataset["schema"] != RUNNER
        or len(dataset["cases"]) != 4
        or len({c["id"] for c in dataset["cases"]}) != 4
    ):
        raise ValueError("four unique frozen controls required")
    requests, order = {}, []
    for number, case in enumerate(dataset["cases"]):
        if (
            len(case["drafts"]) != 2
            or sorted(case["expected_verdicts"]) != ["contradicted", "supported"]
            or not case["rubric"].strip()
        ):
            raise ValueError(
                "each control requires supported/contradicted pair and rubric"
            )
        for profile in tuple(PROFILES) if number % 2 == 0 else tuple(PROFILES)[::-1]:
            probe = Probe()
            await apply(case, profile, probe)
            if len(probe.requests) != (1 if profile == "v1" else 2):
                raise ValueError("unexpected source-review call topology")
            key = case["id"] + ":" + profile
            requests[key] = [sha(r) for r in probe.requests]
            order.append([case["id"], profile])
    files = [
        "benchmarks/source_attribution_controls.py",
        "benchmarks/public_memory_runtime.py",
        "benchmarks/relation_planner_quality.py",
        "benchmarks/aml_evidence_representation.py",
        "benchmarks/public_memory_ingestion.py",
    ]
    files += [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "doppel_memory").rglob("*.py"))
    ]
    plan = {
        "runner": RUNNER,
        "dataset_sha256": sha(dataset),
        "provider": config.model_dump(mode="json"),
        "order": order,
        "requests": requests,
        "max_calls": 12,
        "max_request_bytes": 100000,
        "max_total_request_bytes": 1200000,
        "source_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files
        },
        "policy": "annotate; stop on invalid response; no retry/repair, withheld facts or default promotion",
        "comparison": "joint intervention: per-draft source isolation plus speaker frame; does not isolate their causal contributions",
        "publication_ready": False,
    }
    return {**plan, "fingerprint": sha(plan)}


class BoundModel:
    def __init__(self, model, expected):
        self.model, self.expected, self.index = model, expected, 0
        self.name, self.version = model.name, model.version

    async def generate(self, request):
        if (
            self.index >= len(self.expected)
            or sha(request.model_dump(mode="json")) != self.expected[self.index]
        ):
            raise ValueError("request differs from frozen preflight")
        self.index += 1
        return await self.model.generate(request)


def summarize(rows, dataset):
    cases = {c["id"]: c for c in dataset["cases"]}
    result = {}
    for profile in PROFILES:
        selected = [
            r for r in rows if r["profile"] == profile and r["status"] == "complete"
        ]
        decisions = [
            (
                d,
                cases[r["case_id"]]["expected_verdicts"][d["draft_index"]],
                r["report"]["flagged_indices"],
            )
            for r in selected
            for d in r["report"]["decisions"]
        ]
        result[profile] = {
            "controls_completed": len(selected),
            "drafts_reviewed": len(decisions),
            "verdict_matches": sum(d["verdict"] == e for d, e, _ in decisions),
            "false_flags": sum(
                e == "supported" and d["draft_index"] in flagged
                for d, e, flagged in decisions
            ),
            "missed_flags": sum(
                e == "contradicted" and d["draft_index"] not in flagged
                for d, e, flagged in decisions
            ),
            "uncertain": sum(d["verdict"] == "uncertain" for d, _, _ in decisions),
        }
    return result


async def execute(dataset, plan, model):
    cases = {c["id"]: c for c in dataset["cases"]}
    rows = []
    for identity, profile in plan["order"]:
        row = {"case_id": identity, "profile": profile, "status": "failed"}
        try:
            bound = BoundModel(model, plan["requests"][identity + ":" + profile])
            row.update(await apply(cases[identity], profile, bound))
            if bound.index != len(bound.expected):
                raise ValueError("incomplete request topology")
            row["status"] = "complete"
        except Exception as exc:  # noqa: BLE001 - preserve failed ledger/cache; never persist secret exception bodies
            row["error_type"] = type(exc).__name__
        rows.append(row)
        print(f"{identity} {profile}: {row['status']}", flush=True)
        if row["status"] != "complete":
            break
    return {
        "rows": rows,
        "status": "complete"
        if len(rows) == 8 and all(r["status"] == "complete" for r in rows)
        else "stopped",
        "summary": summarize(rows, dataset),
    }


async def run(args):
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    config = OpenAICompatibleStructuredOutputConfig(
        model="deepseek-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        max_completion_tokens=2048,
        max_tokens_parameter="max_tokens",
        thinking="disabled",
        temperature=0,
    )
    plan = await prepare(dataset, config)
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
        raise ValueError("matching frozen preflight required")
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
        max_calls=12,
        max_request_bytes=100000,
        max_total_request_bytes=1200000,
    )
    provider = None
    try:
        before = ledger.report()["attempts_reserved"]
        if before and not args.cache_only:
            raise ValueError("prior attempts retained; replay requires cache-only")
        provider = ObservedProvider(
            config, key, ledger.observe_usage, args.run_dir / "provider-receipts"
        )
        model = PilotStructuredModel(
            provider,
            ledger=ledger,
            cache_dir=args.run_dir / "cache",
            cache_only=args.cache_only,
        )
        report.update(await execute(dataset, plan, model))
        report.update(
            usage=model.report(),
            new_calls=ledger.report()["attempts_reserved"] - before,
            result_digest=sha(report["rows"]),
        )
        return report
    finally:
        if provider is not None:
            await provider.aclose()
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
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
                "summary": report.get("summary"),
                "new_calls": report.get("new_calls", 0),
            }
        )
    )
    raise SystemExit(0 if report["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

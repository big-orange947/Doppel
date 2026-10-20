"""Reuse frozen extraction; nine bounded source-review calls, no QA or graph."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from benchmarks import public_memory_structured_pair as parent
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_quantity_feedback import (
    SOURCE,
    SOURCE_SHA,
    ReceiptModel,
)
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory import ChatMessage, MemoryScope, PersonalMemoryMiner
from doppel_memory.event_time import event_time_precision_issues
from doppel_memory.intelligence import (
    PersonalMemoryAnalysis,
    PersonalMemoryAnalysisRequest,
    PersonalMemoryDraft,
    ReferencePersonalMemoryAnalyzerV11,
)
from doppel_memory.source_grounding import SourceGroundedPersonalMemoryAnalyzer
from doppel_memory.transient import TransientMemoryViewBuilder

RUNNER = "doppel.opened-source-grounding.v1"
CONTROLS = Path("benchmarks/datasets/source-grounding-controls-v1.json")


class StaticAnalyzer:
    name, version = "doppel.frozen-grounding-control-producer", "1"

    def __init__(self, values):
        self.values = values

    async def analyze(self, request):
        return PersonalMemoryAnalysis(
            memories=[
                PersonalMemoryDraft(
                    content=c["claim"], memory_type="episode", evidence_ids=[c["id"]]
                )
                for c in self.values
            ]
        )


class Probe:
    def __init__(self):
        identity = ReceiptModel("analyzer", 0)
        self.name, self.version = identity.name, identity.version
        self.request = None

    async def generate(self, request):
        self.request = request
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
                            "text": sources[d["evidence_ids"][0]][:200],
                        }
                    ],
                }
                for d in request.input["drafts"]
            ]
        }


async def apply_job(job, model):
    analyzer, request, context, reference, horizon = job
    reports = []
    wrapped = SourceGroundedPersonalMemoryAnalyzer(
        analyzer, model, observer=reports.append
    )
    if context is None:
        analysis = await wrapped.analyze(request)
        return {
            "report": reports[0].model_dump(mode="json"),
            "accepted_contents": [d.content for d in analysis.memories],
        }
    miner = PersonalMemoryMiner(
        wrapped,
        parent.miner_config(len(request.messages)).model_copy(
            update={"max_memories": 40}
        ),
    )
    proposals = await miner.propose(context)
    view = await TransientMemoryViewBuilder().build(
        request, proposals.proposals, reference_time=reference, observed_until=horizon
    )
    return {
        "report": reports[0].model_dump(mode="json"),
        "proposal_count": len(proposals.proposals),
        "checkpoint": proposals.next_checkpoint.model_dump(mode="json")
        if proposals.next_checkpoint
        else None,
        "claims": view.model_dump(mode="json")["claims"],
        "precision_issues": [
            {
                "claim_id": c.claim_id,
                "issues": list(event_time_precision_issues(c.event_time)),
            }
            for c in view.claims
            if c.event_time and event_time_precision_issues(c.event_time)
        ],
    }


async def prepare():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("parent source report changed")
    source = json.loads(SOURCE.read_bytes())
    controls = json.loads(CONTROLS.read_bytes())["controls"]
    scope = MemoryScope(user_id="synthetic-owner", agent_id="synthetic-agent")
    clock = datetime(2025, 6, 3, tzinfo=UTC)
    request = PersonalMemoryAnalysisRequest(
        scope=scope,
        messages=[
            ChatMessage(message_id=c["id"], actor="owner", text=c["source"], at=clock)
            for c in controls
        ],
    )
    jobs: list[tuple[str, tuple]] = [
        ("synthetic-controls", (StaticAnalyzer(controls), request, None, clock, clock))
    ]
    rows, _ = parent.load_rows()
    for index, (ordinal, row, scope) in enumerate(rows):
        if source["rows"][index]["case_id"] != row.case_id:
            raise ValueError("parent source order changed")
        request = PersonalMemoryAnalysisRequest(
            scope=scope, messages=list(parent.messages(row))
        )
        reference = row.runtime.query.reference_time
        horizon = max(reference, *(m.at for m in request.messages))
        jobs.append(
            (
                str(ordinal),
                (
                    ReferencePersonalMemoryAnalyzerV11(ReceiptModel("analyzer", index)),
                    request,
                    parent.batch_context(row, scope),
                    reference,
                    horizon,
                ),
            )
        )
    requests = []
    for identity, job in jobs:
        probe = Probe()
        await apply_job(job, probe)
        if probe.request is None:
            raise ValueError("empty source review request")
        requests.append(
            {
                "id": identity,
                "request": probe.request.model_dump(mode="json"),
                "request_sha256": parent._hash(probe.request.model_dump(mode="json")),
            }
        )
    paths = [
        __file__,
        str(CONTROLS),
        "doppel_memory/source_grounding.py",
        "doppel_memory/event_time.py",
        "doppel_memory/intelligence.py",
        "doppel_memory/query.py",
        "doppel_memory/transient.py",
        "doppel_memory/consolidation.py",
        "benchmarks/public_memory_quantity_feedback.py",
        "benchmarks/public_memory_structured_pair.py",
        "benchmarks/public_memory_runtime.py",
    ]
    plan = {
        "runner": RUNNER,
        "parent_sha256": SOURCE_SHA,
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths
        },
        "requests": requests,
        "config": config(8192).model_dump(mode="json"),
        "max_new_calls": 9,
        "max_request_bytes": 100000,
        "new_extraction_qa_graph_calls": 0,
        "publication_ready": False,
        "control_policy": "record semantic mismatches; invalid source binding stops; no default promotion",
    }
    return jobs, {**plan, "plan_fingerprint": parent._hash(plan)}


async def run(args):
    jobs, plan = await prepare()
    report = {"runner": RUNNER, "status": "ready", "plan": plan}
    if not args.execute:
        return report
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
    ):
        raise ValueError("matching frozen preflight required")
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "")
    if not key and not args.cache_only:
        raise ValueError("provider key absent")
    ledger = DurableCallLedger(
        args.run_dir / "usage.sqlite3",
        budget_id=plan["plan_fingerprint"],
        max_calls=9,
        max_request_bytes=100000,
        max_total_request_bytes=900000,
    )
    results = []
    try:
        if ledger.report()["attempts_reserved"] and not args.cache_only:
            raise ValueError("previous attempts retained; cache-only replay required")
        provider = parent._default_provider_factory(
            config(8192), key, ledger.observe_usage
        )
        model = PilotStructuredModel(
            provider,
            ledger=ledger,
            cache_dir=args.run_dir / "review",
            cache_only=args.cache_only,
        )
        for index, (identity, job) in enumerate(jobs):
            bound = parent.BoundModel(
                model,
                args.run_dir / "receipts" / f"{index}-review.json",
                plan["requests"][index]["request_sha256"],
            )
            result = await apply_job(job, bound)
            results.append({"id": identity, **result})
            print(
                f"review {len(results)}/9: rejected={len(result['report']['rejected_indices'])}",
                flush=True,
            )
        report.update(status="complete", rows=results)
    except Exception as exc:  # noqa: BLE001 - no provider exception text/key persistence
        report.update(status="failed", failure_class=type(exc).__name__, rows=results)
    finally:
        report["usage"] = ledger.report()
        ledger.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.execute):
        parser.error("fresh output required; cache-only requires execute")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(json.dumps({"status": report["status"]}))
    raise SystemExit(0 if report["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

"""Four opened count plans; reuse frozen extraction, test routing, no new QA."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks import public_memory_structured_pair as parent
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory import InMemoryStore, PersonalMemoryMiner
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    ReferencePersonalMemoryAnalyzerV11,
)
from doppel_memory.query import (
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryPlanV2,
    ReferencePersonalMemoryQueryPlannerV3,
)
from doppel_memory.query_feedback import CandidateAwarePersonalMemoryQuery
from doppel_memory.transient import TransientMemoryViewBuilder

SOURCE = Path("data/doppel/structured-event-time-live-v2.json")
SOURCE_SHA = "288809840186943057b82e9aa50dd31fb49719676cfb73b619afa396e7e49b6d"
RECEIPTS = Path("data/doppel/structured-event-time-v2")
RUNNER = "doppel.opened-quantity-feedback.v1"


class ReceiptModel:
    def __init__(self, stage, index):
        self.receipt = json.loads(
            (RECEIPTS / "receipts" / f"{index}-{stage}.json").read_bytes()
        )
        identities = [
            json.loads(p.read_bytes())["model"]
            for p in (RECEIPTS / stage).rglob("*.json")
        ]
        if not identities or any(x != identities[0] for x in identities):
            raise ValueError("frozen provider identity mismatch")
        self.name, self.version = identities[0]["name"], identities[0]["version"]

    async def generate(self, request):
        if self.receipt["status"] != "completed" or self.receipt[
            "request_sha256"
        ] != _hash(request.model_dump(mode="json")):
            raise ValueError("frozen source request changed")
        return self.receipt["output"]


class Probe:
    def __init__(self, model):
        self.name, self.version = model.name, model.version
        self.request = None

    async def generate(self, request):
        self.request = request
        return {"route": "uncertain", "supporting_memory_ids": [], "confidence": 1}


async def prepare():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("frozen source report changed")
    source = json.loads(SOURCE.read_bytes())
    rows, _ = parent.load_rows()
    tasks, requests = [], []
    for index, (ordinal, row, scope) in enumerate(rows):
        previous = source["rows"][index]
        if [previous["ordinal"], previous["case_id"]] != [ordinal, row.case_id]:
            raise ValueError("frozen case ordering changed")
        request = PersonalMemoryAnalysisRequest(
            scope=scope, messages=list(parent.messages(row))
        )
        miner = PersonalMemoryMiner(
            ReferencePersonalMemoryAnalyzerV11(ReceiptModel("analyzer", index)),
            parent.miner_config(len(request.messages)).model_copy(
                update={"max_memories": 40}
            ),
        )
        proposals = await miner.propose(parent.batch_context(row, scope))
        horizon = max(
            row.runtime.query.reference_time, *(m.at for m in request.messages)
        )
        view = await TransientMemoryViewBuilder().build(
            request,
            proposals.proposals,
            reference_time=row.runtime.query.reference_time,
            observed_until=horizon,
        )
        if view.model_dump(mode="json") != previous["audit"]["transient_view"]:
            raise ValueError("source-bound candidate view changed")
        store = InMemoryStore()
        for proposal, claim in zip(proposals.proposals, view.claims, strict=True):
            await store.put(
                proposal.to_record().model_copy(update={"memory_id": claim.claim_id})
            )
        engine = PersonalMemoryQueryEngine(store)
        planner_model = ReceiptModel("planner", index)
        plan = await engine.plan(
            ReferencePersonalMemoryQueryPlannerV3(planner_model),
            row.runtime.query.query,
            [scope],
            now=row.runtime.query.reference_time,
            observed_until=horizon,
        )
        if not isinstance(plan, PersonalMemoryQueryPlanV2):
            raise TypeError("frozen operation/time plan required")
        original = await engine.execute(plan, trace_limit=40)
        if original.model_dump(mode="json") != previous["audit"]["engine_result"]:
            raise ValueError("original query replay changed")
        if plan.operation != "count":
            continue  # selection by frozen operation, never by answer/old grade
        probe = Probe(planner_model)
        await CandidateAwarePersonalMemoryQuery(engine, probe).execute(
            plan, trace_limit=40
        )
        if probe.request is None:
            raise ValueError("expected eligible discovery candidates")
        requests.append(
            {
                "ordinal": ordinal,
                "case_id": row.case_id,
                "request": probe.request.model_dump(mode="json"),
                "request_sha256": _hash(probe.request.model_dump(mode="json")),
            }
        )
        tasks.append((ordinal, row.case_id, engine, plan))
    if len(tasks) != 4:
        raise ValueError("frozen four count plans required")
    paths = [
        __file__,
        "doppel_memory/query_feedback.py",
        "doppel_memory/query.py",
        "doppel_memory/event_time.py",
        "doppel_memory/intelligence.py",
        "doppel_memory/transient.py",
        "doppel_memory/consolidation.py",
        "benchmarks/public_memory_structured_pair.py",
        "benchmarks/public_memory_runtime.py",
    ]
    plan = {
        "runner": RUNNER,
        "source_sha256": SOURCE_SHA,
        "source_code_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths
        },
        "requests": requests,
        "config": config(2048).model_dump(mode="json"),
        "max_new_calls": 4,
        "max_request_bytes": 30000,
        "new_extraction_calls": 0,
        "new_qa_or_judge_calls": 0,
        "complete_history": False,
        "publication_ready": False,
    }
    return tasks, {**plan, "plan_fingerprint": _hash(plan)}


async def run(args):
    tasks, plan = await prepare()
    report = {"runner": RUNNER, "status": "ready", "plan": plan}
    if not args.execute:
        return report
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
    ):
        raise ValueError("matching frozen preflight required")
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "")
    if not args.cache_only and not key:
        raise ValueError("provider key absent")
    ledger = DurableCallLedger(
        args.run_dir / "usage.sqlite3",
        budget_id=plan["plan_fingerprint"],
        max_calls=4,
        max_request_bytes=30000,
        max_total_request_bytes=120000,
    )
    output = []
    try:
        if ledger.report()["attempts_reserved"] and not args.cache_only:
            raise ValueError("preserve previous attempts; cache-only replay required")
        provider = parent._default_provider_factory(
            config(2048), key, ledger.observe_usage
        )
        model = PilotStructuredModel(
            provider,
            ledger=ledger,
            cache_dir=args.run_dir / "feedback",
            cache_only=args.cache_only,
        )
        for index, (ordinal, case_id, engine, bound_plan) in enumerate(tasks):
            expected = plan["requests"][index]["request_sha256"]
            bound_model = parent.BoundModel(
                model, args.run_dir / "receipts" / f"{index}-feedback.json", expected
            )
            result = await CandidateAwarePersonalMemoryQuery(
                engine, bound_model
            ).execute(bound_plan, trace_limit=40)
            output.append(
                {
                    "ordinal": ordinal,
                    "case_id": case_id,
                    "feedback": result.model_dump(mode="json"),
                }
            )
            print(f"routing {len(output)}/4: applied={result.applied}", flush=True)
        report.update(status="complete", rows=output)
    except Exception as exc:  # noqa: BLE001 - retain failure class, never provider text/key
        report.update(status="failed", failure_class=type(exc).__name__, rows=output)
    finally:
        report["usage"] = ledger.report()
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
    report = asyncio.run(run(args))
    save(args.output, report)
    print(json.dumps({"status": report["status"]}))
    raise SystemExit(0 if report["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

"""Cache-derived temporal view and optional four-call Reader representation test."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from benchmarks.aml_evidence_representation import execute
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_lazy_diagnostic import (
    MAX_BYTES,
    analyzer_request,
    load_rows,
    messages,
    miner_config,
    project_proposals,
    reader_request,
    task_context,
)
from benchmarks.public_memory_pilot import _hash
from doppel_memory.intelligence import (
    PersonalMemoryAnalysisRequest,
    PersonalMemoryMiner,
    ReferencePersonalMemoryAnalyzer,
)
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputModel
from doppel_memory.transient import TransientMemoryViewBuilder

RUNNER = "doppel.public-memory-transient-view-diagnostic.v1"
ARMS = ("plain_proposals", "temporal_view")
DECODER = """

temporal_view is an optional read-only index into query_time_proposals. Its
proposal_index links to that list; source observations are not effective dates.
Unknown validity means missing bounds, not an invalid or necessarily valid fact.
Advisory merge/correct/conflict decisions have not been applied or semantically
verified. A suggested conflict means those claims need interpretation, not proof
the original sources contradict. Use the original context to interpret genuine
changes versus unresolved disputes. All proposals remain candidates and available.
Never cite transient claim IDs; cite original context memory_ids only.
"""


class ReceiptReplayModel:
    """No provider/cache mutation; only the exact bound prior analysis output."""

    name = OpenAICompatibleStructuredOutputModel.name

    def __init__(self, receipt, generation_config):
        if receipt.get("status") != "completed":
            raise ValueError("completed analysis receipt required")
        self.receipt = deepcopy(receipt)
        self.version = "1." + generation_config.generation_fingerprint[:16]

    async def generate(self, request):
        if _hash(request.model_dump(mode="json")) != self.receipt["request_sha256"]:
            raise ValueError("source-bound analysis request changed")
        return deepcopy(self.receipt["output"])


def compact_view(view):
    body = view.model_dump(mode="json")
    # Source content/claims already remain in unchanged raw/proposal fields.
    # This is only a compact temporal index, not a substitute evidence payload.
    body["claims"] = [
        {
            "claim_id": c["claim_id"],
            "proposal_index": i,
            **{
                k: c[k]
                for k in (
                    "first_observed_at",
                    "last_observed_at",
                    "observed_after_reference",
                    "validity_at_reference",
                )
            },
            "evidence": [
                {k: e[k] for k in ("evidence_id", "actor", "observed_at")}
                for e in c["evidence"]
            ],
        }
        for i, c in enumerate(body["claims"])
    ]
    return body


async def prepare(args):
    rows, bindings = load_rows(args)
    raw = args.parent.read_bytes()
    parent = json.loads(raw)
    plan = parent["plan"]
    if (
        parent.get("runner") != "doppel.public-memory-query-time-proposal-diagnostic.v1"
        or parent.get("status") != "complete"
        or plan["bindings"] != bindings
        or plan["plan_fingerprint"]
        != _hash({k: v for k, v in plan.items() if k != "plan_fingerprint"})
    ):
        raise ValueError("complete unchanged parent/source binding required")
    previous = {r["case_id"]: r for r in parent["rows"]}
    if len(previous) != len(rows) or set(previous) != {r.case_id for r in rows}:
        raise ValueError("complete unique parent cases required")
    requests, views, receipt_hashes = {}, {}, {}
    for row in rows:
        before = await analyzer_request(row)
        if (
            _hash(before.model_dump(mode="json"))
            != plan["analyzer_requests"][row.case_id]
            or _hash(reader_request(row).model_dump(mode="json"))
            != plan["baseline_reader_requests"][row.case_id]
        ):
            raise ValueError("parent source/question/generation request changed")
        path = args.parent_dir / "receipts" / (row.case_id + "-analysis.json")
        receipt_bytes = path.read_bytes()
        receipt_hashes[row.case_id] = hashlib.sha256(receipt_bytes).hexdigest()
        model = ReceiptReplayModel(json.loads(receipt_bytes), config(4096))
        generated = await PersonalMemoryMiner(
            ReferencePersonalMemoryAnalyzer(model), miner_config(len(messages(row)))
        ).propose(task_context(row))
        if generated.next_checkpoint is None:
            raise ValueError("missing replay checkpoint")
        projected = project_proposals(row, generated.proposals)
        if (
            projected != previous[row.case_id]["analysis"]["proposals"]
            or generated.next_checkpoint.model_dump(mode="json")
            != previous[row.case_id]["analysis"]["checkpoint"]
        ):
            raise ValueError("cache-derived proposals/checkpoint changed")
        context = task_context(row)
        horizon = max(row.runtime.query.reference_time, *(m.at for m in messages(row)))
        view = await TransientMemoryViewBuilder().build(
            PersonalMemoryAnalysisRequest(
                scope=context.scope, messages=list(messages(row))
            ),
            generated.proposals,
            reference_time=row.runtime.query.reference_time,
            observed_until=horizon,
        )
        views[row.case_id] = view.model_dump(mode="json")
        base = reader_request(row, projected)
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
                raise ValueError("temporal request exceeds bound; no truncation")
            requests[(row.case_id, arm)] = request
    root = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__),
        root / "benchmarks/public_memory_lazy_diagnostic.py",
        root / "benchmarks/aml_evidence_representation.py",
        root / "benchmarks/public_memory_reader_v2.py",
        root / "benchmarks/public_memory_response_policy.py",
        root / "benchmarks/public_memory_runtime.py",
        root / "benchmarks/public_memory_high_config_first.py",
        root / "doppel_memory/consolidation.py",
        root / "doppel_memory/intelligence.py",
        root / "doppel_memory/transient.py",
    ]
    order = [
        [r.case_id, a]
        for i, r in enumerate(rows)
        for a in (ARMS if i % 2 == 0 else ARMS[::-1])
    ]
    frozen = {
        "runner": RUNNER,
        "parent_sha256": hashlib.sha256(raw).hexdigest(),
        "bindings": bindings,
        "analysis_receipt_sha256": receipt_hashes,
        "execution_order": order,
        "views_sha256": {k: _hash(v) for k, v in views.items()},
        "request_sha256": {
            c + ":" + a: _hash(requests[(c, a)].model_dump(mode="json"))
            for c, a in order
        },
        "request_bytes": {
            c + ":" + a: len(requests[(c, a)].model_dump_json().encode())
            for c, a in order
        },
        "reader_config": config(1024).model_dump(mode="json"),
        "max_reader_calls": len(order),
        "max_analyzer_calls": 0,
        "max_judge_calls": 0,
        "max_request_bytes": MAX_BYTES,
        "balance_stop_cny": 1,
        "candidate_status_or_original_evidence_changed": False,
        "consolidation_applied": False,
        "causal_replay": False,
        "core_runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "source_sha256": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
        "failure_policy": "single attempt; fail-stop; retain failure; no retry/repair",
        "contrast": "same raw/proposals/schema/common decoder; added observation/validity/advisory index and input length; opened diagnosis only",
        "publication_ready": False,
    }
    frozen["plan_fingerprint"] = _hash(frozen)
    return rows, requests, views, frozen


async def run(args):
    rows, requests, views, plan = await prepare(args)
    result = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "views": views,
        "record_or_index_writes": 0,
        "new_analysis_calls": 0,
        "publication_ready": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        result.update(await execute(args, rows, requests, plan))
    result["execution_metadata"] = execution_metadata()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source",
        "oracle",
        "manifest",
        "comparison",
        "quality",
        "parent",
        "parent-dir",
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
    result = asyncio.run(run(args))
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "view_claims": sum(len(v["claims"]) for v in result["views"].values()),
            }
        )
    )
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

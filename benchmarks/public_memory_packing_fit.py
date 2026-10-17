"""Bounded skip-to-fit comparison, replaying saved top-20 rankings read-only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from benchmarks import public_memory_retrieval_packing as prefix
from benchmarks.public_memory_comparison import pack_ranked_fit
from benchmarks.public_memory_fresh_cohort import validate_fingerprint

RUNNER = "doppel.raw-packing-fit-comparison.v1"


def make_plan(parent, baseline, manifest, binding):
    validate_fingerprint(baseline["plan"], "plan_fingerprint")
    if (
        baseline["runner"] != prefix.RUNNER
        or baseline["status"] != "complete"
        or baseline["plan"]
        != prefix.build_plan(parent, manifest, baseline["plan"]["binding"])
        or len(baseline["rows"]) != 160
        or baseline["llm_calls"] != 0
        or baseline["graph_calls"] != 0
        or baseline["plan"]["binding"]
        != {k: binding[k] for k in ("dataset", "parent_manifest", "retrieval_report")}
    ):
        raise ValueError("complete unchanged prefix baseline required")
    value = {
        "runner": RUNNER,
        "binding": binding,
        "baseline_plan_fingerprint": baseline["plan"]["plan_fingerprint"],
        "schema": baseline["plan"]["schema"],
        "policies": ["unchanged-prefix", "existing-whole-item-ranked-fit"],
        "input_window": 20,
        "item_limit": 20,
        "context_byte_limit": 24000,
        "source_expansion": False,
        "new_ranking": False,
        "llm_calls": 0,
        "baseline_source_sha256": baseline["plan"]["source_sha256"],
        "comparison_wrapper_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "negative_policy": baseline["plan"]["negative_policy"],
        "publication_ready": False,
    }
    return {**value, "plan_fingerprint": prefix._hash(value)}


def compare_row(row, scoring, items, previous):
    original = prefix.audit_row(row, scoring, items)
    if original != previous:
        raise ValueError("prefix baseline not exactly reproduced")
    positions = [tuple(p) for p in row["retrieved_source_positions"]]
    ranked = [items[p] for p in positions]
    packed, trace = pack_ranked_fit(ranked)
    selected = trace["selected_rank_positions"]
    chosen = [positions[i - 1] for i in selected]
    if (
        selected != sorted(set(selected))
        or packed != [ranked[i - 1] for i in selected]
        or not set(map(tuple, original["packed_positions"])).issubset(chosen)
        or len(prefix.encoded(packed)) > 24000
    ):
        raise ValueError("fit changed order/text/budget or dropped prefix")
    fitted = {
        **original,
        "packed_count": len(packed),
        "packed_context_bytes": len(prefix.encoded(packed)),
        "packed_context_sha256": hashlib.sha256(prefix.encoded(packed)).hexdigest(),
        "packed_positions": [list(p) for p in chosen],
        "after": prefix.score_evidence(scoring, chosen),
        "first_excluded_rank": min(trace["over_budget_rank_positions"], default=None),
        "lost_labelled_positions": [
            list(p)
            for p in positions
            if p in scoring.evidence_turns and p not in chosen
        ],
        "packing_trace": trace,
    }
    return {
        "case_id": row["case_id"],
        "profile": row["profile"],
        "prefix": original,
        "ranked_fit": fitted,
    }


async def execute(cases, manifest, parent, baseline, plan):
    store = prefix.ReadOnlyStore(
        prefix.local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    old = {(r["case_id"], r["profile"]): r for r in baseline["rows"]}
    old_certs = {r["case_id"]: r for r in baseline["source_certificates"]}
    rows, certs = [], []
    try:
        for runtime, scoring in cases:
            scope = prefix.memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await prefix.inventory(store, [scope])
            digest = prefix._hash(
                {k: r.model_dump(mode="json") for k, r in records.items()}
            )
            if digest != old_certs[scoring.case_id]["after_sha256"]:
                raise ValueError("original Store snapshot changed")
            by_event = {r.source_event_id: r for r in records.values()}
            sources = {}
            for chunk in runtime.ingestion_chunks(
                max_messages=manifest["max_messages"]
            ):
                for index, (message, event, turn) in enumerate(
                    zip(
                        chunk.request.messages,
                        prefix.event_ids(scope, chunk.request),
                        chunk.source_turn_indices,
                        strict=True,
                    )
                ):
                    if (
                        event not in by_event
                        or message.timestamp is None
                        or (scope.scope_key, event) in sources
                    ):
                        raise ValueError("invalid raw source binding")
                    sources[(scope.scope_key, event)] = prefix.SourceBinding(
                        by_event[event].memory_id,
                        (chunk.source_session_index, turn),
                        message.role,
                        message.content,
                        message.timestamp,
                        chunk.request.session_id,
                        index,
                    )
            if len(sources) != len(records) or len(by_event) != len(records):
                raise ValueError("raw inventory mismatch")
            items = {
                source.position: prefix.context_item(by_event[event], records, sources)
                for (_, event), source in sources.items()
            }
            if any(item is None for item in items.values()):
                raise ValueError("unclassified source")
            rows.extend(
                compare_row(r, scoring, items, old[(r["case_id"], r["profile"])])
                for r in parent["rows"]
                if r["case_id"] == scoring.case_id
            )
            after = await prefix.inventory(store, [scope])
            if digest != prefix._hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("source changed during comparison")
            certs.append(old_certs[scoring.case_id])
    finally:
        await store.close()
    return {
        "status": "complete",
        "rows": rows,
        "source_certificates": certs,
        "summary": {
            policy: prefix.summarize([r[policy] for r in rows])
            for policy in ("prefix", "ranked_fit")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dataset",
        "parent-manifest",
        "retrieval-report",
        "prefix-report",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    content = {
        k: getattr(args, k).read_bytes()
        for k in ("dataset", "parent_manifest", "retrieval_report", "prefix_report")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    cases, manifest = prefix.prepare(
        json.loads(content["dataset"]),
        json.loads(content["parent_manifest"]),
        source_sha=binding["dataset"],
    )
    parent, baseline = (
        json.loads(content["retrieval_report"]),
        json.loads(content["prefix_report"]),
    )
    plan = make_plan(parent, baseline, manifest, binding)
    report = {
        "runner": RUNNER,
        "plan": plan,
        "status": "ready",
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
        "qa_metrics_available": False,
    }
    if args.output.exists():
        parser.error("preserve old report; fresh output required")
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        report.update(asyncio.run(execute(cases, manifest, parent, baseline, plan)))
    prefix.save(args.output, report)
    print(
        json.dumps({"status": report["status"], "summary": report.get("summary", {})})
    )


if __name__ == "__main__":
    main()

"""Read-only packing audit of fixed raw retrieval receipts; no model execution."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata, score_evidence
from benchmarks.public_memory_comparison import (
    CONTEXT_BYTE_LIMIT,
    ITEM_LIMIT,
    SourceBinding,
    context_item,
    encoded,
    inventory,
    pack_context,
)
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_retrieval_expansion import RUNNER as PARENT_RUNNER
from benchmarks.public_memory_retrieval_expansion import prepare
from integrations.aml.contract import event_ids, memory_scope

RUNNER = "doppel.raw-retrieval-packing-audit.v1"


def build_plan(parent, manifest, binding):
    validate_fingerprint(parent["plan"], "plan_fingerprint")
    expected = {
        (c["case_id"], profile)
        for c in manifest["cases"]
        for profile in parent["plan"]["profiles"]
    }
    identities = [(r["case_id"], r["profile"]) for r in parent["rows"]]
    if (
        parent["runner"] != PARENT_RUNNER
        or parent["status"] != "complete"
        or parent["plan"]["manifest"] != manifest
        or parent["llm_calls"] != 0
        or parent["provider_tokens"] != 0
        or parent["graph_calls"] != 0
        or len(manifest["cases"]) != 20
        or len(parent["plan"]["profiles"]) != 8
        or len(identities) != 160
        or set(identities) != expected
        or parent["rows"] != [r for b in parent["blocks"] for r in b["rows"]]
        or parent["plan"]["runtime_source_sha256"]
        != execution_metadata()["runtime_source_sha256"]
    ):
        raise ValueError("complete unchanged twenty-history retrieval receipt required")
    value = {
        "runner": RUNNER,
        "binding": binding,
        "parent_plan_fingerprint": parent["plan"]["plan_fingerprint"],
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "schema": parent["plan"]["schema"],
        "policy": "existing-whole-ranked-prefix-stop-at-first-overflow",
        "context_byte_limit": CONTEXT_BYTE_LIMIT,
        "item_limit": ITEM_LIMIT,
        "profiles": parent["plan"]["profiles"],
        "expected_rows": 160,
        "source_sha256": {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in {
                "wrapper": __file__,
                "packing_and_context": "benchmarks/public_memory_comparison.py",
                "readonly_store": "benchmarks/public_memory_high_config_first.py",
            }.items()
        },
        "llm_calls": 0,
        "graph_calls": 0,
        "retrieval_rerun": False,
        "negative_policy": "report-separately; exclude-predeclared-abstention-from-answer-support-recall",
        "publication_ready": False,
    }
    return {**value, "plan_fingerprint": _hash(value)}


def audit_row(row, scoring, items_by_position):
    positions = [tuple(p) for p in row["retrieved_source_positions"]]
    if (
        len(positions) != len(set(positions))
        or len(positions) != row["hits"]
        or len(positions) > ITEM_LIMIT
        or any(p not in items_by_position for p in positions)
        or score_evidence(scoring, positions) != row["at_20"]
        or score_evidence(scoring, positions[:5]) != row["at_5"]
    ):
        raise ValueError("saved ranking/source/score mismatch")
    # The packing function receives ranked source-bound items, never scoring labels.
    ranked = [items_by_position[p] for p in positions]
    packed = pack_context(ranked)
    packed_positions = positions[: len(packed)]
    if packed != ranked[: len(packed)] or len(encoded(packed)) > CONTEXT_BYTE_LIMIT:
        raise ValueError("unchanged whole-prefix packing contract violated")
    return {
        "case_id": row["case_id"],
        "profile": row["profile"],
        "abstention_label": scoring.abstention,
        "retrieved_count": len(ranked),
        "retrieved_context_bytes": len(encoded(ranked)),
        "packed_count": len(packed),
        "packed_context_bytes": len(encoded(packed)),
        "packed_context_sha256": hashlib.sha256(encoded(packed)).hexdigest(),
        "packed_positions": [list(p) for p in packed_positions],
        "first_excluded_rank": len(packed) + 1 if len(packed) < len(ranked) else None,
        "before": row["at_20"],
        "after": score_evidence(scoring, packed_positions),
        "lost_labelled_positions": [
            list(p) for p in positions[len(packed) :] if p in scoring.evidence_turns
        ],
        "text_modified": False,
    }


def summarize(rows):
    result = {}
    for profile in sorted({r["profile"] for r in rows}):
        selected = [r for r in rows if r["profile"] == profile]
        positive = [r for r in selected if not r["abstention_label"]]
        result[profile] = {
            "questions": len(selected),
            "answerable_questions": len(positive),
            "negative_questions": len(selected) - len(positive),
            "annotated_turns": sum(
                r["before"]["annotated_turn_count"] for r in positive
            ),
            "before_hits": sum(r["before"]["annotated_turn_hits"] for r in positive),
            "after_hits": sum(r["after"]["annotated_turn_hits"] for r in positive),
            "all_required_after": sum(
                r["after"]["annotated_turn_count"] > 0
                and r["after"]["annotated_turn_hits"]
                == r["after"]["annotated_turn_count"]
                for r in positive
            ),
            "overflow_rows": sum(
                r["first_excluded_rank"] is not None for r in selected
            ),
            "packed_items": sum(r["packed_count"] for r in selected),
        }
    return result


async def execute(cases, manifest, parent, plan):
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    rows, certificates = [], []
    try:
        for runtime, scoring in cases:
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            before = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            by_event = {r.source_event_id: r for r in records.values()}
            sources = {}
            for chunk in runtime.ingestion_chunks(
                max_messages=manifest["max_messages"]
            ):
                for index, (message, event, turn) in enumerate(
                    zip(
                        chunk.request.messages,
                        event_ids(scope, chunk.request),
                        chunk.source_turn_indices,
                        strict=True,
                    )
                ):
                    if event not in by_event or message.timestamp is None:
                        raise ValueError("missing raw source/timestamp")
                    key = (scope.scope_key, event)
                    if key in sources:
                        raise ValueError("duplicate source identity")
                    sources[key] = SourceBinding(
                        by_event[event].memory_id,
                        (chunk.source_session_index, turn),
                        message.role,
                        message.content,
                        message.timestamp,
                        chunk.request.session_id,
                        index,
                    )
            if len(sources) != len(records) or len(by_event) != len(records):
                raise ValueError("raw Store/source inventory differs")
            items = {
                source.position: context_item(by_event[event], records, sources)
                for (_, event), source in sources.items()
            }
            if any(item is None for item in items.values()):
                raise ValueError("unclassified raw record")
            selected = [r for r in parent["rows"] if r["case_id"] == scoring.case_id]
            rows.extend(audit_row(r, scoring, items) for r in selected)
            after_records = await inventory(store, [scope])
            after = _hash(
                {k: r.model_dump(mode="json") for k, r in after_records.items()}
            )
            if before != after:
                raise ValueError("read-only source snapshot changed")
            certificates.append(
                {
                    "case_id": scoring.case_id,
                    "records": len(records),
                    "before_sha256": before,
                    "after_sha256": after,
                }
            )
    finally:
        await store.close()
    return {
        "status": "complete",
        "rows": rows,
        "summary": summarize(rows),
        "source_certificates": certificates,
        "source_records": sum(c["records"] for c in certificates),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "parent-manifest", "retrieval-report", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    content = {
        name: getattr(args, name).read_bytes()
        for name in ("dataset", "parent_manifest", "retrieval_report")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    parent = json.loads(content["retrieval_report"])
    cases, manifest = prepare(
        json.loads(content["dataset"]),
        json.loads(content["parent_manifest"]),
        source_sha=binding["dataset"],
    )
    plan = build_plan(parent, manifest, binding)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
        "qa_metrics_available": False,
    }
    if args.output.exists():
        parser.error("preserve existing report; new output required")
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        report.update(asyncio.run(execute(cases, manifest, parent, plan)))
    save(args.output, report)
    print(
        json.dumps({"status": report["status"], "summary": report.get("summary", {})})
    )


if __name__ == "__main__":
    main()

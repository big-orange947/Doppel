"""Zero-model paired packing replay on the opened30 with saved complete ranks.

All50 get frozen stage accounting; other20 have no saved complete rerank order.
Read-only PostgreSQL supplies historical source snapshots, never new candidates.
The packer receives no questions, annotations, task labels or old answer grades.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import encoded, pack_ranked_fit
from benchmarks.public_memory_expansion import local_diagnostic_dsn
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_uniform_completion import bound_source
from doppel_memory.context_packing import pack_context_items, unpack_context

ROOT = Path("data/doppel")
FILES = {
    "summary": ROOT / "uniform-qa-fifty-summary-v1.json",
    "thirty": ROOT / "uniform-qa-11-40-prepare-live-v1.json",
    "twenty": ROOT / "uniform-qa-completion-prepare-live-v1.json",
    "manifest": ROOT / "longmemeval-fresh-high-config-50-manifest-v1.json",
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
}


def stage_totals(rows):
    result = {}
    for name in ("candidate_coverage", "retrieved_coverage", "packed_coverage"):
        evidence = [
            row[name] for row in rows if not row[name].get("abstention_label", False)
        ]
        denominator = sum(item["annotated_turn_count"] for item in evidence)
        hits = sum(item["annotated_turn_hits"] for item in evidence)
        result[name] = {
            "hits": hits,
            "annotated": denominator,
            "recall": hits / denominator if denominator else None,
        }
    return result


def compare(ranked, original, required):
    """Policies execute first; labels are used only for scoring selections."""
    baseline, _ = pack_ranked_fit(ranked)
    if baseline != original:
        raise ValueError("original exact context was not reproduced")
    selected = {"baseline": (baseline, len(encoded(baseline)))}
    for mode in ("retain", "repack"):
        packed = pack_context_items(ranked, mode=mode)
        decoded = unpack_context(packed.payload)
        selected[mode] = (decoded, packed.wire_bytes)
        if mode == "retain" and not {i["memory_id"] for i in baseline} <= {
            i["memory_id"] for i in decoded
        }:
            raise ValueError("retention mode displaced baseline evidence")
    required = set(required)
    result = {}
    for mode, (items, size) in selected.items():
        ids = [item["memory_id"] for item in items]
        result[mode] = {
            "item_count": len(items),
            "wire_bytes": size,
            "selected_ids": ids,
            "annotated_hits": len(required & set(ids)),
            "annotated_count": len(required),
            "all_annotated": required <= set(ids) if required else None,
        }
    return result


async def run(output: Path):
    if output.exists():
        raise ValueError("output exists; frozen artifacts are never overwritten")
    raw = {k: path.read_bytes() for k, path in FILES.items()}
    hashes = {k: hashlib.sha256(value).hexdigest() for k, value in raw.items()}
    data = {k: json.loads(value) for k, value in raw.items()}
    parent = data["manifest"]
    validate_fingerprint(parent, "manifest_fingerprint")
    for key in ("thirty", "twenty"):
        validate_fingerprint(data[key]["plan"], "plan_fingerprint")
        if data[key]["status"] != "complete":
            raise ValueError("complete saved preparation required")
    if hashes["dataset"] != parent["source_sha256"]:
        raise ValueError("frozen dataset changed")
    contexts = data["thirty"]["rows"] + data["twenty"]["rows"]
    summary = data["summary"]
    if {r["ordinal"] for r in contexts} != set(range(1, 51)) or len(contexts) != 50:
        raise ValueError("exact opened50 context cohort required")
    scores = {r["ordinal"]: r for r in summary["rows"]}
    if (
        summary["status"] != "complete"
        or len(summary["rows"]) != 50
        or set(scores) != set(range(1, 51))
    ):
        raise ValueError("exact complete frozen50 summary required")
    for row in contexts:
        if (
            row["case_id"] != scores[row["ordinal"]]["case_id"]
            or hashlib.sha256(encoded(row["context"])).hexdigest()
            != scores[row["ordinal"]]["context_sha256"]
        ):
            raise ValueError("context/summary binding changed")
        if row["packed_coverage"] != scores[row["ordinal"]]["packed_coverage"] or any(
            row[name]["abstention_label"] != scores[row["ordinal"]]["abstention_label"]
            for name in ("candidate_coverage", "retrieved_coverage", "packed_coverage")
        ):
            raise ValueError("scoring-only annotation/negative binding changed")
    by_id = {item["question_id"]: item for item in data["dataset"]}
    manifest = {
        item["case_id"]: item
        for item in parent["cases"]
        if item["partition"] == "diagnostic"
    }
    stores, rows = {}, []
    try:
        for row in sorted(data["thirty"]["rows"], key=lambda r: r["ordinal"]):
            meta = manifest[row["case_id"]]
            case = prepare_case(
                by_id[row["case_id"]], dataset_namespace=parent["dataset_namespace"]
            )
            chunks = case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
            if (
                _hash([chunk.request.model_dump(mode="json") for chunk in chunks])
                != meta["history_payload_sha256"]
            ):
                raise ValueError("opened history payload changed")
            group = data["thirty"]["plan"]["groups"][row["group"]]
            if row["group"] not in stores:
                stores[row["group"]] = ReadOnlyStore(
                    local_diagnostic_dsn("doppel-ablation-pgvector"),
                    schema=group["schema"],
                )
            store = stores[row["group"]]
            _, _, items = await bound_source(
                store,
                {**row, "raw_records": meta["raw_turn_count"]},
                case.runtime,
                group,
            )
            positions = [tuple(p) for p in row["positions"]]
            if len(positions) != 20 or len(set(positions)) != 20:
                raise ValueError("exact unique top20 saved order required")
            ranked = [items[p] for p in positions]
            required = (
                []
                if case.scoring.abstention
                else [items[p]["memory_id"] for p in case.scoring.evidence_turns]
            )
            policies = compare(ranked, row["context"], required)
            rows.append(
                {
                    "ordinal": row["ordinal"],
                    "case_id": row["case_id"],
                    "abstention_label": case.scoring.abstention,
                    "policies": policies,
                }
            )
        report = {
            "runner": "doppel.packing-replay.v1",
            "accounting_version": "positive-turns-only-v2",
            "status": "complete",
            "input_sha256": hashes,
            "code_sha256": {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (Path(__file__), Path("doppel_memory/context_packing.py"))
            },
            "paired_count": 30,
            "stage_accounting_count": 50,
            "paired_ordinals": list(range(11, 41)),
            "unavailable_rank_ordinals": [*range(1, 11), *range(41, 51)],
            "frozen_fifty_stages": stage_totals(contexts),
            "rows": rows,
            "summary": summarize(rows),
            "paid_calls": 0,
            "model_calls": 0,
            "retrieval_rerun": False,
            "source_writes": 0,
            "opened_development_not_blind": True,
            "qa_metrics_available": False,
            "publication_ready": False,
            "official_longmemeval_score": False,
            "aml_score": False,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode()
        )
        print(
            json.dumps(
                {
                    "paired_count": 30,
                    "summary": report["summary"],
                    "fifty_stages": report["frozen_fifty_stages"],
                },
                sort_keys=True,
            )
        )
        return report
    finally:
        for store in stores.values():
            await store.close()
        if any(
            hashlib.sha256(path.read_bytes()).hexdigest() != hashes[k]
            for k, path in FILES.items()
        ):
            raise ValueError("input artifact changed during replay")


def summarize(rows):
    result = {}
    for mode in ("baseline", "retain", "repack"):
        values = [row["policies"][mode] for row in rows]
        result[mode] = {
            "annotated_hits": sum(v["annotated_hits"] for v in values),
            "annotated_count": sum(v["annotated_count"] for v in values),
            "all_annotated_questions": sum(v["all_annotated"] is True for v in values),
            "positive_questions": sum(v["annotated_count"] > 0 for v in values),
            "items": sum(v["item_count"] for v in values),
            "bytes": sum(v["wire_bytes"] for v in values),
            "coverage_gain_questions": sum(
                row["policies"][mode]["annotated_hits"]
                > row["policies"]["baseline"]["annotated_hits"]
                for row in rows
            ),
            "coverage_loss_questions": sum(
                row["policies"][mode]["annotated_hits"]
                < row["policies"]["baseline"]["annotated_hits"]
                for row in rows
            ),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only-postgres", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output))


if __name__ == "__main__":
    main()

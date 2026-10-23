"""One fixed local rank-fusion arm versus saved80 BGE and original retrieval order.

All50 opened cases, same80 candidates/top20/24KB; no retrieval, paid API or graph.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_comparison import encoded, inventory, pack_ranked_fit
from benchmarks.public_memory_context_budget import INPUTS
from benchmarks.public_memory_expansion import local_diagnostic_dsn
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import ReadOnlyStore
from benchmarks.public_memory_packing_replay import FILES
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_prospective_selection import model_identity
from benchmarks.public_memory_uniform_completion import bound_source
from benchmarks.public_memory_uniform_qa import digest
from doppel_memory.rank_fusion import RankFusionReranker
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.neighborhood import _Ids, as_candidate

ARM_NAMES = ("retrieval_order", "cross_encoder", "rank_fusion")
SOURCE = Path("data/doppel/window-ablation-live-v1.json")
CODE = (
    __file__,
    "doppel_memory/rank_fusion.py",
    "benchmarks/public_context_rerank.py",
    "benchmarks/public_memory_comparison.py",
    "benchmarks/public_memory_uniform_completion.py",
    "benchmarks/public_memory_uniform_qa.py",
    "integrations/aml/context.py",
    "integrations/aml/neighborhood.py",
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")


def prepare(provider):
    raw = {
        **{key: path.read_bytes() for key, path in FILES.items()},
        "window": SOURCE.read_bytes(),
    }
    data = {key: json.loads(value) for key, value in raw.items()}
    binding = {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
    source = data["window"]
    if binding["window"] != INPUTS[SOURCE.name] or source["status"] != "complete":
        raise ValueError("fixed completed80/160 source report required")
    validate_fingerprint(source["plan"], "plan_fingerprint")
    if {key: binding[key] for key in FILES} != source["plan"][
        "binding"
    ] or model_identity(provider) != source["plan"]["reranker"]:
        raise ValueError(
            "same original source plans and local BGE runtime/weights required"
        )
    parent = data["manifest"]
    validate_fingerprint(parent, "manifest_fingerprint")
    groups, metadata = {}, {}
    for key in ("thirty", "twenty"):
        validate_fingerprint(data[key]["plan"], "plan_fingerprint")
        if data[key]["status"] != "complete":
            raise ValueError("complete original source preparation required")
        groups.update(data[key]["plan"]["groups"])
        metadata.update({row["ordinal"]: row for row in data[key]["rows"]})
    selected = {
        row["case_id"]: row
        for row in parent["cases"]
        if row["partition"] == "diagnostic"
    }
    rows = source["rows"]
    if (
        len(rows) != 50
        or len(metadata) != 50
        or {row["ordinal"] for row in rows} != set(range(1, 51))
        or {row["case_id"] for row in rows} != set(selected)
    ):
        raise ValueError("fixed opened50 required; reserved cases excluded")
    by_id = {row["question_id"]: row for row in data["dataset"]}
    queue = []
    for row in sorted(rows, key=lambda r: r["ordinal"]):
        meta = metadata[row["ordinal"]]
        case = prepare_case(
            by_id[row["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        if (
            meta["case_id"] != row["case_id"]
            or _hash(case.runtime.query.query) != row["query_sha256"]
        ):
            raise ValueError("fixed question/source identity differs")
        queue.append(
            (
                {**meta, "raw_records": selected[row["case_id"]]["raw_turn_count"]},
                case,
                row,
            )
        )
    plan = {
        "runner": "doppel.rank-fusion-local.v1",
        "binding": binding,
        "code_sha256": {
            str(Path(p)): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in CODE
        },
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "arms": list(ARM_NAMES),
        "rrf_k": 60,
        "weights": "equal; no sweep",
        "candidate_limit": 80,
        "source_limit": 20,
        "context_bytes": 24000,
        "model": model_identity(provider),
        "max_model_calls": 50,
        "max_pairs": 4000,
        "baseline_requirement": "fresh cross-encoder top20/context equals saved80 in all50 cases",
        "paid_calls": 0,
        "query_embeddings": 0,
        "graph_calls": 0,
        "retrieval_calls": 0,
        "source_writes": 0,
        "qa_metrics_available": False,
        "opened_development_not_blind": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}, queue, groups, raw


def score_arm(order, items, required):
    top = [items[key] for key in order[:20]]
    context, trace = pack_ranked_fit(top)
    packed_ids = {item["memory_id"] for item in context}
    return {
        "full_order": order,
        "top20": top,
        "context": context,
        "top20_annotated_ids": sorted(set(order[:20]) & required),
        "packed_annotated_ids": sorted(packed_ids & required),
        "context_sha256": hashlib.sha256(encoded(context)).hexdigest(),
        "context_bytes": len(encoded(context)),
        "packing_trace": trace,
    }


def summarize(rows):
    result = {}
    positives = [r for r in rows if not r["abstention_label"]]
    for name in ARM_NAMES:
        result[name] = {
            "cases": len(rows),
            "positives": len(positives),
            "annotations": sum(r["annotated"] for r in positives),
            "candidate_annotations": sum(r["candidate_annotations"] for r in positives),
            "top20_annotations": sum(
                len(r["arms"][name]["top20_annotated_ids"]) for r in positives
            ),
            "packed_annotations": sum(
                len(r["arms"][name]["packed_annotated_ids"]) for r in positives
            ),
            "complete_positive_questions": sum(
                len(r["arms"][name]["packed_annotated_ids"]) == r["annotated"]
                for r in positives
            ),
            "all_case_items": sum(len(r["arms"][name]["context"]) for r in rows),
            "all_case_bytes": sum(r["arms"][name]["context_bytes"] for r in rows),
        }
        paired = {}
        for stage in ("top20", "packed"):
            pairs = [
                (
                    set(r["arms"]["cross_encoder"][stage + "_annotated_ids"]),
                    set(r["arms"][name][stage + "_annotated_ids"]),
                )
                for r in positives
            ]
            paired[stage] = {
                "recovered": sum(len(b - a) for a, b in pairs),
                "displaced": sum(len(a - b) for a, b in pairs),
                "gain_questions": sum(len(b) > len(a) for a, b in pairs),
                "loss_questions": sum(len(b) < len(a) for a, b in pairs),
            }
        result[name]["paired_vs_cross_encoder"] = paired
    return result


async def execute(args, plan, queue, groups, provider):
    if args.run_dir.exists():
        raise ValueError("fresh run directory required; no silent retry")
    for key in ("DEEPSEEK_API_KEY", "DOPPEL_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(key, None)
    save(args.run_dir / "attempt.json", {"plan": plan})
    stores, rows = {}, []
    failure, current, stage = None, None, "initialize"
    delegate = StrictContextReranker(provider)
    ranker = RankFusionReranker(delegate, rrf_k=60)
    try:
        dsn = local_diagnostic_dsn("doppel-ablation-pgvector")
        for name, group in groups.items():
            stores[name] = ReadOnlyStore(dsn, schema=group["schema"])
        for meta, case, old in queue:
            current, stage = meta["ordinal"], "source-binding"
            store = stores[meta["group"]]
            scope, host, positioned = await bound_source(
                store, meta, case.runtime, groups[meta["group"]]
            )
            items = {item["memory_id"]: item for item in positioned.values()}
            ids = old["arms"]["80"]["candidate_ids"]
            if len(ids) != 80 or len(set(ids)) != 80 or not set(ids) <= set(items):
                raise ValueError("saved80 candidate identities differ")
            anchors = await AttributedContextRetriever(
                store,
                strategy=_Ids(scope, [(key, 0.0) for key in ids]),
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, case.runtime.query.query, limit=80)
            if anchors.rejected or [s.memory_id for s in anchors.snippets] != ids:
                raise ValueError("candidate source/scope/provenance check failed")
            stage = "single-local-full-order"
            fused = await ranker.rerank(
                case.runtime.query.query,
                [as_candidate(scope, s) for s in anchors.snippets],
                limit=80,
            )
            orders = {
                "retrieval_order": ids,
                "cross_encoder": list(delegate.last_order),
                "rank_fusion": [c.memory_id for c in fused],
            }
            # Final current source validation is independent of annotation scoring.
            stage = "final-source-checks"
            checked = 0
            for order in orders.values():
                selected = await AttributedContextRetriever(
                    store,
                    strategy=_Ids(scope, [(key, 0.0) for key in order[:20]]),
                    resolve_event=host.resolve_event,
                    candidate_multiplier=1,
                ).search(scope, case.runtime.query.query, limit=20)
                if (
                    selected.rejected
                    or [s.memory_id for s in selected.snippets] != order[:20]
                ):
                    raise ValueError("final source validation failed")
                checked += selected.final_store_checks
            required = (
                set()
                if case.scoring.abstention
                else {positioned[p]["memory_id"] for p in case.scoring.evidence_turns}
            )
            arms = {
                name: score_arm(order, items, required)
                for name, order in orders.items()
            }
            baseline = arms["cross_encoder"]
            if (
                baseline["top20"] != old["arms"]["80"]["top20"]
                or baseline["context"] != old["arms"]["80"]["context"]
            ):
                raise ValueError(
                    "fresh80 baseline must reproduce historical sources/order/context exactly"
                )
            stage = "final-corpus-check"
            if digest(await inventory(store, [scope])) != meta["corpus_sha256"]:
                raise ValueError("authoritative corpus changed")
            row = {
                "ordinal": current,
                "case_id": case.scoring.case_id,
                "abstention_label": case.scoring.abstention,
                "annotated": len(required),
                "candidate_annotations": len(required & set(ids)),
                "candidate_items": [items[key] for key in ids],
                "arms": arms,
                "missing_after_cross_encoder": [
                    {
                        "memory_id": key,
                        "retrieval_rank": ids.index(key) + 1,
                        "cross_encoder_rank": orders["cross_encoder"].index(key) + 1,
                        "fusion_rank": orders["rank_fusion"].index(key) + 1,
                    }
                    for key in sorted(
                        required & set(ids) - set(orders["cross_encoder"][:20])
                    )
                ],
                "corpus_sha256": meta["corpus_sha256"],
                "final_store_checks": checked,
                "baseline_reproduced": True,
                "local_summary": delegate.last_summary.model_dump(mode="json")
                if delegate.last_summary
                else None,
            }
            rows.append(row)
            save(args.run_dir / f"case-{current:02d}.json", row)
            print(f"completed {current}/50", flush=True)
    except Exception as exc:  # noqa: BLE001 - no credentials/arbitrary exception text
        failure = {"case": current, "stage": stage, "class": type(exc).__name__}
    finally:
        for store in stores.values():
            await store.close()
    return {
        "status": "complete" if failure is None else "failed",
        "rows": rows,
        "summary": summarize(rows),
        "failure": failure,
        "model_usage": provider.report(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    old = json.loads(SOURCE.read_bytes())
    provider = LocalContextCrossEncoder(
        Path(old["plan"]["reranker"]["model_path"]),
        device="cuda",
        max_length=8192,
        batch_size=1,
    )
    plan, queue, groups, raw = prepare(provider)
    result = {"plan": plan, "status": "ready"}
    if args.execute:
        if (
            not args.run_dir
            or not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching preflight and fresh run directory required")
        result.update(asyncio.run(execute(args, plan, queue, groups, provider)))
    if (
        any(
            FILES[key].read_bytes() != value
            for key, value in raw.items()
            if key != "window"
        )
        or SOURCE.read_bytes() != raw["window"]
    ):
        raise ValueError("input changed; checkpoints retained")
    save(args.output, result)
    print(
        f"output: {args.output.resolve()}\nsha256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}",
        flush=True,
    )
    if "summary" in result:
        print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

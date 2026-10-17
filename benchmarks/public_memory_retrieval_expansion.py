"""Twenty fixed unseen histories, existing raw retrieval harness, zero LLMs.

Checkpoint four five-history blocks in a new dedicated namespace. Do not mutate
the frozen source/analyzer/graph experiments or treat evidence recall as QA.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata, run_baseline
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_pilot import _hash, history_group

RUNNER = "doppel.public-memory-raw-retrieval-expansion.v1"
NAMESPACE = "longmemeval-nograph-retrieval-11-30-v1"


def prepare(raw, parent, *, source_sha):
    validate_fingerprint(parent, "manifest_fingerprint")
    if source_sha != parent["source_sha256"]:
        raise ValueError("frozen source bytes differ")
    selected = [c for c in parent["cases"] if c["partition"] == "diagnostic"]
    if len(selected) < 30:
        raise ValueError("fixed first thirty diagnostic histories required")
    by_id = {r["question_id"]: r for r in raw}
    if len(by_id) != len(raw):
        raise ValueError("duplicate source identity")
    cases, rows = [], []
    for ordinal, row in enumerate(selected[10:30], 11):
        case = prepare_case(
            by_id[row["case_id"]], dataset_namespace=parent["dataset_namespace"]
        )
        count = sum(len(s.turns) for s in case.runtime.sessions)
        chunks = list(
            case.runtime.ingestion_chunks(max_messages=parent["max_messages"])
        )
        if (
            history_group(case) != row["history_group"]
            or count != row["raw_turn_count"]
            or len(chunks) != row["chunk_count"]
            or _hash([c.request.model_dump(mode="json") for c in chunks])
            != row["history_payload_sha256"]
        ):
            raise ValueError("selected history differs from original frozen source")
        cases.append((case.runtime, case.scoring))
        rows.append(
            {
                "ordinal": ordinal,
                "case_id": row["case_id"],
                "history_group": row["history_group"],
                "raw_turn_count": count,
                "chunk_count": len(chunks),
                "sampling_stratum": row.get("sampling_stratum", "public"),
            }
        )
    child = {
        "runner": RUNNER,
        "parent_manifest_fingerprint": parent["manifest_fingerprint"],
        "source_sha256": source_sha,
        "run_namespace": NAMESPACE,
        "dataset_namespace": parent["dataset_namespace"],
        "max_messages": parent["max_messages"],
        "temporal_policy": parent["temporal_policy"],
        "cases": rows,
        "selection": "unchanged-parent-diagnostic-ordinals-11-through-30-no-outcome-selection",
    }
    child["manifest_fingerprint"] = _hash(child)
    return cases, child


def build_plan(manifest, reranker):
    plan = {
        "runner": RUNNER,
        "manifest": manifest,
        "schema": "raw_evidence_" + manifest["manifest_fingerprint"][:12],
        "blocks": [list(range(i, i + 5)) for i in (11, 16, 21, 26)],
        "profiles": [
            "raw_lexical",
            "raw_local_vector",
            "raw_lexical_vector",
            "raw_bm25",
            "raw_bm25_vector",
            "raw_local_vector_reranked",
            "raw_bm25_reranked",
            "raw_bm25_vector_reranked",
        ],
        "raw_record_cap": sum(c["raw_turn_count"] for c in manifest["cases"]),
        "reranker": {
            k: v
            for k, v in reranker.report().items()
            if k
            not in {
                "device_actual",
                "calls",
                "pairs_scored",
                "truncated_pairs",
                "longest_pair_tokens",
            }
        },
        "runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "implementation_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
        "candidate_window": 80,
        "output_limit": 20,
        "metric": "annotated-evidence-at-5-and-20-and-candidate-window; not-QA-or-packed-context",
        "embedding": "fastembed:BAAI/bge-small-zh-v1.5/0.8.0/512",
        "failure_policy": "stop; keep block receipts and dedicated raw store; no reset or auto-retry",
        "publication_ready": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


async def execute(args, cases, manifest, plan, reranker):
    if (
        not args.frozen_preflight
        or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
    ):
        raise ValueError("unchanged frozen retrieval-only plan required")
    if any(args.run_dir.glob("block-*.json")):
        raise ValueError("preserve existing blocks; no silent second live invocation")
    # No paid provider is constructed; also remove its conventional environment
    # keys from this child process to make accidental paid wiring fail closed.
    for key in ("DEEPSEEK_API_KEY", "DOPPEL_API_KEY", "OPENAI_API_KEY"):
        os.environ.pop(key, None)
    blocks = []
    for offset in range(0, 20, 5):
        result = await run_baseline(
            cases[offset : offset + 5],
            manifest,
            dsn=local_diagnostic_dsn("doppel-ablation-pgvector"),
            schema=plan["schema"],
            embedding_cache_dir=None,
            with_bm25=True,
            reranker=StrictContextReranker(reranker),
        )
        if (
            result["llm_calls"] != 0
            or result["provider_tokens"] != 0
            or set(result["profiles"]) != set(plan["profiles"])
        ):
            raise ValueError("unexpected provider or profile execution")
        save(args.run_dir / f"block-{offset // 5 + 1:02}.json", result)
        blocks.append(result)
        print(f"completed histories {offset + 5}/20", flush=True)
    return {
        "status": "complete",
        "blocks": blocks,
        "rows": [r for b in blocks for r in b["rows"]],
        "raw_records": sum(b["raw_records"] for b in blocks),
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "parent-manifest", "reranker-model", "run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous output")
    data = args.dataset.read_bytes()
    parent = json.loads(args.parent_manifest.read_bytes())
    cases, manifest = prepare(
        json.loads(data), parent, source_sha=hashlib.sha256(data).hexdigest()
    )
    reranker = LocalContextCrossEncoder(
        args.reranker_model, device="cuda", max_length=8192, batch_size=1
    )
    plan = build_plan(manifest, reranker)
    result = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "llm_calls": 0,
        "provider_tokens": 0,
        "qa_metrics_available": False,
    }
    if args.live:
        result.update(asyncio.run(execute(args, cases, manifest, plan, reranker)))
    save(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "raw_records": plan["raw_record_cap"],
                "llm_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()

"""Opened-five zero-LLM candidate audit; no answers are generated or rescored."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from benchmarks.personal_retrieval_ablation import _LocalEmbeddingProvider
from benchmarks.public_context_baseline import score_evidence
from benchmarks.public_memory_comparison import inventory
from benchmarks.public_memory_expansion import local_diagnostic_dsn, save
from benchmarks.public_memory_fresh_cohort import validate_fingerprint
from benchmarks.public_memory_high_config_first import (
    ReadOnlyStore,
    ReadOnlyVectorIndex,
)
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_prospective_selection import bind_host, prepare
from benchmarks.public_memory_source_aware_diagnostic import SavedCandidates
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import RecallResult
from doppel_memory.source_aware_rerank import source_content
from doppel_memory.source_order import ExplicitSourceOrderIndex, SourcePosition
from doppel_memory.vector import HybridRetrievalStrategy
from integrations.aml.context import AttributedContextRetriever
from integrations.aml.contract import memory_scope
from integrations.aml.neighborhood import (
    AttributedNeighborhoodExpander,
    NeighborhoodConfig,
    as_candidate,
)

RUNNER = "doppel.opened-five-neighborhood-audit.v1"
FILES = {
    "dataset": Path("data/public-benchmarks/longmemeval_s_cleaned.json"),
    "parent": Path("data/doppel/longmemeval-fresh-high-config-50-manifest-v1.json"),
    "preparation": Path("data/doppel/prospective-selection-41-45-prepare-live-v1.json"),
    "evaluation": Path("data/doppel/prospective-selection-41-45-evaluate-live-v1.json"),
}


def source_index(scope, records, items):
    # Original source position comes from the immutable runtime projection, not
    # annotations, timestamps, role assumptions or chunk-local transport indices.
    return ExplicitSourceOrderIndex(
        [
            SourcePosition(
                scope_key=scope.scope_key,
                session_id=records[item["memory_id"]].metadata["raw"]["session_id"],
                ordinal=position[1],
                memory_id=item["memory_id"],
                evidence_id=records[item["memory_id"]].source_event_id,
            )
            for position, item in items.items()
        ]
    )


def make_plan(binding, preparation):
    value = {
        "runner": RUNNER,
        "binding": binding,
        "schema": preparation["plan"]["schema"],
        "manifest": preparation["plan"]["manifest"],
        "config": NeighborhoodConfig().model_dump(mode="json"),
        "baseline": "same-size-native-production-BM25-vector-pool-per-case; same count not guaranteed same bytes",
        "base_retention": "all current original anchors preserved, unchanged payloads",
        "source_order": "explicit-host-original-session-ordinal; no chronology inference",
        "candidate_policy": "anchors first, then neighbor distance/before-after and anchor rank; no actor quotas",
        "llm_calls": 0,
        "qa_calls": 0,
        "graph_calls": 0,
        "local_query_embeddings_max": 5,
        "opened_diagnostic_not_fresh": True,
        "publication_ready": False,
        "source_sha256": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (
                __file__,
                "doppel_memory/source_order.py",
                "integrations/aml/neighborhood.py",
                "integrations/aml/context.py",
                "doppel_memory/source_aware_rerank.py",
                "benchmarks/public_memory_prospective_selection.py",
                "benchmarks/personal_retrieval_ablation.py",
            )
        },
    }
    return {**value, "plan_fingerprint": _hash(value)}


async def execute(args, cases, manifest, preparation, plan):
    save(args.run_dir / "attempt.json", {"plan": plan})
    store = ReadOnlyStore(
        local_diagnostic_dsn("doppel-ablation-pgvector"), schema=plan["schema"]
    )
    index = ReadOnlyVectorIndex(store, _LocalEmbeddingProvider(cache_dir=None))
    hybrid = HybridRetrievalStrategy(
        index,
        lexical_strategy=BM25RetrievalStrategy(),
        candidate_multiplier=1,
        fallback_to_lexical=False,
    )
    rows, current_case = [], None
    try:
        for (runtime, scoring), receipt in zip(
            cases, preparation["receipts"], strict=True
        ):
            current_case = scoring.case_id
            if receipt["case_id"] != current_case:
                raise ValueError("case/preparation ordering changed")
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await inventory(store, [scope])
            digest = _hash({k: r.model_dump(mode="json") for k, r in records.items()})
            if digest != receipt["corpus_sha256"]:
                raise ValueError("source inventory changed")
            host, items = bind_host(runtime, manifest, scope, records, store)
            positions = {
                item["memory_id"]: position for position, item in items.items()
            }
            pool = [RecallResult.model_validate(c) for c in receipt["pool"]]
            if (
                _hash([c.model_dump(mode="json") for c in pool])
                != receipt["pool_sha256"]
            ):
                raise ValueError("original candidate pool changed")
            source = AttributedContextRetriever(
                store,
                strategy=SavedCandidates(pool),
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            )
            anchors = await source.search(scope, runtime.query.query, limit=80)
            if anchors.rejected or len(anchors.snippets) != len(pool):
                raise ValueError("original candidate source validation failed")
            expanded = await AttributedNeighborhoodExpander(
                store,
                resolve_event=host.resolve_event,
                source_order=source_index(scope, records, items),
                config=NeighborhoodConfig.model_validate(plan["config"]),
            ).expand(scope, anchors.snippets)
            if expanded.snippets[: len(anchors.snippets)] != anchors.snippets:
                raise ValueError("expansion changed or removed original anchors")
            matched = await AttributedContextRetriever(
                store,
                strategy=hybrid,
                resolve_event=host.resolve_event,
                candidate_multiplier=1,
            ).search(scope, runtime.query.query, limit=len(expanded.snippets))
            if matched.rejected:
                raise ValueError("matched-size native pool failed validation")
            native_bytes = sum(
                len(source_content(as_candidate(scope, s)).encode("utf-8"))
                for s in matched.snippets
            )
            scores = {
                name: score_evidence(
                    scoring, [positions[s.memory_id] for s in snippets]
                )
                for name, snippets in (
                    ("base", anchors.snippets),
                    ("expanded", expanded.snippets),
                    ("native", matched.snippets),
                )
            }
            row = {
                "case_id": current_case,
                "eligible_answerable": not scoring.abstention
                and bool(scoring.evidence_turns),
                "base_count": len(anchors.snippets),
                "expanded_count": len(expanded.snippets),
                "native_count": len(matched.snippets),
                "base_score": scores["base"],
                "expanded_score": scores["expanded"],
                "native_score": scores["native"],
                "expanded": expanded.model_dump(mode="json"),
                "native_content_bytes": native_bytes,
                "native_exceeds_expansion_byte_cap": native_bytes
                > plan["config"]["max_content_bytes"],
                "native_same_count": len(matched.snippets) == len(expanded.snippets),
                "corpus_sha256": digest,
                "base_pool_sha256": receipt["pool_sha256"],
                "qa_metrics_available": False,
            }
            after = await inventory(store, [scope])
            if digest != _hash(
                {k: r.model_dump(mode="json") for k, r in after.items()}
            ):
                raise ValueError("Store changed during read-only audit")
            rows.append(row)
            save(args.run_dir / f"history-{receipt['ordinal']}.json", row)
            print(
                f"completed {len(rows)}/5 read-only neighborhood/native comparisons",
                flush=True,
            )
        status, failure = "complete", None
    except Exception as exc:  # noqa: BLE001 - redact credentials/provider text
        status, failure = "failed", type(exc).__name__
    finally:
        await store.close()
    positive = [r for r in rows if r["eligible_answerable"]]
    return {
        "status": status,
        "failure_class": failure,
        "stopped_case": current_case if failure else None,
        "rows": rows,
        "summary": {
            "completed_cases": len(rows),
            "positive_cases": len(positive),
            "required_turns": sum(
                r["base_score"]["annotated_turn_count"] for r in positive
            ),
            **{
                profile + "_hits": sum(
                    r[profile + "_score"]["annotated_turn_hits"] for r in positive
                )
                for profile in ("base", "expanded", "native")
            },
        },
        "llm_calls": 0,
        "provider_tokens": 0,
        "graph_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("fresh output required")
    content = {k: p.read_bytes() for k, p in FILES.items()}
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in content.items()}
    data = {k: json.loads(v) for k, v in content.items()}
    cases, manifest = prepare(data["dataset"], data["parent"], binding["dataset"])
    for name in ("preparation", "evaluation"):
        validate_fingerprint(data[name]["plan"], "plan_fingerprint")
        if data[name]["status"] != "complete":
            parser.error("completed original preparation/evaluation required")
    if data["preparation"]["plan"]["manifest"] != manifest or data["evaluation"][
        "plan"
    ]["preparation_sha256"] != _hash(data["preparation"]):
        parser.error("original source/evaluation binding changed")
    plan = make_plan(binding, data["preparation"])
    result = {"runner": RUNNER, "status": "ready", "plan": plan}
    if args.execute:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            parser.error("matching frozen preflight required")
        result.update(
            asyncio.run(execute(args, cases, manifest, data["preparation"], plan))
        )
    save(args.output, result)
    print(
        json.dumps({"status": result["status"], "summary": result.get("summary", {})})
    )
    raise SystemExit(0 if result["status"] in {"ready", "complete"} else 1)


if __name__ == "__main__":
    main()

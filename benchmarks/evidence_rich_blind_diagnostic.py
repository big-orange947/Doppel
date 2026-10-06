"""User-approved diagnostic subset, NOT acceptance of the rejected blind corpus.

Selection is fixed before scores. Background records and retained gold are intact.
The official compile/review gate is intentionally not used or weakened here.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from benchmarks.evidence_rich_blind_authoring import BlindCorpusAuthoringManifest
from benchmarks.evidence_rich_blind_compile import (
    _validate_authored,
    _validate_novel_surfaces,
    compile_corpus,
)
from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousRetrievalDataset,
    load_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/doppel"
PREFIX = "evidence-rich-curated-diagnostic-v1"
CORPUS = DATA / f"{PREFIX}-corpus.json"
SELECTION = DATA / f"{PREFIX}-selection-v2.json"
PREVIOUS_SELECTION = DATA / f"{PREFIX}-selection.json"
PREVIOUS_SELECTION_SHA = (
    "d9ebc46634047ef4023c90f04dd3440a07e10003dbab5098433e34facc07f62a"
)
OUTPUT = DATA / f"{PREFIX}-live.json"
SOURCES = {
    "manifest": (
        DATA / "evidence-rich-blind-v1-bounded-revised-final-manifest.json",
        "893eab19077b76412796aa829359c566812bfb1c472abb2cfb2f85ed7d69b32a",
    ),
    "surfaces": (
        DATA / "evidence-rich-blind-v1-bounded-revised-final-surfaces.json",
        "591275a89778efe6ca5dabfe0ff43b090632a656e25a905f6a4b5d5ce3c4ebc9",
    ),
    "diff": (
        DATA / "evidence-rich-blind-v1-bounded-revised-final-diff.json",
        "90c5a48a41b5584f60816b3f11a57e48fe2e58f4d77fe1d65d51a1fb53f048bf",
    ),
}
KNOWN_ISSUES = {
    "case-blind-04-08": "full_label_number_missing",
    **{
        f"case-blind-{n:02d}-07": "only_account_prefix_present" for n in (6, 16, 22, 24)
    },
    **{
        f"case-blind-{n:02d}-06": "first_hop_already_given_in_question"
        for n in (14, 16, 22)
    },
}
EXCLUSIONS = {
    **KNOWN_ISSUES,
    **{
        f"case-blind-{n:02d}-04": "count_completeness_audit_pending"
        for n in range(1, 25)
    },
}
COMPARISON = {
    "v7": "assembled_semantic_path_exploration_hybrid_memory_reranking",
    "v8": "assembled_semantic_path_family_exploration_hybrid_memory_reranking",
}
CONFIG = {
    "embedding_model": "BAAI/bge-small-zh-v1.5",
    "embedding_dimensions": 512,
    "embedding_batch_size": 32,
    "reranker_model": "D:/project/.doppel-eval-models/bge-reranker-v2-m3",
    "reranker_batch_size": 16,
    "reranker_device": "cuda",
    "reranker_normalization": "sigmoid",
    "rerank_window": 64,
    "planner": "oracle intent/time/subject/entity anchor; not end-to-end LLM planning",
}
CODE_PATHS = (
    Path(__file__).resolve(),
    ROOT / "benchmarks/heterogeneous_retrieval_live.py",
    ROOT / "benchmarks/personal_retrieval_ablation.py",
    ROOT / "benchmarks/evidence_rich_blind_compile.py",
    *sorted((ROOT / "doppel_memory").glob("*.py")),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in CODE_PATHS}


def write_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def build_subset(
    parent: HeterogeneousRetrievalDataset,
) -> HeterogeneousRetrievalDataset:
    cases = {q.case_id: q for q in parent.queries}
    if len(parent.queries) != 240 or len(parent.scopes) != 24:
        raise ValueError("diagnostic selection requires the fixed 24-owner parent")
    if not set(EXCLUSIONS).issubset(cases):
        raise ValueError("excluded query missing from parent")
    if {q.case_id for q in parent.queries if q.intent == "count"} != {
        k for k, v in EXCLUSIONS.items() if v == "count_completeness_audit_pending"
    }:
        raise ValueError("count population changed")
    queries = [q for q in parent.queries if q.case_id not in EXCLUSIONS]
    payload = parent.model_dump(mode="json")
    payload.update(
        suite="doppel-evidence-rich-curated-diagnostic-zh-v1",
        version="1.0.0",
        description=(
            "Assistant-curated, user-approved diagnostic subset. Original full corpus "
            "has NOT passed independent semantic review. All background retained; "
            "oracle planning. Not formal blind evidence or release acceptance."
        ),
        queries=[q.model_dump(mode="json") for q in queries],
    )
    # Separate subset requirements, not a relaxation of the formal compile gate.
    minimums = dict(parent.requirements)
    minimums["min_queries"] = len(queries)
    minimums["min_queries_per_scope"] = min(Counter(q.scope for q in queries).values())
    for field in ("category", "domain", "partition"):
        counts = Counter(getattr(q, field) for q in queries)
        for key in list(minimums):
            if key.startswith(f"min_{field}_"):
                minimums[key] = counts[key.removeprefix(f"min_{field}_")]
    payload["requirements"] = minimums
    subset = HeterogeneousRetrievalDataset.model_validate(payload)
    for field in ("memories", "entities", "edges", "scopes", "relation_types"):
        if getattr(parent, field) != getattr(subset, field):
            raise ValueError("background changed during diagnostic selection")
    if len(subset.queries) != 208 or any(cases[q.case_id] != q for q in subset.queries):
        raise ValueError("diagnostic query/gold changed")
    return subset


def prepare() -> None:
    if SELECTION.exists():
        raise FileExistsError("diagnostic selection already exists")
    for path, expected in SOURCES.values():
        if sha(path) != expected:
            raise ValueError("diagnostic source hash mismatch")
    manifest = BlindCorpusAuthoringManifest.model_validate_json(
        SOURCES["manifest"][0].read_text("utf-8")
    )
    authored = json.loads(SOURCES["surfaces"][0].read_text("utf-8"))
    _validate_authored(manifest, authored)
    parent = compile_corpus(manifest, authored)
    _validate_novel_surfaces(parent)
    subset = build_subset(parent)
    if CORPUS.exists():
        # Explicit harness-only amendment. Never rewrite the original corpus or
        # selection. The interrupted attempt exposed no complete quality result.
        if sha(PREVIOUS_SELECTION) != PREVIOUS_SELECTION_SHA:
            raise ValueError("previous preregistration changed")
        previous = json.loads(PREVIOUS_SELECTION.read_text("utf-8"))
        if (
            sha(CORPUS) != previous["corpus_sha256"]
            or load_dataset(CORPUS).fingerprint != subset.fingerprint
            or previous["selected_case_ids"] != [q.case_id for q in subset.queries]
            or previous["excluded_case_ids_with_reasons"] != EXCLUSIONS
            or previous["runtime_config"] != CONFIG
        ):
            raise ValueError("harness amendment cannot change the selection")
    else:
        write_new(CORPUS, subset.model_dump(mode="json"))
    write_new(
        SELECTION,
        {
            "runner": "doppel.curated-diagnostic-selection.v1",
            "status": "harness_amended_before_complete_scores",
            "selection_method": "fixed semantic audit exclusions, no retrieval scores",
            "source_hashes": {k: digest for k, (_, digest) in SOURCES.items()},
            "implementation_hashes": code_hashes(),
            "parent_fingerprint": parent.fingerprint,
            "corpus_sha256": sha(CORPUS),
            "corpus_fingerprint": subset.fingerprint,
            "selected_case_ids": [q.case_id for q in subset.queries],
            "excluded_case_ids_with_reasons": EXCLUSIONS,
            "sizes": {
                "owners": 24,
                "parent_queries": 240,
                "selected_queries": 208,
                "memories": len(subset.memories),
                "entities": len(subset.entities),
                "edges": len(subset.edges),
            },
            "comparison_profiles": COMPARISON,
            "runtime_config": CONFIG,
            "count_quality": "not_measured: entire count population pending audit",
            "full_corpus_review_accepted": False,
            "publication_ready": False,
            "provider_calls": 0,
            "harness_amendment": {
                "previous_selection_sha256": PREVIOUS_SELECTION_SHA,
                "interrupted_attempt": "RelationPathCandidateOntologyError",
                "complete_quality_result_available": False,
                "change": "oracle control uses declared dataset ontology instead of two hardcoded types",
                "corpus_and_membership_unchanged": True,
            },
        },
    )
    print(
        json.dumps(
            {
                "corpus": str(CORPUS),
                "selection_sha256": sha(SELECTION),
                "queries": 208,
                "publication_ready": False,
            }
        )
    )


def validate_frozen(
    selection: dict[str, Any], dataset: HeterogeneousRetrievalDataset
) -> None:
    if (
        selection["corpus_sha256"] != sha(CORPUS)
        or selection["corpus_fingerprint"] != dataset.fingerprint
        or selection["selected_case_ids"] != [q.case_id for q in dataset.queries]
        or selection["excluded_case_ids_with_reasons"] != EXCLUSIONS
        or selection["comparison_profiles"] != COMPARISON
        or selection["runtime_config"] != CONFIG
        or selection["implementation_hashes"] != code_hashes()
        or selection["source_hashes"] != {k: d for k, (_, d) in SOURCES.items()}
        or selection["full_corpus_review_accepted"] is not False
        or selection["publication_ready"] is not False
    ):
        raise ValueError("frozen diagnostic selection/code/config changed")


def inspect_backend(name: str, port: str) -> tuple[dict[str, Any], dict[str, str]]:
    # Never print/persist raw inspect output, environment or credentials.
    result = subprocess.run(
        ["docker", "inspect", name], capture_output=True, timeout=15, check=True
    )
    item = json.loads(result.stdout)[0]
    state = item["State"]
    if item["Name"] != f"/{name}" or not state["Running"]:
        raise RuntimeError("expected benchmark backend not running")
    if state.get("Health", {}).get("Status") != "healthy":
        raise RuntimeError("benchmark backend not healthy")
    bindings = item["NetworkSettings"]["Ports"].get(f"{port}/tcp") or []
    if not any(
        b["HostPort"] == port and b["HostIp"] in ("0.0.0.0", "127.0.0.1")
        for b in bindings
    ):
        raise RuntimeError("backend does not own the expected local endpoint")
    env = dict(s.split("=", 1) for s in item["Config"]["Env"] if "=" in s)
    return {
        "name": name,
        "container_id": item["Id"],
        "healthy": True,
        "port": port,
        "image": item["Config"]["Image"],
    }, env


def local_credentials() -> tuple[str, str, dict[str, Any]]:
    pg, pg_env = inspect_backend("doppel-ablation-pgvector", "5432")
    neo, neo_env = inspect_backend("memo-echo-neo4j", "7687")
    if (
        pg_env.get("POSTGRES_DB") != "doppel_ablation"
        or pg_env.get("POSTGRES_USER") != "postgres"
    ):
        raise RuntimeError("refusing to reset a non-benchmark PostgreSQL database")
    auth = neo_env.get("NEO4J_AUTH", "")
    if not auth.startswith("neo4j/") or not pg_env.get("POSTGRES_PASSWORD"):
        raise RuntimeError("local backend credentials unavailable")
    return (
        pg_env["POSTGRES_PASSWORD"],
        auth.split("/", 1)[1],
        {"postgres": pg, "neo4j": neo},
    )


def diagnostic_report(raw: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    profiles = {label: raw["profiles"][name] for label, name in COMPARISON.items()}
    checks: dict[str, bool] = {}
    for label, metrics in profiles.items():
        checks[f"{label}_coverage"] = metrics["queries"] == 208
        for field in (
            "scope_leakage",
            "subject_violations",
            "ineligible_hits",
            "temporal_violations",
            "orphan_provenance",
            "hard_forbidden_hits",
        ):
            checks[f"{label}_{field}"] = metrics[field] == 0
        checks[f"{label}_candidate_bound"] = metrics["max_candidates"] <= 20
        assembly = raw[
            f"semantic_path{'_family' if label == 'v8' else ''}_reranking_assembly"
        ]
        from benchmarks.combined_retrieval_live import _store_revalidation_failures

        checks[f"{label}_store_revalidation"] = (
            _store_revalidation_failures(Counter(assembly)) == 0
        )
        checks[f"{label}_path_budget"] = assembly.get("omitted_path_hits", 0) == 0
    for field in (
        "reorder_membership_violations",
        "path_rerank_membership_violations",
        "path_family_membership_violations",
    ):
        checks[field] = raw[field] == 0
    for field in ("rerank_statuses", "path_rerank_statuses"):
        checks[field] = sum(raw[field].values()) == 208 and set(raw[field]) <= {
            "completed",
            "not_run",
        }
    checks["cleanup"] = (
        raw["runtime"]["neo4j_cleanup_performed"]
        and raw["runtime"]["postgres_cleanup_performed"]
    )
    return {
        "runner": "doppel.curated-diagnostic-live.v1",
        "status": "diagnostic_complete",
        "interpretation": "assistant-curated diagnostic; oracle planner; NOT formal blind or release acceptance",
        "selection_sha256": sha(SELECTION),
        "selection": selection,
        "profiles": profiles,
        "delta_v8_minus_v7": {
            field: round(profiles["v8"][field] - profiles["v7"][field], 6)
            for field in (
                "evidence_recall_at_5",
                "evidence_recall_at_10",
                "complete_evidence_rate_at_10",
                "related_evidence_recall_at_10",
                "mrr",
            )
        },
        "count_quality": {
            "status": "not_measured",
            "query_count": 0,
            "exact_count_rate": None,
        },
        "diagnostic_safety_gate": {"ok": all(checks.values()), "checks": checks},
        "full_corpus_review_accepted": False,
        "publication_ready": False,
        "runtime": raw["runtime"],
        "raw_all_profile_result": raw,
        "legacy_v9_gate_is_not_diagnostic_acceptance": True,
    }


async def run() -> int:
    if OUTPUT.exists():
        raise FileExistsError("diagnostic first-run output already exists")
    selection = json.loads(SELECTION.read_text("utf-8"))
    dataset = load_dataset(CORPUS)
    validate_frozen(selection, dataset)
    # Cached local weights only; no DeepSeek or other paid provider path.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from benchmarks import heterogeneous_retrieval_live as live

    pg_password, neo_password, preflight = local_credentials()
    embedding = live._LocalEmbeddingProvider(
        CONFIG["embedding_model"], dimensions=512, batch_size=32
    )
    reranker = live._SentenceTransformersRelationReranker(
        CONFIG["reranker_model"],
        score_normalization="sigmoid",
        batch_size=16,
        device="cuda",
    )
    await embedding.warmup()
    await reranker.warmup()
    print(
        "backend/model preflight complete; 208 queries, all background retained",
        flush=True,
    )
    raw = await live.run_live(
        dataset,
        dataset.queries,
        neo4j_uri="bolt://127.0.0.1:7687",
        neo4j_user="neo4j",
        neo4j_password=neo_password,
        postgres_password=pg_password,
        embedding_provider=embedding,
        memory_reranker=live._PersonalMemoryRerankerAdapter(reranker),
        relation_path_reranker=reranker,
        rerank_window=64,
    )
    report = diagnostic_report(raw, selection)
    report["backend_preflight"] = preflight
    report["reproducibility"] = live._git_metadata(dataset.fingerprint)
    write_new(OUTPUT, report)
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "sha256": sha(OUTPUT),
                "safety_gate": report["diagnostic_safety_gate"]["ok"],
                "delta": report["delta_v8_minus_v7"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0 if report["diagnostic_safety_gate"]["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
        return 0
    try:
        return asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        # Exception strings can contain passwords/URLs. Print class only, no traceback.
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "quality_metrics_available": False,
                    "publication_ready": False,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Freeze a prospective high-config cohort without models, DB writes or gold access.

This prepares selection/config/ingestion bindings, NOT a completed graph or QA run.
Actual source/graph inventories and per-stage request budgets must bind before live.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_expansion import (
    PRIMARY_INSTRUCTIONS,
    PRIMARY_SCHEMA,
    config,
    save,
)
from benchmarks.public_memory_high_config_first import STAGES
from benchmarks.public_memory_ingestion import build_ingestion_plan
from benchmarks.public_memory_pilot import _hash, build_manifest, history_group
from benchmarks.public_memory_reader_v2 import INSTRUCTIONS as READER_INSTRUCTIONS
from benchmarks.public_memory_reader_v2 import SCHEMA as READER_SCHEMA
from benchmarks.public_memory_task_accuracy import INSTRUCTIONS as TASK_INSTRUCTIONS
from doppel_memory.personal_rerank import PersonalMemoryRerankConfig
from doppel_memory.query import PersonalMemoryQueryConfig
from doppel_memory.query_path import ReferencePersonalMemoryRelationPathPlannerV7
from doppel_memory.relation_path_retrieval import EvidenceRichHybridRetrievalConfig

RUNNER = "doppel.public-memory-fresh-high-config-cohort.v1"
NAMESPACE = "longmemeval-s-cleaned-local-v1"


def sampling_projection(raw):
    """Public category/ID + whole history only; never copy questions/gold/labels."""
    return {
        "question_id": raw["question_id"],
        "question_type": "public-no-answer-id"
        if raw["question_id"].endswith("_abs")
        else raw["question_type"],
        "question": "Withheld until frozen query execution",
        "question_date": raw["question_date"],
        "answer": "Withheld",
        "answer_session_ids": [],
        "haystack_dates": raw["haystack_dates"],
        "haystack_session_ids": raw["haystack_session_ids"],
        "haystack_sessions": [
            [{"role": t["role"], "content": t["content"]} for t in session]
            for session in raw["haystack_sessions"]
        ],
    }


def validate_fingerprint(value, field):
    payload = dict(value)
    if payload.pop(field, None) != _hash(payload):
        raise ValueError("prior selection/observation binding is invalid")


def prepare(
    records, *, source_sha, priors, observed, seed=20261013, count=50, reserved=10
):
    projected = [sampling_projection(raw) for raw in records]
    by_id = {r["question_id"]: r for r in projected}
    if len(by_id) != len(projected):
        raise ValueError("duplicate source case identity")
    excluded, observed_ids = set(), set()
    for prior in priors:
        validate_fingerprint(prior, "manifest_fingerprint")
        if prior["source_sha256"] != source_sha:
            raise ValueError("prior manifest belongs to another source")
        excluded.update(c["history_group"] for c in prior["cases"])
    for observation in observed:
        validate_fingerprint(observation["plan"], "plan_fingerprint")
        if observation["plan"]["binding"]["source"] != source_sha:
            raise ValueError("opened observation belongs to another source")
        observed_ids.update(r["case_id"] for r in observation["rows"])
    if not observed_ids <= set(by_id):
        raise ValueError("opened case ID missing from pinned source")
    for identity in observed_ids:
        excluded.add(
            history_group(prepare_case(by_id[identity], dataset_namespace=NAMESPACE))
        )
    manifest = build_manifest(
        projected,
        dataset_namespace=NAMESPACE,
        run_namespace=f"longmemeval-fresh-high-config-{seed}-v1",
        source_sha256=source_sha,
        seed=seed,
        diagnostic_count=count,
        reserved_count=reserved,
        max_messages=20,
        excluded_history_groups=sorted(excluded),
        stratify_by_question_type=True,
    )
    # Retain pilot-compatible partitions and transport shape, explicitly bind
    # the new sampling projection. The legacy selector must not consume this.
    manifest.pop("manifest_fingerprint")
    manifest.update(
        runner=RUNNER,
        sampling_projection="public-type-and-public-abs-id/no-question-gold-or-turn-labels.v1",
        prior_manifest_fingerprints=[p["manifest_fingerprint"] for p in priors],
        opened_observation_fingerprints=[
            p["plan"]["plan_fingerprint"] for p in observed
        ],
        prospective_evaluation=True,
        independently_blind=False,
        opened_case_ids_excluded=sorted(observed_ids),
    )
    manifest["manifest_fingerprint"] = _hash(manifest)
    selected = [c for c in manifest["cases"] if c["partition"] == "diagnostic"]
    runtime = [
        prepare_case(by_id[c["case_id"]], dataset_namespace=NAMESPACE).runtime
        for c in selected
    ]
    chunks = sum(c["chunk_count"] for c in selected)
    ingestion = build_ingestion_plan(
        runtime,
        manifest,
        config(8192),
        max_calls=chunks,
        evidence_error_policy="quarantine",
    )
    return manifest, ingestion


def build_plan(manifest, ingestion, *, input_bindings):
    count = manifest["diagnostic_count"]
    stages = {
        s: {"calls_per_question": n, "provider": config(tokens).model_dump(mode="json")}
        for s, (n, tokens) in STAGES.items()
    }
    query_limits = {
        "full_high_config": {s: n * count for s, (n, _tokens) in STAGES.items()},
        "raw_vector_reranked": {
            s: count for s in ("reader", "task_judge", "citation_judge")
        },
    }
    root = Path(__file__).resolve().parents[1]
    files = [
        Path(__file__),
        *root.joinpath("benchmarks").glob("public_memory_*.py"),
        *root.joinpath("benchmarks").glob("graphiti_*.py"),
        root / "benchmarks/high_config_execution_contract.py",
        root / "benchmarks/public_context_rerank.py",
    ]
    plan = {
        "runner": RUNNER,
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "input_bindings": input_bindings,
        "ingestion_plan": ingestion,
        "profiles": ["full_high_config", "raw_vector_reranked"],
        "planner": {
            "name": ReferencePersonalMemoryRelationPathPlannerV7.name,
            "version": ReferencePersonalMemoryRelationPathPlannerV7.version,
            "two_passes": True,
            "oracle_plan": False,
        },
        "query_config": PersonalMemoryQueryConfig(
            limit=100,
            candidate_fusion="union",
            semantic_fallback_to_lexical=False,
            relation_fallback_to_nonrelation=False,
        ).model_dump(mode="json"),
        "memory_rerank": PersonalMemoryRerankConfig(
            max_candidates=100, timeout_seconds=120
        ).model_dump(mode="json"),
        "hybrid_config": EvidenceRichHybridRetrievalConfig().model_dump(mode="json"),
        "reranker": {
            "model": "bge-reranker-v2-m3",
            "device": "cuda",
            "max_length": 8192,
            "batch_size": 1,
            "artifact_binding_required_before_live": True,
        },
        "raw_candidate_limit": 80,
        "raw_output_limit": 20,
        "source_limit": 80,
        "context": {
            "max_items": 20,
            "max_utf8_bytes": 24000,
            "full_policy": "whole-item-memory-raw-backing-round-robin-v1",
            "raw_policy": "whole-item-reranked-source-prefix",
            "text_truncation": False,
        },
        "clock_policy": "provided-history-v1",
        "reference_time": "original S question_date",
        "timezone_assumption": "source naive calendar treated as UTC; not verified geographic timezone",
        "model_alias_pinned": False,
        "stage_configs": stages,
        "reader_instructions_sha256": hashlib.sha256(
            READER_INSTRUCTIONS.encode()
        ).hexdigest(),
        "reader_schema_sha256": _hash(READER_SCHEMA),
        "task_instructions_sha256": hashlib.sha256(
            TASK_INSTRUCTIONS.encode()
        ).hexdigest(),
        "citation_instructions_sha256": hashlib.sha256(
            PRIMARY_INSTRUCTIONS.encode()
        ).hexdigest(),
        "citation_schema_sha256": _hash(PRIMARY_SCHEMA),
        "query_call_limits": query_limits,
        "max_query_calls": sum(sum(s.values()) for s in query_limits.values()),
        "ingestion_call_limit": ingestion["total_chunks"],
        "graph_and_schema_call_limits": None,
        "graph_write_gate": "bind all eligible scope targets/actual relation-type inventory, exact request/call ceilings before paid authoring",
        "resource_gate": "named local backends/CUDA/models/source hashes verified; no silent degraded full-profile result",
        "live_execution_authorized_by_this_preflight": False,
        "evaluation_denominator": count,
        "failure_policy": "retain every failure, no automatic retry/repair/drop, no outcome-based revision",
        "execution_order": "frozen case order, alternate profile order; report each ten-case block with same snapshot",
        "metrics": [
            "answer_accuracy",
            "per_public_type_accuracy",
            "no_answer_accuracy",
            "annotated_evidence_coverage",
            "citation_legality",
            "provisional_citation_support",
            "scope_provenance_time_violations",
            "graph_participation",
            "stage_calls_tokens",
            "failures_and_missing_usage",
        ],
        "accuracy_denominators": "fixed selected cases incl failures; completed/scored rates reported separately",
        "judge": "DeepSeek reference-only task accuracy; same-model provisional, not official GPT-4o scorer",
        "publication_ready": False,
        "full_500_score": False,
        "aml_score": False,
        "dataset_population_representative": False,
        "no_post_score_algorithm_or_prompt_change": True,
        "baseline_and_full_share_reader_judges_context_caps": True,
        "runtime": execution_metadata(),
        "source_sha256": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in files
        },
    }
    # Git commit/dirty paths are provenance, not the request/config identity.
    identity = {k: v for k, v in plan.items() if k != "runtime"}
    identity["runtime_source_sha256"] = plan["runtime"]["runtime_source_sha256"]
    plan["plan_fingerprint"] = _hash(identity)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", required=True)
    parser.add_argument("--opened-observation", type=Path, action="append", default=[])
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
    args = parser.parse_args()
    if (
        args.manifest_output.exists()
        or args.plan_output.exists()
        or args.manifest_output.resolve() == args.plan_output.resolve()
    ):
        parser.error("preserve distinct prior outputs")
    source = args.dataset.read_bytes()
    raw_priors = [p.read_bytes() for p in args.prior_manifest]
    raw_observed = [p.read_bytes() for p in args.opened_observation]
    manifest, ingestion = prepare(
        json.loads(source),
        source_sha=hashlib.sha256(source).hexdigest(),
        priors=[json.loads(p) for p in raw_priors],
        observed=[json.loads(p) for p in raw_observed],
    )
    bindings = {
        "dataset": hashlib.sha256(source).hexdigest(),
        "prior_manifests": [hashlib.sha256(p).hexdigest() for p in raw_priors],
        "opened_observations": [hashlib.sha256(p).hexdigest() for p in raw_observed],
    }
    plan = build_plan(manifest, ingestion, input_bindings=bindings)
    save(args.manifest_output, manifest)
    save(args.plan_output, plan)
    print(
        json.dumps(
            {
                "selected": manifest["diagnostic_count"],
                "reserved": manifest["reserved_count"],
                "excluded_groups": len(manifest["excluded_history_groups"]),
                "strata": dict(
                    Counter(
                        c["sampling_stratum"]
                        for c in manifest["cases"]
                        if c["partition"] == "diagnostic"
                    )
                ),
                "ingestion_chunks": ingestion["total_chunks"],
                "raw_messages": ingestion["total_messages"],
                "plan_fingerprint": plan["plan_fingerprint"],
                "provider_calls": 0,
                "qa_started": False,
                "readiness": "selection-frozen/materialization-and-graph-budgets-required",
            }
        )
    )


if __name__ == "__main__":
    main()

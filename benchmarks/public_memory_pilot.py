"""Preregister complete public histories without running models or seeing scores."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.public_longmemeval import LOCAL_EMBEDDING, PreparedCase, prepare_case
from integrations.aml.contract import event_ids, memory_scope

TEMPORAL_POLICY = (
    "full-supplied-haystack/question-date-calendar-reference-not-arrival-cutoff"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def history_group(case: PreparedCase) -> str:
    """Exact ordered history equivalence, excluding query, labels and opaque IDs.

    This does not prove independence between histories sharing some filler turns.
    The manifest separately reports repeated-session content overlap.
    """
    return _hash(
        [
            [(turn.role, turn.content, turn.at.isoformat()) for turn in session.turns]
            for session in case.runtime.sessions
        ]
    )


def build_manifest(
    records: Sequence[Mapping[str, Any]],
    *,
    dataset_namespace: str,
    run_namespace: str,
    source_sha256: str,
    seed: int = 20261007,
    diagnostic_count: int = 3,
    reserved_count: int = 3,
    max_messages: int = 20,
    excluded_history_groups: Sequence[str] = (),
    stratify_by_question_type: bool = False,
) -> dict[str, Any]:
    """Default selection is label-free; optional strata use public type, never gold."""
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(stratify_by_question_type) is not bool:
        raise ValueError("stratification must be boolean")
    excluded = sorted(set(excluded_history_groups))
    if any(
        not isinstance(group, str)
        or len(group) != 64
        or any(c not in "0123456789abcdef" for c in group)
        for group in excluded
    ):
        raise ValueError("excluded histories must be SHA-256 group identities")
    if any(
        type(count) is not int or count < 1
        for count in (diagnostic_count, reserved_count)
    ):
        raise ValueError("diagnostic/reserved counts must be positive")
    if len(source_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in source_sha256
    ):
        raise ValueError("source_sha256 must be a SHA-256 hex digest")
    groups: dict[str, list[PreparedCase]] = defaultdict(list)
    seen: set[str] = set()
    for raw in records:
        case = prepare_case(raw, dataset_namespace=dataset_namespace)
        if case.runtime.user_id in seen:
            raise ValueError("duplicate sample identity")
        seen.add(case.runtime.user_id)
        groups[history_group(case)].append(case)
    if not set(excluded) <= set(groups):
        raise ValueError("excluded group is not in the source snapshot")
    eligible = {
        group: members for group, members in groups.items() if group not in excluded
    }
    if diagnostic_count + reserved_count > len(eligible):
        raise ValueError("not enough distinct complete-history groups")
    ordered = sorted(eligible, key=lambda group: (_hash([seed, "group", group]), group))
    representatives = {
        group: min(
            members,
            key=lambda item: (
                _hash([seed, "case", item.scoring.case_id]),
                item.scoring.case_id,
            ),
        )
        for group, members in eligible.items()
    }
    if stratify_by_question_type:
        pools: dict[str, list[str]] = defaultdict(list)
        for group in ordered:
            pools[representatives[group].scoring.category].append(group)
        types = sorted(
            pools, key=lambda category: (_hash([seed, "type", category]), category)
        )
        interleaved = []
        while any(pools.values()):
            for category in types:
                if pools[category]:
                    interleaved.append(pools[category].pop(0))
        ordered = interleaved
    rows = []
    session_content_groups: dict[str, set[str]] = defaultdict(set)
    for index, group in enumerate(ordered[: diagnostic_count + reserved_count]):
        case = representatives[group]
        scope = memory_scope(run_namespace, case.runtime.user_id)
        chunks = case.runtime.ingestion_chunks(max_messages=max_messages)
        for session in case.runtime.sessions:
            session_content_groups[
                _hash([(t.role, t.content) for t in session.turns])
            ].add(group)
        times = [session.turns[0].at for session in case.runtime.sessions]
        rows.append(
            {
                "case_id": case.scoring.case_id,
                "partition": "diagnostic"
                if index < diagnostic_count
                else "reserved-not-run",
                "history_group": group,
                "cases_in_exact_history_group": len(groups[group]),
                "scope_key": scope.scope_key,
                "session_count": len(case.runtime.sessions),
                "raw_turn_count": sum(len(s.turns) for s in case.runtime.sessions),
                "transport_turn_count": sum(len(c.request.messages) for c in chunks),
                "chunk_count": len(chunks),
                "question_reference_time": case.runtime.query.reference_time.isoformat(),
                "sessions_after_query_reference": sum(
                    t > case.runtime.query.reference_time for t in times
                ),
                "history_payload_sha256": _hash(
                    [c.request.model_dump(mode="json") for c in chunks]
                ),
                "chunks": [
                    {
                        "request_id": chunk.request.request_id,
                        "source_session_index": chunk.source_session_index,
                        "source_turn_indices": list(chunk.source_turn_indices),
                        "event_ids": list(event_ids(scope, chunk.request)),
                    }
                    for chunk in chunks
                ],
            }
        )
        if stratify_by_question_type:
            rows[-1]["sampling_stratum"] = case.scoring.category
    overlap_count = sum(
        len(group_set) > 1 for group_set in session_content_groups.values()
    )
    manifest = {
        "runner": "doppel.public-memory-pilot-manifest.v1",
        "source_sha256": source_sha256,
        "source_case_count": len(records),
        "exact_history_group_count": len(groups),
        "dataset_namespace": dataset_namespace,
        "run_namespace": run_namespace,
        "seed": seed,
        "selection_rule": "seeded-hash-complete-history-groups-one-case-per-group-no-label-selection",
        "diagnostic_count": diagnostic_count,
        "reserved_count": reserved_count,
        "max_messages": max_messages,
        "cases": rows,
        "planned_embedding": {"model": LOCAL_EMBEDDING, "dimensions": 512},
        "planned_reranker": "bge-reranker-v2-m3",
        "temporal_policy": TEMPORAL_POLICY,
        "source_order_policy": "preserve-original-order-and-times",
        "shared_session_content_count_across_selected_history_groups": overlap_count,
        "reserved_is_independently_blind": False,
        "publication_ready": False,
        "aml_academic_model_compliant": False,
        "quality_metrics_available": False,
        "model_execution_performed": False,
        "llm_calls": 0,
        "provider_tokens": 0,
        "remaining_execution_gates": [
            "provider-output-cache-budget-and-rejection-accounting",
            "real-local-vector-reranker-and-raw-derived-retrieval-composition",
            "raw-evidence-preserving-graph-projection",
            "production-natural-planning-and-scoring-with-explicit-denominators",
        ],
    }
    if excluded or stratify_by_question_type:
        manifest.update(
            excluded_history_groups=excluded,
            eligible_history_group_count=len(eligible),
            stratify_by_question_type=stratify_by_question_type,
            selection_rule=(
                "seeded-public-type-round-robin-one-case-per-complete-history-excluding-prior-groups-no-gold"
                if stratify_by_question_type
                else "seeded-complete-history-groups-excluding-prior-groups-no-label-selection"
            ),
            public_type_used_for_sampling_only=stratify_by_question_type,
        )
    manifest["manifest_fingerprint"] = _hash(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-namespace", default="longmemeval-s-cleaned-local-v1")
    parser.add_argument(
        "--run-namespace", default="longmemeval-local-pilot-20261007-v1"
    )
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument("--diagnostic-count", type=int, default=3)
    parser.add_argument("--reserved-count", type=int, default=3)
    parser.add_argument("--max-messages", type=int, default=20)
    parser.add_argument("--exclude-manifest", type=Path, action="append", default=[])
    parser.add_argument("--stratify-by-question-type", action="store_true")
    args = parser.parse_args()
    if args.output.resolve() == args.dataset.resolve() or args.output.exists():
        raise FileExistsError(
            "choose a new manifest output path; never overwrite source or plan"
        )
    data = args.dataset.read_bytes()
    records = json.loads(data)
    if not isinstance(records, list) or not all(
        isinstance(item, dict) for item in records
    ):
        raise ValueError("dataset must contain an array of cases")
    excluded = []
    for path in args.exclude_manifest:
        prior = json.loads(path.read_text(encoding="utf-8"))
        payload = dict(prior)
        fingerprint = payload.pop("manifest_fingerprint", None)
        if (
            fingerprint != _hash(payload)
            or prior.get("source_sha256") != hashlib.sha256(data).hexdigest()
        ):
            raise ValueError("excluded manifest must match its fingerprint and source")
        excluded.extend(row["history_group"] for row in prior["cases"])
    manifest = build_manifest(
        records,
        dataset_namespace=args.dataset_namespace,
        run_namespace=args.run_namespace,
        source_sha256=hashlib.sha256(data).hexdigest(),
        seed=args.seed,
        diagnostic_count=args.diagnostic_count,
        reserved_count=args.reserved_count,
        max_messages=args.max_messages,
        excluded_history_groups=excluded,
        stratify_by_question_type=args.stratify_by_question_type,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "manifest_fingerprint": manifest["manifest_fingerprint"],
                "diagnostic_count": manifest["diagnostic_count"],
                "reserved_count": manifest["reserved_count"],
                "quality_metrics_available": False,
            }
        )
    )


if __name__ == "__main__":
    main()

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
) -> dict[str, Any]:
    """Selection depends on raw histories/IDs, never gold labels, category or answer."""
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
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
    if diagnostic_count + reserved_count > len(groups):
        raise ValueError("not enough distinct complete-history groups")
    ordered = sorted(groups, key=lambda group: (_hash([seed, "group", group]), group))
    rows = []
    session_content_groups: dict[str, set[str]] = defaultdict(set)
    for index, group in enumerate(ordered[: diagnostic_count + reserved_count]):
        case = min(
            groups[group],
            key=lambda item: (
                _hash([seed, "case", item.scoring.case_id]),
                item.scoring.case_id,
            ),
        )
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
    manifest = build_manifest(
        records,
        dataset_namespace=args.dataset_namespace,
        run_namespace=args.run_namespace,
        source_sha256=hashlib.sha256(data).hexdigest(),
        seed=args.seed,
        diagnostic_count=args.diagnostic_count,
        reserved_count=args.reserved_count,
        max_messages=args.max_messages,
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

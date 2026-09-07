"""Offline memory-level reranking replay over an existing retrieval report."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from benchmarks.personal_retrieval_ablation import (
    AblationDataset,
    _SentenceTransformersRelationReranker,
)
from doppel_memory import RelationReranker, RelationRerankItem, RelationRerankRequest

ROOT = Path(__file__).resolve().parents[1]
Mode = Literal["raw_question", "planner_context"]


def _load_dataset(path: Path, revision: str = "") -> AblationDataset:
    if not revision:
        return AblationDataset.model_validate_json(path.read_bytes())
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("revision-backed dataset must be inside the repository") from exc
    completed = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return AblationDataset.model_validate_json(completed.stdout)


def _planner_drafts(path: Path | None, fingerprint: str) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    raw = json.loads(path.read_bytes())
    if str((raw.get("dataset") or {}).get("fingerprint") or "") != fingerprint:
        raise ValueError("planner report dataset fingerprint mismatch")
    return {
        str(item["query_id"]): dict(item["actual"])
        for item in raw.get("cases", [])
        if not item.get("error") and item.get("actual") is not None
    }


def _query_text(query: Any, draft: dict[str, Any], mode: Mode) -> str:
    if mode == "raw_question" or not draft:
        return query.query
    return (
        f"Question: {query.query}\n"
        f"Entities: {', '.join(draft.get('entity_mentions') or [])}\n"
        f"Relation hints: {', '.join(draft.get('relation_hints') or [])}\n"
        "Candidate relation types: "
        f"{', '.join(draft.get('relation_types') or [])}"
    )


def _metrics(rows: list[dict[str, Any]], queries: dict[str, Any], field: str) -> dict[str, Any]:
    evidence = [row for row in rows if queries[row["query_id"]].required_memory_ids]
    reciprocal_ranks: list[float] = []
    for row in evidence:
        required = set(queries[row["query_id"]].required_memory_ids)
        reciprocal_ranks.append(next(
            (1 / rank for rank, memory_id in enumerate(row[field], 1)
             if memory_id in required), 0.0
        ))
    return {
        "evidence_query_count": len(evidence),
        "recall_at_1": round(sum(bool(row[field] and row[field][0] in
                              queries[row["query_id"]].required_memory_ids)
                             for row in evidence) / max(len(evidence), 1), 6),
        "recall_at_5": round(sum(any(memory_id in
                                    queries[row["query_id"]].required_memory_ids
                                    for memory_id in row[field][:5])
                             for row in evidence) / max(len(evidence), 1), 6),
        "mrr": round(sum(reciprocal_ranks) / max(len(evidence), 1), 6),
        "legacy_forbidden_top1_count": sum(
            bool(row[field] and row[field][0] in
                 queries[row["query_id"]].forbidden_memory_ids)
            for row in rows
        ),
    }


async def run_replay(
    dataset: AblationDataset,
    source_report: dict[str, Any],
    reranker: RelationReranker,
    *,
    profile: str,
    drafts: dict[str, dict[str, Any]] | None = None,
    modes: tuple[Mode, ...] = ("raw_question",),
    external_llm_calls: int | None = None,
) -> dict[str, Any]:
    if str((source_report.get("dataset") or {}).get("fingerprint") or "") != dataset.fingerprint:
        raise ValueError("source retrieval report dataset fingerprint mismatch")
    queries = {item.query_id: item for item in dataset.queries}
    fixtures = {item.memory_id: item for item in dataset.fixtures}
    source_cases = [case for case in source_report.get("cases", [])
                    if case.get("profile") == profile]
    if {case["query_id"] for case in source_cases} != set(queries):
        raise ValueError("source profile does not contain exactly the dataset queries")
    base_rows = [{
        "query_id": case["query_id"],
        "before": list(case.get("hits") or []),
        "source_failed": bool(case.get("error")),
    } for case in source_cases]
    unknown = sorted({memory_id for row in base_rows for memory_id in row["before"]
                      if memory_id not in fixtures})
    if unknown:
        raise ValueError("source report contains hit IDs outside the dataset")

    mode_results: dict[str, Any] = {}
    for mode in modes:
        rows: list[dict[str, Any]] = []
        started = perf_counter()
        for source in base_rows:
            query = queries[source["query_id"]]
            hits = source["before"]
            aliases = {f"item_{index}": memory_id
                       for index, memory_id in enumerate(hits)}
            if hits:
                raw_scores = await reranker.rerank(
                    RelationRerankRequest(
                        query_text=_query_text(query, (drafts or {}).get(query.query_id, {}), mode),
                        items=[RelationRerankItem(
                            item_id=alias,
                            relation_type=(
                                getattr(
                                    fixtures[memory_id].relation,
                                    "relation_type",
                                    "",
                                )
                                or "UNKNOWN"
                            ),
                            fact=fixtures[memory_id].content,
                        ) for alias, memory_id in aliases.items()],
                    )
                )
                score_by_alias = {item.item_id: float(item.score) for item in raw_scores}
                if set(score_by_alias) != set(aliases) or len(raw_scores) != len(aliases):
                    raise ValueError("reranker must return exactly one score per opaque item")
                positions = sorted(range(len(hits)),
                                   key=lambda index: score_by_alias[f"item_{index}"],
                                   reverse=True)
                after = [hits[index] for index in positions]
                scores = {hits[index]: round(score_by_alias[f"item_{index}"], 6)
                          for index in range(len(hits))}
            else:
                after, scores = [], {}
            rows.append({**source, "after": after, "scores": scores})
        before = _metrics(rows, queries, "before")
        after = _metrics(rows, queries, "after")
        mode_results[mode] = {
            "before": before,
            "after": after,
            "delta": {key: round(after[key] - before[key], 6)
                      for key in ("recall_at_1", "recall_at_5", "mrr",
                                  "legacy_forbidden_top1_count")},
            "top1_gains": [row["query_id"] for row in rows
                           if not _top1_ok(row["before"], queries[row["query_id"]])
                           and _top1_ok(row["after"], queries[row["query_id"]])],
            "top1_losses": [row["query_id"] for row in rows
                            if _top1_ok(row["before"], queries[row["query_id"]])
                            and not _top1_ok(row["after"], queries[row["query_id"]])],
            "candidate_set_changed_count": sum(
                set(row["before"]) != set(row["after"]) for row in rows
            ),
            "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "cases": rows,
        }
    return {
        "runner": "doppel.personal-candidate-rerank-replay.v1",
        "publication_ready": False,
        "dataset": {"name": dataset.suite, "version": dataset.suite_version,
                    "fingerprint": dataset.fingerprint},
        "source_profile": profile,
        "source_candidate_fusion": source_report.get("candidate_fusion"),
        "reranker": {"name": str(reranker.name), "version": str(reranker.version)},
        "external_llm_calls": external_llm_calls,
        "modes": mode_results,
    }


def _top1_ok(hits: list[str], query: Any) -> bool:
    return bool(hits and hits[0] in query.required_memory_ids)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-git-revision", default="")
    parser.add_argument("--planner-report", type=Path)
    parser.add_argument("--profile", default="lexical_vector_relation_reranked")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--include-planner-context", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


async def _main(args: argparse.Namespace) -> None:
    dataset = _load_dataset(args.dataset, args.dataset_git_revision)
    source_bytes = args.source_report.read_bytes()
    source = json.loads(source_bytes)
    drafts = _planner_drafts(args.planner_report, dataset.fingerprint)
    reranker = _SentenceTransformersRelationReranker(
        str(args.model.resolve()), score_normalization="sigmoid",
        device=args.device, batch_size=args.batch_size,
    )
    modes: tuple[Mode, ...] = (
        ("raw_question", "planner_context")
        if args.include_planner_context else ("raw_question",)
    )
    report = await run_replay(dataset, source, reranker, profile=args.profile,
                              drafts=drafts, modes=modes, external_llm_calls=0)
    report["source_report"] = {
        "path": str(args.source_report.resolve()),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{digest}  {args.output.name}\n", encoding="utf-8"
    )
    print(f"personal candidate rerank replay: {args.output}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    asyncio.run(_main(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())

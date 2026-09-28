"""Budgeted downstream judgment replay over bounded retrieval evidence bundles.

This runner deliberately evaluates a boundary that retrieval metrics cannot answer:
whether a model can distinguish sufficient support from merely related memories once
the retriever has assembled a bounded context.  It never gives the model Store memory
IDs, gold labels, scopes, or retrieval-source attribution.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from benchmarks.heterogeneous_retrieval_quality import (
    HeterogeneousMemory,
    HeterogeneousQuery,
    HeterogeneousRetrievalDataset,
    load_dataset,
)
from benchmarks.relation_planner_quality import (
    CachedStructuredOutputModel,
    PlannerCallBudgetExceeded,
    StructuredOutputCallBudget,
    UsageLedger,
)
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import (
    OpenAICompatibleStructuredOutputConfig,
    OpenAICompatibleStructuredOutputModel,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "benchmarks/datasets/heterogeneous-retrieval-zh-v4.json"
DEFAULT_REPORT = (
    ROOT / "data/doppel/heterogeneous-retrieval-v8-path-family-opened-live.json"
)
DEFAULT_OUTPUT = ROOT / "data/doppel/evidence-bundle-judgment-opened.json"
DEFAULT_PROFILES = (
    "assembled_semantic_path_exploration_hybrid_memory_reranking",
    "assembled_semantic_path_family_exploration_hybrid_memory_reranking",
)
RUNNER = "doppel.evidence-bundle-judgment.v1"
RANK_FIRST_PROFILE, EVIDENCE_RICH_PROFILE = DEFAULT_PROFILES
MAX_JUDGMENT_ACCURACY_REGRESSION = 0.02
MAX_EXACT_SUPPORT_REGRESSION = 0.02
INSTRUCTIONS = """\
You judge whether the supplied personal-memory items are sufficient to answer the
user's question. Use only the supplied items; never use outside knowledge or fill a
missing relation by plausibility. Multiple items may jointly provide a multi-hop
answer. A semantically related item is not support unless its stated facts establish
the requested claim. If the evidence is insufficient, conflicting, or answers a
different relation, set answerable=false and return no supporting item IDs. Otherwise
set answerable=true and return every item needed to establish the answer. Return only
the requested JSON object.
"""


class EvidenceJudgment(BaseModel):
    """Provider decision over opaque, request-local candidate identifiers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answerable: bool
    supporting_item_ids: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("supporting_item_ids", mode="before")
    @classmethod
    def _normalize_ids(cls, value: object) -> list[str]:
        items = value if isinstance(value, (list, tuple)) else []
        normalized = [str(item or "").strip() for item in items]
        return list(dict.fromkeys(item for item in normalized if item))

    @model_validator(mode="after")
    def _validate_abstention(self) -> EvidenceJudgment:
        if not self.answerable and self.supporting_item_ids:
            raise ValueError("an abstention cannot select supporting items")
        if self.answerable and not self.supporting_item_ids:
            raise ValueError("an answerable judgment requires supporting items")
        return self


class EvidenceJudgmentSelectionGroup(BaseModel):
    """One explicit post-hoc diagnostic stratum."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    rationale: str = Field(min_length=1)
    case_ids: list[str] = Field(min_length=1)

    @field_validator("case_ids", mode="before")
    @classmethod
    def _normalize_case_ids(cls, value: object) -> list[str]:
        items = value if isinstance(value, (list, tuple)) else []
        normalized = [str(item or "").strip() for item in items]
        result = [item for item in normalized if item]
        if len(result) != len(set(result)):
            raise ValueError("selection group repeats a case ID")
        return result


class EvidenceJudgmentSelection(BaseModel):
    """Bound diagnostic selection; never an unseen-quality corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    suite: Literal["doppel-evidence-bundle-diagnostic-selection"]
    version: Literal["1.0.0"]
    status: Literal["opened_posthoc_diagnostic"]
    publication_ready: Literal[False]
    source_dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_retrieval_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    groups: list[EvidenceJudgmentSelectionGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_cases(self) -> EvidenceJudgmentSelection:
        names = [group.name for group in self.groups]
        if len(names) != len(set(names)):
            raise ValueError("selection group names must be unique")
        case_ids = [case_id for group in self.groups for case_id in group.case_ids]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("diagnostic case IDs cannot overlap between groups")
        return self

    @property
    def case_ids(self) -> list[str]:
        return [case_id for group in self.groups for case_id in group.case_ids]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", action="store_true")
    result.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    result.add_argument("--retrieval-report", type=Path, default=DEFAULT_REPORT)
    result.add_argument("--selection-file", type=Path, default=None)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--profile", action="append", dest="profiles")
    result.add_argument(
        "--partition",
        action="append",
        choices=("dev", "sealed", "adversarial"),
    )
    result.add_argument("--max-cases", type=int, default=0)
    result.add_argument("--context-limit", type=int, default=10)
    result.add_argument("--max-calls", type=int, default=0)
    result.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data/doppel/evidence-bundle-judgment-cache",
    )
    result.add_argument(
        "--model", default=os.environ.get("DOPPEL_MODEL", "deepseek-v4-flash")
    )
    result.add_argument(
        "--base-url",
        default=os.environ.get("DOPPEL_OPENAI_BASE_URL", "https://api.deepseek.com"),
    )
    result.add_argument(
        "--schema-mode",
        choices=("json_object", "json_schema"),
        default=os.environ.get("DOPPEL_SCHEMA_MODE", "json_object"),
    )
    result.add_argument("--max-completion-tokens", type=int, default=256)
    result.add_argument("--timeout-seconds", type=float, default=60.0)
    return result


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _selected_cases(
    dataset: HeterogeneousRetrievalDataset,
    *,
    partitions: Sequence[str],
    max_cases: int,
) -> list[HeterogeneousQuery]:
    if max_cases < 0:
        raise ValueError("max-cases must be non-negative")
    selected = [case for case in dataset.queries if case.partition in partitions]
    if max_cases:
        selected = selected[:max_cases]
    if not selected:
        raise ValueError("selected partitions contain no cases")
    return selected


def load_selection(
    path: Path,
    dataset: HeterogeneousRetrievalDataset,
    retrieval_report: Mapping[str, Any],
) -> EvidenceJudgmentSelection:
    selection = EvidenceJudgmentSelection.model_validate_json(path.read_bytes())
    if selection.source_dataset_fingerprint != dataset.fingerprint:
        raise ValueError("selection dataset fingerprint mismatch")
    if selection.source_retrieval_report_sha256 != retrieval_report.get(
        "report_sha256"
    ):
        raise ValueError("selection retrieval report fingerprint mismatch")
    known = {case.case_id for case in dataset.queries}
    unknown = sorted(set(selection.case_ids).difference(known))
    if unknown:
        raise ValueError("selection contains unknown case IDs")
    return selection


def _selection_cases(
    dataset: HeterogeneousRetrievalDataset,
    selection: EvidenceJudgmentSelection,
) -> list[HeterogeneousQuery]:
    by_id = {case.case_id: case for case in dataset.queries}
    return [by_id[case_id] for case_id in selection.case_ids]


def _load_profile_rows(
    report_path: Path,
    dataset: HeterogeneousRetrievalDataset,
    profiles: Sequence[str],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, Any]]:
    report = json.loads(report_path.read_text("utf-8"))
    if report.get("hard_failure"):
        raise ValueError("retrieval report contains a hard failure")
    report_dataset = dict(report.get("dataset") or {})
    if report_dataset.get("fingerprint") != dataset.fingerprint:
        raise ValueError("retrieval report dataset fingerprint mismatch")
    available = dict(report.get("profiles") or {})
    rows_by_profile: dict[str, dict[str, list[str]]] = {}
    for profile in profiles:
        details = list(dict(available.get(profile) or {}).get("details") or [])
        if not details:
            raise ValueError(f"retrieval profile has no detail rows: {profile}")
        rows: dict[str, list[str]] = {}
        for detail in details:
            case_id = str(detail.get("case_id") or "")
            ids = [str(item) for item in list(detail.get("ids") or [])]
            if not case_id or case_id in rows:
                raise ValueError(f"invalid duplicate retrieval row: {profile}")
            if len(ids) != len(set(ids)):
                raise ValueError(f"retrieval row repeats a memory ID: {case_id}")
            rows[case_id] = ids
        rows_by_profile[profile] = rows
    return rows_by_profile, report


def build_judgment_request(
    case: HeterogeneousQuery,
    ranked_ids: Sequence[str],
    memories: Mapping[str, HeterogeneousMemory],
    *,
    context_limit: int,
) -> tuple[StructuredGenerationRequest, dict[str, str]]:
    """Build one gold-free provider request and its private opaque-ID mapping."""

    if not 1 <= context_limit <= 20:
        raise ValueError("context-limit must be between 1 and 20")
    selected = list(ranked_ids[:context_limit])
    unknown = [memory_id for memory_id in selected if memory_id not in memories]
    if unknown:
        raise ValueError("retrieval bundle contains unknown memory IDs")
    opaque_to_memory: dict[str, str] = {}
    candidates: list[dict[str, Any]] = []
    for index, memory_id in enumerate(selected, start=1):
        item_id = f"item_{index:02d}"
        memory = memories[memory_id]
        opaque_to_memory[item_id] = memory_id
        candidates.append(
            {
                "item_id": item_id,
                "content": memory.content,
                "kind": memory.kind,
                "source_kind": memory.source_kind,
                "temporal_status": memory.temporal_status,
                "valid_from": memory.valid_from,
                "valid_to": memory.valid_to or None,
            }
        )
    return (
        StructuredGenerationRequest(
            instructions=INSTRUCTIONS,
            input={
                "question": case.query,
                "question_time": case.valid_at,
                "candidate_memories": candidates,
            },
            output_schema=EvidenceJudgment.model_json_schema(),
        ),
        opaque_to_memory,
    )


def score_judgment(
    case: HeterogeneousQuery,
    ranked_ids: Sequence[str],
    judgment: EvidenceJudgment,
    opaque_to_memory: Mapping[str, str],
    *,
    context_limit: int,
) -> dict[str, Any]:
    selected_opaque = judgment.supporting_item_ids
    if any(item_id not in opaque_to_memory for item_id in selected_opaque):
        raise ValueError("provider selected an item outside the supplied bundle")
    selected = [opaque_to_memory[item_id] for item_id in selected_opaque]
    context = list(ranked_ids[:context_limit])
    required = set(case.required_memory_ids)
    selected_set = set(selected)
    retrieval_sufficient = case.answerable and required.issubset(context)
    expected_answerable = bool(retrieval_sufficient)
    selected_required = selected_set & required
    support_recall = (
        len(selected_required) / len(required) if required else float(not selected_set)
    )
    support_precision = (
        len(selected_required) / len(selected_set) if selected_set else 1.0
    )
    support_exact = expected_answerable and selected_set == required
    decision_correct = judgment.answerable == expected_answerable
    end_to_end_success = bool(
        case.answerable and judgment.answerable and required.issubset(selected_set)
    )
    return {
        "case_id": case.case_id,
        "partition": case.partition,
        "category": case.category,
        "source_answerable": case.answerable,
        "retrieval_sufficient": retrieval_sufficient,
        "expected_answerable": expected_answerable,
        "judged_answerable": judgment.answerable,
        "decision_correct": decision_correct,
        "support_exact": support_exact,
        "support_recall": round(support_recall, 6),
        "support_precision": round(support_precision, 6),
        "selected_count": len(selected),
        "related_selected": len(selected_set & set(case.related_memory_ids)),
        "hard_forbidden_selected": len(
            selected_set & set(case.hard_forbidden_memory_ids)
        ),
        "end_to_end_success": end_to_end_success,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize an empty judgment result")
    source_answerable = [row for row in rows if row["source_answerable"]]
    sufficient = [row for row in rows if row["retrieval_sufficient"]]
    insufficient = [row for row in rows if not row["retrieval_sufficient"]]
    source_no_answer = [row for row in rows if not row["source_answerable"]]

    def rate(items: Sequence[Mapping[str, Any]], field: str) -> float:
        return (
            round(sum(bool(item[field]) for item in items) / len(items), 6)
            if items
            else 1.0
        )

    return {
        "cases": len(rows),
        "source_answerable_cases": len(source_answerable),
        "retrieval_sufficient_cases": len(sufficient),
        "retrieval_sufficiency_rate": rate(source_answerable, "retrieval_sufficient"),
        "judgment_accuracy": rate(rows, "decision_correct"),
        "sufficient_bundle_judgment_accuracy": rate(sufficient, "decision_correct"),
        "insufficient_bundle_abstention_rate": rate(insufficient, "decision_correct"),
        "source_no_answer_abstention_rate": rate(source_no_answer, "decision_correct"),
        "exact_support_selection_rate": rate(sufficient, "support_exact"),
        "mean_support_recall": round(
            statistics.mean(float(row["support_recall"]) for row in sufficient), 6
        )
        if sufficient
        else 1.0,
        "mean_support_precision": round(
            statistics.mean(float(row["support_precision"]) for row in sufficient),
            6,
        )
        if sufficient
        else 1.0,
        "end_to_end_support_success_rate": rate(
            source_answerable, "end_to_end_success"
        ),
        "related_items_selected": sum(int(row["related_selected"]) for row in rows),
        "hard_forbidden_items_selected": sum(
            int(row["hard_forbidden_selected"]) for row in rows
        ),
        "decision_counts": dict(
            sorted(Counter(bool(row["judged_answerable"]) for row in rows).items())
        ),
    }


def compare_default_profiles(
    summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Apply the frozen V7/V8 policy comparison without inventing a blend."""

    required_metrics = {
        "retrieval_sufficiency_rate",
        "judgment_accuracy",
        "source_no_answer_abstention_rate",
        "exact_support_selection_rate",
        "end_to_end_support_success_rate",
    }
    if not {RANK_FIRST_PROFILE, EVIDENCE_RICH_PROFILE}.issubset(summaries) or any(
        not required_metrics.issubset(summaries[profile])
        for profile in (RANK_FIRST_PROFILE, EVIDENCE_RICH_PROFILE)
    ):
        return None
    rank_first = summaries[RANK_FIRST_PROFILE]
    evidence_rich = summaries[EVIDENCE_RICH_PROFILE]

    def delta(metric: str) -> float:
        return round(float(evidence_rich[metric]) - float(rank_first[metric]), 6)

    deltas = {
        metric: delta(metric)
        for metric in (
            "retrieval_sufficiency_rate",
            "judgment_accuracy",
            "source_no_answer_abstention_rate",
            "exact_support_selection_rate",
            "end_to_end_support_success_rate",
        )
    }
    checks = {
        "retrieval_sufficiency_non_regression": deltas["retrieval_sufficiency_rate"]
        >= 0,
        "end_to_end_support_non_regression": deltas["end_to_end_support_success_rate"]
        >= 0,
        "no_answer_abstention_non_regression": deltas[
            "source_no_answer_abstention_rate"
        ]
        >= 0,
        "judgment_accuracy_bounded_regression": deltas["judgment_accuracy"]
        >= -MAX_JUDGMENT_ACCURACY_REGRESSION,
        "exact_support_selection_bounded_regression": deltas[
            "exact_support_selection_rate"
        ]
        >= -MAX_EXACT_SUPPORT_REGRESSION,
    }
    return {
        "rank_first_profile": RANK_FIRST_PROFILE,
        "evidence_rich_profile": EVIDENCE_RICH_PROFILE,
        "deltas_evidence_rich_minus_rank_first": deltas,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "policy_preference_supported": all(checks.values())
        and deltas["end_to_end_support_success_rate"] > 0,
        "maximum_judgment_accuracy_regression": (MAX_JUDGMENT_ACCURACY_REGRESSION),
        "maximum_exact_support_regression": MAX_EXACT_SUPPORT_REGRESSION,
    }


async def run(args: argparse.Namespace) -> int:
    profiles = tuple(dict.fromkeys(args.profiles or DEFAULT_PROFILES))
    dataset = load_dataset(args.dataset)
    profile_rows, source_report = _load_profile_rows(
        args.retrieval_report, dataset, profiles
    )
    selection: EvidenceJudgmentSelection | None = None
    if args.selection_file is not None:
        if args.partition or args.max_cases:
            raise ValueError(
                "selection-file cannot be combined with partition or max-cases"
            )
        selection = load_selection(args.selection_file, dataset, source_report)
        cases = _selection_cases(dataset, selection)
        partitions = tuple(dict.fromkeys(case.partition for case in cases))
    else:
        partitions = tuple(
            dict.fromkeys(args.partition or ("dev", "sealed", "adversarial"))
        )
        cases = _selected_cases(
            dataset, partitions=partitions, max_cases=args.max_cases
        )
    missing = {
        profile: sorted(
            case.case_id for case in cases if case.case_id not in profile_rows[profile]
        )
        for profile in profiles
    }
    if any(missing.values()):
        raise ValueError("retrieval report does not cover every selected case")
    if not 1 <= args.context_limit <= 20:
        raise ValueError("context-limit must be between 1 and 20")
    if args.max_calls < 0:
        raise ValueError("max-calls must be non-negative")
    plan = {
        "runner": RUNNER,
        "mode": "live" if args.live else "dry_run",
        "dataset": {
            "suite": dataset.suite,
            "fingerprint": dataset.fingerprint,
            "role": "opened_development_replay",
        },
        "retrieval_report": {
            "path": str(args.retrieval_report.resolve()),
            "report_sha256": source_report.get("report_sha256"),
        },
        "profiles": list(profiles),
        "partitions": list(partitions),
        "selection": (
            {
                "path": str(args.selection_file.resolve()),
                "sha256": hashlib.sha256(args.selection_file.read_bytes()).hexdigest(),
                "status": selection.status,
                "publication_ready": selection.publication_ready,
                "groups": [
                    {
                        "name": group.name,
                        "case_count": len(group.case_ids),
                        "rationale": group.rationale,
                    }
                    for group in selection.groups
                ],
            }
            if selection is not None and args.selection_file is not None
            else None
        ),
        "selected_cases": len(cases),
        "context_limit": args.context_limit,
        "maximum_logical_requests": len(cases) * len(profiles),
        "maximum_provider_calls": args.max_calls,
        "gold_memory_ids_exposed_to_model": False,
        "scope_or_retrieval_attribution_exposed_to_model": False,
        "answer_text_scored": False,
        "implementation_commit": _git_commit(),
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    key = os.environ.get("DOPPEL_API_KEY", "").strip()
    if not key and args.max_calls > 0:
        raise RuntimeError("DOPPEL_API_KEY is required when live calls are allowed")
    config = OpenAICompatibleStructuredOutputConfig(
        model=args.model,
        base_url=args.base_url,
        schema_mode=args.schema_mode,
        max_completion_tokens=args.max_completion_tokens,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
        timeout_seconds=args.timeout_seconds,
    )
    usage = UsageLedger()
    provider = OpenAICompatibleStructuredOutputModel(
        config,
        api_key=key or "cache-only-no-network",
        usage_observer=usage.observe,
    )
    budget = StructuredOutputCallBudget(provider, max_calls=args.max_calls)
    cached = CachedStructuredOutputModel(budget, args.cache_dir)
    memories = {memory.memory_id: memory for memory in dataset.memories}
    rows_by_profile: dict[str, list[dict[str, Any]]] = {
        profile: [] for profile in profiles
    }
    errors: list[dict[str, str]] = []
    try:
        stop = False
        for profile in profiles:
            for case in cases:
                ranked = profile_rows[profile][case.case_id]
                request, mapping = build_judgment_request(
                    case, ranked, memories, context_limit=args.context_limit
                )
                try:
                    raw = await cached.generate(request)
                    judgment = EvidenceJudgment.model_validate(raw)
                    row = score_judgment(
                        case,
                        ranked,
                        judgment,
                        mapping,
                        context_limit=args.context_limit,
                    )
                except PlannerCallBudgetExceeded:
                    stop = True
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "profile": profile,
                            "case_id": case.case_id,
                            "error_type": type(exc).__name__,
                        }
                    )
                    continue
                rows_by_profile[profile].append(row)
            if stop:
                break
    finally:
        await provider.aclose()

    summaries = {
        profile: summarize(rows) if rows else {"cases": 0}
        for profile, rows in rows_by_profile.items()
    }
    comparison = compare_default_profiles(summaries)
    complete = all(len(rows_by_profile[profile]) == len(cases) for profile in profiles)
    gate_checks = {
        "selection_complete": complete,
        "provider_errors": not errors,
        "hard_forbidden_selection": all(
            summary.get("hard_forbidden_items_selected", 0) == 0
            for summary in summaries.values()
        ),
        "default_profile_comparison": comparison is None or not comparison["failures"],
    }
    report: dict[str, Any] = {
        "result_schema_version": 1,
        "runner": RUNNER,
        "generated_at": datetime.now(UTC).isoformat(),
        "plan": plan,
        "provider": {
            "model": config.model,
            "generation_fingerprint": config.generation_fingerprint,
            "schema_mode": config.schema_mode,
        },
        "budget": {
            "provider_calls": budget.calls,
            "maximum": args.max_calls,
            "within_budget": budget.calls <= args.max_calls,
        },
        "cache": {"hits": cached.hits, "misses": cached.misses},
        "usage": usage.report(),
        "profiles": summaries,
        "comparison": comparison,
        "errors": errors,
        "gate": {
            "ok": all(gate_checks.values()),
            "checks": gate_checks,
            "failures": [name for name, passed in gate_checks.items() if not passed],
        },
        "limitations": {
            "opened_source_corpus": True,
            "answer_text_correctness_unmeasured": True,
            "publication_quality_claim_allowed": False,
        },
        "details": rows_by_profile,
    }
    report["report_sha256"] = _fingerprint(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "report_sha256": report["report_sha256"],
                "budget": report["budget"],
                "cache": report["cache"],
                "profiles": summaries,
                "gate": report["gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["gate"]["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())

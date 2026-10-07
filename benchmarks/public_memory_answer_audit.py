"""Deterministic audit of the preserved reader/judge run; no model or network use.

The audit reads the frozen live report, the frozen comparison artifact and the public
dataset, builds a per-row packet with the exact model text, and validates hand-authored
audit decisions against it: quotes must appear verbatim in the named source, and
context presence/absence claims are re-verified from the preserved rows. The revised
labels are the auditor's, never a copy of the original judge output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AUDIT_SCHEMA = "doppel.public-memory-answer-audit.v1"
EXPECTED_ROWS = 18
ANSWER_MATCH = ("correct", "partially_correct", "incorrect", "not_applicable")
COMMITMENT = (
    "committed",
    "hedged_derivation",
    "refused_unavailable",
    "refused_conflicting_premise",
    "no_claim",
)
CITATION_SUPPORT = (
    "supported",
    "partially_supported",
    "unsupported",
    "not_applicable",
)
FAITHFULNESS = ("grounded", "partly_grounded", "ungrounded")
ATTRIBUTION = (
    "none",
    "retrieval_or_packing_loss",
    "channel_coverage",
    "reader_reasoning",
    "reader_citation",
    "reader_abstention_consistency",
    "language",
    "judge_criterion",
)
QUOTE_SOURCES = ("answer", "cited_item", "reference_answer", "question")
CHECK_SCOPES = ("row_context", "cited_items")


class AuditToolError(ValueError):
    """Invalid packet/decision input; never contains model or provider text."""


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str
    source: Literal["answer", "cited_item", "reference_answer", "question"]

    @field_validator("text")
    @classmethod
    def quote_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("quote must not be blank")
        return value


class ContextCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    term: str
    expected: Literal["present", "absent"]
    scope: Literal["row_context", "cited_items"]

    @field_validator("term")
    @classmethod
    def term_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("term must not be blank")
        return value


class AuditDecision(BaseModel):
    """One auditor-authored row decision; quotes and checks are re-verified."""

    model_config = ConfigDict(extra="forbid", strict=True)

    row: int
    answer_match: Literal["correct", "partially_correct", "incorrect", "not_applicable"]
    commitment: Literal[
        "committed",
        "hedged_derivation",
        "refused_unavailable",
        "refused_conflicting_premise",
        "no_claim",
    ]
    citation_support: Literal[
        "supported", "partially_supported", "unsupported", "not_applicable"
    ]
    citation_contradiction: bool
    faithfulness: Literal["grounded", "partly_grounded", "ungrounded"]
    abstained_expected: bool
    abstained_consistent: bool
    attributions: list[str]
    rationale: str
    quotes: list[Quote] = Field(min_length=1)
    context_checks: list[ContextCheck]

    @field_validator("rationale")
    @classmethod
    def rationale_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must not be blank")
        return value

    @field_validator("attributions")
    @classmethod
    def attributions_closed(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in ATTRIBUTION]
        if unknown:
            raise ValueError("unknown attribution labels")
        if len(set(value)) != len(value):
            raise ValueError("duplicate attribution labels")
        return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fold(text: str) -> str:
    return _normalize(text).casefold()


def _reference_terms(reference: str) -> list[str]:
    """Heuristic aid only: value-bearing terms of the reference answer."""
    terms = re.findall(r"[A-Za-z]{3,}|\d+", reference.casefold())
    return sorted({term for term in terms})


def _load(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    loaded = json.loads(data)
    if not isinstance(loaded, dict):
        raise AuditToolError("input artifact must be a JSON object")
    return loaded, _sha256(data)


def _dataset_case(
    dataset: Sequence[Mapping[str, Any]], case_id: str
) -> Mapping[str, Any]:
    for record in dataset:
        if record.get("question_id") == case_id:
            return record
    raise AuditToolError("dataset case is missing")


def build_packet(
    report_path: Path, comparison_path: Path, dataset_path: Path
) -> dict[str, Any]:
    """Bind the audit to the exact preserved report, comparison artifact and dataset."""
    report, report_sha256 = _load(report_path)
    comparison, comparison_sha256 = _load(comparison_path)
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    if report.get("runner") != "doppel.public-memory-answer-comparison.v1":
        raise AuditToolError("unexpected report runner")
    if report.get("status") not in {"complete", "partial"}:
        raise AuditToolError("report has no auditable result")
    if comparison.get("runner") != "doppel.public-memory-comparison.v1":
        raise AuditToolError("unexpected comparison runner")
    declared = report.get("input_sha256", {})
    if declared.get("comparison") != comparison_sha256:
        raise AuditToolError("report is not bound to this comparison artifact")
    if declared.get("dataset") != _sha256(dataset_bytes):
        raise AuditToolError("report is not bound to this dataset")
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROWS:
        raise AuditToolError("report does not hold the expected row set")
    context_by_key = {
        (row["case_id"], row["profile"]): row["context"] for row in comparison["rows"]
    }
    packet_rows: list[dict[str, Any]] = []
    for row in rows:
        key = (row["case_id"], row["profile"])
        context = context_by_key.get(key)
        if context is None:
            raise AuditToolError("comparison row is missing for a report row")
        source = _dataset_case(dataset, row["case_id"])
        cited_ids = row["reader"]["cited_memory_ids"]
        cited_items = [item for item in context if item["memory_id"] in set(cited_ids)]
        context_text = _fold(" ".join(item["text"] for item in context))
        cited_text = _fold(" ".join(item["text"] for item in cited_items))
        packet_rows.append(
            {
                "index": row["index"],
                "case_id": row["case_id"],
                "profile": row["profile"],
                "question": str(source.get("question", "")),
                "reference_answer": source.get("answer"),
                "reader": {
                    "status": row["reader"]["status"],
                    "execution": row["reader"]["execution"],
                    "abstained": row["reader"]["abstained"],
                    "answer": row["reader"]["answer"],
                    "cited_memory_ids": list(cited_ids),
                    "failure_class": row["reader"]["failure_class"],
                },
                "old_judge": {
                    "status": row["judge"]["status"],
                    "answer_correct": row["judge"]["answer_correct"],
                    "answer_rationale": row["judge"]["answer_rationale"],
                    "citation_supported": row["judge"]["citation_supported"],
                    "citation_rationale": row["judge"]["citation_rationale"],
                },
                "citation_check": row["citation_check"],
                "cited_items": [_item(item) for item in cited_items],
                "context_items": [_item(item) for item in context],
                "reference_terms": [
                    {
                        "term": term,
                        "present_in_context": term in context_text,
                        "present_in_cited_items": term in cited_text,
                    }
                    for term in _reference_terms(str(source.get("answer", "")))
                ],
            }
        )
    return {
        "audit_schema": AUDIT_SCHEMA,
        "mode": "deterministic-no-model-no-network",
        "source_sha256": {
            "report": report_sha256,
            "comparison": comparison_sha256,
            "dataset": _sha256(dataset_bytes),
        },
        "binding": {
            "report_status": report["status"],
            "plan_fingerprint": report["plan"]["plan_fingerprint"],
            "logical_rows": len(packet_rows),
            "reader_model": report["reader_model"],
            "judge_model": report["judge_model"],
        },
        "rows": packet_rows,
    }


def _item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "memory_id": item["memory_id"],
        "channel": item["channel"],
        "role": item["role"],
        "authority": item["authority"],
        "observed_at": item["observed_at"],
        "temporal_status": item["temporal_status"],
        "valid_from": item["valid_from"],
        "valid_to": item["valid_to"],
        "text": item["text"],
    }


def _source_text(packet_row: Mapping[str, Any], source: str) -> str:
    if source == "answer":
        return str(packet_row["reader"]["answer"] or "")
    if source == "reference_answer":
        return str(packet_row["reference_answer"] or "")
    if source == "question":
        return str(packet_row["question"])
    if source == "cited_item":
        return " ".join(item["text"] for item in packet_row["cited_items"])
    raise AuditToolError("unknown quote source")


def _scope_text(packet_row: Mapping[str, Any], scope: str) -> str:
    if scope == "row_context":
        return " ".join(item["text"] for item in packet_row["context_items"])
    if scope == "cited_items":
        return " ".join(item["text"] for item in packet_row["cited_items"])
    raise AuditToolError("unknown check scope")


def validate_decisions(
    packet: Mapping[str, Any], decisions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Re-verify coverage, closed labels, quote grounding and context checks."""
    if packet.get("audit_schema") != AUDIT_SCHEMA:
        raise AuditToolError("unexpected audit packet schema")
    packet_rows = {row["index"]: row for row in packet["rows"]}
    problems: list[str] = []
    seen: set[int] = set()
    validated: list[dict[str, Any]] = []
    for raw in decisions:
        try:
            decision = AuditDecision.model_validate(raw)
        except Exception as error:  # noqa: BLE001 - report only the validator class
            problems.append(f"decision schema invalid: {type(error).__name__}")
            continue
        if decision.row in seen:
            problems.append(f"row {decision.row}: duplicate decision")
            continue
        seen.add(decision.row)
        packet_row = packet_rows.get(decision.row)
        if packet_row is None:
            problems.append(f"row {decision.row}: no packet row")
            continue
        if decision.abstained_consistent != (
            decision.abstained_expected == bool(packet_row["reader"]["abstained"])
        ):
            problems.append(f"row {decision.row}: abstained consistency mismatch")
        if decision.answer_match == "not_applicable" and packet_row["reader"][
            "status"
        ] != ("completed"):
            problems.append(
                f"row {decision.row}: not_applicable requires a completed reader"
            )
        for quote in decision.quotes:
            haystack = _fold(_source_text(packet_row, quote.source))
            if _fold(quote.text) not in haystack:
                problems.append(
                    f"row {decision.row}: quote not found in {quote.source}"
                )
        for check in decision.context_checks:
            haystack = _fold(_scope_text(packet_row, check.scope))
            present = _fold(check.term) in haystack
            if present != (check.expected == "present"):
                problems.append(
                    f"row {decision.row}: {check.scope} check failed for term"
                )
        validated.append(
            {
                "row": decision.row,
                "case_id": packet_row["case_id"],
                "profile": packet_row["profile"],
                "answer_match": decision.answer_match,
                "commitment": decision.commitment,
                "citation_support": decision.citation_support,
                "citation_contradiction": decision.citation_contradiction,
                "faithfulness": decision.faithfulness,
                "abstained_expected": decision.abstained_expected,
                "abstained_consistent": decision.abstained_consistent,
                "attributions": list(decision.attributions),
                "old_answer_correct": packet_row["old_judge"]["answer_correct"],
                "old_citation_supported": packet_row["old_judge"]["citation_supported"],
            }
        )
    missing = sorted(set(packet_rows) - seen)
    if missing:
        problems.append(f"rows without a decision: {missing}")
    if problems:
        raise AuditToolError("; ".join(problems))
    disagreements = [
        row
        for row in validated
        if (row["answer_match"] == "correct") != (row["old_answer_correct"] is True)
        or (row["citation_support"] in {"supported", "not_applicable"})
        != (row["old_citation_supported"] is True)
    ]
    counts: dict[str, dict[str, int]] = {
        "answer_match": {
            label: sum(row["answer_match"] == label for row in validated)
            for label in ANSWER_MATCH
        },
        "citation_support": {
            label: sum(row["citation_support"] == label for row in validated)
            for label in CITATION_SUPPORT
        },
        "commitment": {
            label: sum(row["commitment"] == label for row in validated)
            for label in COMMITMENT
        },
        "faithfulness": {
            label: sum(row["faithfulness"] == label for row in validated)
            for label in FAITHFULNESS
        },
        "citation_contradiction": {
            "true": sum(row["citation_contradiction"] for row in validated),
            "false": sum(not row["citation_contradiction"] for row in validated),
        },
        "abstained_inconsistent": {
            "true": sum(not row["abstained_consistent"] for row in validated),
            "false": sum(row["abstained_consistent"] for row in validated),
        },
    }
    return {
        "audit_schema": AUDIT_SCHEMA,
        "mode": "deterministic-decision-validation",
        "source_sha256": dict(packet["source_sha256"]),
        "rows_validated": len(validated),
        "counts": counts,
        "disagreements_with_old_judge": disagreements,
        "labels": validated,
    }


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise AuditToolError("output exists; preserve the prior audit artifact")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--packet-out", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--validation-out", type=Path)
    args = parser.parse_args()
    if (args.decisions is None) != (args.validation_out is None):
        parser.error("--decisions and --validation-out are used together")
    if args.packet_out is None and args.validation_out is None:
        parser.error("nothing to write: pass --packet-out and/or --decisions")
    packet = build_packet(args.report, args.comparison, args.dataset)
    if args.decisions is not None:
        decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
        if not isinstance(decisions, list):
            parser.error("decisions file must be a JSON array")
        result = validate_decisions(packet, decisions)
        _write(args.validation_out, result)
        print(
            json.dumps(
                {
                    "rows_validated": result["rows_validated"],
                    "disagreements_with_old_judge": len(
                        result["disagreements_with_old_judge"]
                    ),
                }
            )
        )
    if args.packet_out is not None:
        _write(args.packet_out, packet)
        print(f"packet: {args.packet_out.resolve()}")
        print(f"sha256: {_sha256(args.packet_out.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

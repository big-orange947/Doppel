"""Bounded Judge v2.1: preserved v1 answers, no reader/retrieval/Store mutations.

Keep v2 immutable. Model observations and host-derived taxonomy are separate.
Controls gate the rows arm; citation-order stability is a separate capped arm.
Text anchoring is not semantic verification and audit labels are not ground truth.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_answer_comparison import (
    _ledger_records,
    _request_sha256,
    _StageExecutor,
)
from benchmarks.public_memory_answer_judge_v2 import (
    JUDGE_V2_INSTRUCTIONS,
    JUDGE_V2_SCHEMA,
    JudgeCase,
    JudgeV2Error,
    JudgeV2Output,
    ProviderFactory,
    _abstained_consistency,
    _default_provider_factory,
    _load,
    build_preserved_cases,
    compare_with_audit,
    load_controls,
    summarise_judgments,
    summarise_profiles,
)
from benchmarks.public_memory_answer_judge_v2 import (
    build_judge_request as v2_request,
)
from benchmarks.public_memory_answer_judge_v2 import (
    judge_case_output as v2_output,
)
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.intelligence import StructuredGenerationRequest
from doppel_memory.openai_compatible import OpenAICompatibleStructuredOutputConfig

RUNNER = "doppel.public-memory-answer-judge-v2.1.v1"
RUBRIC = "judge-v2.1-rubric-1"
CAPS = {"controls": 6, "rows": 18, "stability": 6}
STABILITY_INDICES = (1, 5, 6, 7, 9, 11)
LABEL_FIELDS = (
    "answer_match",
    "commitment",
    "citation_support",
    "citation_contradiction",
    "faithfulness",
)

# Generic clarification, no benchmark entities, values or expected labels injected.
INSTRUCTIONS = (
    JUDGE_V2_INSTRUCTIONS.replace(
        '(for example "you had just reached Premier Gold")', ""
    )
    + """

Scope clarification: 'I have no record of X' when the answer explicitly limits the
statement to the supplied items is an items-scoped absence report. Such a report
does not by itself assert a fact about the person, the world or all past history.
Descriptions of what topics these supplied items cover are also context reports.
An unqualified claim that something never happened or that the assistant never
said it is a different, assessable factual claim. Mixed answers that restate a
personal or world fact still make factual claims. Do not infer the claims flag
merely from whether the answer cites records.

Keep commitment as your model assessment; the host separately derives whether a
refusal rests on a contradicted premise from your evidence observations. An answer
that supplies a value with a caveat is not a refusal solely because it has a caveat.
Verify the premise of each absence assertion, including omissions and restatements.

Time clarification: observed_at is the observation time, not necessarily the fact's
effective time. Use explicit valid_from/valid_to, corrections, cancellations and
time descriptions in the text when available. A later observation of an earlier
fact does not automatically supersede a current fact. Neither newest-observation
wins nor a 'current' label is a general rule; retain ambiguity when warranted.
"""
)
SCHEMA = {**JUDGE_V2_SCHEMA, "title": "MemoryAnswerJudgeV21"}


def build_request(case: JudgeCase) -> StructuredGenerationRequest:
    request = v2_request(case)
    return request.model_copy(
        update={"instructions": INSTRUCTIONS, "output_schema": SCHEMA}
    )


def derive_label(case: JudgeCase, raw: Mapping[str, Any]) -> dict[str, Any]:
    label = v2_output(case, raw)
    entries, checks = label["citation_judgments"], label["absence_claim_checks"]
    if any(not e["text_hit"] for e in entries) or any(
        not c["claim_text_hit"] for c in checks
    ):
        raise JudgeV2Error("judge evidence quote is not anchored in its named source")
    base = label["commitment"]
    contradicted_absence = any(not c["true_for_supplied_context"] for c in checks)
    # These observations are model judgments, NOT deterministic semantic facts.
    escalate = base in {"refused_unavailable", "refused_conflicting_premise"} and (
        contradicted_absence or label["citation_contradiction"]
    )
    label["model_commitment"] = base
    label["commitment"] = "refused_conflicting_premise" if escalate else base
    label["commitment_basis"] = (
        "refusal-with-model-observed-contradicted-premise"
        if escalate
        else "model-assessment-unchanged"
    )
    label["false_absence_claims"] = sum(
        not c["true_for_supplied_context"] for c in checks
    )
    label["claims_scope_conflict"] = bool(
        label["answer_makes_factual_claims"]
        and checks
        and all(c["true_for_supplied_context"] for c in checks)
        and not case.cited_memory_ids
    )
    label["claims_scope_conflict_policy"] = "diagnostic-only-no-support-override"
    if label["citation_contradiction"] and label["citation_support"] == "supported":
        label["citation_support"] = "partially_supported"
        label["citation_support_basis"] = "model-observed-contradiction-caps-supported"
    return label


def control_gate(
    cases: Sequence[JudgeCase], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if len(cases) != 6 or len(rows) != 6 or len({r["case_key"] for r in rows}) != 6:
        raise JudgeV2Error("controls gate requires the exact six-control set")
    by_key = {row["case_key"]: row for row in rows}
    invalid, mismatched = [], []
    for case in cases:
        row = by_key.get(case.case_key)
        if row is None or row["judge"]["status"] != "completed":
            invalid.append(case.case_key)
            continue
        judge = row["judge"]
        if judge["request_sha256"] != _request_sha256(build_request(case)):
            raise JudgeV2Error("control report request binding changed")
        try:
            label = derive_label(case, judge["model_output"])
        except JudgeV2Error:
            invalid.append(case.case_key)
            continue
        if label != judge["label"]:
            raise JudgeV2Error(
                "control report label does not match its model observations"
            )
        if case.expected is None or any(
            label[key] != value for key, value in case.expected.items()
        ):
            mismatched.append(case.case_key)
    return {
        "passed": not invalid and len(mismatched) < 2,
        "invalid_controls": invalid,
        "mismatched_controls": mismatched,
        "rule": "all-six-valid-anchored; fewer-than-two-frozen-label-mismatches",
        "scope": "opened-development-controls-not-general-judge-validation",
    }


def require_gate(
    report: Mapping[str, Any],
    controls: Sequence[JudgeCase],
    config: OpenAICompatibleStructuredOutputConfig,
    controls_sha: str,
) -> None:
    expected = build_plan(
        controls,
        arm="controls",
        binding={"controls_sha256": controls_sha},
        config=config,
    )
    if (
        report.get("runner") != RUNNER
        or report.get("plan") != expected
        or report.get("status") != "complete"
    ):
        raise JudgeV2Error("matching complete v2.1 controls report required")
    if not control_gate(controls, report["rows"])["passed"]:
        raise JudgeV2Error(
            "controls gate failed; rows arm is not authorized by this plan"
        )


def build_plan(
    cases: Sequence[JudgeCase],
    *,
    arm: str,
    binding: Mapping[str, Any],
    config: OpenAICompatibleStructuredOutputConfig,
) -> dict[str, Any]:
    if arm not in CAPS or not cases or len(cases) != CAPS[arm]:
        raise JudgeV2Error("arm requires its fixed logical case count")
    if len({case.case_key for case in cases}) != len(cases):
        raise JudgeV2Error("arm case keys must be unique")
    payload = {
        "schema_version": "doppel.public-memory-answer-judge-v2.1-plan.v1",
        "arm": arm,
        "rubric_version": RUBRIC,
        "logical_cases": len(cases),
        "case_keys_sha256": _hash([c.case_key for c in cases]),
        "request_sha256s": [_request_sha256(build_request(c)) for c in cases],
        "input_binding": dict(binding),
        "provider_config": config.model_dump(mode="json"),
        "judge_instructions_sha256": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
        "judge_schema_sha256": _hash(SCHEMA),
        "max_new_judge_calls": CAPS[arm],
        "commitment_rule": "explicit-model-refusal-and-anchored-model-observed-contradiction-escalates; preserve-model-label",
        "claims_scope_flag": "diagnostic-only-no-automatic-not-applicable",
        "quote_policy": "single-record-normalized-text-anchor-not-semantic-proof; missing-anchor-fails-output",
        "gate_rule": "matching-controls-plan; all-six-valid; fewer-than-two-mismatches",
        "stability_indices": list(STABILITY_INDICES),
        "stability_transform": "reverse-cited-id-order-only; no-context-reference-or-answer-rewording",
    }
    return {**payload, "plan_fingerprint": _hash(payload)}


def stability_cases(
    cases: Sequence[JudgeCase],
    rows_report: Mapping[str, Any],
    config: OpenAICompatibleStructuredOutputConfig,
) -> list[JudgeCase]:
    plan = rows_report.get("plan", {})
    if (
        rows_report.get("runner") != RUNNER
        or rows_report.get("status") != "complete"
        or plan.get("arm") != "rows"
        or plan.get("provider_config") != config.model_dump(mode="json")
        or plan.get("request_sha256s")
        != [_request_sha256(build_request(c)) for c in cases]
        or plan.get("rubric_version") != RUBRIC
    ):
        raise JudgeV2Error("complete matching v2.1 rows report required for stability")
    if build_plan(
        cases, arm="rows", binding=plan["input_binding"], config=config
    ) != dict(plan):
        raise JudgeV2Error("stability baseline plan fingerprint changed")
    by_key = {r["case_key"]: r for r in rows_report["rows"]}
    selected = []
    for index in STABILITY_INDICES:
        case = next(c for c in cases if c.provenance["index"] == index)
        row = by_key.get(case.case_key)
        if (
            row is None
            or row["judge"]["status"] != "completed"
            or len(case.cited_memory_ids) < 2
        ):
            raise JudgeV2Error(
                "stability baseline missing or cannot change citation order"
            )
        baseline = derive_label(case, row["judge"]["model_output"])
        if baseline != row["judge"]["label"]:
            raise JudgeV2Error("stability baseline label changed")
        selected.append(
            replace(
                case,
                case_key=case.case_key + ":citation-order-reversed",
                arm="stability",
                cited_memory_ids=tuple(reversed(case.cited_memory_ids)),
                provenance={
                    **dict(case.provenance),
                    "baseline_case_key": case.case_key,
                    "baseline_labels": {key: baseline[key] for key in LABEL_FIELDS},
                },
            )
        )
    return selected


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = summarise_judgments(rows)
    labels = [r["judge"]["label"] for r in rows if r["judge"]["status"] == "completed"]
    applicable = sum(l["citation_support"] != "not_applicable" for l in labels)
    base.update(
        {
            "support_applicable_rows": applicable,
            "citation_supported_among_applicable": f"{base['citation_supported_successes']}/{applicable}",
            "claims_scope_conflict_rows": sum(
                l["claims_scope_conflict"] for l in labels
            ),
            "host_escalated_commitments": sum(
                l["model_commitment"] != l["commitment"] for l in labels
            ),
            "false_absence_claims": sum(l["false_absence_claims"] for l in labels),
        }
    )
    return base


async def run_arm(
    cases: Sequence[JudgeCase],
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    api_key: str,
    cache_only: bool,
    provider_factory: ProviderFactory,
) -> dict[str, Any]:
    config = OpenAICompatibleStructuredOutputConfig.model_validate(
        plan["provider_config"]
    )
    if build_plan(
        cases, arm=plan["arm"], binding=plan["input_binding"], config=config
    ) != dict(plan):
        raise JudgeV2Error("v2.1 plan/case payload changed before execution")
    _bind_json(run_dir / "plan.json", plan)
    usage_path = run_dir / "usage.sqlite3"
    budget_id = f"judge-v2.1-{plan['arm']}:" + plan["plan_fingerprint"]
    ledger = DurableCallLedger(
        usage_path, budget_id=budget_id, max_calls=CAPS[plan["arm"]]
    )
    before = ledger.report()["attempts_reserved"]
    stage = _StageExecutor(
        PilotStructuredModel(
            provider_factory(config, api_key, ledger.observe_usage),
            ledger=ledger,
            cache_dir=run_dir / "provider-cache",
            cache_only=cache_only,
        ),
        ledger,
        JudgeV2Output,
        cache_only=cache_only,
    )
    rows = []
    try:
        for case in cases:
            output, record = await stage.execute(build_request(case), len(rows))
            row: dict[str, Any] = {
                "case_key": case.case_key,
                "arm": plan["arm"],
                **dict(case.provenance),
                "abstained_consistent": None,
                "judge": {
                    **{k: v for k, v in record.items() if k != "first_row"},
                    "model_output": None,
                    "label": None,
                },
            }
            if output is not None:
                row["judge"]["model_output"] = output.model_dump(mode="json")
                try:
                    label = derive_label(case, row["judge"]["model_output"])
                except JudgeV2Error:
                    row["judge"].update(
                        status="failed",
                        failure_class="invalid_or_unanchored_judge_output",
                    )
                else:
                    row["judge"]["label"] = label
                    flag = case.provenance.get("reader_abstained_flag")
                    if flag is not None:
                        row["abstained_consistent"] = _abstained_consistency(
                            case, label["commitment"], flag
                        )
                    if case.expected is not None:
                        row["expected"] = dict(case.expected)
                        row["expected_matches"] = {
                            k: label[k] == v for k, v in case.expected.items()
                        }
            rows.append(row)
    finally:
        model_report = stage.model.report()
        records = _ledger_records(usage_path, budget_id)
        ledger.close()
    for row in rows:
        row["judge"]["attempts"] = [
            r for r in records if r["request_sha256"] == row["judge"]["request_sha256"]
        ]
    report = {
        "runner": RUNNER,
        "arm": plan["arm"],
        "status": "complete"
        if all(r["judge"]["status"] == "completed" for r in rows)
        else "partial",
        "mode": "live-cache-only-replay" if cache_only else "live-model",
        "plan": dict(plan),
        "logical_rows": len(rows),
        "execution_metadata": {
            **execution_metadata(),
            "judge_v21_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "judge_v2_source_sha256": hashlib.sha256(
                Path(__file__)
                .with_name("public_memory_answer_judge_v2.py")
                .read_bytes()
            ).hexdigest(),
        },
        "budget": {
            "new_judge_calls": model_report["ledger"]["attempts_reserved"] - before,
            "ledger": model_report["ledger"],
        },
        "cache": model_report,
        "metrics": summary(rows),
        "rows": rows,
        "reader_or_retrieval_executed": False,
        "store_writes": 0,
        "reference_answer_phrase_checks_used": False,
        "retrieval_or_packing_attribution_emitted": False,
        "model_observations_are_semantic_truth": False,
        "publication_ready": False,
        "aml_academic_model_compliant": False,
    }
    if plan["arm"] == "controls":
        report["gate"] = control_gate(cases, rows)
    if plan["arm"] == "rows":
        report["profile_summary"] = summarise_profiles(rows)
    if plan["arm"] == "stability":
        judged = [r for r in rows if r["judge"]["status"] == "completed"]
        report["label_agreement"] = {
            k: {
                "agree": sum(
                    r["judge"]["label"][k] == r["baseline_labels"][k] for r in judged
                ),
                "compared": len(judged),
                "different_indices": [
                    r["index"]
                    for r in judged
                    if r["judge"]["label"][k] != r["baseline_labels"][k]
                ],
            }
            for k in LABEL_FIELDS
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=tuple(CAPS), required=True)
    for name in (
        "report",
        "comparison",
        "dataset",
        "controls",
        "controls-report",
        "rows-report",
        "compare-audit",
    ):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve prior outputs; cache-only requires live mode")
    if not args.controls:
        parser.error("all arms require the fixed controls file")
    if args.compare_audit and (args.arm != "rows" or not args.live):
        parser.error("audit comparison is reporting-only after rows execution")
    config = OpenAICompatibleStructuredOutputConfig(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        schema_mode="json_object",
        strict_schema=False,
        timeout_seconds=120,
        max_completion_tokens=3072,
        max_tokens_parameter="max_tokens",
        temperature=0,
        thinking="disabled",
    )
    controls = load_controls(args.controls)
    controls_sha = hashlib.sha256(args.controls.read_bytes()).hexdigest()
    binding: dict[str, Any] = {"controls_sha256": controls_sha}
    if args.arm == "controls":
        cases = controls
    else:
        if not (
            args.report and args.comparison and args.dataset and args.controls_report
        ):
            parser.error(
                "rows/stability need original report, comparison, dataset and controls report"
            )
        gate_report, gate_sha = _load(args.controls_report)
        require_gate(gate_report, controls, config, controls_sha)
        cases, source_binding = build_preserved_cases(
            args.report, args.comparison, args.dataset
        )
        binding.update(source_binding)
        binding["controls_report_sha256"] = gate_sha
        if args.arm == "stability":
            if not args.rows_report:
                parser.error("stability needs complete rows report")
            rows_report, rows_sha = _load(args.rows_report)
            if rows_report.get("plan") != build_plan(
                cases, arm="rows", binding=binding, config=config
            ):
                raise JudgeV2Error(
                    "stability baseline is not bound to these inputs and control report"
                )
            cases = stability_cases(cases, rows_report, config)
            binding["rows_report_sha256"] = rows_sha
    plan = build_plan(cases, arm=args.arm, binding=binding, config=config)
    # Preflight validates bindings without creating a ledger or reading a key.
    if not args.live:
        report = {
            "runner": RUNNER,
            "arm": args.arm,
            "status": "ready",
            "mode": "preflight-no-provider",
            "plan": plan,
            "distinct_requests": len(set(plan["request_sha256s"])),
            "api_key_read": False,
            "judge_calls_this_invocation": 0,
            "publication_ready": False,
        }
    else:
        api_key = (
            "" if args.cache_only else os.environ.get(args.api_key_env, "").strip()
        )
        if not args.cache_only and not api_key:
            parser.error("API key environment variable is absent")
        try:
            report = asyncio.run(
                run_arm(
                    cases,
                    plan,
                    run_dir=args.run_dir,
                    api_key=api_key,
                    cache_only=args.cache_only,
                    provider_factory=_default_provider_factory,
                )
            )
        except Exception as error:  # noqa: BLE001 - do not expose provider/key text
            report = {
                "runner": RUNNER,
                "arm": args.arm,
                "status": "failed",
                "mode": "failed-execution",
                "failure_type": type(error).__name__,
                "plan": plan,
                "budget": {
                    "new_judge_calls": None,
                    "accounting": "inspect-durable-ledger; not-assumed-zero",
                },
                "publication_ready": False,
            }
        report["api_key_read"] = not args.cache_only
    if args.compare_audit and report["status"] in {"complete", "partial"}:
        report["audit_comparison"] = compare_with_audit(report, args.compare_audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {hashlib.sha256(args.output.read_bytes()).hexdigest()}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "arm": report["arm"],
                "new_calls": report.get("budget", {}).get("new_judge_calls", 0),
                "gate": report.get("gate"),
            }
        )
    )
    return (
        0
        if report["status"] in {"ready", "complete"}
        and report.get("gate", {}).get("passed", True)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

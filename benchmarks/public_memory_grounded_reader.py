"""Generic grounded Reader policy, controls before an opened paired diagnosis.

No core/default switch or retrieval work. Synthetic rubrics and public references
never enter Reader requests; semantic control review remains explicitly manual.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

from benchmarks import public_memory_official_scoring as pinned
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_answer_comparison import (
    AnswerRow,
    _default_provider_factory,
)
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_oracle_diagnostic import balance, prepare_rows
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_prompt_regrade import (
    DeepSeekPromptJudge,
    verdict,
)
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_response_policy import ADVICE_INSTRUCTIONS, paired_rows
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel

RUNNER = "doppel.public-memory-grounded-reader.v2"
POLICIES = ("grounded_advice_v1", "grounded_advice_v2")
DEFAULT_CONTROLS = Path("benchmarks/datasets/reader-grounded-policy-controls-v1.json")
INSTRUCTIONS = (
    ADVICE_INSTRUCTIONS
    + """

Status-preserving grounding: Preserve the source's modality and completion status
in every personal-history claim, including introductory personalization. Intent,
interest, a proposal, a prediction or a plan is not evidence of an action occurring.
An elapsed planned date is not proof of completion. Describe those premises as
planned or intended unless supplied evidence establishes completion. Conversely,
use explicit completion evidence when present; do not remain uncertain merely
because an earlier item described a plan. General recommendations may be new,
but must be identified as suggestions, not recalled conduct or past experience.

Inference calibration: Read the ordinary meaning of connected statements rather
than requiring an exact phrase, synonym or causal formula. Accept conclusions
directly supported by explicit links, unambiguous referents, paraphrases and
straightforward arithmetic. Distinguish these from plausible guesses: proximity,
similarity or co-occurrence alone does not establish causation, identity, ownership
or completion. Do not add unprovided premises. Explain a real uncertainty without
using arbitrary wording distinctions to discard information that is supported.
For a derived answer, cite every input and use the existing derived block. State
one coherent conclusion; caveats must not contradict the conclusion or citations.

Final consistency check before returning JSON: check ALL supplied items and your
citations for the claimed status and inputs. Confirm that a suggested action has
not been described as a past action, that an absence claim is limited to supplied
evidence, and that abstained agrees with whether you supplied the requested result.
Write the entire answer and derived.result in the question's language, regardless
of the source language; retain names and exact citation IDs without translation.
These are mandatory response rules, not guarantees independently enforced by code.
"""
)


def reader_request(row, policy):
    if policy not in POLICIES:
        raise ValueError("unknown frozen policy")
    return build_request(row).model_copy(
        update={
            "instructions": ADVICE_INSTRUCTIONS
            if policy == POLICIES[0]
            else INSTRUCTIONS
        }
    )


def control_rows(dataset):
    if dataset.get("schema") != "doppel.reader-grounded-policy-controls.v1":
        raise ValueError("unknown controls schema")
    result, seen = [], set()
    for index, case in enumerate(dataset["cases"]):
        if (
            case["id"] in seen
            or not case["items"]
            or not case["rubric"].strip()
            or any(
                item["role"] not in {"user", "assistant"} or not item["text"].strip()
                for item in case["items"]
            )
        ):
            raise ValueError("unique nonempty frozen controls required")
        seen.add(case["id"])
        prepared = prepare_case(
            {
                "question_id": case["id"],
                "question_type": "single-session-user",
                "question": case["question"],
                "answer": "unused-scoring-only",
                "question_date": dataset["question_reference_time"],
                "haystack_session_ids": ["control-session"],
                "haystack_dates": ["2026-08-01T00:00:00Z"],
                "haystack_sessions": [
                    [
                        {"role": item["role"], "content": item["text"]}
                        for item in case["items"]
                    ]
                ],
                "answer_session_ids": ["control-session"],
            },
            dataset_namespace="synthetic-grounded-policy-controls",
        )
        context = tuple(
            {
                "memory_id": f"{case['id']}-item-{n}",
                "channel": "raw",
                "role": item["role"],
                "authority": "human_self" if item["role"] == "user" else "agent_output",
                "text": item["text"],
                "observed_at": item.get("observed_at", "2026-08-01T00:00:00Z"),
                "temporal_status": None,
                "valid_from": None,
                "valid_to": None,
            }
            for n, item in enumerate(case["items"])
        )
        result.append(
            AnswerRow(
                index,
                case["id"],
                "synthetic-control",
                prepared.runtime,
                prepared.scoring,
                context,
            )
        )
    return result


def review_controls(report, dataset, review):
    """Quote anchoring verifies provenance, NOT the truth of semantic decisions."""
    if (
        report.get("runner") != RUNNER
        or report["plan"].get("runner") != RUNNER
        or _hash({k: v for k, v in report["plan"].items() if k != "plan_fingerprint"})
        != report["plan"]["plan_fingerprint"]
        or report.get("status") != "complete"
        or report["plan"]["phase"] != "controls"
        or review.get("reviewer") != "codex-manual"
        or review.get("independent_review") is not False
        or review.get("result_sha256") != _hash(report)
    ):
        raise ValueError(
            "complete bound control report and disclosed manual review required"
        )
    cases = {r.case_id: r for r in control_rows(dataset)}
    outputs = {(r["case_id"], r["policy"]): r for r in report["rows"]}
    if len(outputs) != len(report["rows"]) or len(outputs) != 2 * len(cases):
        raise ValueError("all unique control results required")
    seen, decisions = set(), review["decisions"]
    for decision in decisions:
        identity = (decision["case_id"], decision["policy"])
        if (
            identity in seen
            or identity not in outputs
            or type(decision["passes_rubric"]) is not bool
        ):
            raise ValueError("unique review decisions required")
        seen.add(identity)
        row = outputs[identity]
        if row["status"] != "complete" or not decision["rationale"].strip():
            raise ValueError("complete justified review required")
        if not decision["answer_quotes"] or not decision["source_quotes"]:
            raise ValueError("answer/source anchors required")
        for quote in decision["answer_quotes"]:
            if not quote.strip() or quote not in row["reader"]["answer"]:
                raise ValueError("answer quote not grounded")
        sources = {i["memory_id"]: i["text"] for i in cases[identity[0]].context}
        for source in decision["source_quotes"]:
            if (
                not source["quote"].strip()
                or source["quote"] not in sources[source["memory_id"]]
            ):
                raise ValueError("source quote not grounded")
    if seen != {(c, p) for c in cases for p in POLICIES}:
        raise ValueError("all controls in both arms must be reviewed")
    candidate = [d for d in decisions if d["policy"] == POLICIES[1]]
    return {
        "candidate_passes": sum(d["passes_rubric"] for d in candidate),
        "candidate_count": len(candidate),
        "ok": all(
            d["passes_rubric"]
            and outputs[(d["case_id"], d["policy"])]["checks"]["structurally_valid"]
            for d in candidate
        ),
        "independent_review": False,
        "quote_anchoring_proves_semantics": False,
    }


def build_plan(rows, bindings, phase):
    requests = [reader_request(r, p) for r in rows for p in POLICIES]
    sizes = [len(r.model_dump_json().encode()) for r in requests]
    if any(size > 100_000 for size in sizes):
        raise ValueError("oversize request; no silent truncation")
    plan = {
        "runner": RUNNER,
        "phase": phase,
        "input_sha256": bindings,
        "row_identities": [[r.case_id, r.profile] for r in rows],
        "policies": list(POLICIES),
        "reader_request_sha256": [_hash(r.model_dump(mode="json")) for r in requests],
        "reader_config": config(2048).model_dump(mode="json"),
        "max_reader_calls": len(requests),
        "max_judge_calls": 0 if phase == "controls" else len(requests),
        "balance_stop_cny": 1,
        "failure_policy": "stop, preserve; no automatic retry",
        "control_gate": "all candidate manual rubrics and structural checks pass; baseline reviewed but not required to pass",
        "question_specific_product_rules": False,
        "reader_gold_or_rubric": False,
        "core_default_changed": False,
        "new_retrieval_graph_calls": 0,
        "official_longmemeval_metric": False,
        "publication_ready": False,
        "source_sha256": {
            str(p.resolve().relative_to(Path(__file__).parent.parent)): hashlib.sha256(
                p.read_text(encoding="utf-8").encode()
            ).hexdigest()
            for p in (
                Path(__file__),
                Path("benchmarks/public_memory_response_policy.py"),
                Path("benchmarks/public_memory_reader_v2.py"),
                Path("benchmarks/public_memory_answer_comparison.py"),
                Path("benchmarks/public_memory_runtime.py"),
                Path("benchmarks/public_memory_high_config_first.py"),
                Path("benchmarks/public_memory_prompt_regrade.py"),
                Path("benchmarks/public_memory_official_scoring.py"),
                Path("benchmarks/public_memory_oracle_diagnostic.py"),
                Path("benchmarks/public_memory_expansion.py"),
            )
        },
    }
    plan["plan_fingerprint"] = _hash(plan)
    return plan


async def execute(
    args,
    rows,
    plan,
    *,
    provider_factory=_default_provider_factory,
    balance_reader=balance,
    judge_transport=None,
):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("DEEPSEEK_API_KEY missing")
    _bind_json(args.run_dir / "plan.json", plan)
    initial = None if args.cache_only else await balance_reader(key)
    if not args.cache_only:
        initial_path = args.run_dir / "balance-start.json"
        if not initial_path.exists():
            save(initial_path, {"initial_cny": initial})
        initial = json.loads(initial_path.read_text(encoding="utf-8"))["initial_cny"]
    models, ledgers, results, stopped, final_balance = {}, {}, [], "", None
    try:
        for stage in ("reader", "judge"):
            cap = plan["max_" + stage + "_calls"]
            if not cap:
                continue
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=cap,
                max_request_bytes=100_000,
                max_total_request_bytes=100_000 * cap,
            )
            ledgers[stage] = ledger
            provider = (
                provider_factory(config(2048), key, ledger.observe_usage)
                if stage == "reader"
                else DeepSeekPromptJudge(key, ledger, transport=judge_transport)
            )
            models[stage] = PilotStructuredModel(
                provider,
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        for index, row in enumerate(rows):
            for policy in POLICIES if index % 2 == 0 else POLICIES[::-1]:
                item = {
                    "case_id": row.case_id,
                    "context_profile": row.profile,
                    "policy": policy,
                    "status": "failed",
                }
                try:
                    for stage, model in models.items():
                        if not args.cache_only:
                            final_balance = await balance_reader(key)
                            if (
                                final_balance <= 0
                                or initial - final_balance >= plan["balance_stop_cny"]
                            ):
                                stopped, item["status"] = (
                                    "observed_balance_stop",
                                    "budget_stopped",
                                )
                                break
                        path = (
                            args.run_dir
                            / "receipts"
                            / f"row-{index:02d}-{policy}-{stage}.json"
                        )
                        if stage == "reader":
                            output = await persisted_generation(
                                model, reader_request(row, policy), ReaderV2Output, path
                            )
                            item.update(
                                reader=output.model_dump(mode="json"),
                                checks=structural_check(row, output),
                            )
                            if not item["checks"]["structurally_valid"]:
                                stopped = "invalid_citation_or_derivation_no_retry"
                                break
                        else:
                            prompt = pinned.official_prompt(
                                row.scoring.category,
                                row.runtime.query.query,
                                row.scoring.answer,
                                item["reader"]["answer"],
                                abstention=row.scoring.abstention,
                            )
                            raw = await persisted_generation(
                                model,
                                pinned.request_for({"prompt": prompt}),
                                pinned.OfficialOutput,
                                path,
                            )
                            item["grade"] = verdict(raw)
                            if (
                                not item["grade"]["strict_yes_no_valid"]
                                or not item["grade"]["clean_completion"]
                            ):
                                stopped = "invalid_verdict_no_retry"
                                break
                    if not stopped:
                        item["status"] = "complete"
                except Exception as error:  # noqa: BLE001 - no provider/key text
                    item["failure_type"] = type(error).__name__
                    stopped = "preserved_stage_or_balance_failure_no_retry"
                results.append(item)
                print(f"{row.case_id} {policy}: {item['status']}", flush=True)
                if stopped:
                    break
            if stopped:
                break
        if not args.cache_only:
            try:
                final_balance = await balance_reader(key)
            except Exception:  # noqa: BLE001 - unknown usage stays unknown
                final_balance = None
        return {
            "status": "complete"
            if len(results) == 2 * len(rows) and not stopped
            else "stopped",
            "rows": results,
            "stopped_reason": stopped,
            "usage": {s: m.report() for s, m in models.items()},
            "semantic_control_review": "not_automatically_measured",
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": final_balance,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()


async def run(args):
    controls_content = args.controls.read_bytes()
    dataset = json.loads(controls_content)
    bindings = {"controls": hashlib.sha256(controls_content).hexdigest()}
    if args.phase == "controls":
        rows = control_rows(dataset)
    else:
        if not args.control_result or not args.control_review:
            raise ValueError("paired phase requires bound completed control review")
        for name in (
            "control_result",
            "control_review",
            "source",
            "oracle",
            "manifest",
            "comparison",
            "quality",
        ):
            content = getattr(args, name).read_bytes()
            bindings[name] = hashlib.sha256(content).hexdigest()
        result = json.loads(args.control_result.read_text(encoding="utf-8"))
        if result["plan"] != build_plan(
            control_rows(dataset), {"controls": bindings["controls"]}, "controls"
        ):
            raise ValueError("control data/code/requests changed")
        gate = review_controls(
            result, dataset, json.loads(args.control_review.read_text(encoding="utf-8"))
        )
        if not gate["ok"]:
            raise ValueError("candidate semantic control gate did not pass")
        data = {
            n: json.loads(getattr(args, n).read_text(encoding="utf-8"))
            for n in ("source", "oracle", "manifest", "comparison", "quality")
        }
        protected = set()
        for path in args.prior_manifest:
            content = path.read_bytes()
            prior = json.loads(content)
            if prior["source_sha256"] != bindings["source"]:
                raise ValueError("reserved source mismatch")
            bindings[str(path)] = hashlib.sha256(content).hexdigest()
            protected.update(
                r["case_id"] for r in prior["cases"] if r["partition"] == "reserved"
            )
        rows = paired_rows(
            prepare_rows(data["source"], data["oracle"], data["manifest"], protected),
            data["comparison"],
            data["quality"],
            bindings,
        )
        if [r.case_id for r in rows[::2]] != list(pinned.COHORT):
            raise ValueError("same seven opened cases required")
        rows = [replace(r, index=i) for i, r in enumerate(rows)]
    plan = build_plan(rows, bindings, args.phase)
    report = {
        "runner": RUNNER,
        "plan": plan,
        "status": "ready",
        "official_longmemeval_metric": False,
        "publication_ready": False,
        "record_or_index_writes": 0,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_text(encoding="utf-8"))["plan"]
            != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("controls", "paired"))
    parser.add_argument("--controls", type=Path, default=DEFAULT_CONTROLS)
    for name, default in {
        "source": "data/public-benchmarks/longmemeval_s_cleaned.json",
        "oracle": "data/public-benchmarks/longmemeval_oracle.json",
        "manifest": "data/doppel/longmemeval-expansion-50-manifest-v1.json",
        "comparison": "data/doppel/longmemeval-expansion-50-memory-comparison-v2.json",
        "quality": "data/doppel/longmemeval-expansion-50-quality-v1.json",
    }.items():
        parser.add_argument("--" + name, type=Path, default=Path(default))
    parser.add_argument(
        "--prior-manifest",
        type=Path,
        action="append",
        default=[
            Path("data/doppel/longmemeval-expansion-10-manifest-v1.json"),
            Path("data/doppel/longmemeval-local-pilot-manifest-v1.json"),
        ],
    )
    for name in ("run-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("control-result", "control-review", "frozen-preflight"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve old outputs; cache-only requires live")
    report = asyncio.run(run(args))
    save(args.output, report)
    print(json.dumps({"status": report["status"], "rows": len(report.get("rows", []))}))
    return 0 if report["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline fixed-top20 budget curve; no retrieval, models, DB or QA rescoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

BUDGETS = (24000, 48000, 96000)
WIDTHS = ("80", "160")
INPUTS = {
    "window-ablation-live-v1.json": "d43c29bde9ce4a4d392db97e0e464aea1ce6177f7bfbdf64c03bfbbe4f61c906",
    "window-ablation-plan-v1.json": "f45b41b7f146bd1bcba90103fe40b026b4d8ac1a036d9191d02031b271f95c0d",
    "uniform-qa-fifty-summary-v1.json": "a5ecbc7c038a072eb69e73d5024fd53f3ec92800a5aec8c1bbeedd95c7ad8408",
}


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def pack(items, byte_limit):
    """Same whole-item ranked-fit policy; only its byte cap varies.

    Selection receives no question, annotation, task label or preferred role.
    A larger cap need not retain every previously selected item.
    """
    if type(byte_limit) is not int or byte_limit < 2:
        raise ValueError("byte limit must be an integer >= empty JSON list size")
    packed, selected, skipped = [], [], []
    considered = 0
    for rank, item in enumerate(items[:80], start=1):
        if len(packed) == 20:
            break
        considered += 1
        trial = [*packed, dict(item)]
        if len(encode(trial)) > byte_limit:
            skipped.append(rank)
        else:
            packed = trial
            selected.append(rank)
    return packed, {
        "considered_candidates": considered,
        "selected_rank_positions": selected,
        "over_budget_rank_positions": skipped,
        "text_modified": False,
        "source_expansion_executed": False,
    }


def validate_arm(arm, width):
    top = arm["top20"]
    ids = [item["memory_id"] for item in top]
    candidates = arm["candidate_ids"]
    if (
        len(top) != 20
        or len(set(ids)) != 20
        or len({item["scope_key"] for item in top}) != 1
        or len(candidates) != int(width)
        or len(set(candidates)) != len(candidates)
        or not set(ids) <= set(candidates)
    ):
        raise ValueError("invalid ordered candidate/source identities or scope")
    annotated = arm["annotated"]
    previous = set(candidates)
    if type(annotated) is not int or annotated < 0:
        raise ValueError("invalid annotation denominator")
    for field in (
        "candidate_annotated_ids",
        "top20_annotated_ids",
        "packed_annotated_ids",
    ):
        values = arm[field]
        if len(values) != len(set(values)) or not set(values) <= previous:
            raise ValueError("invalid annotation stage binding")
        previous = set(values)
    if len(arm["candidate_annotated_ids"]) > annotated:
        raise ValueError("annotations exceed denominator")
    if set(arm["top20_annotated_ids"]) != set(ids) & set(
        arm["candidate_annotated_ids"]
    ):
        raise ValueError("top20 annotation binding differs")
    packed, trace = pack(top, BUDGETS[0])
    packed_ids = {item["memory_id"] for item in packed}
    if (
        packed != arm["context"]
        or trace != arm["packing_trace"]
        or sha(encode(packed)) != arm["context_sha256"]
        or len(packed) != arm["packed_items"]
        or len(encode(packed)) != arm["context_bytes"]
        or packed_ids & set(arm["top20_annotated_ids"])
        != set(arm["packed_annotated_ids"])
    ):
        raise ValueError("24KB historical packing reproduction failed")


def summarize(rows):
    result = {}
    positives = [row for row in rows if not row["abstention_label"]]
    for width in WIDTHS:
        denominator = sum(row["annotated"] for row in positives)
        ceiling = sum(row["top20_ceiling"][width] for row in positives)
        values = {}
        for budget in BUDGETS:
            arms = [row["arms"][width][str(budget)] for row in positives]
            all_arms = [row["arms"][width][str(budget)] for row in rows]
            hits = sum(len(arm["annotated_ids"]) for arm in arms)
            values[str(budget)] = {
                "positive_questions": len(positives),
                "annotated": denominator,
                "packed_annotations": hits,
                "annotation_recall": hits / denominator if denominator else None,
                "complete_positive_questions": sum(
                    len(arm["annotated_ids"]) == row["annotated"]
                    for row, arm in zip(positives, arms, strict=True)
                ),
                "top20_annotation_ceiling": ceiling,
                "top20_annotations_still_unpacked": ceiling - hits,
                "annotations_outside_top20": denominator - ceiling,
                "all_case_items": sum(len(arm["selected_ids"]) for arm in all_arms),
                "all_case_bytes": sum(arm["context_bytes"] for arm in all_arms),
                "all_case_max_bytes": max(arm["context_bytes"] for arm in all_arms),
                "all20_fit_cases": sum(
                    len(arm["selected_ids"]) == 20 for arm in all_arms
                ),
            }
        paired = {}
        for budget in BUDGETS[1:]:
            pairs = [
                (
                    set(row["arms"][width]["24000"]["annotated_ids"]),
                    set(row["arms"][width][str(budget)]["annotated_ids"]),
                )
                for row in positives
            ]
            paired[str(budget)] = {
                "recovered_annotations": sum(len(b - a) for a, b in pairs),
                "displaced_annotations": sum(len(a - b) for a, b in pairs),
                "gain_questions": sum(len(b) > len(a) for a, b in pairs),
                "loss_questions": sum(len(b) < len(a) for a, b in pairs),
            }
        result[width] = {"budgets": values, "paired_vs_24000": paired}
    return result


def replay(source):
    rows = source["rows"]
    if (
        source["status"] != "complete"
        or source["failure"] is not None
        or len(rows) != 50
        or {row["ordinal"] for row in rows} != set(range(1, 51))
        or len({row["case_id"] for row in rows}) != 50
    ):
        raise ValueError("complete unique opened50 required")
    output = []
    for row in sorted(rows, key=lambda r: r["ordinal"]):
        record = {
            "ordinal": row["ordinal"],
            "case_id": row["case_id"],
            "abstention_label": row["abstention_label"],
            "annotated": row["arms"]["80"]["annotated"],
            "top20_ceiling": {},
            "arms": {},
        }
        for width in WIDTHS:
            arm = row["arms"][width]
            validate_arm(arm, width)
            if arm["annotated"] != record["annotated"]:
                raise ValueError("arm annotation denominators differ")
            if row["abstention_label"] and arm["annotated"] != 0:
                raise ValueError(
                    "negative annotations must not enter positive denominator"
                )
            gold = set(arm["top20_annotated_ids"])
            record["top20_ceiling"][width] = len(gold)
            record["arms"][width] = {}
            for budget in BUDGETS:
                packed, trace = pack(arm["top20"], budget)
                ids = [item["memory_id"] for item in packed]
                record["arms"][width][str(budget)] = {
                    "selected_ids": ids,
                    "annotated_ids": [identity for identity in ids if identity in gold],
                    "context_bytes": len(encode(packed)),
                    "context_sha256": sha(encode(packed)),
                    "trace": trace,
                }
        output.append(record)
    return {"rows": output, "summary": summarize(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/doppel"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/doppel/context-budget-curve-v1.json")
    )
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite an existing report")
    snapshots = {name: (args.data_dir / name).read_bytes() for name in INPUTS}
    if {name: sha(value) for name, value in snapshots.items()} != INPUTS:
        raise ValueError("frozen input file hash mismatch")
    source, plan, qa = [json.loads(value) for value in snapshots.values()]
    fingerprint = dict(plan)
    expected = fingerprint.pop("plan_fingerprint")
    if (
        sha(
            json.dumps(
                fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        != expected
        or source["plan"] != plan
        or plan["binding"]["summary"] != INPUTS["uniform-qa-fifty-summary-v1.json"]
    ):
        raise ValueError("frozen plan binding mismatch")
    old = {row["ordinal"]: row for row in qa["rows"]}
    for row in source["rows"]:
        prior = old[row["ordinal"]]
        if (
            any(row[key] != prior[key] for key in ("case_id", "abstention_label"))
            or row["arms"]["80"]["context_sha256"] != prior["context_sha256"]
        ):
            raise ValueError("historical QA context binding mismatch")
    report = {
        "runner": "doppel.context-budget-curve.v1",
        "input_sha256": INPUTS,
        "implementation_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "code_sha256": sha(Path(__file__).read_bytes()),
        "budgets_utf8_json_bytes": list(BUDGETS),
        "policy": "fixed ordered top20; whole-item ranked-fit; budget-only resource comparison",
        **replay(source),
        "paid_calls": 0,
        "model_calls": 0,
        "retrieval_calls": 0,
        "source_writes": 0,
        "qa_metrics_available": False,
        "opened_development_not_blind": True,
        "publication_ready": False,
        "official_longmemeval_score": False,
        "aml_score": False,
    }
    if any(
        (args.data_dir / name).read_bytes() != value
        for name, value in snapshots.items()
    ):
        raise ValueError("input changed during replay")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")
    print(f"output: {args.output.resolve()}")
    print(f"sha256: {sha(args.output.read_bytes())}")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

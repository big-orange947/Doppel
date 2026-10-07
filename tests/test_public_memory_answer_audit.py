"""Synthetic audit boundaries; no model, network or benchmark-score claim."""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from benchmarks.public_memory_answer_audit import (
    AuditToolError,
    build_packet,
    main,
    validate_decisions,
)
from tests.test_public_memory_answer_comparison import (
    RecordingFactory,
    default_responder,
    live,
    setup,
)


async def report_fixture(tmp_path: Path) -> tuple[Any, Path, dict[str, Any]]:
    fx, rows, plan = setup(tmp_path)
    report = await live(
        fx, rows, plan, RecordingFactory(default_responder), run_dir=tmp_path / "run"
    )
    report["input_sha256"] = {
        "dataset": hashlib.sha256(fx.dataset_path.read_bytes()).hexdigest(),
        "manifest": hashlib.sha256(fx.manifest_path.read_bytes()).hexdigest(),
        "comparison": fx.comparison_sha256,
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return fx, path, report


def packet_for(tmp_path: Path, fx: Any, report_path: Path) -> dict[str, Any]:
    return build_packet(report_path, fx.comparison_path, fx.dataset_path)


def decisions_for(packet: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = []
    for row in packet["rows"]:
        answer = row["reader"]["answer"]
        decisions.append(
            {
                "row": row["index"],
                "answer_match": (
                    "correct" if row["old_judge"]["answer_correct"] else "incorrect"
                ),
                "commitment": "committed",
                "citation_support": (
                    "supported"
                    if row["old_judge"]["citation_supported"]
                    else "not_applicable"
                ),
                "citation_contradiction": False,
                "faithfulness": "grounded",
                "abstained_expected": bool(row["reader"]["abstained"]),
                "abstained_consistent": True,
                "attributions": [],
                "rationale": "synthetic audit reason",
                "quotes": [{"text": answer[:24], "source": "answer"}],
                "context_checks": [],
            }
        )
    return decisions


async def test_packet_binds_to_the_reported_inputs(tmp_path: Path) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    assert packet["audit_schema"] == "doppel.public-memory-answer-audit.v1"
    assert packet["source_sha256"]["comparison"] == fx.comparison_sha256
    assert packet["binding"]["logical_rows"] == 18
    assert packet["mode"].startswith("deterministic")

    broken = deepcopy(json.loads(report_path.read_text(encoding="utf-8")))
    broken["input_sha256"]["comparison"] = "0" * 64
    altered = tmp_path / "altered.json"
    altered.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(AuditToolError, match="comparison"):
        build_packet(altered, fx.comparison_path, fx.dataset_path)

    broken_dataset = deepcopy(json.loads(report_path.read_text(encoding="utf-8")))
    broken_dataset["input_sha256"]["dataset"] = "0" * 64
    altered_dataset = tmp_path / "altered-dataset.json"
    altered_dataset.write_text(
        json.dumps(broken_dataset, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(AuditToolError, match="dataset"):
        build_packet(altered_dataset, fx.comparison_path, fx.dataset_path)


async def test_packet_rows_resolve_questions_citations_and_terms(
    tmp_path: Path,
) -> None:
    fx, report_path, report = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    by_key = {(row["case_id"], row["profile"]): row for row in report["rows"]}
    sources = {record["question_id"]: record for record in fx.records}
    for row in packet["rows"]:
        source = by_key[(row["case_id"], row["profile"])]
        dataset_case = sources[row["case_id"]]
        assert row["question"] == dataset_case["question"]
        assert row["reference_answer"] == dataset_case["answer"]
        assert [item["memory_id"] for item in row["cited_items"]] == list(
            source["reader"]["cited_memory_ids"]
        )
        assert row["reader"]["answer"] == source["reader"]["answer"]
        assert row["old_judge"]["answer_correct"] == source["judge"]["answer_correct"]
        assert row["reference_terms"]
        assert all(
            item["memory_id"] in {entry["memory_id"] for entry in row["context_items"]}
            for item in row["cited_items"]
        )


async def test_valid_decisions_pass_and_report_disagreements(
    tmp_path: Path,
) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    decisions = decisions_for(packet)
    decisions[0]["answer_match"] = (
        "incorrect" if decisions[0]["answer_match"] == "correct" else "correct"
    )
    result = validate_decisions(packet, decisions)
    assert result["rows_validated"] == 18
    assert [row["row"] for row in result["disagreements_with_old_judge"]] == [0]
    assert (
        result["counts"]["answer_match"]["correct"]
        + result["counts"]["answer_match"]["incorrect"]
        == 18
    )


async def test_missing_and_duplicate_rows_are_rejected(tmp_path: Path) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    decisions = decisions_for(packet)
    with pytest.raises(AuditToolError, match="without a decision"):
        validate_decisions(packet, decisions[:-1])
    duplicated = decisions + [deepcopy(decisions[0])]
    with pytest.raises(AuditToolError, match="duplicate decision"):
        validate_decisions(packet, duplicated)


async def test_unaligned_and_ungrounded_audit_reasons_are_rejected(
    tmp_path: Path,
) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    decisions = decisions_for(packet)

    ungrounded = deepcopy(decisions)
    ungrounded[3]["quotes"] = [
        {"text": "THIS TEXT IS NOT IN THE ROW", "source": "answer"}
    ]
    with pytest.raises(AuditToolError, match="quote not found"):
        validate_decisions(packet, ungrounded)

    failed_check = deepcopy(decisions)
    failed_check[5]["context_checks"] = [
        {"term": "TOTALLY ABSENT", "expected": "present", "scope": "row_context"}
    ]
    with pytest.raises(AuditToolError, match="check failed"):
        validate_decisions(packet, failed_check)

    inconsistent = deepcopy(decisions)
    inconsistent[2]["abstained_expected"] = not inconsistent[2]["abstained_expected"]
    inconsistent[2]["abstained_consistent"] = True
    with pytest.raises(AuditToolError, match="abstained consistency"):
        validate_decisions(packet, inconsistent)


async def test_closed_labels_and_required_quotes_are_enforced(tmp_path: Path) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet = packet_for(tmp_path, fx, report_path)
    decisions = decisions_for(packet)

    unknown = deepcopy(decisions)
    unknown[0]["attributions"] = ["made_up_label"]
    with pytest.raises(AuditToolError, match="schema invalid"):
        validate_decisions(packet, unknown)

    no_quote = deepcopy(decisions)
    no_quote[0]["quotes"] = []
    with pytest.raises(AuditToolError, match="schema invalid"):
        validate_decisions(packet, no_quote)

    blank_reason = deepcopy(decisions)
    blank_reason[1]["rationale"] = "   "
    with pytest.raises(AuditToolError, match="schema invalid"):
        validate_decisions(packet, blank_reason)


async def test_cli_writes_packet_and_validation_and_refuses_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fx, report_path, _ = await report_fixture(tmp_path)
    packet_path = tmp_path / "packet.json"
    decisions_path = tmp_path / "decisions.json"
    validation_path = tmp_path / "validation.json"
    argv = [
        "public_memory_answer_audit",
        "--report",
        str(report_path),
        "--comparison",
        str(fx.comparison_path),
        "--dataset",
        str(fx.dataset_path),
        "--packet-out",
        str(packet_path),
        "--decisions",
        str(decisions_path),
        "--validation-out",
        str(validation_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    packet = build_packet(report_path, fx.comparison_path, fx.dataset_path)
    decisions_path.write_text(
        json.dumps(decisions_for(packet), ensure_ascii=False), encoding="utf-8"
    )
    assert main() == 0
    written_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert written_packet["binding"]["logical_rows"] == 18
    assert validation["rows_validated"] == 18
    assert "packet:" in capsys.readouterr().out
    with pytest.raises(AuditToolError, match="output exists"):
        main()

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from benchmarks import relation_catalog_ablation as paired
from benchmarks.personal_retrieval_ablation import load_ablation_dataset
from benchmarks.planner_semantic_review import review_planner_report
from benchmarks.relation_planner_quality import run_relation_planner_quality
from doppel_memory import PersonalMemoryQueryDraft, RelationTypeDefinition


class _Planner:
    name = "test.paired-planner"
    version = "1"

    async def plan(self, request: Any) -> PersonalMemoryQueryDraft:
        return PersonalMemoryQueryDraft(subject_id=request.default_subject_id)


@pytest.fixture
def pair_setup(monkeypatch: Any) -> list[Any]:
    captured = []
    monkeypatch.setenv("DOPPEL_API_KEY", "test-key-not-for-network")
    monkeypatch.setattr(paired, "_input_identity", lambda: {"source": "fixed"})

    async def fake_arm(args: Any) -> int:
        captured.append(args)
        dataset = load_ablation_dataset(args.dataset)
        definitions = (
            TypeAdapter(list[RelationTypeDefinition]).validate_json(
                args.relation_catalog.read_bytes()
            )
            if args.relation_catalog
            else []
        )
        report = await run_relation_planner_quality(
            dataset, _Planner(), relation_type_definitions=definitions
        )
        report["semantic_review"] = review_planner_report(
            report, dataset, args.semantic_review
        )
        args.output.write_text(json.dumps(report), encoding="utf-8")
        return 1  # Ordinary quality failure, not a reason to skip the other arm.

    monkeypatch.setattr(paired, "_run_arm", fake_arm)
    return captured


def test_dry_run_never_reads_key_or_creates_outputs(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    monkeypatch.setattr(
        paired.getpass, "getpass", lambda *_: pytest.fail("prompted in dry-run")
    )
    output = tmp_path / "reports"
    assert paired.main(["--output-root", str(output)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "dry_run"
    assert plan["max_total_calls"] == 130
    assert plan["cache_enabled"] is False
    assert not output.exists()


async def test_pair_fixes_settings_preserves_quality_failures_and_is_non_overwriting(
    pair_setup: list[Any],
    tmp_path: Path,
) -> None:
    first_code, first_dir = await paired.run_pair(tmp_path)
    second_code, second_dir = await paired.run_pair(tmp_path)
    assert first_code == second_code == 1
    assert first_dir != second_dir
    assert len(pair_setup) == 4
    first, second = pair_setup[:2]
    assert first.relation_catalog is None
    assert second.relation_catalog == paired.CATALOG
    for args in pair_setup:
        assert args.no_cache and args.max_calls == 65
        assert args.model == "deepseek-v4-flash"
        assert args.max_completion_tokens == 768
        assert args.schema_mode == "json_object" and args.thinking == "disabled"
        assert args.max_tokens_parameter == "max_tokens"
    summary = json.loads((first_dir / "comparison.json").read_bytes())
    assert summary["completed"] is True
    assert summary["quality_gate_passed"] is False
    assert (
        summary["comparison"]["metric_deltas_definitions_minus_labels"][
            "relation_type_exact_accuracy"
        ]
        == 0
    )
    assert (first_dir / "comparison.json.sha256").is_file()


async def test_auth_failure_stops_before_second_arm(
    pair_setup: list[Any], monkeypatch: Any, tmp_path: Path
) -> None:
    original = paired._run_arm

    async def unauthenticated(args: Any) -> int:
        code = await original(args)
        report = json.loads(args.output.read_bytes())
        report["execution"]["stop_reason"] = "authentication_error"
        args.output.write_text(json.dumps(report), encoding="utf-8")
        return code

    monkeypatch.setattr(paired, "_run_arm", unauthenticated)
    code, path = await paired.run_pair(tmp_path)
    assert code == 1 and len(pair_setup) == 1
    summary = json.loads((path / "comparison.json").read_bytes())
    assert summary["stop_reason"] == "authentication_error"
    assert summary["comparison"]["available"] is False


async def test_input_drift_stops_calls(
    pair_setup: list[Any], monkeypatch: Any, tmp_path: Path
) -> None:
    snapshots = iter([{"source": "first"}, {"source": "changed"}])
    monkeypatch.setattr(paired, "_input_identity", lambda: next(snapshots))
    code, path = await paired.run_pair(tmp_path)
    assert code == 1 and pair_setup == []
    assert (
        json.loads((path / "comparison.json").read_bytes())["stop_reason"]
        == "inputs_changed"
    )


async def test_exception_text_and_api_key_are_not_in_artifacts(
    pair_setup: list[Any], monkeypatch: Any, tmp_path: Path
) -> None:
    secret = "sk-fake-do-not-record"
    monkeypatch.setenv("DOPPEL_API_KEY", secret)

    async def failure(args: Any) -> int:
        raise RuntimeError(secret)

    monkeypatch.setattr(paired, "_run_arm", failure)
    code, path = await paired.run_pair(tmp_path)
    assert code == 1
    for artifact in path.iterdir():
        assert secret not in artifact.read_text(encoding="utf-8")


def test_hidden_prompt_key_is_process_only_and_removed_after_failure(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    monkeypatch.setattr(paired.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(paired.getpass, "getpass", lambda *_: "sk-fake-process-only")

    async def failed_run(output: Path) -> tuple[int, Path]:
        assert paired.os.environ["DOPPEL_API_KEY"] == "sk-fake-process-only"
        raise RuntimeError("test interruption")

    monkeypatch.setattr(paired, "run_pair", failed_run)
    with pytest.raises(RuntimeError, match="test interruption"):
        paired.main(["--live", "--output-root", str(tmp_path)])
    assert "DOPPEL_API_KEY" not in paired.os.environ


def test_existing_environment_key_is_preserved(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setenv("DOPPEL_API_KEY", "sk-fake-existing")
    monkeypatch.setattr(
        paired.getpass, "getpass", lambda *_: pytest.fail("unneeded prompt")
    )

    async def successful_run(output: Path) -> tuple[int, Path]:
        return 0, output

    monkeypatch.setattr(paired, "run_pair", successful_run)
    assert paired.main(["--live", "--output-root", str(tmp_path)]) == 0
    assert paired.os.environ["DOPPEL_API_KEY"] == "sk-fake-existing"


def test_live_noninteractive_without_key_fails_before_output(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.delenv("DOPPEL_API_KEY", raising=False)
    monkeypatch.setattr(paired.sys.stdin, "isatty", lambda: False)
    with pytest.raises(RuntimeError, match="interactively"):
        paired.main(["--live", "--output-root", str(tmp_path / "no-output")])
    assert not (tmp_path / "no-output").exists()

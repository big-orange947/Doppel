"""Public Store conformance kit runs without coupling third parties to pytest."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from doppel_memory import (
    ConformanceError,
    InMemoryStore,
    StoreCapabilities,
    StoreConformanceCheck,
    StoreConformanceConfig,
    StoreConformanceReport,
    audit_store,
)
from doppel_memory.conformance import _run_conformance_cli


class CoreOnlyStore(InMemoryStore):
    @property
    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(substring_search=True)


async def test_optional_checks_skip_unadvertised_capabilities() -> None:
    report = await audit_store(
        CoreOnlyStore(),
        config=StoreConformanceConfig(
            run_id="core-only",
            checks={"pagination", "temporal_filter", "hard_delete"},
        ),
    )

    assert report.ok
    assert report.passed_count == 0
    assert report.skipped_count == 3
    assert {check.capability for check in report.checks} == {
        "pagination",
        "temporal_search",
        "hard_delete",
    }


async def test_required_capability_turns_a_skip_into_a_structured_failure() -> None:
    report = await audit_store(
        CoreOnlyStore(),
        config=StoreConformanceConfig(
            run_id="required-pagination",
            checks={"pagination"},
            required_capabilities={"pagination"},
        ),
    )

    assert not report.ok
    assert report.failed_count == 1
    assert report.checks[0].name == "pagination"
    assert report.checks[0].issues[0].error_type == "NotImplementedError"
    with pytest.raises(ConformanceError, match="not advertised"):
        report.raise_for_errors()


class UnhealthyStore(InMemoryStore):
    async def health(self):
        return {"enabled": True, "ok": False}


async def test_failure_does_not_hide_later_check_results() -> None:
    report = await audit_store(
        UnhealthyStore(),
        config=StoreConformanceConfig(
            run_id="continue-after-failure",
            checks={"health", "pagination"},
        ),
    )

    assert [check.status for check in report.checks] == ["failed", "passed"]
    assert report.failed_count == 1
    assert report.passed_count == 1
    assert report.issues[0].stage == "health"


def test_store_conformance_config_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown Store conformance checks"):
        StoreConformanceConfig(checks={"not-a-check"})
    with pytest.raises(ValueError, match="unknown Store capabilities"):
        StoreConformanceConfig(required_capabilities={"telepathy"})


def test_store_conformance_wire_models_reject_inconsistent_status() -> None:
    with pytest.raises(ValueError, match="must include an issue"):
        StoreConformanceCheck(name="broken", status="failed")
    passed = StoreConformanceCheck(name="health", status="passed")
    with pytest.raises(ValueError, match="counts do not match"):
        StoreConformanceReport(
            run_id="invalid-counts",
            store="example.Store",
            capabilities=StoreCapabilities(),
            checks=[passed],
        )


async def test_conformance_cli_writes_json_and_refuses_existing_sqlite(
    tmp_path,
) -> None:
    output = tmp_path / "report.json"
    exit_code = await _run_conformance_cli(
        SimpleNamespace(
            backend="memory",
            database=None,
            output=str(output),
            run_id="cli-test",
            require_capability=[],
        )
    )
    report = json.loads(output.read_text("utf-8"))
    assert exit_code == 0
    assert report["run_id"] == "cli-test"
    assert report["failed_count"] == 0

    existing = tmp_path / "application.sqlite3"
    existing.write_text("do-not-touch", encoding="utf-8")
    with pytest.raises(ValueError, match="must not already exist"):
        await _run_conformance_cli(
            SimpleNamespace(
                backend="sqlite",
                database=str(existing),
                output=None,
                run_id="unsafe-cli-test",
                require_capability=[],
            )
        )
    assert existing.read_text("utf-8") == "do-not-touch"

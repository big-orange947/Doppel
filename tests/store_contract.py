"""Thin pytest adapter around the installed, dependency-free Store conformance kit."""

from __future__ import annotations

import pytest

from doppel_memory import StoreConformanceConfig, audit_store

STORE_CHECKS = (
    "health",
    "scope_isolation",
    "idempotency",
    "record_round_trip",
    "filters_and_provenance",
    "owner_samples",
    "lifecycle",
    "convenience_writers",
    "pagination",
    "temporal_filter",
    "hard_delete",
)


class MemoryStoreContract:
    """Subclasses provide one writable, isolated ``store`` fixture."""

    @pytest.mark.parametrize("check", STORE_CHECKS)
    async def test_public_store_conformance(self, store, check: str) -> None:
        report = await audit_store(
            store,
            config=StoreConformanceConfig(
                run_id=f"pytest-{type(store).__name__.lower()}-{check}",
                checks={check},
            ),
        )

        assert report.ok, report.model_dump(mode="json")
        assert report.passed_count == 1
        assert report.skipped_count == 0
        assert report.failed_count == 0
        report.raise_for_errors()

"""Offline driver controls; catalog double makes no semantic-ranking claim."""

import pytest

from doppel_memory import SQLiteStore
from examples.incremental_personal_memory import SQLiteManifestIndex
from scripts.smoke_arrival_pg import STAGES, exercise


class Catalog(SQLiteManifestIndex):
    async def search(self, *args, **kwargs):
        return []


async def test_driver_reopens_and_recovers_frozen_batch_without_reanalysis(tmp_path):
    reports = {}
    for stage in STAGES:
        store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
        try:
            reports[stage] = await exercise(
                stage,
                tmp_path / "jobs",
                store,
                Catalog(tmp_path / "catalog.sqlite3"),
                "storage",
            )
        finally:
            await store.close()
    assert all(r["passed"] for r in reports.values())
    assert reports["seed"]["analyzer_calls"] == 2
    assert reports["interrupt"]["analyzer_calls"] == 1
    assert not reports["interrupt"]["complete"]
    assert reports["interrupt"]["pending_batch"]
    assert (
        reports["resume"]["analyzer_calls"] == reports["replay"]["analyzer_calls"] == 0
    )
    assert (
        reports["interrupt"]["store_digest"]
        == reports["resume"]["store_digest"]
        == reports["replay"]["store_digest"]
    )
    assert reports["replay"]["current_evidence_ids"] == ["new", "old"]
    assert reports["replay"]["historical_hits"] == 1
    assert reports["replay"]["vector_supported_final_hits"] == 0


@pytest.mark.parametrize("stage", STAGES[1:])
async def test_missing_arrival_stage_is_not_rebuilt(tmp_path, stage):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        with pytest.raises(ValueError, match="unexpected arrival stage"):
            await exercise(
                stage,
                tmp_path / "jobs",
                store,
                Catalog(tmp_path / "catalog.sqlite3"),
                "storage",
            )
    finally:
        await store.close()


async def test_live_gate_requires_vector_contribution(tmp_path):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        with pytest.raises(RuntimeError, match="vector candidates"):
            await exercise(
                "seed",
                tmp_path / "jobs",
                store,
                Catalog(tmp_path / "catalog.sqlite3"),
                "storage",
                require_vector=True,
            )
        assert not (tmp_path / "jobs" / "stage.json").exists()
    finally:
        await store.close()

"""Exercise the live-PG runner offline with an explicit catalog test double."""

import pytest

from doppel_memory import SQLiteStore
from examples.incremental_personal_memory import SQLiteManifestIndex
from scripts.smoke_workflow_lifecycle import exercise


class Catalog(SQLiteManifestIndex):
    async def search(self, *args, **kwargs):
        return []  # no semantic ranking is simulated


async def test_five_phase_driver_reopens_store_and_preserves_replay_digest(tmp_path):
    reports = {}
    for stage in ["seed", "interrupt", "resume", "update", "replay"]:
        store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
        try:
            report = await exercise(
                stage,
                tmp_path / "jobs",
                store,
                Catalog(tmp_path / "catalog.sqlite3"),
                "same-storage",
            )
            assert report["passed"]
            reports[stage] = report
        finally:
            await store.close()
    assert reports["seed"]["analyzer_calls"] == 4
    assert reports["interrupt"]["analyzer_calls"] == 3
    interrupted = reports["interrupt"]["cases"][-1]
    assert interrupted["interrupted"] and interrupted["stale_inactive_entries"] > 0
    assert interrupted["current_hits"] == 1
    assert reports["resume"]["analyzer_calls"] == 0
    assert reports["update"]["analyzer_calls"] == 1
    assert reports["replay"]["analyzer_calls"] == 0
    assert reports["update"]["store_digest"] == reports["replay"]["store_digest"]
    assert all(
        case["stale_inactive_entries"] == 0 for case in reports["resume"]["cases"]
    )


@pytest.mark.parametrize("stage", ["interrupt", "resume", "update", "replay"])
async def test_missing_stage_journals_are_not_silently_rebuilt(tmp_path, stage):
    store = SQLiteStore(database=str(tmp_path / "memory.sqlite3"))
    try:
        with pytest.raises(ValueError, match="saved lifecycle stage"):
            await exercise(
                stage,
                tmp_path / "jobs",
                store,
                Catalog(tmp_path / "catalog.sqlite3"),
                "same-storage",
            )
    finally:
        await store.close()

"""Empty-key checkpoint replay without replacing immutable live row receipts.

The V1 query adapter writes exclusive per-profile receipts after evaluation.
For replay, intercept only those two already-existing writes and compare their
semantic content. Retrieval/model/checkpoint logic and frozen sources stay intact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from benchmarks import public_memory_fresh_query as query
from benchmarks.public_memory_expansion import save
from benchmarks.public_memory_pilot import _hash


def semantic_row(row):
    return {k: v for k, v in row.items() if k not in {"usage", "retrieval_execution"}}


@contextmanager
def immutable_receipts(run_dir):
    paths = {run_dir / (p + "-receipt.json") for p in query.PROFILES}
    before = {p: p.read_bytes() for p in paths}
    old_save = query.save

    def check(path, value):
        if path not in paths:
            raise ValueError("unexpected receipt write during checkpoint replay")
        old = json.loads(before[path])
        if old["status"] != "complete" or semantic_row(old) != semantic_row(value):
            raise ValueError("immutable live row differs from replay")

    query.save = check
    try:
        yield
        if any(p.read_bytes() != original for p, original in before.items()):
            raise ValueError("live receipt changed during replay")
    finally:
        query.save = old_save


def call_inventory(run_dir):
    rows = {}
    for path in sorted(run_dir.rglob("*.sqlite3")):
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            values = db.execute("SELECT * FROM pilot_calls ORDER BY call_id").fetchall()
            rows[path.relative_to(run_dir).as_posix()] = values
    return _hash(rows)


async def replay(args):
    frozen = json.loads(args.frozen_preflight.read_bytes())
    if not args.live or not args.cache_only:
        raise ValueError("checkpoint-only replay required")
    before = call_inventory(args.run_dir)
    with immutable_receipts(args.run_dir):
        report = await query.run(args)
    if report["plans"] != frozen["plans"] or call_inventory(args.run_dir) != before:
        raise ValueError("frozen plans or durable provider attempts changed")
    report["checkpoint_replay"] = {
        "live_profile_receipts_unchanged": True,
        "durable_provider_call_inventory_unchanged": True,
        "new_provider_attempts": 0,
        "api_key_used": False,
        "retrieval_execution": "immutable-checkpoint-not-reretrieval",
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in [
        "dataset",
        "manifest",
        "cohort-plan",
        "parent-report",
        "backfill",
        "schema",
        "ingestion-dir",
        "reranker-model",
        "run-dir",
        "output",
        "frozen-preflight",
    ]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--scope-ordinal", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve previous receipts")
    args.live, args.cache_only = True, True
    result = asyncio.run(replay(args))
    save(args.output, result)
    print(
        json.dumps({"status": result["status"], "replay": result["checkpoint_replay"]})
    )
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

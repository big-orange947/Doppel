"""Zero-model audit of destructive episode merge planning and saved draft counts.

Uses fresh in-memory fixture Stores only. Never applies a consolidation plan.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_memory_expansion import save
from doppel_memory.consolidation import (
    ConsolidationAnalysis,
    ConsolidationDecision,
    ConsolidationPlanningError,
    ConsolidationRunner,
    DeterministicMemoryConsolidator,
)
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import FactAuthority, MemoryRecord, MemoryScope
from doppel_memory.processing import MemoryProposal

RUNNER = "doppel.event-consolidation-audit.v1"
DEFAULT_SAVED = Path("data/doppel/analyzer-atomicity-live-v1.json")
SAVED_SHA = "3932b5c5b052f675321c2693d3fe478f1581cad1acb7c1e912a486dbb456a415"


class ForcedMerge:
    """Deliberately unsafe custom decision, no network/model."""

    name, version = "audit.forced-episode-merge", "1"

    async def consolidate(self, input):
        return ConsolidationAnalysis(
            decisions=[
                ConsolidationDecision(
                    operation="merge",
                    source_memory_ids=[r.memory_id for r in input.records],
                    canonical_source_memory_id=input.records[-1].memory_id,
                    explanation="synthetic probe of trusted runner gates",
                )
            ]
        )


def records(contents, keys, *, topic="", starts=None):
    scope = MemoryScope(user_id="event-audit-owner", agent_id="event-audit-agent")
    return [
        MemoryRecord(
            scope=scope,
            memory_id=f"audit-{n}",
            content=content,
            kind="event",
            actor="owner",
            authority=FactAuthority.HUMAN_SELF,
            tags=["personal-memory", "episode"],
            created_at=datetime(2026, 3, n + 1, tzinfo=UTC),
            metadata={
                "subject": "owner",
                "subject_id": scope.user_id,
                "personal_memory_type": "episode",
                "temporal_status": "historical",
                "topic_key": topic,
                "event_key": key,
                "revision_kind": "assertion",
                "valid_from": starts[n] if starts else None,
                "valid_to": None,
            },
        )
        for n, (content, key) in enumerate(zip(contents, keys, strict=True))
    ]


async def inspect_plan(source_records, consolidator):
    store = InMemoryStore()
    for record in source_records:
        await store.put(record)
    runner = ConsolidationRunner(store)
    try:
        plan = await runner.plan_once(
            consolidator, source_records[0].scope, run_id="audit-only"
        )
        return {
            "status": "planned",
            "actions": [
                {
                    "operation": a.operation,
                    "canonical_content": a.proposal.content,
                    "source_count": len(a.sources),
                    "transition_sources": a.transition_sources,
                }
                for a in plan.actions
            ],
            "plan_executed": False,
        }
    except ConsolidationPlanningError:
        return {
            "status": "rejected",
            "failure_type": "ConsolidationPlanningError",
            "plan_executed": False,
        }


async def audit(saved):
    probes = {
        "same_event_complementary_details": records(
            ["I paid 340 yuan for the dinner.", "I left a 25 yuan tip at that dinner."],
            ["dinner-one", "dinner-one"],
        ),
        "different_events_equal_text_topic": records(
            ["I attended a workshop."] * 2,
            ["workshop-one", "workshop-two"],
            topic="activity.workshop",
        ),
        "same_event_equal_text_different_bounds": records(
            ["I attended a workshop."] * 2,
            ["workshop-one"] * 2,
            topic="activity.workshop",
            starts=["2026-01-10T00:00:00+00:00", "2026-02-10T00:00:00+00:00"],
        ),
        "same_event_exact_duplicate": records(
            ["I attended a workshop."] * 2,
            ["workshop-one"] * 2,
            topic="activity.workshop",
        ),
    }
    result = {
        "runner": RUNNER,
        "model_calls": 0,
        "external_store_writes": 0,
        "plans_executed": 0,
        "independent_quality_score": False,
        "execution_metadata": execution_metadata(),
        "synthetic_probes": {},
    }
    for identity, source in probes.items():
        result["synthetic_probes"][identity] = {
            "source_contents": [r.content for r in source],
            "forced_merge": await inspect_plan(source, ForcedMerge()),
            "deterministic": await inspect_plan(
                source, DeterministicMemoryConsolidator()
            ),
        }
    if saved is not None:
        raw = saved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != SAVED_SHA:
            raise ValueError("saved observation changed; do not rewrite old result")
        result["saved_artifact_sha256"] = SAVED_SHA
        rows = []
        for row in json.loads(raw)["rows"]:
            episodes = [
                MemoryProposal.model_validate(p)
                .to_record()
                .model_copy(update={"memory_id": f"audit-{n}"})
                for n, p in enumerate(row["proposals"])
                if p["metadata"]["personal_memory_type"] == "episode"
            ]
            if not episodes:
                continue
            rows.append(
                {
                    "case_id": row["case_id"],
                    "profile": row["profile"],
                    "proposal_count": len(episodes),
                    "distinct_declared_event_keys": len(
                        {r.metadata["event_key"] for r in episodes}
                    ),
                    "deterministic_plan": await inspect_plan(
                        episodes, DeterministicMemoryConsolidator()
                    ),
                }
            )
        result["saved_episode_rows"] = rows
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", type=Path, default=DEFAULT_SAVED)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("preserve existing artifact")
    result = asyncio.run(audit(args.saved))
    save(args.output, result)
    print(json.dumps(result["synthetic_probes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

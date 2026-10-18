from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from benchmarks import public_memory_topk_diagnostic as runner
from doppel_memory.models import FactAuthority, MemoryScope


def test_source_preview_exact_topk_no_gold_no_persistent_ids():
    snippet = SimpleNamespace(
        memory_id="private-memory",
        evidence_id="private-source",
        text="unchanged original",
        actor="agent",
        authority=FactAuthority.AGENT_OUTPUT,
        at=datetime(2026, 1, 1, tzinfo=UTC),
        similarity=0.7,
    )
    request = runner.preview_request(
        "generic", MemoryScope(user_id="private-owner", agent_id="a"), [snippet]
    )
    assert request.input["select_count"] == 1
    assert "private-" not in request.model_dump_json()
    assert set(request.input) == {"question", "select_count", "items"}
    source = json.loads(request.input["items"][0]["content"])
    assert (
        source["source_text"] == "unchanged original"
        and source["authority"] == "agent_output"
    )


def test_fresh_budget_prior_failure_preserved_and_no_implicit_repair(
    tmp_path, monkeypatch
):
    prior = tmp_path / "prior.json"
    prior.write_text(
        json.dumps(
            {
                "status": "failed",
                "usage": {
                    "ranker": {
                        "attempts_reserved": 1,
                        "reported_tokens": {"total_tokens": 19290},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "PRIOR_FAILURE", prior)
    plan = runner.make_plan({}, [{"source_request_bytes": 1000}], "synthetic")
    assert sum(v["max_calls"] for v in plan["stages"].values()) == 12
    assert plan["prior_spend_not_reallocated"] == {"attempts": 1, "total_tokens": 19290}
    assert plan["repair_prior_output"] is False and plan["automatic_retries"] == 0
    assert plan["unselected_status"] == "unranked-no-scores"
    assert not plan["publication_ready"] and plan["graph_calls"] == 0

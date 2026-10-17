from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from benchmarks import public_memory_retrieval_expansion as runner
from benchmarks.public_memory_pilot import _hash, build_manifest
from tests.test_public_memory_fresh_cohort import SHA, dataset


def bound():
    raw = dataset()
    parent = build_manifest(
        raw,
        dataset_namespace="synthetic",
        run_namespace="parent",
        source_sha256=SHA,
        diagnostic_count=30,
        reserved_count=2,
    )
    return raw, parent


def test_fixed_next_twenty_not_resampled_or_reserved_and_no_gold_in_plan():
    raw, parent = bound()
    cases, child = runner.prepare(raw, parent, source_sha=SHA)
    diagnostic = [r for r in parent["cases"] if r["partition"] == "diagnostic"]
    assert [r["case_id"] for r in child["cases"]] == [
        r["case_id"] for r in diagnostic[10:30]
    ]
    assert len(cases) == 20
    assert [r["ordinal"] for r in child["cases"]] == list(range(11, 31))
    assert child["parent_manifest_fingerprint"] == parent["manifest_fingerprint"]
    assert child["run_namespace"] != parent["run_namespace"]
    plan = runner.build_plan(child, SimpleNamespace(report=dict))
    assert plan["llm_calls"] == plan["graph_calls"] == plan["provider_tokens"] == 0
    assert len(plan["blocks"]) == 4 and all(len(b) == 5 for b in plan["blocks"])
    assert "PRIVATE GOLD" not in str(plan) and "has_answer" not in str(plan)
    assert plan["raw_record_cap"] == sum(c["raw_turn_count"] for c in child["cases"])


@pytest.mark.parametrize(
    "mutation", ["source", "selection", "history", "chunks", "digest"]
)
def test_changed_source_or_selection_rejected(mutation):
    raw, parent = bound()
    sha = SHA
    row = [r for r in parent["cases"] if r["partition"] == "diagnostic"][10]
    if mutation == "source":
        sha = "b" * 64
    elif mutation == "selection":
        parent["cases"].reverse()
    else:
        if mutation == "history":
            row["history_group"] = "changed"
        elif mutation == "chunks":
            row["chunk_count"] += 1
        else:
            row["history_payload_sha256"] = "changed"
        parent["manifest_fingerprint"] = _hash(
            {k: v for k, v in parent.items() if k != "manifest_fingerprint"}
        )
    with pytest.raises(ValueError):
        runner.prepare(raw, parent, source_sha=sha)


@pytest.mark.asyncio
async def test_blocks_checkpoint_without_any_provider_and_no_silent_rerun(
    tmp_path, monkeypatch
):
    raw, parent = bound()
    cases, manifest = runner.prepare(raw, parent, source_sha=SHA)
    reranker = SimpleNamespace(report=dict)
    plan = runner.build_plan(manifest, reranker)
    frozen = tmp_path / "frozen.json"
    runner.save(frozen, {"plan": plan})
    args = SimpleNamespace(run_dir=tmp_path / "run", frozen_preflight=frozen)
    calls = []

    async def baseline(block, child, **kwargs):
        import os

        assert not any(
            os.environ.get(k)
            for k in ("DEEPSEEK_API_KEY", "DOPPEL_API_KEY", "OPENAI_API_KEY")
        )
        assert kwargs["schema"] == plan["schema"]
        calls.append(len(block))
        return {
            "llm_calls": 0,
            "provider_tokens": 0,
            "profiles": plan["profiles"],
            "raw_records": len(block),
            "rows": [],
        }

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-not-real")
    monkeypatch.setattr(runner, "local_diagnostic_dsn", lambda *a: "fake")
    monkeypatch.setattr(runner, "run_baseline", baseline)
    result = await runner.execute(args, cases, manifest, plan, reranker)
    assert calls == [5, 5, 5, 5] and result["status"] == "complete"
    assert len(list(args.run_dir.glob("block-*.json"))) == 4
    with pytest.raises(ValueError):
        await runner.execute(args, cases, manifest, plan, reranker)
    changed = copy.deepcopy(plan)
    changed["candidate_window"] = 100
    with pytest.raises(ValueError):
        await runner.execute(args, cases, manifest, changed, reranker)
    assert json.loads(frozen.read_bytes())["plan"] == plan

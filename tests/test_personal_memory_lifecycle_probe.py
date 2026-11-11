"""Synthetic lifecycle probe controls, no HTTP or real API credentials."""

import json

import pytest

from benchmarks.personal_memory_lifecycle_probe import DATASET, exercise, prepare, sha
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory import OpenAICompatibleStructuredOutputConfig


class Model:
    name, version = "test.synthetic-probe", "1"

    def __init__(self, *, empty=False, fail=False):
        self.requests, self.empty, self.fail = [], empty, fail

    async def generate(self, request):
        self.requests.append(request.model_dump(mode="json"))
        if self.fail:
            raise RuntimeError("private-provider-detail")
        return {
            "memories": []
            if self.empty
            else [
                {
                    "content": m["text"],
                    "subject": m["actor"],
                    "memory_type": "fact",
                    "topic_key": "test." + m["evidence_id"],
                    "temporal_status": "unknown",
                    "evidence_ids": [m["evidence_id"]],
                }
                for m in request.input["messages"]
            ]
        }


def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def semantic(result):
    return [
        {
            k: r.get(k)
            for k in (
                "case_id",
                "batch",
                "status",
                "projection",
                "views",
                "observations",
            )
        }
        for r in result["rows"]
    ]


async def test_five_windows_use_actual_miner_without_rubrics_or_agent_evidence(
    tmp_path,
):
    model = Model()
    result = await exercise(dataset(), tmp_path / "state", model)
    assert result["status"] == "complete" and len(result["rows"]) == 5
    assert len(model.requests) == 5
    first, late = model.requests[:2]
    assert first["input"]["messages"][0]["at"] > late["input"]["messages"][0]["at"]
    for request in model.requests:
        assert set(request["input"]) == {"scope", "messages"}
        assert all(m["actor"] != "agent" for m in request["input"]["messages"])
        for case in dataset()["cases"]:
            assert case["rubric"] not in json.dumps(request, ensure_ascii=False)
    contact = result["rows"][-1]["views"]["contact"]["hits"]
    assert contact and all(
        r["metadata"]["subject_id"] == "contact-alan" for r in contact
    )


async def test_raw_cache_rebuilds_fresh_store_without_additional_provider_calls(
    tmp_path,
):
    model = Model()
    ledger = DurableCallLedger(tmp_path / "ledger", budget_id="fixture", max_calls=5)
    try:
        cached = PilotStructuredModel(
            model, ledger=ledger, cache_dir=tmp_path / "cache"
        )
        first = await exercise(dataset(), tmp_path / "first", cached)
        forbidden = Model(fail=True)
        replay = PilotStructuredModel(
            forbidden, ledger=ledger, cache_dir=tmp_path / "cache", cache_only=True
        )
        second = await exercise(dataset(), tmp_path / "replay", replay)
        assert first["status"] == second["status"] == "complete"
        assert sha(semantic(first)) == sha(semantic(second))
        assert not forbidden.requests
        assert replay.report()["cache_hits_this_instance"] == 5
        assert ledger.report()["attempts_reserved"] == 5
    finally:
        ledger.close()


async def test_generation_failure_is_preserved_and_stops_without_retry(tmp_path):
    model = Model(fail=True)
    result = await exercise(dataset(), tmp_path / "state", model)
    assert result["status"] == "stopped" and len(result["rows"]) == 1
    assert len(model.requests) == 1
    assert result["rows"][0]["error_type"] == "RuntimeError"
    assert "private-provider-detail" not in json.dumps(result)
    assert (tmp_path / "state" / "inbox.sqlite3").exists()


async def test_empty_extraction_is_visible_not_graded_as_quality_success(tmp_path):
    result = await exercise(dataset(), tmp_path / "state", Model(empty=True))
    assert result["status"] == "complete"
    assert all(row["projection"] == [] for row in result["rows"])
    assert all(
        row["observations"][0]["analysis"] == {"memories": []} for row in result["rows"]
    )
    assert not any("quality_passed" in row for row in result["rows"])


def test_plan_binds_dataset_config_and_runtime_without_secrets():
    config = OpenAICompatibleStructuredOutputConfig(model="fixture")
    plan = prepare(dataset(), config)
    assert plan["max_calls"] == 5 and plan["reader_calls"] == plan["judge_calls"] == 0
    changed = dataset()
    changed["cases"][0]["rubric"] += " changed"
    assert prepare(changed, config)["fingerprint"] != plan["fingerprint"]
    assert (
        prepare(dataset(), config.model_copy(update={"model": "other"}))["fingerprint"]
        != plan["fingerprint"]
    )
    assert "doppel_memory/intelligence.py" in plan["source_sha256"]
    assert "api_key" not in json.dumps(plan)


def test_duplicate_source_identity_is_rejected_before_generation():
    changed = dataset()
    changed["cases"][0]["batches"][1][0]["message_id"] = "p-new"
    with pytest.raises(ValueError, match="unique stable"):
        prepare(changed, OpenAICompatibleStructuredOutputConfig(model="fixture"))


async def test_contact_query_needs_explicit_host_authorization(tmp_path):
    changed = dataset()
    changed["cases"][-1].pop("allowed_subject_ids")
    result = await exercise(changed, tmp_path / "state", Model())
    assert result["status"] == "stopped"
    assert result["rows"][-1]["error_type"] == "PersonalMemoryQueryPlanningError"

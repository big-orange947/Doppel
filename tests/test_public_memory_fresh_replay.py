import json

import pytest

from benchmarks import public_memory_fresh_query as query
from benchmarks.public_memory_fresh_replay import immutable_receipts


def receipts(tmp_path):
    value = {
        "status": "complete",
        "reader": {"answer": "same"},
        "usage": {"calls": 1},
        "retrieval_execution": "live",
    }
    for name in query.PROFILES:
        (tmp_path / (name + "-receipt.json")).write_text(
            json.dumps(value), encoding="utf-8"
        )
    return value


def test_replay_checks_output_but_preserves_original_receipt_bytes(tmp_path):
    old = receipts(tmp_path)
    original = query.save
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    with immutable_receipts(tmp_path):
        for name in query.PROFILES:
            query.save(
                tmp_path / (name + "-receipt.json"),
                {
                    **old,
                    "usage": {"cache_hits": 1},
                    "retrieval_execution": "checkpoint",
                },
            )
    assert query.save is original
    assert all(p.read_bytes() == content for p, content in before.items())


@pytest.mark.parametrize("mutation", ["answer", "failure", "unexpected_path"])
def test_replay_cannot_mask_changed_output_or_retry_failure(tmp_path, mutation):
    old = receipts(tmp_path)
    original = query.save
    value = (
        {**old, "reader": {"answer": "changed"}}
        if mutation == "answer"
        else {**old, "status": "failed"}
        if mutation == "failure"
        else old
    )
    path = (
        tmp_path / (query.PROFILES[0] + "-receipt.json")
        if mutation != "unexpected_path"
        else tmp_path / "unexpected.json"
    )
    with pytest.raises(ValueError), immutable_receipts(tmp_path):
        query.save(path, value)
    assert query.save is original

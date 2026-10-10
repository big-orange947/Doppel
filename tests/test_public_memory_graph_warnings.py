import asyncio
import json
import logging

import pytest

from benchmarks.public_memory_graph_warnings import GraphExtractionWarnings


def record(
    msg="Target entity not found in nodes for edge relation: %s", args=("OWNS",)
):
    return logging.LogRecord(
        "graphiti_core.test", logging.WARNING, "", 0, msg, args, None
    )


def test_bounded_details_do_not_erase_loss_counts_or_certify_semantics():
    collector = GraphExtractionWarnings(max_entries=1)
    with collector.indexing("scope", "memory"):
        collector.emit(record())
        collector.emit(record())
    result = collector.report()
    assert result["observed_count"] == 2
    assert result["dropped_detail_count"] == 1
    assert result["entries"][0]["memory_id"] == "memory"
    assert result["semantic_completeness_certified"] is False
    assert result["all_warning_classes_captured"] is False
    result["entries"][0]["memory_id"] = "mutated"
    assert collector.report()["entries"][0]["memory_id"] == "memory"


@pytest.mark.parametrize(
    "message,args",
    [
        ("Authorization: %s", ("sk-secret",)),
        ("Target entity not found in nodes for edge relation: %s", ("sk-secret",)),
        (
            "Target entity not found in nodes for edge relation: %s",
            ("OWNS", "sk-secret"),
        ),
        ("Target entity not found in nodes for edge relation: OWNS sk-secret", ()),
        ("unexpected provider exception: sk-secret", ()),
    ],
)
def test_no_raw_provider_credential_or_unrecognized_log_persistence(message, args):
    collector = GraphExtractionWarnings()
    with collector.indexing("scope", "memory"):
        collector.emit(record(message, args))
    assert collector.report()["observed_count"] == 0
    assert "sk-secret" not in json.dumps(collector.report())


def test_capture_is_scoped_restores_handlers_and_context_after_error():
    collector = GraphExtractionWarnings()
    logger = logging.getLogger("graphiti_core.test")
    parent = logging.getLogger("graphiti_core")
    before = list(parent.handlers)
    with (
        pytest.raises(RuntimeError),
        collector.capture(),
        collector.indexing("scope", "memory"),
    ):
        logger.warning("Source entity not found in nodes for edge relation: %s", "OWNS")
        raise RuntimeError("stop")
    assert parent.handlers == before
    collector.emit(record())
    result = collector.report()
    assert result["observed_count"] == 1
    assert result["entries"][0]["endpoint"] == "source"


@pytest.mark.asyncio
async def test_async_record_attribution_does_not_cross_tasks():
    collector = GraphExtractionWarnings()

    async def worker(memory):
        with collector.indexing("scope", memory):
            await asyncio.sleep(0)
            collector.emit(record())

    await asyncio.gather(worker("first"), worker("second"))
    assert {e["memory_id"] for e in collector.report()["entries"]} == {
        "first",
        "second",
    }


@pytest.mark.parametrize("bound", [0, -1, True])
def test_invalid_detail_bound(bound):
    with pytest.raises(ValueError):
        GraphExtractionWarnings(max_entries=bound)

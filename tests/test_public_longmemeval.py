"""Synthetic schema fixtures only; no public benchmark questions are vendored."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from benchmarks.public_longmemeval import (
    DatasetShapeError,
    parse_source_time,
    preflight,
    prepare_case,
)
from integrations.aml.contract import event_ids, memory_scope


def sample() -> dict:
    return {
        "question_id": "synthetic-case",
        "question_type": "temporal-reasoning",
        "question": "Synthetic query, not a released benchmark question",
        "question_date": "2024/01/03 (Wed) 10:30",
        "answer": "GOLD_SENTINEL",
        "answer_session_ids": ["source-two"],
        "haystack_session_ids": ["source-one", "source-two"],
        "haystack_dates": ["2024/01/01 (Mon) 08:15", "2024/01/02 (Tue) 09:45"],
        "haystack_sessions": [
            [
                {
                    "role": "user",
                    "content": " original source text ",
                    "has_answer": False,
                },
                {"role": "assistant", "content": "Historical attributed reply"},
            ],
            [{"role": "user", "content": "Updated source text", "has_answer": True}],
        ],
        "reference_summary": "DERIVED_GOLD_SENTINEL",
    }


def test_gold_and_summaries_are_not_runtime_inputs() -> None:
    prepared = prepare_case(sample(), dataset_namespace="source-version")
    payloads = prepared.runtime.add_requests()
    content = json.dumps([request.model_dump() for request in payloads])
    assert "GOLD_SENTINEL" not in content and "has_answer" not in content
    assert "answer_session_ids" not in content and "question" not in content
    assert prepared.scoring.answer == "GOLD_SENTINEL"
    assert prepared.scoring.evidence_turns == ((1, 0),)
    assert set(asdict(prepared.runtime)) == {"user_id", "sessions", "query"}
    assert payloads[0].messages[0].content == " original source text "
    assert payloads[0].messages[1].role == "assistant"


def test_label_mutation_cannot_change_history_or_query() -> None:
    original = sample()
    changed = deepcopy(original)
    changed["answer"] = "OTHER_GOLD"
    changed["answer_session_ids"] = ["source-one"]
    changed["question_type"] = "knowledge-update"
    changed["haystack_sessions"][0][0]["has_answer"] = True
    changed["reference_summary"] = "DIFFERENT_SUMMARY"
    left = prepare_case(original, dataset_namespace="fixed")
    right = prepare_case(changed, dataset_namespace="fixed")
    assert left.runtime == right.runtime
    assert left.runtime.add_requests() == right.runtime.add_requests()
    assert left.scoring != right.scoring


def test_question_and_query_date_do_not_condition_memory_writes() -> None:
    left = sample()
    right = deepcopy(left)
    right["question"] = "A completely different query"
    right["question_date"] = "2024/02/03 (Sat) 10:30"
    original = prepare_case(left, dataset_namespace="fixed")
    changed = prepare_case(right, dataset_namespace="fixed")
    assert original.runtime.add_requests() == changed.runtime.add_requests()
    assert original.runtime.query != changed.runtime.query


def test_full_history_order_chunking_and_source_time_are_preserved() -> None:
    runtime = prepare_case(sample(), dataset_namespace="fixed").runtime
    chunks = runtime.add_requests(max_messages=1)
    assert len(chunks) == 3
    assert [message.content for chunk in chunks for message in chunk.messages] == [
        " original source text ",
        "Historical attributed reply",
        "Updated source text",
    ]
    assert chunks[0].session_id == chunks[1].session_id != chunks[2].session_id
    assert {chunk.user_id for chunk in chunks} == {runtime.user_id}
    assert chunks[0].messages[0].timestamp == 1704096900000
    assert runtime.query.reference_time == datetime(2024, 1, 3, 10, 30, tzinfo=UTC)
    assert set(
        runtime.query.search_request(top_k=100).model_dump(exclude_none=True)
    ) == {
        "user_id",
        "query",
        "top_k",
    }


def test_duplicate_session_names_across_samples_do_not_collide() -> None:
    other = sample()
    other["question_id"] = "synthetic-other"
    first = prepare_case(sample(), dataset_namespace="fixed").runtime
    second = prepare_case(other, dataset_namespace="fixed").runtime
    assert first.user_id != second.user_id
    a = first.add_requests()[0]
    b = second.add_requests()[0]
    assert a.session_id != b.session_id and a.request_id != b.request_id
    assert set(event_ids(memory_scope("run", a.user_id), a)).isdisjoint(
        event_ids(memory_scope("run", b.user_id), b)
    )
    third = prepare_case(sample(), dataset_namespace="different-version").runtime
    assert first.user_id != third.user_id


@pytest.mark.parametrize(
    "text",
    [
        "2024/01/01 (Mon) 08:15",
        "2024/01/01 08:15",
        "2024-01-01T08:15:00Z",
        "2024-01-01T16:15:00+08:00",
    ],
)
def test_supported_dates_preserve_clock_and_offset(text: str) -> None:
    assert parse_source_time(text) == datetime(2024, 1, 1, 8, 15, tzinfo=UTC)


@pytest.mark.parametrize("text", ["2024/99/01 08:15", "2024-01-01", "no date", " "])
def test_missing_or_invalid_source_time_is_not_wall_clock(text: str) -> None:
    with pytest.raises(DatasetShapeError):
        parse_source_time(text)


@pytest.mark.parametrize(
    "failure",
    [
        "misaligned",
        "empty-history",
        "bad-role",
        "nonstring-text",
        "invalid-label",
        "unknown-evidence",
    ],
)
def test_shape_defects_fail_closed(failure: str) -> None:
    source = sample()
    if failure == "misaligned":
        source["haystack_dates"].pop()
    elif failure == "empty-history":
        source["haystack_sessions"][0] = []
    elif failure == "bad-role":
        source["haystack_sessions"][0][0]["role"] = "system"
    elif failure == "nonstring-text":
        source["haystack_sessions"][0][0]["content"] = None
    elif failure == "invalid-label":
        source["haystack_sessions"][0][0]["has_answer"] = "true"
    elif failure == "unknown-evidence":
        source["answer_session_ids"] = ["missing-session"]
    with pytest.raises(DatasetShapeError):
        prepare_case(source, dataset_namespace="fixed")


@pytest.mark.parametrize("size", [True, 0, -1, "2"])
def test_invalid_chunk_size_rejected(size: object) -> None:
    with pytest.raises(ValueError):
        prepare_case(sample(), dataset_namespace="fixed").runtime.add_requests(
            max_messages=size
        )


def test_preflight_is_not_a_recall_score_or_a_model_run() -> None:
    report = preflight([sample()], dataset_namespace="fixed", max_messages=1)
    assert report["selected_case_count"] == 1
    assert report["cases"][0]["message_count"] == 3
    assert report["cases"][0]["add_request_count"] == 3
    assert report["quality_metrics_available"] is False
    assert report["model_execution_performed"] is False
    assert report["aml_academic_model_compliant"] is False
    assert report["llm_calls"] == 0
    assert "GOLD_SENTINEL" not in json.dumps(report)
    with pytest.raises(DatasetShapeError):
        preflight([sample(), sample()], dataset_namespace="fixed")


def test_cli_does_not_overwrite_existing_outputs_or_source(tmp_path: Path) -> None:
    dataset = tmp_path / "source.json"
    dataset.write_text(json.dumps([sample()]), encoding="utf-8")
    before = dataset.read_bytes()
    output = tmp_path / "preflight.json"
    command = [
        sys.executable,
        "-m",
        "benchmarks.public_longmemeval",
        "--dataset",
        str(dataset),
        "--output",
        str(output),
    ]
    first = subprocess.run(command, capture_output=True, check=False)
    assert first.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["quality_metrics_available"] is False
    previous = output.read_bytes()
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    assert output.read_bytes() == previous
    command[-1] = str(dataset)
    assert subprocess.run(command, capture_output=True, check=False).returncode != 0
    assert dataset.read_bytes() == before


def test_repeated_source_session_id_preserves_each_occurrence() -> None:
    source = sample()
    source["haystack_session_ids"] = ["reused", "reused"]
    source["answer_session_ids"] = ["reused"]
    source["haystack_sessions"][1] = deepcopy(source["haystack_sessions"][0])
    source["haystack_sessions"][1][0]["has_answer"] = True
    prepared = prepare_case(source, dataset_namespace="fixed")
    chunks = prepared.runtime.add_requests()
    assert len(chunks) == 2
    assert chunks[0].session_id != chunks[1].session_id
    assert chunks[0].request_id != chunks[1].request_id
    assert [message.content for message in chunks[0].messages] == [
        message.content for message in chunks[1].messages
    ]
    assert chunks[0].messages[0].timestamp != chunks[1].messages[0].timestamp
    assert prepared.scoring.evidence_turns == ((1, 0),)
    report = preflight([source], dataset_namespace="fixed")
    assert report["cases"][0]["repeated_source_session_id_count"] == 1


def test_source_order_is_not_silently_sorted_or_future_filtered() -> None:
    source = sample()
    source["haystack_dates"].reverse()
    source["question_date"] = "2024/01/01 12:00"
    prepared = prepare_case(source, dataset_namespace="fixed")
    requests = prepared.runtime.add_requests()
    assert requests[0].messages[0].timestamp > requests[1].messages[0].timestamp
    assert requests[0].messages[0].content == " original source text "
    report = preflight([source], dataset_namespace="fixed")
    assert report["cases_with_time_inversions"] == 1
    assert report["cases_with_sessions_after_query_reference"] == 1
    assert report["totals"]["sessions_after_query_reference_count"] == 1
    assert report["temporal_evaluation_policy"] == "pending-before-quality-execution"
    assert report["quality_metrics_available"] is False


def test_blank_turns_are_retained_with_transport_to_source_position_map() -> None:
    source = sample()
    source["haystack_sessions"][0].insert(
        0, {"role": "user", "content": "  ", "has_answer": False}
    )
    prepared = prepare_case(source, dataset_namespace="fixed")
    assert prepared.runtime.sessions[0].turns[0].content == "  "
    chunks = prepared.runtime.ingestion_chunks()
    assert chunks[0].source_session_index == 0
    assert chunks[0].source_turn_indices == (1, 2)
    assert len(chunks[0].request.messages) == 2
    assert chunks[0].request.messages[0].content == " original source text "
    single = prepared.runtime.ingestion_chunks(max_messages=1)
    assert single[0].source_turn_indices == (1,)
    report = preflight([source], dataset_namespace="fixed")
    assert report["totals"]["message_count"] == 4
    assert report["totals"]["blank_turn_count"] == 1
    assert report["totals"]["transport_message_count"] == 3
    # Gold changes must not select or fabricate blank content either.
    source["haystack_sessions"][0][0]["has_answer"] = True
    changed = prepare_case(source, dataset_namespace="fixed")
    assert changed.runtime == prepared.runtime
    assert changed.runtime.ingestion_chunks() == chunks
    assert (0, 0) in changed.scoring.evidence_turns


def test_all_blank_session_has_no_fabricated_transport_request() -> None:
    source = sample()
    source["haystack_sessions"][0] = [{"role": "user", "content": ""}]
    runtime = prepare_case(source, dataset_namespace="fixed").runtime
    assert len(runtime.sessions) == 2
    chunks = runtime.ingestion_chunks()
    assert len(chunks) == 1
    assert chunks[0].source_session_index == 1

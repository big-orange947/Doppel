"""Offline LongMemEval preparation; no provider or retrieval execution.

Dataset-specific parsing belongs here, never in production retrieval. Runtime
inputs are explicit projections of raw history/query fields; scoring labels live
in a separate value. Do not feed PreparedCase.scoring to a memory backend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, cast

from integrations.aml.contract import AddRequest, SearchRequest, TextMessage

ADAPTER_VERSION = "longmemeval-raw-v1"
LOCAL_EMBEDDING = "BAAI/bge-small-zh-v1.5"


class DatasetShapeError(ValueError):
    """Invalid source shape; messages exclude source text and answer values."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetShapeError(f"{field} must be a nonblank string")
    return value


def _digest(domain: str, value: object) -> str:
    data = json.dumps([domain, value], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _array(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise DatasetShapeError(f"{field} must be an array")
    return value


def parse_source_time(value: object) -> datetime:
    """Preserve time-of-day; declare naive source dates as UTC for this local profile.

    The upstream strings do not declare an offset. This is an explicit benchmark
    calendar assumption, not proof of the speakers' geographic timezone. Never
    replace source time with wall-clock time or infer it from question answers.
    """
    source = _text(value, "source date")
    plain = re.sub(r"\s+\([A-Za-z]+\)", "", source)
    if re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", plain):
        try:
            return datetime.strptime(plain, "%Y/%m/%d %H:%M").replace(tzinfo=UTC)
        except ValueError:
            raise DatasetShapeError("invalid source date") from None
    # Require a time component: a missing time must not silently become midnight.
    if "T" not in plain and " " not in plain:
        raise DatasetShapeError("source date must include time-of-day")
    try:
        result = datetime.fromisoformat(plain)
    except ValueError:
        raise DatasetShapeError("invalid source date") from None
    return (
        result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)
    )


def _milliseconds(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000


@dataclass(frozen=True)
class SourceTurn:
    source_session_id: str
    source_session_index: int
    turn_index: int
    role: Literal["user", "assistant"]
    content: str
    at: datetime


@dataclass(frozen=True)
class RawSession:
    source_session_id: str
    source_session_index: int
    turns: tuple[SourceTurn, ...]


@dataclass(frozen=True)
class QueryInput:
    user_id: str
    query: str
    reference_time: datetime

    def search_request(self, *, top_k: int) -> SearchRequest:
        # AML has no question_date field. Keep the local benchmark's reference
        # time separate; any backend using it must declare that protocol variant.
        return SearchRequest(user_id=self.user_id, query=self.query, top_k=top_k)


@dataclass(frozen=True)
class IngestionChunk:
    request: AddRequest
    source_session_index: int
    source_turn_indices: tuple[int, ...]


@dataclass(frozen=True)
class RuntimeCase:
    user_id: str
    sessions: tuple[RawSession, ...]
    query: QueryInput

    def add_requests(self, *, max_messages: int = 20) -> tuple[AddRequest, ...]:
        return tuple(
            chunk.request for chunk in self.ingestion_chunks(max_messages=max_messages)
        )

    def ingestion_chunks(self, *, max_messages: int = 20) -> tuple[IngestionChunk, ...]:
        """Deterministic local batching, not a claim to match AML word splitting."""
        if (
            isinstance(max_messages, bool)
            or not isinstance(max_messages, int)
            or max_messages < 1
        ):
            raise ValueError("max_messages must be a positive integer")
        chunks: list[IngestionChunk] = []
        for session in self.sessions:
            session_id = _digest(
                "lme-session-v1",
                [self.user_id, session.source_session_id, session.source_session_index],
            )
            for start in range(0, len(session.turns), max_messages):
                # Raw blank turns remain in SourceTurn. They have no text to
                # index; retain an ordinal map rather than inventing content or
                # using scoring annotations to decide what to transmit.
                turns = tuple(
                    turn
                    for turn in session.turns[start : start + max_messages]
                    if turn.content.strip()
                )
                if not turns:
                    continue
                chunks.append(
                    IngestionChunk(
                        source_session_index=session.source_session_index,
                        source_turn_indices=tuple(turn.turn_index for turn in turns),
                        request=AddRequest(
                            request_id=_digest(
                                "lme-chunk-v1", [session_id, start, max_messages]
                            ),
                            user_id=self.user_id,
                            session_id=session_id,
                            messages=[
                                TextMessage(
                                    role=turn.role,
                                    content=turn.content,
                                    timestamp=_milliseconds(turn.at),
                                )
                                for turn in turns
                            ],
                        ),
                    )
                )
        return tuple(chunks)


@dataclass(frozen=True)
class ScoringCase:
    case_id: str
    category: str
    abstention: bool
    answer: Any
    evidence_session_ids: tuple[str, ...]
    evidence_turns: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PreparedCase:
    runtime: RuntimeCase
    scoring: ScoringCase


def prepare_case(raw: Mapping[str, Any], *, dataset_namespace: str) -> PreparedCase:
    """No labels/derived summaries appear in RuntimeCase or its Add payloads."""
    namespace = _text(dataset_namespace, "dataset_namespace")
    case_id = _text(raw.get("question_id"), "question_id")
    user_id = _digest("lme-sample-v1", [namespace, case_id])
    ids = _array(raw.get("haystack_session_ids"), "haystack_session_ids")
    dates = _array(raw.get("haystack_dates"), "haystack_dates")
    histories = _array(raw.get("haystack_sessions"), "haystack_sessions")
    if not ids or len(ids) != len(dates) or len(ids) != len(histories):
        raise DatasetShapeError("history arrays must be nonempty and aligned")
    source_ids = [_text(value, "session ID") for value in ids]
    sessions: list[RawSession] = []
    evidence_turns: list[tuple[int, int]] = []
    for session_index, (session_id, date, history) in enumerate(
        zip(source_ids, dates, histories, strict=True)
    ):
        at = parse_source_time(date)
        if not isinstance(history, list) or not history:
            raise DatasetShapeError("history session must contain messages")
        turns: list[SourceTurn] = []
        for index, turn in enumerate(history):
            if not isinstance(turn, Mapping):
                raise DatasetShapeError("turn must be an object")
            role = _text(turn.get("role"), "role")
            if role not in {"user", "assistant"}:
                raise DatasetShapeError("unsupported source role")
            source_role = cast(Literal["user", "assistant"], role)
            content = turn.get("content")
            if not isinstance(content, str):
                raise DatasetShapeError("content must be a string")
            turns.append(
                SourceTurn(
                    source_session_id=session_id,
                    source_session_index=session_index,
                    turn_index=index,
                    role=source_role,
                    content=content,
                    at=at,
                )
            )
            if "has_answer" in turn and not isinstance(turn["has_answer"], bool):
                raise DatasetShapeError("has_answer must be boolean")
            if turn.get("has_answer") is True:
                evidence_turns.append((session_index, index))
        sessions.append(
            RawSession(
                source_session_id=session_id,
                source_session_index=session_index,
                turns=tuple(turns),
            )
        )
    evidence_ids = raw.get("answer_session_ids")
    if not isinstance(evidence_ids, list):
        raise DatasetShapeError("answer_session_ids must be an array")
    evidence_ids = [_text(value, "evidence session ID") for value in evidence_ids]
    if len(set(evidence_ids)) != len(evidence_ids) or not set(evidence_ids).issubset(
        source_ids
    ):
        raise DatasetShapeError("invalid evidence session IDs")
    if "answer" not in raw:
        raise DatasetShapeError("scoring answer is required")
    query = QueryInput(
        user_id=user_id,
        query=_text(raw.get("question"), "question"),
        reference_time=parse_source_time(raw.get("question_date")),
    )
    # Source order is not necessarily time order. Question-relative future
    # sessions are a protocol issue reported below, not malformed input. Never
    # sort/filter the supplied haystack or derive time from gold annotations.
    return PreparedCase(
        runtime=RuntimeCase(user_id=user_id, sessions=tuple(sessions), query=query),
        scoring=ScoringCase(
            case_id=case_id,
            category=_text(raw.get("question_type"), "question_type"),
            abstention=case_id.endswith("_abs"),
            answer=deepcopy(raw["answer"]),
            evidence_session_ids=tuple(evidence_ids),
            evidence_turns=tuple(evidence_turns),
        ),
    )


def preflight(
    records: list[Mapping[str, Any]],
    *,
    dataset_namespace: str,
    limit: int | None = None,
    max_messages: int = 20,
) -> dict[str, Any]:
    """Coverage/shape report only; deliberately produces no recall or QA score."""
    if limit is not None and (isinstance(limit, bool) or limit < 1):
        raise ValueError("limit must be positive")
    selected = records if limit is None else records[:limit]
    if not selected:
        raise DatasetShapeError("dataset must not be empty")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in selected:
        prepared = prepare_case(raw, dataset_namespace=dataset_namespace)
        if prepared.runtime.user_id in seen:
            raise DatasetShapeError("duplicate sample identity")
        seen.add(prepared.runtime.user_id)
        requests = prepared.runtime.add_requests(max_messages=max_messages)
        session_times = [session.turns[0].at for session in prepared.runtime.sessions]
        rows.append(
            {
                "case_id": prepared.scoring.case_id,
                "category": prepared.scoring.category,
                "abstention": prepared.scoring.abstention,
                "session_count": len(prepared.runtime.sessions),
                "repeated_source_session_id_count": len(prepared.runtime.sessions)
                - len(
                    {session.source_session_id for session in prepared.runtime.sessions}
                ),
                "message_count": sum(
                    len(session.turns) for session in prepared.runtime.sessions
                ),
                "blank_turn_count": sum(
                    not turn.content.strip()
                    for session in prepared.runtime.sessions
                    for turn in session.turns
                ),
                "transport_message_count": sum(len(req.messages) for req in requests),
                "adjacent_time_inversion_count": sum(
                    later < earlier for earlier, later in pairwise(session_times)
                ),
                "sessions_after_query_reference_count": sum(
                    at > prepared.runtime.query.reference_time for at in session_times
                ),
                "add_request_count": len(requests),
                "history_payload_sha256": _digest(
                    "lme-runtime-v1",
                    [request.model_dump(mode="json") for request in requests],
                ),
            }
        )
    return {
        "runner": "doppel.public-longmemeval-preflight.v1",
        "mode": "offline-shape-only",
        "adapter_version": ADAPTER_VERSION,
        "dataset_namespace": dataset_namespace,
        "source_case_count": len(records),
        "selected_case_count": len(rows),
        "selection": "source-prefix-not-quality-sample",
        "categories": dict(Counter(row["category"] for row in rows)),
        "totals": {
            field: sum(row[field] for row in rows)
            for field in (
                "session_count",
                "message_count",
                "transport_message_count",
                "add_request_count",
                "blank_turn_count",
                "repeated_source_session_id_count",
                "adjacent_time_inversion_count",
                "sessions_after_query_reference_count",
            )
        },
        "source_order_policy": "preserve-original-order-with-original-timestamps",
        "cases_with_time_inversions": sum(
            row["adjacent_time_inversion_count"] > 0 for row in rows
        ),
        "cases_with_sessions_after_query_reference": sum(
            row["sessions_after_query_reference_count"] > 0 for row in rows
        ),
        "temporal_evaluation_policy": "pending-before-quality-execution",
        "cases": rows,
        "naive_source_timezone_assumption": "UTC",
        "batching": {
            "max_messages": max_messages,
            "aml_word_boundary_implemented": False,
        },
        "planned_local_embedding": LOCAL_EMBEDDING,
        "model_execution_performed": False,
        "llm_calls": 0,
        "provider_tokens": 0,
        "quality_metrics_available": False,
        "aml_academic_model_compliant": False,
        "publication_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-namespace", default="longmemeval-s-cleaned-local-v1")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-messages", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/doppel/longmemeval-local-preflight.json"),
    )
    args = parser.parse_args()
    # No downloader or provider: input is a separately obtained public dataset.
    content = args.dataset.read_bytes()
    raw = json.loads(content)
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise DatasetShapeError("dataset must be an array of cases")
    report = preflight(
        raw,
        dataset_namespace=args.dataset_namespace,
        limit=args.limit,
        max_messages=args.max_messages,
    )
    report["source_sha256"] = hashlib.sha256(content).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a source dataset, including through a symlink.
    if args.output.resolve() == args.dataset.resolve():
        raise ValueError("output must not overwrite source dataset")
    if args.output.exists():
        raise FileExistsError(
            "preflight output already exists; choose a new output path"
        )
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "selected_case_count": report["selected_case_count"],
                "quality_metrics_available": False,
            }
        )
    )


if __name__ == "__main__":
    main()

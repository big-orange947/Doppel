"""Offline AML boundary tests; fake backend is not a persistence implementation."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from doppel_memory.models import MemoryScope
from integrations.aml.contract import (
    AddRequest,
    AddResponse,
    BackendContractError,
    ScopedEvidence,
    SearchItem,
    SearchRequest,
    TextualBoundary,
    WriteConflict,
    WriteNotReady,
    WriteReceipt,
    event_ids,
    memory_scope,
    payload_fingerprint,
    write_key,
)


def add_request(**changes: object) -> AddRequest:
    payload: dict[str, object] = {
        "request_id": " opaque request ",
        "user_id": " opaque user ",
        "session_id": "session-a",
        "messages": [
            {"role": "user", "content": "Original text", "timestamp": 1704067200000},
            {"role": "assistant", "content": "Historical reply"},
        ],
    }
    payload.update(changes)
    return AddRequest.model_validate(payload)


def search_request(**changes: object) -> SearchRequest:
    payload: dict[str, object] = {
        "user_id": " opaque user ",
        "query": "Original question?",
        "top_k": 100,
    }
    payload.update(changes)
    return SearchRequest.model_validate(payload)


class FakeBackend:
    def __init__(self) -> None:
        self.writes: list[tuple[MemoryScope, AddRequest]] = []
        self.searches: list[tuple[MemoryScope, SearchRequest]] = []
        self.receipt_changes: dict[str, object] = {}
        self.hits: list[ScopedEvidence] = []
        self.conflict = False

    async def add(self, scope: MemoryScope, request: AddRequest) -> WriteReceipt:
        self.writes.append((scope, request))
        if self.conflict:
            raise WriteConflict("changed payload")
        payload: dict[str, object] = {
            "scope_key": scope.scope_key,
            "write_key": write_key(scope, request),
            "payload_fingerprint": payload_fingerprint(request),
            "durable": True,
            "searchable": True,
        }
        payload.update(self.receipt_changes)
        return WriteReceipt.model_validate(payload)

    async def search(
        self, scope: MemoryScope, request: SearchRequest
    ) -> list[ScopedEvidence]:
        self.searches.append((scope, request))
        return self.hits


def hit(memory_id: str, user_id: str = " opaque user ") -> ScopedEvidence:
    return ScopedEvidence(
        scope_key=memory_scope("test-run", user_id).scope_key,
        item=SearchItem(id=memory_id, content="Traceable historical evidence"),
        evidence_ids=["source-event-id"],
    )


async def test_add_echoes_exact_ids_and_preserves_roles_text_order_and_millis() -> None:
    backend = FakeBackend()
    boundary = TextualBoundary(backend, namespace="test-run")
    request = add_request()
    response = await boundary.add(request)
    assert response.model_dump() == {
        "success": True,
        "request_id": request.request_id,
        "user_id": request.user_id,
        "session_id": request.session_id,
    }
    supplied = backend.writes[0][1]
    assert supplied == request
    assert supplied is not request and supplied.messages is not request.messages
    assert supplied.messages[0].timestamp == 1704067200000
    assert [message.role for message in supplied.messages] == ["user", "assistant"]


def test_scope_has_no_session_and_preserves_opaque_id_distinctions() -> None:
    left = add_request()
    right = add_request(session_id="session-b")
    assert memory_scope("test-run", left.user_id) == memory_scope(
        "test-run", right.user_id
    )
    assert memory_scope("test-run", "u") != memory_scope("test-run", " u ")
    assert memory_scope("run-a", "u") != memory_scope("run-b", "u")
    assert memory_scope("test-run", "eval:dataset:owner") != memory_scope(
        "test-run", "owner"
    )


def test_retry_key_stable_payload_conflicts_and_event_ids_are_scoped() -> None:
    request = add_request()
    scope = memory_scope("test-run", request.user_id)
    replay = AddRequest.model_validate_json(request.model_dump_json())
    assert write_key(scope, request) == write_key(scope, replay)
    assert payload_fingerprint(request) == payload_fingerprint(replay)
    assert event_ids(scope, request) == event_ids(scope, replay)
    assert len(set(event_ids(scope, request))) == 2
    changed = add_request(session_id="session-b")
    assert write_key(scope, changed) == write_key(scope, request)
    assert payload_fingerprint(changed) != payload_fingerprint(request)
    other_scope = memory_scope("test-run", "other-user")
    assert set(event_ids(scope, request)).isdisjoint(event_ids(other_scope, request))
    reordered = add_request(
        messages=[item.model_dump() for item in reversed(request.messages)]
    )
    assert payload_fingerprint(reordered) != payload_fingerprint(request)


@pytest.mark.parametrize("field", ["durable", "searchable"])
async def test_partial_or_queued_write_never_reports_success(field: str) -> None:
    backend = FakeBackend()
    backend.receipt_changes[field] = False
    with pytest.raises(WriteNotReady):
        await TextualBoundary(backend, namespace="test-run").add(add_request())


@pytest.mark.parametrize("field", ["write_key", "payload_fingerprint", "scope_key"])
async def test_wrong_receipt_identity_fails(field: str) -> None:
    backend = FakeBackend()
    backend.receipt_changes[field] = "wrong"
    with pytest.raises(BackendContractError):
        await TextualBoundary(backend, namespace="test-run").add(add_request())


async def test_backend_conflict_not_swallowed() -> None:
    backend = FakeBackend()
    backend.conflict = True
    with pytest.raises(WriteConflict):
        await TextualBoundary(backend, namespace="test-run").add(add_request())


async def test_search_order_options_and_cross_session_scope_not_changed() -> None:
    backend = FakeBackend()
    backend.hits = [hit("memory-b"), hit("memory-a")]
    boundary = TextualBoundary(backend, namespace="test-run")
    await boundary.add(add_request(session_id="first"))
    await boundary.add(add_request(session_id="second"))
    request = search_request(options=["Option A", "Option B"])
    response = await boundary.search(request)
    assert [item.id for item in response.data] == ["memory-b", "memory-a"]
    assert set(response.model_dump(exclude_none=True)) == {"data"}
    assert all(
        set(item) == {"id", "content"}
        for item in response.model_dump(exclude_none=True)["data"]
    )
    assert backend.searches[0][1] == request
    assert backend.writes[0][0] == backend.writes[1][0] == backend.searches[0][0]


async def test_empty_search_is_valid_and_does_not_pad_to_top_k() -> None:
    boundary = TextualBoundary(FakeBackend(), namespace="test-run")
    assert (await boundary.search(search_request())).model_dump() == {"data": []}


@pytest.mark.parametrize("failure", ["overflow", "cross-user", "duplicate"])
async def test_bad_backend_results_fail_not_silently_truncated(failure: str) -> None:
    backend = FakeBackend()
    if failure == "cross-user":
        backend.hits = [hit("other", "other-user")]
    elif failure == "duplicate":
        backend.hits = [hit("same"), hit("same")]
    else:
        backend.hits = [hit("a"), hit("b")]
    with pytest.raises(BackendContractError):
        await TextualBoundary(backend, namespace="test-run").search(
            search_request(top_k=1 if failure == "overflow" else 100)
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"user_id": " "},
        {"request_id": 12},
        {"messages": []},
        {"messages": [{"role": "system", "content": "text"}]},
        {"messages": [{"role": "user", "content": " "}]},
        {"messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}]},
        {"messages": [{"role": "user", "content": "x", "timestamp": True}]},
        {"metadata": {"gold": "not allowed"}},
    ],
)
def test_bad_add_shape_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        add_request(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"top_k": True},
        {"top_k": "100"},
        {"top_k": 0},
        {"query": " "},
        {"options": [" "]},
        {"session_id": "not a filter"},
        {"answer": "gold not allowed"},
    ],
)
def test_bad_search_shape_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        search_request(**changes)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_scores_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        SearchItem(id="id", content="text", score=score)


def test_evidence_and_timestamp_shape_checked() -> None:
    with pytest.raises(ValidationError):
        ScopedEvidence(
            scope_key="scope", item=SearchItem(id="id", content="x"), evidence_ids=[" "]
        )
    with pytest.raises(ValidationError):
        # Deliberately invalid input: the boundary must reject naive timestamps.
        SearchItem(id="id", content="x", created_at=datetime(2026, 1, 1))  # noqa: DTZ001


@pytest.mark.parametrize("success", [1, "true", False])
def test_success_must_be_boolean_true(success: object) -> None:
    with pytest.raises(ValidationError):
        AddResponse.model_validate(
            {"success": success, "request_id": "r", "user_id": "u", "session_id": "s"}
        )

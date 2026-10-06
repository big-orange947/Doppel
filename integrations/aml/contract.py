"""AML Textual boundary, without HTTP hosting, providers, or benchmark fixtures.

The backend must persist an idempotency ledger and complete indexing before it
issues a receipt. These contracts cannot prove a backend's durability themselves.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from doppel_memory.models import MemoryScope


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        # Validate, never normalize: the platform requires exact opaque ID echoes.
        if isinstance(value, str) and not value.strip():
            raise ValueError("string fields must not be blank")
        return value


class TextMessage(ContractModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: int | None = None  # Unix milliseconds, not seconds.


class AddRequest(ContractModel):
    request_id: str
    user_id: str
    session_id: str
    messages: Annotated[list[TextMessage], Field(min_length=1)]


class AddResponse(ContractModel):
    success: Literal[True] = True
    request_id: str
    user_id: str
    session_id: str

    @field_validator("success", mode="before")
    @classmethod
    def literal_boolean_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("success must be the boolean true")
        return value


class SearchRequest(ContractModel):
    user_id: str
    query: str
    options: list[str] | None = None
    top_k: Annotated[int, Field(ge=1)]

    @field_validator("options")
    @classmethod
    def nonblank_options(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("options must not contain blank strings")
        return value


class SearchItem(ContractModel):
    id: str
    content: str
    score: Annotated[float, Field(allow_inf_nan=False)] | None = None
    created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value


class SearchResponse(ContractModel):
    data: list[SearchItem]


def _digest(domain: str, *values: object) -> str:
    encoded = json.dumps([domain, *values], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def memory_scope(namespace: str, user_id: str) -> MemoryScope:
    """One deployment/run namespace and exact opaque user ID; no session filter.

    Hash before entering MemoryScope, whose normalizers otherwise strip IDs.
    Namespace is trusted host configuration, never inferred from incoming IDs.
    """
    if not namespace.strip() or not user_id.strip():
        raise ValueError("namespace and user_id must not be blank")
    return MemoryScope(
        user_id=_digest("aml-user-v1", user_id),
        agent_id=_digest("aml-host-v1", namespace),
    )


def write_key(scope: MemoryScope, request: AddRequest) -> str:
    # Changing session/content with the same request ID must conflict, not create
    # a second ledger entry. Different users may reuse a request ID safely.
    return _digest("aml-write-v1", scope.scope_key, request.request_id)


def payload_fingerprint(request: AddRequest) -> str:
    return _digest("aml-payload-v1", request.model_dump(mode="json"))


def event_ids(scope: MemoryScope, request: AddRequest) -> tuple[str, ...]:
    return tuple(
        _digest("aml-event-v1", write_key(scope, request), index)
        for index in range(len(request.messages))
    )


class WriteReceipt(ContractModel):
    write_key: str
    payload_fingerprint: str
    scope_key: str
    durable: bool
    searchable: bool


class ScopedEvidence(ContractModel):
    scope_key: str
    item: SearchItem
    evidence_ids: Annotated[list[str], Field(min_length=1)]

    @field_validator("evidence_ids")
    @classmethod
    def nonblank_evidence_ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("evidence_ids must not contain blank strings")
        return value


class AMLBackend(Protocol):
    """Production composition remains to be implemented and independently tested.

    add must persist (write_key, payload fingerprint, completion) across restarts;
    identical retries resume/reuse results, changed payload raises WriteConflict.
    search must use production natural planning and authoritative Store reloads;
    evidence IDs must resolve in that scope. Neither role implies owner identity.
    """

    async def add(self, scope: MemoryScope, request: AddRequest) -> WriteReceipt: ...

    async def search(
        self, scope: MemoryScope, request: SearchRequest
    ) -> list[ScopedEvidence]: ...


class BoundaryError(RuntimeError):
    """Redacted boundary error: never include source histories or credentials."""


class WriteConflict(BoundaryError):
    """HTTP host should map to 409; never treat a conflict as Add success."""


class WriteNotReady(BoundaryError):
    """HTTP host should map to 503; queued/partial writes are not successful."""


class BackendContractError(BoundaryError):
    """HTTP host should map to 500; invalid backend output is not empty evidence."""


class TextualBoundary:
    """Validated in-process boundary only; does not start a public HTTP server."""

    def __init__(self, backend: AMLBackend, *, namespace: str) -> None:
        if not namespace.strip():
            raise ValueError("namespace must not be blank")
        self.backend = backend
        self.namespace = namespace

    async def add(self, request: AddRequest) -> AddResponse:
        # Snapshot mutable nested lists before handing them to the backend.
        snapshot = request.model_copy(deep=True)
        scope = memory_scope(self.namespace, snapshot.user_id)
        expected_key = write_key(scope, snapshot)
        expected_payload = payload_fingerprint(snapshot)
        receipt = await self.backend.add(scope, snapshot)
        if (
            receipt.write_key != expected_key
            or receipt.payload_fingerprint != expected_payload
            or receipt.scope_key != scope.scope_key
        ):
            raise BackendContractError("write receipt identity mismatch")
        if not receipt.durable or not receipt.searchable:
            raise WriteNotReady("write is not durably stored and searchable")
        return AddResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            session_id=request.session_id,
        )

    async def search(self, request: SearchRequest) -> SearchResponse:
        snapshot = request.model_copy(deep=True)
        scope = memory_scope(self.namespace, snapshot.user_id)
        hits = await self.backend.search(scope, snapshot)
        if len(hits) > request.top_k:
            raise BackendContractError("backend exceeded top_k")
        if any(hit.scope_key != scope.scope_key for hit in hits):
            raise BackendContractError("backend returned evidence outside scope")
        if len({hit.item.id for hit in hits}) != len(hits):
            raise BackendContractError("backend returned duplicate memory IDs")
        # Preserve retrieval order. No silent truncation, answer generation, or
        # padding to 100; downstream Answer belongs to the evaluation platform.
        return SearchResponse(data=[hit.item for hit in hits])

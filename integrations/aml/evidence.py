"""Lossless, attributed Search content; no retrieval or answer-generation policy.

The AML platform does not consume arbitrary metadata fields. Put attribution in
SearchItem.content itself, as a versioned JSON document. Source text is a JSON
string, not instructions or a second header. Escaping is reversible, not rewriting.
This experimental exporter is not an HTTP host or a production search backend.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from doppel_memory.models import FactAuthority, MemoryRecord, MemoryScope, MemoryState
from doppel_memory.query import PersonalMemoryQueryHit
from doppel_memory.store import MemoryStore
from integrations.aml.context import ContextSnippet, EventResolver
from integrations.aml.contract import BackendContractError, ScopedEvidence, SearchItem

CONTENT_FORMAT = "doppel.attributed-evidence.v1"


def _fail() -> BackendContractError:
    # No source text, IDs or provider errors in transport-facing exceptions.
    return BackendContractError("evidence export failed source binding")


def _time(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise _fail() from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise _fail()
    return value.astimezone(UTC).isoformat()


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise _fail()
    return value


def _source(record: MemoryRecord) -> dict[str, Any]:
    raw = record.metadata.get("raw")
    if (
        record.kind != "event"
        or record.extractor != "ingestor"
        or not isinstance(raw, dict)
        or raw.get("transport_role") not in {"user", "assistant"}
        or not isinstance(raw.get("source_text"), str)
        or not raw["source_text"].strip()
        or raw["source_text"].strip() != record.content
        or not isinstance(raw.get("session_id"), str)
        or not raw["session_id"]
        or type(raw.get("turn_index")) is not int
        or raw["turn_index"] < 0
        or record.authority != FactAuthority.of(record.actor)
    ):
        raise _fail()
    # Transport role is NOT a speaker identity. Only host-supplied actor binding
    # identifies the owner/historical assistant; inner quoted speakers stay raw.
    speaker = {
        "owner": "owner",
        "contact": "contact",
        "agent": "historical_assistant",
    }.get(record.actor, "unresolved")
    return {
        "memory_id": record.memory_id,
        "event_id": record.source_event_id,
        "message_id": record.source_message_id,
        "transport_role": raw["transport_role"],
        "speaker": speaker,
        "actor": record.actor or "unknown",
        "source_authority": record.authority.value,
        "session_id": raw["session_id"],
        "turn_index": raw["turn_index"],
        "observed_at": _time(record.created_at),
        "text": raw["source_text"],
    }


def _item(
    scope: MemoryScope,
    record: MemoryRecord,
    score: float,
    body: dict[str, Any],
    evidence_ids: list[str],
) -> ScopedEvidence:
    if not math.isfinite(score) or not record.content.strip():
        raise _fail()
    content = json.dumps(
        {"format": CONTENT_FORMAT, **body}, ensure_ascii=False, separators=(",", ":")
    )
    return ScopedEvidence(
        scope_key=scope.scope_key,
        item=SearchItem(
            id=record.memory_id,
            content=content,
            score=score,
            created_at=record.created_at,
        ),
        evidence_ids=evidence_ids,
    )


class AttributedEvidenceExporter:
    """Project ranked, already selected hits into AML's declared content field.

    Reload snapshots and source links before export. Fail the batch, never silently
    drop/reorder/truncate invalid hits. This is an additional export-time check,
    not a substitute for engine authorization, temporal gates or atomic snapshots.
    The resolver must resolve original event/message identities in the exact scope.
    No role-to-actor guessing, facts inferred from raw dialogue, or answer support
    classification is performed here. Confirmed state is lifecycle, not truth.
    """

    def __init__(self, store: MemoryStore, *, resolve_event: EventResolver) -> None:
        self.store = store
        self.resolve_event = resolve_event

    async def _load(self, scope: MemoryScope, memory_id: str) -> MemoryRecord:
        expected_scope = scope.scope_key
        try:
            record = await self.store.get(scope, memory_id)
        except Exception:  # noqa: BLE001 - redact arbitrary host Store errors
            raise _fail() from None
        if (
            scope.scope_key != expected_scope
            or record is None
            or record.memory_id != memory_id
            or record.scope.scope_key != scope.scope_key
            or record.state != MemoryState.CONFIRMED
        ):
            raise _fail()
        return record.model_copy(deep=True)

    async def _resolve(self, scope: MemoryScope, identity: str) -> MemoryRecord:
        expected_scope = scope.scope_key
        try:
            source = await self.resolve_event(scope, identity)
        except Exception:  # noqa: BLE001 - redact arbitrary host resolver errors
            raise _fail() from None
        if (
            scope.scope_key != expected_scope
            or source is None
            or identity not in {source.source_event_id, source.source_message_id}
            or not identity
            or source.scope.scope_key != scope.scope_key
        ):
            raise _fail()
        loaded = await self._load(scope, source.memory_id)
        if loaded.model_dump(mode="json") != source.model_dump(mode="json"):
            raise _fail()
        _source(loaded)
        return loaded

    async def _final_check(
        self, scope: MemoryScope, records: Sequence[MemoryRecord]
    ) -> None:
        # Resolve awaits can permit revocation/change. Recheck all snapshots before
        # returning. This still does not promise a cross-record DB transaction.
        for record in records:
            refreshed = await self._load(scope, record.memory_id)
            if refreshed.model_dump(mode="json") != record.model_dump(mode="json"):
                raise _fail()

    async def historical(
        self, scope: MemoryScope, snippets: Sequence[ContextSnippet]
    ) -> list[ScopedEvidence]:
        bound_scope = scope.model_copy(deep=True)
        snapshots = [snippet.model_copy(deep=True) for snippet in snippets]
        if len({s.memory_id for s in snapshots}) != len(snapshots):
            raise _fail()
        items, records = [], []
        for snippet in snapshots:
            if snippet.scope_key != bound_scope.scope_key:
                raise _fail()
            record = await self._resolve(bound_scope, snippet.evidence_id)
            source = _source(record)
            if (
                record.memory_id != snippet.memory_id
                or source["transport_role"] != snippet.role
                or record.actor != snippet.actor
                or record.authority != snippet.authority
                or source["session_id"] != snippet.session_id
                or source["turn_index"] != snippet.transport_turn_index
                or source["observed_at"] != _time(snippet.at)
                or source["text"] != snippet.text
            ):
                raise _fail()
            records.append(record)
            items.append(
                _item(
                    bound_scope,
                    record,
                    snippet.similarity,
                    {"channel": "historical-dialogue", "source": source},
                    [snippet.evidence_id],
                )
            )
        await self._final_check(bound_scope, records)
        return items

    async def memories(
        self, scope: MemoryScope, hits: Sequence[PersonalMemoryQueryHit]
    ) -> list[ScopedEvidence]:
        bound_scope = scope.model_copy(deep=True)
        snapshots = [hit.model_copy(deep=True) for hit in hits]
        if len({h.record.memory_id for h in snapshots}) != len(snapshots):
            raise _fail()
        items, records = [], []
        for hit in snapshots:
            if hit.record.scope.scope_key != bound_scope.scope_key:
                raise _fail()
            record = await self._load(bound_scope, hit.record.memory_id)
            if record.model_dump(mode="json") != hit.record.model_dump(mode="json"):
                raise _fail()
            metadata = record.metadata
            links = metadata.get("evidence")
            if (
                "personal-memory" not in record.tags
                or not isinstance(links, list)
                or not links
                or metadata.get("source_scope_key") != bound_scope.scope_key
            ):
                raise _fail()
            sources, identities = [], []
            for link in links:
                if not isinstance(link, dict):
                    raise _fail()
                identity = _text(link.get("evidence_id"))
                if not identity or identity in identities:
                    raise _fail()
                source_record = await self._resolve(bound_scope, identity)
                if (
                    link.get("actor") != source_record.actor
                    or _time(link.get("at")) != _time(source_record.created_at)
                    or link.get("event_id") != source_record.source_event_id
                    or link.get("message_id") != source_record.source_message_id
                    or link.get("sender_id")
                    != source_record.metadata.get("sender_id", "")
                    or source_record.actor != record.actor
                    or source_record.authority != record.authority
                ):
                    raise _fail()
                identities.append(identity)
                sources.append(_source(source_record))
                records.append(source_record)
            records.append(record)
            if (
                record.source_event_id not in identities
                and record.source_message_id not in identities
            ):
                raise _fail()
            valid_from = _time(metadata.get("valid_from"))
            valid_to = _time(metadata.get("valid_to"))
            if valid_from and valid_to and valid_to < valid_from:
                raise _fail()
            # These are stored interpretations, NOT freshly inferred labels.
            # Unknown subjects/statuses remain unknown, not defaults to the owner.
            body = {
                "channel": "extracted-personal-memory",
                "memory": {
                    "text": record.content,
                    "source_actor": record.actor or "unknown",
                    "source_authority": record.authority.value,
                    "lifecycle_state": record.state.value,
                    "subject": _text(metadata.get("subject", "unknown")) or "unknown",
                    "subject_id": _text(metadata.get("subject_id", "")),
                    "memory_type": _text(
                        metadata.get("personal_memory_type", "unknown")
                    ),
                    "temporal_status": _text(
                        metadata.get("temporal_status", "unknown")
                    ),
                    "observed_at": _time(record.created_at),
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
                "sources": sources,
            }
            items.append(_item(bound_scope, record, hit.score, body, identities))
        await self._final_check(bound_scope, records)
        return items

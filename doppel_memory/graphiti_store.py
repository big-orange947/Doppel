"""Experimental Graphiti/Neo4j integrations.

``GraphitiSemanticIndex`` is the preferred integration: a durable Store remains the
source of truth while Graphiti contributes graph-derived semantic candidates. The
legacy ``GraphitiMemoryStore`` remains temporarily available for migration, but it
cannot satisfy Doppel's core Store contract.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import warnings
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.search.search_filters import (
    ComparisonOperator,
    DateFilter,
    SearchFilters,
)

from doppel_memory.indexing import (
    IndexEntry,
    IndexEntryPage,
    IndexOperationResult,
    IndexOperationStatus,
    memory_index_fingerprint,
)
from doppel_memory.models import (
    ACTIVE_MEMORY_STATES,
    Actor,
    ChatMessage,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryPage,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
    WriteResult,
    WriteStatus,
)
from doppel_memory.store import MemoryStore
from doppel_memory.vector import SemanticIndexUnavailableError

logger = logging.getLogger(__name__)
LOCAL_EMBEDDING_DIM = 512
GRAPHITI_PROJECTION_VERSION = 4
GRAPHITI_TEMPORAL_EXTRACTION_INSTRUCTIONS = """\
The DOPPEL_TEMPORAL JSON line is trusted temporal metadata from the authoritative
Store. Use observed_at as the episode reference time. When valid_from is present,
map it to the fact's valid_at. When valid_to is present, map it to invalid_at.
Keep planned, historical, current, timeless, and unknown distinct. Do not invalidate
a fact merely because another fact uses a non-overlapping validity interval.
The DOPPEL_SUBJECT JSON line is trusted subject metadata from the authoritative
Store. Materialize its entity_name as the subject entity for facts about that
subject, and resolve first-person language such as "I" or "my" to that entity.
Connect the subject to distinct people, places, things, attributes, or concepts;
never replace a subject-object relation with a self-loop merely because the source
sentence names only the object explicitly.
"""


class FastEmbedderClient(EmbedderClient):
    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self.config = config or EmbedderConfig(embedding_dim=LOCAL_EMBEDDING_DIM)
        self._model: Any = None
        self._model_lock = asyncio.Lock()

    async def _ensure_model(self) -> Any:
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = await asyncio.to_thread(
                        TextEmbedding, "BAAI/bge-small-zh-v1.5"
                    )
        return self._model

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await self._ensure_model()
        vectors = await asyncio.to_thread(list, model.embed(texts))
        return [[float(value) for value in vector] for vector in vectors]

    async def create(self, input_data: Any) -> list[float]:
        texts = [input_data] if isinstance(input_data, str) else list(input_data)
        if not texts or not all(isinstance(item, str) for item in texts):
            raise TypeError("FastEmbedderClient accepts text input only")
        return (await self._embed(texts))[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self._embed(input_data_list)


class NoOpCrossEncoder(CrossEncoderClient):
    """Graphiti 0.29 CrossEncoder-compatible stable-order ranker."""

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        size = len(passages)
        return [
            (passage, float(size - index)) for index, passage in enumerate(passages)
        ]


class GraphitiIndexUnavailableError(SemanticIndexUnavailableError):
    """Graphiti cannot currently index or search graph-derived candidates."""


class GraphitiFilterUnsupportedError(SemanticIndexUnavailableError):
    """Legacy compatibility error retained for pre-v3 Graphiti integrations.

    Projection v3 proves MemoryFilter fields against authoritative source records
    instead of asking Graphiti edges to represent Doppel metadata.
    """


@dataclass(frozen=True)
class GraphitiIndexResult:
    """Provenance returned after submitting one authoritative Store record."""

    memory_id: str
    episode_id: str
    scope_key: str
    fingerprint: str = ""
    source_version: int = 1
    status: IndexOperationStatus = IndexOperationStatus.INDEXED


class GraphitiSemanticIndex:
    """Experimental Graphiti 0.29 semantic candidate index.

    The caller first commits a ``MemoryRecord`` to a conforming Store, then explicitly
    submits that authoritative record here. Graphiti facts remain derived candidates;
    they never become the lifecycle source of truth for the core record.
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        neo4j_uri: str = "bolt://127.0.0.1:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "neo4j",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "",
        enabled: bool = True,
        graphiti_client: Any | None = None,
    ) -> None:
        self._store = store
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._llm_api_key = llm_api_key
        self._llm_base_url = llm_base_url
        self._llm_model = llm_model
        self._enabled = enabled
        self._graphiti: Any | None = graphiti_client
        self._owns_client = graphiti_client is None
        self._init_lock = asyncio.Lock()

    @property
    def identity(self) -> str:
        return f"graphiti:0.29:doppel-v{GRAPHITI_PROJECTION_VERSION}"

    async def index_record(self, record: MemoryRecord) -> GraphitiIndexResult:
        operation = await self.upsert(record)
        return GraphitiIndexResult(
            memory_id=operation.memory_id,
            episode_id=_graphiti_episode_id(record.scope, operation.memory_id),
            scope_key=operation.scope_key,
            fingerprint=operation.fingerprint,
            source_version=operation.source_version or 1,
            status=operation.status,
        )

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult:
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        if not record.memory_id:
            raise ValueError(
                "Graphiti indexing requires a committed MemoryRecord with memory_id"
            )
        authoritative = await self._store.get(record.scope, record.memory_id)
        if authoritative is None:
            raise ValueError(
                "Graphiti indexing requires a record present in the authoritative Store"
            )
        record = authoritative
        fingerprint = memory_index_fingerprint(record)
        episode_id = _graphiti_episode_id(record.scope, record.memory_id)
        current = await self.inspect(record.scope, record.memory_id)
        if current is not None and current.fingerprint == fingerprint:
            return IndexOperationResult(
                index_identity=self.identity,
                status=IndexOperationStatus.SKIPPED,
                memory_id=record.memory_id,
                scope_key=record.scope.scope_key,
                fingerprint=fingerprint,
                source_version=record.version,
            )
        body = _graphiti_episode_body(record, fingerprint)
        graphiti: Any | None = None
        managed_episode_slot = False
        try:
            graphiti = await self._ensure_graphiti()
            if current is not None:
                await graphiti.remove_episode(episode_id)
            managed_episode_slot = _can_precreate_graphiti_episode_slot(graphiti)
            if managed_episode_slot:
                await _precreate_graphiti_episode_slot(
                    graphiti,
                    episode_id=episode_id,
                    name=_graphiti_episode_name(
                        record.memory_id, fingerprint, record.version
                    ),
                    group_id=record.scope.scope_key,
                    content=body,
                    source_description=record.extractor or "doppel",
                    reference_time=_graphiti_reference_time(record),
                )
            result = await graphiti.add_episode(
                name=_graphiti_episode_name(
                    record.memory_id, fingerprint, record.version
                ),
                episode_body=body,
                source_description=record.extractor or "doppel",
                reference_time=_graphiti_reference_time(record),
                group_id=record.scope.scope_key,
                uuid=episode_id,
                custom_extraction_instructions=(
                    GRAPHITI_TEMPORAL_EXTRACTION_INSTRUCTIONS
                ),
            )
            actual_episode_id = str(
                getattr(result.episode, "uuid", "") or episode_id
            )
            if actual_episode_id != episode_id:
                raise RuntimeError(
                    "Graphiti returned an episode UUID different from the requested ID"
                )
        except Exception as exc:
            if managed_episode_slot and graphiti is not None:
                try:
                    await graphiti.remove_episode(episode_id)
                except Exception:
                    logger.warning(
                        "Graphiti failed to clean incomplete episode %s",
                        episode_id,
                        exc_info=True,
                    )
            raise GraphitiIndexUnavailableError(
                f"Graphiti episode indexing failed: {exc}"
            ) from exc
        return IndexOperationResult(
            index_identity=self.identity,
            status=IndexOperationStatus.INDEXED,
            memory_id=record.memory_id,
            scope_key=record.scope.scope_key,
            fingerprint=fingerprint,
            source_version=record.version,
        )

    async def inspect(self, scope: MemoryScope, memory_id: str) -> IndexEntry | None:
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        graphiti = await self._ensure_graphiti()
        episode_id = _graphiti_episode_id(scope, memory_id)
        try:
            episode = await _load_graphiti_episode(graphiti, episode_id)
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti episode inspection failed: {exc}"
            ) from exc
        if episode is None:
            return None
        group_id = str(getattr(episode, "group_id", "") or "")
        source_id, fingerprint, source_version = _episode_index_metadata(
            str(getattr(episode, "name", "") or "")
        )
        if group_id != scope.scope_key or source_id != memory_id:
            # The deterministic UUID is occupied by malformed or legacy metadata.
            # Treat it as stale so ``upsert``/``delete`` can repair the slot.
            return IndexEntry(
                memory_id=memory_id,
                scope_key=scope.scope_key,
                fingerprint="",
                source_version=1,
            )
        return IndexEntry(
            memory_id=memory_id,
            scope_key=scope.scope_key,
            fingerprint=fingerprint,
            source_version=source_version,
        )

    async def delete(self, scope: MemoryScope, memory_id: str) -> IndexOperationResult:
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        current = await self.inspect(scope, memory_id)
        status = IndexOperationStatus.MISSING
        if current is not None:
            try:
                graphiti = await self._ensure_graphiti()
                await graphiti.remove_episode(_graphiti_episode_id(scope, memory_id))
            except Exception as exc:
                raise GraphitiIndexUnavailableError(
                    f"Graphiti episode deletion failed: {exc}"
                ) from exc
            status = IndexOperationStatus.DELETED
        return IndexOperationResult(
            index_identity=self.identity,
            status=status,
            memory_id=memory_id,
            scope_key=scope.scope_key,
        )

    async def scan_entries(
        self,
        scope: MemoryScope,
        *,
        cursor: str = "",
        limit: int = 100,
    ) -> IndexEntryPage:
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        if limit <= 0:
            raise ValueError("limit must be positive")
        try:
            graphiti = await self._ensure_graphiti()
            episodes = list(
                await _load_graphiti_scope_episodes(
                    graphiti,
                    scope.scope_key,
                    limit=limit + 1,
                    cursor=cursor,
                )
            )
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti episode catalog scan failed: {exc}"
            ) from exc
        selected = episodes[:limit]
        entries: list[IndexEntry] = []
        for episode in selected:
            memory_id, fingerprint, source_version = _episode_index_metadata(
                str(getattr(episode, "name", "") or "")
            )
            group_id = str(getattr(episode, "group_id", "") or "")
            if memory_id and group_id == scope.scope_key:
                entries.append(
                    IndexEntry(
                        memory_id=memory_id,
                        scope_key=group_id,
                        fingerprint=fingerprint,
                        source_version=source_version,
                    )
                )
        next_cursor = cursor
        if selected:
            next_cursor = str(getattr(selected[-1], "uuid", "") or cursor)
        return IndexEntryPage(
            entries=entries,
            next_cursor=next_cursor,
            has_more=len(episodes) > limit,
        )

    async def search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        return await self._search(
            query, scopes, filters=filters, limit=limit, graph_valid_at=None
        )

    async def search_at(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        valid_at: datetime,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        if valid_at.tzinfo is None:
            raise ValueError("Graphiti valid_at must include a timezone")
        return await self._search(
            query,
            scopes,
            filters=filters,
            limit=limit,
            graph_valid_at=valid_at.astimezone(UTC),
        )

    async def _search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None,
        limit: int,
        graph_valid_at: datetime | None,
    ) -> Sequence[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "Graphiti semantic search requires at least one exact scope"
            )
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        if limit <= 0 or not str(query or "").strip():
            return []
        filter_obj = filters or MemoryFilter()
        scope_by_key = {scope.scope_key: scope for scope in scopes}
        try:
            graphiti = await self._ensure_graphiti()
            edges = await graphiti.search(
                query=query.strip(),
                group_ids=list(scope_by_key),
                num_results=limit * 2,
                search_filter=_graphiti_search_filter(graph_valid_at),
            )
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti semantic search failed: {exc}"
            ) from exc

        edge_episodes = {
            str(episode_id)
            for edge in edges
            for episode_id in (getattr(edge, "episodes", None) or [])
            if episode_id
        }
        try:
            episodes = await _load_graphiti_episodes(graphiti, edge_episodes)
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti episode provenance lookup failed: {exc}"
            ) from exc
        source_by_episode = {
            str(getattr(episode, "uuid", "") or ""): (
                str(getattr(episode, "group_id", "") or ""),
                _memory_id_from_episode_name(str(getattr(episode, "name", "") or "")),
            )
            for episode in episodes
        }
        source_keys = sorted(
            {
                source
                for source in source_by_episode.values()
                if source[0] in scope_by_key and source[1]
            }
        )
        source_records = await asyncio.gather(
            *(
                self._store.get(scope_by_key[scope_key], memory_id)
                for scope_key, memory_id in source_keys
            )
        )
        record_by_source = dict(zip(source_keys, source_records, strict=True))

        results: dict[tuple[str, str], RecallResult] = {}
        for rank, edge in enumerate(edges):
            fact = str(getattr(edge, "fact", "") or "").strip()
            group_id = str(getattr(edge, "group_id", "") or "")
            scope = scope_by_key.get(group_id)
            if not fact or scope is None:
                continue
            episode_ids = [
                str(value) for value in (getattr(edge, "episodes", None) or [])
            ]
            for episode_id in episode_ids:
                source_key = source_by_episode.get(episode_id, ("", ""))
                source = record_by_source.get(source_key)
                if (
                    source is None
                    or source_key[0] != group_id
                    or source.scope.scope_key != group_id
                    or not _core_record_matches_filter(source, filter_obj)
                    or not _core_record_valid_at(source, graph_valid_at)
                ):
                    continue
                key = (group_id, source.memory_id)
                if key in results:
                    continue
                source_chain = source.metadata.get("derived_chain", [])
                if not isinstance(source_chain, list):
                    source_chain = []
                results[key] = RecallResult(
                    fact=source.content,
                    kind=source.kind,
                    scope=scope,
                    memory_id=source.memory_id,
                    actor=source.actor,
                    authority=source.authority,
                    source_event_id=source.source_event_id,
                    source_message_id=source.source_message_id,
                    source_episode=",".join(episode_ids),
                    extractor="graphiti",
                    extracted_at=source.updated_at,
                    raw_text=fact,
                    derived_chain=[
                        *(str(value) for value in source_chain),
                        "graphiti:0.29",
                        f"graphiti-edge:{getattr(edge, 'uuid', '')}",
                    ],
                    valid_at=(
                        _record_valid_from(source)
                        or _optional_datetime(getattr(edge, "valid_at", None))
                        or _graphiti_reference_time(source)
                    ),
                    similarity=_graphiti_rank_score(rank, len(edges)),
                    state=source.state,
                )
                if len(results) >= limit:
                    return list(results.values())
        return list(results.values())

    async def health(self) -> dict[str, Any]:
        if not self._enabled:
            return {"enabled": False, "ok": False, "reason": "disabled"}
        try:
            graphiti = await self._ensure_graphiti()
            driver = getattr(graphiti, "driver", None)
            if driver is None:
                raise RuntimeError("Graphiti client does not expose a graph driver")
            await driver.execute_query("RETURN 1 AS doppel_health")
            return {
                "enabled": True,
                "ok": True,
                "backend": "graphiti",
                "role": "semantic_index",
                "experimental": True,
            }
        except Exception as exc:  # noqa: BLE001 - health is an observation boundary
            return {
                "enabled": True,
                "ok": False,
                "backend": "graphiti",
                "role": "semantic_index",
                "experimental": True,
                "reason": str(exc),
            }

    async def close(self) -> None:
        if self._graphiti is not None and self._owns_client:
            await self._graphiti.close()
            self._graphiti = None

    async def _ensure_graphiti(self) -> Any:
        if self._graphiti is None:
            async with self._init_lock:
                if self._graphiti is None:
                    self._graphiti = _build_graphiti_client(
                        neo4j_uri=self._neo4j_uri,
                        neo4j_user=self._neo4j_user,
                        neo4j_password=self._neo4j_password,
                        llm_api_key=self._llm_api_key,
                        llm_base_url=self._llm_base_url,
                        llm_model=self._llm_model,
                    )
        return self._graphiti


class GraphitiMemoryStore(MemoryStore):
    """Deprecated compatibility adapter; prefer Store plus GraphitiSemanticIndex."""

    def __init__(
        self,
        *,
        neo4j_uri: str = "bolt://127.0.0.1:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "neo4j",
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model: str = "",
        enabled: bool = True,
        owner_sample_limit: int = 20,
    ) -> None:
        warnings.warn(
            "GraphitiMemoryStore cannot satisfy Doppel's core Store contract and is "
            "deprecated; use a conforming Store plus GraphitiSemanticIndex",
            DeprecationWarning,
            stacklevel=2,
        )
        self._neo4j_uri = neo4j_uri
        self._neo4j_user = neo4j_user
        self._neo4j_password = neo4j_password
        self._llm_api_key = llm_api_key
        self._llm_base_url = llm_base_url
        self._llm_model = llm_model
        self._enabled = enabled
        self._owner_sample_limit = owner_sample_limit
        self._graphiti: Graphiti | None = None
        self._init_lock = asyncio.Lock()
        self._seen_keys: set[tuple[str, str]] = set()
        self._owner_samples: dict[str, deque[ChatMessage]] = {}
        self._capabilities = StoreCapabilities(
            semantic_search=True,
            temporal_search=True,
            graph_relations=True,
        )

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        if not self._enabled:
            return WriteResult(status=WriteStatus.SKIPPED, message="backend disabled")
        key = str(idempotency_key or record.idempotency_key or "").strip()
        index_key = (record.scope.scope_key, key)
        if key and index_key in self._seen_keys:
            return WriteResult(status=WriteStatus.DUPLICATE)
        body = (
            f"[DOPPEL kind={record.kind} actor={record.actor or '-'} "
            f"authority={record.authority.value} state={record.state.value}] {record.content}"
        )
        try:
            graphiti = await self._ensure_graphiti()
            result = await graphiti.add_episode(
                name=f"Doppel:{record.kind}:{record.scope.describe()}",
                episode_body=body,
                source_description=record.extractor or "doppel",
                reference_time=record.created_at,
                group_id=record.scope.scope_key,
            )
        except Exception as exc:  # noqa: BLE001 - optional backend fails open
            logger.warning("Graphiti write failed: %s", exc)
            return WriteResult(
                status=WriteStatus.FAILED,
                error_code="graphiti_write_failed",
                message=str(exc),
            )
        memory_id = str(result.episode.uuid)
        stored = record.model_copy(
            update={"memory_id": memory_id, "idempotency_key": key}, deep=True
        )
        if key:
            self._seen_keys.add(index_key)
        if (
            stored.kind == MemoryKind.EVENT
            and stored.actor == Actor.OWNER
            and stored.content
        ):
            samples = self._owner_samples.setdefault(
                stored.scope.scope_key, deque(maxlen=self._owner_sample_limit)
            )
            samples.append(
                ChatMessage(
                    actor=stored.actor,
                    text=stored.content,
                    at=stored.created_at,
                    event_id=stored.source_event_id,
                    message_id=stored.source_message_id,
                    sender_id=str(stored.metadata.get("sender_id", "")),
                    message_type=str(stored.metadata.get("message_type", "message")),
                    reply_to_id=str(stored.metadata.get("reply_to_id", "")),
                    quoted_message_id=str(stored.metadata.get("quoted_message_id", "")),
                    thread_id=str(stored.metadata.get("thread_id", "")),
                    thread_root_id=str(stored.metadata.get("thread_root_id", "")),
                    attachments=list(stored.metadata.get("attachments", [])),
                    raw=dict(stored.metadata.get("raw", {})),
                    parts=list(stored.metadata.get("parts", [])),
                )
            )
        return WriteResult(status=WriteStatus.CREATED, record=stored)

    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError("search requires at least one exact scope")
        if not self._enabled or not str(query or "").strip() or limit <= 0:
            return []
        filter_obj = filters or MemoryFilter()
        scope_by_key = {scope.scope_key: scope for scope in scopes}
        try:
            graphiti = await self._ensure_graphiti()
            edges = await graphiti.search(
                query=query,
                group_ids=list(scope_by_key),
                num_results=limit * 2,
            )
        except Exception as exc:  # noqa: BLE001 - optional backend fails open
            logger.warning("Graphiti search failed: %s", exc)
            return []
        results: list[RecallResult] = []
        for edge in edges:
            fact = str(getattr(edge, "fact", "") or "").strip()
            if not fact:
                continue
            group_id = str(getattr(edge, "group_id", "") or "")
            item = RecallResult(
                fact=fact,
                scope=scope_by_key.get(group_id),
                memory_id=str(getattr(edge, "uuid", "") or ""),
                source_episode=str(getattr(edge, "episodes", "") or ""),
                extracted_at=_optional_datetime(getattr(edge, "created_at", None)),
                valid_at=_optional_datetime(getattr(edge, "valid_at", None)),
            )
            if _matches_filter(item, filter_obj):
                results.append(item)
            if len(results) >= limit:
                break
        return results

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        samples = self._owner_samples.get(scope.scope_key)
        return list(samples)[-limit:] if samples and limit > 0 else []

    async def scan(
        self,
        scope: MemoryScope,
        *,
        filters: MemoryFilter | None = None,
        cursor: str = "",
        limit: int = 100,
    ) -> MemoryPage:
        raise NotImplementedError(
            "experimental Graphiti backend does not support paginated scans"
        )

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        raise NotImplementedError("experimental Graphiti backend does not support get")

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        raise NotImplementedError(
            "experimental Graphiti backend does not support lifecycle transitions"
        )

    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool:
        raise NotImplementedError(
            "experimental Graphiti backend does not support deletion"
        )

    async def health(self) -> dict[str, Any]:
        if not self._enabled:
            return {"enabled": False, "ok": False, "reason": "disabled"}
        try:
            await self._ensure_graphiti()
            return {"enabled": True, "ok": True, "experimental": True}
        except Exception as exc:  # noqa: BLE001 - health reports backend failures
            return {
                "enabled": True,
                "ok": False,
                "experimental": True,
                "reason": str(exc),
            }

    async def close(self) -> None:
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    async def _ensure_graphiti(self) -> Graphiti:
        if self._graphiti is None:
            async with self._init_lock:
                if self._graphiti is None:
                    self._graphiti = self._build_graphiti()
        return self._graphiti

    def _build_graphiti(self) -> Graphiti:
        return _build_graphiti_client(
            neo4j_uri=self._neo4j_uri,
            neo4j_user=self._neo4j_user,
            neo4j_password=self._neo4j_password,
            llm_api_key=self._llm_api_key,
            llm_base_url=self._llm_base_url,
            llm_model=self._llm_model,
        )


def _build_graphiti_client(
    *,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str,
) -> Graphiti:
    if not llm_api_key:
        raise RuntimeError("Graphiti integration requires llm_api_key")
    return Graphiti(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        llm_client=OpenAIClient(
            LLMConfig(
                api_key=llm_api_key,
                model=llm_model or None,
                base_url=llm_base_url or None,
            )
        ),
        embedder=FastEmbedderClient(),
        cross_encoder=NoOpCrossEncoder(),
    )


def _can_precreate_graphiti_episode_slot(graphiti: Any) -> bool:
    driver = getattr(graphiti, "driver", None)
    return driver is not None and driver is not graphiti


async def _precreate_graphiti_episode_slot(
    graphiti: Any,
    *,
    episode_id: str,
    name: str,
    group_id: str,
    content: str,
    source_description: str,
    reference_time: datetime,
) -> None:
    """Create the deterministic Episode expected by Graphiti 0.29's UUID path.

    ``Graphiti.add_episode(uuid=...)`` loads that UUID as an existing Episode; it
    does not create a missing node. Doppel therefore creates the empty stable slot
    first and lets ``add_episode`` hydrate its entities and edges. Lightweight
    injected test clients that act as their own driver retain their legacy direct-
    create behavior and never call this helper.
    """
    driver = getattr(graphiti, "driver", None)
    if driver is None or driver is graphiti:
        raise RuntimeError("Graphiti client does not expose a separate graph driver")
    episode = EpisodicNode(
        uuid=episode_id,
        name=name,
        group_id=group_id,
        labels=[],
        created_at=datetime.now(UTC),
        source=EpisodeType.message,
        source_description=source_description,
        content=content,
        valid_at=reference_time,
    )
    await episode.save(driver)


async def _load_graphiti_episodes(
    graphiti: Any, episode_ids: set[str]
) -> Sequence[Any]:
    if not episode_ids:
        return []
    ordered_ids = sorted(episode_ids)
    injected_loader = getattr(graphiti, "get_episodes_by_uuids", None)
    if injected_loader is not None:
        return await graphiti.get_episodes_by_uuids(ordered_ids)
    driver = getattr(graphiti, "driver", None)
    if driver is None:
        raise RuntimeError("Graphiti client does not expose a graph driver")
    return await EpisodicNode.get_by_uuids(driver, ordered_ids)


async def _load_graphiti_episode(graphiti: Any, episode_id: str) -> Any | None:
    injected_loader = getattr(graphiti, "get_episode_by_uuid", None)
    if injected_loader is not None:
        return await injected_loader(episode_id)
    injected_bulk_loader = getattr(graphiti, "get_episodes_by_uuids", None)
    if injected_bulk_loader is not None:
        episodes = await injected_bulk_loader([episode_id])
        return episodes[0] if episodes else None
    driver = getattr(graphiti, "driver", None)
    if driver is None:
        raise RuntimeError("Graphiti client does not expose a graph driver")
    try:
        return await EpisodicNode.get_by_uuid(driver, episode_id)
    except Exception as exc:
        if type(exc).__name__ == "NodeNotFoundError":
            return None
        raise


async def _load_graphiti_scope_episodes(
    graphiti: Any,
    scope_key: str,
    *,
    limit: int,
    cursor: str,
) -> Sequence[Any]:
    injected_loader = getattr(graphiti, "get_episodes_by_group_ids", None)
    if injected_loader is not None:
        return await injected_loader(
            [scope_key], limit=limit, uuid_cursor=cursor or None
        )
    driver = getattr(graphiti, "driver", None)
    if driver is None:
        raise RuntimeError("Graphiti client does not expose a graph driver")
    return await EpisodicNode.get_by_group_ids(
        driver,
        [scope_key],
        limit=limit,
        uuid_cursor=cursor or None,
    )


def _graphiti_episode_id(scope: MemoryScope, memory_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"doppel:{scope.scope_key}:{memory_id}"))


def _graphiti_reference_time(record: MemoryRecord) -> datetime:
    evidence = record.metadata.get("evidence", [])
    evidence_times = [
        parsed
        for item in evidence if isinstance(evidence, list) and isinstance(item, dict)
        if (parsed := _optional_datetime(item.get("at"))) is not None
    ]
    return max(evidence_times, default=record.created_at)


def _record_valid_from(record: MemoryRecord) -> datetime | None:
    return _optional_datetime(record.metadata.get("valid_from"))


def _record_valid_to(record: MemoryRecord) -> datetime | None:
    return _optional_datetime(record.metadata.get("valid_to"))


def _graphiti_episode_body(record: MemoryRecord, fingerprint: str) -> str:
    reference_time = _graphiti_reference_time(record)
    valid_from = _record_valid_from(record)
    valid_to = _record_valid_to(record)
    temporal = {
        "observed_at": reference_time.isoformat(),
        "temporal_status": str(
            record.metadata.get("temporal_status", "unknown") or "unknown"
        ).strip().lower(),
        "valid_from": valid_from.isoformat() if valid_from is not None else None,
        "valid_to": valid_to.isoformat() if valid_to is not None else None,
    }
    subject_id = str(record.metadata.get("subject_id") or "").strip()
    if not subject_id:
        subject_id = str(record.scope.user_id or "").strip() or "owner"
    subject_role = str(
        record.metadata.get("subject") or record.actor or ""
    ).strip() or "owner"
    subject = {
        "entity_name": subject_id,
        "role": subject_role,
        "subject_id": subject_id,
    }
    header = (
        f"[DOPPEL memory_id={record.memory_id} version={record.version} "
        f"fingerprint={fingerprint} kind={record.kind} "
        f"actor={record.actor or '-'} authority={record.authority.value} "
        f"state={record.state.value}]"
    )
    return "\n".join(
        (
            header,
            "DOPPEL_TEMPORAL "
            + json.dumps(temporal, ensure_ascii=False, sort_keys=True),
            "DOPPEL_SUBJECT "
            + json.dumps(subject, ensure_ascii=False, sort_keys=True),
            record.content,
        )
    )


def _graphiti_search_filter(valid_at: datetime | None) -> SearchFilters | None:
    if valid_at is None:
        return None
    at_or_before = DateFilter(
        date=valid_at,
        comparison_operator=ComparisonOperator.less_than_equal,
    )
    after = DateFilter(
        date=valid_at,
        comparison_operator=ComparisonOperator.greater_than,
    )
    missing = DateFilter(comparison_operator=ComparisonOperator.is_null)
    return SearchFilters(
        valid_at=[[at_or_before], [missing]],
        invalid_at=[[after], [missing]],
        expired_at=[[after], [missing]],
    )


def _graphiti_rank_score(rank: int, result_count: int) -> float:
    if result_count <= 0:
        return 0.0
    # Graphiti's basic search exposes RRF order rather than raw BM25/cosine scores.
    # Preserve that ordering in the SemanticIndex score range without inventing a
    # cosine value; every accepted top-k candidate remains above the default gate.
    return round(1.0 - (max(rank, 0) / (2.0 * result_count)), 6)


def _graphiti_episode_name(
    memory_id: str, fingerprint: str, source_version: int
) -> str:
    encoded = base64.urlsafe_b64encode(memory_id.encode()).decode().rstrip("=")
    return f"DoppelMemory:v4:{encoded}:{fingerprint}:{source_version}"


def _episode_index_metadata(name: str) -> tuple[str, str, int]:
    prefix_v4 = "DoppelMemory:v4:"
    if name.startswith(prefix_v4):
        parts = name[len(prefix_v4) :].split(":")
        if len(parts) != 3:
            return "", "", 1
        encoded, fingerprint, raw_version = parts
        try:
            source_version = int(raw_version)
        except ValueError:
            return "", "", 1
        if (
            source_version < 1
            or len(fingerprint) != 64
            or any(value not in "0123456789abcdef" for value in fingerprint)
        ):
            return "", "", 1
        return _decode_memory_id(encoded), fingerprint, source_version

    for legacy_prefix in ("DoppelMemory:v3:", "DoppelMemory:v2:"):
        if not name.startswith(legacy_prefix):
            continue
        parts = name[len(legacy_prefix) :].split(":")
        if len(parts) != 3:
            return "", "", 1
        encoded, fingerprint, raw_version = parts
        try:
            source_version = int(raw_version)
        except ValueError:
            return "", "", 1
        if (
            source_version < 1
            or len(fingerprint) != 64
            or any(value not in "0123456789abcdef" for value in fingerprint)
        ):
            return "", "", 1
        # Older projections did not materialize authoritative subjects (v3) or
        # explicit temporal coordinates (v2). Preserve source identity but expose
        # an empty fingerprint so reconciliation upgrades the graph projection.
        return _decode_memory_id(encoded), "", source_version

    prefix_v1 = "DoppelMemory:v1:"
    if name.startswith(prefix_v1):
        return _decode_memory_id(name[len(prefix_v1) :]), "", 1
    return "", "", 1


def _memory_id_from_episode_name(name: str) -> str:
    return _episode_index_metadata(name)[0]


def _decode_memory_id(encoded: str) -> str:
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except (UnicodeDecodeError, ValueError):
        return ""


def _core_record_matches_filter(
    record: MemoryRecord, filters: MemoryFilter
) -> bool:
    if filters.states is not None:
        if record.state not in filters.states:
            return False
    elif not filters.include_inactive and record.state not in ACTIVE_MEMORY_STATES:
        return False
    if filters.kinds is not None and record.kind not in filters.kinds:
        return False
    if filters.actors is not None and record.actor not in filters.actors:
        return False
    if filters.exclude_actors is not None and record.actor in filters.exclude_actors:
        return False
    if filters.authorities is not None and record.authority not in filters.authorities:
        return False
    if (
        filters.exclude_authorities is not None
        and record.authority in filters.exclude_authorities
    ):
        return False
    if filters.tags is not None and not filters.tags.issubset(record.tags):
        return False
    if (
        filters.importance_min is not None
        and record.importance < filters.importance_min
    ):
        return False
    if filters.time_from is not None and record.created_at < filters.time_from:
        return False
    return not (
        filters.time_to is not None and record.created_at > filters.time_to
    )


def _core_record_valid_at(
    record: MemoryRecord, valid_at: datetime | None
) -> bool:
    if valid_at is None:
        return True
    valid_from = _record_valid_from(record)
    valid_to = _record_valid_to(record)
    if valid_from is not None and valid_from > valid_at:
        return False
    return not (valid_to is not None and valid_to < valid_at)


def _matches_filter(record: RecallResult, filters: MemoryFilter) -> bool:
    if filters.states is not None:
        if record.state not in filters.states:
            return False
    elif not filters.include_inactive and record.state not in ACTIVE_MEMORY_STATES:
        return False
    if filters.kinds is not None and record.kind not in filters.kinds:
        return False
    if filters.actors is not None and record.actor not in filters.actors:
        return False
    if filters.exclude_actors is not None and record.actor in filters.exclude_actors:
        return False
    if filters.authorities is not None and record.authority not in filters.authorities:
        return False
    if (
        filters.exclude_authorities is not None
        and record.authority in filters.exclude_authorities
    ):
        return False
    comparable_time = record.valid_at or record.extracted_at
    if filters.time_from is not None and (
        comparable_time is None or comparable_time < filters.time_from
    ):
        return False
    return not (
        filters.time_to is not None
        and (comparable_time is None or comparable_time > filters.time_to)
    )


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

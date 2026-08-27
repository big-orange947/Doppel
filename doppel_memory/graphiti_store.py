"""Experimental Graphiti/Neo4j integrations.

``GraphitiSemanticIndex`` is the preferred integration: a durable Store remains the
source of truth while Graphiti contributes graph-derived semantic candidates. The
legacy ``GraphitiMemoryStore`` remains temporarily available for migration, but it
cannot satisfy Doppel's core Store contract.
"""

from __future__ import annotations

import asyncio
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
    utc_now,
)
from doppel_memory.store import MemoryStore
from doppel_memory.vector import SemanticIndexUnavailableError

logger = logging.getLogger(__name__)
LOCAL_EMBEDDING_DIM = 512


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
    """A query requested filters Graphiti cannot represent without inventing data."""


@dataclass(frozen=True)
class GraphitiIndexResult:
    """Provenance returned after submitting one authoritative Store record."""

    memory_id: str
    episode_id: str
    scope_key: str


class GraphitiSemanticIndex:
    """Experimental Graphiti 0.29 semantic candidate index.

    The caller first commits a ``MemoryRecord`` to a conforming Store, then explicitly
    submits that authoritative record here. Graphiti facts remain derived candidates;
    they never become the lifecycle source of truth for the core record.
    """

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
        graphiti_client: Any | None = None,
    ) -> None:
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

    async def index_record(self, record: MemoryRecord) -> GraphitiIndexResult:
        if not self._enabled:
            raise GraphitiIndexUnavailableError("Graphiti semantic index is disabled")
        if not record.memory_id:
            raise ValueError(
                "Graphiti indexing requires a committed MemoryRecord with memory_id"
            )
        episode_id = str(
            uuid5(
                NAMESPACE_URL,
                f"doppel:{record.scope.scope_key}:{record.memory_id}",
            )
        )
        body = (
            f"[DOPPEL memory_id={record.memory_id} kind={record.kind} "
            f"actor={record.actor or '-'} authority={record.authority.value} "
            f"state={record.state.value}] {record.content}"
        )
        try:
            graphiti = await self._ensure_graphiti()
            result = await graphiti.add_episode(
                name=f"Doppel:{record.memory_id}",
                episode_body=body,
                source_description=record.extractor or "doppel",
                reference_time=record.created_at,
                group_id=record.scope.scope_key,
                uuid=episode_id,
            )
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti episode indexing failed: {exc}"
            ) from exc
        actual_episode_id = str(getattr(result.episode, "uuid", "") or episode_id)
        return GraphitiIndexResult(
            memory_id=record.memory_id,
            episode_id=actual_episode_id,
            scope_key=record.scope.scope_key,
        )

    async def search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
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
        unsupported = _unsupported_graphiti_filters(filter_obj)
        if unsupported:
            raise GraphitiFilterUnsupportedError(
                "Graphiti semantic search cannot honor filters: "
                + ", ".join(unsupported)
            )
        scope_by_key = {scope.scope_key: scope for scope in scopes}
        try:
            graphiti = await self._ensure_graphiti()
            edges = await graphiti.search(
                query=query.strip(),
                group_ids=list(scope_by_key),
                num_results=limit * 2,
            )
        except Exception as exc:
            raise GraphitiIndexUnavailableError(
                f"Graphiti semantic search failed: {exc}"
            ) from exc

        results: list[RecallResult] = []
        for edge in edges:
            fact = str(getattr(edge, "fact", "") or "").strip()
            group_id = str(getattr(edge, "group_id", "") or "")
            scope = scope_by_key.get(group_id)
            if not fact or scope is None:
                continue
            episodes = getattr(edge, "episodes", None) or []
            item = RecallResult(
                fact=fact,
                scope=scope,
                memory_id=str(getattr(edge, "uuid", "") or ""),
                source_episode=",".join(str(value) for value in episodes),
                extractor="graphiti",
                extracted_at=_optional_datetime(getattr(edge, "created_at", None)),
                valid_at=_optional_datetime(
                    getattr(edge, "valid_at", None)
                    or getattr(edge, "reference_time", None)
                ),
                state=_graphiti_edge_state(edge),
                derived_chain=["graphiti:0.29"],
            )
            if _matches_filter(item, filter_obj):
                results.append(item)
            if len(results) >= limit:
                break
        return results

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


def _unsupported_graphiti_filters(filters: MemoryFilter) -> list[str]:
    unsupported: list[str] = []
    for name in (
        "kinds",
        "actors",
        "authorities",
        "exclude_authorities",
        "exclude_actors",
        "tags",
        "importance_min",
    ):
        if getattr(filters, name) is not None:
            unsupported.append(name)
    return unsupported


def _graphiti_edge_state(edge: Any) -> MemoryState:
    now = utc_now()
    for name in ("invalid_at", "expired_at"):
        value = _optional_datetime(getattr(edge, name, None))
        if value is not None and value <= now:
            return MemoryState.EXPIRED
    return MemoryState.CONFIRMED


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

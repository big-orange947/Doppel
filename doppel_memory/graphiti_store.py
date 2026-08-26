"""Experimental Graphiti/Neo4j backend.

The adapter supports Graphiti 0.29.x construction, episode writes and semantic
search. Durable idempotency, state transitions and deletion remain unsupported;
callers can discover those limitations through capabilities and explicit errors.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

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
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
    WriteResult,
    WriteStatus,
)
from doppel_memory.store import MemoryStore

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


class GraphitiMemoryStore(MemoryStore):
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
        if not self._llm_api_key:
            raise RuntimeError("Graphiti backend requires llm_api_key")
        return Graphiti(
            uri=self._neo4j_uri,
            user=self._neo4j_user,
            password=self._neo4j_password,
            llm_client=OpenAIClient(
                LLMConfig(
                    api_key=self._llm_api_key,
                    model=self._llm_model or None,
                    base_url=self._llm_base_url or None,
                )
            ),
            embedder=FastEmbedderClient(),
            cross_encoder=NoOpCrossEncoder(),
        )


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
    return not (
        filters.exclude_authorities is not None
        and record.authority in filters.exclude_authorities
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

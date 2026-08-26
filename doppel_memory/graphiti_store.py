"""Graphiti + Neo4j 记忆存储实现（Doppel 高级后端，extra 安装 doppel-memory[graphiti]）。

经验来自 Memo Echo 项目 P-A 落地（graphiti-core==0.29.x）：
- 懒初始化：Neo4j 连接与 Graphiti 推迟到首次写入/检索，失败降级。
- group_id：只允许字母数字/短横线/下划线；用 MemoryScope.group_id 规范化。
- 首次 add_episode 不能传自定义 uuid（graphiti 会按已存在节点查询并抛错），
  幂等由本层 identity_key 注册表保证。
- Embedder：本地 fastembed（BAAI/bge-small-zh-v1.5，512 维），不依赖外网。
- Reranker：NoOpRerankerClient 保序，避免默认 OpenAIRerankerClient 缺 key 报错。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from datetime import datetime, timezone
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.config import LLMConfig

from doppel_memory.models import (
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
)
from doppel_memory.store import MemoryStore

logger = logging.getLogger(__name__)

LOCAL_EMBEDDING_DIM = 512
_GROUP_TOKEN_RE = re.compile(r"[^a-zA-Z0-9_-]")


class FastEmbedderClient(EmbedderClient):
    """直接用 fastembed 本地 bge-small-zh 的 Graphiti Embedder（512 维）。"""

    def __init__(self, config: EmbedderConfig | None = None) -> None:
        self.config = config or EmbedderConfig(embedding_dim=LOCAL_EMBEDDING_DIM)
        self._model: Any = None
        self._model_lock = asyncio.Lock()

    def _normalize_input(self, input_data: Any) -> list[str]:
        if isinstance(input_data, str):
            return [input_data]
        if isinstance(input_data, list) and all(isinstance(item, str) for item in input_data):
            return input_data
        raise TypeError(f"FastEmbedderClient only accepts text input, got {type(input_data)}")

    async def _ensure_model(self) -> Any:
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = await asyncio.to_thread(TextEmbedding, "BAAI/bge-small-zh-v1.5")
        return self._model

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await self._ensure_model()
        vectors = await asyncio.to_thread(list, model.embed(texts))
        return [[float(v) for v in vec] for vec in vectors]

    async def create(self, input_data: Any) -> list[float]:
        texts = self._normalize_input(input_data)
        return (await self._embed(texts))[0]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return await self._embed(input_data_list)


class NoOpRerankerClient:
    """保序 reranker：Graphiti 未配置时不用默认 OpenAIReranker（避免无 key 报错）。"""

    def __init__(self) -> None:
        from graphiti_core.reranker.client import RerankerConfig

        self.config = RerankerConfig()

    async def rerank(self, query: str, edges: list[Any]) -> list[Any]:
        return edges


class GraphitiMemoryStore(MemoryStore):
    """Graphiti/Neo4j 后端：事件/背景/关系都以 Episode 写入，语义+时间+scope 检索。"""

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
        self._lock = asyncio.Lock()
        self._seen_keys: dict[str, set[str]] = {}
        self._owner_samples: dict[str, deque[ChatMessage]] = {}
        self._capabilities = StoreCapabilities(
            semantic_search=True,
            full_text_search=False,
            temporal_search=True,
            graph_relations=True,
            metadata_filter=False,
            hard_delete=False,
            transactions=False,
            reranking=False,
        )

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    # ---------------------------------------------------------------- 写入

    async def write_event(self, scope: MemoryScope, message: ChatMessage) -> MemoryRecord:
        key = message.identity_key
        group = scope.group_id
        if key:
            seen = self._seen_keys.setdefault(group, set())
            if key in seen:
                return MemoryRecord(memory_id="", scope=scope)
            seen.add(key)
        if message.actor.value == "owner" and message.text:
            samples = self._owner_samples.setdefault(group, deque(maxlen=self._owner_sample_limit))
            samples.append(message)
        memory_id = await self._add_episode(
            group=group,
            name=f"会话事件:{group}",
            body=message.episode_line(),
            reference_time=message.at,
            source=f"event:{message.event_id or key or 'unspecified'}",
        )
        return MemoryRecord(
            memory_id=memory_id or "",
            kind=MemoryKind.EVENT,
            scope=scope,
            content=message.text,
            actor=message.actor.value,
            authority=message.fact_authority,
            state=MemoryState.CONFIRMED,
            source_event_id=message.event_id,
            source_message_id=message.message_id,
            extractor="ingestor",
            created_at=message.at or _now_iso(),
            updated_at=message.at or _now_iso(),
        )

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> MemoryRecord:
        group = scope.group_id
        tags_text = ",".join(tags or [])
        body = (
            f"[BACKGROUND importance={importance} source={source} tags={tags_text}] "
            f"{str(content or '').strip()}"
        )
        memory_id = await self._add_episode(
            group=group,
            name=f"背景:{group}",
            body=body,
            reference_time=_now_iso(),
            source=f"background:{source}",
        )
        return MemoryRecord(
            memory_id=memory_id or "",
            kind=MemoryKind.BACKGROUND,
            scope=scope,
            content=content,
            state=MemoryState.CONFIRMED,
            tags=list(tags or []),
            importance=importance,
            extractor=source,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )

    async def write_relation(
        self,
        scope: MemoryScope,
        *,
        counterpart: str,
        relationship: str = "",
        address: str = "",
        communication_preference: str = "",
        attributes: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        group = scope.group_id
        body = (
            f"[RELATION counterpart={counterpart} relationship={relationship} "
            f"address={address} pref={communication_preference}]"
        )
        memory_id = await self._add_episode(
            group=group,
            name=f"关系:{group}",
            body=body,
            reference_time=_now_iso(),
            source=f"relation:{counterpart}",
        )
        return MemoryRecord(
            memory_id=memory_id or "",
            kind=MemoryKind.RELATION,
            scope=scope,
            content=body,
            state=MemoryState.CONFIRMED,
            extractor="relation_writer",
            created_at=_now_iso(),
            updated_at=_now_iso(),
            metadata={
                "counterpart": counterpart,
                "relationship": relationship,
                "address": address,
                "communication_preference": communication_preference,
                **(attributes or {}),
            },
        )

    async def _add_episode(
        self,
        *,
        group: str,
        name: str,
        body: str,
        reference_time: str,
        source: str,
    ) -> str | None:
        try:
            graphiti = await self._ensure_graphiti()
            await graphiti.add_episode(
                name=name,
                episode_body=body,
                source_description=source,
                reference_time=_parse_time(reference_time),
                group_id=_normalize_group(group),
            )
            return f"{group}:{len(body)}:{hash(body) & 0xFFFFFFFF:08x}"
        except Exception as exc:  # noqa: BLE001 — 降级不阻断
            logger.warning("Graphiti episode write degraded: %s", exc)
            return None

    # ---------------------------------------------------------------- 检索

    async def search(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "search requires explicit scopes; Doppel refuses unscoped search."
            )
        if not self._enabled or not str(query or "").strip():
            return []
        filter_obj = filters or MemoryFilter()
        try:
            graphiti = await self._ensure_graphiti()
            group_ids = [_normalize_group(scope.group_id) for scope in scopes]
            edges = await graphiti.search(query=query, group_ids=group_ids, num_results=limit * 2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Graphiti search degraded: %s", exc)
            return []
        results: list[RecallResult] = []
        for edge in edges:
            fact = str(getattr(edge, "fact", "") or "").strip()
            if not fact:
                continue
            record = self._edge_to_recall(edge, fact)
            if not self._matches_filter(record, filter_obj):
                continue
            results.append(record)
        return results[:limit]

    async def list_recent_owner_messages(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[ChatMessage]:
        samples = self._owner_samples.get(scope.group_id)
        if not samples:
            return []
        return list(samples)[-limit:]

    # ---------------------------------------------------------------- 管理

    async def forget(self, memory_id: str, *, hard: bool = False) -> bool:
        if hard:
            raise NotImplementedError(
                "Graphiti backend does not support hard delete; use soft forget."
            )
        # S1：软删记录到内存；完整删除随治理阶段（P-E）提供。
        logger.info("forget(%s) soft-recorded for governance phase", memory_id)
        return True

    async def health(self) -> dict[str, Any]:
        if not self._enabled:
            return {"enabled": False, "ok": False, "reason": "disabled"}
        try:
            await self._ensure_graphiti()
            return {"enabled": True, "ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"enabled": True, "ok": False, "reason": str(exc)}

    async def close(self) -> None:
        if self._graphiti is not None:
            try:
                await self._graphiti.close()
            except Exception:  # noqa: BLE001
                logger.debug("graphiti close failed", exc_info=True)
            self._graphiti = None

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _edge_to_recall(edge: Any, fact: str) -> RecallResult:
        kind = MemoryKind.EVENT
        if fact.startswith("[BACKGROUND"):
            kind = MemoryKind.BACKGROUND
        elif fact.startswith("[RELATION"):
            kind = MemoryKind.RELATION
        return RecallResult(
            fact=fact,
            kind=kind,
            source_episode=str(getattr(edge, "episodes", "") or ""),
            valid_at=str(getattr(edge, "valid_at", "") or ""),
        )

    @staticmethod
    def _matches_filter(record: RecallResult, f: MemoryFilter) -> bool:
        if f.kinds is not None and record.kind not in f.kinds:
            return False
        if f.actors is not None and record.actor not in f.actors:
            return False
        if f.exclude_actors is not None and record.actor in f.exclude_actors:
            return False
        if f.authorities is not None and record.authority not in f.authorities:
            return False
        if f.exclude_authorities is not None and record.authority in f.exclude_authorities:
            return False
        return True

    # ---------------------------------------------------------------- 初始化

    async def _ensure_graphiti(self) -> Graphiti:
        if self._graphiti is not None:
            return self._graphiti
        async with self._lock:
            if self._graphiti is None:
                self._graphiti = self._build_graphiti()
        return self._graphiti

    def _build_graphiti(self) -> Graphiti:
        if not self._llm_api_key:
            raise RuntimeError(
                "Doppel Graphiti backend needs an LLM: pass llm_api_key / llm_base_url / llm_model"
            )
        graphiti = Graphiti(
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
            cross_encoder=NoOpRerankerClient(),
        )
        logger.info(
            "doppel graphiti ready: uri=%s model=%s embedder=local(bge-small-zh,512)",
            self._neo4j_uri,
            self._llm_model or "default",
        )
        return graphiti


def _normalize_group(raw: str) -> str:
    return _GROUP_TOKEN_RE.sub("_", str(raw or "").strip())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

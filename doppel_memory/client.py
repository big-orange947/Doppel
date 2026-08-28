"""Doppel 门面（三层 API）。

低层：``client.store`` 直连后端（write/search/delete，开发者完全控制）。
中层：``ingest`` / ``process`` / ``recall``（标准事件与可插拔 proposal 管线）。
高层：``materials``（结构化材料 + 可替换 renderer + persona preset）。

```python
from doppel_memory import DoppelClient, MemoryScope

memory = DoppelClient(backend="sqlite")          # 零配置默认
await memory.ingest(scope, msg)                   # ① 喂消息（自动记忆，幂等）
bundle = await memory.materials(scope, query)     # ② 拿结构化记忆材料
prompt_block = bundle.render()                    # ③ 拼进你自己的 prompt
```
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from doppel_memory.batch import (
    BatchCheckpoint,
    BatchProposalPolicy,
    BatchReadLimits,
    BatchRunResult,
    BatchTaskRunner,
    HistoryWindow,
    MemoryBatchTask,
    ScopedHistoryReader,
    ScopedMemoryReader,
)
from doppel_memory.consolidation import (
    ConsolidationCheckpoint,
    ConsolidationConfig,
    ConsolidationRunner,
    ConsolidationRunResult,
    MemoryConsolidator,
)
from doppel_memory.imports import IMImportBatch, ImportResult
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    ChatMessage,
    MemoryFilter,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
    WriteResult,
    WriteStatus,
    utc_now,
)
from doppel_memory.persona import MaterialBundle, PersonaMaterialsBuilder
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.processing import (
    MemoryPipeline,
    MemoryProcessor,
    ProcessingResult,
    ProcessorHooks,
    ProposalEvaluator,
    ProposalPolicy,
)
from doppel_memory.query import (
    DeterministicPersonalMemoryQueryPlanner,
    PersonalMemoryQueryConfig,
    PersonalMemoryQueryEngine,
    PersonalMemoryQueryPlanner,
    PersonalMemoryQueryResult,
)
from doppel_memory.retriever import Reranker, RetrievalStrategy, Retriever
from doppel_memory.sqlite_store import SQLiteStore
from doppel_memory.store import MemoryStore
from doppel_memory.style import StyleGuideCompiler
from doppel_memory.vector import SemanticIndex


class DoppelClient:
    """记忆框架统一入口；记忆材料提供商，不包含对话引擎职责。"""

    def __init__(
        self,
        store: MemoryStore | None = None,
        *,
        backend: str = "sqlite",
        retrieval_strategy: RetrievalStrategy | None = None,
        reranker: Reranker | None = None,
        candidate_multiplier: int = 4,
        **backend_kwargs: Any,
    ) -> None:
        if store is None:
            if backend == "sqlite":
                store = SQLiteStore(**backend_kwargs)
            elif backend == "memory":
                store = InMemoryStore()
            elif backend in {"postgres", "postgresql"}:
                store = PostgreSQLStore(**backend_kwargs)
            elif backend == "graphiti":
                store = _build_graphiti_store(**backend_kwargs)
            else:
                raise ValueError(
                    f"unknown backend: {backend!r} "
                    "(supported: sqlite/memory/postgres/graphiti)"
                )
        self._store = store
        self._retriever = Retriever(
            store,
            strategy=retrieval_strategy,
            reranker=reranker,
            candidate_multiplier=candidate_multiplier,
        )
        self._materials = PersonaMaterialsBuilder(self._retriever, store=self._store)

    @property
    def store(self) -> MemoryStore:
        """低层 API：直连后端（能力声明见 store.capabilities）。"""
        return self._store

    @property
    def is_enabled(self) -> bool:
        return self._store.is_enabled

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._store.capabilities

    # ---------------------------------------------------------------- 中层 API

    async def ingest(self, scope: MemoryScope, message: ChatMessage) -> WriteResult:
        """写入一条聊天事件，返回可区分成功/重复/失败的结果。"""
        return await self._store.write_event(scope, message)

    async def process(
        self,
        scope: MemoryScope,
        message: ChatMessage,
        *,
        processors: Sequence[MemoryProcessor] | None = None,
        policy: ProposalPolicy | None = None,
        hooks: ProcessorHooks | None = None,
        allowed_scopes: Sequence[MemoryScope] | None = None,
    ) -> ProcessingResult:
        """Run pluggable proposal processors and persist policy-approved results."""

        pipeline = MemoryPipeline(
            self._store,
            processors or (),
            policy=policy,
            hooks=hooks,
        )
        return await pipeline.run(scope, message, allowed_scopes=allowed_scopes)

    async def run_batch_task(
        self,
        task: MemoryBatchTask,
        scope: MemoryScope,
        window: HistoryWindow,
        *,
        checkpoint: BatchCheckpoint | None = None,
        history: ScopedHistoryReader | None = None,
        memories: ScopedMemoryReader | None = None,
        read_scopes: Sequence[MemoryScope] | None = None,
        allowed_scopes: Sequence[MemoryScope] | None = None,
        policy: BatchProposalPolicy | None = None,
        hooks: ProcessorHooks | None = None,
        read_limits: BatchReadLimits | None = None,
        run_id: str | None = None,
    ) -> BatchRunResult:
        """Run one host-scheduled history aggregation task."""

        return await BatchTaskRunner(self._store).run_once(
            task,
            scope,
            window,
            checkpoint=checkpoint,
            history=history,
            memories=memories,
            read_scopes=read_scopes,
            allowed_scopes=allowed_scopes,
            policy=policy,
            hooks=hooks,
            read_limits=read_limits,
            run_id=run_id,
        )

    async def consolidate(
        self,
        consolidator: MemoryConsolidator,
        scope: MemoryScope,
        *,
        checkpoint: ConsolidationCheckpoint | None = None,
        config: ConsolidationConfig | None = None,
        evaluator: ProposalEvaluator | None = None,
        hooks: ProcessorHooks | None = None,
        run_id: str | None = None,
    ) -> ConsolidationRunResult:
        """Plan and execute one exact-scope personal-memory consolidation cycle."""

        return await ConsolidationRunner(self._store, config).run_once(
            consolidator,
            scope,
            checkpoint=checkpoint,
            evaluator=evaluator,
            hooks=hooks,
            run_id=run_id,
        )

    async def put(
        self, record: MemoryRecord, *, idempotency_key: str | None = None
    ) -> WriteResult:
        """通用记忆写入入口，供自定义 kind 与未来 Processor 使用。"""
        return await self._store.put(record, idempotency_key=idempotency_key)

    async def ingest_messages(
        self,
        scope: MemoryScope,
        messages: list[ChatMessage],
        *,
        batch_size: int = 8,
        progress=None,
    ) -> dict[str, Any]:
        """批量导入历史聊天记录并自动记忆（冷启动/历史迁移，幂等）。"""
        accepted = 0
        skipped = 0
        failed = 0
        total = len(messages)
        normalized_batch_size = max(1, batch_size)
        for start in range(0, total, normalized_batch_size):
            batch = messages[start : start + normalized_batch_size]
            for message in batch:
                result = await self.ingest(scope, message)
                if result.accepted:
                    accepted += 1
                elif result.status is WriteStatus.FAILED:
                    failed += 1
                else:
                    skipped += 1
            if progress:
                progress(min(start + len(batch), total), total)
        batch_count = (total + normalized_batch_size - 1) // normalized_batch_size
        return {
            "accepted": accepted,
            "skipped": skipped,
            "failed": failed,
            "batchCount": batch_count,
        }

    async def import_batch(
        self,
        batch: IMImportBatch,
        *,
        progress: Callable[[int, int], None] | None = None,
    ) -> ImportResult:
        """Import a portable multi-scope IM batch using normal event idempotency."""

        results: list[WriteResult] = []
        total = len(batch.items)
        for index, item in enumerate(batch.items, start=1):
            source_identity = item.source_id or (
                f"{batch.batch_id}:{index}" if batch.batch_id else ""
            )
            import_provenance = {
                "source": batch.source,
                "source_version": batch.source_version,
                "batch_id": batch.batch_id,
                "source_id": item.source_id,
                "item_metadata": item.metadata,
            }
            raw = dict(item.message.raw)
            raw["doppel_import"] = import_provenance
            fallback_event_id = (
                f"import:{batch.source}:{source_identity}"
                if source_identity and not item.message.identity_key
                else item.message.event_id
            )
            message = item.message.model_copy(
                update={"event_id": fallback_event_id, "raw": raw}, deep=True
            )
            results.append(await self.ingest(item.scope, message))
            if progress is not None:
                progress(index, total)
        return ImportResult.summarize(results)

    async def recall(
        self,
        query: str,
        scopes: list[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> list[RecallResult]:
        """中层检索：scope 显式 + filters 组合。"""
        return await self._retriever.recall(query, scopes, filters=filters, limit=limit)

    async def query_personal_memory(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        planner: PersonalMemoryQueryPlanner | None = None,
        now: datetime | None = None,
        config: PersonalMemoryQueryConfig | None = None,
        semantic_index: SemanticIndex | None = None,
        default_subject: str = "owner",
        default_subject_id: str = "",
        allowed_subject_ids: Sequence[str] = (),
    ) -> PersonalMemoryQueryResult:
        """Return structured personal-memory evidence and safe aggregation."""

        return await PersonalMemoryQueryEngine(
            self._store, config, semantic_index=semantic_index
        ).query(
            planner or DeterministicPersonalMemoryQueryPlanner(),
            query,
            scopes,
            now=now or utc_now(),
            default_subject=default_subject,
            default_subject_id=default_subject_id,
            allowed_subject_ids=allowed_subject_ids,
        )

    # ---------------------------------------------------------------- 高层 API

    async def materials(
        self,
        scope: MemoryScope,
        query: str = "",
        *,
        scopes: list[MemoryScope] | None = None,
        memory_limit: int = 10,
        style_sample_limit: int = 5,
        policy=None,
        style_professor: StyleGuideCompiler | None = None,
    ) -> MaterialBundle:
        """高层材料装配：结构化记忆、风格 profile/guidance 与 provenance。

        ``policy`` 默认 OwnerPersonaPolicy（会话级 + 联系人级 + 用户全局层）；
        显式传 ``scopes`` 可完全接管检索范围。
        """
        return await self._materials.build(
            scope,
            query,
            scopes=scopes,
            memory_limit=memory_limit,
            style_sample_limit=style_sample_limit,
            policy=policy,
            style_professor=style_professor,
        )

    async def persona_materials(
        self, scope: MemoryScope, query: str = ""
    ) -> MaterialBundle:
        """preset 快捷方式：owner_persona（与 materials 默认策略一致）。"""
        return await self.materials(scope, query)

    async def owner_style_samples(
        self, scope: MemoryScope, *, limit: int = 5
    ) -> list[str]:
        return await self._retriever.owner_style_samples(scope, limit=limit)

    # ---------------------------------------------------------------- 写入

    async def write_background(
        self,
        scope: MemoryScope,
        content: str,
        tags: list[str] | None = None,
        *,
        importance: float = 0.5,
        source: str = "manual",
    ) -> WriteResult:
        return await self._store.write_background(
            scope, content, tags, importance=importance, source=source
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
    ) -> WriteResult:
        return await self._store.write_relation(
            scope,
            counterpart=counterpart,
            relationship=relationship,
            address=address,
            communication_preference=communication_preference,
            attributes=attributes,
        )

    # ---------------------------------------------------------------- 管理

    async def get(self, scope: MemoryScope, memory_id: str) -> MemoryRecord | None:
        return await self._store.get(scope, memory_id)

    async def transition(
        self,
        scope: MemoryScope,
        memory_id: str,
        to_state: MemoryState,
        *,
        expected_state: MemoryState | None = None,
    ) -> MemoryRecord:
        return await self._store.transition(
            scope,
            memory_id,
            to_state,
            expected_state=expected_state,
        )

    async def forget(
        self, scope: MemoryScope, memory_id: str, *, hard: bool = False
    ) -> bool:
        return await self._store.forget(scope, memory_id, hard=hard)

    async def health(self) -> dict[str, Any]:
        return await self._store.health()

    async def close(self) -> None:
        await self._store.close()


def _build_graphiti_store(**kwargs: Any) -> MemoryStore:
    try:
        from doppel_memory.graphiti_store import GraphitiMemoryStore
    except ImportError as exc:
        raise RuntimeError(
            "Graphiti backend is optional; install doppel-memory[graphiti]"
        ) from exc

    return GraphitiMemoryStore(**kwargs)

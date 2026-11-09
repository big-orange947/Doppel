"""Single-writer host recipe; durable plans, not an installed core API or scheduler."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from doppel_memory import (
    BatchCheckpoint,
    BatchProposalPlan,
    BatchTaskRunner,
    ConsolidationCheckpoint,
    ConsolidationConfig,
    ConsolidationPlan,
    ConsolidationRunner,
    HistoryWindow,
    IndexMaintainer,
    IndexMaintenanceCheckpoint,
    IndexWriter,
    MemoryConsolidator,
    MemoryScope,
    MemoryStore,
    PersonalMemoryMiner,
)


class WorkflowState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    binding: str
    window: HistoryWindow
    stage: Literal["batch", "consolidation", "index", "complete"] = "batch"
    batch_checkpoint: BatchCheckpoint | None = None
    consolidation_checkpoint: ConsolidationCheckpoint | None = None
    index_checkpoint: IndexMaintenanceCheckpoint | None = None
    pending_batch: BatchProposalPlan | None = None
    pending_consolidation: ConsolidationPlan | None = None
    revision: int = Field(default=0, ge=0)


def _digest(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class PersonalMemoryWorkflow:
    """One bounded step; host owns authorization, scheduling and an exclusive lease.

    Windows must be closed, ordered and non-overlapping. Late events behind the
    history cursor require a separate backfill job. One instance/worker per state
    file: atomic replacement is crash-safe publication, not distributed locking.
    """

    def __init__(
        self,
        directory: Path,
        *,
        workflow_key: str,
        store: MemoryStore,
        scope: MemoryScope,
        miner: PersonalMemoryMiner,
        consolidator: MemoryConsolidator,
        index: IndexWriter,
        consolidation_config: ConsolidationConfig | None = None,
        index_page_size: int = 100,
    ) -> None:
        if (
            not workflow_key.strip()
            or type(index_page_size) is not int
            or index_page_size < 1
        ):
            raise ValueError("workflow key and positive page size required")
        if miner.config.owner_target_scope != "conversation":
            raise ValueError(
                "reference workflow only writes its exact conversation scope"
            )
        self.store, self.scope, self.miner = store, scope, miner
        self.consolidator = consolidator
        self.runner = ConsolidationRunner(store, consolidation_config)
        self.maintainer = IndexMaintainer(store, index)
        self.page_size = index_page_size
        self.binding = _digest(
            {
                "schema": 1,
                "workflow_key": workflow_key,
                "scope": scope.scope_key,
                "miner": miner.checkpoint_key,
                "consolidator": [consolidator.name, consolidator.version],
                "consolidator_config": getattr(
                    getattr(consolidator, "config", None), "fingerprint", ""
                ),
                "runner_config": self.runner.config.fingerprint,
                "index": index.identity,
            }
        )
        # Keep the path stable when model/config changes, so drift is rejected.
        self.path = directory / (
            _digest({"key": workflow_key, "scope": scope.scope_key}) + ".json"
        )
        self._lock = asyncio.Lock()

    async def _save(self, state: WorkflowState) -> None:
        payload = state.model_dump_json(indent=2)

        def write() -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + "." + uuid4().hex + ".tmp")
            try:
                with temporary.open("x", encoding="utf-8") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)

        await asyncio.to_thread(write)

    async def step(self, window: HistoryWindow) -> dict:
        async with self._lock:
            return await self._step(window)

    async def _step(self, window: HistoryWindow) -> dict:
        if self.path.exists():
            state = WorkflowState.model_validate_json(
                await asyncio.to_thread(self.path.read_text, encoding="utf-8")
            )
            if state.binding != self.binding:
                raise ValueError(
                    "workflow configuration changed; migrate or use a new job"
                )
            if state.window != window:
                if state.stage != "complete" or window.start <= state.window.end:
                    raise ValueError(
                        "finish the pending window before a later non-overlapping window"
                    )
                state.window = window.model_copy(deep=True)
                state.stage = "batch"
        else:
            state = WorkflowState(
                binding=self.binding, window=window.model_copy(deep=True)
            )
            await self._save(state)
        stage = state.stage
        if stage == "complete":
            return {"ok": True, "stage": stage, "complete": True}

        if stage == "batch":
            original = self.miner
            workflow = self

            class SavedMiner:
                name, version = original.name, original.version
                checkpoint_schema_version = original.checkpoint_schema_version

                async def propose(self, context):
                    if state.pending_batch is None:
                        state.pending_batch = BatchProposalPlan.model_validate(
                            await original.propose(context)
                        ).model_copy(deep=True)
                        await workflow._save(state)  # before any proposal writes
                    return state.pending_batch.model_copy(deep=True)

            result = await BatchTaskRunner(self.store).run_once(
                SavedMiner(),
                self.scope,
                state.window,
                checkpoint=state.batch_checkpoint,
            )
            if result.errors or result.committable_checkpoint is None:
                return {
                    "ok": False,
                    "stage": stage,
                    "complete": False,
                    "errors": [error.stage for error in result.errors],
                }
            state.batch_checkpoint = result.committable_checkpoint
            state.pending_batch = None
            if not state.batch_checkpoint.metadata.get("truncated", False):
                state.stage = "consolidation"

        elif stage == "consolidation":
            if state.pending_consolidation is None:
                state.pending_consolidation = await self.runner.plan_once(
                    self.consolidator,
                    self.scope,
                    checkpoint=state.consolidation_checkpoint,
                )
                await self._save(state)  # before canonical writes/source transitions
            if (
                state.pending_consolidation.scope.scope_key != self.scope.scope_key
                or state.pending_consolidation.consolidator != self.consolidator.name
                or state.pending_consolidation.consolidator_version
                != self.consolidator.version
                or state.pending_consolidation.config_fingerprint
                != self.runner.config.fingerprint
            ):
                raise ValueError(
                    "saved consolidation plan does not belong to this workflow"
                )
            result = await self.runner.execute(state.pending_consolidation)
            if result.errors or result.committable_checkpoint is None:
                return {
                    "ok": False,
                    "stage": stage,
                    "complete": False,
                    "errors": [error.stage for error in result.errors],
                }
            state.consolidation_checkpoint = result.committable_checkpoint
            state.pending_consolidation = None
            state.stage = "index"

        elif stage == "index":
            report = await self.maintainer.reconcile(
                self.scope, checkpoint=state.index_checkpoint, page_size=self.page_size
            )
            if not report.ok or report.committable_checkpoint is None:
                return {
                    "ok": False,
                    "stage": stage,
                    "complete": False,
                    "errors": [failure.stage for failure in report.failures],
                }
            state.index_checkpoint = report.committable_checkpoint
            if report.complete:
                state.stage = "complete"

        state.revision += 1
        await self._save(state)
        return {
            "ok": True,
            "stage": stage,
            "next_stage": state.stage,
            "complete": state.stage == "complete",
        }

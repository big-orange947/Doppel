"""Local content-only CrossEncoder adapter for attributed context candidates.

No relation/entity/intent metadata is injected. This harness is not a framework
provider default. Requested model, tokenizer cap and device are explicit. Invalid
scores/timeout/limits fail the reranked profile; base order is never mislabeled as
a successful reranker execution.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import math
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

from doppel_memory.models import RecallResult
from doppel_memory.personal_rerank import (
    PersonalMemoryRerankConfig,
    PersonalMemoryRerankItem,
    PersonalMemoryRerankRequest,
    PersonalMemoryRerankScore,
    PersonalMemoryRerankSummary,
    score_personal_memories,
)


class LocalContextCrossEncoder:
    def __init__(
        self,
        model_path: Path,
        *,
        device: str = "cuda",
        max_length: int = 8192,
        batch_size: int = 1,
    ) -> None:
        if not model_path.is_dir():
            raise ValueError("reranker requires an existing local model directory")
        if (
            type(max_length) is not int
            or max_length < 1
            or type(batch_size) is not int
            or batch_size < 1
        ):
            raise ValueError("reranker token cap and batch size must be positive")
        self.path = model_path.resolve()
        self.artifact_sha256 = {}
        for file in sorted(self.path.iterdir()):
            if file.is_file() and file.suffix in {
                ".json",
                ".safetensors",
                ".bin",
                ".model",
            }:
                digest = hashlib.sha256()
                with file.open("rb") as source:
                    for block in iter(lambda: source.read(8_388_608), b""):
                        digest.update(block)
                self.artifact_sha256[file.name] = digest.hexdigest()
        self.device, self.max_length, self.batch_size = device, max_length, batch_size
        self.name = f"local-cross-encoder:{self.path.name}"
        self.version = f"{version('sentence-transformers')};raw-logit-sigmoid;max_length={max_length}"
        self._model: Any = None
        self._lock = asyncio.Lock()
        self.calls = 0
        self.pairs_scored = 0
        self.truncated_pairs = 0
        self.longest_pair_tokens = 0

    async def _ensure_model(self) -> Any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    module = importlib.import_module("sentence_transformers")
                    self._model = await asyncio.to_thread(
                        module.CrossEncoder,
                        str(self.path),
                        device=self.device,
                        max_length=self.max_length,
                        local_files_only=True,
                    )
        return self._model

    async def rerank(
        self, request: PersonalMemoryRerankRequest
    ) -> Sequence[PersonalMemoryRerankScore]:
        if not request.items:
            return []
        model = await self._ensure_model()
        pairs = [(request.question, item.content) for item in request.items]

        def predict() -> tuple[list[float], list[int]]:
            lengths = list(
                model.tokenizer(
                    [pair[0] for pair in pairs],
                    [pair[1] for pair in pairs],
                    truncation=False,
                    padding=False,
                    return_length=True,
                    verbose=False,
                )["length"]
            )
            raw = model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                activation_fn=lambda value: value,
            )
            return [float(value) for value in raw], lengths

        values, lengths = await asyncio.to_thread(predict)
        if len(values) != len(request.items) or len(lengths) != len(request.items):
            raise ValueError(
                "reranker returned mismatched number of scores/token counts"
            )
        result = []
        for item, value in zip(request.items, values, strict=True):
            if not math.isfinite(value):
                raise ValueError("reranker returned nonfinite logit")
            score = (
                1 / (1 + math.exp(-value))
                if value >= 0
                else math.exp(value) / (1 + math.exp(value))
            )
            result.append(PersonalMemoryRerankScore(item_id=item.item_id, score=score))
        self.calls += 1
        self.pairs_scored += len(pairs)
        self.truncated_pairs += sum(length > self.max_length for length in lengths)
        self.longest_pair_tokens = max(
            self.longest_pair_tokens, max(lengths, default=0)
        )
        return result

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "model_path": str(self.path),
            "device_requested": self.device,
            "device_actual": str(getattr(self._model, "device", "not_loaded")),
            "model_artifact_sha256": self.artifact_sha256,
            "max_length": self.max_length,
            "batch_size": self.batch_size,
            "calls": self.calls,
            "pairs_scored": self.pairs_scored,
            "truncated_pairs": self.truncated_pairs,
            "longest_pair_tokens": self.longest_pair_tokens,
            "input_policy": "question-and-authorized-raw-text-only-no-metadata",
        }


class StrictContextReranker:
    """Reorder existing snapshots with production bounded score validation."""

    def __init__(
        self, provider: Any, config: PersonalMemoryRerankConfig | None = None
    ) -> None:
        self.provider = provider
        self.config = config or PersonalMemoryRerankConfig(
            max_candidates=80,
            max_input_chars=1_000_000,
            timeout_seconds=300,
        )
        self.last_summary: PersonalMemoryRerankSummary | None = None
        self.last_order: list[str] = []

    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ) -> Sequence[RecallResult]:
        bound = [item.model_copy(deep=True) for item in candidates]
        request = PersonalMemoryRerankRequest(
            question=query,
            items=[
                PersonalMemoryRerankItem(
                    item_id=f"candidate-{index}", content=item.raw_text or item.fact
                )
                for index, item in enumerate(bound)
            ],
        )
        scores, summary = await score_personal_memories(
            self.provider,
            request,
            self.config,
            total_candidates=len(bound),
        )
        self.last_summary = summary
        if summary.status not in {"completed", "not_run"}:
            raise RuntimeError(
                f"reranked context profile did not execute: {summary.status}"
            )
        order = sorted(
            range(len(bound)), key=lambda index: (-scores[f"candidate-{index}"], index)
        )
        self.last_order = [bound[index].memory_id for index in order]
        # Source snapshot is preserved. Score affects order only, not authority.
        return [bound[index] for index in order[:limit]]

"""Offline-only service providers, independent of frozen benchmark harnesses."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import math
import threading
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

from doppel_memory.models import RecallResult


def model_fingerprint(path: Path) -> str:
    if not path.is_dir():
        raise ValueError("an existing local model directory is required")
    artifacts = {}
    for file in sorted(path.rglob("*")):
        if file.is_file() and file.suffix in {
            ".json",
            ".onnx",
            ".data",
            ".safetensors",
            ".bin",
            ".model",
            ".txt",
        }:
            digest = hashlib.sha256()
            with file.open("rb") as stream:
                for block in iter(lambda: stream.read(8_388_608), b""):
                    digest.update(block)
            artifacts[file.relative_to(path).as_posix()] = digest.hexdigest()
    if not artifacts:
        raise ValueError("no local model artifacts found")
    return hashlib.sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()


class LocalEmbedding:
    """The existing small Chinese BGE profile, explicitly CPU and offline."""

    name = "fastembed:BAAI/bge-small-zh-v1.5"
    dimensions = 512

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.version = (
            f"{version('fastembed')};local-artifacts={model_fingerprint(self.path)}"
        )
        self.identity = {
            "name": self.name,
            "version": self.version,
            "dimensions": self.dimensions,
            "device": "cpu",
        }
        self._model: Any = None
        self._lock = threading.Lock()

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []

        def encode():
            with self._lock:
                if self._model is None:
                    module = importlib.import_module("fastembed")
                    self._model = module.TextEmbedding(
                        "BAAI/bge-small-zh-v1.5",
                        specific_model_path=str(self.path),
                        local_files_only=True,
                        providers=["CPUExecutionProvider"],
                    )
                vectors = [
                    list(map(float, v))
                    for v in self._model.embed(list(texts), batch_size=32)
                ]
                if len(vectors) != len(texts) or any(
                    len(v) != self.dimensions
                    or not all(math.isfinite(x) for x in v)
                    or not any(v)
                    for v in vectors
                ):
                    raise ValueError("invalid local embedding shape or values")
                return vectors

        return await asyncio.to_thread(encode)


class LocalCrossEncoder:
    """Reorder only the authorized 80-window; invalid output fails the profile."""

    def __init__(self, path: Path, *, device: str = "cpu"):
        self.path = path.resolve()
        self.identity = {
            "artifacts": model_fingerprint(self.path),
            "package": version("sentence-transformers"),
            "device": device,
            "max_length": 8192,
            "batch_size": 1,
            "input": "question-and-source-text-only",
            "scores": "raw-logit-order",
        }
        self.device = device
        self._model: Any = None
        self._lock = threading.Lock()
        self.calls = self.truncated_pairs = 0

    def _load(self):
        if self._model is None:
            module = importlib.import_module("sentence_transformers")
            self._model = module.CrossEncoder(
                str(self.path),
                device=self.device,
                max_length=8192,
                local_files_only=True,
                trust_remote_code=False,
            )
        return self._model

    async def warmup(self):
        def load():
            with self._lock:
                self._load()

        await asyncio.to_thread(load)

    async def rerank(
        self, query: str, candidates: Sequence[RecallResult], *, limit: int
    ):
        bound = [item.model_copy(deep=True) for item in candidates]
        if (
            len(bound) > 80
            or len(query) + sum(len(c.raw_text or c.fact) for c in bound) > 1_000_000
        ):
            raise ValueError("local reranker candidate/input cap exceeded")
        if not bound:
            return []
        pairs = [(query, c.raw_text or c.fact) for c in bound]

        def predict():
            with self._lock:
                model = self._load()
                lengths = model.tokenizer(
                    [p[0] for p in pairs],
                    [p[1] for p in pairs],
                    truncation=False,
                    padding=False,
                    return_length=True,
                    verbose=False,
                )["length"]
                values = [
                    float(v)
                    for v in model.predict(
                        pairs,
                        batch_size=1,
                        show_progress_bar=False,
                        convert_to_numpy=True,
                        activation_fn=lambda value: value,
                    )
                ]
                if (
                    len(values) != len(bound)
                    or len(lengths) != len(bound)
                    or not all(map(math.isfinite, values))
                ):
                    raise ValueError("invalid local reranker scores")
                self.calls += 1
                self.truncated_pairs += sum(length > 8192 for length in lengths)
                return values

        scores = await asyncio.to_thread(predict)
        order = sorted(range(len(bound)), key=lambda i: (-scores[i], i))
        return [bound[i] for i in order[:limit]]

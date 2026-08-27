"""Correctness-gated pgvector and hybrid retrieval benchmark."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import (
    HybridRetrievalStrategy,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PostgreSQLStore,
    PostgreSQLVectorIndex,
    Retriever,
    VectorIndexConfig,
    WriteStatus,
    __version__,
)
from doppel_memory.models import utc_now

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "vector-quality-v1.json"


class VectorQualityScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    user_id: str
    agent_id: str = "benchmark-agent"
    chat_id: str

    def to_scope(self) -> MemoryScope:
        return MemoryScope(
            user_id=self.user_id,
            agent_id=self.agent_id,
            platform="vector-benchmark",
            chat_type="private",
            chat_id=self.chat_id,
        )


class VectorQualityRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_id: str
    scope: str
    content: str
    embedding: list[float]
    tags: list[str] = Field(default_factory=list)


class VectorQualityQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    scope: str
    text: str
    embedding: list[float]
    expected_memory_id: str
    forbidden_memory_ids: list[str] = Field(min_length=1)


class VectorQualityDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: Literal[1] = 1
    name: str
    provider_name: str
    provider_version: str
    dimensions: int = Field(ge=1, le=2000)
    scopes: list[VectorQualityScope] = Field(min_length=2)
    records: list[VectorQualityRecord] = Field(min_length=2)
    queries: list[VectorQualityQuery] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_references(self) -> VectorQualityDataset:
        scope_names = {scope.name for scope in self.scopes}
        if len(scope_names) != len(self.scopes):
            raise ValueError("vector quality scope names must be unique")
        record_ids = {record.memory_id for record in self.records}
        if len(record_ids) != len(self.records):
            raise ValueError("vector quality memory IDs must be unique")
        inputs: set[str] = set()
        for item in [*self.records, *self.queries]:
            if item.scope not in scope_names:
                raise ValueError(f"unknown vector quality scope: {item.scope}")
            if len(item.embedding) != self.dimensions:
                raise ValueError("fixture embedding dimensions do not match dataset")
            input_text = (
                item.content if isinstance(item, VectorQualityRecord) else item.text
            )
            if input_text in inputs:
                raise ValueError("provider fixture inputs must be unique")
            inputs.add(input_text)
        for query in self.queries:
            if query.expected_memory_id not in record_ids:
                raise ValueError("query expected memory ID does not exist")
            if not set(query.forbidden_memory_ids).issubset(record_ids):
                raise ValueError("query forbidden memory ID does not exist")
        return self

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()


class FixtureEmbeddingProvider:
    def __init__(self, dataset: VectorQualityDataset) -> None:
        self.name = dataset.provider_name
        self.version = dataset.provider_version
        self.dimensions = dataset.dimensions
        self._vectors = {
            item.content
            if isinstance(item, VectorQualityRecord)
            else item.text: item.embedding
            for item in [*dataset.records, *dataset.queries]
        }

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [self._vectors[text] for text in texts]


def load_vector_quality_dataset(
    path: str | Path = DEFAULT_DATASET,
) -> VectorQualityDataset:
    with Path(path).open(encoding="utf-8") as source:
        return VectorQualityDataset.model_validate(json.load(source))


async def run_vector_quality_benchmark(
    dataset: VectorQualityDataset,
    *,
    dsn: str,
) -> dict[str, Any]:
    if not str(dsn or "").strip():
        raise ValueError("PostgreSQL DSN is required")
    store = PostgreSQLStore(dsn, min_pool_size=0, max_pool_size=6)
    index = PostgreSQLVectorIndex(
        store,
        FixtureEmbeddingProvider(dataset),
        VectorIndexConfig(create_extension=True, create_hnsw_index=True),
    )
    errors: list[str] = []
    scopes = {item.name: item.to_scope() for item in dataset.scopes}
    stored_records: list[MemoryRecord] = []
    try:
        for position, item in enumerate(dataset.records):
            created_at = datetime(2026, 1, 1, 0, position, tzinfo=UTC)
            record = MemoryRecord(
                memory_id=item.memory_id,
                kind=MemoryKind.BACKGROUND,
                scope=scopes[item.scope],
                content=item.content,
                tags=item.tags,
                state=MemoryState.CONFIRMED,
                idempotency_key=f"vector-quality:{item.memory_id}",
                extractor=dataset.name,
                metadata={"vector_quality_scope": item.scope},
                created_at=created_at,
                updated_at=created_at,
            )
            result = await store.put(record, idempotency_key=record.idempotency_key)
            if result.status is not WriteStatus.CREATED or result.record is None:
                errors.append(
                    f"record {item.memory_id} was not created: {result.status.value}"
                )
                continue
            stored_records.append(result.record)

        index_report = await index.index_records(stored_records)
        if not index_report.ok or index_report.indexed != len(dataset.records):
            errors.append("not all fixture records were indexed successfully")
        replay_report = await index.index_records(stored_records)
        if not replay_report.ok or replay_report.skipped != len(dataset.records):
            errors.append("embedding content-hash replay was not idempotent")

        hybrid = Retriever(
            store,
            strategy=HybridRetrievalStrategy(index, candidate_multiplier=4),
        )
        cases: list[dict[str, Any]] = []
        semantic_missing = 0
        hybrid_missing = 0
        scope_leakage = 0
        forbidden_hits = 0
        for query in dataset.queries:
            scope = scopes[query.scope]
            semantic = list(await index.search(query.text, [scope], limit=5))
            hybrid_hits = await hybrid.recall(query.text, [scope], limit=5)
            semantic_ids = [hit.memory_id for hit in semantic]
            hybrid_ids = [hit.memory_id for hit in hybrid_hits]
            semantic_ok = (
                bool(semantic_ids) and semantic_ids[0] == query.expected_memory_id
            )
            hybrid_ok = bool(hybrid_ids) and hybrid_ids[0] == query.expected_memory_id
            semantic_missing += not semantic_ok
            hybrid_missing += not hybrid_ok
            all_hits = [*semantic, *hybrid_hits]
            scope_leakage += sum(
                hit.scope is None or hit.scope.scope_key != scope.scope_key
                for hit in all_hits
            )
            forbidden = set(query.forbidden_memory_ids)
            forbidden_hits += len(forbidden.intersection(semantic_ids))
            forbidden_hits += len(forbidden.intersection(hybrid_ids))
            cases.append(
                {
                    "name": query.name,
                    "expected_memory_id": query.expected_memory_id,
                    "semantic_ids": semantic_ids,
                    "hybrid_ids": hybrid_ids,
                    "semantic_top1_passed": semantic_ok,
                    "hybrid_top1_passed": hybrid_ok,
                }
            )

        if semantic_missing:
            errors.append(f"semantic top-1 misses: {semantic_missing}")
        if hybrid_missing:
            errors.append(f"hybrid top-1 misses: {hybrid_missing}")
        if scope_leakage:
            errors.append(f"scope leakage hits: {scope_leakage}")
        if forbidden_hits:
            errors.append(f"forbidden memory hits: {forbidden_hits}")
        health = await index.health()
        return {
            "result_schema_version": 1,
            "doppel_version": __version__,
            "generated_at": utc_now().isoformat(),
            "dataset": {
                "name": dataset.name,
                "version": dataset.dataset_version,
                "fingerprint": dataset.fingerprint,
                "dimensions": dataset.dimensions,
                "record_count": len(dataset.records),
                "query_count": len(dataset.queries),
            },
            "index": {
                "health": health,
                "initial": index_report.model_dump(mode="json"),
                "replay": replay_report.model_dump(mode="json"),
            },
            "cases": cases,
            "correctness": {
                "passed": not errors,
                "semantic_top1_misses": semantic_missing,
                "hybrid_top1_misses": hybrid_missing,
                "scope_leakage_count": scope_leakage,
                "forbidden_memory_hits": forbidden_hits,
                "errors": errors,
            },
        }
    finally:
        await store.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--dsn", required=True)
    parser.add_argument(
        "--allow-mutating-benchmark",
        action="store_true",
        help="Confirms that the PostgreSQL target is a disposable test database.",
    )
    parser.add_argument("--output")
    return parser


async def _main() -> int:
    args = _parser().parse_args()
    if not args.allow_mutating_benchmark:
        raise ValueError(
            "vector quality benchmark mutates its target; pass "
            "--allow-mutating-benchmark only for a disposable database"
        )
    result = await run_vector_quality_benchmark(
        load_vector_quality_dataset(args.dataset),
        dsn=args.dsn,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["correctness"]["passed"] else 1


def main() -> int:
    try:
        return asyncio.run(_main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())

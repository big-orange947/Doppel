"""Deterministic synthetic datasets for backend-neutral Store benchmarks."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from doppel_memory import (
    Actor,
    FactAuthority,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
)

GENERATOR = "doppel.synthetic.v1"
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
_KINDS = (MemoryKind.EVENT, MemoryKind.FACT, MemoryKind.BACKGROUND)
_ACTORS = (Actor.OWNER, Actor.CONTACT, Actor.AGENT)


@dataclass(frozen=True, slots=True)
class SyntheticDatasetConfig:
    dataset_version: int
    generator: str
    seed: int
    scope_count: int
    records_per_scope: int
    query_samples: int
    page_size: int

    @property
    def record_count(self) -> int:
        return self.scope_count * self.records_per_scope

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class BenchmarkQuery:
    text: str
    scope: MemoryScope
    expected_memory_id: str
    forbidden_memory_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticDataset:
    config: SyntheticDatasetConfig
    scopes: tuple[MemoryScope, ...]
    records: tuple[MemoryRecord, ...]
    queries: tuple[BenchmarkQuery, ...]


def load_dataset_config(path: str | Path) -> SyntheticDatasetConfig:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("benchmark dataset config must be a JSON object")
    config = SyntheticDatasetConfig(
        dataset_version=_integer(raw, "dataset_version"),
        generator=str(raw.get("generator", "")),
        seed=_integer(raw, "seed", minimum=0),
        scope_count=_integer(raw, "scope_count", minimum=2),
        records_per_scope=_integer(raw, "records_per_scope", minimum=1),
        query_samples=_integer(raw, "query_samples", minimum=1),
        page_size=_integer(raw, "page_size", minimum=1),
    )
    if config.dataset_version != 1:
        raise ValueError(
            f"unsupported benchmark dataset version: {config.dataset_version}"
        )
    if config.generator != GENERATOR:
        raise ValueError(f"unsupported benchmark generator: {config.generator!r}")
    if config.query_samples > config.record_count:
        raise ValueError("query_samples cannot exceed the generated record count")
    return config


def generate_dataset(config: SyntheticDatasetConfig) -> SyntheticDataset:
    """Materialize a stable dataset from a small, versioned generator config."""
    scopes = tuple(_scope(index) for index in range(config.scope_count))
    records = tuple(
        _record(scope, scope_index, record_index, config.records_per_scope)
        for scope_index, scope in enumerate(scopes)
        for record_index in range(config.records_per_scope)
    )

    candidates = [
        (scope_index, record_index)
        for scope_index in range(config.scope_count)
        for record_index in range(config.records_per_scope)
    ]
    random.Random(config.seed).shuffle(candidates)
    queries = tuple(
        BenchmarkQuery(
            text=_needle(record_index),
            scope=scopes[scope_index],
            expected_memory_id=_memory_id(scope_index, record_index),
            forbidden_memory_ids=tuple(
                _memory_id(other_scope, record_index)
                for other_scope in range(config.scope_count)
                if other_scope != scope_index
            ),
        )
        for scope_index, record_index in candidates[: config.query_samples]
    )
    return SyntheticDataset(
        config=config,
        scopes=scopes,
        records=records,
        queries=queries,
    )


def _scope(index: int) -> MemoryScope:
    return MemoryScope(
        user_id=f"benchmark-user-{index // 2:04d}",
        agent_id="benchmark-agent",
        platform="synthetic",
        chat_type="private",
        chat_id=f"benchmark-chat-{index:04d}",
    )


def _record(
    scope: MemoryScope,
    scope_index: int,
    record_index: int,
    records_per_scope: int,
) -> MemoryRecord:
    memory_id = _memory_id(scope_index, record_index)
    at = _BASE_TIME + timedelta(seconds=scope_index * records_per_scope + record_index)
    kind = _KINDS[record_index % len(_KINDS)]
    actor = _ACTORS[record_index % len(_ACTORS)]
    authority = (
        FactAuthority.of(actor)
        if kind == MemoryKind.EVENT
        else FactAuthority.DERIVED_SUMMARY
    )
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        kind=kind,
        content=(
            f"synthetic benchmark memory {_needle(record_index)} "
            f"topic{record_index % 17:02d} scope{scope_index:04d}"
        ),
        actor=actor,
        authority=authority,
        state=MemoryState.CONFIRMED,
        tags=["benchmark", f"topic-{record_index % 17:02d}"],
        importance=(record_index % 10) / 10,
        idempotency_key=f"benchmark:{memory_id}",
        source_event_id=f"event-{memory_id}",
        extractor=GENERATOR,
        created_at=at,
        updated_at=at,
        metadata={
            "dataset_generator": GENERATOR,
            "scope_index": scope_index,
            "record_index": record_index,
        },
    )


def _memory_id(scope_index: int, record_index: int) -> str:
    return f"bench-s{scope_index:04d}-r{record_index:08d}"


def _needle(record_index: int) -> str:
    # The same needle exists in every scope, making leakage immediately observable.
    return f"needle{record_index:08d}"


def _integer(data: dict[str, object], key: str, *, minimum: int = 1) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{key} must be an integer >= {minimum}")
    return value

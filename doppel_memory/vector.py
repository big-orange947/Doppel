"""Explicit embedding indexes and scope-guarded hybrid retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from doppel_memory.indexing import (
    IndexEntry,
    IndexEntryPage,
    IndexOperationResult,
    IndexOperationStatus,
    memory_index_fingerprint,
)
from doppel_memory.models import (
    MemoryFilter,
    MemoryIsolationError,
    MemoryRecord,
    MemoryScope,
    RecallResult,
    utc_now,
)
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.retriever import RetrievalStrategy, StoreRetrievalStrategy
from doppel_memory.store import MemoryStore

VECTOR_SCHEMA_VERSION = 2


class EmbeddingProviderError(RuntimeError):
    """An embedding provider failed or violated its declared vector contract."""


class SemanticIndexUnavailableError(RuntimeError):
    """A semantic candidate source cannot honor the current request."""


class VectorIndexUnavailableError(SemanticIndexUnavailableError):
    """The configured database cannot currently provide the vector index."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Host-supplied text embedder with a stable, versioned vector identity."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


@runtime_checkable
class SemanticIndex(Protocol):
    """Scope-aware semantic candidate source consumed by retrieval strategies."""

    async def search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]: ...


@runtime_checkable
class TemporalSemanticIndex(SemanticIndex, Protocol):
    """Optional semantic index extension for facts valid at one exact instant.

    Candidate sources remain non-authoritative. The query engine always reloads
    their Store records and applies Doppel's own temporal interval checks.
    """

    async def search_at(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        valid_at: datetime,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]: ...


class SemanticSourceContribution(BaseModel):
    """One explainable source contribution to a fused semantic candidate."""

    source: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    rank: int = Field(ge=1)
    similarity: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    rrf_score: float = Field(gt=0.0)


class CompositeRecallResult(RecallResult):
    """A RecallResult carrying per-index evidence for later query explanation."""

    contributions: list[SemanticSourceContribution] = Field(min_length=1)


class CompositeSemanticIndex:
    """Parallel RRF over multiple semantic or temporal candidate indexes.

    This composes pgvector and Graphiti without treating either as authoritative. It
    does not query the Store itself; the PersonalMemoryQueryEngine continues to reload
    every fused `(scope, memory_id)` before applying lifecycle and provenance gates.
    """

    def __init__(
        self,
        indexes: Mapping[str, SemanticIndex],
        *,
        weights: Mapping[str, float] | None = None,
        rrf_k: int = 60,
        candidate_multiplier: int = 4,
    ) -> None:
        self._indexes = dict(indexes)
        if not self._indexes:
            raise ValueError("composite semantic index requires at least one source")
        invalid_names = sorted(
            name
            for name in self._indexes
            if re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name) is None
        )
        if invalid_names:
            raise ValueError(
                f"invalid composite semantic source names: {invalid_names}"
            )
        configured_weights = dict(weights or {})
        unknown_weights = sorted(set(configured_weights).difference(self._indexes))
        if unknown_weights:
            raise ValueError(
                f"weights reference unknown semantic sources: {unknown_weights}"
            )
        self._weights = {
            name: float(configured_weights.get(name, 1.0)) for name in self._indexes
        }
        if any(weight < 0 for weight in self._weights.values()):
            raise ValueError("composite semantic weights must be non-negative")
        if not any(weight > 0 for weight in self._weights.values()):
            raise ValueError("at least one composite semantic weight must be positive")
        if rrf_k < 1:
            raise ValueError("composite semantic rrf_k must be positive")
        if candidate_multiplier < 1:
            raise ValueError(
                "composite semantic candidate_multiplier must be positive"
            )
        self._rrf_k = rrf_k
        self._candidate_multiplier = candidate_multiplier

    async def search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        return await self._search(
            query, scopes, filters=filters, limit=limit, valid_at=None
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
            raise ValueError("composite semantic valid_at must include a timezone")
        return await self._search(
            query, scopes, filters=filters, limit=limit, valid_at=valid_at
        )

    async def _search(
        self,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None,
        limit: int,
        valid_at: datetime | None,
    ) -> Sequence[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "composite semantic search requires at least one exact scope"
            )
        if limit <= 0 or not str(query or "").strip():
            return []
        candidate_limit = limit * self._candidate_multiplier
        active = [
            (name, index)
            for name, index in self._indexes.items()
            if self._weights[name] > 0
        ]
        calls = [
            self._search_source(
                index,
                query,
                scopes,
                filters=filters,
                limit=candidate_limit,
                valid_at=valid_at,
            )
            for _, index in active
        ]
        raw_results = await asyncio.gather(*calls, return_exceptions=True)
        available: dict[str, Sequence[RecallResult]] = {}
        unavailable: list[tuple[str, BaseException]] = []
        for (name, _), result in zip(active, raw_results, strict=True):
            if isinstance(result, (EmbeddingProviderError, SemanticIndexUnavailableError)):
                unavailable.append((name, result))
            elif isinstance(result, BaseException):
                raise result
            else:
                available[name] = result
        if not available:
            detail = ", ".join(
                f"{name}={type(error).__name__}" for name, error in unavailable
            )
            raise SemanticIndexUnavailableError(
                f"all composite semantic sources are unavailable: {detail}"
            )
        return _semantic_rrf(
            available,
            scopes=scopes,
            weights=self._weights,
            rrf_k=self._rrf_k,
            limit=limit,
        )

    @staticmethod
    async def _search_source(
        index: SemanticIndex,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None,
        limit: int,
        valid_at: datetime | None,
    ) -> Sequence[RecallResult]:
        if valid_at is not None and isinstance(index, TemporalSemanticIndex):
            return await index.search_at(
                query,
                scopes,
                valid_at=valid_at,
                filters=filters,
                limit=limit,
            )
        return await index.search(query, scopes, filters=filters, limit=limit)


class VectorIndexConfig(BaseModel):
    """Database setup and bounded indexing policy for one embedding profile."""

    create_extension: bool = False
    create_hnsw_index: bool = False
    embedding_batch_size: int = Field(default=64, ge=1, le=1024)
    hnsw_m: int = Field(default=16, ge=2, le=100)
    hnsw_ef_construction: int = Field(default=64, ge=4, le=1000)


class VectorIndexFailure(BaseModel):
    memory_id: str = ""
    stage: str
    error_type: str
    message: str


class VectorIndexReport(BaseModel):
    schema_version: int = VECTOR_SCHEMA_VERSION
    profile: str
    attempted: int = Field(ge=0)
    indexed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    failed: int = Field(ge=0)
    failures: list[VectorIndexFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_counts(self) -> VectorIndexReport:
        if self.indexed + self.skipped + self.failed != self.attempted:
            raise ValueError("vector index report counts must equal attempted")
        if self.failed != len(self.failures):
            raise ValueError("vector index report failures must match failed count")
        return self

    @property
    def ok(self) -> bool:
        return self.failed == 0


class VectorBackfillResult(BaseModel):
    report: VectorIndexReport
    next_cursor: str = ""
    has_more: bool = False


class PostgreSQLVectorIndex:
    """A caller-owned pgvector index layered over a ``PostgreSQLStore``.

    Core records remain authoritative. Embeddings live in a profile-specific table,
    so changing provider identity, version, or dimensions creates a new namespace
    instead of silently comparing incompatible vectors.
    """

    def __init__(
        self,
        store: PostgreSQLStore,
        provider: EmbeddingProvider,
        config: VectorIndexConfig | None = None,
    ) -> None:
        self._store = store
        self._provider = provider
        self._config = config or VectorIndexConfig()
        self._provider_name = str(getattr(provider, "name", "") or "").strip()
        self._provider_version = str(getattr(provider, "version", "") or "").strip()
        raw_dimensions = getattr(provider, "dimensions", 0)
        if isinstance(raw_dimensions, bool) or not isinstance(raw_dimensions, int):
            raise TypeError("embedding provider dimensions must be an integer")
        self._dimensions = raw_dimensions
        if not self._provider_name:
            raise ValueError("embedding provider name is required")
        if not self._provider_version:
            raise ValueError("embedding provider version is required")
        if not 1 <= self._dimensions <= 16_000:
            raise ValueError(
                "embedding provider dimensions must be between 1 and 16000"
            )
        if self._config.create_hnsw_index and self._dimensions > 2_000:
            raise ValueError("HNSW vector indexes support at most 2000 dimensions")

        identity = {
            "dimensions": self._dimensions,
            "metric": "cosine",
            "name": self._provider_name,
            "version": self._provider_version,
        }
        payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:16]
        self._identity_json = payload
        self._profile = f"dplv_{fingerprint}"
        self._table_name = f"doppel_memory_vectors_{fingerprint}"
        self._index_name = f"doppel_memory_hnsw_{fingerprint}"
        self._table_sql = f'{store._schema_sql}."{self._table_name}"'
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._extension_version = ""
        self._vector_type_sql = ""

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def identity(self) -> str:
        """Stable identity used to bind maintenance checkpoints."""

        return f"pgvector:{self._profile}"

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            pool = await self._store._ensure_pool()
            async with pool.acquire() as connection:
                extension = await self._find_extension(connection)
                if extension is None and self._config.create_extension:
                    await connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    extension = await self._find_extension(connection)
                if extension is None:
                    raise VectorIndexUnavailableError(
                        "pgvector is not enabled in this database; provision the server "
                        "extension and run CREATE EXTENSION vector, or explicitly set "
                        "VectorIndexConfig(create_extension=True) for a disposable or "
                        "authorized database"
                    )
                extension_version, extension_schema = extension
                vector_type_sql = f'{_quote_identifier(extension_schema)}."vector"'
                opclass_sql = (
                    f'{_quote_identifier(extension_schema)}."vector_cosine_ops"'
                )
                await self._migrate(connection, vector_type_sql, opclass_sql)
            self._extension_version = extension_version
            self._vector_type_sql = vector_type_sql
            self._initialized = True

    @staticmethod
    async def _find_extension(connection: Any) -> tuple[str, str] | None:
        row = await connection.fetchrow(
            """
            SELECT extension.extversion, namespace.nspname
            FROM pg_extension AS extension
            JOIN pg_namespace AS namespace
              ON namespace.oid=extension.extnamespace
            WHERE extension.extname='vector'
            """
        )
        if row is None:
            return None
        return str(row["extversion"]), str(row["nspname"])

    async def _migrate(
        self, connection: Any, vector_type_sql: str, opclass_sql: str
    ) -> None:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                f"doppel-vector-schema:{self._store.schema}:{self._profile}",
            )
            await connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table_sql} (
                    memory_id TEXT PRIMARY KEY REFERENCES
                        {self._store._records_sql}(id) ON DELETE CASCADE,
                    scope_key TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    record_fingerprint TEXT NOT NULL,
                    source_version INTEGER NOT NULL,
                    embedding {vector_type_sql}({self._dimensions}) NOT NULL,
                    embedded_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} ADD COLUMN IF NOT EXISTS scope_key TEXT"
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} "
                "ADD COLUMN IF NOT EXISTS record_fingerprint TEXT"
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} "
                "ADD COLUMN IF NOT EXISTS source_version INTEGER"
            )
            await connection.execute(
                f"""
                UPDATE {self._table_sql} AS vector
                SET scope_key=record.scope_key,
                    record_fingerprint=COALESCE(vector.record_fingerprint, ''),
                    source_version=record.version
                FROM {self._store._records_sql} AS record
                WHERE vector.memory_id=record.id
                  AND (vector.scope_key IS NULL
                       OR vector.record_fingerprint IS NULL
                       OR vector.source_version IS NULL)
                """
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} ALTER COLUMN scope_key SET NOT NULL"
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} "
                "ALTER COLUMN record_fingerprint SET NOT NULL"
            )
            await connection.execute(
                f"ALTER TABLE {self._table_sql} "
                "ALTER COLUMN source_version SET NOT NULL"
            )
            await connection.execute(
                f'CREATE INDEX IF NOT EXISTS "{self._table_name}_scope_memory" '
                f"ON {self._table_sql}(scope_key, memory_id)"
            )
            if self._config.create_hnsw_index:
                await connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS "{self._index_name}"
                    ON {self._table_sql}
                    USING hnsw (embedding {opclass_sql})
                    WITH (m={self._config.hnsw_m},
                          ef_construction={self._config.hnsw_ef_construction})
                    """
                )
            metadata_key = f"vector_profile:{self._profile}"
            await connection.execute(
                f"""
                INSERT INTO {self._store._meta_sql}(key, value)
                VALUES($1, $2)
                ON CONFLICT (key) DO NOTHING
                """,
                metadata_key,
                self._identity_json,
            )
            stored_identity = await connection.fetchval(
                f"SELECT value FROM {self._store._meta_sql} WHERE key=$1",
                metadata_key,
            )
            if str(stored_identity) != self._identity_json:
                raise RuntimeError(
                    f"vector profile identity conflict for {self._profile}"
                )

    async def index_record(self, record: MemoryRecord) -> VectorIndexReport:
        return await self.index_records([record])

    async def index_records(self, records: Sequence[MemoryRecord]) -> VectorIndexReport:
        await self.initialize()
        failures: list[VectorIndexFailure] = []
        authoritative: list[MemoryRecord] = []
        attempted = len(records)
        for record in records:
            if not record.memory_id:
                failures.append(
                    _failure("", "load", ValueError("memory ID is required"))
                )
                continue
            stored = await self._store.get(record.scope, record.memory_id)
            if stored is None:
                failures.append(
                    _failure(
                        record.memory_id,
                        "load",
                        KeyError("record was not found in the supplied exact scope"),
                    )
                )
                continue
            authoritative.append(stored)

        hashes = {
            record.memory_id: _content_hash(record.content) for record in authoritative
        }
        fingerprints = {
            record.memory_id: memory_index_fingerprint(record)
            for record in authoritative
        }
        existing = await self._existing_metadata(list(hashes))
        pending = [
            record
            for record in authoritative
            if existing.get(record.memory_id, ("", ""))[1]
            != fingerprints[record.memory_id]
        ]
        skipped = len(authoritative) - len(pending)
        indexed = 0
        manifest_only = [
            record
            for record in pending
            if existing.get(record.memory_id, ("", ""))[0] == hashes[record.memory_id]
        ]
        if manifest_only:
            try:
                await self._update_manifests(manifest_only, hashes, fingerprints)
                indexed += len(manifest_only)
            except Exception as exc:  # noqa: BLE001 - report database batch failures
                failures.extend(
                    _failure(record.memory_id, "persist", exc)
                    for record in manifest_only
                )
        embedding_pending = [
            record for record in pending if record not in manifest_only
        ]
        batch_size = self._config.embedding_batch_size
        for offset in range(0, len(embedding_pending), batch_size):
            batch = embedding_pending[offset : offset + batch_size]
            try:
                vectors = await self._embed_texts([record.content for record in batch])
                await self._upsert_vectors(batch, vectors, hashes, fingerprints)
                indexed += len(batch)
            except EmbeddingProviderError as exc:
                failures.extend(
                    _failure(record.memory_id, "embed", exc) for record in batch
                )
            except Exception as exc:  # noqa: BLE001 - report database batch failures
                failures.extend(
                    _failure(record.memory_id, "persist", exc) for record in batch
                )
        return VectorIndexReport(
            profile=self._profile,
            attempted=attempted,
            indexed=indexed,
            skipped=skipped,
            failed=len(failures),
            failures=failures,
        )

    async def _existing_metadata(
        self, memory_ids: list[str]
    ) -> dict[str, tuple[str, str]]:
        if not memory_ids:
            return {}
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"SELECT memory_id, content_hash, record_fingerprint "
                f"FROM {self._table_sql} "
                "WHERE memory_id=ANY($1::text[])",
                memory_ids,
            )
        return {
            str(row["memory_id"]): (
                str(row["content_hash"]),
                str(row["record_fingerprint"]),
            )
            for row in rows
        }

    async def _embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            raw_vectors = await self._provider.embed(texts)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"embedding provider {self._provider_name}@{self._provider_version} "
                f"failed: {type(exc).__name__}: {exc}"
            ) from exc
        vectors = list(raw_vectors)
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"embedding provider returned {len(vectors)} vectors for "
                f"{len(texts)} texts"
            )
        return [self._validate_vector(vector) for vector in vectors]

    def _validate_vector(self, vector: Sequence[float]) -> list[float]:
        values: list[float] = []
        try:
            for raw_value in vector:
                value = float(raw_value)
                if not math.isfinite(value):
                    raise ValueError("vector values must be finite")
                values.append(value)
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError(f"invalid embedding vector: {exc}") from exc
        if len(values) != self._dimensions:
            raise EmbeddingProviderError(
                f"embedding provider declared {self._dimensions} dimensions but "
                f"returned {len(values)}"
            )
        if not any(value != 0.0 for value in values):
            raise EmbeddingProviderError(
                "cosine embeddings must contain at least one non-zero value"
            )
        return values

    async def _upsert_vectors(
        self,
        records: Sequence[MemoryRecord],
        vectors: Sequence[Sequence[float]],
        hashes: Mapping[str, str],
        fingerprints: Mapping[str, str],
    ) -> None:
        pool = await self._store._ensure_pool()
        now = utc_now()
        rows = [
            (
                record.memory_id,
                record.scope.scope_key,
                hashes[record.memory_id],
                fingerprints[record.memory_id],
                record.version,
                _vector_literal(vector),
                now,
            )
            for record, vector in zip(records, vectors, strict=True)
        ]
        async with pool.acquire() as connection, connection.transaction():
            await connection.executemany(
                f"""
                INSERT INTO {self._table_sql}
                    (memory_id, scope_key, content_hash, record_fingerprint,
                     source_version, embedding, embedded_at)
                VALUES($1, $2, $3, $4, $5,
                       $6::{self._vector_type_sql}({self._dimensions}), $7)
                ON CONFLICT (memory_id) DO UPDATE SET
                    scope_key=EXCLUDED.scope_key,
                    content_hash=EXCLUDED.content_hash,
                    record_fingerprint=EXCLUDED.record_fingerprint,
                    source_version=EXCLUDED.source_version,
                    embedding=EXCLUDED.embedding,
                    embedded_at=EXCLUDED.embedded_at
                """,
                rows,
            )

    async def _update_manifests(
        self,
        records: Sequence[MemoryRecord],
        hashes: Mapping[str, str],
        fingerprints: Mapping[str, str],
    ) -> None:
        pool = await self._store._ensure_pool()
        rows = [
            (
                record.scope.scope_key,
                hashes[record.memory_id],
                fingerprints[record.memory_id],
                record.version,
                record.memory_id,
            )
            for record in records
        ]
        async with pool.acquire() as connection, connection.transaction():
            await connection.executemany(
                f"""
                UPDATE {self._table_sql}
                SET scope_key=$1, content_hash=$2, record_fingerprint=$3,
                    source_version=$4
                WHERE memory_id=$5
                """,
                rows,
            )

    async def inspect(self, scope: MemoryScope, memory_id: str) -> IndexEntry | None:
        await self.initialize()
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                f"""
                SELECT memory_id, scope_key, record_fingerprint, source_version
                FROM {self._table_sql}
                WHERE memory_id=$1 AND scope_key=$2
                """,
                memory_id,
                scope.scope_key,
            )
        if row is None:
            return None
        return _vector_index_entry(row)

    async def upsert(self, record: MemoryRecord) -> IndexOperationResult:
        if not record.memory_id:
            raise ValueError("vector indexing requires a committed memory ID")
        authoritative = await self._store.get(record.scope, record.memory_id)
        if authoritative is None:
            raise ValueError(
                "vector indexing requires a record in the authoritative exact scope"
            )
        fingerprint = memory_index_fingerprint(authoritative)
        current = await self.inspect(authoritative.scope, authoritative.memory_id)
        if current is not None and current.fingerprint == fingerprint:
            status = IndexOperationStatus.SKIPPED
        else:
            report = await self.index_record(authoritative)
            if not report.ok:
                failure = report.failures[0]
                raise VectorIndexUnavailableError(
                    f"{failure.stage}: {failure.error_type}: {failure.message}"
                )
            status = IndexOperationStatus.INDEXED
        return IndexOperationResult(
            index_identity=self.identity,
            status=status,
            memory_id=authoritative.memory_id,
            scope_key=authoritative.scope.scope_key,
            fingerprint=fingerprint,
            source_version=authoritative.version,
        )

    async def delete(self, scope: MemoryScope, memory_id: str) -> IndexOperationResult:
        await self.initialize()
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            removed = await connection.fetchval(
                f"DELETE FROM {self._table_sql} "
                "WHERE memory_id=$1 AND scope_key=$2 RETURNING memory_id",
                memory_id,
                scope.scope_key,
            )
        return IndexOperationResult(
            index_identity=self.identity,
            status=(
                IndexOperationStatus.DELETED
                if removed is not None
                else IndexOperationStatus.MISSING
            ),
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
        if limit <= 0:
            raise ValueError("limit must be positive")
        await self.initialize()
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT memory_id, scope_key, record_fingerprint, source_version
                FROM {self._table_sql}
                WHERE scope_key=$1 AND memory_id>$2
                ORDER BY memory_id ASC
                LIMIT $3
                """,
                scope.scope_key,
                cursor,
                limit + 1,
            )
        selected = rows[:limit]
        entries = [_vector_index_entry(row) for row in selected]
        return IndexEntryPage(
            entries=entries,
            next_cursor=entries[-1].memory_id if entries else cursor,
            has_more=len(rows) > limit,
        )

    async def backfill(
        self,
        scope: MemoryScope,
        *,
        filters: MemoryFilter | None = None,
        cursor: str = "",
        page_size: int = 100,
    ) -> VectorBackfillResult:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        page = await self._store.scan(
            scope,
            filters=filters,
            cursor=cursor,
            limit=page_size,
        )
        report = await self.index_records(page.records)
        return VectorBackfillResult(
            report=report,
            next_cursor=page.next_cursor,
            has_more=page.has_more,
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
                "semantic search requires at least one exact scope"
            )
        if limit <= 0 or not str(query or "").strip():
            return []
        await self.initialize()
        (query_vector,) = await self._embed_texts([query.strip()])
        vector_literal = _vector_literal(query_vector)
        scope_keys = list(dict.fromkeys(scope.scope_key for scope in scopes))
        where = ["record.scope_key = ANY($1::text[])"]
        params: list[Any] = [scope_keys, vector_literal]
        self._store._append_filters(
            where,
            params,
            filters or MemoryFilter(),
            prefix="record.",
        )
        params.append(limit)
        distance = (
            f"vector.embedding <=> $2::{self._vector_type_sql}({self._dimensions})"
        )
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT record.*, 1 - ({distance}) AS vector_similarity
                FROM {self._table_sql} AS vector
                JOIN {self._store._records_sql} AS record
                  ON record.id=vector.memory_id
                WHERE {" AND ".join(where)}
                ORDER BY {distance} ASC, record.created_at DESC, record.id ASC
                LIMIT ${len(params)}
                """,
                *params,
            )
        return [
            self._store._row_to_recall(row).model_copy(
                update={"similarity": float(row["vector_similarity"])}
            )
            for row in rows
        ]

    async def health(self) -> dict[str, Any]:
        await self.initialize()
        pool = await self._store._ensure_pool()
        async with pool.acquire() as connection:
            indexed = await connection.fetchval(
                f"SELECT COUNT(*) FROM {self._table_sql}"
            )
            core_records = await connection.fetchval(
                f"SELECT COUNT(*) FROM {self._store._records_sql}"
            )
        return {
            "enabled": True,
            "ok": True,
            "backend": "pgvector",
            "schema_version": VECTOR_SCHEMA_VERSION,
            "extension_version": self._extension_version,
            "profile": self._profile,
            "provider": self._provider_name,
            "provider_version": self._provider_version,
            "dimensions": self._dimensions,
            "metric": "cosine",
            "indexed_records": int(indexed),
            "core_records": int(core_records),
            "create_hnsw_index": self._config.create_hnsw_index,
        }


class HybridRetrievalStrategy:
    """Reciprocal-rank fusion of lexical Store and semantic index candidates."""

    def __init__(
        self,
        semantic_index: SemanticIndex,
        *,
        lexical_strategy: RetrievalStrategy | None = None,
        lexical_weight: float = 1.0,
        semantic_weight: float = 1.0,
        rrf_k: int = 60,
        candidate_multiplier: int = 4,
        fallback_to_lexical: bool = True,
    ) -> None:
        if lexical_weight < 0 or semantic_weight < 0:
            raise ValueError("hybrid retrieval weights must be non-negative")
        if lexical_weight == 0 and semantic_weight == 0:
            raise ValueError("at least one hybrid retrieval weight must be positive")
        if rrf_k < 1:
            raise ValueError("rrf_k must be positive")
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be positive")
        self._semantic_index = semantic_index
        self._lexical = lexical_strategy or StoreRetrievalStrategy()
        self._lexical_weight = float(lexical_weight)
        self._semantic_weight = float(semantic_weight)
        self._rrf_k = rrf_k
        self._candidate_multiplier = candidate_multiplier
        self._fallback_to_lexical = fallback_to_lexical

    async def search(
        self,
        store: MemoryStore,
        query: str,
        scopes: Sequence[MemoryScope],
        *,
        filters: MemoryFilter | None = None,
        limit: int = 10,
    ) -> Sequence[RecallResult]:
        if not scopes:
            raise MemoryIsolationError(
                "hybrid search requires at least one exact scope"
            )
        if limit <= 0:
            return []
        candidate_limit = limit * self._candidate_multiplier
        lexical_result, semantic_result = await asyncio.gather(
            self._lexical.search(
                store,
                query,
                scopes,
                filters=filters,
                limit=candidate_limit,
            ),
            self._semantic_index.search(
                query,
                scopes,
                filters=filters,
                limit=candidate_limit,
            ),
            return_exceptions=True,
        )
        if isinstance(lexical_result, BaseException):
            raise lexical_result
        lexical = lexical_result
        if isinstance(
            semantic_result, (EmbeddingProviderError, SemanticIndexUnavailableError)
        ):
            if not self._fallback_to_lexical:
                raise semantic_result
            semantic = []
        elif isinstance(semantic_result, BaseException):
            raise semantic_result
        else:
            semantic = semantic_result
        return _rrf(
            lexical,
            semantic,
            scopes=scopes,
            lexical_weight=self._lexical_weight,
            semantic_weight=self._semantic_weight,
            rrf_k=self._rrf_k,
            limit=limit,
        )


def _rrf(
    lexical: Sequence[RecallResult],
    semantic: Sequence[RecallResult],
    *,
    scopes: Sequence[MemoryScope],
    lexical_weight: float,
    semantic_weight: float,
    rrf_k: int,
    limit: int,
) -> list[RecallResult]:
    allowed = {scope.scope_key for scope in scopes}
    candidates: dict[tuple[str, ...], RecallResult] = {}
    scores: dict[tuple[str, ...], float] = {}
    best_rank: dict[tuple[str, ...], int] = {}

    def add(items: Sequence[RecallResult], weight: float) -> None:
        if weight == 0:
            return
        seen: set[tuple[str, ...]] = set()
        for rank, candidate in enumerate(items, start=1):
            if candidate.scope is None or candidate.scope.scope_key not in allowed:
                continue
            identity = _recall_identity(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            candidates.setdefault(identity, candidate)
            scores[identity] = scores.get(identity, 0.0) + weight / (rrf_k + rank)
            best_rank[identity] = min(best_rank.get(identity, rank), rank)

    add(lexical, lexical_weight)
    add(semantic, semantic_weight)
    maximum = (lexical_weight + semantic_weight) / (rrf_k + 1)
    ordered = sorted(
        candidates,
        key=lambda identity: (
            -scores[identity],
            best_rank[identity],
            identity,
        ),
    )
    return [
        candidates[identity].model_copy(
            update={"similarity": scores[identity] / maximum}
        )
        for identity in ordered[:limit]
    ]


def _semantic_rrf(
    sources: Mapping[str, Sequence[RecallResult]],
    *,
    scopes: Sequence[MemoryScope],
    weights: Mapping[str, float],
    rrf_k: int,
    limit: int,
) -> list[CompositeRecallResult]:
    allowed = {scope.scope_key for scope in scopes}
    candidates: dict[tuple[str, ...], RecallResult] = {}
    scores: dict[tuple[str, ...], float] = {}
    best_rank: dict[tuple[str, ...], int] = {}
    contributions: dict[tuple[str, ...], list[SemanticSourceContribution]] = {}
    chains: dict[tuple[str, ...], list[str]] = {}

    for source, items in sources.items():
        weight = weights[source]
        if weight <= 0:
            continue
        seen: set[tuple[str, ...]] = set()
        for rank, candidate in enumerate(items, start=1):
            if candidate.scope is None or candidate.scope.scope_key not in allowed:
                continue
            identity = _recall_identity(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            rrf_score = weight / (rrf_k + rank)
            candidates.setdefault(identity, candidate)
            scores[identity] = scores.get(identity, 0.0) + rrf_score
            best_rank[identity] = min(best_rank.get(identity, rank), rank)
            contributions.setdefault(identity, []).append(
                SemanticSourceContribution(
                    source=source,
                    rank=rank,
                    similarity=min(max(float(candidate.similarity), 0.0), 1.0),
                    weight=weight,
                    rrf_score=rrf_score,
                )
            )
            chain = chains.setdefault(identity, [])
            for item in candidate.derived_chain:
                if item not in chain:
                    chain.append(item)

    maximum = sum(weights[source] for source in sources if weights[source] > 0) / (
        rrf_k + 1
    )
    ordered = sorted(
        candidates,
        key=lambda identity: (
            -scores[identity],
            best_rank[identity],
            identity,
        ),
    )
    return [
        CompositeRecallResult(
            **candidates[identity].model_dump(
                exclude={"derived_chain", "similarity", "contributions"}
            ),
            derived_chain=chains[identity],
            similarity=min(scores[identity] / maximum, 1.0),
            contributions=contributions[identity],
        )
        for identity in ordered[:limit]
    ]


def _recall_identity(candidate: RecallResult) -> tuple[str, ...]:
    scope_key = candidate.scope.scope_key if candidate.scope is not None else ""
    if candidate.memory_id:
        return ("id", scope_key, candidate.memory_id)
    return (
        "value",
        scope_key,
        candidate.source_message_id,
        candidate.source_event_id,
        candidate.fact,
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _vector_index_entry(row: Mapping[str, Any]) -> IndexEntry:
    return IndexEntry(
        memory_id=str(row["memory_id"]),
        scope_key=str(row["scope_key"]),
        fingerprint=str(row["record_fingerprint"]),
        source_version=int(row["source_version"]),
    )


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".17g") for value in vector) + "]"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _failure(memory_id: str, stage: str, error: Exception) -> VectorIndexFailure:
    return VectorIndexFailure(
        memory_id=memory_id,
        stage=stage,
        error_type=type(error).__name__,
        message=str(error),
    )

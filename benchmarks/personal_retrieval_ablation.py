"""v0.9 personal hybrid retrieval ablation benchmark.

Compares four main execution profiles over the same pre-extracted fixture set:

- ``lexical``                : Store structural/lexical scan only (no semantic index)
- ``lexical_vector``         : Store lexical candidates + pgvector semantic candidates
- ``lexical_graph``          : Store lexical candidates + Graphiti graph candidates
- ``lexical_vector_graph``   : Store lexical candidates + weighted RRF of both indexes

plus three index-direct diagnostics (``vector_direct`` / ``graph_direct`` /
``composite_direct``) that bypass the query engine and report raw candidate
behaviour, Store-revalidation rejects, and per-source contributions.

Every main profile runs the real ``PersonalMemoryQueryEngine`` end-to-end:
planner -> lexical/semantic candidate retrieval -> exact-scope Store reload ->
subject/authority/lifecycle/temporal hard gates -> ranked hits. Results never
compare raw index memory IDs.

Budget discipline: this benchmark performs **zero** external LLM calls and **zero**
paid tokens. Graphiti relation data is preseeded directly into Neo4j (Episodic
nodes, entities, edges with local embeddings); pgvector uses a local embedding
provider (BAAI/bge-small-zh-v1.5 via fastembed) and a caller-owned profile-specific
table. If Neo4j or PostgreSQL is unreachable the affected profiles are reported as
structured ``unavailable``.

Runtime modules never import ``benchmarks``; this package lives outside the
product namespace on purpose.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import platform
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doppel_memory import (
    Actor,
    DeterministicPersonalMemoryQueryPlanner,
    FactAuthority,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    PersonalMemoryQueryEngine,
    __version__,
)
from doppel_memory.intelligence import MemoryTemporalStatus, PersonalMemoryType
from doppel_memory.models import WriteStatus, utc_now
from doppel_memory.query import (
    PersonalMemoryQueryDraft,
    PersonalMemoryQueryHit,
    PersonalMemoryQueryRequest,
    PersonalMemoryQueryResult,
)

PROFILE_MAIN = ("lexical", "lexical_vector", "lexical_graph", "lexical_vector_graph")
PROFILE_DIRECT = ("vector_direct", "graph_direct", "composite_direct")
ALL_PROFILES = (*PROFILE_MAIN, *PROFILE_DIRECT)

SOURCE_VECTOR = "vector"
SOURCE_GRAPH = "graph"
FALLBACK_EDGE_NAME = "DOPPEL_MEMORY_FALLBACK"
RICH_EDGE_NAME = "HAS_PERSONAL_MEMORY"

DEFAULT_DATASET = (
    Path(__file__).parent / "datasets" / "personal-retrieval-ablation-zh-v1.json"
)
NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_DATABASE = "doppel_ablation"
PG_USER = "postgres"


# --------------------------------------------------------------------------- #
# dataset models
# --------------------------------------------------------------------------- #


class AblationScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    agent_id: str
    display_name: str = ""

    def to_scope(self) -> MemoryScope:
        return MemoryScope(user_id=self.user_id, agent_id=self.agent_id)


class AblationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    message_id: str
    at: datetime


class AblationMemory(BaseModel):
    """One pre-extracted authoritative MemoryRecord in the fixture set."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    scope: str
    content: str
    subject: str = "owner"
    subject_id: str = ""
    authority: str = "human_self"
    personal_memory_type: str = "fact"
    temporal_status: str = "unknown"
    state: str = "confirmed"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    topic_key: str = ""
    event_key: str = ""
    revision_kind: str = ""
    tags: list[str] = Field(default_factory=list)
    evidence: list[AblationEvidence] = Field(default_factory=list)
    authorization: dict[str, Any] | None = None


class AblationQuery(BaseModel):
    """One labeled retrieval case."""

    model_config = ConfigDict(frozen=True)

    query_id: str
    query: str
    scopes: list[str] = Field(min_length=1)
    now: datetime
    intent: str
    as_of: datetime | None = None
    time_from: datetime | None = None
    time_to: datetime | None = None
    required_memory_ids: list[str] = Field(default_factory=list)
    forbidden_memory_ids: list[str] = Field(default_factory=list)
    expected_abstain: bool = False
    expected_ambiguous: bool = False
    expected_count: int | None = None
    expected_count_status: str = "not_requested"
    category: str = "general"
    partition: Literal["dev", "heldout", "adversarial", "deferred_cross_subject"] = (
        "dev"
    )
    abstain_reason: str = ""
    adversarial_note: str = ""
    count_episode_context: str = ""
    note: str = ""


class MetamorphicVariant(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    substitutions: list[list[str]] = Field(min_length=1)


class AblationDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: str
    suite_version: str
    language: str
    status: str = "draft"
    frozen: bool = False
    publication_ready: bool = False
    description: str = ""
    scopes: dict[str, AblationScope]
    metamorphic_variants: list[MetamorphicVariant] = Field(default_factory=list)
    fixtures: list[AblationMemory] = Field(min_length=10)
    queries: list[AblationQuery] = Field(min_length=30)
    requirements: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _references_known_scopes(self) -> AblationDataset:
        known = set(self.scopes)
        unknown_fixtures = sorted(
            {item.scope for item in self.fixtures}.difference(known)
        )
        if unknown_fixtures:
            raise ValueError(f"fixtures reference unknown scopes: {unknown_fixtures}")
        unknown_queries = sorted(
            {scope for item in self.queries for scope in item.scopes}.difference(
                known
            )
        )
        if unknown_queries:
            raise ValueError(f"queries reference unknown scopes: {unknown_queries}")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()


def load_ablation_dataset(path: Path) -> AblationDataset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    dataset = AblationDataset.model_validate(raw)
    fixture_validation_failures = validate_dataset_semantics(dataset)
    if fixture_validation_failures:
        raise ValueError(
            "ablation dataset fixture validation failed:\n"
            + "\n".join(f"  - {item}" for item in fixture_validation_failures)
        )
    return dataset


# --------------------------------------------------------------------------- #
# fixture semantic validation (dataset-level, not product code)
# --------------------------------------------------------------------------- #


def validate_dataset_semantics(dataset: AblationDataset) -> list[str]:
    """Return fixture-level semantic violations; empty means the dataset is valid.

    These checks make the fixture set itself trustworthy so that query failures
    can be attributed to planner/retrieval rather than to malformed gold data.
    """
    failures: list[str] = []
    scope_ids = {name: item.user_id for name, item in dataset.scopes.items()}
    for item in dataset.fixtures:
        scope_user = scope_ids.get(item.scope, "")
        if item.event_key and item.personal_memory_type != "episode":
            failures.append(
                f"{item.memory_id}: event_key present but memory_type is not episode"
            )
        if item.personal_memory_type == "plan" and item.event_key:
            failures.append(f"{item.memory_id}: plan must not carry event_key")
        if item.subject == "owner" and item.subject_id not in (scope_user, ""):
            failures.append(
                f"{item.memory_id}: owner subject_id {item.subject_id!r} does not "
                f"match scope user {scope_user!r}"
            )
        if item.subject != "owner" and not item.authorization:
            failures.append(
                f"{item.memory_id}: cross-subject fixture requires explicit "
                "authorization declaration"
            )
    for query in dataset.queries:
        if query.partition == "deferred_cross_subject":
            continue
        for memory_id in query.required_memory_ids:
            fixture = next(
                (item for item in dataset.fixtures if item.memory_id == memory_id),
                None,
            )
            if fixture is None:
                failures.append(
                    f"{query.query_id}: required memory {memory_id} not in fixtures"
                )
                continue
            query_scope_users = {
                scope_ids[name] for name in query.scopes if name in scope_ids
            }
            if (
                fixture.subject == "owner"
                and fixture.scope not in query.scopes
                and fixture.subject_id not in query_scope_users
            ):
                failures.append(
                    f"{query.query_id}: required memory {memory_id} is structurally "
                    f"unreachable from scopes {query.scopes}"
                )
            if query.as_of is not None:
                if fixture.valid_from is not None and fixture.valid_from > query.as_of:
                    failures.append(
                        f"{query.query_id}: required memory {memory_id} is not yet "
                        f"valid at as_of {query.as_of.isoformat()}"
                    )
                if (
                    fixture.valid_to is not None
                    and fixture.valid_to < query.as_of
                ):
                    failures.append(
                        f"{query.query_id}: required memory {memory_id} already "
                        f"expired at as_of {query.as_of.isoformat()}"
                    )
        if (
            query.as_of is not None
            and query.as_of > query.now
            and query.required_memory_ids
        ):
            failures.append(
                f"{query.query_id}: future as_of must not require asserting "
                "future state"
            )
        if query.expected_count is not None and query.expected_count_status not in (
            "exact",
            "not_requested",
        ):
            failures.append(
                f"{query.query_id}: expected_count with status "
                f"{query.expected_count_status!r} is contradictory"
            )
    return failures


# --------------------------------------------------------------------------- #
# oracle planner (repository-only, never part of doppel_memory)
# --------------------------------------------------------------------------- #

PLANNER_MODE_ORACLE = "oracle"
PLANNER_MODE_DETERMINISTIC = "deterministic"
PLANNER_MODES = (PLANNER_MODE_ORACLE, PLANNER_MODE_DETERMINISTIC)


class BenchmarkOraclePlanner:
    """Fixture-grounded planner: injects only the dataset's labeled structure.

    Deliberately does not choose scopes, memory IDs, topic keys, or any retrieval
    hint beyond intent/as_of/time interval. It maps the exact fixture query text
    back to its labeled plan so retrieval/index/Store layers can be measured
    independently of natural-language planning.
    """

    name = "doppel.benchmark-oracle-planner"
    version = "1"

    def __init__(self, queries: Sequence[AblationQuery]) -> None:
        self._by_text: dict[str, AblationQuery] = {}
        duplicate_texts = set()
        for query in queries:
            key = str(query.query or "").strip()
            if key in self._by_text:
                duplicate_texts.add(key)
            self._by_text[key] = query
        if duplicate_texts:
            raise ValueError(
                f"oracle planner requires unique query texts: {sorted(duplicate_texts)}"
            )

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        fixture = self._by_text.get(str(request.query or "").strip())
        if fixture is None:
            raise ValueError(
                "oracle planner received a query not present in the dataset: "
                f"{request.query!r}"
            )
        intent = str(fixture.intent or "").strip().lower()
        if intent not in _INTENT_VALUES:
            raise ValueError(f"oracle planner does not know intent {intent!r}")
        return PersonalMemoryQueryDraft(
            intent=intent,
            search_text=str(request.query or "").strip(),
            as_of=fixture.as_of,
            time_from=fixture.time_from,
            time_to=fixture.time_to,
            explanation=(
                "benchmark oracle: fixture-labeled plan; no scope, memory ID, "
                "topic key, or retrieval hint injected"
            ),
        )


_INTENT_VALUES = {
    "lookup",
    "current",
    "history",
    "planned",
    "as_of",
    "list",
    "count",
}


# --------------------------------------------------------------------------- #
# fixture injection
# --------------------------------------------------------------------------- #


def _memory_record(
    item: AblationMemory, scope: MemoryScope, since: datetime
) -> MemoryRecord:
    created_at = item.evidence[0].at if item.evidence else since
    updated_at = max((evidence.at for evidence in item.evidence), default=created_at)
    tags = list(dict.fromkeys(["personal-memory", *item.tags]))
    authority_values = {value.value for value in FactAuthority}
    state_values = {value.value for value in MemoryState}
    metadata: dict[str, Any] = {
        "personal_memory_type": PersonalMemoryType.normalize(item.personal_memory_type),
        "topic_key": item.topic_key,
        "event_key": item.event_key,
        "subject": item.subject,
        "subject_id": item.subject_id or scope.user_id,
        "temporal_status": MemoryTemporalStatus.normalize(item.temporal_status),
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
        "valid_to": item.valid_to.isoformat() if item.valid_to else None,
        "revision_kind": item.revision_kind,
        "evidence": [
            {"message_id": evidence.message_id, "at": evidence.at.isoformat()}
            for evidence in item.evidence
        ],
    }
    return MemoryRecord(
        memory_id=item.memory_id,
        scope=scope,
        content=item.content,
        kind="fact",
        actor=Actor.OWNER,
        authority=FactAuthority(item.authority)
        if item.authority in authority_values
        else FactAuthority.DERIVED_SUMMARY,
        state=MemoryState(item.state)
        if item.state in state_values
        else MemoryState.CONFIRMED,
        tags=tags,
        source_message_id=item.evidence[-1].message_id if item.evidence else "",
        extractor="doppel.personal-retrieval-ablation-fixture.v1",
        created_at=created_at,
        updated_at=updated_at,
        metadata=metadata,
    )


# --------------------------------------------------------------------------- #
# provider / index runtimes
# --------------------------------------------------------------------------- #


class _LocalEmbeddingProvider:
    """BAAI/bge-small-zh-v1.5 via fastembed; honest, low-cost, local-only."""

    name = "fastembed:BAAI/bge-small-zh-v1.5"

    def __init__(self, dimensions: int = 512) -> None:
        self._dimensions = dimensions
        self._model: Any = None

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding("BAAI/bge-small-zh-v1.5")
        vectors = await asyncio.to_thread(list, self._model.embed(list(texts)))
        return [[float(value) for value in vector] for vector in vectors]


# --------------------------------------------------------------------------- #
# Neo4j preseed (zero LLM)
# --------------------------------------------------------------------------- #


def _optional_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


async def _preseed_graph(
    graph: Any,
    records: Sequence[MemoryRecord],
    *,
    graph_kind: Literal["fallback", "rich", "mixed"] = "mixed",
) -> dict[str, Any]:
    """Preseed Episode/Entity/Edge into Neo4j without any LLM call.

    ``graph_kind`` selects which edge type carries each record:
    - ``fallback``: a deterministic ``DOPPEL_MEMORY_FALLBACK`` edge (provenance +
      validity + scope only; does not claim relation understanding).
    - ``rich``: a named relation edge (``HAS_PERSONAL_MEMORY``) whose fact and
      entity embeddings come from the local provider.
    - ``mixed``: half the records use each path (ordered by fixture index).
    """
    from graphiti_core.edges import EntityEdge
    from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode

    stats = {"fallback": 0, "rich": 0, "episodes": 0}
    driver = graph.driver
    for index, record in enumerate(records):
        valid_from = _optional_time(record.metadata.get("valid_from"))
        valid_to = _optional_time(record.metadata.get("valid_to"))
        evidence_times = [
            _optional_time(item.get("at"))
            for item in record.metadata.get("evidence", [])
            if isinstance(item, dict)
        ]
        observed_at = max(evidence_times, default=record.created_at) or record.created_at
        episode_id = str(
            uuid5(
                NAMESPACE_URL,
                f"doppel:{record.scope.scope_key}:{record.memory_id}",
            )
        )
        fingerprint = hashlib.sha256(record.content.encode("utf-8")).hexdigest()
        episode_name = (
            "DoppelMemory:v5:" f"{_b64(record.memory_id)}:{fingerprint}:1"
        )
        source_id = str(uuid5(NAMESPACE_URL, f"ablation:source:{episode_id}"))
        target_id = str(uuid5(NAMESPACE_URL, f"ablation:target:{episode_id}"))
        edge_id = str(uuid5(NAMESPACE_URL, f"ablation:edge:{episode_id}"))
        source_name = f"owner:{record.scope.user_id}"
        target_name = str(record.metadata.get("topic_key") or "memory")
        source_embedding = await graph.embedder.create(source_name)
        target_embedding = await graph.embedder.create(target_name)
        fact_embedding = await graph.embedder.create(record.content)
        source = EntityNode(
            uuid=source_id,
            name=source_name,
            group_id=record.scope.scope_key,
            name_embedding=source_embedding,
            summary="doppel ablation owner",
        )
        target = EntityNode(
            uuid=target_id,
            name=target_name,
            group_id=record.scope.scope_key,
            name_embedding=target_embedding,
            summary=record.content,
        )
        use_fallback = graph_kind == "fallback" or (
            graph_kind == "mixed" and index % 2 == 0
        )
        edge = EntityEdge(
            uuid=edge_id,
            group_id=record.scope.scope_key,
            source_node_uuid=source_id,
            target_node_uuid=target_id,
            created_at=observed_at,
            name=FALLBACK_EDGE_NAME if use_fallback else RICH_EDGE_NAME,
            fact=record.content,
            fact_embedding=fact_embedding,
            episodes=[episode_id],
            valid_at=valid_from,
            invalid_at=valid_to,
            reference_time=observed_at,
        )
        episode = EpisodicNode(
            uuid=episode_id,
            name=episode_name,
            group_id=record.scope.scope_key,
            source=EpisodeType.text,
            source_description="doppel.personal-retrieval-ablation preseed",
            content=record.content,
            valid_at=observed_at,
            entity_edges=[edge_id],
        )
        await source.save(driver)
        await target.save(driver)
        await edge.save(driver)
        await episode.save(driver)
        stats["fallback" if use_fallback else "rich"] += 1
        stats["episodes"] += 1
    return stats


async def _cleanup_graph_scope(graph: Any, group_ids: Sequence[str]) -> None:
    if not group_ids:
        return
    await graph.driver.execute_query(
        "MATCH (n) WHERE n.group_id IN $group_ids DETACH DELETE n",
        group_ids=list(group_ids),
    )


async def _probe_neo4j(uri: str, user: str, password: str) -> str:
    """Return a reason string when Neo4j is unavailable, else empty."""
    try:
        import neo4j

        driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
        return ""
    except Exception as exc:  # noqa: BLE001 - structured unavailability
        return f"{type(exc).__name__}: {exc}"


async def _build_graphiti_client(
    uri: str, user: str, password: str
) -> Any:
    from graphiti_core import Graphiti
    from graphiti_core.llm_client.client import LLMClient
    from graphiti_core.llm_client.config import LLMConfig

    from doppel_memory.graphiti_store import FastEmbedderClient, NoOpCrossEncoder

    class _NoNetworkLLM(LLMClient):
        async def _generate_response(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("personal-retrieval-ablation forbids LLM calls")

    return Graphiti(
        uri=uri,
        user=user,
        password=password,
        llm_client=_NoNetworkLLM(LLMConfig(model="disabled-ablation-eval"), cache=False),
        embedder=FastEmbedderClient(),
        cross_encoder=NoOpCrossEncoder(),
    )


async def _build_graph_index(store: Any, graph: Any) -> Any:
    from doppel_memory.graphiti_store import GraphitiSemanticIndex

    return GraphitiSemanticIndex(store, enabled=True, graphiti_client=graph)


# --------------------------------------------------------------------------- #
# pgvector runtime
# --------------------------------------------------------------------------- #


async def _probe_postgres(
    *, host: str, port: int, database: str, user: str, password: str
) -> str:
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=3,
        )
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return ""
    except Exception as exc:  # noqa: BLE001 - structured unavailability
        return f"{type(exc).__name__}: {exc}"


async def _build_vector_index(
    *, host: str, port: int, database: str, user: str, password: str
) -> Any:
    from doppel_memory.postgres_store import PostgreSQLStore

    pg_store = PostgreSQLStore(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )
    await pg_store.ensure_schema()
    return pg_store


async def _build_vector_candidates(
    pg_store: Any,
    records: Sequence[MemoryRecord],
) -> Any:
    from doppel_memory.vector import PostgreSQLVectorIndex, VectorIndexConfig

    index = PostgreSQLVectorIndex(
        pg_store,
        provider=_LocalEmbeddingProvider(),
        config=VectorIndexConfig(create_extension=True, create_hnsw_index=False),
    )
    await index.index_records(records)
    return index


async def _build_composite_index(
    vector_index: Any, graph_index: Any
) -> Any:
    from doppel_memory.vector import CompositeSemanticIndex

    indexes: dict[str, Any] = {}
    if vector_index is not None:
        indexes[SOURCE_VECTOR] = vector_index
    if graph_index is not None:
        indexes[SOURCE_GRAPH] = graph_index
    if not indexes:
        raise ValueError("composite index requires at least one semantic source")
    return CompositeSemanticIndex(indexes)


# --------------------------------------------------------------------------- #
# per-case evaluation
# --------------------------------------------------------------------------- #

INTENT_ALIASES = {
    "current": ("current",),
    "history": ("history", "historical"),
    "as_of": ("as_of",),
    "planned": ("planned",),
    "count": ("count",),
    "lookup": ("lookup",),
    "list": ("list",),
}


async def _run_case(
    engine: PersonalMemoryQueryEngine,
    planner: Any,
    query: AblationQuery,
    scopes: dict[str, MemoryScope],
    *,
    profile: str,
    mode: str = PLANNER_MODE_DETERMINISTIC,
) -> dict[str, Any]:
    started = perf_counter()
    bound_scopes = [scopes[name] for name in query.scopes]
    allowed_scope_keys = {scope.scope_key for scope in bound_scopes}
    try:
        result = await engine.query(planner, query.query, bound_scopes, now=query.now)
    except Exception as exc:  # noqa: BLE001 - structured failure
        return {
            "query_id": query.query_id,
            "profile": profile,
            "mode": mode,
            "partition": query.partition,
            "category": query.category,
            "error": f"{type(exc).__name__}: {exc}",
            "latency_ms": round((perf_counter() - started) * 1_000, 3),
            "hits": [],
            "missing": [],
            "forbidden": [],
            "scope_leakage": 0,
            "temporal_violations": 0,
            "provenance_failures": 0,
            "inactive_rejections": 0,
            "agent_output_hits": 0,
            "abstention_ok": False,
            "ambiguity_ok": False,
            "count_ok": False,
            "hit_top1_ok": False,
            "recall_at_1": 0,
            "recall_at_5": 0,
            "mrr": 0.0,
            "evidence_recall": 0.0,
            "intent_ok": False,
            "required_evidence": bool(query.required_memory_ids),
            "expected_abstain": query.expected_abstain,
            "as_of_recognized": False,
            "planner_temporal_miss": False,
            "planner_intent_miss": False,
            "planner_interval_miss": False,
            "planner_failures": [],
            "retrieval_failures": [],
            "security_failures": [],
            "contribution": {
                "vector": 0,
                "graph": 0,
                "both": 0,
            },
        }
    latency_ms = round((perf_counter() - started) * 1_000, 3)
    return _evaluate_result(
        result,
        query,
        profile,
        latency_ms,
        allowed_scope_keys=allowed_scope_keys,
        mode=mode,
    )


def _expected_intent_ok(result: PersonalMemoryQueryResult, query: AblationQuery) -> bool:
    expected_aliases = INTENT_ALIASES.get(query.intent, (query.intent,))
    return str(result.plan.intent) in expected_aliases


def _evaluate_result(
    result: PersonalMemoryQueryResult,
    query: AblationQuery,
    profile: str,
    latency_ms: float,
    *,
    allowed_scope_keys: set[str],
    mode: str = PLANNER_MODE_DETERMINISTIC,
) -> dict[str, Any]:
    hits: list[PersonalMemoryQueryHit] = list(result.hits)
    hit_set = {hit.record.memory_id for hit in hits}
    missing = sorted(set(query.required_memory_ids).difference(hit_set))
    forbidden = sorted(set(query.forbidden_memory_ids).intersection(hit_set))
    scope_leakage = 0
    temporal_violations = 0
    provenance_failures = 0
    inactive_rejections = 0
    agent_output_hits = 0
    plan_as_of = result.plan.as_of
    as_of_recognized = plan_as_of is not None
    for hit in hits:
        record = hit.record
        if record.scope.scope_key not in allowed_scope_keys:
            scope_leakage += 1
        if query.as_of is not None and mode == PLANNER_MODE_ORACLE:
            # Temporal failure is attributed to retrieval only under an oracle
            # plan (correct as_of was injected). Deterministic misses are
            # planner failures and are never counted here.
            record_valid_from = _optional_time(record.metadata.get("valid_from"))
            record_valid_to = _optional_time(record.metadata.get("valid_to"))
            if record_valid_from is not None and record_valid_from > query.as_of or record_valid_to is not None and record_valid_to < query.as_of:
                temporal_violations += 1
        if not record.metadata.get("evidence"):
            provenance_failures += 1
        inactive_is_invalid = record.state == MemoryState.REJECTED or (
            record.state in {MemoryState.EXPIRED, MemoryState.SUPERSEDED}
            and result.plan.intent not in {"history", "as_of"}
        )
        if inactive_is_invalid:
            inactive_rejections += 1
        if str(getattr(record.authority, "value", "")) == "agent_output":
            agent_output_hits += 1

    abstention_ok = (not hit_set) if query.expected_abstain else bool(hit_set)
    ambiguity_ok = bool(result.ambiguous) == bool(query.expected_ambiguous)
    expected_count_requested = query.expected_count is not None
    if expected_count_requested:
        count_ok = (
            result.count.status == "exact"
            and result.count.value == query.expected_count
        )
    else:
        count_ok = result.count.status in {"not_requested", "exact"}
    intent_ok = _expected_intent_ok(result, query)

    # ---- planner-mode attribution --------------------------------------- #
    planner_temporal_miss = bool(
        mode == PLANNER_MODE_DETERMINISTIC
        and query.as_of is not None
        and not as_of_recognized
    )
    planner_interval_miss = bool(
        mode == PLANNER_MODE_DETERMINISTIC
        and (
            (query.time_from is not None and result.plan.time_from is None)
            or (query.time_to is not None and result.plan.time_to is None)
        )
    )
    planner_intent_miss = bool(mode == PLANNER_MODE_DETERMINISTIC and not intent_ok)
    planner_failures: list[str] = []
    if planner_temporal_miss:
        planner_failures.append("planner_temporal_miss")
    if planner_interval_miss:
        planner_failures.append("planner_interval_miss")
    if planner_intent_miss:
        planner_failures.append("planner_intent_miss")
    retrieval_failures: list[str] = []
    if mode == PLANNER_MODE_ORACLE and temporal_violations:
        retrieval_failures.append("retrieval_temporal_failure")
    if forbidden:
        retrieval_failures.append("forbidden_hit")
    if missing and not query.expected_abstain:
        retrieval_failures.append("missing_required_hit")
    security_failures: list[str] = []
    if scope_leakage:
        security_failures.append("scope_leakage")
    if provenance_failures:
        security_failures.append("invalid_provenance_accepted")
    if inactive_rejections:
        security_failures.append("inactive_record_accepted")
    if agent_output_hits:
        security_failures.append("agent_output_accepted_as_owner_fact")

    required_set = set(query.required_memory_ids)
    hit_top1_ok = bool(hits and hits[0].record.memory_id in required_set)
    recall_at_1 = int(any(hit.record.memory_id in required_set for hit in hits[:1]))
    recall_at_5 = int(any(hit.record.memory_id in required_set for hit in hits[:5]))
    mrr = 0.0
    for rank, hit in enumerate(hits, start=1):
        if hit.record.memory_id in required_set:
            mrr = 1.0 / rank
            break
    evidence_recall = (
        len(required_set.intersection(hit_set)) / len(required_set)
        if required_set
        else 1.0
    )
    contribution = {
        "vector": 0,
        "graph": 0,
        "both": 0,
    }
    for hit in hits:
        hit_sources = [
            reason[len("semantic_source:") :]
            for reason in hit.reasons
            if reason.startswith("semantic_source:")
        ]
        has_vector = SOURCE_VECTOR in hit_sources
        has_graph = SOURCE_GRAPH in hit_sources
        if has_vector and has_graph:
            contribution["both"] += 1
        elif has_vector:
            contribution["vector"] += 1
        elif has_graph:
            contribution["graph"] += 1
    return {
        "query_id": query.query_id,
        "profile": profile,
        "mode": mode,
        "partition": query.partition,
        "category": query.category,
        "error": "",
        "latency_ms": latency_ms,
        "actual_intent": str(result.plan.intent),
        "hits": [hit.record.memory_id for hit in hits],
        "hit_scores": [
            {
                "memory_id": hit.record.memory_id,
                "score": round(hit.score, 6),
                "lexical_score": round(hit.lexical_score, 6),
                "semantic_score": round(hit.semantic_score, 6),
                "reasons": list(hit.reasons),
            }
            for hit in hits
        ],
        "missing": missing,
        "forbidden": forbidden,
        "scope_leakage": scope_leakage,
        "temporal_violations": temporal_violations,
        "provenance_failures": provenance_failures,
        "inactive_rejections": inactive_rejections,
        "agent_output_hits": agent_output_hits,
        "abstention_ok": abstention_ok,
        "ambiguity_ok": ambiguity_ok,
        "count_ok": count_ok,
        "count_status": result.count.status,
        "count_value": result.count.value,
        "hit_top1_ok": hit_top1_ok,
        "recall_at_1": recall_at_1,
        "recall_at_5": recall_at_5,
        "mrr": mrr,
        "evidence_recall": evidence_recall,
        "intent_ok": intent_ok,
        "required_evidence": bool(query.required_memory_ids),
        "expected_abstain": query.expected_abstain,
        "as_of_recognized": as_of_recognized,
        "planner_temporal_miss": planner_temporal_miss,
        "planner_intent_miss": planner_intent_miss,
        "planner_interval_miss": planner_interval_miss,
        "planner_failures": planner_failures,
        "retrieval_failures": retrieval_failures,
        "security_failures": security_failures,
        "ambiguous": bool(result.ambiguous),
        "contribution": contribution,
        "warnings": list(result.warnings),
    }


# --------------------------------------------------------------------------- #
# profile aggregation and hard gates
# --------------------------------------------------------------------------- #

HARD_GATES_KEYS = (
    "forbidden",
    "scope_leakage",
    "temporal_violations",
    "provenance_failures",
)


def _aggregate(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    errors = [case for case in cases if case["error"]]
    valid = [case for case in cases if not case["error"]]
    expected_evidence = [
        case
        for case in valid
        if case["required_evidence"] or not case["expected_abstain"]
    ]
    expected_evidence_total = max(len(expected_evidence), 1)
    latencies = [case["latency_ms"] for case in valid]
    sorted_latencies = sorted(latencies)
    p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
    p95_index = (
        min(int(len(sorted_latencies) * 0.95), len(sorted_latencies) - 1)
        if sorted_latencies
        else 0
    )
    p95 = sorted_latencies[p95_index] if sorted_latencies else 0.0
    contribution = {
        "vector": sum(case["contribution"]["vector"] for case in valid),
        "graph": sum(case["contribution"]["graph"] for case in valid),
        "both": sum(case["contribution"]["both"] for case in valid),
    }
    return {
        "query_count": total,
        "error_count": len(errors),
        "expected_evidence_count": len(expected_evidence),
        "hit_at_1": sum(case["hit_top1_ok"] for case in expected_evidence),
        "recall_at_1": round(
            sum(case["recall_at_1"] for case in expected_evidence)
            / expected_evidence_total,
            4,
        ),
        "recall_at_5": round(
            sum(case["recall_at_5"] for case in expected_evidence)
            / expected_evidence_total,
            4,
        ),
        "mrr": round(
            sum(case["mrr"] for case in expected_evidence) / expected_evidence_total,
            4,
        ),
        "required_evidence_recall": round(
            sum(case["evidence_recall"] for case in expected_evidence)
            / expected_evidence_total,
            4,
        ),
        "forbidden_hit_count": sum(len(case["forbidden"]) for case in valid),
        "scope_leakage_count": sum(case["scope_leakage"] for case in valid),
        "temporal_violation_count": sum(
            case["temporal_violations"] for case in valid
        ),
        "provenance_failure_count": sum(
            case["provenance_failures"] for case in valid
        ),
        "inactive_candidate_rejection_count": sum(
            case["inactive_rejections"] for case in valid
        ),
        "abstention_accuracy": round(
            sum(case["abstention_ok"] for case in valid) / max(total, 1), 4
        ),
        "ambiguity_accuracy": round(
            sum(case["ambiguity_ok"] for case in valid) / max(total, 1), 4
        ),
        "count_accuracy": round(
            sum(case["count_ok"] for case in valid) / max(total, 1), 4
        ),
        "latency_ms": {
            "p50": round(p50, 3),
            "p95": round(p95, 3),
            "max": round(max(latencies, default=0.0), 3),
        },
        "contribution": contribution,
    }


def _delta(full: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    suffix = {key: base.get(key, 0) for key in ()}
    del suffix
    return {
        "recall_at_1_delta": round(full["recall_at_1"] - base["recall_at_1"], 4),
        "recall_at_5_delta": round(full["recall_at_5"] - base["recall_at_5"], 4),
        "mrr_delta": round(full["mrr"] - base["mrr"], 4),
        "required_evidence_recall_delta": round(
            full["required_evidence_recall"] - base["required_evidence_recall"], 4
        ),
        "forbidden_hit_count_delta": (
            full["forbidden_hit_count"] - base["forbidden_hit_count"]
        ),
        "scope_leakage_count_delta": (
            full["scope_leakage_count"] - base["scope_leakage_count"]
        ),
        "temporal_violation_count_delta": (
            full["temporal_violation_count"] - base["temporal_violation_count"]
        ),
        "provenance_failure_count_delta": (
            full["provenance_failure_count"] - base["provenance_failure_count"]
        ),
        "abstention_accuracy_delta": round(
            full["abstention_accuracy"] - base["abstention_accuracy"], 4
        ),
    }


# --------------------------------------------------------------------------- #
# metamorphic support
# --------------------------------------------------------------------------- #


def substitute(text: str, pairs: Sequence[tuple[str, str]]) -> str:
    for source, target in pairs:
        text = text.replace(source, target)
    return text


def apply_variant(
    dataset: AblationDataset, variant: MetamorphicVariant
) -> AblationDataset:
    pairs = [
        (str(pair[0]), str(pair[1]))
        for pair in variant.substitutions
        if len(pair) == 2
    ]
    fixtures = [
        item.model_copy(update={"content": substitute(item.content, pairs)})
        for item in dataset.fixtures
    ]
    queries = [
        item.model_copy(update={"query": substitute(item.query, pairs)})
        for item in dataset.queries
    ]
    return dataset.model_copy(update={"fixtures": fixtures, "queries": queries})


def _safety_metrics(
    base_cases: Sequence[dict[str, Any]], variant_cases: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Compare scope/abstention/count/evidence behaviour across substitution."""

    def buckets(cases: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
        grouped: dict[str, dict[str, int]] = {}
        for case in cases:
            item = grouped.setdefault(
                case["query_id"], {"leakage": 0, "forbidden": 0, "abstain_ok": 0, "count_ok": 0, "evidence": 0}
            )
            item["leakage"] = max(item["leakage"], case["scope_leakage"])
            item["forbidden"] = max(item["forbidden"], len(case["forbidden"]))
            item["abstain_ok"] = int(case["abstention_ok"])
            item["count_ok"] = int(case["count_ok"])
            item["evidence"] = 1 if not case["missing"] else 0
        return grouped

    base_buckets = buckets(base_cases)
    variant_buckets = buckets(variant_cases)
    diverged = []
    for query_id, base in base_buckets.items():
        variant = variant_buckets.get(query_id)
        if variant != base:
            diverged.append(
                {
                    "query_id": query_id,
                    "base": base,
                    "variant": variant,
                }
            )
    return {
        "safe": not diverged,
        "query_count": len(base_buckets),
        "diverged_queries": diverged,
    }


# --------------------------------------------------------------------------- #
# direct diagnostics
# --------------------------------------------------------------------------- #


async def _direct_scan(
    semantic: Any,
    store: Any,
    dataset: AblationDataset,
    scopes: dict[str, MemoryScope],
    source_name: str,
    *,
    graph: Any | None = None,
) -> dict[str, Any]:
    """Diagnostic: raw semantic candidates before Store revalidation."""
    from doppel_memory.store import MemoryFilter

    per_query: list[dict[str, Any]] = []
    total_candidates = 0
    total_scope_leak_candidates = 0
    total_orphan_candidates = 0
    total_inactive_candidates = 0
    total_store_reload_ok = 0
    total_errors = 0
    fallback_edges = 0
    rich_edges = 0
    attribution_by_query: dict[str, list[dict[str, Any]]] = {}
    for query in dataset.queries:
        bound_scopes = [scopes[name] for name in query.scopes]
        allowed = {scope.scope_key for scope in bound_scopes}
        try:
            candidates = await semantic.search(
                query.query,
                bound_scopes,
                filters=MemoryFilter(tags={"personal-memory"}),
                limit=10,
            )
        except Exception as exc:  # noqa: BLE001 - structured diagnostic
            per_query.append(
                {
                    "query_id": query.query_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "candidate_count": 0,
                }
            )
            total_errors += 1
            continue
        scope_leak = 0
        orphan = 0
        inactive = 0
        reload_ok = 0
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            scope = candidate.scope
            memory_id = str(candidate.memory_id or "").strip()
            if not memory_id or scope is None:
                continue
            key = (scope.scope_key, memory_id)
            if key in seen:
                continue
            seen.add(key)
            total_candidates += 1
            if scope.scope_key not in allowed:
                scope_leak += 1
                continue
            record = await store.get(scope, memory_id)
            if record is None:
                orphan += 1
                continue
            if record.state in {
                MemoryState.EXPIRED,
                MemoryState.SUPERSEDED,
                MemoryState.REJECTED,
            }:
                inactive += 1
                continue
            reload_ok += 1
        total_scope_leak_candidates += scope_leak
        total_orphan_candidates += orphan
        total_inactive_candidates += inactive
        total_store_reload_ok += reload_ok
        per_query.append(
            {
                "query_id": query.query_id,
                "candidate_count": len(seen),
                "scope_leak_candidates": scope_leak,
                "orphan_candidates": orphan,
                "inactive_candidates": inactive,
                "store_reload_ok": reload_ok,
            }
        )
    if graph is not None and source_name == SOURCE_GRAPH:
        try:
            from graphiti_core.nodes import EpisodicNode

            from doppel_memory.graphiti_store import _memory_id_from_episode_name

            for query in dataset.queries:
                bound_scopes = [scopes[name] for name in query.scopes]
                group_ids = [scope.scope_key for scope in bound_scopes]
                edges = await graph.search(
                    query.query.strip(),
                    group_ids=group_ids,
                    num_results=10,
                )
                rows: list[dict[str, Any]] = []
                for edge in edges:
                    name = str(getattr(edge, "name", "") or "")
                    edge_uuid = str(getattr(edge, "uuid", "") or "")
                    is_fallback = name == FALLBACK_EDGE_NAME
                    if is_fallback:
                        fallback_edges += 1
                    elif name:
                        rich_edges += 1
                    for episode_uuid in getattr(edge, "episodes", None) or []:
                        memory_id = ""
                        try:
                            episode = await EpisodicNode.get_by_uuid(
                                graph.driver, str(episode_uuid)
                            )
                            memory_id = _memory_id_from_episode_name(
                                str(getattr(episode, "name", "") or "")
                            )
                        except Exception:  # noqa: BLE001 - attribution best effort
                            memory_id = ""
                        rows.append(
                            {
                                "edge_name": name,
                                "edge_uuid": edge_uuid,
                                "episode_uuid": str(episode_uuid),
                                "memory_id": memory_id,
                                "edge_kind": (
                                    "fallback" if is_fallback else "rich"
                                ),
                            }
                        )
                attribution_by_query[query.query_id] = rows
        except Exception as exc:  # noqa: BLE001 - diagnostic best effort
            per_query.append(
                {
                    "query_id": "graph-edge-classification",
                    "error": f"{type(exc).__name__}: {exc}",
                    "candidate_count": 0,
                }
            )
    return {
        "execution_profile": f"{source_name}_direct",
        "candidate_sources": [source_name],
        "candidate_count": total_candidates,
        "scope_leak_candidate_count": total_scope_leak_candidates,
        "orphan_candidate_count": total_orphan_candidates,
        "inactive_candidate_count": total_inactive_candidates,
        "store_reload_ok_count": total_store_reload_ok,
        "error_count": total_errors,
        "returned_edge_counts": {
            "returned_fallback_edges": fallback_edges,
            "returned_rich_edges": rich_edges,
        },
        "edge_attribution_by_query": attribution_by_query,
        "cases": per_query,
        "note": (
            "index-direct diagnostics bypass the query engine; they do not "
            "measure end-to-end correctness and their counts are not comparable "
            "across queries. returned_edge_counts are raw search edge counts and "
            "must not be called final-hit contributions; final-hit attribution "
            "lives in report.graph_final_hit_attribution and requires the full "
            "engine chain (accepted hit after Store revalidation)."
        ),
    }


# --------------------------------------------------------------------------- #
# main benchmark
# --------------------------------------------------------------------------- #


async def run_ablation(
    dataset: AblationDataset,
    *,
    profiles: Sequence[str] = PROFILE_MAIN,
    planner_modes: Sequence[str] = PLANNER_MODES,
    require_live_postgres: bool = False,
    require_live_neo4j: bool = False,
    run_metamorphic: bool = True,
) -> dict[str, Any]:
    unknown = set(profiles).difference(ALL_PROFILES)
    if unknown:
        raise ValueError(f"unknown profiles: {sorted(unknown)}")
    unknown_modes = set(planner_modes).difference(PLANNER_MODES)
    if unknown_modes:
        raise ValueError(f"unknown planner modes: {sorted(unknown_modes)}")
    started = perf_counter()
    store_dir = tempfile.mkdtemp(prefix="doppel-ablation-store-")
    store_path = Path(store_dir) / "store.sqlite3"
    scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
    group_ids = [scope.scope_key for scope in scopes.values()]

    from doppel_memory.sqlite_store import SQLiteStore

    store = SQLiteStore(database=str(store_path))
    since = utc_now()
    records = [
        _memory_record(item, scopes[item.scope], since) for item in dataset.fixtures
    ]
    graph: Any | None = None
    graph_index: Any | None = None
    pg_store: Any | None = None
    vector_index: Any | None = None
    vector_reason = ""
    graph_reason = ""
    graph_seed_stats: dict[str, Any] = {}
    try:
        for record in records:
            written = await store.put(record)
            if written.status not in {WriteStatus.CREATED, WriteStatus.DUPLICATE}:
                raise RuntimeError(
                    f"fixture memory was not created: {record.memory_id}: {written}"
                )

        # --- vector availability ------------------------------------------- #
        pg_password = os.environ.get("DOPPEL_ABLATION_PG_PASSWORD", "")
        vector_reason = await _probe_postgres(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=pg_password,
        )
        if not vector_reason:
            pg_store = await _build_vector_index(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DATABASE,
                user=PG_USER,
                password=pg_password,
            )
            vector_index = await _build_vector_candidates(pg_store, records)

        # --- graph availability ------------------------------------------- #
        graph_reason = await _probe_neo4j(
            NEO4J_URI, NEO4J_USER, os.environ.get("NEO4J_PASSWORD", "")
        )
        if not graph_reason:
            graph = await _build_graphiti_client(NEO4J_URI, NEO4J_USER, os.environ.get("NEO4J_PASSWORD", ""))
            await _cleanup_graph_scope(graph, group_ids)
            graph_seed_stats = await _preseed_graph(graph, records, graph_kind="mixed")
            graph_index = await _build_graph_index(store, graph)

        semantic_by_source: dict[str, Any] = {}
        if vector_index is not None:
            semantic_by_source[SOURCE_VECTOR] = vector_index
        if graph_index is not None:
            semantic_by_source[SOURCE_GRAPH] = graph_index

        report = await _run_profiles(
            store=store,
            scopes=scopes,
            dataset=dataset,
            profiles=profiles,
            semantic_by_source=semantic_by_source,
            graph=graph,
            planner_modes=planner_modes,
        )
        report["runtime"] = {
            "store": {
                "kind": "sqlite",
                "available": True,
                "path_shape": "tempfile(sqlite3)",
            },
            "vector": {
                "kind": "postgresql_pgvector",
                "available": not bool(vector_reason),
                "reason": vector_reason,
                "metadata": {
                    "provider": _LocalEmbeddingProvider.name,
                    "dimensions": str(_LocalEmbeddingProvider().dimensions),
                    "normalization": "none",
                    "distance_metric": "cosine",
                    "candidate_limit": "10",
                    "host": PG_HOST,
                    "port": str(PG_PORT),
                    "database": PG_DATABASE,
                    "user": PG_USER,
                },
            },
            "graph": {
                "kind": "neo4j_graphiti",
                "available": not bool(graph_reason),
                "reason": graph_reason,
                "metadata": {
                    "uri_host": "bolt://127.0.0.1:7687",
                    "user": NEO4J_USER,
                    "preseed": graph_seed_stats,
                },
            },
        }
        report["elapsed_seconds"] = round(perf_counter() - started, 3)
        report["doppel_version"] = __version__
        report["generated_at"] = utc_now().isoformat()
        report["suite_fingerprint"] = dataset.fingerprint
        return report
    finally:
        if store is not None:
            await store.close()
        if graph is not None and group_ids:
            try:
                await _cleanup_graph_scope(graph, group_ids)
            except Exception as exc:  # noqa: BLE001 - cleanup best effort
                print(
                    f"ablation graph cleanup failed (best effort): {exc}",
                    file=sys.stderr,
                )
            await graph.close()
        if pg_store is not None:
            await pg_store.close()


async def _run_profiles(
    *,
    store: Any,
    scopes: dict[str, MemoryScope],
    dataset: AblationDataset,
    profiles: Sequence[str],
    semantic_by_source: dict[str, Any],
    graph: Any | None,
    planner_modes: Sequence[str] = PLANNER_MODES,
) -> dict[str, Any]:
    unknown_modes = set(planner_modes).difference(PLANNER_MODES)
    if unknown_modes:
        raise ValueError(f"unknown planner modes: {sorted(unknown_modes)}")
    vector_available = SOURCE_VECTOR in semantic_by_source
    graph_available = SOURCE_GRAPH in semantic_by_source
    vector_source = semantic_by_source.get(SOURCE_VECTOR)
    graph_source = semantic_by_source.get(SOURCE_GRAPH)
    composite = (
        await _build_composite_index(vector_source, graph_source)
        if vector_available and graph_available
        else None
    )
    profile_to_semantic: dict[str, Any | None] = {
        "lexical": None,
        "lexical_vector": vector_source if vector_available else None,
        "lexical_graph": graph_source if graph_available else None,
        # full hybrid executes only when BOTH indexes are available.
        "lexical_vector_graph": composite,
    }
    planners: dict[str, Any] = {
        PLANNER_MODE_DETERMINISTIC: DeterministicPersonalMemoryQueryPlanner(),
        PLANNER_MODE_ORACLE: BenchmarkOraclePlanner(dataset.queries),
    }
    per_mode: dict[str, dict[str, dict[str, Any]]] = {}
    all_cases: list[dict[str, Any]] = []
    deferred_queries: list[str] = []
    for mode in planner_modes:
        planner = planners[mode]
        per_profile: dict[str, dict[str, Any]] = {}
        for profile in PROFILE_MAIN:
            if profile not in profiles:
                continue
            semantic = profile_to_semantic[profile]
            if semantic is None and profile != "lexical":
                per_profile[profile] = {
                    "query_count": len(dataset.queries),
                    "error_count": len(dataset.queries),
                    "unavailable": True,
                    "reason": "semantic source unavailable (see runtime)",
                }
                continue
            engine = _engines(store, semantic)
            cases: list[dict[str, Any]] = []
            for query in dataset.queries:
                if query.partition == "deferred_cross_subject":
                    deferred_queries.append(query.query_id)
                    continue
                cases.append(
                    await _run_case(
                        engine, planner, query, scopes, profile=profile, mode=mode
                    )
                )
            per_profile[profile] = _aggregate(cases)
            all_cases.extend(cases)
        per_mode[mode] = per_profile

    diagnostics: dict[str, dict[str, Any]] = {}
    if "vector_direct" in profiles and vector_source is not None:
        diagnostics["vector_direct"] = await _direct_scan(
            vector_source, store, dataset, scopes, SOURCE_VECTOR
        )
    if "graph_direct" in profiles and graph_source is not None:
        diagnostics["graph_direct"] = await _direct_scan(
            graph_source, store, dataset, scopes, SOURCE_GRAPH, graph=graph
        )
    if "composite_direct" in profiles and composite is not None:
        diagnostics["composite_direct"] = await _direct_scan(
            composite, store, dataset, scopes, "composite"
        )
    # A single-source composite is a degradation diagnostic, never full hybrid.
    if not vector_available and graph_available:
        single = await _build_composite_index(None, graph_source)
        degraded = await _direct_scan(
            single, store, dataset, scopes, "composite_graph_only"
        )
        degraded["execution_profile"] = "composite_graph_only_degradation"
        degraded["note"] = (
            "single-source composite degradation diagnostic (graph only); "
            "this is NOT the full hybrid profile"
        )
        diagnostics["composite_graph_only_degradation"] = degraded
    if vector_available and not graph_available:
        single = await _build_composite_index(vector_source, None)
        degraded = await _direct_scan(
            single, store, dataset, scopes, "composite_vector_only"
        )
        degraded["execution_profile"] = "composite_vector_only_degradation"
        degraded["note"] = (
            "single-source composite degradation diagnostic (vector only); "
            "this is NOT the full hybrid profile"
        )
        diagnostics["composite_vector_only_degradation"] = degraded

    report: dict[str, Any] = {
        "runner": "doppel.personal-retrieval-ablation.v1",
        "dataset": {
            "name": dataset.suite,
            "version": dataset.suite_version,
            "status": dataset.status,
            "frozen": dataset.frozen,
            "publication_ready": dataset.publication_ready,
            "fingerprint": dataset.fingerprint,
            "memory_count": len(dataset.fixtures),
            "query_count": len(dataset.queries),
            "partition_counts": {
                name: sum(1 for query in dataset.queries if query.partition == name)
                for name in ("dev", "heldout", "adversarial", "deferred_cross_subject")
            },
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "planner_modes": list(planner_modes),
        "profiles": per_mode,
        "diagnostics": diagnostics,
        "comparisons": {},
        "hard_gates": {
            "planner_failures": [],
            "retrieval_failures": [],
            "security_failures": [],
            "fixture_validation_failures": [],
        },
        "cases": all_cases,
        "deferred_queries": sorted(set(deferred_queries)),
        "metamorphic": {},
    }
    comparisons: dict[str, dict[str, Any]] = {}
    for mode in planner_modes:
        full = per_mode[mode].get("lexical_vector_graph")
        for base_name in ("lexical", "lexical_vector", "lexical_graph"):
            base = per_mode[mode].get(base_name)
            if (
                full is not None
                and base is not None
                and not base.get("unavailable", False)
                and not full.get("unavailable", False)
            ):
                comparisons[f"{mode}_full_vs_{base_name}"] = _delta(full, base)
    report["comparisons"] = comparisons

    layered: dict[str, list[str]] = {
        "planner_failures": [],
        "retrieval_failures": [],
        "security_failures": [],
        "fixture_validation_failures": [],
    }
    for case in all_cases:
        if case["error"]:
            layered["retrieval_failures"].append(
                f"{case['query_id']}:execution_error:{case['error'][:120]}"
            )
            continue
        for failure in case["planner_failures"]:
            layered["planner_failures"].append(f"{case['query_id']}:{failure}")
        for failure in case["retrieval_failures"]:
            layered["retrieval_failures"].append(f"{case['query_id']}:{failure}")
        for failure in case["security_failures"]:
            layered["security_failures"].append(f"{case['query_id']}:{failure}")
    report["hard_gates"] = {
        key: sorted(set(items)) for key, items in layered.items()
    }
    report["graph_final_hit_attribution"] = _build_final_hit_attribution(
        report=report,
        dataset=dataset,
        per_mode=per_mode,
    )
    return report


def _build_final_hit_attribution(
    *,
    report: dict[str, Any],
    dataset: AblationDataset,
    per_mode: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Cross the engine's accepted final hits with per-edge graph mapping.

    Only a candidate that survived Store revalidation and appears in the query
    engine's final hit list counts as a final-hit contribution. Requires the
    oracle mode so the plan is not itself a confound.
    """
    graph_direct = report.get("diagnostics", {}).get("graph_direct")
    attribution_by_query = (
        graph_direct.get("edge_attribution_by_query", {}) if graph_direct else {}
    )
    if not attribution_by_query:
        return {
            "available": False,
            "reason": "graph_direct diagnostic did not produce per-edge mapping",
            "fallback_edge_final_hit_links": None,
            "rich_edge_final_hit_links": None,
            "unique_final_hits_with_fallback": None,
            "unique_final_hits_with_rich": None,
            "unique_queries_with_fallback": None,
            "unique_queries_with_rich": None,
        }
    oracle_cases = [
        case
        for case in report.get("cases", [])
        if case.get("mode") == PLANNER_MODE_ORACLE
        and case.get("profile") == "lexical_graph"
        and not case.get("error")
    ]
    by_query = {case["query_id"]: case for case in oracle_cases}
    fallback_links: set[tuple[str, str, str, str]] = set()
    rich_links: set[tuple[str, str, str, str]] = set()
    fallback_hits: set[tuple[str, str]] = set()
    rich_hits: set[tuple[str, str]] = set()
    fallback_queries: set[str] = set()
    rich_queries: set[str] = set()
    mapped_queries = 0
    for query in dataset.queries:
        case = by_query.get(query.query_id)
        if case is None:
            continue
        final_hits = set(case.get("hits", []))
        rows = attribution_by_query.get(query.query_id, [])
        if not rows:
            continue
        mapped_queries += 1
        for row in rows:
            memory_id = str(row.get("memory_id") or "")
            if not memory_id or memory_id not in final_hits:
                continue
            link = (
                query.query_id,
                memory_id,
                str(row.get("edge_uuid") or ""),
                str(row.get("episode_uuid") or ""),
            )
            if row.get("edge_kind") == "fallback":
                fallback_links.add(link)
                fallback_hits.add((query.query_id, memory_id))
                fallback_queries.add(query.query_id)
            else:
                rich_links.add(link)
                rich_hits.add((query.query_id, memory_id))
                rich_queries.add(query.query_id)
    return {
        "available": True,
        "method": (
            "unique edge/episode-to-hit links refined by oracle lexical_graph "
            "final accepted hits (Store revalidation + ranking); link counts are "
            "not unique hit counts"
        ),
        "fallback_edge_final_hit_links": len(fallback_links),
        "rich_edge_final_hit_links": len(rich_links),
        "unique_final_hits_with_fallback": len(fallback_hits),
        "unique_final_hits_with_rich": len(rich_hits),
        "unique_queries_with_fallback": len(fallback_queries),
        "unique_queries_with_rich": len(rich_queries),
        "queries_with_mapping": mapped_queries,
    }


def _engines(store: Any, semantic: Any | None) -> PersonalMemoryQueryEngine:
    return PersonalMemoryQueryEngine(store, semantic_index=semantic)


# --------------------------------------------------------------------------- #
# metamorphic sweep
# --------------------------------------------------------------------------- #


async def _run_metamorphic_safety(
    dataset: AblationDataset,
    scopes: dict[str, MemoryScope],
    store: Any,
    planner: Any,
    *,
    mode: str = PLANNER_MODE_DETERMINISTIC,
) -> dict[str, Any]:
    """Run the lexical profile on each substituted variant and compare safety."""
    from doppel_memory.sqlite_store import SQLiteStore

    results: dict[str, Any] = {}
    base_engine = _engines(store, None)
    base_cases = [
        await _run_case(
            base_engine, planner, query, scopes, profile="lexical", mode=mode
        )
        for query in dataset.queries
    ]
    for variant in dataset.metamorphic_variants:
        variant_dataset = apply_variant(dataset, variant)
        variant_dir = tempfile.mkdtemp(prefix="doppel-ablation-variant-")
        variant_store = SQLiteStore(database=str(Path(variant_dir) / "store.sqlite3"))
        since = utc_now()
        try:
            for item in variant_dataset.fixtures:
                record = _memory_record(item, scopes[item.scope], since)
                written = await variant_store.put(record)
                if written.status not in {
                    WriteStatus.CREATED,
                    WriteStatus.DUPLICATE,
                }:
                    raise RuntimeError(
                        f"variant fixture was not created: {record.memory_id}"
                    )
            engine = _engines(variant_store, None)
            variant_cases = [
                await _run_case(
                    engine, planner, query, scopes, profile="lexical", mode=mode
                )
                for query in variant_dataset.queries
            ]
            results[variant.name] = _safety_metrics(base_cases, variant_cases)
        finally:
            await variant_store.close()
    return results


# --------------------------------------------------------------------------- #
# threshold sweep
# --------------------------------------------------------------------------- #


def build_threshold_sweep(cases: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        if case["error"]:
            continue
        hits = case["hit_scores"]
        top = hits[0] if hits else None
        rows.append(
            {
                "query_id": case["query_id"],
                "positive": bool(case["hits"])
                and not case["missing"],
                "negative": not case["hits"],
                "top_score": top["score"] if top else 0.0,
                "top_lexical": top["lexical_score"] if top else 0.0,
                "top_semantic": top["semantic_score"] if top else 0.0,
            }
        )
    sweep: list[dict[str, Any]] = []
    for threshold in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        positives = sum(1 for row in rows if row["positive"])
        negatives = sum(1 for row in rows if row["negative"])
        sweep.append(
            {
                "threshold": threshold,
                "positive_recall": round(
                    sum(
                        1
                        for row in rows
                        if row["positive"] and row["top_score"] >= threshold
                    )
                    / max(positives, 1),
                    4,
                ),
                "negative_fp_rate": round(
                    sum(
                        1
                        for row in rows
                        if row["negative"] and row["top_score"] >= threshold
                    )
                    / max(negatives, 1),
                    4,
                ),
            }
        )
    return {
        "note": (
            "distribution only; thresholds are not applied to retrieval and "
            "must not be hardcoded from dev-only fixtures"
        ),
        "positive_rows": sum(1 for row in rows if row["positive"]),
        "negative_rows": sum(1 for row in rows if row["negative"]),
        "sweep": sweep,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Doppel v0.9 personal hybrid retrieval ablation",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="ablation dataset manifest (default: bundled zh-v1)",
    )
    parser.add_argument(
        "--profiles",
        default=",".join(PROFILE_MAIN),
        help=(
            "comma-separated profiles; main: "
            + ",".join(PROFILE_MAIN)
            + "; diagnostics: "
            + ",".join(PROFILE_DIRECT)
        ),
    )
    parser.add_argument("--output", type=Path, default=None, help="report JSON path")
    parser.add_argument(
        "--planner-modes",
        default=",".join(PLANNER_MODES),
        help="comma-separated planner modes: oracle,deterministic",
    )
    parser.add_argument(
        "--require-live-postgres",
        action="store_true",
        help="exit non-zero when pgvector is unavailable",
    )
    parser.add_argument(
        "--require-live-neo4j",
        action="store_true",
        help="exit non-zero when Neo4j is unavailable",
    )
    parser.add_argument(
        "--require-all-profiles",
        action="store_true",
        help="exit non-zero when any requested profile could not execute",
    )
    parser.add_argument("--max-scope-leakage", type=int, default=0)
    parser.add_argument("--max-temporal-violations", type=int, default=0)
    parser.add_argument("--no-metamorphic", action="store_true")
    return parser


def _validate_report(
    report: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> list[str]:
    failures: list[str] = []
    runtime = report.get("runtime", {})
    if args.require_live_postgres and not runtime.get("vector", {}).get("available"):
        failures.append("required live PostgreSQL/pgvector but it is unavailable")
    if args.require_live_neo4j and not runtime.get("graph", {}).get("available"):
        failures.append("required live Neo4j but it is unavailable")
    modes = [mode for mode in (args.planner_modes or "").split(",") if mode.strip()]
    if args.require_all_profiles:
        for profile in (args.profiles or "").split(","):
            profile = profile.strip()
            if not profile or profile in PROFILE_DIRECT:
                continue
            for mode in modes:
                item = (report.get("profiles", {}).get(mode) or {}).get(profile)
                error_count = (item or {}).get("error_count", 0)
                query_count = (item or {}).get("query_count", 0)
                if (item or {}).get("unavailable") or (
                    query_count and error_count == query_count
                ):
                    failures.append(f"profile {profile} ({mode}) did not execute")
    hard_gates = report.get("hard_gates", {})
    for group, items in hard_gates.items():
        if items:
            failures.append(f"{group}: {items[:5]}")
    for mode in modes:
        full = (report.get("profiles", {}).get(mode) or {}).get(
            "lexical_vector_graph"
        )
        if (full or {}).get("scope_leakage_count", 0) > args.max_scope_leakage:
            failures.append("scope leakage exceeds --max-scope-leakage")
        if (full or {}).get("temporal_violation_count", 0) > args.max_temporal_violations:
            failures.append("temporal violations exceed --max-temporal-violations")
    return failures


def _git_commit_hash() -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip() or ""
    except Exception:  # noqa: BLE001 - best effort
        return ""


async def _async_main(args: argparse.Namespace) -> int:
    dataset = load_ablation_dataset(args.dataset)
    profiles = tuple(name.strip() for name in args.profiles.split(",") if name.strip())
    modes = tuple(name.strip() for name in args.planner_modes.split(",") if name.strip())
    report = await run_ablation(
        dataset,
        profiles=profiles,
        planner_modes=modes,
        require_live_postgres=args.require_live_postgres,
        require_live_neo4j=args.require_live_neo4j,
        run_metamorphic=not args.no_metamorphic,
    )
    if not args.no_metamorphic:
        scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
        store_dir = tempfile.mkdtemp(prefix="doppel-ablation-meta-")
        from doppel_memory.sqlite_store import SQLiteStore

        meta_store = SQLiteStore(database=str(Path(store_dir) / "store.sqlite3"))
        planner = DeterministicPersonalMemoryQueryPlanner()
        try:
            since = utc_now()
            for item in dataset.fixtures:
                record = _memory_record(item, scopes[item.scope], since)
                await meta_store.put(record)
            report["metamorphic"] = await _run_metamorphic_safety(
                dataset,
                scopes,
                meta_store,
                planner,
                mode=PLANNER_MODE_DETERMINISTIC,
            )
        finally:
            await meta_store.close()
    cases = report.get("cases", [])
    if cases:
        report["threshold_sweep"] = build_threshold_sweep(cases)
    executed = sorted(
        {
            f"{mode}:{profile}"
            for mode, profiles_by_mode in report.get("profiles", {}).items()
            for profile in profiles_by_mode
            if not profiles_by_mode[profile].get("unavailable", False)
        }
    )
    unavailable = sorted(
        {
            f"{mode}:{profile}"
            for mode, profiles_by_mode in report.get("profiles", {}).items()
            for profile in profiles_by_mode
            if profiles_by_mode[profile].get("unavailable", False)
        }
    )
    report["reproducibility"] = {
        "output_path": (
            str(Path(args.output).resolve()) if args.output is not None else ""
        ),
        "command": " ".join(sys.argv),
        "commit_hash": _git_commit_hash(),
        "planner_modes": list(modes),
        "requested_profiles": list(profiles),
        "executed_profiles": executed,
        "unavailable_profiles": unavailable,
        "dataset_fingerprint": report.get("suite_fingerprint", ""),
        "canonical_payload_sha256": "",
        "file_sha256_sidecar": (
            str(Path(f"{args.output}.sha256").resolve())
            if args.output is not None
            else ""
        ),
    }
    canonical = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    report["reproducibility"]["canonical_payload_sha256"] = hashlib.sha256(
        canonical
    ).hexdigest()
    file_sha256 = ""
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        args.output.write_bytes(report_bytes)
        file_sha256 = hashlib.sha256(report_bytes).hexdigest()
        sidecar = Path(f"{args.output}.sha256")
        sidecar.write_text(
            f"{file_sha256}  {args.output.name}\n",
            encoding="utf-8",
        )
    failures = _validate_report(report, args=args)
    print(
        json.dumps(
            {
                "planner_modes": modes,
                "profiles": report.get("profiles", {}),
                "comparisons": report.get("comparisons", {}),
                "hard_gates": report.get("hard_gates", {}),
                "graph_final_hit_attribution": report.get(
                    "graph_final_hit_attribution", {}
                ),
                "reproducibility": report.get("reproducibility", {}),
                "file_sha256": file_sha256,
                "runtime": report.get("runtime", {}),
                "metamorphic_safe": all(
                    item.get("safe", False)
                    for item in report.get("metamorphic", {}).values()
                )
                if report.get("metamorphic")
                else None,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

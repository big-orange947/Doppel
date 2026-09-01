"""v0.9 personal hybrid retrieval ablation benchmark.

Compares four main execution profiles over the same pre-extracted fixture set:

- ``lexical``                : Store structural/lexical scan only (no semantic index)
- ``lexical_vector``         : Store lexical candidates + pgvector semantic candidates
- ``lexical_graph``          : Store lexical candidates + Graphiti graph candidates
- ``lexical_vector_graph``   : Store lexical candidates + weighted RRF of both indexes
- ``lexical_relation``       : Store lexical candidates + Graphiti rich relations
- ``lexical_vector_relation``: pgvector semantic + Graphiti relation-only candidates
- ``lexical_relation_reranked``: relation-only candidates + local cross-encoder
- ``lexical_vector_relation_reranked``: pgvector + reranked relation candidates

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
import math
import os
import platform
import re
import sys
import tempfile
from collections import Counter
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
    RelationRerankRequest,
    RelationRerankScore,
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
PROFILE_RELATION_BASE = ("lexical_relation", "lexical_vector_relation")
PROFILE_RELATION_RERANKED = (
    "lexical_relation_reranked",
    "lexical_vector_relation_reranked",
)
PROFILE_RELATION = (*PROFILE_RELATION_BASE, *PROFILE_RELATION_RERANKED)
PROFILE_EXECUTION = (*PROFILE_MAIN, *PROFILE_RELATION)
PROFILE_DIRECT = ("vector_direct", "graph_direct", "composite_direct")
ALL_PROFILES = (*PROFILE_EXECUTION, *PROFILE_DIRECT)

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


class AblationRelation(BaseModel):
    """Gold rich edge used only by the repository relation benchmark."""

    model_config = ConfigDict(frozen=True)

    source_entity: str
    relation_type: str
    target_entity: str
    fact: str
    edge_kind: Literal["rich", "fallback"] = "rich"


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
    relation: AblationRelation | None = None


class AblationQuery(BaseModel):
    """One labeled retrieval case."""

    model_config = ConfigDict(frozen=True)

    query_id: str
    query: str
    scopes: list[str] = Field(min_length=1)
    now: datetime
    intent: str
    accepted_intents: list[str] = Field(default_factory=list)
    as_of: datetime | None = None
    accept_interval_covering_as_of: bool = False
    time_from: datetime | None = None
    time_to: datetime | None = None
    entity_mentions: list[str] = Field(default_factory=list)
    relation_hints: list[str] = Field(default_factory=list)
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
        fixture_ids = [item.memory_id for item in self.fixtures]
        duplicate_fixture_ids = sorted(
            item for item, count in Counter(fixture_ids).items() if count > 1
        )
        if duplicate_fixture_ids:
            raise ValueError(f"duplicate fixture IDs: {duplicate_fixture_ids}")
        query_ids = [item.query_id for item in self.queries]
        duplicate_query_ids = sorted(
            item for item, count in Counter(query_ids).items() if count > 1
        )
        if duplicate_query_ids:
            raise ValueError(f"duplicate query IDs: {duplicate_query_ids}")
        known = set(self.scopes)
        unknown_fixtures = sorted(
            {item.scope for item in self.fixtures}.difference(known)
        )
        if unknown_fixtures:
            raise ValueError(f"fixtures reference unknown scopes: {unknown_fixtures}")
        unknown_queries = sorted(
            {scope for item in self.queries for scope in item.scopes}.difference(known)
        )
        if unknown_queries:
            raise ValueError(f"queries reference unknown scopes: {unknown_queries}")
        minimum_queries = int(self.requirements.get("min_queries", 0) or 0)
        if len(self.queries) < minimum_queries:
            raise ValueError(
                f"dataset has {len(self.queries)} queries; requires {minimum_queries}"
            )
        minimum_scopes = int(self.requirements.get("min_scopes", 0) or 0)
        if len(self.scopes) < minimum_scopes:
            raise ValueError(
                f"dataset has {len(self.scopes)} scopes; requires {minimum_scopes}"
            )
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
    relation_benchmark = bool(dataset.requirements.get("relation_benchmark", False))
    for item in dataset.fixtures:
        scope_user = scope_ids.get(item.scope, "")
        if (
            item.valid_from is not None
            and item.valid_to is not None
            and item.valid_to < item.valid_from
        ):
            failures.append(f"{item.memory_id}: valid_to precedes valid_from")
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
        overlap = sorted(
            set(query.required_memory_ids).intersection(query.forbidden_memory_ids)
        )
        if overlap:
            failures.append(
                f"{query.query_id}: required and forbidden gold overlap: {overlap}"
            )
        if query.expected_abstain and query.required_memory_ids:
            failures.append(
                f"{query.query_id}: abstention gold cannot require a memory"
            )
        if relation_benchmark and not (query.entity_mentions or query.relation_hints):
            failures.append(
                f"{query.query_id}: relation benchmark query requires an entity "
                "or relation anchor"
            )
        if query.accepted_intents and query.intent not in query.accepted_intents:
            failures.append(
                f"{query.query_id}: accepted_intents must include primary intent"
            )
        if query.accept_interval_covering_as_of and query.as_of is None:
            failures.append(
                f"{query.query_id}: interval alternative requires as_of gold"
            )
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
            if relation_benchmark and (
                fixture.relation is None or fixture.relation.edge_kind != "rich"
            ):
                failures.append(
                    f"{query.query_id}: required relation memory {memory_id} lacks a "
                    "rich edge gold label"
                )
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
                if fixture.valid_to is not None and fixture.valid_to < query.as_of:
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
PLANNER_MODE_REPORT = "report"
PLANNER_MODES = (PLANNER_MODE_ORACLE, PLANNER_MODE_DETERMINISTIC)
ALL_PLANNER_MODES = (*PLANNER_MODES, PLANNER_MODE_REPORT)


class BenchmarkOraclePlanner:
    """Fixture-grounded planner: injects only the dataset's labeled structure.

    Deliberately does not choose scopes, memory IDs, topic keys, or any retrieval
    identifier. It maps exact fixture query text back to intent/time labels and, for
    relation datasets, explicit entity/relation labels so retrieval/index/Store layers
    can be measured independently of natural-language planning.
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
            entity_mentions=fixture.entity_mentions,
            relation_hints=fixture.relation_hints,
            explanation=(
                "benchmark oracle: fixture-labeled plan; no scope, memory ID, "
                "or topic key injected"
            ),
        )


class BenchmarkReportPlanner:
    """Replay successful provider drafts from a planner-quality report.

    The report must belong to the exact current dataset. This lets one paid planner
    run feed every local retrieval profile without multiplying provider calls.
    """

    name = "doppel.benchmark-report-planner"

    def __init__(self, path: Path, dataset: AblationDataset) -> None:
        self.path = Path(path).resolve()
        payload = self.path.read_bytes()
        raw = json.loads(payload)
        source_fingerprint = str((raw.get("dataset") or {}).get("fingerprint") or "")
        if source_fingerprint != dataset.fingerprint:
            raise ValueError(
                "planner report dataset fingerprint does not match the current "
                "ablation dataset"
            )
        source_planner = dict(raw.get("planner") or {})
        self.version = (
            f"{source_planner.get('name') or 'unknown'}@"
            f"{source_planner.get('version') or 'unknown'}"
        )
        self.source = {
            "path": str(self.path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "dataset_fingerprint": source_fingerprint,
            "planner": source_planner,
            "provider_calls_during_replay": 0,
        }
        drafts: dict[str, PersonalMemoryQueryDraft] = {}
        for item in list(raw.get("cases") or []):
            query_text = str(item.get("query") or "").strip()
            if not query_text or item.get("error") or item.get("actual") is None:
                continue
            if query_text in drafts:
                raise ValueError(f"planner report repeats query text: {query_text!r}")
            drafts[query_text] = PersonalMemoryQueryDraft.model_validate(item["actual"])
        required = {
            query.query.strip()
            for query in dataset.queries
            if query.partition != "deferred_cross_subject"
        }
        missing = sorted(required.difference(drafts))
        if missing:
            raise ValueError(
                f"planner report lacks {len(missing)} successful dataset drafts"
            )
        self._drafts = drafts

    async def plan(
        self, request: PersonalMemoryQueryRequest
    ) -> PersonalMemoryQueryDraft:
        draft = self._drafts.get(str(request.query or "").strip())
        if draft is None:
            raise ValueError(
                f"planner report has no draft for query: {request.query!r}"
            )
        return draft.model_copy(
            update={
                "subject": request.default_subject,
                "subject_id": request.default_subject_id,
            }
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
    relation = getattr(item, "relation", None)
    if relation is not None:
        metadata["benchmark_relation"] = relation.model_dump(mode="json")
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
        self.version = _fastembed_version()

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


class _FastEmbedRelationReranker:
    """Benchmark-only local cross-encoder with normalized protocol scores.

    FastEmbed exposes raw cross-encoder logits. Doppel's public protocol requires a
    stable 0..1 range, so this harness applies a documented sigmoid before returning
    scores. Model selection and the acceptance threshold remain explicit CLI inputs;
    this class is intentionally not a product default.
    """

    def __init__(
        self,
        model_name: str,
        *,
        cache_dir: Path | None = None,
        batch_size: int = 32,
    ) -> None:
        self.model_name = str(model_name or "").strip()
        if not self.model_name:
            raise ValueError("relation reranker model name must not be empty")
        if batch_size < 1:
            raise ValueError("relation reranker batch size must be positive")
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self._model: Any = None
        self._model_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return f"fastembed-cross-encoder:{self.model_name}"

    @property
    def version(self) -> str:
        return _fastembed_version()

    @property
    def score_normalization(self) -> str:
        return "sigmoid(raw_cross_encoder_logit)"

    async def warmup(self) -> None:
        model = await self._ensure_model()
        await asyncio.to_thread(
            list,
            model.rerank(
                "关系查询",
                ["RELATED_TO\n关系事实"],
                batch_size=self.batch_size,
            ),
        )

    async def rerank(
        self, request: RelationRerankRequest
    ) -> Sequence[RelationRerankScore]:
        if not request.items:
            return []
        model = await self._ensure_model()
        query = request.query_text or " ".join(request.relation_hints)
        documents = [f"{item.relation_type}\n{item.fact}" for item in request.items]

        def _score() -> list[float]:
            return [
                float(value)
                for value in model.rerank(
                    query,
                    documents,
                    batch_size=self.batch_size,
                )
            ]

        raw_scores = await asyncio.to_thread(_score)
        if len(raw_scores) != len(request.items):
            raise RuntimeError(
                "relation reranker returned a different number of scores than items"
            )
        scores: list[RelationRerankScore] = []
        for item, raw_score in zip(request.items, raw_scores, strict=True):
            if not math.isfinite(raw_score):
                raise RuntimeError("relation reranker returned a non-finite score")
            probability = _sigmoid(raw_score)
            scores.append(RelationRerankScore(item_id=item.item_id, score=probability))
        return scores

    async def _ensure_model(self) -> Any:
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    kwargs: dict[str, Any] = {}
                    if self.cache_dir is not None:
                        kwargs["cache_dir"] = str(self.cache_dir)
                    self._model = await asyncio.to_thread(
                        TextCrossEncoder,
                        self.model_name,
                        **kwargs,
                    )
        return self._model


def _sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)


def _fastembed_version() -> str:
    try:
        import fastembed

        return str(getattr(fastembed, "__version__", "") or "unknown")
    except Exception:  # noqa: BLE001 - version is best effort
        return "unknown"


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
        observed_at = (
            max(evidence_times, default=record.created_at) or record.created_at
        )
        episode_id = str(
            uuid5(
                NAMESPACE_URL,
                f"doppel:{record.scope.scope_key}:{record.memory_id}",
            )
        )
        fingerprint = hashlib.sha256(record.content.encode("utf-8")).hexdigest()
        episode_name = f"DoppelMemory:v5:{_b64(record.memory_id)}:{fingerprint}:1"
        source_id = str(uuid5(NAMESPACE_URL, f"ablation:source:{episode_id}"))
        target_id = str(uuid5(NAMESPACE_URL, f"ablation:target:{episode_id}"))
        edge_id = str(uuid5(NAMESPACE_URL, f"ablation:edge:{episode_id}"))
        relation_spec = record.metadata.get("benchmark_relation")
        if isinstance(relation_spec, dict):
            source_name = str(relation_spec.get("source_entity") or "").strip()
            target_name = str(relation_spec.get("target_entity") or "").strip()
            relation_name = str(relation_spec.get("relation_type") or "").strip()
            relation_fact = str(relation_spec.get("fact") or record.content).strip()
            relation_edge_kind = str(relation_spec.get("edge_kind") or "rich").strip()
            if not source_name or not target_name or not relation_name:
                raise ValueError(
                    f"invalid benchmark relation fixture: {record.memory_id}"
                )
            if source_name == "DOPPEL_SUBJECT":
                from doppel_memory.graphiti_store import _graphiti_subject_identity

                source_name = _graphiti_subject_identity(
                    record.scope,
                    str(record.metadata.get("subject_id") or record.scope.user_id),
                )[0]
        else:
            source_name = f"owner:{record.scope.user_id}"
            target_name = str(record.metadata.get("topic_key") or "memory")
            relation_name = RICH_EDGE_NAME
            relation_fact = record.content
            relation_edge_kind = ""
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
        use_fallback = relation_edge_kind == "fallback" or (
            not relation_edge_kind
            and (graph_kind == "fallback" or (graph_kind == "mixed" and index % 2 == 0))
        )
        edge = EntityEdge(
            uuid=edge_id,
            group_id=record.scope.scope_key,
            source_node_uuid=source_id,
            target_node_uuid=target_id,
            created_at=observed_at,
            name=FALLBACK_EDGE_NAME if use_fallback else relation_name,
            fact=relation_fact,
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


async def _build_graphiti_client(uri: str, user: str, password: str) -> Any:
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
        llm_client=_NoNetworkLLM(
            LLMConfig(model="disabled-ablation-eval"), cache=False
        ),
        embedder=FastEmbedderClient(),
        cross_encoder=NoOpCrossEncoder(),
    )


async def _build_graph_index(store: Any, graph: Any) -> Any:
    from doppel_memory.graphiti_store import GraphitiSemanticIndex

    return GraphitiSemanticIndex(store, enabled=True, graphiti_client=graph)


async def _build_relation_index(
    store: Any,
    graph: Any,
    *,
    relation_reranker: Any | None = None,
    minimum_reranker_score: float | None = None,
) -> Any:
    from doppel_memory.graphiti_store import GraphitiRelationIndex

    return GraphitiRelationIndex(
        store,
        enabled=True,
        graphiti_client=graph,
        relation_reranker=relation_reranker,
        minimum_reranker_score=minimum_reranker_score,
    )


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
    from urllib.parse import quote

    from doppel_memory.postgres_store import PostgreSQLStore

    dsn = (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )
    # DSN carries credentials internally; the report only ever records
    # host/port/database/user, never the password.
    pg_store = PostgreSQLStore(dsn)
    # PostgreSQLStore initializes lazily through its public Store operations; the
    # fixture ``put`` calls below create the pool and schema before vector indexing.
    return pg_store


async def _reset_ablation_postgres(
    *, host: str, port: int, database: str, user: str, password: str
) -> None:
    """Wipe the dedicated ablation database before a run.

    ``doppel_ablation`` is a benchmark-only database (nothing but fixture rows
    and vector projections live there), so dropping and recreating the public
    schema is a safe, deterministic reset for repeatable runs.
    """
    import asyncpg

    conn = await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        timeout=5,
    )
    try:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    finally:
        await conn.close()


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


async def _build_composite_index(vector_index: Any, graph_index: Any) -> Any:
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
                "relation": 0,
                "relation_reranker": 0,
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


def _expected_intent_ok(
    result: PersonalMemoryQueryResult, query: AblationQuery
) -> bool:
    accepted = query.accepted_intents or list(
        INTENT_ALIASES.get(query.intent, (query.intent,))
    )
    return str(result.plan.intent) in accepted


def _planner_report_failures(
    result: PersonalMemoryQueryResult, query: AblationQuery
) -> list[str]:
    """Compare a replayed natural-language plan with labeled query structure."""

    failures: list[str] = []
    if not _expected_intent_ok(result, query):
        failures.append("planner_intent_miss")
    temporal_ok = True
    if query.as_of is not None:
        plan_as_of = result.plan.as_of
        point_ok = plan_as_of is not None and plan_as_of.date() == query.as_of.date()
        interval_ok = bool(
            query.accept_interval_covering_as_of
            and result.plan.time_from is not None
            and result.plan.time_to is not None
            and result.plan.time_from <= query.as_of <= result.plan.time_to
        )
        temporal_ok = point_ok or interval_ok
    elif result.plan.as_of is not None:
        temporal_ok = False
    if query.time_from is not None:
        temporal_ok = temporal_ok and result.plan.time_from == query.time_from
    if query.time_to is not None:
        temporal_ok = temporal_ok and result.plan.time_to == query.time_to
    if not temporal_ok:
        failures.append("planner_temporal_miss")
    expected_entities, unexpected_entities = _planner_term_matches(
        query.entity_mentions, list(result.plan.entity_mentions)
    )
    if expected_entities != len(query.entity_mentions) or unexpected_entities:
        failures.append("planner_entity_miss")
    expected_relations, unexpected_relations = _planner_term_matches(
        query.relation_hints, list(result.plan.relation_hints), exact=True
    )
    if expected_relations != len(query.relation_hints) or unexpected_relations:
        failures.append("planner_relation_miss")
    if result.plan.memory_types or result.plan.topic_keys:
        failures.append("planner_hard_filter_miss")
    return failures


def _planner_term_matches(
    expected: Sequence[str], actual: Sequence[str], *, exact: bool = False
) -> tuple[int, list[str]]:
    def normalized(value: str) -> str:
        return re.sub(r"[^\w\u3400-\u9fff]+", "", str(value or "").casefold())

    expected_terms = [normalized(item) for item in expected]
    actual_terms = [normalized(item) for item in actual]
    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    for expected_index, expected_term in enumerate(expected_terms):
        for actual_index, actual_term in enumerate(actual_terms):
            if actual_index in matched_actual:
                continue
            matches = (
                actual_term == expected_term
                if exact
                else (expected_term in actual_term or actual_term in expected_term)
            )
            if expected_term and actual_term and matches:
                matched_expected.add(expected_index)
                matched_actual.add(actual_index)
                break
    unexpected = [
        actual[index] for index in range(len(actual)) if index not in matched_actual
    ]
    return len(matched_expected), unexpected


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
    report_planner_failures = (
        _planner_report_failures(result, query) if mode == PLANNER_MODE_REPORT else []
    )
    temporal_plan_is_trusted = mode == PLANNER_MODE_ORACLE or (
        mode == PLANNER_MODE_REPORT
        and "planner_temporal_miss" not in report_planner_failures
    )
    for hit in hits:
        record = hit.record
        if record.scope.scope_key not in allowed_scope_keys:
            scope_leakage += 1
        if query.as_of is not None and temporal_plan_is_trusted:
            # Temporal failure is attributed to retrieval only under an oracle
            # plan (correct as_of was injected). Deterministic misses are
            # planner failures and are never counted here.
            record_valid_from = _optional_time(record.metadata.get("valid_from"))
            record_valid_to = _optional_time(record.metadata.get("valid_to"))
            if (
                record_valid_from is not None
                and record_valid_from > query.as_of
                or record_valid_to is not None
                and record_valid_to < query.as_of
            ):
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
    if mode == PLANNER_MODE_REPORT:
        planner_failures = report_planner_failures
        planner_temporal_miss = "planner_temporal_miss" in planner_failures
        planner_interval_miss = False
        planner_intent_miss = "planner_intent_miss" in planner_failures
    retrieval_failures: list[str] = []
    retrieval_plan_is_trusted = mode != PLANNER_MODE_REPORT or not planner_failures
    if temporal_plan_is_trusted and temporal_violations:
        retrieval_failures.append("retrieval_temporal_failure")
    if forbidden and retrieval_plan_is_trusted:
        retrieval_failures.append("forbidden_hit")
    if missing and not query.expected_abstain and retrieval_plan_is_trusted:
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
        "relation": 0,
        "relation_reranker": 0,
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
        if any(reason.startswith("relation_source:") for reason in hit.reasons):
            contribution["relation"] += 1
        if "relation_match_kind:reranker" in hit.reasons:
            contribution["relation_reranker"] += 1
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
                "relation_score": round(
                    float(getattr(hit, "relation_score", 0.0)),
                    6,
                ),
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
        "planner_entity_miss": "planner_entity_miss" in planner_failures,
        "planner_relation_miss": "planner_relation_miss" in planner_failures,
        "planner_hard_filter_miss": "planner_hard_filter_miss" in planner_failures,
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
        "relation": sum(case["contribution"].get("relation", 0) for case in valid),
        "relation_reranker": sum(
            case["contribution"].get("relation_reranker", 0) for case in valid
        ),
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
        "temporal_violation_count": sum(case["temporal_violations"] for case in valid),
        "provenance_failure_count": sum(case["provenance_failures"] for case in valid),
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
        (str(pair[0]), str(pair[1])) for pair in variant.substitutions if len(pair) == 2
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
                case["query_id"],
                {
                    "leakage": 0,
                    "forbidden": 0,
                    "abstain_ok": 0,
                    "count_ok": 0,
                    "evidence": 0,
                },
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
    candidate_memory_ids_by_query: dict[str, list[str]] = {}
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
        raw_ids: list[str] = []
        for candidate in candidates:
            scope = candidate.scope
            memory_id = str(candidate.memory_id or "").strip()
            if not memory_id or scope is None:
                continue
            key = (scope.scope_key, memory_id)
            if key in seen:
                continue
            seen.add(key)
            raw_ids.append(memory_id)
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
        candidate_memory_ids_by_query[query.query_id] = raw_ids
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
                                "edge_kind": ("fallback" if is_fallback else "rich"),
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
        "candidate_memory_ids_by_query": candidate_memory_ids_by_query,
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
    planner_report: Path | None = None,
    require_live_postgres: bool = False,
    require_live_neo4j: bool = False,
    run_metamorphic: bool = True,
    relation_reranker: Any | None = None,
    minimum_reranker_score: float | None = None,
    relation_reranker_reason: str = "",
) -> dict[str, Any]:
    unknown = set(profiles).difference(ALL_PROFILES)
    if unknown:
        raise ValueError(f"unknown profiles: {sorted(unknown)}")
    unknown_modes = set(planner_modes).difference(ALL_PLANNER_MODES)
    if unknown_modes:
        raise ValueError(f"unknown planner modes: {sorted(unknown_modes)}")
    if PLANNER_MODE_REPORT in planner_modes and planner_report is None:
        raise ValueError("planner mode 'report' requires planner_report")
    if minimum_reranker_score is not None and not (
        0.0 <= minimum_reranker_score <= 1.0
    ):
        raise ValueError("minimum_reranker_score must be between 0 and 1")
    reranker_requested = bool(set(profiles) & set(PROFILE_RELATION_RERANKED))
    if (
        reranker_requested
        and relation_reranker is None
        and not relation_reranker_reason
    ):
        relation_reranker_reason = "relation reranker model is not configured"
    if (
        reranker_requested
        and relation_reranker is not None
        and minimum_reranker_score is None
    ):
        relation_reranker_reason = "relation reranker threshold is not configured"
    started = perf_counter()
    store_dir = tempfile.mkdtemp(prefix="doppel-ablation-store-")
    store_path = Path(store_dir) / "store.sqlite3"
    scopes = {name: item.to_scope() for name, item in dataset.scopes.items()}
    group_ids = [scope.scope_key for scope in scopes.values()]
    vector_requested = require_live_postgres or bool(
        set(profiles)
        & {
            "lexical_vector",
            "lexical_vector_graph",
            "lexical_vector_relation",
            "lexical_vector_relation_reranked",
            "vector_direct",
            "composite_direct",
        }
    )
    graph_requested = require_live_neo4j or bool(
        set(profiles)
        & {
            "lexical_graph",
            "lexical_vector_graph",
            "lexical_relation",
            "lexical_vector_relation",
            "lexical_relation_reranked",
            "lexical_vector_relation_reranked",
            "graph_direct",
            "composite_direct",
        }
    )

    # v0.9 keeps PostgreSQL authoritative when it is live; SQLite is the
    # degradation path. The same authoritative store backs the pgvector
    # projection so index_records can re-load records it indexes (orphan
    # protection) instead of duplicating another authority.
    pg_password = os.environ.get("DOPPEL_ABLATION_PG_PASSWORD", "")
    vector_reason = (
        await _probe_postgres(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=pg_password,
        )
        if vector_requested
        else "not requested"
    )
    store: Any = None
    pg_store: Any | None = None
    if not vector_reason:
        await _reset_ablation_postgres(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=pg_password,
        )
        pg_store = await _build_vector_index(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=pg_password,
        )
        store = pg_store
    else:
        from doppel_memory.sqlite_store import SQLiteStore

        store = SQLiteStore(database=str(store_path))
    store_kind = "postgresql" if pg_store is not None else "sqlite"
    since = utc_now()
    records = [
        _memory_record(item, scopes[item.scope], since) for item in dataset.fixtures
    ]
    graph: Any | None = None
    graph_index: Any | None = None
    relation_index: Any | None = None
    relation_reranked_index: Any | None = None
    vector_index: Any | None = None
    graph_reason = ""
    graph_seed_stats: dict[str, Any] = {}
    try:
        for record in records:
            written = await store.put(record)
            if written.status not in {WriteStatus.CREATED, WriteStatus.DUPLICATE}:
                raise RuntimeError(
                    f"fixture memory was not created: {record.memory_id}: {written}"
                )

        # --- vector index (same authoritative store) ------------------------ #
        if not vector_reason:
            vector_index = await _build_vector_candidates(pg_store, records)

        # --- graph availability ------------------------------------------- #
        graph_reason = (
            await _probe_neo4j(
                NEO4J_URI, NEO4J_USER, os.environ.get("NEO4J_PASSWORD", "")
            )
            if graph_requested
            else "not requested"
        )
        if not graph_reason:
            graph = await _build_graphiti_client(
                NEO4J_URI, NEO4J_USER, os.environ.get("NEO4J_PASSWORD", "")
            )
            await _cleanup_graph_scope(graph, group_ids)
            graph_seed_stats = await _preseed_graph(graph, records, graph_kind="mixed")
            graph_index = await _build_graph_index(store, graph)
            relation_index = await _build_relation_index(store, graph)
            if (
                relation_reranker is not None
                and minimum_reranker_score is not None
                and not relation_reranker_reason
            ):
                relation_reranked_index = await _build_relation_index(
                    store,
                    graph,
                    relation_reranker=relation_reranker,
                    minimum_reranker_score=minimum_reranker_score,
                )

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
            relation_index=relation_index,
            relation_reranked_index=relation_reranked_index,
            graph=graph,
            planner_modes=planner_modes,
            planner_report=planner_report,
        )
        report["runtime"] = {
            "store": {
                "kind": store_kind,
                "available": True,
                "path_shape": (
                    "postgresql(doppel_ablation)"
                    if pg_store is not None
                    else "tempfile(sqlite3)"
                ),
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
                    "direct_diagnostic_candidate_limit": "10",
                    "engine_semantic_candidate_limit": "100",
                    "composite_candidate_multiplier": "4",
                    "composite_per_source_requested_limit": "400",
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
            "relation_reranker": {
                "kind": "relation_cross_encoder",
                "available": relation_reranked_index is not None,
                "reason": (
                    "not requested"
                    if not reranker_requested
                    else relation_reranker_reason or "relation graph is unavailable"
                    if relation_reranked_index is None
                    else ""
                ),
                "metadata": {
                    "provider": (
                        str(getattr(relation_reranker, "name", "") or "")
                        if relation_reranker is not None
                        else ""
                    ),
                    "version": (
                        str(getattr(relation_reranker, "version", "") or "")
                        if relation_reranker is not None
                        else ""
                    ),
                    "minimum_score": (
                        str(minimum_reranker_score)
                        if minimum_reranker_score is not None
                        else ""
                    ),
                    "score_normalization": str(
                        getattr(
                            relation_reranker,
                            "score_normalization",
                            "provider-normalized 0..1",
                        )
                    ),
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
        if pg_store is not None:
            try:
                await _reset_ablation_postgres(
                    host=PG_HOST,
                    port=PG_PORT,
                    database=PG_DATABASE,
                    user=PG_USER,
                    password=pg_password,
                )
            except Exception as exc:  # noqa: BLE001 - cleanup best effort
                print(
                    f"ablation PostgreSQL cleanup failed (best effort): {exc}",
                    file=sys.stderr,
                )
        if graph is not None and group_ids:
            try:
                await _cleanup_graph_scope(graph, group_ids)
            except Exception as exc:  # noqa: BLE001 - cleanup best effort
                print(
                    f"ablation graph cleanup failed (best effort): {exc}",
                    file=sys.stderr,
                )
            await graph.close()


async def _run_profiles(
    *,
    store: Any,
    scopes: dict[str, MemoryScope],
    dataset: AblationDataset,
    profiles: Sequence[str],
    semantic_by_source: dict[str, Any],
    relation_index: Any | None,
    graph: Any | None,
    relation_reranked_index: Any | None = None,
    planner_modes: Sequence[str] = PLANNER_MODES,
    planner_report: Path | None = None,
) -> dict[str, Any]:
    unknown_modes = set(planner_modes).difference(ALL_PLANNER_MODES)
    if unknown_modes:
        raise ValueError(f"unknown planner modes: {sorted(unknown_modes)}")
    if PLANNER_MODE_REPORT in planner_modes and planner_report is None:
        raise ValueError("planner mode 'report' requires planner_report")
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
        "lexical_relation": None,
        "lexical_vector_relation": vector_source if vector_available else None,
        "lexical_relation_reranked": None,
        "lexical_vector_relation_reranked": (
            vector_source if vector_available else None
        ),
    }
    profile_to_relation: dict[str, Any | None] = {
        "lexical": None,
        "lexical_vector": None,
        "lexical_graph": None,
        "lexical_vector_graph": None,
        "lexical_relation": relation_index,
        "lexical_vector_relation": relation_index,
        "lexical_relation_reranked": relation_reranked_index,
        "lexical_vector_relation_reranked": relation_reranked_index,
    }
    planners: dict[str, Any] = {
        PLANNER_MODE_DETERMINISTIC: DeterministicPersonalMemoryQueryPlanner(),
        PLANNER_MODE_ORACLE: BenchmarkOraclePlanner(dataset.queries),
    }
    if planner_report is not None:
        planners[PLANNER_MODE_REPORT] = BenchmarkReportPlanner(planner_report, dataset)
    per_mode: dict[str, dict[str, dict[str, Any]]] = {}
    all_cases: list[dict[str, Any]] = []
    deferred_queries: list[str] = []
    for mode in planner_modes:
        planner = planners[mode]
        per_profile: dict[str, dict[str, Any]] = {}
        for profile in PROFILE_EXECUTION:
            if profile not in profiles:
                continue
            semantic = profile_to_semantic[profile]
            relation = profile_to_relation[profile]
            semantic_required = profile in {
                "lexical_vector",
                "lexical_graph",
                "lexical_vector_graph",
                "lexical_vector_relation",
                "lexical_vector_relation_reranked",
            }
            relation_required = profile in PROFILE_RELATION
            reranker_required = profile in PROFILE_RELATION_RERANKED
            if (semantic_required and semantic is None) or (
                relation_required and relation is None
            ):
                missing = []
                if semantic_required and semantic is None:
                    missing.append("semantic")
                if relation_required and relation is None:
                    missing.append(
                        "relation_reranker" if reranker_required else "relation"
                    )
                per_profile[profile] = {
                    "query_count": len(dataset.queries),
                    "error_count": len(dataset.queries),
                    "unavailable": True,
                    "reason": f"{' + '.join(missing)} source unavailable (see runtime)",
                }
                continue
            engine = _engines(store, semantic, relation)
            warmup = next(
                (
                    query
                    for query in dataset.queries
                    if query.partition != "deferred_cross_subject"
                ),
                None,
            )
            if warmup is not None:
                await engine.query(
                    planner,
                    warmup.query,
                    [scopes[name] for name in warmup.scopes],
                    now=warmup.now,
                )
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
        "runner": (
            "doppel.personal-relation-ablation.v1"
            if dataset.requirements.get("relation_benchmark", False)
            else "doppel.personal-retrieval-ablation.v1"
        ),
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
        "planner_sources": {
            mode: planner.source
            for mode, planner in planners.items()
            if mode in planner_modes and hasattr(planner, "source")
        },
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
        relation_full = per_mode[mode].get("lexical_vector_relation")
        for base_name in ("lexical", "lexical_vector", "lexical_relation"):
            base = per_mode[mode].get(base_name)
            if (
                relation_full is not None
                and base is not None
                and not base.get("unavailable", False)
                and not relation_full.get("unavailable", False)
            ):
                comparisons[f"{mode}_relation_full_vs_{base_name}"] = _delta(
                    relation_full, base
                )
        for reranked_name, base_name in (
            ("lexical_relation_reranked", "lexical_relation"),
            ("lexical_vector_relation_reranked", "lexical_vector_relation"),
        ):
            reranked = per_mode[mode].get(reranked_name)
            base = per_mode[mode].get(base_name)
            if (
                reranked is not None
                and base is not None
                and not reranked.get("unavailable", False)
                and not base.get("unavailable", False)
            ):
                comparisons[f"{mode}_{reranked_name}_vs_{base_name}"] = _delta(
                    reranked, base
                )
    report["comparisons"] = comparisons

    report["hard_gates"] = _collect_hard_gates(all_cases)
    report["hard_gates_by_profile"] = {
        mode: {
            profile: _collect_hard_gates(
                [
                    case
                    for case in all_cases
                    if case.get("mode") == mode and case.get("profile") == profile
                ]
            )
            for profile in per_mode.get(mode, {})
        }
        for mode in planner_modes
    }
    report["graph_final_hit_attribution"] = _build_final_hit_attribution(
        report=report,
        dataset=dataset,
        per_mode=per_mode,
    )
    report["relation_final_hit_attribution"] = _build_relation_final_hit_attribution(
        report=report, dataset=dataset
    )
    return report


def _collect_hard_gates(cases: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
    """Layer failures for one explicitly identified set of executed cases."""

    layered: dict[str, list[str]] = {
        "planner_failures": [],
        "retrieval_failures": [],
        "security_failures": [],
        "fixture_validation_failures": [],
    }
    for case in cases:
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
    return {key: sorted(set(items)) for key, items in layered.items()}


def _build_relation_final_hit_attribution(
    *,
    report: dict[str, Any],
    dataset: AblationDataset,
) -> dict[str, Any]:
    """Count accepted relation-ranked hits against query gold, never raw edges."""

    query_by_id = {query.query_id: query for query in dataset.queries}
    oracle_cases = [
        case
        for case in report.get("cases", [])
        if case.get("mode") == PLANNER_MODE_ORACLE
        and case.get("profile") in PROFILE_RELATION
        and not case.get("error")
    ]
    if not oracle_cases:
        return {"available": False, "reason": "relation profiles were not executed"}
    correct_links: set[tuple[str, str, str]] = set()
    incorrect_links: set[tuple[str, str, str]] = set()
    relation_queries: set[tuple[str, str]] = set()
    for case in oracle_cases:
        query = query_by_id[case["query_id"]]
        required = set(query.required_memory_ids)
        forbidden = set(query.forbidden_memory_ids)
        for hit in case.get("hit_scores", []):
            reasons = list(hit.get("reasons", []))
            if not any(reason == "relation_match" for reason in reasons):
                continue
            memory_id = str(hit.get("memory_id") or "")
            edge_ids = [
                reason.removeprefix("relation_edge:")
                for reason in reasons
                if reason.startswith("relation_edge:")
            ] or [""]
            relation_queries.add((case["profile"], case["query_id"]))
            for edge_id in edge_ids:
                link = (case["query_id"], memory_id, edge_id)
                if memory_id in required:
                    correct_links.add(link)
                if memory_id in forbidden or query.expected_abstain:
                    incorrect_links.add(link)
    return {
        "available": True,
        "method": (
            "oracle final accepted hits carrying relation_match, checked against "
            "required/forbidden labels after Store revalidation"
        ),
        "correct_relation_final_hit_links": len(correct_links),
        "incorrect_relation_final_hit_links": len(incorrect_links),
        "unique_profile_queries_with_relation_hit": len(relation_queries),
        "correct_links": [list(item) for item in sorted(correct_links)],
        "incorrect_links": [list(item) for item in sorted(incorrect_links)],
    }


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
            "graph": None,
            "vector": None,
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
    graph_result = {
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
    # ---- vector final-hit attribution ------------------------------------ #
    vector_direct = report.get("diagnostics", {}).get("vector_direct")
    vector_candidates_by_query = (
        vector_direct.get("candidate_memory_ids_by_query", {}) if vector_direct else {}
    )
    vector_result = None
    if vector_candidates_by_query:
        oracle_vector_cases = [
            case
            for case in report.get("cases", [])
            if case.get("mode") == PLANNER_MODE_ORACLE
            and case.get("profile") == "lexical_vector"
            and not case.get("error")
        ]
        vector_by_query = {case["query_id"]: case for case in oracle_vector_cases}
        vector_contribution = 0
        vector_queries: set[str] = set()
        vector_mapped_queries = 0
        for query in dataset.queries:
            case = vector_by_query.get(query.query_id)
            if case is None:
                continue
            final_hits = set(case.get("hits", []))
            candidates = vector_candidates_by_query.get(query.query_id, [])
            if not candidates:
                continue
            vector_mapped_queries += 1
            for memory_id in candidates:
                if memory_id in final_hits:
                    vector_contribution += 1
                    vector_queries.add(query.query_id)
        vector_result = {
            "available": True,
            "method": (
                "oracle lexical_vector final accepted hits intersected with "
                "vector_direct candidate memory IDs per query"
            ),
            "vector_final_hit_links": vector_contribution,
            "unique_queries_with_vector": len(vector_queries),
            "queries_with_mapping": vector_mapped_queries,
        }
    return {
        "available": True,
        "graph": graph_result,
        "vector": vector_result,
    }


def _engines(
    store: Any,
    semantic: Any | None,
    relation: Any | None = None,
) -> PersonalMemoryQueryEngine:
    return PersonalMemoryQueryEngine(
        store,
        semantic_index=semantic,
        relation_index=relation,
    )


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
                "positive": bool(case["hits"]) and not case["missing"],
                "negative": not case["hits"],
                "top_score": top["score"] if top else 0.0,
                "top_lexical": top["lexical_score"] if top else 0.0,
                "top_semantic": top["semantic_score"] if top else 0.0,
                "top_relation": top.get("relation_score", 0.0) if top else 0.0,
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
            + ",".join(PROFILE_EXECUTION)
            + "; diagnostics: "
            + ",".join(PROFILE_DIRECT)
        ),
    )
    parser.add_argument("--output", type=Path, default=None, help="report JSON path")
    parser.add_argument(
        "--planner-modes",
        default=",".join(PLANNER_MODES),
        help="comma-separated planner modes: oracle,deterministic,report",
    )
    parser.add_argument(
        "--planner-report",
        type=Path,
        help=(
            "relation-planner quality report to replay when --planner-modes "
            "contains report; performs zero provider calls"
        ),
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
    parser.add_argument(
        "--gate-profiles",
        default="",
        help=(
            "comma-separated execution profiles whose quality gates determine "
            "the exit code; empty keeps the legacy all-profile aggregate gate"
        ),
    )
    parser.add_argument("--max-scope-leakage", type=int, default=0)
    parser.add_argument("--max-temporal-violations", type=int, default=0)
    parser.add_argument(
        "--relation-reranker-model",
        default="",
        help=(
            "local FastEmbed cross-encoder model used only by *_relation_reranked "
            "profiles; no model is downloaded unless such a profile is requested"
        ),
    )
    parser.add_argument(
        "--relation-reranker-threshold",
        type=float,
        default=None,
        help="explicit normalized 0..1 relation promotion threshold",
    )
    parser.add_argument(
        "--relation-reranker-cache-dir",
        type=Path,
        default=None,
        help="optional local FastEmbed model cache directory",
    )
    parser.add_argument(
        "--relation-reranker-batch-size",
        type=int,
        default=32,
    )
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
    gate_profiles = [
        item.strip() for item in (args.gate_profiles or "").split(",") if item.strip()
    ]
    if gate_profiles:
        invalid = sorted(set(gate_profiles).difference(PROFILE_EXECUTION))
        if invalid:
            failures.append(f"unknown --gate-profiles: {invalid}")
        gates_by_profile = report.get("hard_gates_by_profile", {})
        for mode in modes:
            for profile in gate_profiles:
                profile_gates = (gates_by_profile.get(mode) or {}).get(profile)
                if profile_gates is None:
                    failures.append(f"gate profile {profile} ({mode}) did not execute")
                    continue
                for group, items in profile_gates.items():
                    if items:
                        failures.append(f"{mode}:{profile}:{group}: {items[:5]}")
    else:
        hard_gates = report.get("hard_gates", {})
        for group, items in hard_gates.items():
            if items:
                failures.append(f"{group}: {items[:5]}")
    for mode in modes:
        checked_profiles = gate_profiles or ["lexical_vector_graph"]
        for profile in checked_profiles:
            metrics = (report.get("profiles", {}).get(mode) or {}).get(profile)
            if not metrics:
                continue
            if metrics.get("scope_leakage_count", 0) > args.max_scope_leakage:
                failures.append(
                    f"{mode}:{profile}: scope leakage exceeds --max-scope-leakage"
                )
            if (
                metrics.get("temporal_violation_count", 0)
                > args.max_temporal_violations
            ):
                failures.append(
                    f"{mode}:{profile}: temporal violations exceed "
                    "--max-temporal-violations"
                )
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
    modes = tuple(
        name.strip() for name in args.planner_modes.split(",") if name.strip()
    )
    relation_reranker: _FastEmbedRelationReranker | None = None
    relation_reranker_reason = ""
    if set(profiles) & set(PROFILE_RELATION_RERANKED):
        if not str(args.relation_reranker_model or "").strip():
            relation_reranker_reason = "relation reranker model is not configured"
        elif args.relation_reranker_threshold is None:
            relation_reranker_reason = "relation reranker threshold is not configured"
        else:
            relation_reranker = _FastEmbedRelationReranker(
                args.relation_reranker_model,
                cache_dir=args.relation_reranker_cache_dir,
                batch_size=args.relation_reranker_batch_size,
            )
            try:
                await relation_reranker.warmup()
            except Exception as exc:  # noqa: BLE001 - structured unavailability
                relation_reranker_reason = f"{type(exc).__name__}: {exc}"
                relation_reranker = None
    report = await run_ablation(
        dataset,
        profiles=profiles,
        planner_modes=modes,
        planner_report=args.planner_report,
        require_live_postgres=args.require_live_postgres,
        require_live_neo4j=args.require_live_neo4j,
        run_metamorphic=not args.no_metamorphic,
        relation_reranker=relation_reranker,
        minimum_reranker_score=args.relation_reranker_threshold,
        relation_reranker_reason=relation_reranker_reason,
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
        "gate_profiles": [
            item.strip()
            for item in (args.gate_profiles or "").split(",")
            if item.strip()
        ],
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
                "hard_gates_by_profile": report.get("hard_gates_by_profile", {}),
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

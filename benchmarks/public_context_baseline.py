"""Real raw-history retrieval baseline, not full Doppel/AML or answer quality.

Uses only preregistered diagnostic histories, production PostgreSQL/pgvector and
local embeddings, with opt-in BM25 and strict local CrossEncoder comparisons.
No extraction, graph, Planner or reader is substituted with an oracle/fake.
Those stages are explicitly not run here; reranking runs only when configured.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from benchmarks.personal_retrieval_ablation import (
    _git_commit_hash,
    _git_tracked_dirty_paths,
    _LocalEmbeddingProvider,
)
from benchmarks.public_context_rerank import (
    LocalContextCrossEncoder,
    StrictContextReranker,
)
from benchmarks.public_longmemeval import RuntimeCase, ScoringCase, prepare_case
from benchmarks.public_memory_pilot import _hash, build_manifest
from doppel_memory.lexical import BM25RetrievalStrategy
from doppel_memory.models import (
    Actor,
    ChatMessage,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    WriteStatus,
)
from doppel_memory.postgres_store import PostgreSQLStore
from doppel_memory.retriever import StoreRetrievalStrategy
from doppel_memory.store import MemoryStore
from doppel_memory.vector import (
    HybridRetrievalStrategy,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
)
from integrations.aml.context import AttributedContextRetriever, ContextSnippet
from integrations.aml.contract import event_ids, memory_scope


def execution_metadata() -> dict[str, Any]:
    """Bind actual source bytes, including uncommitted harness code; no credentials."""
    root = Path(__file__).resolve().parents[1]
    files = {
        Path(__file__).resolve(),
        root / "benchmarks/public_longmemeval.py",
        root / "benchmarks/public_memory_pilot.py",
        root / "benchmarks/personal_retrieval_ablation.py",
        root / "benchmarks/public_context_rerank.py",
        root / "integrations/aml/context.py",
        root / "integrations/aml/contract.py",
        *root.joinpath("doppel_memory").rglob("*.py"),
    }
    source_hash = hashlib.sha256()
    for file in sorted(files):
        source_hash.update(file.relative_to(root).as_posix().encode())
        source_hash.update(b"\0" + file.read_bytes() + b"\0")
    return {
        "git_commit": _git_commit_hash(),
        "tracked_dirty_paths": _git_tracked_dirty_paths(),
        "runtime_source_sha256": source_hash.hexdigest(),
        "runtime_source_file_count": len(files),
    }


def select_diagnostic_cases(
    records: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    *,
    source_sha256: str,
) -> list[tuple[RuntimeCase, ScoringCase]]:
    payload = dict(manifest)
    fingerprint = payload.pop("manifest_fingerprint", None)
    if fingerprint != _hash(payload) or source_sha256 != manifest["source_sha256"]:
        raise ValueError("pilot source/manifest integrity check failed")
    rebuilt = build_manifest(
        records,
        dataset_namespace=manifest["dataset_namespace"],
        run_namespace=manifest["run_namespace"],
        source_sha256=source_sha256,
        seed=manifest["seed"],
        diagnostic_count=manifest["diagnostic_count"],
        reserved_count=manifest["reserved_count"],
        max_messages=manifest["max_messages"],
        excluded_history_groups=manifest.get("excluded_history_groups", ()),
        stratify_by_question_type=manifest.get("stratify_by_question_type", False),
    )
    if rebuilt != dict(manifest):
        raise ValueError("pilot selection differs from preregistered plan")
    selected = []
    by_id = {item["question_id"]: item for item in records}
    for row in manifest["cases"]:
        if row["partition"] != "diagnostic":
            continue
        prepared = prepare_case(
            by_id[row["case_id"]], dataset_namespace=manifest["dataset_namespace"]
        )
        selected.append((prepared.runtime, prepared.scoring))
    return selected


class RawHistoryHost:
    """Raw-only diagnostic ingestion with trusted source bookkeeping, no labels.

    Extracted-memory composition uses DurableTextualIngestor separately. This
    baseline intentionally avoids claiming its own raw completion is AML Add.
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.sources: dict[tuple[str, str], str] = {}
        self.positions: dict[tuple[str, str], tuple[int, int]] = {}

    async def ingest(
        self, case: RuntimeCase, scope: MemoryScope, *, max_messages: int
    ) -> list[MemoryRecord]:
        records = []
        for chunk in case.ingestion_chunks(max_messages=max_messages):
            identities = event_ids(scope, chunk.request)
            for transport_index, (message, evidence_id, source_turn) in enumerate(
                zip(
                    chunk.request.messages,
                    identities,
                    chunk.source_turn_indices,
                    strict=True,
                )
            ):
                if message.timestamp is None:
                    raise ValueError("raw baseline source needs timestamp")
                actor = Actor.OWNER if message.role == "user" else Actor.AGENT
                chat = ChatMessage(
                    event_id=evidence_id,
                    actor=actor,
                    text=message.content,
                    sender_id=scope.user_id if actor == Actor.OWNER else scope.agent_id,
                    at=datetime(1970, 1, 1, tzinfo=UTC)
                    + timedelta(milliseconds=message.timestamp),
                    raw={
                        "source_text": message.content,
                        "transport_role": message.role,
                        "session_id": chunk.request.session_id,
                        "turn_index": transport_index,
                    },
                )
                result = await self.store.write_event(scope, chat)
                if result.status not in {
                    WriteStatus.CREATED,
                    WriteStatus.UPDATED,
                    WriteStatus.DUPLICATE,
                }:
                    raise RuntimeError("raw baseline Store write failed")
                record = await self.store.get(scope, result.memory_id)
                if record is None or (
                    record.scope.scope_key != scope.scope_key
                    or record.content != chat.text
                    or record.source_event_id != evidence_id
                    or record.actor != actor
                    or record.authority != chat.fact_authority
                    or record.created_at != chat.at
                    or record.metadata.get("raw") != chat.raw
                    or record.state != MemoryState.CONFIRMED
                    or record.kind != MemoryKind.EVENT
                    or record.extractor != "ingestor"
                ):
                    raise RuntimeError("raw baseline Store revalidation failed")
                key = (scope.scope_key, evidence_id)
                self.sources[key] = record.memory_id
                self.positions[key] = (chunk.source_session_index, source_turn)
                records.append(record)
        return records

    async def resolve_event(
        self, scope: MemoryScope, evidence_id: str
    ) -> MemoryRecord | None:
        memory_id = self.sources.get((scope.scope_key, evidence_id))
        return await self.store.get(scope, memory_id) if memory_id else None

    def retrieved_positions(
        self, snippets: Sequence[ContextSnippet]
    ) -> list[tuple[int, int]]:
        return [self.positions[(s.scope_key, s.evidence_id)] for s in snippets]


def score_evidence(
    scoring: ScoringCase, retrieved: Sequence[tuple[int, int]]
) -> dict[str, Any]:
    """Scoring-only annotations; not every alternative valid evidence is labeled.

    Sessions use occurrence ordinals, not potentially repeated source ID strings.
    No gold-turn denominator means undefined recall, not automatic success.
    """
    required = set(scoring.evidence_turns)
    sessions = {session for session, _ in required}
    positions = set(retrieved)
    hit_turns = required & positions
    hit_sessions = sessions & {session for session, _ in positions}
    return {
        "annotated_turn_count": len(required),
        "annotated_turn_hits": len(hit_turns),
        "annotated_turn_recall": len(hit_turns) / len(required) if required else None,
        "annotated_session_count": len(sessions),
        "annotated_session_hits": len(hit_sessions),
        "annotated_session_recall": len(hit_sessions) / len(sessions)
        if sessions
        else None,
        "all_annotated_sessions_covered": sessions <= {s for s, _ in positions}
        if sessions
        else None,
        "abstention_label": scoring.abstention,
    }


async def run_baseline(
    cases: Sequence[tuple[RuntimeCase, ScoringCase]],
    manifest: Mapping[str, Any],
    *,
    dsn: str,
    schema: str,
    embedding_cache_dir: Path | None,
    with_bm25: bool = False,
    reranker: StrictContextReranker | None = None,
) -> dict[str, Any]:
    if not cases:
        raise ValueError(
            "raw baseline requires nonempty preregistered diagnostic cases"
        )
    store = PostgreSQLStore(dsn, schema=schema, create_schema=True)
    provider = _LocalEmbeddingProvider(cache_dir=embedding_cache_dir)
    index = PostgreSQLVectorIndex(
        store, provider, VectorIndexConfig(create_extension=True)
    )
    host = RawHistoryHost(store)
    source_metadata = execution_metadata()
    rows = []
    total_records = 0
    try:
        for runtime, scoring in cases:
            scope = memory_scope(manifest["run_namespace"], runtime.user_id)
            records = await host.ingest(
                runtime, scope, max_messages=manifest["max_messages"]
            )
            total_records += len(records)
            indexing = await index.index_records(records)
            if not indexing.ok or indexing.indexed + indexing.skipped != len(records):
                raise RuntimeError("raw baseline vector indexing incomplete")
            strategies = {
                "raw_lexical": StoreRetrievalStrategy(),
                "raw_local_vector": index,
                "raw_lexical_vector": HybridRetrievalStrategy(
                    index, fallback_to_lexical=False
                ),
            }
            if with_bm25:
                strategies["raw_bm25"] = BM25RetrievalStrategy()
                strategies["raw_bm25_vector"] = HybridRetrievalStrategy(
                    index,
                    lexical_strategy=BM25RetrievalStrategy(),
                    candidate_multiplier=1,
                    fallback_to_lexical=False,
                )
            profiles: list[tuple[str, Any, StrictContextReranker | None]] = [
                (name, strategy, None) for name, strategy in strategies.items()
            ]
            if reranker is not None:
                profiles.extend(
                    (name + "_reranked", strategy, reranker)
                    for name, strategy in strategies.items()
                    if name in {"raw_local_vector", "raw_bm25", "raw_bm25_vector"}
                )
            for profile, strategy, ordering in profiles:
                # SemanticIndex lacks the Store parameter: adapt without changing ranking.
                if profile in {"raw_local_vector", "raw_local_vector_reranked"}:
                    strategy = _VectorStrategy(index)
                retriever = AttributedContextRetriever(
                    store,
                    strategy=strategy,
                    resolve_event=host.resolve_event,
                    reranker=ordering,
                )
                start = perf_counter()
                result = await retriever.search(scope, runtime.query.query, limit=20)
                positions = host.retrieved_positions(result.snippets)
                candidate_positions = [
                    host.positions[(scope.scope_key, evidence_id)]
                    for evidence_id in result.candidate_evidence_ids
                ]
                rows.append(
                    {
                        "case_id": scoring.case_id,
                        "profile": profile,
                        "raw_records": len(records),
                        "hits": len(result.snippets),
                        "candidates_seen": result.candidates_seen,
                        "revalidated": result.revalidated,
                        "rejected": result.rejected,
                        "final_store_checks": result.final_store_checks,
                        "candidate_window_positions": candidate_positions,
                        "candidate_window_score": score_evidence(
                            scoring, candidate_positions
                        ),
                        "rerank_summary": ordering.last_summary.model_dump(mode="json")
                        if ordering and ordering.last_summary
                        else None,
                        "returned_roles": [s.role for s in result.snippets],
                        "retrieved_source_positions": positions,
                        "search_ms": (perf_counter() - start) * 1000,
                        "at_5": score_evidence(scoring, positions[:5]),
                        "at_20": score_evidence(scoring, positions),
                    }
                )
                print(
                    f"{scoring.case_id} {profile}: retrieved {len(result.snippets)}",
                    flush=True,
                )
        return {
            "runner": "doppel.public-raw-context-comparison.v1"
            if with_bm25 or reranker
            else "doppel.public-raw-context-baseline.v1",
            "execution_metadata": source_metadata,
            "manifest_fingerprint": manifest["manifest_fingerprint"],
            "source_sha256": manifest["source_sha256"],
            "postgres_schema": schema,
            "scope_count": len(cases),
            "raw_records": total_records,
            "profiles": [name for name, _, _ in profiles],
            "bm25": {
                "name": BM25RetrievalStrategy.name,
                "version": BM25RetrievalStrategy.version,
                "config": BM25RetrievalStrategy().config.model_dump(mode="json"),
            }
            if with_bm25
            else None,
            "reranker": reranker.provider.report() if reranker else None,
            "candidate_budget": {
                "final_window": 80,
                "output_limit": 20,
                "bm25_vector_per_source": 80,
                "legacy_lexical_vector_per_source": 320,
            },
            "rows": rows,
            "embedding": {
                "name": provider.name,
                "version": provider.version,
                "dimensions": provider.dimensions,
            },
            "llm_calls": 0,
            "provider_tokens": 0,
            "graph_used": False,
            "extraction_used": False,
            "planner_used": False,
            "reranker_used": reranker is not None,
            "reader_used": False,
            "qa_metrics_available": False,
            "retrieval_metrics_available": True,
            "publication_ready": False,
            "aml_academic_model_compliant": False,
            "profile_scope": "raw-dialogue-baseline-only-not-full-Doppel",
            "time_policy": manifest["temporal_policy"],
            "latency_is_highest_configuration_benchmark": False,
            "reserved_histories_executed": False,
        }
    finally:
        await store.close()


class _VectorStrategy:
    def __init__(self, index: PostgreSQLVectorIndex) -> None:
        self.index = index

    async def search(self, store, query, scopes, *, filters=None, limit=10):
        return await self.index.search(query, scopes, filters=filters, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dsn-env", default="DOPPEL_PUBLIC_PILOT_PG_DSN")
    parser.add_argument("--embedding-cache-dir", type=Path)
    parser.add_argument("--with-bm25", action="store_true")
    parser.add_argument("--reranker-model", type=Path)
    parser.add_argument("--reranker-device", default="cuda")
    parser.add_argument("--reranker-max-length", type=int, default=8192)
    parser.add_argument("--reranker-batch-size", type=int, default=1)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() in {
        args.dataset.resolve(),
        args.manifest.resolve(),
    }:
        raise FileExistsError(
            "choose a new report path, never overwrite source/manifest/results"
        )
    dsn = os.environ.get(args.dsn_env, "")
    if not dsn:
        raise ValueError(
            "configure local diagnostic PostgreSQL DSN in the named environment variable"
        )
    data = args.dataset.read_bytes()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    cases = select_diagnostic_cases(
        json.loads(data), manifest, source_sha256=hashlib.sha256(data).hexdigest()
    )
    # New dedicated namespace; do not reset/drop any existing database or schema.
    schema = "public_raw_" + manifest["manifest_fingerprint"][:12]
    report = asyncio.run(
        run_baseline(
            cases,
            manifest,
            dsn=dsn,
            schema=schema,
            embedding_cache_dir=args.embedding_cache_dir,
            with_bm25=args.with_bm25,
            reranker=StrictContextReranker(
                LocalContextCrossEncoder(
                    args.reranker_model,
                    device=args.reranker_device,
                    max_length=args.reranker_max_length,
                    batch_size=args.reranker_batch_size,
                )
            )
            if args.reranker_model
            else None,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"output: {args.output.resolve()}")


if __name__ == "__main__":
    main()

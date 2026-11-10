"""Opt-in PG/pgvector workflow with offline embeddings and explicit analyzer mode.

FixtureAnalyzer by default; reference mode requires --live-llm. Retains all state.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from doppel_memory import (
    ChatMessage,
    DeterministicMemoryConsolidator,
    DoppelClient,
    HistoryWindow,
    MemoryFilter,
    MemoryScope,
    OpenAICompatibleStructuredOutputConfig,
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    PostgreSQLStore,
    PostgreSQLVectorIndex,
    VectorIndexConfig,
    memory_index_fingerprint,
)
from examples.incremental_personal_memory import FixtureAnalyzer
from examples.personal_memory_runtime import PersonalMemoryWorkflow
from examples.workflow_analyzer import WorkflowAnalyzerSession
from integrations.aml.local_models import model_fingerprint


def storage_identity(dsn: str, schema: str) -> str:
    endpoint = urlsplit(dsn)
    if (
        endpoint.scheme not in {"postgres", "postgresql"}
        or not endpoint.hostname
        or not endpoint.path.strip("/")
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("a PostgreSQL URL with explicit database is required")
    payload = [endpoint.hostname, endpoint.port or 5432, endpoint.path, schema]
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


class OfflineSentenceEmbedding:
    """Explicit independent local profile; no downloads or silent truncation."""

    name = "sentence-transformers:local-workflow"

    def __init__(self, path: Path):
        artifacts = model_fingerprint(path)
        module = importlib.import_module("sentence_transformers")
        self.model = module.SentenceTransformer(
            str(path.resolve()),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
        )
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.version = f"1:{version('sentence-transformers')}:{artifacts}:normalized:max={self.model.max_seq_length}"
        self.calls = 0

    async def embed(self, texts):
        if not texts:
            return []

        def encode():
            lengths = self.model.tokenizer(
                list(texts), truncation=False, padding=False, return_length=True
            )["length"]
            if any(size > self.model.max_seq_length for size in lengths):
                raise ValueError("explicit host chunking required for oversized input")
            self.calls += 1
            return self.model.encode(
                list(texts), normalize_embeddings=True, show_progress_bar=False
            ).tolist()

        return await asyncio.to_thread(encode)


async def run(args, analyzer=None) -> dict:
    dsn = os.environ.get("DOPPEL_WORKFLOW_PG_DSN", "")
    identity = storage_identity(dsn, args.schema)
    if not args.schema.startswith("doppel_workflow_"):
        raise ValueError("dedicated doppel_workflow_ schema required")
    store = PostgreSQLStore(dsn, schema=args.schema, create_schema=True)
    memory = DoppelClient(store)
    try:
        provider = await asyncio.to_thread(
            OfflineSentenceEmbedding, args.embedding_model_path
        )
        index = PostgreSQLVectorIndex(
            store, provider, VectorIndexConfig(create_extension=True)
        )
        scope = MemoryScope(user_id="workflow-smoke-owner", agent_id="personal-agent")
        job = PersonalMemoryWorkflow(
            args.directory,
            workflow_key="real-pg-v1",
            storage_identity=identity,
            store=store,
            scope=scope,
            miner=PersonalMemoryMiner(
                analyzer or FixtureAnalyzer(),
                PersonalMemoryMinerConfig(owner_target_scope="conversation"),
            ),
            consolidator=DeterministicMemoryConsolidator(),
            index=index,
            index_page_size=2,
        )
        driver = importlib.import_module("asyncpg")
        connection = await driver.connect(dsn)
        try:
            exists = bool(
                await connection.fetchval(
                    "SELECT 1 FROM pg_namespace WHERE nspname=$1", args.schema
                )
            )
            if exists != job.path.exists():
                raise ValueError(
                    "schema/journal presence mismatch; use a new dedicated pair or inspect recovery"
                )
        finally:
            await connection.close()
        await index.initialize()
        for message_id, text, at in [
            ("theme-1", "我喜欢浅色主题。", "2026-11-01T09:00:00Z"),
            ("theme-2", "更正一下，我现在喜欢深色主题。", "2026-11-02T09:00:00Z"),
        ]:
            result = await memory.ingest(
                scope, ChatMessage.of("owner", text, at, message_id=message_id)
            )
            if result.record is None:
                raise RuntimeError("source write failed")
        window = HistoryWindow(
            start=datetime(2026, 11, 1, tzinfo=UTC),
            end=datetime(2026, 11, 3, tzinfo=UTC),
        )
        progress = []
        for _ in range(args.steps):
            item = await job.step(window)
            progress.append(item)
            if not item["ok"] or item["complete"]:
                break
        complete = progress[-1]["complete"]
        hits = await memory.query_personal_memory(
            "主题", [scope], now=window.end, semantic_index=index
        )
        foreign = await memory.query_personal_memory(
            "主题",
            [MemoryScope(user_id="different-owner", agent_id="personal-agent")],
            now=window.end,
            semantic_index=index,
        )
        if foreign.hits:
            raise RuntimeError("scope isolation failed")
        records = (
            await store.scan(
                scope, filters=MemoryFilter(include_inactive=True), limit=100
            )
        ).records
        checked = 0
        if complete:
            if args.analyzer == "fixture" and (
                len(hits.hits) != 1
                or hits.hits[0].record.content != "更正一下，我现在喜欢深色主题。"
            ):
                raise RuntimeError("fixture correction query failed")
            for record in records:
                entry = await index.inspect(scope, record.memory_id)
                if record.state.value in {"confirmed", "candidate"}:
                    if entry is None or entry.fingerprint != memory_index_fingerprint(
                        record
                    ):
                        raise RuntimeError("active manifest mismatch")
                elif entry is not None:
                    raise RuntimeError("inactive index entry retained")
                checked += 1
        return {
            "runner": "doppel.personal-workflow-pg.v1",
            "passed": all(item["ok"] for item in progress),
            "complete": complete,
            "progress": progress,
            "schema": args.schema,
            "index": index.identity,
            "embedding_dimensions": provider.dimensions,
            "embedding_calls": provider.calls,
            "source_and_memory_records": len(records),
            "manifest_checks": checked,
            "foreign_hits": len(foreign.hits),
            "hit_ids": [hit.record.memory_id for hit in hits.hits],
            "analyzer": args.analyzer,
            "paid_calls": 0 if args.analyzer == "fixture" else None,
            "personal_memories_returned": len(hits.hits),
            "extracted_claims": [
                {
                    "content": hit.record.content,
                    "state": hit.record.state.value,
                    "authority": hit.record.authority.value,
                    "evidence_ids": [
                        ref.get("evidence_id")
                        for ref in hit.record.metadata.get("evidence", [])
                    ],
                }
                for hit in hits.hits
            ],
            "quality_score_available": False,
            "fixtures_retained": True,
        }
    finally:
        await memory.close()


async def dispatch(args) -> dict:
    session = None
    try:
        if args.analyzer == "fixture":
            return await run(args)
        # Explicit flags/credentials are required before opening a client or DB.
        if not args.live_llm:
            raise ValueError("reference mode requires --live-llm")
        required = ["DOPPEL_MODEL", "DOPPEL_OPENAI_BASE_URL", "DOPPEL_API_KEY"]
        if any(not os.environ.get(key, "").strip() for key in required):
            raise ValueError("explicit model/base URL/key configuration required")
        config = OpenAICompatibleStructuredOutputConfig(
            model=os.environ["DOPPEL_MODEL"],
            base_url=os.environ["DOPPEL_OPENAI_BASE_URL"],
            schema_mode="json_object",
            max_completion_tokens=2048,
            max_tokens_parameter="max_tokens",
            temperature=0,
            thinking="disabled",
        )
        session = WorkflowAnalyzerSession(
            args.directory / "llm-ledger.jsonl",
            binding=storage_identity(
                os.environ.get("DOPPEL_WORKFLOW_PG_DSN", ""), args.schema
            ),
            config=config,
            api_key=os.environ["DOPPEL_API_KEY"],
            max_calls=args.max_llm_calls,
        )
        async with session:
            report = await run(args, session.analyzer)
        report["llm_usage"] = session.report()
        return report
    except Exception as exc:  # noqa: BLE001 - redact errors but preserve reserved/unknown usage
        return {
            "passed": False,
            "error_type": type(exc).__name__,
            "analyzer": args.analyzer,
            "paid_calls": None if session else 0,
            "llm_usage": session.report() if session else None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-pg", action="store_true")
    parser.add_argument("--schema", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--embedding-model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument(
        "--analyzer", choices=["fixture", "reference"], default="fixture"
    )
    parser.add_argument("--live-llm", action="store_true")
    parser.add_argument("--max-llm-calls", type=int, default=2)
    args = parser.parse_args()
    if not args.live_pg or not 1 <= args.steps <= 1000 or args.output.exists():
        parser.error("--live-pg, bounded steps and a new output path are required")
    if (
        args.live_llm != (args.analyzer == "reference")
        or not 1 <= args.max_llm_calls <= 20
    ):
        parser.error(
            "reference requires --live-llm; fixture forbids it; call cap must be 1..20"
        )
    try:
        report = asyncio.run(dispatch(args))
    except Exception as exc:  # noqa: BLE001 - receipt must not expose DSN/provider exception text
        report = {"passed": False, "error_type": type(exc).__name__, "paid_calls": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

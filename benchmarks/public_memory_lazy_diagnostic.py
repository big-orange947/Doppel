"""Bounded query-time proposal diagnosis on two opened, frozen raw contexts.

No new retrieval, graph, gold-selected oracle context, or production writes.
Uses the real reference analyzer and miner gates, not a second extraction prompt.
Temporary proposals supplement, never replace, the same original Reader evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from benchmarks.aml_evidence_representation import ObservedProvider
from benchmarks.public_context_baseline import execution_metadata
from benchmarks.public_longmemeval import prepare_case
from benchmarks.public_memory_expansion import config, save
from benchmarks.public_memory_high_config_first import persisted_generation
from benchmarks.public_memory_ingestion import _bind_json
from benchmarks.public_memory_oracle_diagnostic import balance, prepare_rows
from benchmarks.public_memory_pilot import _hash
from benchmarks.public_memory_reader_v2 import (
    ReaderV2Output,
    build_request,
    structural_check,
)
from benchmarks.public_memory_response_policy import ADVICE_INSTRUCTIONS, paired_rows
from benchmarks.public_memory_runtime import DurableCallLedger, PilotStructuredModel
from doppel_memory.batch import (
    BatchCheckpoint,
    BatchTaskContext,
    HistoryPage,
    HistoryWindow,
)
from doppel_memory.intelligence import (
    PersonalMemoryMiner,
    PersonalMemoryMinerConfig,
    ReferencePersonalMemoryAnalyzer,
)
from doppel_memory.models import ChatMessage, MemoryState
from integrations.aml.contract import memory_scope

RUNNER = "doppel.public-memory-query-time-proposal-diagnostic.v1"
CATEGORIES = ("temporal-reasoning", "knowledge-update")
ARMS = ("recall_only", "lazy_proposals")
MAX_BYTES = 100_000
INSTRUCTIONS = (
    ADVICE_INSTRUCTIONS
    + """

query_time_proposals are optional, unverified analyzer interpretations of the
same supplied context items, not additional sources or confirmed facts. Check
their evidence_ids against the original items, including actor and observation
versus effective time. Resolve the question from the original evidence if a
proposal is incorrect or incomplete. Cite original context memory_ids only.
An empty proposal list is not proof that the original items contain no answer.
This is supplied-history evaluation, not causal replay: observed_until states
the available observation horizon, which can follow question_reference_time.
Keep observation dates distinct from effective event dates and the question clock.
"""
)


def miner_config(count):
    return PersonalMemoryMinerConfig(
        owner_target_scope="conversation",
        minimum_confidence=0.75,
        max_memories=100,
        allowed_source_actors={"owner", "agent"},
        require_subject_matches_source_actor=True,
        proposed_state=MemoryState.CANDIDATE,
        page_size=200,
        max_messages=count,
        evidence_error_policy="quarantine",
    )


def messages(row):
    """Bind the saved raw channel to this exact runtime, not role-only identity."""
    originals = {
        (t.content, t.role, t.at.isoformat())
        for s in row.runtime.sessions
        for t in s.turns
    }
    ids = [item["memory_id"] for item in row.context]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("unique nonempty retrieved source set required")
    result = []
    for item in row.context:
        role = item["role"]
        actor = item["actor"]
        expected = {
            "user": ("owner", "human_self"),
            "assistant": ("agent", "agent_output"),
        }
        if (
            item["channel"] != "raw"
            or (item["text"], role, item["observed_at"]) not in originals
            or expected.get(role) != (actor, item["authority"])
            or not item.get("source_events")
        ):
            raise ValueError("retrieved source/actor/time binding mismatch")
        at = datetime.fromisoformat(item["observed_at"])
        result.append(
            ChatMessage(
                actor=actor,
                text=item["text"],
                at=at,
                message_id=item["memory_id"],
                sender_id=row.runtime.user_id
                if actor == "owner"
                else "historical-agent",
            )
        )
    return tuple(sorted(result, key=lambda m: (m.at, m.identity_key)))


class EvidenceWindow:
    def __init__(self, scope, source):
        self.scope, self.source = scope, source

    async def read(
        self, *, cursor="", limit=500, actors=None, time_from=None, time_to=None
    ):
        eligible = [
            m
            for m in self.source
            if (actors is None or m.actor in actors)
            and (time_from is None or m.at >= time_from)
            and (time_to is None or m.at <= time_to)
        ]
        start = int(cursor or "0")
        if (
            str(start) != (cursor or "0")
            or not 0 <= start <= len(eligible)
            or limit < 1
        ):
            raise ValueError("invalid bounded cursor")
        end = min(len(eligible), start + limit)
        return HistoryPage(
            messages=eligible[start:end],
            next_cursor=str(end),
            has_more=end < len(eligible),
        )


class NoMemoryAccess:
    scopes = ()

    async def recall(self, *args, **kwargs):
        raise ValueError("query-time diagnosis may not read other memories")

    async def get(self, *args, **kwargs):
        raise ValueError("query-time diagnosis may not read other memories")


def task_context(row):
    source = messages(row)
    scope = memory_scope(RUNNER, row.case_id)
    return BatchTaskContext(
        run_id=RUNNER + ":" + row.case_id,
        scope=scope,
        window=HistoryWindow(start=source[0].at, end=source[-1].at),
        checkpoint=BatchCheckpoint(),
        history=EvidenceWindow(scope, source),
        memories=NoMemoryAccess(),
    )


class ProbeModel:
    name, version = "diagnostic-request-probe", "1"

    async def generate(self, request):
        self.request = request
        return {"memories": []}


async def analyzer_request(row):
    probe = ProbeModel()
    context = task_context(row)
    await PersonalMemoryMiner(
        ReferencePersonalMemoryAnalyzer(probe), miner_config(len(messages(row)))
    ).propose(context)
    return probe.request


def project_proposals(row, proposals):
    context = task_context(row)
    sources = {m.identity_key: m for m in messages(row)}
    projected = []
    for proposal in proposals:
        meta = proposal.metadata
        evidence = meta["evidence"]
        if proposal.scope != context.scope or not evidence:
            raise ValueError("proposal scope or provenance invalid")
        for e in evidence:
            m = sources.get(e["evidence_id"])
            if (
                m is None
                or m.actor != proposal.actor
                or e["actor"] != m.actor
                or e["at"] != m.at.isoformat()
            ):
                raise ValueError("proposal provenance not bound to retrieved sources")
        projected.append(
            {
                "content": proposal.content,
                "actor": proposal.actor,
                "authority": proposal.authority,
                "confidence": proposal.confidence,
                "state": proposal.proposed_state.value,
                **{
                    k: meta[k]
                    for k in (
                        "subject",
                        "subject_id",
                        "personal_memory_type",
                        "topic_key",
                        "event_key",
                        "revision_kind",
                        "temporal_status",
                        "valid_from",
                        "valid_to",
                    )
                },
                "evidence_ids": [e["evidence_id"] for e in evidence],
            }
        )
    return projected


def reader_request(row, proposals=()):
    base = build_request(row)
    result = base.model_copy(
        update={
            "instructions": INSTRUCTIONS,
            "input": {
                **base.input,
                "query_time_proposals": list(proposals),
                "observation_policy": "provided-history-v1; not causal replay",
                "observed_until": max(
                    row.runtime.query.reference_time, *(m.at for m in messages(row))
                ).isoformat(),
            },
        }
    )
    if len(result.model_dump_json().encode()) > MAX_BYTES:
        raise ValueError("Reader request exceeds bound; no silent truncation")
    return result


async def build_plan(rows, bindings):
    requests = {r.case_id: await analyzer_request(r) for r in rows}
    if any(
        len(req.model_dump_json().encode()) > MAX_BYTES for req in requests.values()
    ):
        raise ValueError("analyzer request too large")
    root = Path(__file__).resolve().parents[1]
    paths = [
        Path(__file__),
        *[
            root / p
            for p in (
                "benchmarks/aml_evidence_representation.py",
                "benchmarks/public_memory_oracle_diagnostic.py",
                "benchmarks/public_memory_response_policy.py",
                "benchmarks/public_memory_reader_v2.py",
                "benchmarks/public_memory_high_config_first.py",
                "benchmarks/public_memory_ingestion.py",
                "benchmarks/public_memory_expansion.py",
                "benchmarks/public_memory_answer_comparison.py",
                "benchmarks/public_memory_runtime.py",
                "benchmarks/public_longmemeval.py",
            )
        ],
    ]
    plan = {
        "runner": RUNNER,
        "bindings": bindings,
        "selection": "previous first-opened temporal and knowledge-update; saved S raw reranked; no outcome selection",
        "case_ids": [r.case_id for r in rows],
        "source_context_sha256": {r.case_id: _hash(r.context) for r in rows},
        "analyzer_requests": {
            k: _hash(v.model_dump(mode="json")) for k, v in requests.items()
        },
        "analyzer_request_bytes": {
            k: len(v.model_dump_json().encode()) for k, v in requests.items()
        },
        "baseline_reader_requests": {
            r.case_id: _hash(reader_request(r).model_dump(mode="json")) for r in rows
        },
        "analyzer_config": config(4096).model_dump(mode="json"),
        "reader_config": config(1024).model_dump(mode="json"),
        "miner_config": {
            r.case_id: {
                **miner_config(len(messages(r))).model_dump(mode="json"),
                "allowed_source_actors": ["agent", "owner"],
            }
            for r in rows
        },
        "observation_policy": "provided-history-v1; original question clock retained; not causal replay",
        "observations_after_question_clock": {
            r.case_id: sum(m.at > r.runtime.query.reference_time for m in messages(r))
            for r in rows
        },
        "max_analyzer_calls": len(rows),
        "max_reader_calls": 2 * len(rows),
        "max_judge_calls": 0,
        "max_request_bytes": MAX_BYTES,
        "balance_stop_cny": 1,
        "failure_policy": "single attempt; preserve failure; fail-stop; no retry/repair",
        "candidate_reader_request": "dynamic from actual gated proposals; hash receipted before its call; generation rule frozen, not pre-known output",
        "contrast": "same raw evidence plus optional unverified proposals; unequal context length and one extra analyzer call",
        "not_executed": [
            "new retrieval",
            "graph",
            "consolidation",
            "Store writes",
            "oracle context",
            "eager S analysis",
            "reserved cases",
            "Judge",
        ],
        "core_runtime_source_sha256": execution_metadata()["runtime_source_sha256"],
        "source_sha256": {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths
        },
        "semantic_scores": None,
        "publication_ready": False,
    }
    return {**plan, "plan_fingerprint": _hash(plan)}


class RawAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memories: list[dict]


class ReceiptedAnalyzerModel:
    def __init__(self, model, path, expected_hash):
        self.model, self.path, self.expected_hash = model, path, expected_hash
        self.name, self.version = model.name, model.version

    async def generate(self, request):
        if _hash(request.model_dump(mode="json")) != self.expected_hash:
            raise ValueError("analyzer request differs from frozen source window")
        return await persisted_generation(self.model, request, RawAnalysis, self.path)


async def execute(args, rows, plan, *, provider_factory=None, balance_reader=balance):
    key = "" if args.cache_only else os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and not args.cache_only:
        raise ValueError("DEEPSEEK_API_KEY missing")
    _bind_json(args.run_dir / "plan.json", plan)
    initial = None
    if not args.cache_only:
        current = await balance_reader(key)
        start = args.run_dir / "balance-start.json"
        if not start.exists():
            save(start, {"initial_cny": current})
        initial = json.loads(start.read_bytes())["initial_cny"]
    ledgers, providers, models = {}, {}, {}
    results, stopped, final = [], "", None
    try:
        for stage, tokens, cap in (
            ("analyzer", 4096, plan["max_analyzer_calls"]),
            ("reader", 1024, plan["max_reader_calls"]),
        ):
            ledger = DurableCallLedger(
                args.run_dir / (stage + ".sqlite"),
                budget_id=plan["plan_fingerprint"] + ":" + stage,
                max_calls=cap,
                max_request_bytes=MAX_BYTES,
                max_total_request_bytes=MAX_BYTES * cap,
            )
            ledgers[stage] = ledger
            provider = (
                provider_factory(config(tokens), key, ledger.observe_usage)
                if provider_factory
                else ObservedProvider(
                    config(tokens),
                    key,
                    ledger.observe_usage,
                    args.run_dir / "model-receipts" / stage,
                )
            )
            providers[stage] = provider
            models[stage] = PilotStructuredModel(
                provider,
                ledger=ledger,
                cache_dir=args.run_dir / stage,
                cache_only=args.cache_only,
            )
        for row in rows:
            outcome = {"case_id": row.case_id, "status": "failed", "arms": {}}
            try:
                # Analyzer is question-independent. Its only input is the selected
                # source window. Never expose answer, scoring category or labels.
                diagnostics = []
                model = ReceiptedAnalyzerModel(
                    models["analyzer"],
                    args.run_dir / "receipts" / (row.case_id + "-analysis.json"),
                    plan["analyzer_requests"][row.case_id],
                )
                analyzer = ReferencePersonalMemoryAnalyzer(
                    model,
                    diagnostics_observer=lambda d, sink=diagnostics: sink.append(
                        d.model_dump(mode="json")
                    ),
                )
                cfg = miner_config(len(messages(row)))
                tasks = (
                    ("baseline", "analyzer", "candidate")
                    if row.index % 2 == 0
                    else ("analyzer", "candidate", "baseline")
                )
                proposals = []
                for task in tasks:
                    if not args.cache_only:
                        final = await balance_reader(key)
                        if final <= 0 or initial - final >= plan["balance_stop_cny"]:
                            raise ValueError("observed balance stop")
                    if task == "analyzer":
                        generated = await PersonalMemoryMiner(analyzer, cfg).propose(
                            task_context(row)
                        )
                        if generated.next_checkpoint is None:
                            raise ValueError("missing analysis checkpoint")
                        proposals = project_proposals(row, generated.proposals)
                        outcome["analysis"] = {
                            "proposals": proposals,
                            "schema_diagnostics": diagnostics,
                            "checkpoint": generated.next_checkpoint.model_dump(
                                mode="json"
                            ),
                        }
                        if generated.next_checkpoint.metadata["truncated"]:
                            raise ValueError("incomplete bounded window")
                    else:
                        arm = ARMS[0] if task == "baseline" else ARMS[1]
                        request = reader_request(
                            row, proposals if task == "candidate" else ()
                        )
                        output = await persisted_generation(
                            models["reader"],
                            request,
                            ReaderV2Output,
                            args.run_dir
                            / "receipts"
                            / (row.case_id + "-" + arm + ".json"),
                        )
                        checks = structural_check(row, output)
                        outcome["arms"][arm] = {
                            "output": output.model_dump(mode="json"),
                            "checks": checks,
                            "request_sha256": _hash(request.model_dump(mode="json")),
                            "request_bytes": len(request.model_dump_json().encode()),
                        }
                        if not checks["structurally_valid"]:
                            raise ValueError("invalid citations or derivation")
                    print(f"{row.case_id} {task}: complete", flush=True)
                outcome["status"] = "complete"
            except Exception as error:  # noqa: BLE001 - preserve closed type, never key/provider text
                outcome["failure_type"] = type(error).__name__
                stopped = "preserved_failure_no_retry"
            results.append(outcome)
            if stopped:
                break
        if not args.cache_only:
            try:
                final = await balance_reader(key)
            except Exception:  # noqa: BLE001 - accounting uncertainty disclosed
                final = None
        return {
            "status": "complete"
            if len(results) == len(rows) and not stopped
            else "stopped",
            "rows": results,
            "stopped_reason": stopped,
            "usage": {s: m.report() for s, m in models.items()},
            "balance_observation": {
                "initial_cny": initial,
                "final_cny": final,
                "exclusive_billing_attribution_proven": False,
            },
        }
    finally:
        for ledger in ledgers.values():
            ledger.close()
        for provider in providers.values():
            if hasattr(provider, "aclose"):
                await provider.aclose()


def load_rows(args):
    contents = {
        k: getattr(args, k).read_bytes()
        for k in ("source", "oracle", "manifest", "comparison", "quality")
    }
    binding = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
    data = {k: json.loads(v) for k, v in contents.items()}
    if data["manifest"]["source_sha256"] != binding["source"]:
        raise ValueError("manifest source changed")
    protected = set()
    for path in args.prior_manifest:
        raw = path.read_bytes()
        prior = json.loads(raw)
        if prior["source_sha256"] != binding["source"]:
            raise ValueError("reserved source changed")
        binding[str(path)] = hashlib.sha256(raw).hexdigest()
        protected.update(
            r["case_id"] for r in prior["cases"] if r["partition"] == "reserved"
        )
    # Existing deterministic public-category selection; oracle is used here only
    # to reconstruct that existing selection, never as an analyzer/Reader context.
    original = prepare_rows(data["source"], data["oracle"], data["manifest"], protected)
    pairs = paired_rows(original, data["comparison"], data["quality"], binding)
    rows = [
        r
        for r in pairs
        if r.profile == "s-raw-vector-reranked" and r.scoring.category in CATEGORIES
    ]
    if len(rows) != 2 or {r.scoring.category for r in rows} != set(CATEGORIES):
        raise ValueError("two frozen opened categories required")
    by_id = {r["question_id"]: r for r in data["source"]}
    return [
        replace(
            r,
            index=i,
            runtime=prepare_case(
                by_id[r.case_id], dataset_namespace="lazy-proposal-diagnostic-v1"
            ).runtime,
        )
        for i, r in enumerate(rows)
    ], binding


async def run(args):
    rows, bindings = load_rows(args)
    plan = await build_plan(rows, bindings)
    report = {
        "runner": RUNNER,
        "status": "ready",
        "plan": plan,
        "record_or_index_writes": 0,
        "publication_ready": False,
    }
    if args.live:
        if (
            not args.frozen_preflight
            or json.loads(args.frozen_preflight.read_bytes())["plan"] != plan
        ):
            raise ValueError("unchanged frozen preflight required")
        report.update(await execute(args, rows, plan))
    report["execution_metadata"] = execution_metadata()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "source",
        "oracle",
        "manifest",
        "comparison",
        "quality",
        "run-dir",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path, action="append", required=True)
    parser.add_argument("--frozen-preflight", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or (args.cache_only and not args.live):
        parser.error("preserve artifacts; cache-only requires live")
    result = asyncio.run(run(args))
    save(args.output, result)
    print(json.dumps({"status": result["status"], "cases": result["plan"]["case_ids"]}))
    return 0 if result["status"] in {"ready", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

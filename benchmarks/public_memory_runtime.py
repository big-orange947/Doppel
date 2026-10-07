"""Persistent, content-free call accounting for the public-history pilot.

No provider is constructed here. Hosts wire ``ledger.observe_usage`` to their
provider, then wrap it in ``PilotStructuredModel``. Each reservation counts as
an attempted call even after a timeout, cancellation or process termination.
This bounds attempts, not exact billing or tokens, and never retries itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from benchmarks.relation_planner_quality import CachedStructuredOutputModel
from doppel_memory.intelligence import (
    StructuredGenerationRequest,
    StructuredOutputModel,
)

_ACTIVE_CALL: ContextVar[tuple[object, int] | None] = ContextVar(
    "public_pilot_call", default=None
)
_TOKEN_FIELDS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "cache_miss_input_tokens",
    "reasoning_tokens",
}


class PilotRuntimeError(RuntimeError):
    """Redacted runtime failure; cached source/output stay in local ignored files."""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DurableCallLedger:
    """Cross-process atomic attempt cap with immutable run/stage configuration.

    Byte limits apply to canonical StructuredGenerationRequest JSON, not the
    transport's HTTP envelope or a tokenizer estimate. Unknown/missing usage is
    counted separately; unobserved tokens are never reported as zero spent.
    Increasing a budget requires an explicit new budget identity; reports must
    aggregate identities if the host authorizes an extension.
    """

    def __init__(
        self,
        path: Path,
        *,
        budget_id: str,
        max_calls: int,
        max_request_bytes: int = 1_000_000,
        max_total_request_bytes: int = 100_000_000,
    ) -> None:
        if not budget_id.strip():
            raise ValueError("budget_id must be nonempty and non-secret")
        if any(
            type(v) is not int or v < 0
            for v in (max_calls, max_request_bytes, max_total_request_bytes)
        ):
            raise ValueError("budget limits must be nonnegative integers")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS pilot_budgets (
                budget_id TEXT PRIMARY KEY, limits TEXT NOT NULL, model TEXT
            );
            CREATE TABLE IF NOT EXISTS pilot_calls (
                call_id INTEGER PRIMARY KEY, budget_id TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, request_bytes INTEGER NOT NULL,
                status TEXT NOT NULL, usage TEXT
            );
            CREATE INDEX IF NOT EXISTS pilot_calls_budget ON pilot_calls(budget_id);
        """)
        self.budget_id = budget_id
        self.max_calls = max_calls
        self.max_request_bytes = max_request_bytes
        self.max_total_request_bytes = max_total_request_bytes
        limits = _json(
            {
                "max_calls": max_calls,
                "max_request_bytes": max_request_bytes,
                "max_total_request_bytes": max_total_request_bytes,
            }
        )
        self._db.execute(
            "INSERT OR IGNORE INTO pilot_budgets VALUES (?, ?, NULL)",
            (budget_id, limits),
        )
        row = self._db.execute(
            "SELECT limits FROM pilot_budgets WHERE budget_id=?", (budget_id,)
        ).fetchone()
        if row is None or row[0] != limits:
            self._db.close()
            raise PilotRuntimeError(
                "budget configuration differs from durable checkpoint"
            )
        self._bound = False

    def bind_model(self, name: str, version: str) -> None:
        if not name or not version:
            raise ValueError("model requires stable non-secret name/version")
        identity = _json({"name": name, "version": version})
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT model FROM pilot_budgets WHERE budget_id=?", (self.budget_id,)
            ).fetchone()
            if row is None or row[0] not in (None, identity):
                raise PilotRuntimeError("model differs from durable budget checkpoint")
            self._db.execute(
                "UPDATE pilot_budgets SET model=? WHERE budget_id=?",
                (identity, self.budget_id),
            )
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        self._bound = True

    def reserve(self, request: StructuredGenerationRequest) -> int:
        if not self._bound:
            raise PilotRuntimeError("bind model before reserving calls")
        encoded = _json(request.model_dump(mode="json")).encode("utf-8")
        if len(encoded) > self.max_request_bytes:
            raise PilotRuntimeError("per-call canonical request byte budget exhausted")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            count, size = self._db.execute(
                "SELECT COUNT(*), COALESCE(SUM(request_bytes), 0) FROM pilot_calls "
                "WHERE budget_id=?",
                (self.budget_id,),
            ).fetchone()
            if count >= self.max_calls:
                raise PilotRuntimeError("durable provider attempt budget exhausted")
            if size + len(encoded) > self.max_total_request_bytes:
                raise PilotRuntimeError("total canonical request byte budget exhausted")
            cursor = self._db.execute(
                "INSERT INTO pilot_calls(budget_id, request_sha256, request_bytes, status) "
                "VALUES (?, ?, ?, 'reserved')",
                (self.budget_id, hashlib.sha256(encoded).hexdigest(), len(encoded)),
            )
            call_id = cursor.lastrowid
            if call_id is None:
                raise PilotRuntimeError("call reservation has no identity")
            self._db.execute("COMMIT")
            return call_id
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def observe_usage(self, usage: Mapping[str, int]) -> None:
        active = _ACTIVE_CALL.get()
        if active is None or active[0] is not self:
            raise PilotRuntimeError("usage has no bound provider attempt")
        safe = {
            key: value
            for key, value in usage.items()
            if key in _TOKEN_FIELDS and type(value) is int and value >= 0
        }
        if not safe:
            return
        cursor = self._db.execute(
            "UPDATE pilot_calls SET usage=? WHERE call_id=? AND budget_id=? AND usage IS NULL",
            (_json(safe), active[1], self.budget_id),
        )
        if cursor.rowcount != 1:
            raise PilotRuntimeError("duplicate or unknown usage observation")

    def finish(self, call_id: int, status: str) -> None:
        if status not in {"succeeded", "failed", "interrupted"}:
            raise ValueError("unsupported attempt status")
        self._db.execute(
            "UPDATE pilot_calls SET status=? WHERE call_id=? AND budget_id=?",
            (status, call_id, self.budget_id),
        )

    def report(self) -> dict[str, Any]:
        rows = self._db.execute(
            "SELECT request_bytes, status, usage FROM pilot_calls WHERE budget_id=?",
            (self.budget_id,),
        ).fetchall()
        counts = {
            status: 0 for status in ("reserved", "succeeded", "failed", "interrupted")
        }
        totals: dict[str, int] = {}
        observed = 0
        complete_usage = 0
        for _, status, raw in rows:
            counts[status] += 1
            if raw is not None:
                observed += 1
                usage = json.loads(raw)
                complete_usage += {
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                } <= set(usage)
                for field, value in usage.items():
                    totals[field] = totals.get(field, 0) + value
        size = sum(row[0] for row in rows)
        return {
            "budget_id": self.budget_id,
            "attempts_reserved": len(rows),
            "attempt_status_counts": counts,
            "max_calls": self.max_calls,
            "canonical_request_bytes": size,
            "within_attempt_and_byte_budget": len(rows) <= self.max_calls
            and size <= self.max_total_request_bytes,
            "calls_with_usage": observed,
            "calls_with_complete_usage": complete_usage,
            "calls_without_usage": len(rows) - observed,
            "reported_tokens": totals if observed else None,
            "token_accounting_complete": complete_usage == len(rows),
            "token_hard_cap_enforced": False,
            "exact_billing_guaranteed": False,
        }

    def close(self) -> None:
        self._db.close()


class _BudgetedModel:
    def __init__(self, model: StructuredOutputModel, ledger: DurableCallLedger) -> None:
        self.name, self.version = model.name, model.version
        self.model, self.ledger = model, ledger
        ledger.bind_model(self.name, self.version)

    async def generate(
        self, request: StructuredGenerationRequest
    ) -> Mapping[str, Any] | BaseModel:
        call_id = self.ledger.reserve(request)
        token = _ACTIVE_CALL.set((self.ledger, call_id))
        try:
            raw = await self.model.generate(request)
        except Exception:  # noqa: BLE001 - never persist arbitrary provider error text
            self.ledger.finish(call_id, "failed")
            raise PilotRuntimeError(
                "provider attempt failed; details not persisted"
            ) from None
        except BaseException:
            self.ledger.finish(call_id, "interrupted")
            raise
        else:
            self.ledger.finish(call_id, "succeeded")
            return raw
        finally:
            _ACTIVE_CALL.reset(token)


class PilotStructuredModel:
    """Reuse raw-output cache, serialize local duplicate requests, never retry.

    Separate instances/processes may reserve duplicate misses, but the shared
    ledger still enforces the total cap. Cache-only mode never reaches provider.
    Cache write/parse failures are surfaced; they are not silently rebilled.
    """

    def __init__(
        self,
        model: StructuredOutputModel,
        *,
        ledger: DurableCallLedger,
        cache_dir: Path,
        cache_only: bool = False,
        read_only_cache_dirs: Sequence[Path] = (),
    ) -> None:
        self.name, self.version = model.name, model.version
        self.ledger = ledger
        self._provider = model
        budgeted = _BudgetedModel(model, ledger)
        self._cache = CachedStructuredOutputModel(
            budgeted,
            cache_dir,
            cache_only=cache_only,
            fail_on_invalid_cache=True,
        )
        paths = [path.resolve() for path in read_only_cache_dirs]
        if len(set(paths)) != len(paths) or cache_dir.resolve() in paths:
            raise ValueError("cache parents must be distinct from the writable cache")
        if any(not path.is_dir() for path in paths):
            raise ValueError("read-only provider cache directory is unavailable")
        self._parents = [
            CachedStructuredOutputModel(
                budgeted, path, cache_only=True, fail_on_invalid_cache=True
            )
            for path in paths
        ]
        self._lock = asyncio.Lock()

    async def generate(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        bound = StructuredGenerationRequest.model_validate_json(
            request.model_dump_json()
        )
        async with self._lock:
            if (self._provider.name, self._provider.version) != (
                self.name,
                self.version,
            ):
                raise PilotRuntimeError("model identity changed after binding")
            try:
                primary_path = self._cache._cache_path(bound)
                if primary_path is not None and not primary_path.is_file():
                    for parent in self._parents:
                        parent_path = parent._cache_path(bound)
                        if parent_path is not None and parent_path.is_file():
                            # Envelope binds exact prompt/input/schema/model. Invalid
                            # parent output fails closed; never rebill or rewrite it.
                            return await parent.generate(bound)
                return await self._cache.generate(bound)
            except PilotRuntimeError:
                raise
            except Exception:  # noqa: BLE001 - redact cache/provider payloads
                raise PilotRuntimeError(
                    "provider-output cache/read validation failed"
                ) from None

    def report(self) -> dict[str, Any]:
        return {
            "ledger": self.ledger.report(),
            "cache_hits_this_instance": self._cache.hits
            + sum(parent.hits for parent in self._parents),
            "read_only_cache_hits_this_instance": sum(
                parent.hits for parent in self._parents
            ),
            "cache_misses_this_instance": self._cache.misses,
            "invalid_cache_entries_this_instance": self._cache.invalid_entries_ignored
            + sum(parent.invalid_entries_ignored for parent in self._parents),
        }

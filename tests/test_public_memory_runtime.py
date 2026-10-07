"""Durable SQLite budgets and raw response replay; no external model calls."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from benchmarks.public_memory_runtime import (
    DurableCallLedger,
    PilotRuntimeError,
    PilotStructuredModel,
)
from doppel_memory.intelligence import StructuredGenerationRequest

REQUEST = StructuredGenerationRequest(
    instructions="Return structured data",
    input={"text": "原始消息"},
    output_schema={"type": "object"},
)


class FakeModel:
    name, version = "fake-no-network", "1"

    def __init__(self, ledger: DurableCallLedger) -> None:
        self.ledger = ledger
        self.calls = 0
        self.error = False
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None

    async def generate(self, request: StructuredGenerationRequest) -> dict:
        self.calls += 1
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        self.ledger.observe_usage(
            {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}
        )
        if self.error:
            raise ValueError("NEVER_PERSIST_PROVIDER_SECRET")
        await asyncio.sleep(0)
        # Deliberately invalid downstream schema: raw cache must still replay it.
        return {"memories": [{"invalid": True}]}


def ledger_at(path: Path, *, calls: int = 2, **kwargs) -> DurableCallLedger:
    return DurableCallLedger(
        path / "ledger.sqlite3", budget_id="pilot/extraction", max_calls=calls, **kwargs
    )


def wrap(
    path: Path, ledger: DurableCallLedger, model: FakeModel, **kwargs
) -> PilotStructuredModel:
    return PilotStructuredModel(
        model, ledger=ledger, cache_dir=path / "cache", **kwargs
    )


@pytest.mark.asyncio
async def test_restart_replays_raw_invalid_drafts_without_spending(
    tmp_path: Path,
) -> None:
    ledger = ledger_at(tmp_path, calls=1)
    first = wrap(tmp_path, ledger, FakeModel(ledger))
    raw = await first.generate(REQUEST)
    ledger.close()
    restarted = ledger_at(tmp_path, calls=1)
    provider = FakeModel(restarted)
    model = wrap(tmp_path, restarted, provider, cache_only=True)
    assert await model.generate(REQUEST) == raw
    assert provider.calls == 0
    assert model.report()["ledger"]["attempts_reserved"] == 1
    assert model.report()["ledger"]["reported_tokens"]["total_tokens"] == 7
    assert model.report()["cache_hits_this_instance"] == 1
    restarted.close()


async def test_read_only_parent_cache_reuses_raw_outputs_without_rewriting_or_rebilling(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    old_ledger = ledger_at(parent, calls=1)
    old_model = FakeModel(old_ledger)
    old = wrap(parent, old_ledger, old_model)
    output = await old.generate(REQUEST)
    snapshot = {path: path.read_bytes() for path in (parent / "cache").rglob("*.json")}
    old_ledger.close()
    child = tmp_path / "child"
    child.mkdir()
    new_ledger = ledger_at(child, calls=0)
    provider = FakeModel(new_ledger)
    model = wrap(
        child,
        new_ledger,
        provider,
        cache_only=True,
        read_only_cache_dirs=[parent / "cache"],
    )
    assert await model.generate(REQUEST) == output
    assert provider.calls == 0 and new_ledger.report()["attempts_reserved"] == 0
    assert model.report()["read_only_cache_hits_this_instance"] == 1
    assert not list((child / "cache").rglob("*.json"))
    assert {path: path.read_bytes() for path in snapshot} == snapshot
    changed = REQUEST.model_copy(update={"instructions": "Different prompt"})
    with pytest.raises(PilotRuntimeError):
        await model.generate(changed)
    assert provider.calls == 0
    new_ledger.close()


@pytest.mark.asyncio
async def test_invalid_parent_cache_fails_closed_without_rebilling(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    old_ledger = ledger_at(parent, calls=1)
    await wrap(parent, old_ledger, FakeModel(old_ledger)).generate(REQUEST)
    old_ledger.close()
    cache_file = next((parent / "cache").rglob("*.json"))
    cache_file.write_text("{broken", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    ledger = ledger_at(child, calls=1)
    provider = FakeModel(ledger)
    try:
        model = wrap(child, ledger, provider, read_only_cache_dirs=[parent / "cache"])
        with pytest.raises(PilotRuntimeError, match="cache/read"):
            await model.generate(REQUEST)
        assert provider.calls == ledger.report()["attempts_reserved"] == 0
        assert model.report()["invalid_cache_entries_this_instance"] == 1
        assert cache_file.read_text(encoding="utf-8") == "{broken"
        assert not list((child / "cache").rglob("*.json"))
    finally:
        ledger.close()


@pytest.mark.asyncio
async def test_same_request_concurrency_coalesces_locally(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, calls=1)
    provider = FakeModel(ledger)
    model = wrap(tmp_path, ledger, provider)
    result = await asyncio.gather(*(model.generate(REQUEST) for _ in range(10)))
    assert all(value == result[0] for value in result)
    assert provider.calls == 1
    assert model.report()["cache_hits_this_instance"] == 9
    ledger.close()


@pytest.mark.asyncio
async def test_different_requests_stop_at_cap(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, calls=3)
    provider = FakeModel(ledger)
    model = wrap(tmp_path, ledger, provider)
    results = await asyncio.gather(
        *(
            model.generate(REQUEST.model_copy(update={"input": {"sequence": i}}))
            for i in range(10)
        ),
        return_exceptions=True,
    )
    assert provider.calls == 3
    assert sum(isinstance(value, PilotRuntimeError) for value in results) == 7
    assert ledger.report()["within_attempt_and_byte_budget"]
    ledger.close()


@pytest.mark.asyncio
async def test_failure_charges_attempt_and_usage_but_no_cache_or_secrets(
    tmp_path: Path,
) -> None:
    ledger = ledger_at(tmp_path, calls=1)
    provider = FakeModel(ledger)
    provider.error = True
    model = wrap(tmp_path, ledger, provider)
    with pytest.raises(PilotRuntimeError) as error:
        await model.generate(REQUEST)
    assert "NEVER_PERSIST" not in str(error.value)
    assert ledger.report()["attempt_status_counts"]["failed"] == 1
    assert ledger.report()["reported_tokens"]["total_tokens"] == 7
    with pytest.raises(PilotRuntimeError, match="budget exhausted"):
        await model.generate(REQUEST)
    assert provider.calls == 1
    assert not list((tmp_path / "cache").rglob("*.json"))
    ledger.close()
    assert b"NEVER_PERSIST" not in (tmp_path / "ledger.sqlite3").read_bytes()


@pytest.mark.asyncio
async def test_cancellation_is_not_refunded_and_lock_released(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, calls=1)
    provider = FakeModel(ledger)
    provider.release = asyncio.Event()
    model = wrap(tmp_path, ledger, provider)
    task = asyncio.create_task(model.generate(REQUEST))
    await provider.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ledger.report()["attempt_status_counts"]["interrupted"] == 1
    assert ledger.report()["reported_tokens"] is None
    assert ledger.report()["calls_without_usage"] == 1
    with pytest.raises(PilotRuntimeError, match="budget exhausted"):
        await model.generate(REQUEST)
    ledger.close()


@pytest.mark.asyncio
async def test_invalid_cache_does_not_silently_rebill(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    provider = FakeModel(ledger)
    model = wrap(tmp_path, ledger, provider)
    await model.generate(REQUEST)
    cache_file = next((tmp_path / "cache").rglob("*.json"))
    cache_file.write_text("{broken", encoding="utf-8")
    with pytest.raises(PilotRuntimeError, match="cache/read"):
        await model.generate(REQUEST)
    assert provider.calls == 1
    assert model.report()["invalid_cache_entries_this_instance"] == 1
    ledger.close()


@pytest.mark.asyncio
async def test_zero_budget_allows_cache_only_miss_without_call(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, calls=0)
    provider = FakeModel(ledger)
    with pytest.raises(PilotRuntimeError):
        await wrap(tmp_path, ledger, provider, cache_only=True).generate(REQUEST)
    assert provider.calls == 0
    assert ledger.report()["attempts_reserved"] == 0
    ledger.close()


@pytest.mark.parametrize(
    "limits",
    [
        {"max_request_bytes": 1},
        {"max_total_request_bytes": 1},
    ],
)
@pytest.mark.asyncio
async def test_byte_caps_reject_before_provider(tmp_path: Path, limits: dict) -> None:
    ledger = ledger_at(tmp_path, **limits)
    provider = FakeModel(ledger)
    with pytest.raises(PilotRuntimeError, match="byte budget"):
        await wrap(tmp_path, ledger, provider).generate(REQUEST)
    assert provider.calls == 0
    assert ledger.report()["attempts_reserved"] == 0
    ledger.close()


def test_budget_and_provider_config_drift_rejected(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    ledger.bind_model("same-model", "1")
    ledger.close()
    with pytest.raises(PilotRuntimeError, match="configuration differs"):
        ledger_at(tmp_path, calls=3)
    restarted = ledger_at(tmp_path)
    with pytest.raises(PilotRuntimeError, match="model differs"):
        restarted.bind_model("same-model", "2")
    restarted.close()


def test_cross_process_style_connections_reserve_atomically(tmp_path: Path) -> None:
    original = ledger_at(tmp_path, calls=3)
    original.bind_model("fake", "1")
    original.close()

    def reserve(_: int) -> bool:
        ledger = ledger_at(tmp_path, calls=3)
        try:
            ledger.bind_model("fake", "1")
            ledger.reserve(REQUEST)
            return True
        except PilotRuntimeError:
            return False
        finally:
            ledger.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(reserve, range(10))) == 3
    restarted = ledger_at(tmp_path, calls=3)
    assert restarted.report()["attempt_status_counts"]["reserved"] == 3
    assert not restarted.report()["token_accounting_complete"]
    assert json.dumps(restarted.report()).find("原始消息") == -1
    restarted.close()


def test_unbound_usage_not_assigned_to_wrong_call(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    with pytest.raises(PilotRuntimeError, match="no bound"):
        ledger.observe_usage({"total_tokens": 42})
    ledger.close()


@pytest.mark.asyncio
async def test_mutated_model_identity_cannot_read_an_old_cache(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path)
    provider = FakeModel(ledger)
    model = wrap(tmp_path, ledger, provider)
    await model.generate(REQUEST)
    provider.version = "changed-configuration"
    with pytest.raises(PilotRuntimeError, match="identity changed"):
        await model.generate(REQUEST)
    assert provider.calls == 1
    ledger.close()

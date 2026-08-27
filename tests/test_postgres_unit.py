"""PostgreSQL API validation that does not require a running server."""

from __future__ import annotations

import pytest

from doppel_memory.postgres_store import PostgreSQLStore


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dsn": ""}, "DSN is required"),
        ({"dsn": "postgresql://unused", "schema": "bad-name"}, "schema must"),
        (
            {
                "dsn": "postgresql://unused",
                "min_pool_size": 3,
                "max_pool_size": 2,
            },
            "max_pool_size",
        ),
        (
            {"dsn": "postgresql://unused", "command_timeout": 0},
            "command_timeout",
        ),
    ],
)
def test_constructor_rejects_unsafe_or_invalid_configuration(
    kwargs, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PostgreSQLStore(**kwargs)


def test_capabilities_match_implemented_contract() -> None:
    store = PostgreSQLStore("postgresql://unused")
    assert store.schema == "public"
    assert store.capabilities.substring_search
    assert store.capabilities.temporal_search
    assert store.capabilities.transactions
    assert store.capabilities.pagination
    assert store.capabilities.hard_delete
    assert not store.capabilities.full_text_search
    assert not store.capabilities.semantic_search


async def test_missing_optional_driver_fails_at_first_operation(monkeypatch) -> None:
    import doppel_memory.postgres_store as postgres_module

    def missing_driver(name: str):
        assert name == "asyncpg"
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(postgres_module.importlib, "import_module", missing_driver)
    store = PostgreSQLStore("postgresql://unused")
    with pytest.raises(RuntimeError, match=r"doppel-memory\[postgres\]"):
        await store.health()

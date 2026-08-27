"""PostgreSQLStore runs the installed Store conformance suite when a DSN is set."""

from __future__ import annotations

import os

import pytest

from doppel_memory.postgres_store import PostgreSQLStore
from tests.store_contract import MemoryStoreContract

POSTGRES_DSN = os.environ.get("DOPPEL_TEST_POSTGRES_DSN", "")

pytestmark = pytest.mark.skipif(
    not POSTGRES_DSN,
    reason="DOPPEL_TEST_POSTGRES_DSN is not configured",
)


class TestPostgreSQLStoreContract(MemoryStoreContract):
    @pytest.fixture()
    async def store(self):
        backend = PostgreSQLStore(POSTGRES_DSN, min_pool_size=0, max_pool_size=4)
        yield backend
        await backend.close()

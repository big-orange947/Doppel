"""SQLiteStore runs the exact same conformance suite."""

import pytest

from doppel_memory.sqlite_store import SQLiteStore
from tests.store_contract import MemoryStoreContract


class TestSQLiteStoreContract(MemoryStoreContract):
    @pytest.fixture()
    async def store(self, tmp_path):
        backend = SQLiteStore(database=str(tmp_path / "doppel-test.sqlite3"))
        yield backend
        await backend.close()

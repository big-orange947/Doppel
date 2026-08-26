"""InMemoryStore runs the shared conformance suite."""

import pytest

from doppel_memory.in_memory_store import InMemoryStore
from tests.store_contract import MemoryStoreContract


class TestInMemoryStoreContract(MemoryStoreContract):
    @pytest.fixture()
    def store(self) -> InMemoryStore:
        return InMemoryStore()

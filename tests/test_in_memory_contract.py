"""InMemoryStore 契约测试（InMemory 后端必须通过全部契约断言）。"""

from __future__ import annotations

from doppel_memory.in_memory_store import InMemoryStore
from tests.store_contract import MemoryStoreContract


class TestInMemoryStoreContract(MemoryStoreContract):
    store_factory = InMemoryStore

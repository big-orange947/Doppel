"""Doppel：面向 IM Agent 的模块化记忆框架（说话人感知/会话隔离/可插拔后端）。"""

from doppel_memory.client import DoppelClient
from doppel_memory.in_memory_store import InMemoryStore
from doppel_memory.models import (
    Actor,
    ActorType,
    ChatMessage,
    FactAuthority,
    MemoryFilter,
    MemoryIsolationError,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryState,
    RecallResult,
    StoreCapabilities,
)
from doppel_memory.persona import (
    DefaultPromptRenderer,
    MaterialBundle,
    OwnerPersonaPolicy,
    PersonaMaterialsBuilder,
)
from doppel_memory.retriever import Retriever
from doppel_memory.sqlite_store import SQLiteStore
from doppel_memory.store import MemoryStore

__version__ = "0.2.0"

__all__ = [
    "Actor",
    "ActorType",
    "ChatMessage",
    "DefaultPromptRenderer",
    "DoppelClient",
    "FactAuthority",
    "InMemoryStore",
    "MaterialBundle",
    "MemoryFilter",
    "MemoryIsolationError",
    "MemoryKind",
    "MemoryRecord",
    "MemoryScope",
    "MemoryState",
    "MemoryStore",
    "OwnerPersonaPolicy",
    "PersonaMaterialsBuilder",
    "RecallResult",
    "Retriever",
    "SQLiteStore",
    "StoreCapabilities",
    "__version__",
]

"""Doppel：让聊天机器人像号主本人一样说话的代理人格记忆框架。"""

from doppel_memory.client import DoppelClient
from doppel_memory.models import (
    ActorType,
    BackgroundFact,
    ChatMessage,
    FactAuthority,
    MemoryIsolationError,
    MemoryScope,
    MemorableType,
    RecallResult,
    RelationFact,
    StyleProfile,
)
from doppel_memory.persona import PersonaMaterials
from doppel_memory.store import MemoryStore

__version__ = "0.1.0"

__all__ = [
    "ActorType",
    "BackgroundFact",
    "ChatMessage",
    "DoppelClient",
    "FactAuthority",
    "MemoryIsolationError",
    "MemoryScope",
    "MemoryStore",
    "MemorableType",
    "PersonaMaterials",
    "RecallResult",
    "RelationFact",
    "StyleProfile",
    "__version__",
]

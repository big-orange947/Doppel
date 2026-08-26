"""Doppel：面向 IM Agent 的模块化记忆框架（说话人感知/会话隔离/可插拔后端）。"""

from doppel_memory.client import DoppelClient
from doppel_memory.imports import IMImportBatch, IMImportItem, ImportResult
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
    MemoryStateConflictError,
    RecallResult,
    StoreCapabilities,
    WriteResult,
    WriteStatus,
)
from doppel_memory.persona import (
    DefaultPromptRenderer,
    MaterialBundle,
    OwnerPersonaPolicy,
    PersonaMaterialsBuilder,
)
from doppel_memory.processing import (
    EventProcessor,
    MemoryPipeline,
    MemoryProcessor,
    MemoryProposal,
    PassThroughProposalPolicy,
    ProcessingError,
    ProcessingResult,
    ProcessorHooks,
    ProposalPolicy,
)
from doppel_memory.retriever import (
    IdentityReranker,
    Reranker,
    RetrievalStrategy,
    Retriever,
    StoreRetrievalStrategy,
)
from doppel_memory.sqlite_store import SQLiteStore
from doppel_memory.store import MemoryStore

__version__ = "0.4.0"

__all__ = [
    "Actor",
    "ActorType",
    "ChatMessage",
    "DefaultPromptRenderer",
    "DoppelClient",
    "EventProcessor",
    "FactAuthority",
    "IMImportBatch",
    "IMImportItem",
    "IdentityReranker",
    "ImportResult",
    "InMemoryStore",
    "MaterialBundle",
    "MemoryFilter",
    "MemoryIsolationError",
    "MemoryKind",
    "MemoryPipeline",
    "MemoryProcessor",
    "MemoryProposal",
    "MemoryRecord",
    "MemoryScope",
    "MemoryState",
    "MemoryStateConflictError",
    "MemoryStore",
    "OwnerPersonaPolicy",
    "PassThroughProposalPolicy",
    "PersonaMaterialsBuilder",
    "ProcessingError",
    "ProcessingResult",
    "ProcessorHooks",
    "ProposalPolicy",
    "RecallResult",
    "Reranker",
    "RetrievalStrategy",
    "Retriever",
    "SQLiteStore",
    "StoreCapabilities",
    "StoreRetrievalStrategy",
    "WriteResult",
    "WriteStatus",
    "__version__",
]

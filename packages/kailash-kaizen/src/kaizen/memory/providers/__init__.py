"""
Memory Provider Interface for Autonomous Agents.

This module provides a standardized memory provider interface designed for
autonomous agent integration, particularly with LocalKaizenAdapter.

Types:
- MemorySource: Source of memory entries (conversation, learned, etc.)
- MemoryEntry: Structured memory entry with session awareness
- MemoryContext: LLM-ready context built from memories
- RetrievalStrategy: How to retrieve and rank memories

Providers:
- MemoryProvider: Abstract interface for memory operations
- BufferMemoryAdapter: Adapter wrapping existing BufferMemory
- HierarchicalMemory: Multi-tier memory with hot/warm/cold storage

Backends:
- DataFlowMemoryBackend: Database persistence via DataFlow
"""

from .buffer_adapter import BufferMemoryAdapter
from .hierarchical import HierarchicalMemory
from .provider import (
    MemoryContextError,
    MemoryDeletionError,
    MemoryProvider,
    MemoryProviderError,
    MemoryRetrievalError,
    MemoryStorageError,
    MemorySummarizationError,
)
from .types import MemoryContext, MemoryEntry, MemorySource, RetrievalStrategy

# Optional DataFlow backend (requires kailash-dataflow)
try:
    from .dataflow_backend import DATAFLOW_AVAILABLE, DataFlowMemoryBackend
except ImportError:
    DataFlowMemoryBackend = None
    DATAFLOW_AVAILABLE = False

__all__ = [
    # Types
    "MemorySource",
    "MemoryEntry",
    "MemoryContext",
    "RetrievalStrategy",
    # Interface
    "MemoryProvider",
    # Errors
    "MemoryProviderError",
    "MemoryStorageError",
    "MemoryRetrievalError",
    "MemoryContextError",
    "MemorySummarizationError",
    "MemoryDeletionError",
    # Implementations
    "BufferMemoryAdapter",
    "HierarchicalMemory",
    # Backends
    "DataFlowMemoryBackend",
    "DATAFLOW_AVAILABLE",
]

"""
Memory system interfaces and providers.

This module provides memory management capabilities for AI workflows,
including persistent storage, caching, and context management.

Conversation Memory:
- KaizenMemory: Abstract base for conversation memory
- BufferMemory: Full conversation history storage (in-memory)
- PersistentBufferMemory: Buffer memory with database persistence
- SummaryMemory: LLM-generated summaries with recent verbatim
- VectorMemory: Semantic search over conversation
- KnowledgeGraphMemory: Entity extraction and relationships

Shared Memory:
- SharedMemoryPool: Shared insight storage for multi-agent collaboration

Enterprise Memory:
- EnterpriseMemorySystem: 3-tier caching (hot/warm/cold)
"""

from .buffer import BufferMemory

# Conversation memory
from .conversation_base import KaizenMemory
from .enterprise import EnterpriseMemorySystem, MemoryMonitor, MemorySystemConfig
from .knowledge_graph import KnowledgeGraphMemory

# Persistence backends
from .persistence_backend import PersistenceBackend
from .persistent_buffer import PersistentBufferMemory
from .persistent_tiers import ColdMemoryTier, WarmMemoryTier

# Shared memory
from .shared_memory import SharedMemoryPool
from .summary import SummaryMemory
from .tiers import HotMemoryTier, MemoryTier, TierManager
from .vector import VectorMemory

__all__ = [
    # Tiered memory (existing)
    "MemoryTier",
    "HotMemoryTier",
    "WarmMemoryTier",
    "ColdMemoryTier",
    "TierManager",
    "EnterpriseMemorySystem",
    "MemorySystemConfig",
    "MemoryMonitor",
    # Individual conversation memory
    "KaizenMemory",
    "BufferMemory",
    "PersistentBufferMemory",  # NEW
    "SummaryMemory",
    "VectorMemory",
    "KnowledgeGraphMemory",
    # Shared memory
    "SharedMemoryPool",
    # Persistence
    "PersistenceBackend",
]

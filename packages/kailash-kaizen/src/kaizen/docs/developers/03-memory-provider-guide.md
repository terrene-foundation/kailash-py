# Memory Provider Interface Guide

This guide covers the Memory Provider interface for Kaizen autonomous agents, providing standardized memory operations with session awareness and multi-tier storage support.

## Overview

The Memory Provider interface defines a standardized API for memory operations in autonomous agents. It supports:

- **Session-aware storage**: All entries are scoped to sessions for multi-tenant support
- **Multiple retrieval strategies**: Recency, importance, relevance, and hybrid ranking
- **Token-aware context building**: Build LLM-ready context within token budgets
- **Multi-tier storage**: Hot (in-memory), warm (database), cold (archive) tiers
- **Semantic search**: Optional embedding-based relevance search

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MemoryProvider (ABC)                      │
│  store() | recall() | build_context() | summarize() | forget()│
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│BufferMemoryAdapter│  │HierarchicalMemory│  │ Custom Provider │
│  (In-memory)     │  │  (Multi-tier)    │  │  (Your impl)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              ┌────────┐ ┌────────┐ ┌────────┐
              │Hot Tier│ │Warm Tier│ │Cold Tier│
              │(Buffer)│ │(DataFlow)│ │(Archive)│
              └────────┘ └────────┘ └────────┘
```

## Core Types

### MemorySource

Indicates the origin of a memory entry:

```python
from kaizen.memory.providers import MemorySource

MemorySource.CONVERSATION  # From agent/user conversation
MemorySource.LEARNED       # Agent-learned information
MemorySource.EXTERNAL      # External knowledge injection
MemorySource.SYSTEM        # System-generated entries
```

### MemoryEntry

A session-aware memory entry with rich metadata:

```python
from kaizen.memory.providers import MemoryEntry, MemorySource
from datetime import datetime, timezone

entry = MemoryEntry(
    content="The user prefers dark mode interfaces",
    session_id="session-123",
    role="assistant",  # "user", "assistant", "system", "tool"
    source=MemorySource.LEARNED,
    importance=0.8,  # 0.0-1.0, higher = more important
    tags=["preference", "ui"],
    metadata={"context": "settings discussion"},
)

# Convert to LLM message format
message = entry.to_message()
# {"role": "assistant", "content": "The user prefers..."}

# Serialize for storage
data = entry.to_dict()
restored = MemoryEntry.from_dict(data)

# Create from LLM message
entry = MemoryEntry.from_message(
    {"role": "user", "content": "Hello!"},
    session_id="session-123",
    source=MemorySource.CONVERSATION,
    importance=0.5,
)

# Filter matching
filters = {"source": MemorySource.LEARNED, "min_importance": 0.7}
if entry.matches_filter(filters):
    print("Entry matches!")
```

### MemoryContext

LLM-ready context built from memories:

```python
from kaizen.memory.providers import MemoryContext, RetrievalStrategy

context = MemoryContext(
    entries=[entry1, entry2, entry3],
    summary="Summary of older memories...",
    total_tokens=1500,
    entries_retrieved=3,
    entries_summarized=10,
    retrieval_strategy=RetrievalStrategy.HYBRID,
    retrieval_query="user preferences",
)

# Build system prompt
system_prompt = context.to_system_prompt()
# "Previous conversation context:\n\n[user]: Hello\n[assistant]: Hi!..."

# Build message list for LLM
messages = context.to_messages()
# [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}]

# Check if empty
if context.is_empty:
    print("No memories found")
```

### RetrievalStrategy

How to rank and retrieve memories:

```python
from kaizen.memory.providers import RetrievalStrategy

RetrievalStrategy.RECENCY     # Newest first
RetrievalStrategy.IMPORTANCE  # Highest importance first
RetrievalStrategy.RELEVANCE   # Most relevant to query (requires embeddings)
RetrievalStrategy.HYBRID      # Weighted combination (0.4 recency + 0.3 importance + 0.3 relevance)
```

## MemoryProvider Interface

All memory providers implement this abstract interface:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime

from kaizen.memory.providers import (
    MemoryEntry,
    MemoryContext,
    RetrievalStrategy,
)


class MemoryProvider(ABC):
    """Abstract interface for memory operations."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry. Returns entry ID."""
        ...

    @abstractmethod
    async def recall(
        self,
        query: str = "",
        session_id: str = "",
        max_entries: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryEntry]:
        """Recall relevant memory entries."""
        ...

    @abstractmethod
    async def build_context(
        self,
        query: str = "",
        session_id: str = "",
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.RECENCY,
    ) -> MemoryContext:
        """Build LLM-ready context from memories."""
        ...

    @abstractmethod
    async def summarize(
        self,
        session_id: str = "",
        entries: Optional[List[MemoryEntry]] = None,
    ) -> str:
        """Summarize memory entries."""
        ...

    @abstractmethod
    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Remove entries. Returns count deleted."""
        ...

    # Optional methods with default implementations
    async def store_many(self, entries: List[MemoryEntry]) -> List[str]:
        """Bulk store entries."""
        return [await self.store(e) for e in entries]

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get specific entry by ID."""
        return None

    async def count(
        self,
        session_id: str = "",
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count matching entries."""
        return 0

    async def clear(self, session_id: str = "") -> int:
        """Clear all entries (optionally by session)."""
        return await self.forget(session_id=session_id if session_id else None)

    async def health_check(self) -> bool:
        """Check provider health."""
        return True
```

## Built-in Providers

### BufferMemoryAdapter

Wraps existing BufferMemory for backward compatibility:

```python
from kaizen.memory import BufferMemory
from kaizen.memory.providers import BufferMemoryAdapter, MemoryEntry

# Option 1: Create with existing BufferMemory
buffer = BufferMemory(max_turns=100)
adapter = BufferMemoryAdapter(buffer)

# Option 2: Create standalone
adapter = BufferMemoryAdapter(max_turns=100)

# Store entries
entry = MemoryEntry(content="Hello!", session_id="s1", role="user")
entry_id = await adapter.store(entry)

# Recall with keyword search
entries = await adapter.recall(
    query="hello",
    session_id="s1",
    max_entries=10,
)

# Build context
context = await adapter.build_context(
    session_id="s1",
    max_tokens=4000,
)

# Access underlying BufferMemory
raw_buffer = adapter.buffer_memory

# Load existing data from BufferMemory
adapter.load_from_buffer("s1")
```

**Limitations**:
- No semantic search (keyword only)
- No summarization support
- Single-tier storage only

### HierarchicalMemory

Multi-tier memory with automatic promotion/demotion:

```python
from kaizen.memory.providers import (
    HierarchicalMemory,
    MemoryEntry,
    RetrievalStrategy,
)

# Basic usage (hot tier only)
memory = HierarchicalMemory(hot_size=1000)

# With database persistence (warm tier)
from kaizen.memory.providers import DataFlowMemoryBackend
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class MemoryEntryModel:
    id: str
    session_id: str
    content: str
    role: str
    timestamp: str
    source: str
    importance: float
    tags: str
    metadata: str
    embedding: Optional[str] = None

warm_backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")

memory = HierarchicalMemory(
    hot_size=1000,
    warm_backend=warm_backend,
    promotion_threshold=0.7,  # Entries with importance >= 0.7 go to hot tier
    demotion_age_hours=24,    # Inactive entries demoted after 24h
)

# With embedding provider for semantic search
def embed(text: str) -> List[float]:
    # Your embedding function (OpenAI, local model, etc.)
    return embedding_model.encode(text).tolist()

memory = HierarchicalMemory(
    hot_size=1000,
    embedding_provider=embed,
)

# With summarizer for context overflow
def summarize(entries: List[MemoryEntry]) -> str:
    # Your summarization function
    texts = [e.content for e in entries]
    return summarization_model.summarize(texts)

memory = HierarchicalMemory(
    hot_size=1000,
    summarizer=summarize,
)

# Store entries (automatically routed by importance)
high_importance = MemoryEntry(
    content="Critical user preference",
    session_id="s1",
    importance=0.9,  # Goes to hot tier
)
await memory.store(high_importance)

low_importance = MemoryEntry(
    content="Minor note",
    session_id="s1",
    importance=0.3,  # Goes to warm tier (if available)
)
await memory.store(low_importance)

# Recall from all tiers (parallel retrieval)
entries = await memory.recall(
    query="preferences",
    session_id="s1",
    max_entries=20,
)

# Build context with strategy
context = await memory.build_context(
    query="user preferences",
    session_id="s1",
    max_tokens=4000,
    strategy=RetrievalStrategy.HYBRID,
)

# Check tier availability
print(f"Hot tier: always enabled")
print(f"Warm tier: {memory.has_warm_tier}")
print(f"Cold tier: {memory.has_cold_tier}")
print(f"Embeddings: {memory.has_embeddings}")
```

**Features**:
- **Automatic tier management**: High-importance entries in hot tier, others in warm
- **Parallel retrieval**: Queries all tiers concurrently
- **Token-aware context**: Respects token budget with overflow summarization
- **Multiple strategies**: Recency, importance, relevance, hybrid

### DataFlowMemoryBackend

Database persistence using Kailash DataFlow:

```python
from dataflow import DataFlow
from kaizen.memory.providers import DataFlowMemoryBackend, MemoryEntry
from typing import Optional

# Setup database
db = DataFlow("postgresql://user:pass@localhost:5432/memory")

# Define model (required schema)
@db.model
class MemoryEntryModel:
    id: str
    session_id: str
    content: str
    role: str
    timestamp: str  # ISO format
    source: str
    importance: float
    tags: str       # JSON array
    metadata: str   # JSON object
    embedding: Optional[str] = None  # JSON array

# Create backend
backend = DataFlowMemoryBackend(db, model_name="MemoryEntryModel")

# Store single entry
entry = MemoryEntry(content="Hello", session_id="s1")
entry_id = backend.store(entry)

# Store multiple entries (bulk operation)
entries = [MemoryEntry(content=f"Msg {i}", session_id="s1") for i in range(10)]
ids = backend.store_many(entries)

# Retrieve by ID
entry = backend.get("entry-id")

# List entries with filters
entries = backend.list_entries(
    session_id="s1",
    filters={"source": "conversation", "min_importance": 0.5},
    limit=100,
    offset=0,
    order_by="timestamp",
    ascending=False,
)

# Keyword search
matches = backend.search(
    query="hello",
    session_id="s1",
    limit=10,
)

# Count entries
count = backend.count(session_id="s1")

# Delete entries
backend.delete("entry-id")  # Single entry
backend.delete_many(session_id="s1")  # By session
backend.delete_many(before=datetime.now() - timedelta(days=30))  # By age
```

## Retrieval Strategies

### Recency Strategy

Returns newest entries first:

```python
context = await memory.build_context(
    session_id="s1",
    strategy=RetrievalStrategy.RECENCY,
)
# Entries sorted by timestamp descending
```

### Importance Strategy

Returns highest-importance entries first:

```python
context = await memory.build_context(
    session_id="s1",
    strategy=RetrievalStrategy.IMPORTANCE,
)
# Entries sorted by importance descending
```

### Relevance Strategy

Returns entries most relevant to query (requires embedding provider):

```python
memory = HierarchicalMemory(embedding_provider=embed_function)

context = await memory.build_context(
    query="user preferences for UI",
    session_id="s1",
    strategy=RetrievalStrategy.RELEVANCE,
)
# Entries sorted by cosine similarity to query embedding
```

**Note**: Falls back to recency if no embedding provider is configured.

### Hybrid Strategy

Weighted combination of all factors:

```python
context = await memory.build_context(
    query="user preferences",
    session_id="s1",
    strategy=RetrievalStrategy.HYBRID,
)
# Score = 0.4 * recency + 0.3 * importance + 0.3 * relevance
```

## Token-Aware Context Building

Context building respects token budgets:

```python
# 70% of budget for entries, 30% for summary
context = await memory.build_context(
    session_id="s1",
    max_tokens=4000,  # Total budget
)

# If entries exceed budget:
# 1. Most relevant entries included up to 70% budget
# 2. Overflow entries summarized (if summarizer provided)
# 3. Summary uses remaining 30% budget

print(f"Entries: {context.entries_retrieved}")
print(f"Summarized: {context.entries_summarized}")
print(f"Tokens used: {context.total_tokens}")
```

## Integration with LocalKaizenAdapter

The Memory Provider integrates with LocalKaizenAdapter for autonomous agent memory:

```python
from kaizen.runtime import LocalKaizenAdapter
from kaizen.memory.providers import HierarchicalMemory

# Create memory provider
memory = HierarchicalMemory(
    hot_size=1000,
    embedding_provider=embed_function,
    summarizer=summarize_function,
)

# Use with LocalKaizenAdapter
adapter = LocalKaizenAdapter(
    memory_provider=memory,
    # ... other config
)

# Memory operations happen automatically during agent execution
# The adapter uses build_context() to provide conversation history
# and stores new entries after each turn
```

## Custom Provider Implementation

Implement your own provider:

```python
from kaizen.memory.providers import (
    MemoryProvider,
    MemoryEntry,
    MemoryContext,
    RetrievalStrategy,
)


class RedisMemoryProvider(MemoryProvider):
    """Redis-backed memory provider."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def store(self, entry: MemoryEntry) -> str:
        # Store in Redis
        key = f"memory:{entry.session_id}:{entry.id}"
        await self.redis.set(key, entry.to_dict())
        return entry.id

    async def recall(
        self,
        query: str = "",
        session_id: str = "",
        max_entries: int = 10,
        filters=None,
    ) -> List[MemoryEntry]:
        # Retrieve from Redis
        pattern = f"memory:{session_id}:*"
        keys = await self.redis.keys(pattern)
        entries = []
        for key in keys[:max_entries]:
            data = await self.redis.get(key)
            entries.append(MemoryEntry.from_dict(data))
        return entries

    async def build_context(
        self,
        query: str = "",
        session_id: str = "",
        max_tokens: int = 4000,
        strategy: RetrievalStrategy = RetrievalStrategy.RECENCY,
    ) -> MemoryContext:
        entries = await self.recall(query, session_id)
        # Sort by strategy
        # Apply token budget
        # Return context
        return MemoryContext(entries=entries, ...)

    async def summarize(self, session_id="", entries=None) -> str:
        return ""  # No summarization

    async def forget(
        self,
        entry_id=None,
        session_id=None,
        before=None,
    ) -> int:
        # Delete from Redis
        if entry_id:
            key = f"memory:*:{entry_id}"
            keys = await self.redis.keys(key)
            await self.redis.delete(*keys)
            return len(keys)
        # ... handle session_id and before
        return 0
```

## Error Handling

The provider defines specific error types:

```python
from kaizen.memory.providers import (
    MemoryProviderError,      # Base error
    MemoryStorageError,       # Store operation failed
    MemoryRetrievalError,     # Recall/get failed
    MemoryContextError,       # Context building failed
    MemorySummarizationError, # Summarization failed
    MemoryDeletionError,      # Forget/clear failed
)

try:
    await memory.store(entry)
except MemoryStorageError as e:
    logger.error(f"Failed to store entry: {e}")

try:
    context = await memory.build_context(session_id="s1")
except MemoryContextError as e:
    logger.error(f"Failed to build context: {e}")
    # Fall back to empty context
    context = MemoryContext()
```

## Best Practices

### 1. Session Management

Always scope operations to sessions:

```python
# Good: Session-scoped operations
entries = await memory.recall(session_id="user-123")
context = await memory.build_context(session_id="user-123")

# Bad: Global operations (may be slow, return mixed data)
entries = await memory.recall()  # All sessions!
```

### 2. Importance Scoring

Use meaningful importance scores:

```python
# System messages: lower importance
system_entry = MemoryEntry(
    content="Session started",
    importance=0.2,
    source=MemorySource.SYSTEM,
)

# User preferences: higher importance
preference_entry = MemoryEntry(
    content="User prefers dark mode",
    importance=0.9,
    source=MemorySource.LEARNED,
)
```

### 3. Token Budgets

Leave room for new content:

```python
# Reserve tokens for new response
max_context_tokens = model_context_window - expected_response_length - prompt_tokens

context = await memory.build_context(
    max_tokens=max_context_tokens,
)
```

### 4. Cleanup Old Entries

Regularly clean up old entries:

```python
from datetime import datetime, timezone, timedelta

# Delete entries older than 30 days
cutoff = datetime.now(timezone.utc) - timedelta(days=30)
deleted = await memory.forget(before=cutoff)
print(f"Cleaned up {deleted} old entries")
```

### 5. Use Tags for Organization

Tag entries for better filtering:

```python
entry = MemoryEntry(
    content="User wants email notifications",
    tags=["preference", "notification", "email"],
)

# Later: recall by tag
entries = await memory.recall(
    filters={"tags": {"$contains": "preference"}},
)
```

## Testing

Unit tests for memory providers:

```python
import pytest
from kaizen.memory.providers import (
    HierarchicalMemory,
    MemoryEntry,
    RetrievalStrategy,
)


@pytest.mark.asyncio
async def test_store_and_recall():
    memory = HierarchicalMemory()

    entry = MemoryEntry(content="Test", session_id="s1")
    await memory.store(entry)

    entries = await memory.recall(session_id="s1")
    assert len(entries) == 1
    assert entries[0].content == "Test"


@pytest.mark.asyncio
async def test_build_context_token_budget():
    memory = HierarchicalMemory()

    # Add many entries
    for i in range(100):
        await memory.store(MemoryEntry(
            content="A" * 100,  # ~25 tokens each
            session_id="s1",
        ))

    context = await memory.build_context(
        session_id="s1",
        max_tokens=100,
    )

    assert context.total_tokens <= 100
```

## See Also

- [Native Tools Guide](00-native-tools-guide.md) - Tool system for autonomous agents
- [Runtime Abstraction Guide](01-runtime-abstraction-guide.md) - Multi-LLM runtime support
- [LocalKaizenAdapter Guide](02-local-kaizen-adapter-guide.md) - TAOD loop implementation

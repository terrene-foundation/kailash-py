# Memory Provider Interface Developer Guide

The Memory Provider Interface (TODO-193) provides a standardized way to manage agent memory across different storage backends and access patterns.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent Execution                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   MemoryProvider ABC                         │
│  store() | recall() | build_context() | summarize() | forget()│
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│BufferMemory   │    │Hierarchical   │    │ Custom        │
│(backward compat)│  │Memory         │    │ Providers     │
└───────────────┘    │(Hot/Warm/Cold)│    └───────────────┘
                     └───────────────┘
                              │
                     ┌────────┼────────┐
                     ▼        ▼        ▼
                  ┌─────┐ ┌──────┐ ┌──────┐
                  │ Hot │ │ Warm │ │ Cold │
                  └─────┘ └──────┘ └──────┘
```

## Core Types

### MemoryEntry

Represents a single memory item:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    content: str
    entry_type: str  # "message", "tool_result", "observation", "summary"
    timestamp: datetime
    importance: float = 0.5  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Access tracking
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    # Relationships
    parent_id: Optional[str] = None
    session_id: Optional[str] = None
```

### MemoryContext

Context built from memories for LLM:

```python
@dataclass
class MemoryContext:
    """Context built from memories."""

    entries: List[MemoryEntry]
    summary: Optional[str] = None
    total_tokens: int = 0
    truncated: bool = False

    def to_prompt(self) -> str:
        """Convert to prompt string."""
        parts = []
        if self.summary:
            parts.append(f"Summary of previous context:\n{self.summary}\n")
        for entry in self.entries:
            parts.append(f"[{entry.entry_type}] {entry.content}")
        return "\n".join(parts)
```

## MemoryProvider ABC

Abstract base class for all memory providers:

```python
from abc import ABC, abstractmethod

class MemoryProvider(ABC):
    """Abstract base for memory providers."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry. Returns entry ID."""
        ...

    @abstractmethod
    async def recall(
        self,
        query: str,
        limit: int = 10,
        session_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """Recall relevant memories."""
        ...

    @abstractmethod
    async def build_context(
        self,
        session_id: str,
        max_tokens: int = 4000,
    ) -> MemoryContext:
        """Build context for LLM from memories."""
        ...

    @abstractmethod
    async def summarize(
        self,
        session_id: str,
    ) -> str:
        """Generate summary of session memories."""
        ...

    @abstractmethod
    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        """Remove memories. Returns count deleted."""
        ...
```

## BufferMemoryAdapter

Simple in-memory buffer with backward compatibility:

```python
from kaizen.runtime.memory import BufferMemoryAdapter

# Create buffer with size limit
memory = BufferMemoryAdapter(max_entries=100)

# Store entry
entry = MemoryEntry(
    id="entry-1",
    content="User asked about Python",
    entry_type="message",
    timestamp=datetime.now(),
)
await memory.store(entry)

# Recall recent entries
entries = await memory.recall("Python", limit=5)

# Build context
context = await memory.build_context(session_id="session-1", max_tokens=4000)
print(context.to_prompt())
```

### Configuration

```python
memory = BufferMemoryAdapter(
    max_entries=100,      # Maximum entries to keep
    eviction_policy="lru", # "lru", "fifo", or "importance"
)
```

## HierarchicalMemory

Advanced memory with hot/warm/cold tiers:

```python
from kaizen.runtime.memory import HierarchicalMemory

memory = HierarchicalMemory(
    hot_capacity=100,     # Immediate access
    warm_capacity=1000,   # Fast access
    cold_capacity=10000,  # Slower but persistent
    storage_path="./memory",  # Persistence location
)
```

### Memory Tiers

| Tier | Access Pattern | Retention | Storage |
|------|----------------|-----------|---------|
| Hot | Immediate | Current session | In-memory |
| Warm | Fast | Hours to days | In-memory + file |
| Cold | Slower | Permanent | File/database |

### Tier Movement

Entries move between tiers based on access patterns:

```
New Entry → Hot
                ↓ (time decay)
            Warm
                ↓ (further decay)
            Cold

Recall → Entry moves up (Hot)
```

### Usage

```python
# Store with automatic tier selection
await memory.store(entry)  # Goes to Hot

# Recall (promotes accessed entries)
entries = await memory.recall("query")
# Accessed entries move to Hot tier

# Build context (uses all tiers)
context = await memory.build_context(
    session_id="session-1",
    max_tokens=4000,
)

# Force tier (advanced)
await memory.store(entry, tier="warm")
```

### Persistence

```python
# Memory persists automatically
memory = HierarchicalMemory(storage_path="./memory")

# Explicit save
await memory.persist()

# Load from disk
memory = await HierarchicalMemory.load("./memory")
```

## Building Context

### Token-Aware Context Building

```python
# Build context within token limit
context = await memory.build_context(
    session_id="session-1",
    max_tokens=4000,
)

if context.truncated:
    print(f"Context truncated to {context.total_tokens} tokens")
    print(f"Summary: {context.summary}")
```

### Priority-Based Selection

The context builder prioritizes:

1. **High importance entries** - User-marked or system-flagged
2. **Recent entries** - More relevant to current task
3. **Frequently accessed** - Likely important
4. **Related entries** - Semantic similarity to current task

### Custom Context Building

```python
# Get specific entry types
context = await memory.build_context(
    session_id="session-1",
    max_tokens=4000,
    entry_types=["message", "tool_result"],  # Exclude observations
)

# Include cross-session context
context = await memory.build_context(
    session_id="session-1",
    max_tokens=4000,
    include_related_sessions=True,
)
```

## Memory Summarization

### Automatic Summarization

```python
# Generate summary when context is too large
summary = await memory.summarize(session_id="session-1")
print(summary)
# "User is building a Python web application with FastAPI.
#  They've asked about routing, middleware, and database integration.
#  Current focus is on authentication implementation."
```

### Configuring Summarization

```python
memory = HierarchicalMemory(
    summarize_threshold=5000,  # Tokens before summarizing
    summarize_model="gpt-4o-mini",  # Model for summarization
    summarize_prompt="Summarize the key points...",
)
```

## Memory Lifecycle

### Forgetting

```python
# Forget specific entry
await memory.forget(entry_id="entry-123")

# Forget entire session
await memory.forget(session_id="session-1")

# Forget old entries
from datetime import datetime, timedelta
cutoff = datetime.now() - timedelta(days=30)
count = await memory.forget(before=cutoff)
print(f"Forgot {count} old entries")
```

### Importance Decay

Importance naturally decays over time:

```python
memory = HierarchicalMemory(
    importance_decay_rate=0.01,  # Per hour
    min_importance=0.1,  # Never drop below this
)
```

## Integration with Agents

### Using Memory with Agent

```python
from kaizen.agent import Agent
from kaizen.runtime.memory import HierarchicalMemory

memory = HierarchicalMemory(storage_path="./agent_memory")

agent = Agent(
    memory_depth="persistent",
    memory_provider=memory,
)

# Memory is used automatically
await agent.run("My project is called 'Acme'")
await agent.run("What is my project called?")  # "Your project is called 'Acme'"
```

### Memory in TAOD Loop

The LocalKaizenAdapter uses memory in each cycle:

```
Think:
  1. Recall relevant memories
  2. Build context from memories
  3. Include context in LLM prompt

Observe:
  1. Store observations as memories
  2. Update entry importance
  3. Trigger summarization if needed
```

## Custom Memory Provider

### Step 1: Implement Provider

```python
from kaizen.runtime.memory import MemoryProvider, MemoryEntry, MemoryContext

class RedisMemoryProvider(MemoryProvider):
    """Redis-backed memory provider."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client = None

    async def _ensure_connected(self):
        if self._client is None:
            import aioredis
            self._client = await aioredis.from_url(self.redis_url)

    async def store(self, entry: MemoryEntry) -> str:
        await self._ensure_connected()
        key = f"memory:{entry.session_id}:{entry.id}"
        await self._client.hset(key, mapping={
            "content": entry.content,
            "entry_type": entry.entry_type,
            "timestamp": entry.timestamp.isoformat(),
            "importance": str(entry.importance),
        })
        return entry.id

    async def recall(
        self,
        query: str,
        limit: int = 10,
        session_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        await self._ensure_connected()
        # Implement semantic search or pattern matching
        pattern = f"memory:{session_id or '*'}:*"
        keys = await self._client.keys(pattern)
        entries = []
        for key in keys[:limit]:
            data = await self._client.hgetall(key)
            entries.append(self._parse_entry(key, data))
        return entries

    async def build_context(
        self,
        session_id: str,
        max_tokens: int = 4000,
    ) -> MemoryContext:
        entries = await self.recall("", limit=100, session_id=session_id)
        # Token-aware selection
        selected = self._select_within_limit(entries, max_tokens)
        return MemoryContext(entries=selected)

    async def summarize(self, session_id: str) -> str:
        entries = await self.recall("", limit=50, session_id=session_id)
        # Use LLM to summarize
        return await self._generate_summary(entries)

    async def forget(
        self,
        entry_id: Optional[str] = None,
        session_id: Optional[str] = None,
        before: Optional[datetime] = None,
    ) -> int:
        await self._ensure_connected()
        count = 0
        # Implement deletion logic
        return count
```

### Step 2: Use with Agent

```python
memory = RedisMemoryProvider("redis://localhost:6379")

agent = Agent(
    memory_depth="persistent",
    memory_provider=memory,
)
```

## Testing Memory Providers

```python
import pytest
from kaizen.runtime.memory import HierarchicalMemory, MemoryEntry
from datetime import datetime

@pytest.fixture
def memory():
    return HierarchicalMemory(
        hot_capacity=10,
        warm_capacity=50,
        cold_capacity=100,
    )

@pytest.mark.asyncio
async def test_store_and_recall(memory):
    entry = MemoryEntry(
        id="test-1",
        content="Test content about Python",
        entry_type="message",
        timestamp=datetime.now(),
    )

    await memory.store(entry)
    recalled = await memory.recall("Python")

    assert len(recalled) == 1
    assert recalled[0].content == "Test content about Python"

@pytest.mark.asyncio
async def test_context_building(memory):
    for i in range(20):
        await memory.store(MemoryEntry(
            id=f"entry-{i}",
            content=f"Message {i}",
            entry_type="message",
            timestamp=datetime.now(),
            session_id="session-1",
        ))

    context = await memory.build_context("session-1", max_tokens=100)
    assert context.total_tokens <= 100
```

## Best Practices

1. **Choose the right provider** - BufferMemory for simple, HierarchicalMemory for complex
2. **Set appropriate capacities** - Balance memory usage vs context quality
3. **Use importance wisely** - Mark critical entries as high importance
4. **Summarize regularly** - Keeps context manageable
5. **Clean up old data** - Use forget() to manage storage
6. **Test token limits** - Ensure context fits in LLM context window

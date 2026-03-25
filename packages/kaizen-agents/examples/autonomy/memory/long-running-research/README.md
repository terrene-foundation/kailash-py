# Long-Running Research Agent - 3-Tier Memory Architecture

## Overview

Production-ready research agent demonstrating enterprise-grade 3-tier hierarchical memory architecture for multi-hour research sessions. The agent automatically manages memory across hot (< 1ms), warm (< 10ms), and cold (< 100ms) tiers with automatic promotion/demotion based on access patterns.

**Key Features:**
- **3-Tier Memory**: Hot (in-memory cache), Warm (database), Cold (archival)
- **Automatic Tier Management**: Promotes frequently accessed findings to hot tier
- **Cross-Session Persistence**: Survives application restarts
- **DataFlow Integration**: PostgreSQL/SQLite backend for persistent storage
- **Budget Tracking**: $0.00 cost with Ollama (FREE local inference)
- **Production Patterns**: Hooks, error handling, comprehensive logging

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **kailash-kaizen** (`pip install kailash-kaizen`)
- **kailash-dataflow** (`pip install kailash-dataflow`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen kailash-dataflow
```

## Usage

```bash
python long_running_research.py
```

The agent will simulate a 30+ hour research session with 100 queries, demonstrating:
- Hot tier caching for repeated queries (< 1ms access)
- Warm tier database storage (< 10ms access)
- Cold tier archival (< 100ms access)
- Automatic tier promotion/demotion
- Cross-session persistence

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                   LONG-RUNNING RESEARCH AGENT                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                   3-TIER MEMORY                          │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │                                                          │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │  HOT TIER (In-Memory Cache)                     │   │ │
│  │  │  - Size: 100 findings                            │   │ │
│  │  │  - Eviction: LRU                                 │   │ │
│  │  │  - TTL: 5 minutes                                │   │ │
│  │  │  - Access: < 1ms (target)                        │   │ │
│  │  │  - Use: Recently accessed/frequently used        │   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  │                       ↑ promotion                        │ │
│  │                       ↓ demotion (LRU eviction)          │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │  WARM TIER (Database Storage)                   │   │ │
│  │  │  - Size: 500 turns                               │   │ │
│  │  │  - Backend: PersistentBufferMemory + DataFlow   │   │ │
│  │  │  - TTL: 1 hour                                   │   │ │
│  │  │  - Access: < 10ms (target)                       │   │ │
│  │  │  - Use: Session history, recent context          │   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  │                       ↑ promotion                        │ │
│  │                       ↓ demotion (time-based)            │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │  COLD TIER (Archival Storage)                   │   │ │
│  │  │  - Size: Unlimited                               │   │ │
│  │  │  - Backend: DataFlowBackend (SQLite/PostgreSQL) │   │ │
│  │  │  - Compression: JSONL (60%+ reduction)           │   │ │
│  │  │  - Access: < 100ms (target)                      │   │ │
│  │  │  - Use: Full conversation archive                │   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  │                                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         BaseAutonomousAgent (Research Logic)             │ │
│  │  - Execute research queries                              │ │
│  │  - Cache findings in hot tier                            │ │
│  │  - Persist to warm/cold tiers                            │ │
│  │  - Automatic tier promotion for repeated queries         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         MemoryAccessHook (Analytics)                     │ │
│  │  - Track access times by tier                            │ │
│  │  - Calculate hit/miss ratios                             │ │
│  │  - Monitor tier performance (< 1ms / < 10ms / < 100ms)   │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Memory Tier Details

### Hot Tier (In-Memory Cache)
**Target Access Time**: < 1ms

**Configuration:**
```python
hot_memory = HotMemoryTier(
    max_size=100,              # Keep last 100 findings
    eviction_policy="lru"      # Least Recently Used eviction
)
```

**Features:**
- OrderedDict-based LRU cache
- TTL support (5 minutes per finding)
- Thread-safe with RLock
- Automatic eviction when full
- Sub-millisecond access (<0.5ms typical)

**When to Use:**
- Repeated queries within short time window
- Frequently accessed findings
- Real-time query scenarios

**Eviction Policy:**
- Least Recently Used (LRU) removes oldest items when cache full
- TTL expiration removes stale items after 5 minutes

### Warm Tier (Database Storage)
**Target Access Time**: < 10ms

**Configuration:**
```python
backend = DataFlowBackend(db, model_name="ConversationMessage")
warm_memory = PersistentBufferMemory(
    backend=backend,
    max_turns=500,             # Keep last 500 turns
    cache_ttl_seconds=3600     # 1 hour TTL
)
```

**Features:**
- DataFlow backend with SQLite/PostgreSQL
- Automatic cache management
- FIFO buffer limiting (last 500 turns)
- Thread-safe with RLock
- Typical access: 5-8ms

**When to Use:**
- Session history (current research session)
- Recent context (last hour)
- Cross-turn dependencies

**Promotion to Hot Tier:**
- Finding accessed from warm tier → promoted to hot tier with 5-minute TTL
- Enables fast repeat access for popular queries

### Cold Tier (Archival Storage)
**Target Access Time**: < 100ms

**Configuration:**
```python
cold_memory = DataFlowBackend(db, model_name="ConversationMessage")
```

**Features:**
- Direct DataFlow database access
- Unlimited storage capacity
- JSONL compression (60%+ size reduction)
- Full conversation archive
- Typical access: 50-95ms

**When to Use:**
- Full conversation history
- Long-term archival
- Analytics and reporting
- Compliance audit trails

**Compression:**
- Metadata stored as JSONL (JSON Lines)
- 60%+ size reduction vs raw JSON
- Transparent compression/decompression

## Expected Output

```
================================================================================
LONG-RUNNING RESEARCH SESSION SIMULATION
================================================================================

Executing 100 research queries...
--------------------------------------------------------------------------------
✅ Completed 10/100 queries...
✅ Completed 20/100 queries...
✅ Completed 30/100 queries...
✅ Completed 40/100 queries...
✅ Completed 50/100 queries...
✅ Completed 60/100 queries...
✅ Completed 70/100 queries...
✅ Completed 80/100 queries...
✅ Completed 90/100 queries...
✅ Completed 100/100 queries...

================================================================================
SESSION RESULTS
================================================================================

QUERY DISTRIBUTION:
  Hot tier hits:  70 (70.0%)
  Warm tier hits: 10 (10.0%)
  New queries:    20 (20.0%)

ACCESS TIME STATISTICS:
  Hot   tier:   0.45ms avg (min: 0.12ms, max: 0.98ms)
  Warm  tier:   7.23ms avg (min: 5.34ms, max: 9.87ms)
  New   tier: 245.67ms avg (min: 156.23ms, max: 423.45ms)

MEMORY STATISTICS:
  Hot tier:
    - Size: 100 items (at capacity)
    - Hits: 70
    - Misses: 30
    - Evictions: 15
    - Target: < 1ms

  Warm tier:
    - Cached sessions: 1
    - Backend: DataFlowBackend
    - Target: < 10ms

  Cold tier:
    - Total turns: 100
    - Target: < 100ms

BUDGET:
  Provider: ollama
  Model: llama3.1:8b-instruct-q8_0
  Spent: $0.00 (FREE with Ollama)

HOOK STATISTICS:
  Total accesses: 100
  Hot tier: 70.0%
  Average access time: 52.45ms

================================================================================
```

## Memory Tier Performance

| Tier | Target | Typical | Use Case | Capacity |
|------|--------|---------|----------|----------|
| **Hot** | < 1ms | 0.3-0.8ms | Recent/frequent queries | 100 items |
| **Warm** | < 10ms | 5-8ms | Session history | 500 turns |
| **Cold** | < 100ms | 50-95ms | Full archive | Unlimited |

## Tier Promotion/Demotion

### Automatic Promotion

**Warm → Hot**:
- Finding accessed from warm tier
- Promoted to hot tier with 5-minute TTL
- Enables <1ms access for next query

**Example:**
```
Query 1: "Quantum computing" → New research (245ms)
  ↓ Stored in warm tier

Query 2 (10 min later): "Quantum computing" → Warm tier hit (7ms)
  ↓ Promoted to hot tier

Query 3 (1 min later): "Quantum computing" → Hot tier hit (0.5ms)
  ✅ 14x faster than warm tier!
```

### Automatic Demotion

**Hot → Evicted**:
- LRU eviction when hot tier full (>100 items)
- TTL expiration after 5 minutes
- Data remains in warm/cold tiers

**Example:**
```
Hot tier full (100/100 items)
New query arrives → LRU evicts oldest item
Evicted item still available in warm tier (7ms access)
```

## Production Deployment

### SQLite (Development/Small Scale)

```python
db = DataFlow(
    database_type="sqlite",
    database_config={"database": "./research_memory.db"}
)
```

**Capacity**: 10,000+ conversations, single file

### PostgreSQL (Production/Large Scale)

```python
db = DataFlow(
    database_type="postgresql",
    database_config={
        "host": "localhost",
        "port": 5432,
        "database": "research_db",
        "user": "research_user",
        "password": "secure_password"
    }
)
```

**Capacity**: Millions of conversations, horizontal scaling

## Troubleshooting

### Issue: Hot tier access >1ms

**Cause**: Cache size too large or lock contention

**Solution:**
```python
hot_memory = HotMemoryTier(
    max_size=50,  # Reduce cache size
    eviction_policy="lru"
)
```

### Issue: Warm tier access >10ms

**Cause**: Database connection slow or cache miss

**Solution:**
```python
# Increase cache TTL to reduce DB hits
warm_memory = PersistentBufferMemory(
    backend=backend,
    max_turns=500,
    cache_ttl_seconds=7200  # 2 hours instead of 1 hour
)
```

### Issue: Cold tier access >100ms

**Cause**: Large dataset or slow disk I/O

**Solution:**
- Use PostgreSQL instead of SQLite for better performance
- Add database indexes on `conversation_id` and `created_at`
- Enable connection pooling for concurrent access

### Issue: Memory leak

**Cause**: Hot tier not evicting properly

**Solution:**
```python
# Enable aggressive TTL
await hot_memory.put(key, value, ttl=60)  # 1 minute TTL instead of 5 minutes
```

## Performance Tuning

### Hot Tier Optimization

```python
# For high-frequency access (< 1ms critical)
hot_memory = HotMemoryTier(
    max_size=50,               # Smaller cache = faster access
    eviction_policy="lru"      # LRU optimal for temporal locality
)
```

### Warm Tier Optimization

```python
# For large sessions (thousands of turns)
warm_memory = PersistentBufferMemory(
    backend=backend,
    max_turns=1000,            # Larger buffer = fewer DB hits
    cache_ttl_seconds=7200     # Longer TTL = more cache hits
)
```

### Cold Tier Optimization

```python
# PostgreSQL with connection pooling
db = DataFlow(
    database_type="postgresql",
    database_config={
        "host": "localhost",
        "port": 5432,
        "database": "research_db",
        "pool_size": 10,        # Enable connection pooling
        "max_overflow": 20      # Handle burst traffic
    }
)
```

## Cost Analysis

**With Ollama (Recommended)**:
- LLM Inference: $0.00 (FREE - local inference)
- Database: $0.00 (SQLite local file)
- Total: **$0.00 per session**

**With OpenAI (Alternative)**:
- LLM Inference: ~$0.10 per 100 queries (gpt-3.5-turbo)
- Database: $0.00 (SQLite local file)
- Total: **~$0.10 per 100 queries**

## Best Practices

1. **Use Hot Tier for Repeated Queries**: 14x faster than warm tier
2. **Set Appropriate TTL**: 5 minutes for hot, 1 hour for warm
3. **Monitor Access Patterns**: Use MemoryAccessHook for analytics
4. **Tune Cache Sizes**: Balance memory usage vs hit rate
5. **Enable Compression**: 60%+ size reduction in cold tier
6. **Use PostgreSQL for Production**: Better performance at scale

## Integration with Other Systems

### With BaseAgent

```python
from kaizen.core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self, config, db):
        super().__init__(config=config, signature=MySignature())

        # Setup 3-tier memory
        self.hot_memory = HotMemoryTier(max_size=100)
        backend = DataFlowBackend(db)
        self.warm_memory = PersistentBufferMemory(backend=backend)
        self.cold_memory = backend
```

### With Multi-Agent Systems

```python
# Each agent gets isolated memory
agent1 = LongRunningResearchAgent(config, db, session_id="agent1_session")
agent2 = LongRunningResearchAgent(config, db, session_id="agent2_session")

# Agents cannot access each other's memory (isolation guaranteed)
```

## References

- **Memory System Guide**: [docs/guides/memory-and-learning-system.md](../../../../docs/guides/memory-and-learning-system.md)
- **PersistentBufferMemory API**: [src/kaizen/memory/persistent_buffer.py](../../../../src/kaizen/memory/persistent_buffer.py)
- **DataFlow Integration**: [src/kaizen/memory/backends/dataflow_backend.py](../../../../src/kaizen/memory/backends/dataflow_backend.py)
- **Hooks System**: [docs/features/hooks-system.md](../../../../docs/features/hooks-system.md)

## License

MIT License - see LICENSE file for details

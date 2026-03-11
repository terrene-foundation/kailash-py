# Memory E2E Tests

Tier 3 E2E tests for Kaizen's 3-tier memory architecture with real infrastructure.

## Test Coverage

### Tests 22-23: Hot Tier (In-Memory Cache)
**File**: `test_hot_tier_e2e.py`

- **Test 22**: Hot memory operations (add, retrieve, search, update)
  - Validates in-memory cache operations
  - Fast retrieval (<1ms)
  - Thread-safe concurrent access

- **Test 23**: Hot memory eviction policy (LRU)
  - Validates LRU eviction when capacity reached
  - Capacity limits enforcement
  - Eviction statistics tracking

**Infrastructure**: In-memory only (no external dependencies)
**Duration**: 10-20s each

### Test 24: Warm Tier (Redis)
**File**: `test_warm_tier_e2e.py`

- **Test 24**: Warm memory with real Redis instance
  - Validates Redis persistence (<10ms access)
  - TTL expiration handling
  - Access pattern tracking

**Infrastructure**: Redis (if available, otherwise skip gracefully)
**Duration**: 15-30s
**Note**: Test skips if Redis not available

### Test 25: Cold Tier (PostgreSQL)
**File**: `test_cold_tier_e2e.py`

- **Test 25**: Cold memory persistence with PostgreSQL
  - Validates DataFlow backend integration
  - Database persistence across sessions
  - Large data handling

**Infrastructure**: Real PostgreSQL via DataFlow
**Duration**: 20-40s

### Tests 26-28: Persistence & Tier Management
**File**: `test_persistence_e2e.py`

- **Test 26**: Memory persistence across agent restarts
  - Same session_id retrieves stored memories
  - Cache invalidation forces database load
  - Metadata preservation

- **Test 27**: Memory tier promotion (hot ← warm ← cold)
  - Frequent access promotes to hot tier
  - Access pattern tracking
  - Automatic promotion based on thresholds

- **Test 28**: Memory tier demotion (hot → warm → cold)
  - Infrequent access demotes to lower tiers
  - Age-based demotion policies
  - Tier statistics validation

**Infrastructure**: PostgreSQL + in-memory cache
**Duration**: 30-60s each

## Architecture

### 3-Tier Memory System

```
┌─────────────────────────────────────────┐
│         Hot Tier (In-Memory)            │
│  - <1ms access time                     │
│  - LRU/LFU/FIFO eviction                │
│  - Thread-safe OrderedDict              │
│  - Max capacity enforcement             │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│       Warm Tier (Redis - Optional)      │
│  - <10ms access time                    │
│  - SQLite persistence                   │
│  - TTL support                          │
│  - Access tracking                      │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│      Cold Tier (PostgreSQL/SQLite)      │
│  - <50ms access time                    │
│  - DataFlow backend                     │
│  - Full persistence                     │
│  - Unlimited capacity                   │
└─────────────────────────────────────────┘
```

### Tier Manager

Orchestrates data movement between tiers based on:
- **Access frequency**: Hot data stays in hot tier
- **Access recency**: Recent access prevents demotion
- **Capacity constraints**: LRU eviction when full
- **TTL policies**: Automatic expiration
- **Size heuristics**: Large data prefers cold tier

## Requirements

### Infrastructure
- **Ollama**: Running locally with llama3.1:8b-instruct-q8_0 model (FREE)
- **PostgreSQL/SQLite**: Via DataFlow (local, free)
- **Redis**: Optional (test skips if unavailable)

### Test Environment
```bash
# Check Ollama
ollama list | grep llama3.1:8b-instruct-q8_0

# Run tests
pytest tests/e2e/autonomy/memory/ -v

# Run specific test
pytest tests/e2e/autonomy/memory/test_hot_tier_e2e.py::test_hot_memory_operations -v
```

## Budget & Performance

- **Total Cost**: $0.00 (100% Ollama + local infrastructure)
- **Total Duration**: ~2-4 minutes (7 tests)
- **NO MOCKING**: All tests use real infrastructure

## Test Patterns

### Standard E2E Pattern
```python
import pytest
from kaizen.memory.tiers import HotMemoryTier
from tests.utils.cost_tracking import get_global_tracker

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]

@pytest.mark.timeout(30)
async def test_hot_memory_operations():
    """Test 22: Hot memory operations."""
    cost_tracker = get_global_tracker()

    # Create hot tier
    hot_tier = HotMemoryTier(max_size=100, eviction_policy="lru")

    # Add memory entry
    await hot_tier.put("key1", {"content": "test"})

    # Retrieve from hot tier
    result = await hot_tier.get("key1")
    assert result["content"] == "test"

    # Track cost (no LLM used for basic memory ops)
    cost_tracker.track_usage(
        test_name="test_hot_memory_operations",
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        input_tokens=0,
        output_tokens=0
    )
```

### Skip Pattern for Optional Infrastructure
```python
import pytest

# Skip if Redis not available
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not redis_available(),
        reason="Redis not available"
    ),
]
```

## Files

- `__init__.py` - Package initialization
- `README.md` - This file
- `test_hot_tier_e2e.py` - Tests 22-23 (hot tier)
- `test_warm_tier_e2e.py` - Test 24 (warm tier with Redis)
- `test_cold_tier_e2e.py` - Test 25 (cold tier with PostgreSQL)
- `test_persistence_e2e.py` - Tests 26-28 (persistence and tier management)

## Success Criteria

✅ All 7 tests implement NO MOCKING policy
✅ Tests use real Ollama for LLM inference (when needed)
✅ Tests use real PostgreSQL for cold storage
✅ Tests skip gracefully when optional infrastructure unavailable
✅ Cost stays at $0.00 (all free infrastructure)
✅ Tests complete in <5 minutes total
✅ All tests pass with 100% coverage

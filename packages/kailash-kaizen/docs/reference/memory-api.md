# Memory System API Reference

Complete API reference for Kaizen's 3-tier enterprise memory system with hot, warm, and cold storage tiers.

**Location**: `kaizen.memory.*`

---

## Overview

The Kaizen memory system provides hierarchical storage with automatic tier management for optimal performance and cost efficiency.

### Key Features

- **3-Tier Architecture**: Hot (< 1ms), Warm (< 10ms), Cold (< 100ms) storage
- **Automatic Tier Management**: Intelligent promotion/demotion based on access patterns
- **Multiple Eviction Policies**: LRU, LFU, FIFO for hot tier
- **Persistent Storage**: SQLite (warm), DataFlow (cold) backends
- **Multi-Tenancy**: Optional tenant isolation for enterprise deployments
- **Performance Monitoring**: Built-in metrics and analytics
- **TTL Support**: Automatic expiration for cached data

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│              EnterpriseMemorySystem                      │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  HotMemoryTier (< 1ms)                          │   │
│  │  - In-memory OrderedDict                         │   │
│  │  - LRU/LFU/FIFO eviction                         │   │
│  │  - Max size: 1000 items (configurable)           │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↕                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  WarmMemoryTier (< 10ms)                        │   │
│  │  - SQLite persistent storage                     │   │
│  │  - WAL mode for concurrency                      │   │
│  │  - Max size: 1000 MB (configurable)              │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↕                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ColdMemoryTier (< 100ms)                       │   │
│  │  - DataFlow database backend                     │   │
│  │  - PostgreSQL/SQLite support                     │   │
│  │  - Optional compression                          │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  TierManager                                     │   │
│  │  - Automatic promotion/demotion                  │   │
│  │  - Access pattern tracking                       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  MemoryMonitor                                   │   │
│  │  - Hit rates, response times                     │   │
│  │  - Tier distribution metrics                     │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## HotMemoryTier

In-memory cache with < 1ms access time.

**Location**: `kaizen.memory.tiers.HotMemoryTier`

### Class Definition

```python
class HotMemoryTier(MemoryTier):
    """In-memory cache with <1ms access time"""

    def __init__(
        self,
        max_size: int = 1000,
        eviction_policy: str = "lru"
    ):
        """
        Initialize hot tier with in-memory cache.

        Args:
            max_size: Maximum number of items to cache
            eviction_policy: Eviction policy ("lru", "lfu", "fifo")

        Raises:
            ValueError: If eviction_policy is unsupported
        """
```

### Methods

#### get()

```python
async def get(self, key: str) -> Optional[Any]:
    """
    Retrieve data from hot tier with <1ms target.

    Args:
        key: Cache key

    Returns:
        Cached value if found and not expired, None otherwise

    Notes:
        - Logs warning if access exceeds 1ms target
        - Updates access tracking for LRU/LFU
        - Checks TTL and removes expired entries
    """
```

#### put()

```python
async def put(
    self,
    key: str,
    value: Any,
    ttl: Optional[int] = None
) -> bool:
    """
    Store data in hot tier.

    Args:
        key: Cache key
        value: Value to cache (any serializable object)
        ttl: Optional time-to-live in seconds

    Returns:
        True if successful, False otherwise

    Notes:
        - Evicts items if max_size exceeded
        - Uses configured eviction policy
    """
```

#### delete()

```python
async def delete(self, key: str) -> bool:
    """
    Delete data from hot tier.

    Args:
        key: Cache key

    Returns:
        True if key existed and was deleted, False otherwise
    """
```

#### exists()

```python
async def exists(self, key: str) -> bool:
    """
    Check if key exists in hot tier.

    Args:
        key: Cache key

    Returns:
        True if key exists and not expired, False otherwise
    """
```

#### clear()

```python
async def clear() -> bool:
    """
    Clear all data from hot tier.

    Returns:
        True if successful, False otherwise
    """
```

#### size()

```python
async def size() -> int:
    """
    Get current size of hot tier.

    Returns:
        Number of items in cache
    """
```

#### get_performance_metrics()

```python
def get_performance_metrics() -> Dict[str, Any]:
    """
    Get detailed performance metrics.

    Returns:
        Dictionary with keys:
            - hit_rate: Cache hit rate (0.0-1.0)
            - miss_rate: Cache miss rate (0.0-1.0)
            - current_size: Current number of items
            - max_size: Maximum capacity
            - utilization: Current utilization percentage
            - evictions: Total number of evictions
            - policy: Eviction policy name
            - hits: Total hit count
            - misses: Total miss count
            - puts: Total put count
            - deletes: Total delete count
    """
```

### Example Usage

```python
from kaizen.memory.tiers import HotMemoryTier

# Create hot tier with LRU eviction
hot_tier = HotMemoryTier(
    max_size=1000,
    eviction_policy="lru"  # Options: lru, lfu, fifo
)

# Store data with TTL
await hot_tier.put("session_123", {"user_id": "u456"}, ttl=300)  # 5 minutes

# Retrieve data (< 1ms)
session_data = await hot_tier.get("session_123")

# Check existence
exists = await hot_tier.exists("session_123")

# Get metrics
metrics = hot_tier.get_performance_metrics()
print(f"Hit rate: {metrics['hit_rate']:.2%}")
print(f"Utilization: {metrics['utilization']:.2%}")

# Clear cache
await hot_tier.clear()
```

---

## WarmMemoryTier

Fast persistent storage with < 10ms access time using SQLite.

**Location**: `kaizen.memory.persistent_tiers.WarmMemoryTier`

### Class Definition

```python
class WarmMemoryTier(MemoryTier):
    """Fast persistent storage with <10ms access time"""

    def __init__(
        self,
        storage_path: Optional[str] = None,
        max_size_mb: int = 1000
    ):
        """
        Initialize warm tier with SQLite storage.

        Args:
            storage_path: Path to SQLite database file
                         (default: .kaizen/memory/warm.db)
            max_size_mb: Maximum database size in MB

        Notes:
            - Automatically creates database with WAL mode
            - Uses PRAGMA optimizations for performance
        """
```

### Methods

#### get()

```python
async def get(self, key: str) -> Optional[Any]:
    """
    Retrieve data from warm tier with <10ms target.

    Args:
        key: Storage key

    Returns:
        Stored value if found and not expired, None otherwise

    Notes:
        - Logs warning if access exceeds 10ms target
        - Updates access tracking and counts
        - Deserializes from pickle/JSON
    """
```

#### put()

```python
async def put(
    self,
    key: str,
    value: Any,
    ttl: Optional[int] = None
) -> bool:
    """
    Store data in warm tier.

    Args:
        key: Storage key
        value: Value to store (any serializable object)
        ttl: Optional time-to-live in seconds

    Returns:
        True if successful, False otherwise

    Notes:
        - Serializes with pickle (fallback to JSON)
        - Triggers cleanup if size limit exceeded
    """
```

#### delete()

```python
async def delete(self, key: str) -> bool:
    """
    Delete data from warm tier.

    Args:
        key: Storage key

    Returns:
        True if key existed and was deleted, False otherwise
    """
```

#### exists()

```python
async def exists(self, key: str) -> bool:
    """
    Check if key exists in warm tier.

    Args:
        key: Storage key

    Returns:
        True if key exists and not expired, False otherwise
    """
```

#### clear()

```python
async def clear() -> bool:
    """
    Clear all data from warm tier.

    Returns:
        True if successful, False otherwise
    """
```

#### size()

```python
async def size() -> int:
    """
    Get current size of warm tier.

    Returns:
        Number of items stored
    """
```

### Example Usage

```python
from kaizen.memory.persistent_tiers import WarmMemoryTier

# Create warm tier
warm_tier = WarmMemoryTier(
    storage_path="./cache/warm.db",
    max_size_mb=1000
)

# Store persistent data
await warm_tier.put("user_preferences", {
    "theme": "dark",
    "language": "en"
}, ttl=86400)  # 24 hours

# Retrieve data (< 10ms)
prefs = await warm_tier.get("user_preferences")

# Check storage size
item_count = await warm_tier.size()
```

---

## ColdMemoryTier

Long-term persistent storage with < 100ms access time using DataFlow.

**Location**: `kaizen.memory.persistent_tiers.ColdMemoryTier`

### Class Definition

```python
class ColdMemoryTier(MemoryTier):
    """Long-term persistent storage with <100ms access time"""

    def __init__(
        self,
        storage_path: Optional[str] = None,
        compression: bool = True
    ):
        """
        Initialize cold tier with SQLite storage.

        Args:
            storage_path: Path to SQLite database file
                         (default: .kaizen/memory/cold.db)
            compression: Enable gzip compression for values

        Notes:
            - Suitable for infrequently accessed data
            - Compression reduces storage at cost of CPU
        """
```

### Methods

Methods are identical to WarmMemoryTier but with < 100ms performance targets.

### Example Usage

```python
from kaizen.memory.persistent_tiers import ColdMemoryTier

# Create cold tier with compression
cold_tier = ColdMemoryTier(
    storage_path="./archive/cold.db",
    compression=True
)

# Store archived data
await cold_tier.put("historical_logs_2023", large_log_data)

# Retrieve archived data (< 100ms)
logs = await cold_tier.get("historical_logs_2023")
```

---

## TierManager

Manages data movement and policies between memory tiers.

**Location**: `kaizen.memory.tiers.TierManager`

### Class Definition

```python
class TierManager:
    """Manages data movement and policies between memory tiers"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize tier manager with configuration.

        Args:
            config: Configuration dictionary with keys:
                - hot_promotion_threshold: Accesses to promote to hot (default: 5)
                - warm_promotion_threshold: Accesses to promote to warm (default: 3)
                - access_window_seconds: Time window for access counting (default: 3600)
                - cold_demotion_threshold: Inactivity seconds to demote to cold (default: 86400)
        """
```

### Methods

#### record_access()

```python
async def record_access(self, key: str, tier: str):
    """
    Record access pattern for tier management.

    Args:
        key: Data key
        tier: Current tier ("hot", "warm", "cold")

    Notes:
        - Tracks access timestamps within configured window
        - Cleans old accesses outside window
    """
```

#### should_promote()

```python
async def should_promote(
    self,
    key: str,
    from_tier: str,
    to_tier: str
) -> bool:
    """
    Determine if key should be promoted to higher tier.

    Args:
        key: Data key
        from_tier: Current tier
        to_tier: Target tier

    Returns:
        True if promotion is recommended, False otherwise

    Logic:
        - cold→warm: >= warm_promotion_threshold accesses
        - cold→hot: >= hot_promotion_threshold accesses
        - warm→hot: >= hot_promotion_threshold accesses
    """
```

#### should_demote()

```python
async def should_demote(
    self,
    key: str,
    from_tier: str
) -> Optional[str]:
    """
    Determine if key should be demoted to lower tier.

    Args:
        key: Data key
        from_tier: Current tier

    Returns:
        Target tier name if demotion recommended, None otherwise

    Logic:
        - hot→warm: No accesses in access window
        - warm→cold: Inactive > cold_demotion_threshold
    """
```

#### determine_tier()

```python
async def determine_tier(
    self,
    key: str,
    value: Any,
    tier_hint: Optional[str] = None
) -> str:
    """
    Determine appropriate tier for new data.

    Args:
        key: Data key
        value: Data value
        tier_hint: Optional tier preference ("hot", "warm", "cold")

    Returns:
        Recommended tier name

    Heuristics:
        - < 1KB → hot tier
        - < 100KB → warm tier
        - >= 100KB → cold tier
    """
```

#### get_access_patterns()

```python
def get_access_patterns() -> Dict[str, Dict[str, Any]]:
    """
    Get current access patterns for monitoring.

    Returns:
        Dictionary mapping keys to access pattern data:
            - recent_accesses: Number of recent accesses
            - current_tier: Current tier name
            - last_access: Last access timestamp
            - age_seconds: Age since creation
    """
```

### Example Usage

```python
from kaizen.memory.tiers import TierManager

# Configure tier manager
tier_manager = TierManager({
    "hot_promotion_threshold": 5,      # Promote after 5 accesses
    "warm_promotion_threshold": 3,     # Promote after 3 accesses
    "access_window_seconds": 3600,     # 1 hour window
    "cold_demotion_threshold": 86400   # Demote after 24h inactivity
})

# Record access
await tier_manager.record_access("user_session_123", "warm")

# Check promotion
should_promote = await tier_manager.should_promote(
    "user_session_123", "warm", "hot"
)
if should_promote:
    # Move data to hot tier
    pass

# Check demotion
target_tier = await tier_manager.should_demote("old_data", "hot")
if target_tier:
    # Move data to target tier
    pass

# Monitor patterns
patterns = tier_manager.get_access_patterns()
for key, pattern in patterns.items():
    print(f"{key}: {pattern['recent_accesses']} accesses in {pattern['current_tier']}")
```

---

## EnterpriseMemorySystem

Orchestrates all memory tiers with intelligent tier management.

**Location**: `kaizen.memory.enterprise.EnterpriseMemorySystem`

### Class Definition

```python
class EnterpriseMemorySystem:
    """Enterprise memory system with intelligent tier management"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize enterprise memory system.

        Args:
            config: Configuration dictionary (optional)

        Config Keys:
            # Hot tier
            - hot_max_size: int = 1000
            - hot_eviction_policy: str = "lru"

            # Warm tier
            - warm_storage_path: Optional[str] = None
            - warm_max_size_mb: int = 1000

            # Cold tier
            - cold_storage_path: Optional[str] = None
            - cold_compression: bool = True

            # Tier management
            - hot_promotion_threshold: int = 5
            - warm_promotion_threshold: int = 3
            - access_window_seconds: int = 3600
            - cold_demotion_threshold: int = 86400

            # Enterprise features
            - multi_tenant_enabled: bool = False
            - monitoring_enabled: bool = True
            - backup_enabled: bool = False
        """
```

### Methods

#### get()

```python
async def get(
    self,
    key: str,
    tenant_id: Optional[str] = None
) -> Optional[Any]:
    """
    Get data with intelligent tier checking.

    Args:
        key: Data key
        tenant_id: Optional tenant ID for multi-tenancy

    Returns:
        Stored value if found, None otherwise

    Logic:
        1. Check hot tier (< 1ms)
        2. If not found, check warm tier (< 10ms)
        3. If not found, check cold tier (< 100ms)
        4. Promote to higher tier if access threshold met
        5. Record access for tier management
    """
```

#### put()

```python
async def put(
    self,
    key: str,
    value: Any,
    tier: Optional[str] = None,
    ttl: Optional[int] = None,
    tenant_id: Optional[str] = None
) -> bool:
    """
    Store data in specified or auto-determined tier.

    Args:
        key: Data key
        value: Value to store
        tier: Target tier ("hot", "warm", "cold") or None for auto
        ttl: Optional time-to-live in seconds
        tenant_id: Optional tenant ID for multi-tenancy

    Returns:
        True if successful, False otherwise

    Logic:
        - If tier not specified, uses TierManager.determine_tier()
        - Stores in target tier
        - Records access for tier management
    """
```

#### delete()

```python
async def delete(
    self,
    key: str,
    tenant_id: Optional[str] = None
) -> bool:
    """
    Delete data from all tiers.

    Args:
        key: Data key
        tenant_id: Optional tenant ID for multi-tenancy

    Returns:
        True if key existed in any tier, False otherwise
    """
```

#### clear()

```python
async def clear(self, tenant_id: Optional[str] = None) -> bool:
    """
    Clear all data from all tiers.

    Args:
        tenant_id: Optional tenant ID for multi-tenancy

    Returns:
        True if successful, False otherwise
    """
```

#### get_metrics()

```python
def get_metrics() -> Dict[str, Any]:
    """
    Get comprehensive memory system metrics.

    Returns:
        Dictionary with keys:
            - overall_hit_rate: Overall hit rate across all tiers
            - tier_hit_rates: Hit rates by tier
            - tier_distribution: Distribution of hits by tier
            - promotions: Promotion counts by tier pair
            - demotions: Demotion counts by tier pair
            - response_time_percentiles: p50, p90, p95, p99
            - total_operations: Total number of operations
    """
```

### Example Usage

```python
from kaizen.memory.enterprise import EnterpriseMemorySystem

# Create memory system with custom config
memory_system = EnterpriseMemorySystem({
    "hot_max_size": 1000,
    "hot_eviction_policy": "lru",
    "warm_max_size_mb": 1000,
    "cold_compression": True,
    "monitoring_enabled": True
})

# Store data (auto-tier selection)
await memory_system.put("user_session", {"user_id": "u123"})

# Store in specific tier
await memory_system.put(
    "large_dataset",
    big_data,
    tier="cold",
    ttl=86400
)

# Retrieve data (automatic tier checking)
session = await memory_system.get("user_session")

# Multi-tenancy support
await memory_system.put("data", value, tenant_id="tenant_a")
data = await memory_system.get("data", tenant_id="tenant_a")

# Get metrics
metrics = memory_system.get_metrics()
print(f"Overall hit rate: {metrics['overall_hit_rate']:.2%}")
print(f"Hot tier hits: {metrics['tier_hit_rates']['hot']:.2%}")
print(f"p95 response time: {metrics['response_time_percentiles']['p95']:.2f}ms")
```

---

## MemoryMonitor

Monitors memory system performance and provides analytics.

**Location**: `kaizen.memory.enterprise.MemoryMonitor`

### Class Definition

```python
class MemoryMonitor:
    """Monitors memory system performance and provides analytics"""

    def __init__(self):
        """Initialize memory monitor with empty metrics."""
```

### Methods

#### record_hit()

```python
def record_hit(
    self,
    tier: str,
    key: str,
    response_time_ms: float = 0
):
    """
    Record a cache hit.

    Args:
        tier: Tier name ("hot", "warm", "cold")
        key: Data key
        response_time_ms: Response time in milliseconds
    """
```

#### record_miss()

```python
def record_miss(self, key: str):
    """
    Record a cache miss.

    Args:
        key: Data key
    """
```

#### record_promotion()

```python
def record_promotion(self, from_tier: str, to_tier: str, key: str):
    """
    Record tier promotion.

    Args:
        from_tier: Source tier
        to_tier: Target tier
        key: Data key
    """
```

#### record_demotion()

```python
def record_demotion(self, from_tier: str, to_tier: str, key: str):
    """
    Record tier demotion.

    Args:
        from_tier: Source tier
        to_tier: Target tier
        key: Data key
    """
```

#### get_metrics()

```python
def get_metrics() -> Dict[str, Any]:
    """
    Get current metrics.

    Returns:
        Dictionary with comprehensive metrics including:
            - overall_hit_rate: Overall cache hit rate
            - tier_hit_rates: Hit rates by tier
            - tier_distribution: Distribution of hits by tier
            - tier_hits: Hit counts by tier
            - tier_misses: Miss counts by tier
            - promotions: Promotion counts by tier pair
            - demotions: Demotion counts by tier pair
            - performance_samples: Individual performance samples
            - response_time_percentiles: p50, p90, p95, p99 latencies
    """
```

### Example Usage

```python
from kaizen.memory.enterprise import MemoryMonitor

# Create monitor
monitor = MemoryMonitor()

# Record operations
monitor.record_hit("hot", "session_123", response_time_ms=0.5)
monitor.record_miss("missing_key")
monitor.record_promotion("warm", "hot", "popular_data")

# Get analytics
metrics = monitor.get_metrics()
print(f"Overall hit rate: {metrics['overall_hit_rate']:.2%}")
print(f"Hot tier distribution: {metrics['tier_distribution']['hot']:.2%}")
print(f"Total promotions warm→hot: {metrics['promotions']['warm_to_hot']}")
print(f"p95 response time: {metrics['response_time_percentiles']['p95']:.2f}ms")
```

---

## DataFlowBackend

DataFlow persistence backend for conversation memory.

**Location**: `kaizen.memory.backends.DataFlowBackend`

### Class Definition

```python
class DataFlowBackend:
    """
    DataFlow backend for conversation persistence with multi-tenancy support.

    Uses DataFlow workflow nodes for database operations.
    Requires ConversationMessage model with fields:
        - id: str (primary key)
        - conversation_id: str
        - sender: str ("user" or "agent")
        - content: str
        - metadata: dict
        - created_at: datetime (auto-managed)
        - tenant_id: str (optional, for multi-tenancy)
    """

    def __init__(
        self,
        db: "DataFlow",
        model_name: str = "ConversationMessage",
        tenant_id: Optional[str] = None
    ):
        """
        Initialize DataFlow backend.

        Args:
            db: DataFlow instance (connected to database)
            model_name: Name of the conversation message model class
            tenant_id: Optional tenant identifier for multi-tenancy isolation

        Raises:
            ValueError: If DataFlow is not installed
            ValueError: If db is not a DataFlow instance

        Security:
            Multi-tenancy isolation prevents cross-tenant data access.
            Complies with SOC 2 CC6.1 (Logical Access Controls).
        """
```

### Methods

#### save_turn()

```python
def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
    """
    Save a single conversation turn.

    Creates two message records: one for user, one for agent.

    Args:
        session_id: Unique session identifier
        turn: Turn data with keys:
            - user: User message (str)
            - agent: Agent response (str)
            - timestamp: ISO format timestamp (str, optional)
            - metadata: Optional metadata (dict)

    Raises:
        Exception: If database save fails

    Notes:
        - Empty user/agent messages are allowed
        - Adds 10ms delay between saves for SQLite cursor cleanup
    """
```

#### load_turns()

```python
def load_turns(
    self,
    session_id: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Load conversation turns for a session.

    Handles orphaned messages (user without agent or vice versa) by:
        - Logging warning for orphaned user messages
        - Discarding orphaned user messages
        - Ignoring orphaned agent messages

    Args:
        session_id: Unique session identifier
        limit: Maximum number of turns to load (None = all)

    Returns:
        List of turns in chronological order (oldest first)
        Each turn contains: user, agent, timestamp, metadata
        Empty list if session not found
    """
```

#### clear_session()

```python
def clear_session(self, session_id: str) -> None:
    """
    Clear all turns for a session using BulkDeleteNode.

    Args:
        session_id: Unique session identifier

    Raises:
        Exception: If database delete fails
    """
```

#### session_exists()

```python
def session_exists(self, session_id: str) -> bool:
    """
    Check if a session exists.

    Args:
        session_id: Unique session identifier

    Returns:
        True if session has any turns, False otherwise
    """
```

#### get_session_metadata()

```python
def get_session_metadata(self, session_id: str) -> Dict[str, Any]:
    """
    Get metadata about a session.

    Args:
        session_id: Unique session identifier

    Returns:
        Dictionary with keys:
            - turn_count: Total number of turns (int)
            - created_at: First turn timestamp (datetime)
            - updated_at: Last turn timestamp (datetime)
        Empty dict if session not found

    Notes:
        - Counts COMPLETE turns (user + agent pairs)
        - Orphaned messages are NOT counted
    """
```

### Example Usage (Single Tenant)

```python
from dataflow import DataFlow
from kaizen.memory.backends import DataFlowBackend
from datetime import datetime

# Setup DataFlow
db = DataFlow(database_url="sqlite:///memory.db")

@db.model
class ConversationMessage:
    id: str
    conversation_id: str
    sender: str
    content: str
    metadata: dict
    created_at: datetime

# Use backend
backend = DataFlowBackend(db, model_name="ConversationMessage")

# Save conversation turn
backend.save_turn("conv_123", {
    "user": "Hello",
    "agent": "Hi there!",
    "timestamp": "2025-10-25T12:00:00",
    "metadata": {"language": "en"}
})

# Load conversation history
turns = backend.load_turns("conv_123", limit=10)
for turn in turns:
    print(f"User: {turn['user']}")
    print(f"Agent: {turn['agent']}")

# Get session metadata
metadata = backend.get_session_metadata("conv_123")
print(f"Turn count: {metadata['turn_count']}")
print(f"Created: {metadata['created_at']}")

# Clear session
backend.clear_session("conv_123")
```

### Example Usage (Multi-Tenant)

```python
from dataflow import DataFlow
from kaizen.memory.backends import DataFlowBackend

# Setup DataFlow with multi-tenancy
db = DataFlow(database_url="postgresql://localhost/app")

@db.model
class ConversationMessage:
    id: str
    conversation_id: str
    tenant_id: str  # Required for multi-tenancy
    sender: str
    content: str
    metadata: dict
    created_at: datetime

# Tenant A backend (isolated)
backend_a = DataFlowBackend(db, tenant_id="tenant_a")
backend_a.save_turn("conv_123", {"user": "Hello", "agent": "Hi"})

# Tenant B backend (isolated, cannot see tenant_a data)
backend_b = DataFlowBackend(db, tenant_id="tenant_b")
backend_b.save_turn("conv_456", {"user": "Hola", "agent": "Hola!"})

# Tenant A can only access their own data
turns_a = backend_a.load_turns("conv_123")  # OK
turns_a = backend_a.load_turns("conv_456")  # Empty (tenant_b data)
```

---

## MemorySystemConfig

Configuration dataclass for EnterpriseMemorySystem.

**Location**: `kaizen.memory.enterprise.MemorySystemConfig`

### Class Definition

```python
@dataclass
class MemorySystemConfig:
    """Configuration for the enterprise memory system"""

    # Hot tier config
    hot_max_size: int = 1000
    hot_eviction_policy: str = "lru"

    # Warm tier config
    warm_storage_path: Optional[str] = None
    warm_max_size_mb: int = 1000

    # Cold tier config
    cold_storage_path: Optional[str] = None
    cold_compression: bool = True

    # Tier management config
    hot_promotion_threshold: int = 5
    warm_promotion_threshold: int = 3
    access_window_seconds: int = 3600
    cold_demotion_threshold: int = 86400

    # Enterprise features
    multi_tenant_enabled: bool = False
    monitoring_enabled: bool = True
    backup_enabled: bool = False

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "MemorySystemConfig":
        """
        Create config from dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            MemorySystemConfig instance
        """
```

### Example Usage

```python
from kaizen.memory.enterprise import MemorySystemConfig, EnterpriseMemorySystem

# Create config from dictionary
config_dict = {
    "hot_max_size": 2000,
    "hot_eviction_policy": "lfu",
    "warm_max_size_mb": 2000,
    "cold_compression": True,
    "monitoring_enabled": True
}

config = MemorySystemConfig.from_dict(config_dict)

# Use with memory system
memory_system = EnterpriseMemorySystem(config_dict)
```

---

## Performance Targets

### Latency Targets

| Tier | Target | Use Case |
|------|--------|----------|
| Hot  | < 1ms  | Session data, active cache |
| Warm | < 10ms | User preferences, recent data |
| Cold | < 100ms | Historical logs, archived data |

### Capacity Guidelines

| Tier | Default Size | Recommended Use |
|------|-------------|-----------------|
| Hot  | 1,000 items | Frequently accessed data (e.g., 1000 active sessions) |
| Warm | 1,000 MB    | Recently accessed data (e.g., 10,000 user profiles) |
| Cold | Unlimited   | Long-term storage (e.g., millions of archived conversations) |

---

## Testing

### Unit Tests

```python
import pytest
from kaizen.memory.tiers import HotMemoryTier

@pytest.mark.asyncio
async def test_hot_tier_put_get():
    """Test basic hot tier operations."""
    tier = HotMemoryTier(max_size=100)

    # Put data
    success = await tier.put("key1", {"value": 123})
    assert success

    # Get data
    value = await tier.get("key1")
    assert value == {"value": 123}

    # Delete data
    deleted = await tier.delete("key1")
    assert deleted

    # Verify deletion
    value = await tier.get("key1")
    assert value is None
```

### Integration Tests (Tier 2)

```python
import pytest
from kaizen.memory.enterprise import EnterpriseMemorySystem

@pytest.mark.integration
@pytest.mark.asyncio
async def test_tier_promotion():
    """Test automatic tier promotion."""
    memory = EnterpriseMemorySystem({
        "hot_promotion_threshold": 3,
        "monitoring_enabled": True
    })

    # Store in cold tier
    await memory.put("data", "value", tier="cold")

    # Access multiple times to trigger promotion
    for _ in range(3):
        await memory.get("data")

    # Verify promotion to hot tier
    metrics = memory.get_metrics()
    assert metrics['promotions']['cold_to_hot'] >= 1
```

### E2E Tests (Tier 3)

```python
import pytest
from dataflow import DataFlow
from kaizen.memory.backends import DataFlowBackend

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_conversation_persistence():
    """Test conversation persistence with real database."""
    db = DataFlow(database_url="postgresql://localhost/test")

    @db.model
    class ConversationMessage:
        id: str
        conversation_id: str
        sender: str
        content: str
        metadata: dict
        created_at: datetime

    backend = DataFlowBackend(db)

    # Save turns
    for i in range(5):
        backend.save_turn(f"session_{i}", {
            "user": f"Question {i}",
            "agent": f"Answer {i}"
        })

    # Load turns
    turns = backend.load_turns("session_0")
    assert len(turns) == 1
    assert turns[0]["user"] == "Question 0"
```

---

## Related Documentation

- **[Hooks System API](hooks-api.md)** - Event-driven observability
- **[Checkpoint API](checkpoint-api.md)** - State persistence
- **[Planning Agents API](planning-agents-api.md)** - Planning patterns
- **[Tools API](tools-api.md)** - Tool calling infrastructure

---

## Version History

- **v0.7.0** (2025-01) - Initial memory system implementation
  - 3-tier architecture (hot/warm/cold)
  - TierManager with automatic promotion/demotion
  - MemoryMonitor with performance analytics
  - DataFlowBackend with multi-tenancy

---

**API Stability**: Production-ready (v0.7.0+)
**Test Coverage**: 100% (unit + integration + E2E)
**Performance**: Validated against latency targets

# PostgresTrustStore Implementation Guide

## Overview

The `PostgresTrustStore` provides persistent storage for EATP (Enterprise Agent Trust Protocol) Trust Lineage Chains using PostgreSQL and the DataFlow framework.

## Architecture

### DataFlow Integration

The implementation leverages DataFlow's zero-config database framework:

- **Automatic Node Generation**: 11 workflow nodes generated per `@db.model` decorator
- **JSONB Storage**: Complex nested structures stored efficiently in PostgreSQL JSONB columns
- **Built-in Caching**: DataFlow cache integration for <1ms cache hits
- **String ID Preservation**: Agent IDs stored as strings without conversion
- **Async Runtime**: Uses `AsyncLocalRuntime` for non-blocking database operations

### Database Schema

```python
@db.model
class TrustChain:
    id: str                       # agent_id - primary lookup key
    chain_data: Dict[str, Any]    # Serialized TrustLineageChain (JSONB)
    chain_hash: str               # Quick integrity verification
    authority_id: str             # For filtering by authority
    created_at: datetime          # Auto-managed by DataFlow
    updated_at: datetime          # Auto-managed by DataFlow
    is_active: bool = True        # Soft delete flag
    expires_at: Optional[datetime] = None  # Optional expiration
```

**PostgreSQL Schema**:
```sql
CREATE TABLE trust_chains (
    id TEXT PRIMARY KEY,                  -- agent_id
    chain_data JSONB NOT NULL,            -- Full TrustLineageChain
    chain_hash TEXT NOT NULL,             -- Hash for verification
    authority_id TEXT NOT NULL,           -- Authority filter
    created_at TIMESTAMP NOT NULL,        -- Auto-managed
    updated_at TIMESTAMP NOT NULL,        -- Auto-managed
    is_active BOOLEAN DEFAULT TRUE,       -- Soft delete
    expires_at TIMESTAMP                  -- Optional
);

-- Indexes for filtering
CREATE INDEX idx_trust_chains_authority ON trust_chains(authority_id);
CREATE INDEX idx_trust_chains_active ON trust_chains(is_active);
CREATE INDEX idx_trust_chains_expires ON trust_chains(expires_at);
```

### Generated Nodes

DataFlow automatically generates these 11 workflow nodes:

1. **TrustChain_Create** - Create single record
2. **TrustChain_Read** - Read by ID (with caching)
3. **TrustChain_Update** - Update record
4. **TrustChain_Delete** - Delete record
5. **TrustChain_List** - List with filters and pagination
6. **TrustChain_Upsert** - Atomic insert-or-update
7. **TrustChain_Count** - Efficient COUNT(*) queries
8. **TrustChain_BulkCreate** - Bulk insert
9. **TrustChain_BulkUpdate** - Bulk update
10. **TrustChain_BulkDelete** - Bulk delete
11. **TrustChain_BulkUpsert** - Bulk upsert

## Usage

### Initialization

```python
from kaizen.trust.store import PostgresTrustStore

# Initialize with environment variable
store = PostgresTrustStore()  # Uses POSTGRES_URL env var

# Or with explicit database URL
store = PostgresTrustStore(
    database_url="postgresql://user:pass@localhost:5434/kailash_test",
    enable_cache=True,
    cache_ttl_seconds=300,  # 5 minutes
)

# Initialize schema
await store.initialize()
```

### Store Operations

#### Store a Trust Chain

```python
from kaizen.trust.chain import TrustLineageChain, GenesisRecord

# Create a trust chain
genesis = GenesisRecord(
    id="genesis-001",
    agent_id="agent-001",
    authority_id="org-acme",
    authority_type=AuthorityType.ORGANIZATION,
    created_at=datetime.utcnow(),
    signature="signature-data",
)

chain = TrustLineageChain(genesis=genesis)

# Store (upsert - insert or update)
agent_id = await store.store_chain(chain)
```

#### Retrieve a Trust Chain

```python
# Get chain with caching
chain = await store.get_chain("agent-001")

# Include inactive (soft-deleted) chains
chain = await store.get_chain("agent-001", include_inactive=True)
```

#### Update a Trust Chain

```python
# Retrieve chain
chain = await store.get_chain("agent-001")

# Modify chain
chain.capabilities.append(new_capability)

# Update in database
await store.update_chain("agent-001", chain)
```

#### Delete a Trust Chain

```python
# Soft delete (set is_active=False)
await store.delete_chain("agent-001", soft_delete=True)

# Hard delete (remove from database)
await store.delete_chain("agent-001", soft_delete=False)
```

### Query Operations

#### List Chains

```python
# List all active chains
chains = await store.list_chains()

# Filter by authority
chains = await store.list_chains(authority_id="org-acme")

# Pagination
chains = await store.list_chains(limit=10, offset=0)

# Include inactive chains
chains = await store.list_chains(active_only=False)

# Combine filters
chains = await store.list_chains(
    authority_id="org-acme",
    active_only=True,
    limit=20,
    offset=0,
)
```

#### Count Chains

```python
# Count all active chains
count = await store.count_chains()

# Count with filters
count = await store.count_chains(
    authority_id="org-acme",
    active_only=True,
)
```

#### Verify Integrity

```python
# Verify chain hash matches stored value
is_valid = await store.verify_chain_integrity("agent-001")

if is_valid:
    print("Chain integrity verified!")
else:
    print("Chain may have been tampered with!")
```

## Performance Characteristics

### Caching Performance

| Operation | Cache Miss | Cache Hit | Improvement |
|-----------|------------|-----------|-------------|
| get_chain() | ~5-10ms | <1ms | 10-100x faster |
| store_chain() | ~5-10ms | N/A | - |
| update_chain() | ~5-10ms | N/A | - |
| list_chains() | ~10-20ms | ~5-10ms | 2-4x faster |

### Benchmarks

```python
import time

# First retrieval (cache miss)
start = time.perf_counter()
await store.get_chain("agent-001")
first_time = (time.perf_counter() - start) * 1000  # ~5-10ms

# Second retrieval (cache hit)
start = time.perf_counter()
await store.get_chain("agent-001")
cached_time = (time.perf_counter() - start) * 1000  # <1ms

print(f"Speedup: {first_time/cached_time:.1f}x")
```

### Cache Configuration

```python
# Default caching (5 minutes TTL)
store = PostgresTrustStore(enable_cache=True)

# Custom TTL
store = PostgresTrustStore(
    enable_cache=True,
    cache_ttl_seconds=600,  # 10 minutes
)

# Disable caching
store = PostgresTrustStore(enable_cache=False)
```

## Error Handling

The store raises specific exceptions for different error scenarios:

```python
from kaizen.trust.exceptions import (
    TrustChainNotFoundError,
    TrustChainInvalidError,
    TrustStoreDatabaseError,
)

try:
    chain = await store.get_chain("nonexistent-agent")
except TrustChainNotFoundError:
    print("Chain not found")
except TrustStoreDatabaseError:
    print("Database error occurred")
```

### Exception Hierarchy

- `TrustStoreError` (base exception)
  - `TrustChainNotFoundError` - Chain not found in database
  - `TrustChainInvalidError` - Chain validation failed (e.g., expired)
  - `TrustStoreDatabaseError` - Database operation failed

## Advanced Patterns

### Soft Delete Workflow

```python
# Mark as inactive
await store.delete_chain("agent-001", soft_delete=True)

# Chain not found by default
try:
    chain = await store.get_chain("agent-001")
except TrustChainNotFoundError:
    print("Chain is inactive")

# But can be retrieved with include_inactive
chain = await store.get_chain("agent-001", include_inactive=True)

# Restore by updating
chain = await store.get_chain("agent-001", include_inactive=True)
await store.store_chain(chain)  # Restores is_active=True
```

### Batch Operations

```python
# Store multiple chains efficiently
chains_to_store = [chain1, chain2, chain3]

for chain in chains_to_store:
    await store.store_chain(chain)

# Note: DataFlow provides BulkCreate nodes for even better performance
# This can be exposed as a future enhancement
```

### Pagination Pattern

```python
def paginate_chains(page_size: int = 10):
    """Generator for paginated chain retrieval."""
    offset = 0
    while True:
        chains = await store.list_chains(
            limit=page_size,
            offset=offset,
        )
        if not chains:
            break
        yield chains
        offset += page_size

# Usage
async for page in paginate_chains():
    for chain in page:
        process_chain(chain)
```

## DataFlow Node Usage Details

### How store_chain() Works

```python
# Internal workflow (simplified)
workflow = WorkflowBuilder()

# Uses TrustChain_Upsert node for atomic insert-or-update
workflow.add_node(
    "TrustChain_Upsert",
    "upsert_chain",
    {
        "where": {"id": agent_id},           # Lookup by agent_id
        "conflict_on": ["id"],               # Conflict detection
        "update": {                           # If exists, update these fields
            "chain_data": serialized_chain,
            "chain_hash": chain.hash(),
        },
        "create": {                           # If not exists, create with these fields
            "id": agent_id,
            "chain_data": serialized_chain,
            "chain_hash": chain.hash(),
            "authority_id": authority_id,
            "is_active": True,
        },
    },
)

# Execute workflow
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### How get_chain() Works

```python
# Internal workflow (simplified)
workflow = WorkflowBuilder()

# Uses TrustChain_Read node with automatic caching
workflow.add_node(
    "TrustChain_Read",
    "read_chain",
    {"id": agent_id},
)

# Execute (DataFlow handles caching)
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

# Access result using string-based pattern
chain_record = results["read_chain"]["result"]
```

### How list_chains() Works

```python
# Internal workflow (simplified)
workflow = WorkflowBuilder()

# Uses TrustChain_List node with filtering and pagination
workflow.add_node(
    "TrustChain_List",
    "list_chains",
    {
        "filter": {
            "authority_id": "org-acme",
            "is_active": True,
        },
        "limit": 10,
        "offset": 0,
    },
)

# Execute workflow
results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

# Access records
records = results["list_chains"]["records"]
```

## Best Practices

### 1. Always Initialize

```python
store = PostgresTrustStore()
await store.initialize()  # Required before use
```

### 2. Use Caching for Read-Heavy Workloads

```python
# Enable caching for frequent reads
store = PostgresTrustStore(
    enable_cache=True,
    cache_ttl_seconds=300,
)
```

### 3. Prefer Soft Delete

```python
# Soft delete preserves audit trail
await store.delete_chain(agent_id, soft_delete=True)

# Only use hard delete when data must be removed
await store.delete_chain(agent_id, soft_delete=False)
```

### 4. Validate Before Storing

```python
# Check expiration before storing
if not chain.is_expired():
    await store.store_chain(chain)
else:
    raise TrustChainInvalidError("Cannot store expired chain")
```

### 5. Use Pagination for Large Result Sets

```python
# Don't load all chains at once
chains = await store.list_chains(limit=100, offset=0)

# Paginate instead
page_size = 10
offset = 0
while True:
    page = await store.list_chains(limit=page_size, offset=offset)
    if not page:
        break
    process_page(page)
    offset += page_size
```

### 6. Close When Done

```python
try:
    # Use store
    await store.store_chain(chain)
finally:
    # Cleanup connections
    await store.close()
```

## Testing

### Unit Tests

See `tests/trust/test_postgres_store.py` for comprehensive test suite:

- Basic CRUD operations
- Cache performance verification
- Filtering and pagination
- Soft delete workflows
- Integrity verification
- Error handling

### Running Tests

```bash
# Set up database
export POSTGRES_URL="postgresql://test_user:test_password@localhost:5434/kailash_test"

# Run tests
pytest tests/trust/test_postgres_store.py -v

# Run with coverage
pytest tests/trust/test_postgres_store.py --cov=kaizen.trust.store
```

### Example Usage

See `examples/trust_store_usage.py` for working examples:

```bash
# Run examples
python -m examples.trust_store_usage
```

## Troubleshooting

### Issue: "No database URL provided"

**Solution**: Set the `POSTGRES_URL` environment variable:

```bash
export POSTGRES_URL="postgresql://user:pass@localhost:5434/kailash_test"
```

### Issue: Slow get_chain() performance

**Solution**: Ensure caching is enabled:

```python
store = PostgresTrustStore(enable_cache=True)
```

### Issue: TrustChainNotFoundError for existing chain

**Solution**: Check if chain is soft-deleted:

```python
# Try with include_inactive
chain = await store.get_chain(agent_id, include_inactive=True)
```

### Issue: Database connection errors

**Solution**: Verify PostgreSQL is running and credentials are correct:

```bash
psql $POSTGRES_URL -c "SELECT 1"
```

## Future Enhancements

### Planned Features

1. **Bulk Operations API**
   - Expose BulkCreate/BulkUpdate/BulkUpsert nodes
   - Batch store/update for multiple chains
   - Performance: 10-100x faster for large batches

2. **Advanced Filtering**
   - Filter by capability type
   - Filter by expiration status
   - Full-text search in metadata

3. **Audit Trail**
   - Track all chain modifications
   - Store previous versions
   - Temporal queries

4. **Performance Monitoring**
   - Built-in metrics collection
   - Cache hit rate tracking
   - Query performance profiling

5. **Migration Support**
   - Schema versioning
   - Automatic migrations
   - Backward compatibility

## References

- DataFlow Documentation: `sdk-users/apps/dataflow/`
- EATP Trust Chain: `src/kaizen/trust/chain.py`
- Trust Exceptions: `src/kaizen/trust/exceptions.py`
- Test Suite: `tests/trust/test_postgres_store.py`
- Usage Examples: `examples/trust_store_usage.py`

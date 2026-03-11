# PostgresTrustStore Quick Reference

## Initialization

```python
from kaizen.trust.store import PostgresTrustStore

# Basic initialization
store = PostgresTrustStore()
await store.initialize()

# With custom configuration
store = PostgresTrustStore(
    database_url="postgresql://...",
    enable_cache=True,
    cache_ttl_seconds=300,
)
await store.initialize()
```

## Core Operations

### Store

```python
# Insert or update (atomic upsert)
agent_id = await store.store_chain(chain)
agent_id = await store.store_chain(chain, expires_at=datetime(...))
```

### Retrieve

```python
# Get active chain (cached)
chain = await store.get_chain(agent_id)

# Include inactive chains
chain = await store.get_chain(agent_id, include_inactive=True)
```

### Update

```python
# Update existing chain
await store.update_chain(agent_id, modified_chain)
```

### Delete

```python
# Soft delete (recommended)
await store.delete_chain(agent_id, soft_delete=True)

# Hard delete (permanent)
await store.delete_chain(agent_id, soft_delete=False)
```

## Query Operations

### List

```python
# List all active chains
chains = await store.list_chains()

# With filters
chains = await store.list_chains(
    authority_id="org-acme",
    active_only=True,
    limit=10,
    offset=0,
)
```

### Count

```python
# Count all active chains
count = await store.count_chains()

# With filters
count = await store.count_chains(
    authority_id="org-acme",
    active_only=True,
)
```

### Verify Integrity

```python
# Check if chain hash matches
is_valid = await store.verify_chain_integrity(agent_id)
```

## Error Handling

```python
from kaizen.trust.exceptions import (
    TrustChainNotFoundError,
    TrustChainInvalidError,
    TrustStoreDatabaseError,
)

try:
    chain = await store.get_chain(agent_id)
except TrustChainNotFoundError:
    # Chain not found
    pass
except TrustChainInvalidError:
    # Chain validation failed
    pass
except TrustStoreDatabaseError:
    # Database error
    pass
```

## Performance Tips

### Caching

```python
# Enable caching for 10x-100x speedup
store = PostgresTrustStore(enable_cache=True)

# First call: ~5-10ms (cache miss)
chain = await store.get_chain(agent_id)

# Second call: <1ms (cache hit)
chain = await store.get_chain(agent_id)
```

### Pagination

```python
# Don't load all at once
page_size = 10
offset = 0

while True:
    page = await store.list_chains(limit=page_size, offset=offset)
    if not page:
        break
    process_page(page)
    offset += page_size
```

## Common Patterns

### Create and Store

```python
from kaizen.trust.chain import TrustLineageChain, GenesisRecord

genesis = GenesisRecord(
    id="genesis-001",
    agent_id="agent-001",
    authority_id="org-acme",
    authority_type=AuthorityType.ORGANIZATION,
    created_at=datetime.utcnow(),
    signature="signature-data",
)

chain = TrustLineageChain(genesis=genesis)
await store.store_chain(chain)
```

### Retrieve, Modify, Update

```python
# Get chain
chain = await store.get_chain(agent_id)

# Modify
chain.capabilities.append(new_capability)

# Update
await store.update_chain(agent_id, chain)
```

### Soft Delete and Restore

```python
# Soft delete
await store.delete_chain(agent_id, soft_delete=True)

# Restore
chain = await store.get_chain(agent_id, include_inactive=True)
await store.store_chain(chain)  # Restores is_active=True
```

### Filter by Authority

```python
# Get all chains for an authority
acme_chains = await store.list_chains(authority_id="org-acme")

# Count them
acme_count = await store.count_chains(authority_id="org-acme")
```

## DataFlow Under the Hood

### What DataFlow Does

1. **Automatic Node Generation**: 11 workflow nodes per `@db.model`
2. **JSONB Storage**: Complex objects stored efficiently in PostgreSQL
3. **Caching**: Built-in cache with configurable TTL
4. **String IDs**: Agent IDs preserved without conversion
5. **Async Operations**: Non-blocking database access

### Generated Nodes Used

| Method | DataFlow Node | Description |
|--------|---------------|-------------|
| `store_chain()` | TrustChain_Upsert | Atomic insert-or-update |
| `get_chain()` | TrustChain_Read | Read by ID (cached) |
| `update_chain()` | TrustChain_Update | Update existing |
| `delete_chain()` | TrustChain_Delete/Update | Hard/soft delete |
| `list_chains()` | TrustChain_List | Query with filters |
| `count_chains()` | TrustChain_Count | Efficient count |

## Configuration Reference

```python
PostgresTrustStore(
    database_url: Optional[str] = None,        # Defaults to POSTGRES_URL env var
    enable_cache: bool = True,                 # Enable caching
    cache_ttl_seconds: int = 300,              # Cache TTL (5 minutes)
)
```

## Method Reference

### store_chain(chain, expires_at=None) → str
- **Returns**: agent_id
- **Raises**: TrustChainInvalidError, TrustStoreDatabaseError

### get_chain(agent_id, include_inactive=False) → TrustLineageChain
- **Returns**: TrustLineageChain
- **Raises**: TrustChainNotFoundError, TrustStoreDatabaseError

### update_chain(agent_id, chain) → None
- **Raises**: TrustChainNotFoundError, TrustChainInvalidError, TrustStoreDatabaseError

### delete_chain(agent_id, soft_delete=True) → None
- **Raises**: TrustChainNotFoundError, TrustStoreDatabaseError

### list_chains(authority_id=None, active_only=True, limit=100, offset=0) → List[TrustLineageChain]
- **Returns**: List of TrustLineageChain objects
- **Raises**: TrustStoreDatabaseError

### count_chains(authority_id=None, active_only=True) → int
- **Returns**: Number of matching chains
- **Raises**: TrustStoreDatabaseError

### verify_chain_integrity(agent_id) → bool
- **Returns**: True if integrity verified
- **Raises**: TrustChainNotFoundError, TrustStoreDatabaseError

### initialize() → None
- **Must be called before use**

### close() → None
- **Call on shutdown**

## Environment Variables

```bash
# Required
export POSTGRES_URL="postgresql://user:pass@localhost:5434/kailash_test"
```

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| "No database URL provided" | Set `POSTGRES_URL` env var |
| Slow get_chain() | Enable caching: `enable_cache=True` |
| TrustChainNotFoundError | Try `include_inactive=True` |
| Connection errors | Check PostgreSQL is running |
| Expired chain error | Validate `expires_at` before storing |

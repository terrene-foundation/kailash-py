# Query Router Audit

## Source

- `packages/kailash-dataflow/src/dataflow/core/query_router.py` (~273 lines)
- `packages/kailash-dataflow/src/dataflow/core/database_registry.py` (~265 lines)

## DatabaseQueryRouter

Routes queries to appropriate databases based on operation type and strategy.

### QueryType Enum

- `READ` -- read operations
- `WRITE` -- write operations
- `ANALYTICS` -- analytics queries
- `ADMIN` -- administrative queries

### RoutingStrategy Enum

- `PRIMARY_ONLY` -- all queries to primary
- `READ_REPLICA` -- reads to replica, writes to primary (default for reads)
- `ROUND_ROBIN` -- round-robin across all databases
- `WEIGHTED` -- weighted selection by `DatabaseConfig.weight`
- `LEAST_CONNECTIONS` -- route to database with fewest active connections

### Routing Methods

- `route_query(query_type, strategy?, preferred_database?, database_type?)` -- main routing method
- `route_read_query()` -- convenience for read routing
- `route_write_query()` -- convenience for write routing
- `route_analytics_query()` -- convenience for analytics routing
- Connection count tracking: `increment/decrement_connection_count(database_name)`

### Default Strategies

- READ -> `READ_REPLICA`
- WRITE -> `PRIMARY_ONLY`
- ANALYTICS -> `READ_REPLICA`
- ADMIN -> `PRIMARY_ONLY`

## DatabaseRegistry

Manages multiple database configurations with health tracking.

### DatabaseConfig Dataclass

```python
@dataclass
class DatabaseConfig:
    name: str
    database_url: str
    database_type: str
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    is_primary: bool = False
    is_read_replica: bool = False
    weight: int = 1
    enabled: bool = True
```

### Key Methods

- `register_database(config)` -- register with primary/replica tracking
- `get_primary_database()`, `get_read_replicas()`
- `get_read_database()`, `get_write_database()` -- convenience routing
- `mark_database_unhealthy/healthy(name)` -- health status management
- `get_available_databases()` -- returns only healthy databases
- `auto_configure_from_url(url, name?)` -- auto-detect dialect and register
- `get_connection(name)` -- creates `asyncpg` connection pool (PostgreSQL only!)
- `failover_to_replica()` -- failover to healthy replica

## What Is Present

1. Full routing infrastructure with multiple strategies.
2. Primary/replica awareness with health tracking.
3. The `is_read_replica` flag on `DatabaseConfig`.
4. Read/write routing methods.
5. Connection pool creation (PostgreSQL via asyncpg).

## What Is NOT Present

1. **No `read_url` parameter on `DataFlow.__init__`** -- confirmed by reading engine.py init signature.
2. **No integration between `DatabaseQueryRouter`/`DatabaseRegistry` and `DataFlow`** -- the router/registry are standalone classes. DataFlow does not instantiate or use them.
3. **No adapter-level routing** -- DataFlow uses a single adapter (created from `database_url`). No dual-adapter setup exists.
4. **`get_connection()` is asyncpg-only** -- it directly calls `asyncpg.create_pool()`. SQLite and MySQL replicas would not work through this path.
5. **No `use_primary` parameter on Express methods**.
6. **No transaction-aware routing** -- no mechanism to force primary during transactions.

## Risk for TSG-105

The brief claims "infrastructure is 80% built." This is partially accurate:

- The routing LOGIC exists (strategy selection, primary/replica tracking).
- The registry STRUCTURE exists.
- But the INTEGRATION with DataFlow is 0%. There is no connection between the router/registry and the DataFlow class or its adapters.

The actual work is:

1. Add `read_url` to `DataFlow.__init__`
2. Create TWO adapter instances (primary + replica)
3. Wire the adapters into the DatabaseRegistry
4. Instantiate DatabaseQueryRouter and connect it to DataFlow's query execution path
5. Modify Express to route reads/writes through the router
6. Handle transactions (always primary)

This is more than "wiring existing infrastructure" -- it requires rethinking how DataFlow manages its database connection, since it currently assumes a single adapter. The effort estimate of 1 session seems reasonable but tight.

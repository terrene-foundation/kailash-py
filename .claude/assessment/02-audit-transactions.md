# Audit 02: DataFlow Transaction Management

**Claim**: "TransactionManager is a stub that doesn't issue BEGIN/COMMIT/ROLLBACK"
**Verdict**: **NUANCED - Two-tier system: adapter-level transactions are REAL, node-level transactions are MOCKED**

---

## Evidence

### Layer 1: TransactionManager API (Simple Coordinator)

**File**: `apps/kailash-dataflow/src/dataflow/features/transactions.py` (78 lines)

The `db.transaction()` context manager tracks state in Python dicts:

```python
class TransactionManager:
    def __init__(self, dataflow_instance):
        self._active_transactions = {}  # Python dict

    @contextmanager
    def transaction(self, isolation_level="READ_COMMITTED"):
        transaction_context = {"status": "active", ...}
        yield transaction_context
        transaction_context["status"] = "committed"  # Sets string, not SQL COMMIT
```

This layer does NOT issue SQL BEGIN/COMMIT/ROLLBACK directly.

### Layer 2: Engine DDL Transactions (REAL)

**File**: `apps/kailash-dataflow/src/dataflow/core/engine.py:4076-4131`

The engine uses REAL SQLAlchemy transactions for DDL operations:

```python
def _execute_ddl_with_transaction(self, ddl_statement):
    transaction = connection.begin()       # Real SQL BEGIN
    connection.execute(ddl_statement)
    transaction.commit()                   # Real SQL COMMIT
    # On error:
    transaction.rollback()                 # Real SQL ROLLBACK
```

Also `_execute_multi_statement_ddl()` wraps multiple DDL statements in a single transaction.

### Layer 3: Transaction Workflow Nodes (MOCKED)

**File**: `apps/kailash-dataflow/src/dataflow/nodes/transaction_nodes.py` (300 lines)

Five dedicated workflow node classes:

| Class                                | Lines   | Status                                   |
| ------------------------------------ | ------- | ---------------------------------------- |
| `TransactionScopeNode`               | 11-96   | MOCK - uses dict-based mock transactions |
| `TransactionCommitNode`              | 98-132  | MOCK - handles mock transactions only    |
| `TransactionRollbackNode`            | 135-184 | MOCK - simulated rollback                |
| `TransactionSavepointNode`           | 187-240 | PARTIAL - attempts async SQL execution   |
| `TransactionRollbackToSavepointNode` | 243-300 | PARTIAL - attempts async SQL execution   |

**Critical Finding**: TransactionScopeNode (lines 63-88) uses mock dictionaries:

```python
# This is a real DataFlow instance with models
# Store mock transaction info for testing
mock_connection = {"type": "mock", "id": f"conn_{self.id}"}
mock_transaction = {"type": "mock", "id": f"tx_{self.id}", "active": True}
```

Lines 90-95 explicitly state:

```python
# Real implementation would use actual async connection
# This is a limitation of mixing sync nodes with async database operations
raise NodeExecutionError(
    "Transaction nodes require async runtime support..."
)
```

### Layer 4: Transaction Manager Node (Delegates to SDK)

**File**: `apps/kailash-dataflow/src/dataflow/nodes/transaction_manager.py` (409 lines)

`DataFlowTransactionManagerNode` extends AsyncNode and delegates to SDK's `DistributedTransactionManagerNode`:

- **Saga pattern** (lines 183-260): Forward execution with compensation
- **Two-phase commit** (lines 261-361): Prepare/commit/abort phases
- **Compensating transactions** (lines 363-368): Explicit rollback

This layer delegates to the SDK transaction manager rather than implementing SQL directly.

### Layer 5: Adapter-Level Transactions (REAL SQL)

**File**: `apps/kailash-dataflow/src/dataflow/adapters/postgresql.py:411-468`

```python
class PostgreSQLTransaction:
    async def __aenter__(self):
        self.connection = await self.connection_pool.acquire()
        self.transaction = self.connection.transaction()
        await self.transaction.start()      # Real asyncpg BEGIN

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.transaction.commit()   # Real SQL COMMIT
        else:
            await self.transaction.rollback() # Real SQL ROLLBACK
```

**File**: `apps/kailash-dataflow/src/dataflow/adapters/sqlite.py:818-899`

```python
class SQLiteTransaction:
    async def __aenter__(self):
        await self.connection.execute("BEGIN")  # Real SQL BEGIN

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            await self.connection.commit()       # Real SQL COMMIT
        else:
            await self.connection.rollback()     # Real SQL ROLLBACK
```

Both `PostgreSQLTransaction` and `SQLiteTransaction` issue real SQL commands.

---

## Corrected Assessment

| Layer                    | What                   | Status    | Notes                                                 |
| ------------------------ | ---------------------- | --------- | ----------------------------------------------------- |
| `db.transaction()` API   | High-level coordinator | SIMPLE    | Tracks state in dicts, no SQL commands                |
| Engine DDL               | Schema operations      | REAL      | `connection.begin()`/`commit()`/`rollback()`          |
| Transaction Nodes        | Workflow-level control | MOCKED    | Dict-based mocks, not real SQL                        |
| Transaction Manager Node | Enterprise patterns    | DELEGATES | Saga, 2PC via SDK's DistributedTransactionManagerNode |
| Adapter Transactions     | Database-level ACID    | REAL      | PostgreSQL + SQLite both issue real SQL               |

### The Two-Tier Gap

The codebase has a **two-tier transaction system**:

1. **Adapter level (REAL)**: `PostgreSQLTransaction` and `SQLiteTransaction` issue real SQL `BEGIN`/`COMMIT`/`ROLLBACK`
2. **Node level (MOCKED)**: `TransactionScopeNode` and related nodes use dict-based mock transactions due to sync/async impedance mismatch

The `db.transaction()` API does not delegate to either layer. Users who need ACID guarantees should use the adapter-level transactions directly or through the engine's DDL transaction methods.

### Severity: MEDIUM

- Real transaction capabilities exist at the adapter level
- But the high-level API (`db.transaction()`) and workflow nodes don't connect to them
- The sync/async mismatch between workflow nodes and async database adapters is the root cause

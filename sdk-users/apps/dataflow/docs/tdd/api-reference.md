# DataFlow TDD API Reference

**Complete reference for all TDD fixtures, utilities, and configuration options**

## Core Infrastructure

### Environment Configuration

#### `is_tdd_mode() -> bool`
Check if DataFlow is running in TDD mode.

```python
from dataflow.testing.tdd_support import is_tdd_mode

# Enable TDD mode
import os
os.environ["DATAFLOW_TDD_MODE"] = "true"

if is_tdd_mode():
    print("TDD infrastructure is active")
```

**Returns**: `True` if TDD mode is enabled, `False` otherwise

**Environment Variables**:
- `DATAFLOW_TDD_MODE`: Set to `"true"`, `"yes"`, `"1"`, `"on"`, or `"enabled"`

---

### Core Classes

#### `TDDTestContext`
Test context for TDD infrastructure with savepoint-based isolation.

```python
from dataflow.testing.tdd_support import TDDTestContext

context = TDDTestContext(
    test_id="custom_test_id",           # Optional: auto-generated if None
    isolation_level="READ COMMITTED",   # PostgreSQL isolation level
    timeout=30,                         # Test timeout in seconds
    rollback_on_error=True,            # Auto-rollback on test failure
    savepoint_name="custom_sp",        # Optional: auto-generated if None
)
```

**Attributes**:
- `test_id: str` - Unique test identifier
- `isolation_level: str` - PostgreSQL transaction isolation level
- `timeout: int` - Maximum test execution timeout
- `savepoint_name: str` - PostgreSQL savepoint name
- `rollback_on_error: bool` - Whether to rollback on failure
- `connection: Optional[asyncpg.Connection]` - Active database connection
- `savepoint_created: bool` - Whether savepoint has been created
- `metadata: Dict[str, Any]` - Additional test metadata

#### `TDDDatabaseManager`
Database connection manager for TDD infrastructure.

```python
from dataflow.testing.tdd_support import get_database_manager

db_manager = get_database_manager()

# Initialize with custom connection string
await db_manager.initialize(
    connection_string="postgresql://user:pass@localhost:5432/test_db"
)

# Get connection for test context
connection = await db_manager.get_test_connection(context)

# Cleanup connections
await db_manager.cleanup_test_connection(context)
await db_manager.close()
```

**Methods**:
- `async initialize(connection_string=None)` - Initialize connection pool
- `async get_test_connection(context)` - Get connection for test
- `async cleanup_test_connection(context)` - Release test connection
- `async cleanup_all_test_connections()` - Release all connections
- `async close()` - Close manager and all connections

#### `TDDTransactionManager`
Transaction and savepoint manager for test isolation.

```python
from dataflow.testing.tdd_support import get_transaction_manager

tx_manager = get_transaction_manager()

# Begin test transaction with savepoint
await tx_manager.begin_test_transaction(connection, context)

# End transaction (rollback by default for isolation)
await tx_manager.end_test_transaction(connection, context, rollback=True)

# Manual savepoint operations
await tx_manager.create_savepoint(connection, context)
await tx_manager.rollback_to_savepoint(connection, context)
await tx_manager.release_savepoint(connection, context)
```

**Methods**:
- `async begin_test_transaction(connection, context)` - Start test transaction
- `async end_test_transaction(connection, context, rollback=None)` - End transaction
- `async create_savepoint(connection, context)` - Create savepoint
- `async rollback_to_savepoint(connection, context)` - Rollback to savepoint
- `async release_savepoint(connection, context)` - Release savepoint

---

## Core Fixtures

### Basic TDD Fixtures

#### `tdd_test_context`
Async context manager for TDD test execution with automatic cleanup.

```python
@pytest.mark.asyncio
async def test_with_context(tdd_test_context):
    """Test using basic TDD context"""
    context = tdd_test_context

    # Direct database access
    connection = context.connection
    result = await connection.fetchval("SELECT 1")
    assert result == 1

    # Context info
    print(f"Test ID: {context.test_id}")
    print(f"Savepoint: {context.savepoint_name}")

    # Automatic cleanup on exit
```

**Provides**: `TDDTestContext` with active database connection and savepoint

#### `tdd_dataflow`
DataFlow instance optimized for TDD testing.

```python
@pytest.mark.asyncio
async def test_with_dataflow(tdd_dataflow):
    """Test using TDD-optimized DataFlow"""
    df = tdd_dataflow

    @df.model
    class TestModel:
        name: str
        value: int = 0

    # Fast table creation (existing_schema_mode=True)
    df.create_tables()

    # Standard DataFlow operations
    result = await df.TestModel.create({"name": "test", "value": 42})
    assert result["success"] is True

    # Automatic cleanup via TDD infrastructure
```

**Configuration**:
- `existing_schema_mode=True` - No table recreation
- `auto_migrate=False` - No migrations
- `cache_enabled=False` - No caching for isolation
- `pool_size=1` - Minimal pool
- `echo=False` - No SQL logging

#### `fast_test_db`
Fast database connection for TDD tests using savepoint isolation.

```python
@pytest.mark.asyncio
async def test_with_fast_db(fast_test_db):
    """Test using fast database connection"""
    connection = fast_test_db

    # Sub-100ms database operations
    await connection.execute("""
        CREATE TEMP TABLE test_table (
            id SERIAL PRIMARY KEY,
            data TEXT
        )
    """)

    await connection.execute(
        "INSERT INTO test_table (data) VALUES ($1)",
        "test data"
    )

    count = await connection.fetchval("SELECT COUNT(*) FROM test_table")
    assert count == 1
```

**Provides**: `asyncpg.Connection` with active savepoint

---

## Enhanced TDD Fixtures

### Performance-Optimized Fixtures

#### `enhanced_tdd_context`
Enhanced TDD context with full performance optimization.

```python
@pytest.mark.asyncio
async def test_enhanced_performance(enhanced_tdd_context):
    """Test with all performance optimizations enabled"""
    context = enhanced_tdd_context

    # Performance metrics available
    metrics = context.metrics
    assert metrics.setup_time_ms < 10  # Setup under 10ms

    # All optimizations enabled
    assert context.preheated_pool is True
    assert context.cached_schema is True
    assert context.parallel_safe is True
    assert context.memory_optimized is True
```

**Features**:
- Preheated connection pools (<5ms acquisition)
- Schema caching (sub-10ms operations)
- Parallel execution support
- Real-time performance monitoring
- Memory optimization

#### `preheated_dataflow`
DataFlow instance with preheated connection pool for maximum performance.

```python
@pytest.mark.asyncio
async def test_preheated_performance(preheated_dataflow):
    """Test with preheated connection pool"""
    df, pool_stats = preheated_dataflow

    # Connection immediately available
    assert pool_stats["preheated"] is True
    assert pool_stats["acquisition_time_ms"] < 5

    # Normal DataFlow operations at maximum speed
    @df.model
    class FastModel:
        name: str

    df.create_tables()
    result = await df.FastModel.create({"name": "fast test"})
    assert result["success"] is True
```

**Returns**: `(DataFlow, pool_statistics)`

#### `cached_schema_models`
Pre-cached test models for immediate use without DDL overhead.

```python
@pytest.mark.asyncio
async def test_cached_models(cached_schema_models):
    """Test with pre-cached model schemas"""
    User, Product, Order, cache_stats = cached_schema_models

    # Models immediately available
    assert cache_stats["cache_hits"] > 0
    assert cache_stats["ddl_operations"] == 0

    # Standard model usage
    user_data = {"name": "Alice", "email": "alice@example.com"}
    # These would work with actual DataFlow instance:
    # user = await df.User.create(user_data)
```

**Returns**: `(User, Product, Order, cache_statistics)`

**Models Provided**:
- `User`: name, email, active, created_at, metadata
- `Product`: name, price, category, in_stock, sku, tags
- `Order`: user_id, product_id, quantity, total_price, status

---

### Parallel Execution Fixtures

#### `parallel_test_execution`
Thread-safe parallel test execution support.

```python
@pytest.mark.asyncio
async def test_parallel_safe(parallel_test_execution):
    """Test designed for parallel execution"""
    context, isolation_id, resource_manager = parallel_test_execution

    # Each parallel test gets unique isolation
    assert isolation_id.startswith("iso_")
    assert context.isolation_level == "SERIALIZABLE"

    # Resource allocation for deadlock prevention
    if resource_manager.allocate("database_table_users"):
        # Safe to operate on users table
        pass

    # Automatic resource cleanup
```

**Features**:
- SERIALIZABLE isolation level
- Unique isolation identifiers
- Resource allocation management
- Deadlock prevention
- Thread-safe execution

#### `tdd_parallel_safe`
Simplified parallel-safe execution context.

```python
@pytest.mark.asyncio
async def test_simple_parallel(tdd_parallel_safe):
    """Simple parallel-safe test"""
    context, unique_id = tdd_parallel_safe

    # Unique context for this parallel execution
    assert unique_id.startswith("parallel_")
    assert len(unique_id) == 21  # parallel_ + 12 char hex

    # Safe for concurrent execution
    connection = context.connection
    table_name = f"test_table_{unique_id.split('_')[1]}"

    await connection.execute(f"""
        CREATE TEMP TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            data TEXT
        )
    """)
```

**Returns**: `(TDDTestContext, unique_identifier)`

---

### Performance Monitoring Fixtures

#### `performance_monitored_test`
Test execution with real-time performance monitoring.

```python
@pytest.mark.asyncio
async def test_with_monitoring(performance_monitored_test):
    """Test with performance monitoring"""
    monitor, metrics_collector, alert_handler = performance_monitored_test

    # Measure specific operations
    with metrics_collector.measure("database_operation"):
        # Database work here
        pass

    # Check performance metrics
    assert metrics_collector.current_metrics.duration_ms < 100

    # Check for performance alerts
    alerts = alert_handler.get_alerts()
    assert len(alerts) == 0  # No performance issues
```

**Features**:
- Real-time performance measurement
- Regression detection
- Alert handling
- Comprehensive metrics collection

#### `tdd_performance_tracker`
Simple performance tracking for validation.

```python
def test_performance_validation(tdd_performance_tracker):
    """Validate test performance targets"""
    import time

    start = time.time()
    # Test operations
    time.sleep(0.05)  # 50ms work

    duration_ms = (time.time() - start) * 1000

    # Automatic performance tracking
    # Warning logged if test exceeds 100ms
    assert duration_ms < 100
```

**Features**:
- Automatic performance tracking
- 100ms target validation
- Performance data collection
- Regression warnings

---

### Memory Management Fixtures

#### `memory_optimized_test`
Test execution with memory optimization and leak detection.

```python
@pytest.mark.asyncio
async def test_memory_efficient(memory_optimized_test):
    """Test with memory optimization"""
    optimizer, tracker, cleanup_manager = memory_optimized_test

    # Track memory usage
    with tracker.track():
        # Memory-intensive operations
        data = list(range(10000))
        processed = [x * 2 for x in data]

    # Validate memory usage
    delta_mb = tracker.get_memory_delta()
    assert delta_mb < 5.0  # Under 5MB increase

    # Manual cleanup if needed
    cleanup_manager.force_cleanup()
```

**Features**:
- Memory usage tracking
- Leak detection (>5MB threshold)
- Automatic optimization
- Manual cleanup controls

---

### Comprehensive Testing Fixtures

#### `comprehensive_tdd_benchmark`
Complete benchmark environment with all optimizations.

```python
@pytest.mark.asyncio
async def test_complete_benchmark(comprehensive_tdd_benchmark):
    """Comprehensive performance benchmark"""
    benchmark_context = comprehensive_tdd_benchmark

    # All optimizations enabled
    assert benchmark_context.optimizations_enabled["connection_pooling"] is True
    assert benchmark_context.optimizations_enabled["schema_caching"] is True
    assert benchmark_context.optimizations_enabled["parallel_execution"] is True

    # Performance validation
    assert benchmark_context.validate_performance_target(100.0)

    # Comprehensive reporting
    report = benchmark_context.get_comprehensive_report()
    assert report["target_achieved"] is True
```

**Features**:
- All performance optimizations
- Complete metrics collection
- Target validation
- Comprehensive reporting

---

## Test Data Fixtures

### Pre-seeded Data

#### `tdd_seeded_data`
Pre-populated test data for scenarios requiring existing relationships.

```python
@pytest.mark.asyncio
async def test_with_seeded_data(tdd_seeded_data):
    """Test with pre-populated data"""
    context, data, models = tdd_seeded_data

    # Access seeded data
    users = data["users"]        # 3 users
    products = data["products"]  # 5 products
    orders = data["orders"]      # 3 orders

    assert len(users) == 3
    assert all(user["email"].endswith("@example.com") for user in users)

    # Access models for additional operations
    User = models["User"]
    Product = models["Product"]
    Order = models["Order"]
```

**Data Structure**:
```python
{
    "users": [
        {"name": "Alice Smith", "email": "alice@example.com", "active": True},
        {"name": "Bob Jones", "email": "bob@example.com", "active": True},
        {"name": "Charlie Brown", "email": "charlie@example.com", "active": False}
    ],
    "products": [
        {"name": "Laptop", "price": 999.99, "category": "electronics"},
        {"name": "Mouse", "price": 29.99, "category": "electronics"},
        {"name": "Coffee", "price": 12.99, "category": "food"},
        {"name": "Notebook", "price": 5.99, "category": "office"},
        {"name": "Pen", "price": 1.99, "category": "office"}
    ],
    "orders": [
        {"user_id": 1, "product_id": 1, "quantity": 1, "total_price": 999.99, "status": "completed"},
        {"user_id": 2, "product_id": 2, "quantity": 2, "total_price": 59.98, "status": "pending"},
        {"user_id": 1, "product_id": 3, "quantity": 1, "total_price": 12.99, "status": "shipped"}
    ]
}
```

---

## Utility Functions

### Context Management

#### `tdd_test_context()`
Async context manager for manual TDD context creation.

```python
from dataflow.testing.tdd_support import tdd_test_context

async def custom_test_function():
    async with tdd_test_context(
        test_id="custom_test",
        isolation_level="SERIALIZABLE",
        timeout=60,
        rollback_on_error=True
    ) as context:
        # Test operations with custom context
        connection = context.connection
        # ... test code ...
    # Automatic cleanup
```

**Parameters**:
- `test_id: str = None` - Custom test identifier
- `isolation_level: str = "READ COMMITTED"` - PostgreSQL isolation level
- `timeout: int = 30` - Test timeout in seconds
- `rollback_on_error: bool = True` - Auto-rollback on failure
- `**kwargs` - Additional metadata

### Infrastructure Management

#### `setup_tdd_infrastructure()`
Initialize TDD infrastructure for test session.

```python
from dataflow.testing.tdd_support import setup_tdd_infrastructure

# In conftest.py
@pytest.fixture(scope="session", autouse=True)
async def initialize_tdd():
    await setup_tdd_infrastructure()
    yield
    await teardown_tdd_infrastructure()
```

#### `teardown_tdd_infrastructure()`
Cleanup TDD infrastructure after test session.

```python
from dataflow.testing.tdd_support import teardown_tdd_infrastructure

# Cleanup after test session
await teardown_tdd_infrastructure()
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATAFLOW_TDD_MODE` | `"false"` | Enable TDD mode |
| `TEST_DATABASE_URL` | `postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test` | Test database connection |
| `DATAFLOW_TDD_POOL_SIZE` | `5` | Connection pool size |
| `DATAFLOW_TDD_TIMEOUT` | `30` | Default test timeout |

### DataFlow TDD Configuration

```python
TDD_CONFIG = {
    "database_url": "postgresql://user:pass@host:port/db",
    "existing_schema_mode": True,     # No table recreation
    "auto_migrate": False,            # No automatic migrations
    "cache_enabled": False,           # Disable caching for isolation
    "pool_size": 1,                   # Minimal connection pool
    "pool_max_overflow": 0,           # No overflow connections
    "pool_timeout": 5,                # Fast connection timeout
    "pool_recycle": 30,               # Aggressive recycling
    "pool_pre_ping": True,            # Verify connections
    "echo": False,                    # No SQL logging
    "monitoring": False,              # No monitoring overhead
}
```

### Performance Targets

| Metric | Target | Description |
|--------|--------|-------------|
| Individual Test | <100ms | Single test execution time |
| Fixture Setup | <5ms | Test fixture initialization |
| Schema Operations | <10ms | DDL operations with caching |
| Connection Acquisition | <5ms | Database connection time |
| Memory Overhead | <2MB | Per-test context memory |
| Parallel Success Rate | 100% | Concurrent test isolation |

---

## Performance Optimization

### Enhanced Performance Features

#### Connection Pool Preheating
```python
# Automatic connection preheating
pool_manager = get_pool_manager()
pool = await pool_manager.create_optimized_pool(
    pool_id="test_pool",
    connection_string=database_url,
    min_size=2,
    max_size=5,
    preheat=True  # Warm connections on startup
)
```

#### Schema Caching
```python
# Schema caching for DDL operations
schema_cache = get_schema_cache()
schema_cache.cache_schema("User", {
    "users": "CREATE TABLE users (id SERIAL PRIMARY KEY, name VARCHAR(255))"
})

# Fast retrieval
if schema_cache.is_schema_cached("User"):
    cached_ddl = schema_cache.get_cached_schema("User")
```

#### Memory Optimization
```python
# Memory optimization features
memory_optimizer = get_memory_optimizer()

# Track memory usage
snapshot = memory_optimizer.take_memory_snapshot("test_start")

# Object tracking
memory_optimizer.track_object(large_object, "large_data_structure")

# Optimize memory usage
memory_optimizer.optimize_memory()
```

---

## Error Handling

### Common Exceptions

#### `TDDInfrastructureError`
Raised when TDD infrastructure fails to initialize.

```python
try:
    await setup_tdd_infrastructure()
except TDDInfrastructureError as e:
    print(f"TDD setup failed: {e}")
    # Check database connectivity
    # Verify environment configuration
```

#### `SavepointError`
Raised when savepoint operations fail.

```python
try:
    await tx_manager.create_savepoint(connection, context)
except SavepointError as e:
    print(f"Savepoint creation failed: {e}")
    # Check transaction state
    # Verify connection validity
```

#### `ConnectionPoolExhaustedError`
Raised when connection pool is exhausted.

```python
try:
    connection = await db_manager.get_test_connection(context)
except ConnectionPoolExhaustedError as e:
    print(f"No connections available: {e}")
    # Increase pool size
    # Check for connection leaks
```

### Error Recovery

```python
# Automatic error recovery in fixtures
@pytest.fixture
async def resilient_tdd_context():
    retries = 3
    for attempt in range(retries):
        try:
            async with tdd_test_context() as context:
                yield context
                break
        except TDDInfrastructureError:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(0.1)  # Brief pause before retry
```

---

## Best Practices

### Fixture Usage Guidelines

1. **Use Appropriate Fixture**: Choose the right fixture for your test complexity
   - `tdd_test_context` for basic database operations
   - `tdd_dataflow` for model-based testing
   - `enhanced_tdd_context` for performance-critical tests

2. **Avoid Mixing Fixtures**: Don't combine TDD and traditional fixtures
   ```python
   # AVOID
   def test_mixed_approach(clean_database, tdd_test_context):
       pass

   # PREFER
   @pytest.mark.asyncio
   async def test_tdd_only(tdd_test_context):
       pass
   ```

3. **Performance Monitoring**: Use performance fixtures for regression testing
   ```python
   @pytest.mark.asyncio
   async def test_performance_critical(performance_monitored_test):
       # Critical path testing with monitoring
       pass
   ```

### Test Organization

```python
# Organize tests by performance requirements
@pytest.mark.tdd  # Basic TDD tests
@pytest.mark.performance  # Performance-critical tests
@pytest.mark.parallel  # Parallel-safe tests
@pytest.mark.memory  # Memory-sensitive tests
```

### CI/CD Integration

```python
# Performance validation in CI
def test_tdd_performance_gate():
    """Gate test for CI/CD performance requirements"""
    # Run representative test suite
    # Validate all tests complete under time budget
    # Fail build if performance degrades
    pass
```

This API reference provides complete coverage of DataFlow's TDD infrastructure, enabling teams to achieve enterprise-grade test performance with production-quality isolation.

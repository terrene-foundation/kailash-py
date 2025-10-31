# DataFlow TDD Troubleshooting Guide

**Common issues and solutions for DataFlow TDD infrastructure**

This guide provides solutions to common problems encountered when using DataFlow's TDD infrastructure, organized by symptom and category.

## Quick Diagnosis Checklist

### ✅ TDD Mode Verification

```python
# First, verify TDD mode is properly enabled
from dataflow.testing.tdd_support import is_tdd_mode

def check_tdd_setup():
    """Verify TDD infrastructure is properly configured"""
    print("TDD Mode Enabled:", is_tdd_mode())

    if not is_tdd_mode():
        print("❌ TDD mode not enabled")
        print("Solution: Set DATAFLOW_TDD_MODE=true")
        return False

    print("✅ TDD mode is enabled")
    return True

# Run this first if experiencing issues
check_tdd_setup()
```

### ✅ Database Connectivity Check

```python
import asyncpg
import asyncio

async def check_database_connectivity():
    """Verify database connection works"""
    test_db_url = "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"

    try:
        connection = await asyncpg.connect(test_db_url)
        result = await connection.fetchval("SELECT 1")
        await connection.close()

        print("✅ Database connectivity working")
        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Solutions:")
        print("1. Check PostgreSQL is running: pg_isready -h localhost -p 5433")
        print("2. Verify credentials and database exist")
        print("3. Check firewall/network settings")
        return False

# Run if getting connection errors
asyncio.run(check_database_connectivity())
```

## Performance Issues

### Tests Exceeding 100ms Target

#### Symptom
```
test_user_creation PASSED [234ms]  # Exceeds 100ms target
```

#### Diagnosis

```python
import time
import pytest

@pytest.mark.asyncio
async def diagnose_slow_test(tdd_test_context):
    """Diagnose why a test is running slowly"""
    context = tdd_test_context

    # Time fixture setup
    setup_start = time.time()
    connection = context.connection
    setup_time = (time.time() - setup_start) * 1000
    print(f"Fixture setup: {setup_time:.2f}ms")

    # Time schema creation
    schema_start = time.time()
    await connection.execute("""
        CREATE TEMP TABLE test_table (
            id SERIAL PRIMARY KEY,
            data TEXT
        )
    """)
    schema_time = (time.time() - schema_start) * 1000
    print(f"Schema creation: {schema_time:.2f}ms")

    # Time data operations
    data_start = time.time()
    await connection.execute("INSERT INTO test_table (data) VALUES ('test')")
    result = await connection.fetchval("SELECT COUNT(*) FROM test_table")
    data_time = (time.time() - data_start) * 1000
    print(f"Data operations: {data_time:.2f}ms")

    total_time = setup_time + schema_time + data_time
    print(f"Total measured: {total_time:.2f}ms")

    # Identify bottleneck
    if setup_time > 20:
        print("⚠️  Fixture setup is slow - check connection pool")
    if schema_time > 20:
        print("⚠️  Schema creation is slow - consider templates")
    if data_time > 30:
        print("⚠️  Data operations are slow - check query complexity")
```

#### Solutions

**1. Connection Pool Optimization**
```python
# Problem: New connections being created per test
# Solution: Use session-scoped connection pool

@pytest.fixture(scope="session")
async def fast_connection_pool():
    """Session-scoped connection pool for speed"""
    pool = await asyncpg.create_pool(
        test_database_url,
        min_size=3,        # Keep connections warm
        max_size=8,        # Reasonable limit
        command_timeout=5,  # Fast timeout
        server_settings={
            "jit": "off",   # Disable JIT for small queries
        }
    )
    yield pool
    await pool.close()
```

**2. Schema Template Optimization**
```python
# Problem: Complex DDL operations per test
# Solution: Pre-defined schema templates

FAST_SCHEMA_TEMPLATES = {
    "simple_user": "CREATE TEMP TABLE {name} (id SERIAL, name TEXT, email TEXT)",
    "simple_order": "CREATE TEMP TABLE {name} (id SERIAL, user_id INT, total DECIMAL)",
}

@pytest.mark.asyncio
async def test_with_fast_schema(tdd_test_context):
    """Use fast schema template"""
    context = tdd_test_context
    connection = context.connection

    # Fast schema creation
    schema_sql = FAST_SCHEMA_TEMPLATES["simple_user"].format(name="users")
    await connection.execute(schema_sql)
```

**3. Data Minimization**
```python
# Problem: Too much test data being created
# Solution: Minimal essential data only

@pytest.mark.asyncio
async def test_with_minimal_data(tdd_test_context):
    """Use minimal data for faster tests"""
    context = tdd_test_context
    connection = context.connection

    # Minimal schema
    await connection.execute("CREATE TEMP TABLE t (id SERIAL, v TEXT)")

    # Minimal data - just what's needed for test
    await connection.execute("INSERT INTO t (v) VALUES ('test')")

    # Single assertion
    count = await connection.fetchval("SELECT COUNT(*) FROM t")
    assert count == 1
```

### Connection Pool Exhaustion

#### Symptom
```
asyncpg.exceptions.ConnectionError: connection pool exhausted
pytest.TimeoutError: Test timed out after 30 seconds
```

#### Diagnosis
```python
async def diagnose_connection_pool():
    """Diagnose connection pool issues"""
    from dataflow.testing.tdd_support import get_database_manager

    db_manager = get_database_manager()

    # Check current pool status
    if hasattr(db_manager, 'connection_pool') and db_manager.connection_pool:
        pool = db_manager.connection_pool
        print(f"Pool size: {pool.get_size()}")
        print(f"Pool min size: {pool.get_min_size()}")
        print(f"Pool max size: {pool.get_max_size()}")
        print(f"Pool idle connections: {pool.get_idle_size()}")

        if pool.get_size() >= pool.get_max_size():
            print("❌ Pool exhausted - no available connections")
        else:
            print("✅ Pool has available connections")
    else:
        print("❌ No connection pool found")
```

#### Solutions

**1. Increase Pool Size**
```python
# For test environments with many parallel tests
TEST_POOL_CONFIG = {
    "min_size": 5,    # Increased minimum
    "max_size": 20,   # Increased maximum
    "command_timeout": 10  # Faster timeout to release stuck connections
}
```

**2. Proper Connection Cleanup**
```python
@pytest.fixture
async def managed_connection():
    """Properly managed connection with guaranteed cleanup"""
    db_manager = get_database_manager()
    context = TDDTestContext()

    connection = None
    try:
        connection = await db_manager.get_test_connection(context)
        yield connection
    finally:
        if connection:
            await db_manager.cleanup_test_connection(context)
```

**3. Connection Leak Detection**
```python
@pytest.fixture(autouse=True)
async def detect_connection_leaks():
    """Detect connection leaks automatically"""
    db_manager = get_database_manager()

    # Count connections before test
    initial_connections = len(db_manager.active_connections)

    yield

    # Count connections after test
    final_connections = len(db_manager.active_connections)

    if final_connections > initial_connections:
        leaked = final_connections - initial_connections
        pytest.warns(UserWarning, f"Connection leak detected: {leaked} connections")
```

## Infrastructure Issues

### TDD Mode Not Working

#### Symptom
```python
# Tests fall back to traditional approach
# No performance improvement
# Fixtures not available
```

#### Solutions

**1. Environment Variable Setup**
```bash
# Multiple ways to set TDD mode
export DATAFLOW_TDD_MODE=true
export DATAFLOW_TDD_MODE=1
export DATAFLOW_TDD_MODE=yes
export DATAFLOW_TDD_MODE=on

# Verify setting
echo $DATAFLOW_TDD_MODE
```

**2. Programmatic Activation**
```python
# In conftest.py or test file
import os
os.environ["DATAFLOW_TDD_MODE"] = "true"

# Verify activation
from dataflow.testing.tdd_support import is_tdd_mode
assert is_tdd_mode(), "TDD mode should be enabled"
```

**3. Fixture Import Issues**
```python
# Ensure proper imports in conftest.py
import pytest
import os

# Enable TDD mode
os.environ["DATAFLOW_TDD_MODE"] = "true"

# Import TDD fixtures
from dataflow.testing.tdd_support import (
    setup_tdd_infrastructure,
    teardown_tdd_infrastructure
)

@pytest.fixture(scope="session", autouse=True)
async def tdd_session():
    """Session-wide TDD infrastructure"""
    await setup_tdd_infrastructure()
    yield
    await teardown_tdd_infrastructure()
```

### Database Connection Failures

#### Symptom
```
asyncpg.exceptions.InvalidCatalogNameError: database "dataflow_test" does not exist
asyncpg.exceptions.InvalidPasswordError: password authentication failed
Connection refused on port 5433
```

#### Solutions

**1. Database Creation**
```sql
-- Create test database and user
CREATE DATABASE dataflow_test;
CREATE USER dataflow_test WITH PASSWORD 'dataflow_test_password';
GRANT ALL PRIVILEGES ON DATABASE dataflow_test TO dataflow_test;

-- Verify connection
\c dataflow_test dataflow_test
SELECT current_database(), current_user;
```

**2. Connection String Verification**
```python
def verify_connection_string():
    """Verify database connection string components"""
    import os
    from urllib.parse import urlparse

    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
    )

    parsed = urlparse(db_url)

    print(f"Scheme: {parsed.scheme}")
    print(f"Username: {parsed.username}")
    print(f"Password: {'*' * len(parsed.password) if parsed.password else 'None'}")
    print(f"Host: {parsed.hostname}")
    print(f"Port: {parsed.port}")
    print(f"Database: {parsed.path[1:]}")  # Remove leading /

    return parsed
```

**3. PostgreSQL Service Check**
```bash
# Check if PostgreSQL is running
pg_isready -h localhost -p 5433

# Start PostgreSQL if needed
brew services start postgresql@13  # macOS
sudo systemctl start postgresql    # Linux
```

### Savepoint Failures

#### Symptom
```
asyncpg.exceptions.InvalidTransactionStateError: cannot rollback - no transaction is active
asyncpg.exceptions.InvalidSavepointNameError: savepoint "sp_abc123" does not exist
```

#### Diagnosis
```python
async def diagnose_savepoint_issue(connection):
    """Diagnose savepoint-related issues"""
    try:
        # Check transaction status
        tx_status = await connection.fetchval("SELECT txid_current_if_assigned()")
        print(f"Transaction ID: {tx_status}")

        # Check if in transaction
        in_tx = await connection.fetchval("SELECT (SELECT count(*) FROM pg_stat_activity WHERE pid = pg_backend_pid() AND state LIKE '%transaction%') > 0")
        print(f"In transaction: {in_tx}")

        # Check active savepoints
        savepoints = await connection.fetch("""
            SELECT name FROM pg_savepoints
        """)
        print(f"Active savepoints: {[sp['name'] for sp in savepoints]}")

    except Exception as e:
        print(f"Diagnosis error: {e}")
```

#### Solutions

**1. Proper Transaction Management**
```python
async def robust_savepoint_test():
    """Test with robust savepoint management"""
    from dataflow.testing.tdd_support import get_transaction_manager

    db_manager = get_database_manager()
    tx_manager = get_transaction_manager()

    await db_manager.initialize()
    context = TDDTestContext()

    try:
        connection = await db_manager.get_test_connection(context)

        # Begin transaction properly
        await tx_manager.begin_test_transaction(connection, context)

        # Test operations here
        await connection.execute("SELECT 1")

        # End transaction (rollback by default)
        await tx_manager.end_test_transaction(connection, context)

    finally:
        await db_manager.cleanup_test_connection(context)
```

**2. Manual Savepoint Recovery**
```python
async def recover_from_savepoint_error(connection, context):
    """Recover from savepoint errors"""
    try:
        # Try to rollback to savepoint
        await connection.execute(f"ROLLBACK TO SAVEPOINT {context.savepoint_name}")
    except:
        try:
            # If that fails, try to rollback transaction
            await connection.execute("ROLLBACK")
        except:
            # If that fails, close and recreate connection
            await connection.close()
            # Create new connection
            pass
```

## Test-Specific Issues

### Fixture Not Found Errors

#### Symptom
```
pytest.fixtures.FixtureNotFoundError: 'tdd_test_context' fixture not found
AttributeError: 'NoneType' object has no attribute 'connection'
```

#### Solutions

**1. Import TDD Fixtures Properly**
```python
# In conftest.py - ensure all fixtures are available
import os
import pytest

# Enable TDD mode first
os.environ["DATAFLOW_TDD_MODE"] = "true"

# Import fixtures to make them available
from dataflow.testing.tdd_support import (
    setup_tdd_infrastructure,
    teardown_tdd_infrastructure,
    tdd_test_context
)

# Make fixtures discoverable
pytest_plugins = ["dataflow.testing.tdd_support"]
```

**2. Manual Fixture Registration**
```python
# If automatic discovery fails, register manually
@pytest.fixture
async def tdd_test_context():
    """Manual TDD test context fixture"""
    from dataflow.testing.tdd_support import tdd_test_context as tdd_ctx

    async with tdd_ctx() as context:
        yield context
```

### Parallel Test Failures

#### Symptom
```
Multiple tests failing when run in parallel
Race conditions between tests
Intermittent failures that don't reproduce in isolation
```

#### Solutions

**1. Use Parallel-Safe Fixtures**
```python
@pytest.mark.asyncio
async def test_parallel_safe(tdd_parallel_safe):
    """Use parallel-safe fixtures for concurrent tests"""
    context, unique_id = tdd_parallel_safe

    # Each test gets unique isolation
    table_name = f"test_table_{unique_id.split('_')[1]}"

    await context.connection.execute(f"""
        CREATE TEMP TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            data TEXT
        )
    """)
```

**2. Resource Allocation**
```python
class TestResourceManager:
    """Manage shared resources for parallel tests"""

    def __init__(self):
        self.allocated_resources = set()
        self.lock = asyncio.Lock()

    async def allocate(self, resource_name: str) -> bool:
        """Allocate a resource for exclusive use"""
        async with self.lock:
            if resource_name in self.allocated_resources:
                return False
            self.allocated_resources.add(resource_name)
            return True

    async def release(self, resource_name: str):
        """Release a resource"""
        async with self.lock:
            self.allocated_resources.discard(resource_name)

# Use in tests
@pytest.fixture
async def resource_manager():
    manager = TestResourceManager()
    yield manager
    # Cleanup any remaining allocations
    manager.allocated_resources.clear()
```

### Memory Issues

#### Symptom
```
MemoryError: unable to allocate memory
Process killed by OS (OOM)
Gradual memory increase across test runs
```

#### Solutions

**1. Memory Leak Detection**
```python
import psutil
import gc

@pytest.fixture(autouse=True)
def memory_monitor():
    """Monitor memory usage for each test"""
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    yield

    # Force garbage collection
    gc.collect()

    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory

    if memory_increase > 10:  # 10MB threshold
        pytest.warns(
            UserWarning,
            f"Memory increase detected: {memory_increase:.2f}MB"
        )
```

**2. Connection Cleanup**
```python
@pytest.fixture
async def clean_connection():
    """Connection with guaranteed cleanup"""
    connection = None
    try:
        connection = await asyncpg.connect(test_database_url)
        yield connection
    finally:
        if connection and not connection.is_closed():
            await connection.close()
```

## Environment-Specific Issues

### Docker/Container Environments

#### Issue: Tests fail in containers but work locally

**Solution: Container-specific configuration**
```python
# Container-optimized TDD configuration
def get_container_optimized_config():
    """Get TDD configuration optimized for containers"""
    import os

    # Detect container environment
    in_container = os.path.exists('/.dockerenv') or os.getenv('CONTAINER') == 'true'

    if in_container:
        return {
            "pool_size": 2,           # Smaller pools in containers
            "pool_max_overflow": 1,   # Limited overflow
            "pool_timeout": 5,        # Faster timeout
            "command_timeout": 10,    # Container-friendly timeout
        }
    else:
        return {
            "pool_size": 5,
            "pool_max_overflow": 3,
            "pool_timeout": 10,
            "command_timeout": 30,
        }
```

### CI/CD Environments

#### Issue: Tests pass locally but fail in CI

**Solution: CI-specific configuration**
```python
# CI-optimized test configuration
def configure_for_ci():
    """Configure TDD for CI environment"""
    import os

    # CI environment detection
    ci_environments = ['CI', 'GITHUB_ACTIONS', 'GITLAB_CI', 'JENKINS']
    in_ci = any(os.getenv(env) for env in ci_environments)

    if in_ci:
        # CI-specific settings
        os.environ["DATAFLOW_TDD_POOL_SIZE"] = "3"
        os.environ["DATAFLOW_TDD_TIMEOUT"] = "15"
        os.environ["DATAFLOW_TDD_MAX_CONNECTIONS"] = "10"

        # Enable additional logging in CI
        import logging
        logging.getLogger('dataflow.testing').setLevel(logging.DEBUG)
```

## Debugging Tools

### TDD Infrastructure Status Check

```python
async def check_tdd_infrastructure_status():
    """Comprehensive TDD infrastructure status check"""
    from dataflow.testing.tdd_support import (
        is_tdd_mode,
        get_database_manager,
        get_transaction_manager
    )

    print("=== TDD Infrastructure Status ===")

    # 1. TDD Mode
    tdd_enabled = is_tdd_mode()
    print(f"TDD Mode: {'✅ Enabled' if tdd_enabled else '❌ Disabled'}")

    if not tdd_enabled:
        print("Fix: Set DATAFLOW_TDD_MODE=true")
        return

    # 2. Database Manager
    try:
        db_manager = get_database_manager()
        await db_manager.initialize()
        print("✅ Database Manager: Initialized")

        # Test connection
        context = TDDTestContext()
        connection = await db_manager.get_test_connection(context)
        await connection.fetchval("SELECT 1")
        await db_manager.cleanup_test_connection(context)
        print("✅ Database Connection: Working")

    except Exception as e:
        print(f"❌ Database Manager: {e}")

    # 3. Transaction Manager
    try:
        tx_manager = get_transaction_manager()
        print("✅ Transaction Manager: Available")
    except Exception as e:
        print(f"❌ Transaction Manager: {e}")

    print("=== Status Check Complete ===")

# Run this function if experiencing issues
# asyncio.run(check_tdd_infrastructure_status())
```

### Performance Debugging

```python
import time
import functools

def debug_performance(func):
    """Decorator to debug test performance"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()

        try:
            result = await func(*args, **kwargs)
            duration = (time.time() - start_time) * 1000

            status = "✅" if duration < 100 else "⚠️"
            print(f"{status} {func.__name__}: {duration:.2f}ms")

            return result

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            print(f"❌ {func.__name__}: {duration:.2f}ms (FAILED: {e})")
            raise

    return wrapper

# Usage
@pytest.mark.asyncio
@debug_performance
async def test_with_performance_debug(tdd_test_context):
    """Test with automatic performance debugging"""
    # Test code here
    pass
```

## Getting Help

### Collecting Diagnostic Information

```python
def collect_diagnostic_info():
    """Collect comprehensive diagnostic information"""
    import sys
    import os
    import platform
    import asyncio

    print("=== DataFlow TDD Diagnostic Information ===")
    print(f"Python Version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"DataFlow TDD Mode: {os.getenv('DATAFLOW_TDD_MODE', 'Not Set')}")
    print(f"Database URL: {os.getenv('TEST_DATABASE_URL', 'Not Set')}")
    print(f"Available Memory: {psutil.virtual_memory().available / 1024 / 1024:.0f}MB")

    # Test basic TDD functionality
    try:
        from dataflow.testing.tdd_support import is_tdd_mode
        print(f"TDD Infrastructure: {'✅ Available' if is_tdd_mode else '❌ Not Available'}")
    except ImportError as e:
        print(f"TDD Infrastructure: ❌ Import Error: {e}")

    # Test database connectivity
    try:
        async def test_db():
            import asyncpg
            conn = await asyncpg.connect(
                "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
            )
            await conn.close()
            return True

        result = asyncio.run(test_db())
        print(f"Database Connectivity: ✅ Working")
    except Exception as e:
        print(f"Database Connectivity: ❌ {e}")

    print("=== End Diagnostic Information ===")

# Run this and include output when reporting issues
collect_diagnostic_info()
```

This troubleshooting guide covers the most common issues encountered with DataFlow's TDD infrastructure. For additional support, include the diagnostic information when reporting issues to the development team.

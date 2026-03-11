# Event Loop-Safe Async Fixture Pattern for DataFlow Integration Tests

## Problem
Integration tests using complex async fixture hierarchies (session-scoped + function-scoped) cause event loop conflicts:
- `RuntimeError: Task got Future attached to a different loop`
- asyncpg pool conflicts across test event loops
- Connection cleanup failures

## Root Cause
Session-scoped async fixtures create asyncpg pools in one event loop, but function-scoped fixtures try to use them in different event loops.

## Solution: Function-Scoped Pattern

### ✅ Recommended Pattern

```python
import asyncio
import pytest
import asyncpg

# Simple function-scoped fixtures
@pytest.fixture
async def database_config():
    """Get database configuration from environment."""
    import os
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5434"))
    user = os.getenv("DB_USER", "test_user")
    password = os.getenv("DB_PASSWORD", "test_password")
    database = os.getenv("DB_NAME", "kailash_test")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


@pytest.fixture
async def test_connection(database_config):
    """Create a direct database connection for each test."""
    conn = await asyncpg.connect(database_config)

    # Verify connection works
    await conn.fetchval("SELECT 1")

    yield conn

    # Cleanup
    await conn.close()


@pytest.fixture
async def connection_manager(database_config):
    """Create async connection manager for each test."""
    class AsyncConnectionManager:
        def __init__(self, db_url):
            self.database_url = db_url
            self._connection = None

        async def get_connection(self):
            """Get async database connection."""
            if self._connection is None or self._connection.is_closed():
                self._connection = await asyncpg.connect(self.database_url)
            return self._connection

        def close_all_connections(self):
            """Close all connections."""
            if self._connection and not self._connection.is_closed():
                asyncio.create_task(self._connection.close())

    manager = AsyncConnectionManager(database_config)

    yield manager

    # Cleanup
    manager.close_all_connections()


@pytest.fixture
async def dependency_analyzer(connection_manager):
    """Create DependencyAnalyzer for each test."""
    from dataflow.migrations.dependency_analyzer import DependencyAnalyzer
    analyzer = DependencyAnalyzer(connection_manager)
    yield analyzer


@pytest.fixture(autouse=True)
async def clean_test_schema(test_connection):
    """Clean test schema before each test."""
    await test_connection.execute("""
        DO $$
        DECLARE r RECORD;
        BEGIN
            -- Drop test tables, views, functions in correct order
            FOR r IN (SELECT schemaname, tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename LIKE 'test_%')
            LOOP
                EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.schemaname) || '.' ||
                        quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestExample:
    """Integration tests using event loop-safe pattern."""

    @pytest.mark.asyncio
    async def test_database_operations(self, dependency_analyzer, test_connection):
        """Test with real database operations."""
        # Create test schema
        await test_connection.execute("""
            CREATE TABLE test_users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL
            );
        """)

        # Use analyzer with real database
        result = await dependency_analyzer.find_foreign_key_dependencies("test_users", "id")
        assert isinstance(result, list)
```

### Key Principles

1. **All fixtures are function-scoped** - No session-scoped async fixtures
2. **Fresh connections per test** - Each test gets its own database connection
3. **Simple async connection manager** - Matches the expected interface
4. **Clean separation** - test_connection for setup, connection_manager for analyzers
5. **Proper cleanup** - Each fixture handles its own cleanup

## Migration Guide

### Before (Problematic)
```python
@pytest.fixture(scope="session")  # ❌ Session scope causes conflicts
async def test_database():
    config = DatabaseConfig.from_environment()
    infrastructure = DatabaseInfrastructure(config)
    await infrastructure.initialize()  # Creates asyncpg pool
    yield infrastructure

@pytest.fixture  # ❌ Function scope tries to use session pool
async def connection_manager(test_database):
    manager = MigrationConnectionManager(mock_dataflow)
    yield manager
```

### After (Working)
```python
@pytest.fixture  # ✅ Function scope only
async def database_config():
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

@pytest.fixture  # ✅ Function scope with direct connection
async def test_connection(database_config):
    conn = await asyncpg.connect(database_config)
    yield conn
    await conn.close()

@pytest.fixture  # ✅ Simple async connection manager
async def connection_manager(database_config):
    class AsyncConnectionManager:
        async def get_connection(self):
            return await asyncpg.connect(self.database_url)
    yield AsyncConnectionManager(database_config)
```

## Performance Impact

- **Slightly slower**: Each test creates new connections (~50-100ms overhead)
- **More reliable**: No event loop conflicts or connection pool issues
- **Easier debugging**: Isolated test environments
- **Better for CI**: No shared state between tests

## Alternative: Session with Proper Event Loop Handling

If you need session-scoped resources, use synchronous setup:

```python
@pytest.fixture(scope="session")
def database_config():  # ✅ Sync fixture
    return DatabaseConfig.from_environment()

@pytest.fixture
async def test_connection(database_config):  # ✅ Function-scoped async
    conn = await asyncpg.connect(database_config.url)
    yield conn
    await conn.close()
```

## Testing the Fix

```bash
# Before fix - fails with event loop errors
pytest tests/integration/migration/test_dependency_analyzer_integration.py -v

# After fix - passes cleanly
pytest tests/integration/migration/test_dependency_analyzer_integration_fixed.py -v
```

## Files to Update

Apply this pattern to these problematic files:
- `tests/integration/migration/test_dependency_analyzer_integration.py`
- `tests/integration/migration/test_performance_large_schema_integration.py`
- Any test file mixing session-scoped + function-scoped async fixtures

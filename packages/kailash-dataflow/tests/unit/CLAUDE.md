# DataFlow Unit Test Guide (Tier 1)

## ⚠️ CRITICAL: For Claude Code - Always Use Standardized Unit Test Fixtures

**When writing unit tests, ALWAYS use the standardized unit test fixtures:**

```python
from tests.fixtures.unit_test_harness import UnitTestSuite

@pytest.mark.unit
class TestMyFeature:
    def test_with_memory_dataflow(self, memory_dataflow):
        """Test using in-memory SQLite DataFlow instance."""
        db = memory_dataflow

        @db.model
        class TestModel:
            name: str
            value: int

        models = db.get_models()
        assert "TestModel" in models

    @pytest.mark.asyncio
    async def test_with_connection(self, memory_test_suite):
        """Test using direct SQLite connection."""
        async with memory_test_suite.get_connection() as conn:
            await conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            # Your test code here
```

**NEVER hardcode database URLs or create manual SQLite connections in unit tests!**

## 🏗️ Unit Test Organization (Tier 1)

### Three-Tier Testing Strategy

```
tests/
├── unit/           # Isolated component tests (Tier 1) - THIS DIRECTORY
├── integration/    # Component interaction tests (Tier 2)
└── e2e/            # Full user workflow tests (Tier 3)
```

## 🔌 Standardized Unit Test Infrastructure

### UnitTestSuite - The Standard Fixture System for Unit Tests

All unit tests MUST use the `UnitTestSuite` fixture system for database operations:

```python
@pytest.mark.unit
class TestMyFeature:
    def test_with_memory_database(self, memory_dataflow):
        """Use memory-based DataFlow for fast unit tests."""
        db = memory_dataflow
        # Test code here

    @pytest.mark.asyncio
    async def test_with_sqlite_connection(self, memory_test_suite):
        """Use direct SQLite connection for database operations."""
        async with memory_test_suite.get_connection() as conn:
            await conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            # Test database operations
```

### Key Benefits

- **Fast Execution**: In-memory SQLite databases for rapid test execution
- **No Configuration Drift**: Single source of truth for test database configurations
- **Automatic Cleanup**: Database lifecycle managed by the fixtures
- **Test Isolation**: Each test gets fresh database state
- **Consistent Patterns**: Following IntegrationTestSuite architecture

### Directory Structure

#### Unit Tests (`tests/unit/`)
- **adapters/** - Database adapter unit tests (with mocks)
- **cli/** - Command-line interface unit tests
- **core/** - Core functionality, API validation, basic SQLite operations
- **migrations/** - Migration system component unit tests
- **schema/** - Schema comparison and caching unit tests
- **security/** - SQL injection validation unit tests
- **performance/** - Performance and concurrency unit tests
- **testing/** - Testing infrastructure unit tests
- **validation/** - General validation logic unit tests
- **web/** - Web API unit tests

## 🚨 Critical Testing Policies (Tier 1 Only)

### 1. Allowed Dependencies by Tier

**Unit Tests (Tier 1) - THIS DIRECTORY:**
- ✅ **SQLite databases** (both `:memory:` and file-based) - Lightweight, no external infrastructure required
- ✅ **Mocks and stubs** for external services and complex components
- ❌ **PostgreSQL connections** - Use integration tests instead

### 2. ALWAYS Use Standardized Fixtures

```python
# ✅ ALWAYS use standardized fixtures:
def test_feature(self, memory_dataflow):
    db = memory_dataflow
    # Test logic

@pytest.mark.asyncio
async def test_async_feature(self, memory_test_suite):
    async with memory_test_suite.get_connection() as conn:
        # Test database operations

# ❌ NEVER create manual database connections:
def test_feature_bad():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        db = DataFlow(f"sqlite:///{tmp.name}")  # DON'T DO THIS
```

### 3. Use Appropriate Mocking for External Dependencies

```python
# ✅ GOOD - Mock external services:
def test_with_mock_executor(self, mock_migration_executor):
    executor = mock_migration_executor
    # Test with mocked external dependency

# ❌ BAD - Don't use PostgreSQL in unit tests:
def test_feature(self, postgresql_connection):  # Use integration tests instead
    pass

# ❌ BAD - Don't mock SQLite in unit tests:
@patch('aiosqlite.connect')
def test_feature(self, mock_sqlite):  # Use real SQLite instead
    pass
```

## 📋 Standard Fixtures Available

### Database Configuration Fixtures

- **`unit_test_suite`** - Standard memory-based unit test suite
- **`memory_test_suite`** - Explicit memory-based SQLite test suite
- **`file_test_suite`** - File-based SQLite test suite for persistent tests

### DataFlow Fixtures

- **`memory_dataflow`** - DataFlow instance with memory database (fastest)
- **`file_dataflow`** - DataFlow instance with file database (persistent)
- **`auto_migrate_dataflow`** - DataFlow instance with auto-migration enabled

### Connection Fixtures

- **`sqlite_memory_connection`** - Direct SQLite memory connection
- **`sqlite_file_connection`** - Direct SQLite file connection

### Table Factory Fixtures

- **`basic_test_table`** - Pre-created basic test table with standard data (Alice, Bob, Charlie)
- **`constrained_test_tables`** - Test tables with constraints and foreign keys

### Mocking Fixtures

- **`mock_connection_manager`** - Mock connection manager for unit tests
- **`mock_migration_executor`** - Mock migration executor for unit tests
- **`mock_dataflow_engine`** - Mock DataFlow engine for unit tests
- **`mock_postgresql_config`** - Mock PostgreSQL config for unit tests

## 🎯 Standard Test Patterns

### 1. Basic DataFlow Model Testing

```python
@pytest.mark.unit
class TestModelRegistration:
    def test_model_registration(self, memory_dataflow):
        """Test model registration with memory DataFlow."""
        db = memory_dataflow

        @db.model
        class User:
            name: str
            email: str

        models = db.get_models()
        assert "User" in models
```

### 2. SQLite Database Operations

```python
@pytest.mark.unit
class TestDatabaseOperations:
    @pytest.mark.asyncio
    async def test_database_operations(self, memory_test_suite):
        """Test database operations with standardized connection."""
        async with memory_test_suite.get_connection() as conn:
            # Create test table
            await conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
            )

            # Insert data
            await conn.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))

            # Query data
            cursor = await conn.execute("SELECT name FROM users")
            row = await cursor.fetchone()
            assert row[0] == "Alice"
```

### 3. Using Pre-created Test Tables

```python
@pytest.mark.unit
class TestWithStandardData:
    @pytest.mark.asyncio
    async def test_with_standard_table(self, basic_test_table, memory_test_suite):
        """Test using pre-created standard test table."""
        table_name = basic_test_table

        async with memory_test_suite.get_connection() as conn:
            # Table already has 3 standard records (Alice, Bob, Charlie)
            cursor = await conn.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = await cursor.fetchone()
            assert row[0] == 3  # Standard test data
```

### 4. Mocking External Dependencies

```python
@pytest.mark.unit
@pytest.mark.mocking
class TestWithMocks:
    def test_with_mock_executor(self, mock_migration_executor):
        """Test using mock migration executor."""
        executor = mock_migration_executor

        # Mock is pre-configured with standard behavior
        executor.add_migration("test_migration", "CREATE TABLE test;", "DROP TABLE test;")
        result = executor.execute_migration("test_migration")

        assert result["success"] is True
        assert result["duration"] == 0.1  # Mock duration
```

### 5. File-based SQLite for Persistence

```python
@pytest.mark.unit
class TestPersistentOperations:
    def test_persistence_with_file_db(self, file_dataflow):
        """Test that requires file-based persistence."""
        db = file_dataflow

        @db.model
        class PersistentModel:
            data: str

        # This will persist to the file database
        assert "PersistentModel" in db.get_models()
```

## ⚡ Running Unit Tests

```bash
# All unit tests (Tier 1)
pytest tests/unit/

# Specific category
pytest tests/unit/core/
pytest tests/unit/migrations/

# With coverage
pytest tests/unit/ --cov=dataflow

# Only memory-based tests (fastest)
pytest tests/unit/ -m sqlite_memory

# Only mocking tests
pytest tests/unit/ -m mocking

# Exclude file-based tests for speed
pytest tests/unit/ -m "not sqlite_file"
```

## 🏷️ Test Markers

### Automatic Markers

The fixtures automatically apply appropriate pytest markers:

- **`@pytest.mark.unit`** - Applied to all tests in `tests/unit/`
- **`@pytest.mark.sqlite_memory`** - Applied to tests using memory fixtures
- **`@pytest.mark.sqlite_file`** - Applied to tests using file fixtures
- **`@pytest.mark.mocking`** - Applied to tests using mock fixtures

### Manual Marking

```python
@pytest.mark.unit
@pytest.mark.sqlite_memory
class TestMyFeature:
    """Explicitly marked unit test class."""

    def test_feature(self, memory_dataflow):
        """Test with in-memory SQLite."""
        pass
```

## 📝 Adding New Unit Tests

1. **Determine the appropriate subdirectory** within `tests/unit/`
2. **Use standardized fixtures** - never create manual database connections
3. **Follow existing patterns** in that directory
4. **Use SQLite for database operations** - save PostgreSQL for integration tests
5. **Mock external dependencies** appropriately
6. **Include proper test isolation** - each test should be independent

## 🔧 Common Patterns

### Async Test Pattern with SQLite

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_database_operation(self, memory_test_suite):
    """Test async database operations."""
    async with memory_test_suite.get_connection() as conn:
        await conn.execute("CREATE TABLE test (id INTEGER, data TEXT)")
        await conn.execute("INSERT INTO test VALUES (1, 'test')")

        cursor = await conn.execute("SELECT * FROM test")
        result = await cursor.fetchall()
        assert len(result) == 1
```

### Mock Setup Pattern

```python
@pytest.mark.unit
@pytest.mark.mocking
class TestWithExternalDependencies:
    def test_external_service_interaction(self, mock_connection_manager):
        """Test interaction with external services using mocks."""
        manager = mock_connection_manager

        # Mock is pre-configured with standard behavior
        connection = manager.get_connection()
        assert connection is not None
```

### Test Cleanup Pattern

```python
@pytest.mark.unit
class TestAutoCleanup:
    def test_automatic_cleanup(self, file_test_suite):
        """Test that demonstrates automatic cleanup."""
        # File database is created and will be automatically cleaned up
        # No manual teardown required
        db_config = file_test_suite.config
        assert not db_config.in_memory
        # Test will automatically clean up the file database
```

## 🚨 Critical Rules for Unit Tests

### Database Usage
- **ALWAYS**: Use SQLite (`:memory:` or file-based) for unit tests
- **NEVER**: Use PostgreSQL in unit tests (use integration tests instead)
- **ALWAYS**: Use standardized fixtures (`memory_dataflow`, `file_dataflow`, etc.)
- **NEVER**: Create manual database connections with `tempfile` or hardcoded paths

### Mocking Strategy
- **Mock external services**: HTTP clients, external APIs, complex dependencies
- **Don't mock SQLite**: Use real SQLite databases for database operations
- **Use provided mocks**: Leverage `mock_migration_executor`, `mock_connection_manager`, etc.

### Test Isolation
- **Each test is independent**: Fixtures provide fresh state for each test
- **No shared state**: Don't rely on state from other tests
- **Automatic cleanup**: Trust the fixtures to handle cleanup

## 📊 Performance Guidelines

### Fast Tests (Prefer These)
- **Memory databases**: Use `memory_dataflow` and `memory_test_suite` for speed
- **Simple operations**: Keep unit tests focused on individual components
- **Minimal setup**: Use standardized fixtures to minimize setup overhead

### Slower Tests (Use When Necessary)
- **File databases**: Only when persistence between operations is required
- **Complex scenarios**: Move complex multi-component scenarios to integration tests

## 🔍 Debugging Unit Tests

### Enable Debug Logging

```python
import logging
logging.getLogger('tests.fixtures.unit_test_harness').setLevel(logging.DEBUG)
```

### Inspect Fixture State

```python
def test_debug_fixture(self, memory_test_suite):
    """Debug fixture state."""
    print(f"Database URL: {memory_test_suite.config.url}")
    print(f"Database type: {memory_test_suite.config.type}")
    print(f"Is memory: {memory_test_suite.config.in_memory}")
```

## ❓ FAQ

**Q: When should I use memory vs file-based SQLite?**
A: Use memory for fast, isolated tests (95% of cases). Use file only when you need persistence across multiple operations within the same test.

**Q: Can I use PostgreSQL in unit tests?**
A: No. PostgreSQL should only be used in integration/e2e tests (Tier 2-3). Use SQLite with mocks for unit tests.

**Q: How do I test PostgreSQL-specific features in unit tests?**
A: Mock the PostgreSQL-specific behavior or move the test to integration tests. Unit tests should focus on logic, not database-specific features.

**Q: What if my test needs specific database state?**
A: Use the table factory fixtures (`basic_test_table`, `constrained_test_tables`) or create the state within your test using the connection.

**Q: How do I test migration operations in unit tests?**
A: Use `mock_migration_executor` to test migration logic without real database operations, or use SQLite to test the actual migration mechanics.

**Q: Can I mix different fixture types in one test?**
A: Yes, but ensure they're compatible. For example, don't mix `memory_dataflow` and `file_dataflow` in the same test - choose one approach per test.

## 🔗 Related Documentation

- **Integration Test Guide**: `/tests/integration/CLAUDE.md` - For Tier 2 tests with real infrastructure
- **Fixtures Documentation**: `/tests/fixtures/README.md` - Comprehensive fixture usage guide
- **Main Test Guide**: `/tests/CLAUDE.md` - Overall testing strategy and three-tier approach

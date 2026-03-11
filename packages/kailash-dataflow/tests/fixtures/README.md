# DataFlow Unit Test Fixtures (Tier 1)

This directory contains standardized fixtures for DataFlow unit tests, following the IntegrationTestSuite patterns but adapted for Tier 1 (unit) testing constraints.

## 🏗️ Architecture Overview

### Three-Tier Testing Strategy Compliance

**Unit Tests (Tier 1) - This Directory:**
- ✅ **SQLite databases** (both `:memory:` and file-based) - Lightweight, no external infrastructure required
- ✅ **Mocks and stubs** for external services and complex components
- ❌ **PostgreSQL connections** - Use integration tests instead

**Integration/E2E Tests (Tiers 2-3):**
- ✅ **PostgreSQL databases** on shared test infrastructure (port 5434)
- ❌ **NO MOCKING** - Must use real infrastructure components

## 📁 File Structure

```
tests/fixtures/
├── README.md                 # This file
├── unit_test_harness.py     # Core unit test infrastructure (Tier 1)
└── tdd_fixtures.py          # Legacy fixtures (being phased out)

tests/unit/
└── conftest.py              # Standardized fixtures for unit tests
```

## 🚀 Quick Start

### Basic Usage

```python
import pytest
from dataflow import DataFlow

@pytest.mark.unit
class TestMyFeature:
    """Unit tests following standardized patterns."""

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
            await conn.execute("INSERT INTO test VALUES (1, 'test')")

            cursor = await conn.execute("SELECT COUNT(*) FROM test")
            row = await cursor.fetchone()
            assert row[0] == 1
```

## 🔧 Available Fixtures

### Database Configuration Fixtures

- **`unit_test_suite`** - Standard memory-based unit test suite
- **`memory_test_suite`** - Explicit memory-based SQLite test suite
- **`file_test_suite`** - File-based SQLite test suite for persistent tests

### DataFlow Fixtures

- **`memory_dataflow`** - DataFlow instance with memory database
- **`file_dataflow`** - DataFlow instance with file database
- **`auto_migrate_dataflow`** - DataFlow instance with auto-migration enabled

### Connection Fixtures

- **`sqlite_memory_connection`** - Direct SQLite memory connection
- **`sqlite_file_connection`** - Direct SQLite file connection

### Table Factory Fixtures

- **`basic_test_table`** - Pre-created basic test table with standard data
- **`constrained_test_tables`** - Test tables with constraints and foreign keys

### Mocking Fixtures

- **`mock_connection_manager`** - Mock connection manager for unit tests
- **`mock_migration_executor`** - Mock migration executor for unit tests
- **`mock_dataflow_engine`** - Mock DataFlow engine for unit tests
- **`mock_postgresql_config`** - Mock PostgreSQL config for unit tests

## 📋 Usage Patterns

### 1. Basic Model Testing

```python
def test_model_registration(self, memory_dataflow):
    """Test model registration with memory DataFlow."""
    db = memory_dataflow

    @db.model
    class User:
        name: str
        email: str

    assert "User" in db.get_models()
```

### 2. Database Operations Testing

```python
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
def test_with_mock_executor(self, mock_migration_executor):
    """Test using mock migration executor."""
    executor = mock_migration_executor

    # Mock is pre-configured with standard behavior
    executor.add_migration("test_migration", "CREATE TABLE test;", "DROP TABLE test;")
    result = executor.execute_migration("test_migration")

    assert result["success"] is True
    assert result["duration"] == 0.1  # Mock duration
```

## 🏷️ Test Markers

The fixtures automatically apply appropriate pytest markers:

- **`@pytest.mark.unit`** - Applied to all tests in `tests/unit/`
- **`@pytest.mark.sqlite_memory`** - Applied to tests using memory fixtures
- **`@pytest.mark.sqlite_file`** - Applied to tests using file fixtures
- **`@pytest.mark.mocking`** - Applied to tests using mock fixtures

## 🚨 Important Guidelines

### 1. Database Choice for Unit Tests

```python
# ✅ GOOD - Use SQLite for unit tests
def test_feature(self, memory_dataflow):
    pass

# ❌ BAD - Don't use PostgreSQL in unit tests
def test_feature(self, postgresql_connection):  # Use integration tests instead
    pass
```

### 2. Mocking vs Real Infrastructure

```python
# ✅ GOOD - Mock external services in unit tests
def test_feature(self, mock_connection_manager):
    pass

# ✅ GOOD - Use real SQLite for database operations
def test_feature(self, sqlite_memory_connection):
    pass

# ❌ BAD - Don't mock SQLite in unit tests
@patch('aiosqlite.connect')
def test_feature(self, mock_sqlite):  # Use real SQLite instead
    pass
```

## 🔄 Migration from Legacy Patterns

### Before (Legacy)

```python
class TestOldPattern:
    def setup_method(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db = DataFlow(f"sqlite:///{self.db_file.name}")

    def teardown_method(self):
        os.unlink(self.db_file.name)
```

### After (Standardized)

```python
@pytest.mark.unit
class TestNewPattern:
    def test_feature(self, file_dataflow):
        # Automatic setup and cleanup
        db = file_dataflow
        # Test logic here
```

## 📝 Summary

The standardized unit test fixtures provide:

✅ **Consistent patterns** following IntegrationTestSuite architecture
✅ **Proper tier isolation** - SQLite for unit tests, PostgreSQL for integration
✅ **Automatic cleanup** - No manual database file management
✅ **Standard test data** - Pre-created tables with consistent test records
✅ **Comprehensive mocking** - Mock utilities for external dependencies
✅ **Type safety** - Proper typing and fixture declarations
✅ **Performance optimized** - Memory databases for fast test execution

This standardization eliminates hardcoded configurations, reduces boilerplate, and ensures consistent testing patterns across the DataFlow codebase.

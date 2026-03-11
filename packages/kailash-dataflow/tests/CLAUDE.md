# DataFlow Test Suite Guide

## ⚠️ CRITICAL: For Claude Code - Always Use IntegrationTestSuite

**When writing integration or E2E tests, ALWAYS use the IntegrationTestSuite fixture:**

```python
from tests.infrastructure.test_harness import IntegrationTestSuite

@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite

async def test_my_feature(test_suite):  # Use test_suite fixture
    db_url = test_suite.config.url
    async with test_suite.get_connection() as conn:
        # Your test code here
```

**NEVER hardcode database URLs or create direct asyncpg connections in integration/E2E tests!**

## 🏗️ Test Organization

### Three-Tier Testing Strategy

```
tests/
├── unit/           # Isolated component tests (mocks allowed)
├── integration/    # Component interaction tests (NO MOCKING - real infrastructure)
└── e2e/            # Full user workflow tests (NO MOCKING - production scenarios)
```

## 🔌 Standardized Test Infrastructure

### IntegrationTestSuite - The Standard Fixture System

All integration and E2E tests MUST use the `IntegrationTestSuite` fixture system for database connections:

```python
from tests.infrastructure.test_harness import IntegrationTestSuite

@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite

async def test_my_feature(test_suite):
    """Use test_suite for database operations."""
    # Get database URL from test suite
    db_url = test_suite.config.url

    # Get a connection from the pool
    async with test_suite.get_connection() as conn:
        result = await conn.fetch("SELECT ...")
```

### Key Benefits
- **Connection Pooling**: Efficient reuse of database connections with asyncpg
- **No Configuration Drift**: Single source of truth for database URLs
- **Automatic Cleanup**: Connection management handled by the suite
- **Session Isolation**: Each test gets isolated database state

### Directory Structure

#### Unit Tests (`tests/unit/`)
- **core/** - Architecture validation, API compatibility, bulk operations
- **cli/** - Command-line interface functionality
- **migrations/** - Migration system components
- **schema/** - Schema comparison and caching
- **security/** - SQL injection validation
- **validation/** - General validation logic
- **performance/** - Performance and concurrency tests

#### Integration Tests (`tests/integration/`)
- **database/** - Database operations, PostgreSQL specifics
- **adapters/** - Database adapter integration
- **security/** - SQL injection prevention, DDL protection
- **schema/** - Schema validation with real databases
- **web/** - API gateway integration
- **personas/** - User persona scenarios
- **dataflow/** - DataFlow-specific features
- **migration/** - Migration system with real databases

#### E2E Tests (`tests/e2e/`)
- **applications/** - Complete application scenarios
- **workflows/** - User workflow journeys
- **migrations/** - Migration system end-to-end
- **security/** - Security scenario validation
- **dataflow/** - DataFlow complete workflows

## 🚨 Critical Testing Policies

### 1. Allowed Dependencies by Tier

**Unit Tests (Tier 1):**
- ✅ **SQLite databases** (both `:memory:` and file-based) - Lightweight, no external infrastructure required
- ✅ **Mocks and stubs** for external services and complex components
- ❌ **PostgreSQL connections** - Use mocks instead, save real DB testing for integration

**Integration/E2E Tests (Tiers 2-3):**
- ✅ **PostgreSQL databases** on shared test infrastructure (port 5434)
- ❌ **NO MOCKING** - Must use real infrastructure components

### 2. NO MOCKING in Integration/E2E Tests
```python
# ❌ NEVER DO THIS in integration/e2e tests:
@patch('dataflow.connection')
def test_something(mock_conn):
    mock_conn.execute.return_value = ...

# ✅ ALWAYS use IntegrationTestSuite:
async def test_something(test_suite):
    async with test_suite.get_connection() as conn:
        result = await conn.execute(...)
```

### 3. Use Shared SDK Docker Infrastructure
All tests use the shared PostgreSQL on port **5434** via IntegrationTestSuite:
```python
# IntegrationTestSuite automatically handles this configuration:
TEST_DATABASE_URL = "postgresql://test_user:test_password@localhost:5434/kailash_test"
```

### 4. Standard Test Patterns with IntegrationTestSuite

#### Basic Integration Test
```python
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_database_operation(test_suite):
    """Example integration test using test suite."""
    db_url = test_suite.config.url

    # Clean database first
    await test_suite.clean_database()

    # Use connection from pool
    async with test_suite.get_connection() as conn:
        await conn.execute("CREATE TABLE test_table ...")
        result = await conn.fetch("SELECT ...")
        assert result[0]['count'] > 0
```

#### DataFlow Integration Test
```python
async def test_dataflow_with_real_db(test_suite):
    """Example DataFlow test with real database."""
    db_url = test_suite.config.url

    # Create DataFlow with real database
    df = DataFlow(db_url, auto_migrate=True)

    @df.model
    class TestModel:
        name: str
        value: int

    await df.initialize()

    # Test with real database operations
    async with test_suite.get_connection() as conn:
        await conn.execute("INSERT INTO test_models ...")
```

### 5. Standard Fixtures
The IntegrationTestSuite provides:
- `test_suite.config.url` - Database URL
- `test_suite.get_connection()` - Connection from pool
- `test_suite.clean_database()` - Database cleanup
- `test_suite.session()` - Session management

### 6. Test Isolation
- Each test creates unique table names using timestamps
- Always clean up resources in test teardown
- Use transactions for data isolation when possible
- IntegrationTestSuite handles connection pooling and cleanup

## 🎯 When to Use Each Tier

### Unit Tests
- Testing individual functions/methods
- Algorithm correctness
- Edge cases with controlled inputs
- **Mocking allowed** for external dependencies

### Integration Tests
- Database operations
- Multi-component interactions
- API endpoint testing
- **MUST use real infrastructure**

### E2E Tests
- Complete user workflows
- Multi-step scenarios
- Production-like usage patterns
- **MUST use real infrastructure**

## ⚡ Running Tests

```bash
# All tests
pytest tests/

# Specific tier
pytest tests/integration/

# Specific category
pytest tests/integration/migration/

# With coverage
pytest tests/unit/ --cov=dataflow

# Using test environment
TEST_DATABASE_URL="postgresql://..." pytest tests/integration/
```

## 📝 Adding New Tests

1. **Determine the appropriate tier** based on what you're testing
2. **Place in the correct subdirectory** within that tier
3. **Follow existing patterns** in that directory
4. **Use real infrastructure** for integration/e2e tests
5. **Include proper cleanup** in test teardown

## 🔧 Common Patterns

### Async Test Pattern
```python
@pytest.mark.integration
@pytest.mark.timeout(5)
async def test_database_operation(postgres_connection):
    # Your async test code
    result = await postgres_connection.fetch("SELECT ...")
    assert result[0]['count'] > 0
```

### Table Cleanup Pattern
```python
@pytest.fixture
async def test_table(postgres_connection):
    table_name = f"test_table_{int(time.time())}"
    await postgres_connection.execute(f"CREATE TABLE {table_name} ...")
    yield table_name
    await postgres_connection.execute(f"DROP TABLE IF EXISTS {table_name}")
```

### DataFlow Test Pattern
```python
async def test_dataflow_operation(standard_dataflow):
    @standard_dataflow.model
    class TestModel:
        name: str
        value: int

    # Test operations on the model
    result = await standard_dataflow.execute_operation(...)

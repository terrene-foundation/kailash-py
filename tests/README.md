# Kailash SDK Tests

## Overview

The Kailash SDK test suite includes both unit tests with mocks and integration tests with real services.

## Test Setup

### Quick Start

Run tests with real services:
```bash
./run_real_tests.sh
```

This script will:
1. Start required Docker services (PostgreSQL, Ollama)
2. Create test database and tables
3. Install required Python packages
4. Run integration tests

### Manual Setup

1. **Start Docker services:**
   ```bash
   cd docker
   docker-compose -f docker-compose.sdk-dev.yml up -d postgres ollama
   ```

2. **Setup test database:**
   ```bash
   ./tests/setup_test_env.sh
   ```

3. **Install dependencies:**
   ```bash
   pip install asyncpg aiosqlite aiomysql
   ```

4. **Run tests:**
   ```bash
   # All tests
   pytest tests/

   # Specific test file
   pytest tests/test_nodes/test_async_database_integration_real.py -v

   # With coverage
   pytest tests/ --cov=kailash --cov-report=html
   ```

### Stop Services

```bash
cd docker
docker-compose -f docker-compose.sdk-dev.yml down
```

## Test Organization

```
tests/
├── README.md                    # This file
├── setup_test_env.sh           # Setup script for test environment
├── test_config.py              # Test configuration and constants
├── conftest.py                 # Root pytest configuration
├── test_nodes/                 # Node-specific tests
│   ├── conftest.py            # Node test configuration
│   ├── test_async_database_integration.py      # Original tests with mocks
│   ├── test_async_database_integration_real.py # Tests with real services
│   └── test_async_sql.py      # Async SQL node tests
├── integration/                # Integration tests
├── unit/                      # Unit tests
└── fixtures/                  # Test fixtures and data
```

## Test Types

### Unit Tests (Mocked)
- Fast execution
- No external dependencies
- Good for CI/CD pipelines
- Located in original test files

### Integration Tests (Real Services)
- Use actual PostgreSQL, Ollama, etc.
- More realistic testing
- Slower execution
- Files ending with `_real.py`

## Configuration

Test configuration is managed through:
- `test_config.py` - Database connections, test data
- Environment variables - Override defaults
- Docker environment - Service configuration

### Environment Variables

- `TEST_DB_HOST` - PostgreSQL host (default: localhost)
- `TEST_DB_PORT` - PostgreSQL port (default: 5432)
- `TEST_DB_NAME` - Test database name (default: test_db)
- `TEST_DB_USER` - Database user (default: kailash)
- `TEST_DB_PASSWORD` - Database password (default: kailash123)
- `OLLAMA_HOST` - Ollama API URL (default: http://localhost:11434)
- `OLLAMA_MODEL` - Ollama model to use (default: llama3.2:1b)

## Writing Tests

### For Real Service Tests

```python
import pytest
from test_config import TEST_DB_CONFIG

@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_database_operation():
    node = AsyncSQLDatabaseNode(
        connection_string=TEST_DB_CONFIG["connection_string"],
        query="SELECT * FROM users"
    )
    result = await node.async_run()
    assert result["result"]["row_count"] >= 0
```

### For Mocked Tests

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_database_operation_mocked():
    with patch.dict("sys.modules", {"asyncpg": mock_asyncpg}):
        # Test with mocks
        pass
```

## Troubleshooting

### PostgreSQL Connection Issues
- Ensure Docker is running
- Check if port 5432 is available
- Verify credentials in test_config.py

### Test Database Missing
- Run `./tests/setup_test_env.sh` to create database
- Check Docker logs: `docker logs kailash-sdk-postgres`

### Import Errors
- Install required packages: `pip install asyncpg aiosqlite aiomysql`
- Ensure you're in the project root when running tests

## CI/CD Considerations

For CI/CD pipelines, you can:
1. Use mocked tests only (faster, no dependencies)
2. Set up services in CI (GitHub Actions services, etc.)
3. Use Docker-in-Docker for full integration tests

Example GitHub Actions:
```yaml
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_PASSWORD: kailash123
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```
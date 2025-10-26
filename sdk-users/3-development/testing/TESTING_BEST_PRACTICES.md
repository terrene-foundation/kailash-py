# Kailash SDK Testing Best Practices

## 🚨 Critical Testing Policies

### 1. Zero Skip Tolerance
```python
# ❌ NEVER DO THIS
@pytest.mark.skip("Redis not available")
def test_redis_operations():
    pass

# ❌ NEVER DO THIS
def test_postgres_connection():
    if not check_postgres():
        pytest.skip("PostgreSQL not running")

# ✅ DO THIS INSTEAD
def test_redis_operations():
    """Test will fail immediately if Redis is not available."""
    redis_client = redis.Redis(host='localhost', port=6380)
    redis_client.ping()  # Fails fast with clear error
```

### 2. No Mocking in Integration/E2E Tests
```python
# ❌ NEVER DO THIS IN INTEGRATION TESTS
from unittest.mock import patch

@patch('requests.get')
def test_api_integration(mock_get):
    mock_get.return_value.status_code = 200

# ✅ DO THIS INSTEAD - Use real Docker services
def test_api_integration():
    """Use real Docker mock-api service."""
    response = requests.get('http://localhost:8888/v1/users')
    assert response.status_code == 200
```

### 3. Proper Test Organization
```
tests/
├── unit/           # Fast, isolated, mocking allowed, LocalRuntime
├── integration/    # Real Docker services, NO MOCKING, LocalRuntime/AsyncLocalRuntime
└── e2e/           # Full scenarios, real infrastructure, AsyncLocalRuntime
```

## Docker Service Usage

### Available Services
- **PostgreSQL**: `localhost:5434`
- **Redis**: `localhost:6380`
- **Ollama**: `localhost:11435`
- **MySQL**: `localhost:3307`
- **MongoDB**: `localhost:27017`
- **Mock API**: `localhost:8888`

### Using Docker Services in Tests

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from tests.utils.docker_config import (
    get_postgres_connection_string,
    get_redis_url,
    OLLAMA_CONFIG,
    MOCK_API_CONFIG
)
import pytest

class TestWithRealServices:
    @pytest.mark.requires_docker
    def test_postgres_operations(self):
        """Test with real PostgreSQL - NO MOCKING."""
        conn_string = get_postgres_connection_string()

        workflow = WorkflowBuilder()
        workflow.add_node("SQLDatabaseNode", "db_node", {
            "connection_string": conn_string,
            "query": "SELECT 1 as value",
            "operation": "select"
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results['db_node']['success']
        assert len(results['db_node']['data']) > 0

    @pytest.mark.requires_docker
    def test_redis_caching(self):
        """Test with real Redis - NO MOCKING."""
        redis_url = get_redis_url()
        redis_client = redis.from_url(redis_url)

        redis_client.set('test_key', 'test_value')
        assert redis_client.get('test_key') == b'test_value'

    @pytest.mark.requires_docker
    def test_api_integration(self):
        """Test with real mock-api Docker service - NO MOCKING."""
        workflow = WorkflowBuilder()
        workflow.add_node("HTTPRequestNode", "api", {
            "url": f"{MOCK_API_CONFIG['base_url']}/v1/users",
            "method": "GET"
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["api"]["status_code"] == 200
```

## Common Patterns

### 1. Fast Failure for Missing Services
```python
def test_requires_postgres():
    # This will fail immediately with a clear error if PostgreSQL is down
    conn = psycopg2.connect(
        host="localhost",
        port=5434,
        database="kailash_test",
        user="test_user",
        password="test_password"
    )
    # Test continues only if connection succeeds
```

### 2. Runtime Selection
```python
from kailash.runtime import LocalRuntime, AsyncLocalRuntime
import pytest

# ✅ Correct - LocalRuntime for sync tests
def test_sync_workflow():
    """Unit/integration test with LocalRuntime."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node", {"code": "result = 42"})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    assert results["node"]["result"] == 42

# ✅ Correct - AsyncLocalRuntime for async tests
@pytest.mark.asyncio
async def test_async_workflow():
    """E2E test with AsyncLocalRuntime."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node", {"code": "result = 42"})

    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow.build(), inputs={})

    assert results["node"]["result"] == 42
```

### 3. Testing Both Runtimes
```python
import asyncio

@pytest.mark.parametrize("runtime_class", [LocalRuntime, AsyncLocalRuntime])
def test_workflow_with_both_runtimes(runtime_class):
    """Test workflow works with both sync and async runtimes."""
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "node", {"code": "result = 100"})

    runtime = runtime_class()

    if isinstance(runtime, AsyncLocalRuntime):
        results = asyncio.run(runtime.execute_workflow_async(workflow.build(), inputs={}))
    else:
        results, run_id = runtime.execute(workflow.build())

    assert results["node"]["result"] == 100
```

### 4. Proper Node Usage
```python
# ✅ Correct - String-based API with LocalRuntime
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'status': 'completed'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ❌ Wrong - Instance-based API
# Never create node instances directly
```

## Test Environment Setup

### Starting Docker Services
```bash
# Start all test services
cd tests/utils
docker-compose -f docker-compose.test.yml up -d

# Verify services are healthy
docker-compose -f docker-compose.test.yml ps
```

### Running Tests by Tier
```bash
# Tier 1 - Unit tests (ALL unit tests - no exclusions)
pytest tests/unit/

# Tier 2 - Integration tests (ALL integration tests - no exclusions)
pytest tests/integration/

# Tier 3 - E2E tests (ALL e2e tests - no exclusions)
pytest tests/e2e/
```

**IMPORTANT**: Do NOT use marker exclusions like `-m "not requires_docker"`. This creates "zombie tests" that never run, violating our zero-skip policy. If a test requires Docker, ensure Docker is running.

## Debugging Failed Tests

### 1. Service Not Available
```
Error: [Errno 111] Connection refused
```
**Solution**: Start Docker services with `docker-compose up`

### 2. Import Not Found
```
ModuleNotFoundError: No module named 'aioredis'
```
**Solution**: Install test dependencies with `pip install -r requirements-test.txt`

### 3. Deprecated API Usage
```
DeprecationWarning: Using workflow.add_connection("source", "result", "target", "input")with # Use CycleBuilder API instead is deprecated
```
**Solution**: Update to new CycleBuilder API

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Start test services
  run: |
    cd tests/utils
    docker-compose -f docker-compose.test.yml up -d
    # Wait for services to be healthy
    sleep 10

- name: Run tests
  run: |
    pytest tests/unit
    pytest tests/integration
    pytest tests/e2e
```

## Migration Guide

### From Skipped Tests
1. Remove all `@pytest.mark.skip` decorators
2. Remove all `pytest.skip()` calls
3. Let tests fail naturally when services are missing
4. Add clear error messages

### From Mocked Integration Tests
1. Start Docker mock-api service
2. Replace mock objects with real HTTP calls
3. Use `test_api_with_real_docker_services.py` as reference
4. Run migration script: `python scripts/migrate_api_tests_to_docker.py`

## Resources
- Test organization policy: `sdk-users/testing/test-organization-policy.md`
- Regression strategy: `sdk-users/testing/regression-testing-strategy.md`
- Docker setup: `tests/utils/docker-compose.test.yml`
- Test utilities: `tests/utils/docker_config.py`

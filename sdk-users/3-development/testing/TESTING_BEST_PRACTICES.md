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
    # Test will fail immediately if Redis is not available
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

# ✅ DO THIS INSTEAD
def test_api_integration():
    # Use real Docker mock-api service
    response = requests.get('http://localhost:8888/v1/users')
    assert response.status_code == 200
```

### 3. Proper Test Organization
```
tests/
├── unit/           # Fast, isolated, mocking allowed
├── integration/    # Real services, no mocking
└── e2e/           # Full scenarios, real infrastructure
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
from tests.utils.docker_config import (
    get_postgres_connection_string,
    get_redis_url,
    OLLAMA_CONFIG,
    MOCK_API_CONFIG
)

class TestWithRealServices:
    def test_postgres_operations(self):
        # Real PostgreSQL connection
        conn_string = get_postgres_connection_string()
        workflow = WorkflowBuilder()
        workflow.add_node("SQLDatabaseNode", "db_node", {
            "connection_string": conn_string,
            "query": "SELECT 1",
            "operation": "select"
        })
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())
        assert results['db_node']['success']

    def test_redis_caching(self):
        # Real Redis connection
        redis_url = get_redis_url()
        redis_client = redis.from_url(redis_url)
        redis_client.set('key', 'value')
        assert redis_client.get('key') == b'value'

    def test_api_integration(self):
        # Real HTTP calls to mock API
        response = requests.get(f"{MOCK_API_CONFIG['base_url']}/v1/users")
        assert response.status_code == 200
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

### 2. Using WorkflowBuilder Correctly
```python
# ✅ Correct usage
workflow = WorkflowBuilder()
workflow.add_node("NodeType", "node_id", {})

# ❌ Old deprecated way
# AsyncWorkflowBuilder is deprecated - use WorkflowBuilder with LocalRuntime
```

### 3. Using CycleBuilder API
```python
# ✅ New CycleBuilder API
cycle_builder = workflow.create_cycle("my_cycle")
cycle_builder.connect("node1", "output", "node2", "input")
    .max_iterations(5)
    .converge_when("condition == True")
    .build()
```

### 4. Proper Node Initialization
```python
# ✅ Correct - String-based API
workflow.add_node("PythonCodeNode", "processor", {
    "code": code
})

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

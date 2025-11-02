# Kailash SDK Test Suite

## 🚀 Quick Start - Standardized Test Environment

```bash
# One-time setup (downloads models, initializes databases)
./tests/utils/test-env setup

# Run all tier 2 (integration) tests
./tests/utils/test-env test tier2

# Check service status
./tests/utils/test-env status
```

See [test-environment/README.md](test-environment/README.md) for complete documentation.

## 🎯 Test Excellence (v0.5.0)

### Latest Achievements (v0.6.3 - Session 090)
- **Enterprise MCP E2E Testing**: 4/4 comprehensive enterprise scenarios PASSING (100% success rate) ✅
- **Custom Enterprise Nodes**: 4 production-grade nodes (TenantAssignmentNode, MCPServiceDiscoveryNode, EnterpriseMLCPExecutorNode, EnterpriseAuditLoggerNode) ✅
- **Core SDK Enhancements**: Fixed 6 critical issues (EdgeDiscovery, SSOAuthenticationNode, PythonCodeNode, StreamPublisherNode) ✅
- **Real-World Compliance**: HIPAA healthcare, SOX finance, multi-tenant isolation scenarios ✅
- **Enterprise Authentication**: SSO + MFA flows with audit trails and compliance validation ✅
- **Production Resilience**: Circuit breakers, service discovery, load balancing, streaming data processing ✅

### Previous Achievements (v0.5.0 - Session 075)
- **Production-Quality Testing**: Achieved "best production quality" standards ✅
- **Durable Gateway Testing**: 4/4 core tests PASSING (100% success rate) ✅
- **Docker Infrastructure**: Real PostgreSQL, Ollama AI, Redis, MongoDB integration ✅
- **AI/LLM Testing**: Ollama llama3.2:3b model integration with business workflows ✅
- **Real-World Scenarios**: E-commerce, fraud detection, customer support pipelines ✅
- **Business Journey E2E**: Complete order-to-fulfillment workflow validation ✅

### Previous Improvements (v0.4.0)
- **799 Tests Passing**: 100% pass rate with comprehensive coverage
- **Gateway Test Refactoring**: Updated integration tests for middleware-based architecture
- **Slow Test Optimization**: 43 slow tests properly marked, excluded from CI
- **CI Performance**: Build times reduced to <2 minutes
- **Middleware Testing**: New integration tests for enterprise middleware layer

### Previous Reorganization (Session 070)
The test suite was **completely reorganized** from 321 scattered files into a clean, maintainable structure:
- **127 test files** organized by purpose
- **Old scattered structure** → **Clean unit/integration/e2e organization**
- **Unified conftest.py** with 76+ fixtures
- **4 duplicate files removed**

## 🎯 3-Tier Testing Strategy

### Test Philosophy: Real Infrastructure + NO MOCKING (Tiers 2-3)

The Kailash SDK follows a rigorous 3-tier testing strategy that emphasizes **real infrastructure** for integration and E2E tests:

- **Tier 1 (Unit)**: Mocking allowed, isolated components (< 1s per test)
- **Tier 2 (Integration)**: **NO MOCKING** - Real Docker services required (< 5s per test)
- **Tier 3 (E2E)**: **NO MOCKING** - Complete real infrastructure (< 10s per test)

### Why NO MOCKING for Tiers 2-3?

1. **Real-world validation**: Tests must prove the system works in production
2. **Integration verification**: Mocks hide integration failures
3. **Deployment confidence**: Real tests = real confidence
4. **Configuration validation**: Real services catch config errors

### Critical Test Execution Commands

```bash
# ✅ TIER 1: Proper unit tests (mocking allowed)
python -m pytest tests/unit/ --tb=short --timeout=5 -v -m "not (integration or e2e or slow or requires_docker or requires_postgres or requires_mysql or requires_redis or requires_ollama)" --maxfail=10 -q

# ✅ TIER 2: Integration tests (NO MOCKING)
./tests/utils/test-env up && pytest tests/integration/ --timeout=5

# ✅ TIER 3: E2E tests (NO MOCKING)
./tests/utils/test-env up && pytest tests/e2e/ --timeout=10
```

## Test Organization

The test suite is organized into three main categories:

### 1. Unit Tests (`/tests/unit/`)
Fast, isolated tests that verify individual components work correctly in isolation.

- **nodes/** - Tests for individual node types
  - **ai/** - AI node tests (LLMAgent, Embedding, etc.)
  - **data/** - Data node tests (CSV, SQL, etc.)
  - **transform/** - Transform node tests (Filter, Map, etc.)
  - **logic/** - Logic node tests (Switch, Merge, etc.)
  - **security/** - Security node tests (Auth, RBAC, etc.)
  - **admin/** - Admin node tests (User/Role management)
- **workflow/** - Workflow component tests
- **runtime/** - Runtime component tests
- **utils/** - Utility function tests
- **validation/** - Validation logic tests

### 2. Integration Tests (`/tests/integration/`)
Tests that verify components work together correctly.

- **workflows/** - End-to-end workflow execution tests
- **nodes/** - Node interaction and communication tests
- **runtime/** - Runtime integration tests
- **middleware/** - Middleware integration tests (v0.4.0)
- **enterprise/** - Enterprise feature integration tests
- **test_gateway_integration.py** - Gateway tests updated for middleware architecture (v0.4.0)
- **test_durable_gateway_simple.py** - Core durable gateway functionality (NEW in v0.5.0) ✅
- **test_durable_gateway_production.py** - Production scenarios with Docker/Ollama (NEW in v0.5.0)
- **test_workflow_connection_pool.py** - Actor-based connection management tests

### 3. End-to-End Tests (`/tests/e2e/`)
Complete business scenario tests and performance benchmarks.

- **scenarios/** - Real-world business scenario tests
- **performance/** - Performance and load tests
- **test_mcp_advanced_patterns_e2e.py** - Enterprise MCP workflows (NEW in v0.6.3) ✅
  - Multi-tenant MCP with SSO + MFA authentication
  - Service discovery with circuit breaker protection
  - Streaming MCP with intelligent load balancing
  - Complete enterprise workflow (Healthcare HIPAA, Finance SOX)
- **test_durable_gateway_real_world.py** - Complete business journey E2E tests (NEW in v0.5.0)
  - E-commerce order-to-fulfillment pipelines
  - Customer support AI workflows
  - Content moderation with AI analysis
  - Personalized recommendation generation
  - System monitoring and alerting

### 4. Test Fixtures (`/tests/fixtures/`)
Shared test data, mocks, and utilities used across test suites.

## Running Tests

### Run all tests
```bash
pytest
```

### Run specific test category

#### Tier 1: Unit Tests (Fast, Isolated, < 1 second per test)
```bash
# RECOMMENDED: Proper tier 1 tests with NO MOCKING restrictions for integration/E2E
python -m pytest tests/unit/ --tb=short --timeout=5 -v -m "not (integration or e2e or slow or requires_docker or requires_postgres or requires_mysql or requires_redis or requires_ollama)" --maxfail=10 -q

# Unit tests only (basic - may include some E2E collection issues)
pytest tests/unit/

# Quick unit test run for development
python -m pytest tests/unit/ --tb=short --timeout=1 -x -q
```

#### Tier 2: Integration Tests (Component Interactions, < 5 seconds per test)
```bash
# Integration tests (requires real infrastructure - NO MOCKING!)
pytest tests/integration/

# Start infrastructure first for integration tests
./tests/utils/test-env up && ./tests/utils/test-env status
pytest tests/integration/ --timeout=5
```

#### Tier 3: E2E Tests (Complete Scenarios, < 10 seconds per test)
```bash
# E2E tests (requires full infrastructure - NO MOCKING!)
pytest tests/e2e/

# Complete E2E test run
./tests/utils/test-env up && pytest tests/e2e/ --timeout=10
```

### Run tests for specific component
```bash
# Test specific node type
pytest tests/unit/nodes/ai/

# Test workflows
pytest tests/integration/workflows/
```

### Run with coverage
```bash
pytest --cov=kailash --cov-report=html
```

### Exclude slow tests (CI-friendly)
```bash
# Skip performance benchmarks and slow integration tests
pytest -m "not slow"

# Or run only slow tests
pytest -m "slow"
```

### Run enterprise MCP tests (v0.6.3)
```bash
# All enterprise MCP E2E tests (RECOMMENDED - comprehensive enterprise scenarios)
pytest tests/e2e/test_mcp_advanced_patterns_e2e.py -v

# Specific enterprise scenarios
pytest tests/e2e/test_mcp_advanced_patterns_e2e.py::TestMCPAdvancedPatternsE2E::test_multi_tenant_mcp_with_sso_mfa -v
pytest tests/e2e/test_mcp_advanced_patterns_e2e.py::TestMCPAdvancedPatternsE2E::test_service_discovery_with_circuit_breaker -v
pytest tests/e2e/test_mcp_advanced_patterns_e2e.py::TestMCPAdvancedPatternsE2E::test_streaming_mcp_with_load_balancing -v
pytest tests/e2e/test_mcp_advanced_patterns_e2e.py::TestMCPAdvancedPatternsE2E::test_complete_enterprise_workflow -v

# All MCP-related tests
pytest -k "mcp" -v
```

### Run production-quality tests (v0.5.0)
```bash
# Core durable gateway functionality (RECOMMENDED - fast & reliable)
pytest tests/integration/test_durable_gateway_simple.py -v

# Production scenarios with Docker services
pytest tests/integration/test_durable_gateway_production.py -v

# Complete business journey E2E tests
pytest tests/e2e/test_durable_gateway_real_world.py -v

# All durable gateway tests
pytest -k "durable_gateway" -v
```

### Run middleware integration tests (v0.4.0)
```bash
# Test new middleware architecture
pytest tests/integration/test_gateway_integration.py

# Test all middleware components
pytest tests/integration/ -k "middleware"
```

### Run specific test markers
```bash
# Run only unit tests
pytest -m "unit"

# Run integration tests (excluding slow ones)
pytest -m "integration and not slow"

# Run smoke tests only
pytest -m "smoke"
```

## Test Setup

### Quick Start with Real Services

Run tests with real services (PostgreSQL, Ollama):
```bash
./run_real_tests.sh
```

This script will:
1. Start required Docker services
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

### Stop Services

```bash
cd docker
docker-compose -f docker-compose.sdk-dev.yml down
```

## Test Types & Markers

### Unit Tests (`@pytest.mark.unit`)
- Fast execution (< 1 second per test)
- No external dependencies
- Good for CI/CD pipelines
- Test individual components in isolation

### Integration Tests (`@pytest.mark.integration`)
- Test component interactions
- May use mocked or real services
- Moderate execution time
- Test workflows and communication between nodes

### E2E Tests (`@pytest.mark.e2e`)
- Complete business scenario tests
- Use real services when possible
- Longer execution time
- Test entire user journeys

### Slow Tests (`@pytest.mark.slow`)
- Performance benchmarks and load tests
- Tests with > 30 second execution time
- Excluded from CI to keep builds fast
- Include memory usage and scalability tests

### Service-Specific Tests
- `@pytest.mark.requires_postgres` - Needs PostgreSQL
- `@pytest.mark.requires_ollama` - Needs Ollama AI service
- `@pytest.mark.requires_docker` - Needs Docker environment

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
    result = await node.execute_async()
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

## Test Naming Conventions

- All test files must start with `test_` (e.g., `test_llm_agent.py`)
- Test classes should be named `Test<Component>` (e.g., `TestLLMAgent`)
- Test methods should start with `test_` and describe what they test

## Writing Tests

### Unit Test Example
```python
# tests/unit/nodes/ai/test_llm_agent.py
from kailash.nodes.ai import LLMAgentNode

class TestLLMAgentNode:
    def test_initialization(self):
        """Test node initializes with correct parameters."""
        node = LLMAgentNode(name="test_agent")
        assert node.name == "test_agent"

    def test_process_message(self):
        """Test processing a single message."""
        # Test implementation
```

### Integration Test Example
```python
# tests/integration/workflows/test_data_pipeline.py
from kailash import Workflow
from kailash.runtime import LocalRuntime

class TestDataPipeline:
    def test_csv_to_database_workflow(self, temp_data_dir):
        """Test complete CSV to database workflow."""
        workflow = Workflow("data_pipeline")
        # Build and test workflow
```

### E2E Test Example
```python
# tests/e2e/scenarios/test_customer_analytics.py
class TestCustomerAnalytics:
    def test_complete_analytics_pipeline(self):
        """Test end-to-end customer analytics scenario."""
        # Test complete business scenario
```

## Common Testing Patterns

### Using Fixtures
```python
@pytest.fixture
def sample_ workflow():
    """Create a sample workflow for testing."""
    workflow = Workflow("test")
    # Configure workflow
    return workflow
```

### Testing Async Code
```python
@pytest.mark.asyncio
async def test_async_node():
    """Test async node execution."""
    node = AsyncSQLDatabaseNode()
    result = await node.execute_async()
```

### Mocking External Services
```python
from unittest.mock import patch

@patch('kailash.nodes.api.requests.get')
def test_api_call(mock_get):
    """Test API calls with mocked responses."""
    mock_get.return_value.json.return_value = {"data": "test"}
```

### Testing Middleware Components (v0.4.0)
```python
# tests/integration/test_gateway_integration.py
import pytest
from kailash.middleware import AgentUIMiddleware, create_gateway

@pytest.mark.slow
@pytest.mark.integration
class TestMiddlewareGatewayIntegration:
    """Integration tests for the middleware-based gateway architecture."""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow_execution(self):
        """Test complete end-to-end workflow execution through middleware stack."""
        agent_ui = AgentUIMiddleware(max_sessions=10, session_timeout_minutes=5)
        gateway = create_gateway(title="E2E Test Gateway")
        gateway.agent_ui = agent_ui

        # Create session and dynamic workflow
        session_id = await agent_ui.create_session("testuser")
        workflow_id = await agent_ui.create_dynamic_workflow(session_id, workflow_config)
        execution_id = await agent_ui.execute_workflow(session_id, workflow_id, inputs={})

        # Verify results
        results = await agent_ui.get_execution_results(session_id, execution_id)
        assert results is not None

        # Cleanup
        await agent_ui.cleanup_session(session_id)
```

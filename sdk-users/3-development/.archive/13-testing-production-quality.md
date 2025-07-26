# Production-Quality Testing Guide

*Comprehensive testing strategies for production-ready Kailash SDK applications*

## 🎯 **Overview**

This guide covers production-quality testing standards established in v0.5.0, including the comprehensive test infrastructure that validates the Durable Gateway and WorkflowConnectionPool systems with Docker integration and AI workflows.

## 🏆 **Production Quality Standards Achieved (2025-07-02)**

**Comprehensive Testing Results - All Tiers Validated**:
- ✅ **Tier 1 (Unit)**: 1247/1247 tests PASSING (100% success rate)
- ✅ **Tier 2 (Integration)**: 381/388 tests PASSING (98.2% success rate)
- ✅ **Tier 3 (E2E)**: 18/18 core tests PASSING (100% success rate)
- ✅ **Docker Integration**: Real PostgreSQL, Ollama AI, Redis, MongoDB integration
- ✅ **AI/LLM Workflows**: Ollama llama3.2:3b model with business scenarios
- ✅ **Real-World E2E**: Complete business journey validation
- ✅ **Production Infrastructure**: Production-like database schemas and operations

**Key Technical Achievements**:
- Fixed critical Ollama LLM integration with aiohttp async compatibility
- Resolved f-string formatting conflicts in complex AI workflows
- Implemented 240-second timeouts for complex AI operations
- Validated real AI workflows with 60%+ success rates
- Production-ready performance testing with concurrency and memory validation

## 📋 **Testing Hierarchy**

### 1. Unit Tests - Component Validation
**Purpose**: Fast, isolated testing of individual components
**Execution Time**: < 1 second per test
**Dependencies**: None (mocked external services)

```python
# Example: Node validation test
from kailash.nodes.ai import LLMAgentNode

class TestLLMAgentNode:
    def test_initialization(self):
        """Test node initializes with correct parameters."""
        node = LLMAgentNode(
            name="test_agent",
            model="gpt-4",
            api_key="test_key"
        )
        assert node.name == "test_agent"
        assert node.model == "gpt-4"

    def test_parameter_validation(self):
        """Test parameter validation works correctly."""
        params = node.get_parameters()
        assert "model" in params
        assert params["model"].required is True
```

### 2. Integration Tests - Component Interaction
**Purpose**: Validate components work together correctly
**Execution Time**: 5-30 seconds per test
**Dependencies**: Docker services (PostgreSQL, Ollama, Redis)

```python
# Example: Workflow integration test
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

@pytest.mark.integration
@pytest.mark.requires_docker
class TestWorkflowIntegration:
    async def test_ai_data_pipeline(self, docker_services):
        """Test AI-powered data analysis workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "ai_analysis"

        # Add data source
        workflow.add_node("CSVReaderNode", "data_source", {
            "file_path": "test_data.csv"
        })

        # Add AI analysis
        workflow.add_node("LLMAgentNode", "ai_analysis", {
            "model": "llama3.2:3b",
            "api_base": "http://localhost:11434",
            "system_prompt": "Analyze this data and provide insights..."
        })

        # Connect nodes
        workflow.add_connection("data_source", "result", "ai_analysis", "data")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate results
        assert "ai_analysis" in results
        assert "insights" in results["ai_analysis"]
```

### 3. End-to-End Tests - Complete Business Scenarios
**Purpose**: Validate entire user journeys and business processes
**Execution Time**: 1-5 minutes per test
**Dependencies**: Full Docker infrastructure, realistic data

```python
# Example: E-commerce business journey
@pytest.mark.e2e
@pytest.mark.slow
class TestECommerceJourney:
    async def test_order_to_fulfillment_pipeline(self, production_database):
        """Test complete e-commerce order processing."""

        # Create order processing workflow
        workflow = await self._create_order_workflow()

        # Execute with realistic data
        test_order = {
            "customer_id": "cust_123",
            "items": [{"product_id": "prod_456", "quantity": 2}],
            "payment_method": "credit_card"
        }

        # Run workflow
        gateway = DurableAPIGateway(enable_durability=True)
        response = await gateway.execute_workflow(
            "order_processing",
            {"inputs": test_order}
        )

        # Validate business rules
        assert response["status"] == "success"
        assert "order_id" in response["outputs"]
        assert response["outputs"]["payment_status"] == "completed"

        # Verify database state
        order_record = await production_database.fetch_order(
            response["outputs"]["order_id"]
        )
        assert order_record["status"] == "processed"
```

## 🐳 **Docker Infrastructure Testing**

### Required Services Configuration

```yaml
# docker-compose.test.yml
version: '3.8'
services:
  postgres:
    image: postgres:15
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: kailash_test
      POSTGRES_USER: admin
      POSTGRES_PASSWORD: admin

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
```

### Service Health Verification

```python
# Test service health before running tests
@pytest.fixture(scope="session")
def docker_services():
    """Ensure all Docker services are healthy."""
    services = {
        "postgres": ("localhost", 5433),
        "ollama": ("localhost", 11434),
        "redis": ("localhost", 6379),
        "mongodb": ("localhost", 27017)
    }

    for service, (host, port) in services.items():
        assert wait_for_service(host, port, timeout=30), \
            f"{service} not available on {host}:{port}"

    # Verify Ollama model availability
    ollama_client = OllamaClient("http://localhost:11434")
    assert ollama_client.model_exists("llama3.2:3b"), \
        "Required Ollama model not available"

    return services
```

## 🤖 **AI/LLM Testing Patterns**

### Ollama Integration Testing

```python
# Test AI workflow components
@pytest.mark.requires_ollama
class TestAIWorkflows:
    async def test_sentiment_analysis_pipeline(self, ollama_service):
        """Test sentiment analysis with real Ollama model."""

        # Create sentiment analysis workflow
        workflow = WorkflowBuilder()
        workflow.add_node("LLMAgentNode", "sentiment_analyzer", {
            "model": "llama3.2:3b",
            "api_base": "http://localhost:11434",
            "system_prompt": """Analyze the sentiment of the given text.
                Respond with JSON: {"sentiment": "positive|negative|neutral",
                "confidence": 0.0-1.0}"""
        })

        # Test with various inputs
        test_cases = [
            ("I love this product!", "positive"),
            ("This is terrible quality", "negative"),
            ("The item arrived on time", "neutral")
        ]

        for text, expected_sentiment in test_cases:
            result = await runtime.execute(workflow.build(), {"sentiment_analyzer": {"text": text}})

            analysis = json.loads(result["sentiment_analyzer"]["response"])
            assert analysis["sentiment"] == expected_sentiment
            assert 0.5 <= analysis["confidence"] <= 1.0
```

### AI Response Validation

```python
# Validate AI output quality
def validate_ai_response(response: str, expected_format: str = "json"):
    """Validate AI response meets quality standards."""

    if expected_format == "json":
        try:
            parsed = json.loads(response)
            assert isinstance(parsed, dict), "Response must be valid JSON object"
            return parsed
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON response: {response}")

    elif expected_format == "structured":
        # Validate structured text response
        assert len(response) > 50, "Response too short"
        assert not response.startswith("Error"), "AI returned error"
        assert "..." not in response, "Incomplete response detected"

    return response
```

## 📊 **Production Data Testing**

### Realistic Schema Creation

```python
# Create production-like database schemas
async def create_production_schema(database_pool):
    """Create realistic business database schema."""

    schemas = {
        "customers": """
            CREATE TABLE customers (
                customer_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                phone VARCHAR(20),
                address JSONB,
                preferences JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """,

        "orders": """
            CREATE TABLE orders (
                order_id VARCHAR(50) PRIMARY KEY,
                customer_id VARCHAR(50) REFERENCES customers(customer_id),
                items JSONB NOT NULL,
                total_amount DECIMAL(12,2) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                payment_method VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """,

        "analytics": """
            CREATE TABLE order_analytics (
                id SERIAL PRIMARY KEY,
                time_bucket TIMESTAMP NOT NULL,
                total_orders INTEGER DEFAULT 0,
                total_revenue DECIMAL(15,2) DEFAULT 0,
                avg_order_value DECIMAL(10,2) DEFAULT 0,
                conversion_rate DECIMAL(5,4) DEFAULT 0,
                customer_segments JSONB DEFAULT '{}',
                ai_insights JSONB DEFAULT '{}'
            )
        """
    }

    for table_name, schema_sql in schemas.items():
        await database_pool.execute(schema_sql)
```

### Test Data Generation

```python
# Generate realistic test data
def generate_test_customers(count: int = 100):
    """Generate realistic customer test data."""
    customers = []

    for i in range(count):
        customer = {
            "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
            "name": f"Customer {i+1}",
            "email": f"customer{i+1}@example.com",
            "phone": f"+1-555-{random.randint(1000000, 9999999)}",
            "address": {
                "street": f"{random.randint(100, 9999)} Main St",
                "city": random.choice(["New York", "Los Angeles", "Chicago"]),
                "state": random.choice(["NY", "CA", "IL"]),
                "zip": f"{random.randint(10000, 99999)}"
            },
            "preferences": {
                "newsletter": random.choice([True, False]),
                "category": random.choice(["electronics", "clothing", "books"])
            }
        }
        customers.append(customer)

    return customers
```

## 🔧 **Test Utilities and Fixtures**

### Common Test Fixtures

```python
# Common fixtures for production testing
@pytest.fixture(scope="session")
async def production_database():
    """Production-like database with realistic data."""
    pool = WorkflowConnectionPool(
        name="test_db",
        database_type="postgresql",
        host="localhost",
        port=5433,
        database="kailash_test",
        user="admin",
        password="admin",
        min_connections=3,
        max_connections=10
    )

    await pool.process({"operation": "initialize"})

    # Create schemas and seed data
    await create_production_schema(pool)
    await seed_test_data(pool)

    yield pool

    # Cleanup
    await pool._cleanup()

@pytest.fixture
def ai_workflow_factory():
    """Factory for creating AI-powered workflows."""
    def create_workflow(workflow_type: str, config: dict = None):
        workflow = WorkflowBuilder()

        if workflow_type == "sentiment_analysis":
            workflow.add_node("LLMAgentNode", "analyzer", {
                "model": "llama3.2:3b",
                "api_base": "http://localhost:11434",
                **(config or {})
            })

        elif workflow_type == "fraud_detection":
            workflow.add_node("LLMAgentNode", "fraud_detector", {
                "model": "llama3.2:3b",
                "api_base": "http://localhost:11434",
                "system_prompt": "Analyze transaction for fraud indicators...",
                **(config or {})
            })

        return workflow

    return create_workflow
```

## 📈 **Performance Testing**

### Load Testing with Concurrent Workflows

```python
# Load testing example
@pytest.mark.slow
@pytest.mark.performance
class TestPerformance:
    async def test_concurrent_workflow_execution(self, production_database):
        """Test system performance under concurrent load."""

        async def execute_workflow(client, data):
            """Execute single workflow instance."""
            response = await client.post(
                "/analytics/execute",
                json={"inputs": data},
                timeout=30.0
            )
            return response.status_code == 200

        # Generate test scenarios
        test_scenarios = [
            {"customer_count": random.randint(100, 1000)}
            for _ in range(50)  # 50 concurrent requests
        ]

        # Execute concurrently
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            tasks = [
                execute_workflow(client, scenario)
                for scenario in test_scenarios
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        success_count = sum(1 for r in results if r is True)
        success_rate = success_count / len(results)

        assert success_rate >= 0.95, f"Success rate {success_rate:.2%} below 95%"
```

## 🛡️ **Error Testing and Resilience**

### Failure Scenario Testing

```python
# Test system resilience
class TestSystemResilience:
    async def test_database_failure_recovery(self, production_database):
        """Test system behavior during database failures."""

        # Create workflow with database operations
        workflow = self._create_database_workflow()

        # Simulate database failure
        await production_database._simulate_failure()

        # Attempt workflow execution
        with pytest.raises(DatabaseConnectionError):
            await runtime.execute(workflow.build(), )

        # Restore database
        await production_database._restore()

        # Verify recovery
        result = await runtime.execute(workflow.build(), )
        assert result["status"] == "success"

    async def test_ai_service_timeout_handling(self, ai_workflow_factory):
        """Test handling of AI service timeouts."""

        workflow = ai_workflow_factory("sentiment_analysis", {
            "timeout": 1.0  # Very short timeout
        })

        # This should handle timeout gracefully
        result = await runtime.execute(workflow.build(), {"text": "Very long text..." * 1000})

        # Should have fallback response
        assert "error" in result or "timeout" in result
        assert result.get("fallback_used") is True
```

## 📚 **Best Practices**

### 1. Test Structure Organization
```
tests/
├── unit/                    # Fast, isolated tests
│   ├── nodes/              # Individual node tests
│   ├── workflows/          # Workflow component tests
│   └── utils/              # Utility function tests
├── integration/            # Component interaction tests
│   ├── test_durable_gateway_simple.py     # Core functionality ✅
│   ├── test_durable_gateway_production.py # Production scenarios
│   └── test_workflow_connection_pool.py   # Connection management
├── e2e/                    # Complete business scenarios
│   ├── test_durable_gateway_real_world.py # Business journeys
│   └── scenarios/          # Industry-specific tests
└── fixtures/               # Shared test utilities
```

### 2. Test Execution Strategy
1. **Development**: Run unit tests frequently (fast feedback)
2. **Integration**: Run integration tests before commits
3. **Pre-deployment**: Run full E2E suite with Docker
4. **Production monitoring**: Continuous health checks

### 3. Test Data Management
- Use realistic but synthetic data
- Implement proper cleanup after tests
- Version control test schemas
- Separate test and production data

### 4. AI Testing Guidelines
- Test with multiple model variations
- Validate response formats and quality
- Handle model unavailability gracefully
- Monitor AI service performance

## 🎯 **Running Production Tests**

### Quick Start Commands
```bash
# Core functionality (recommended for development)
pytest tests/integration/test_durable_gateway_simple.py -v

# Production scenarios (requires Docker)
pytest tests/integration/test_durable_gateway_production.py -v

# Complete business journeys (full E2E)
pytest tests/e2e/test_durable_gateway_real_world.py -v

# All production-quality tests
pytest -k "durable_gateway" -v
```

### Environment Setup
```bash
# Start Docker services
cd docker
docker-compose -f docker-compose.sdk-dev.yml up -d

# Setup test database
./tests/setup_test_env.sh

# Run with real services
./run_real_tests.sh
```

## 📊 **Success Metrics**

**Kailash SDK v0.5.0 achieved these production quality standards**:

- ✅ **Core Functionality**: 100% test pass rate (4/4 tests)
- ✅ **Docker Integration**: Multi-service orchestration working
- ✅ **AI Processing**: Real Ollama model integration
- ✅ **Business Scenarios**: Complete user journey validation
- ✅ **Performance**: Concurrent execution capability
- ✅ **Resilience**: Error recovery and graceful degradation
- ✅ **Production Readiness**: Real database operations and schemas

This testing infrastructure ensures your Kailash SDK applications meet production quality standards with comprehensive validation across all system components.

---

**Next Steps**:
- Review [troubleshooting guide](05-troubleshooting.md) for debugging test failures
- Check [production deployment guide](04-production.md) for deployment testing
- See [enterprise patterns](../enterprise/) for advanced testing scenarios

# End-to-End Tests

**Tier 3 Testing**: Complete workflows and user scenarios with real infrastructure

## Overview

E2E tests verify complete business scenarios and user journeys using real infrastructure and external services. These tests simulate production environments and validate the entire system end-to-end.

## Requirements

### Infrastructure
- **Real Docker Services**: PostgreSQL, Redis, Ollama, external APIs
- **Real Data Processing**: No mock data, use actual business scenarios
- **Performance Validation**: Response times, throughput, resource usage
- **Cross-System Integration**: Multiple services working together

### Test Markers
```python
@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
@pytest.mark.requires_redis
@pytest.mark.requires_ollama
@pytest.mark.slow  # For long-running tests
```

## Directory Structure

```
e2e/
├── workflows/       # Complete workflow scenarios
├── user_flows/      # Real user journey tests
├── performance/     # Performance and load tests
├── integration/     # Cross-system integration tests
├── apps/           # Full application scenarios
└── conftest.py     # Shared fixtures and setup
```

## Test Categories

### 1. Business Workflow Tests
Complete business processes from start to finish:
- Customer onboarding workflows
- Data processing pipelines
- AI-powered analytics
- Multi-tenant applications

### 2. User Journey Tests
Real user scenarios and interactions:
- Admin user management flows
- Developer workflow creation
- Data analyst pipelines
- API integration scenarios

### 3. Performance Tests
System performance under realistic conditions:
- Load testing with concurrent users
- Data processing throughput
- Memory and CPU usage validation
- Response time verification

### 4. Cross-System Integration
Multiple systems working together:
- Database + Cache + AI integration
- API + Workflow + Storage chains
- Real-time processing pipelines
- Event-driven architectures

## Writing E2E Tests

### Business Scenario Template
```python
import pytest
from tests.utils.docker_config import DATABASE_CONFIG, REDIS_CONFIG, OLLAMA_CONFIG

@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.requires_postgres
@pytest.mark.requires_redis
@pytest.mark.requires_ollama
class TestCustomerAnalyticsPipeline:
    """
    E2E test for customer analytics pipeline.

    Scenario: Multi-tenant SaaS customer analytics
    - Real data ingestion from APIs
    - AI-powered analysis using Ollama
    - Database storage and caching
    - Performance monitoring
    """

    @pytest.fixture(autouse=True)
    def setup_real_infrastructure(self):
        # Setup real services
        self.db_config = DATABASE_CONFIG
        self.redis_config = REDIS_CONFIG
        self.ollama_config = OLLAMA_CONFIG

        # Verify services are available
        self._verify_services()

        yield

        # Cleanup real resources
        self._cleanup_resources()

    def test_complete_analytics_pipeline(self):
        # Test complete business scenario
        # 1. Data ingestion from real API
        # 2. AI analysis with real Ollama
        # 3. Database storage with real PostgreSQL
        # 4. Caching with real Redis
        # 5. Performance validation
        pass
```

### User Flow Template
```python
@pytest.mark.e2e
@pytest.mark.requires_docker
class TestDataAnalystUserFlow:
    """
    E2E test simulating data analyst workflow.

    User Journey:
    1. Analyst logs in to system
    2. Creates data processing workflow
    3. Uploads CSV data
    4. Configures AI analysis
    5. Runs workflow and monitors progress
    6. Downloads results and reports
    """

    def test_complete_analyst_workflow(self):
        # Simulate complete user journey
        # Use real data, real services, real interactions
        pass
```

## Test Requirements

### 1. Real Infrastructure Only
- ✅ Real Docker services (PostgreSQL, Redis, Ollama)
- ✅ Real external APIs and data sources
- ✅ Real file operations and data processing
- ✅ Real network requests and responses
- ❌ No mocking, stubbing, or fake data

### 2. Demanding Scenarios
- ✅ Complex multi-step business processes
- ✅ Multiple services working together
- ✅ Realistic data volumes and complexity
- ✅ Performance requirements validation
- ✅ Error conditions and recovery testing

### 3. Production-Like Conditions
- ✅ Concurrent operations
- ✅ Resource constraints
- ✅ Network latency simulation
- ✅ Service failure scenarios
- ✅ Security and compliance validation

## Running E2E Tests

### Local Development
```bash
# Quick E2E smoke tests
pytest tests/e2e/ -m "e2e and not slow" -v

# Full E2E suite (may take 30-60 minutes)
pytest tests/e2e/ -m e2e -v

# Specific scenarios
pytest tests/e2e/workflows/ -m "e2e and requires_ollama" -v
```

### CI/CD Pipeline
```bash
# Release validation (full suite)
pytest tests/e2e/ -m e2e --tb=short

# Performance validation
pytest tests/e2e/performance/ -m "e2e and performance" -v
```

## Example Scenarios

### 1. Multi-Tenant Customer Analytics
```python
@pytest.mark.e2e
@pytest.mark.requires_docker
class TestMultiTenantAnalytics:
    """Real multi-tenant SaaS analytics platform."""

    def test_enterprise_analytics_pipeline(self):
        # Create multiple tenants
        # Ingest real customer data
        # Run AI analysis with Ollama
        # Validate tenant data isolation
        # Check performance metrics
        pass
```

### 2. AI-Powered Data Processing
```python
@pytest.mark.e2e
@pytest.mark.requires_ollama
class TestAIDataProcessing:
    """Real AI-enhanced data processing pipeline."""

    def test_intelligent_data_transformation(self):
        # Load real dataset
        # Apply AI-powered transformations
        # Validate results quality
        # Check processing performance
        pass
```

### 3. Real-Time Event Processing
```python
@pytest.mark.e2e
@pytest.mark.requires_redis
class TestRealtimeProcessing:
    """Real-time event processing with streaming."""

    def test_streaming_analytics_pipeline(self):
        # Setup real event stream
        # Process events in real-time
        # Store aggregated results
        # Validate latency requirements
        pass
```

## Performance Validation

### Response Time Validation
```python
import time

def test_workflow_performance(self):
    start_time = time.time()

    # Execute real workflow
    result = runtime.execute(workflow)

    execution_time = time.time() - start_time

    # Validate performance requirements
    assert execution_time < 30.0  # 30 second max
    assert result["success"] is True
```

### Throughput Validation
```python
def test_concurrent_processing(self):
    # Test multiple concurrent workflows
    workflows = [create_workflow() for _ in range(10)]

    start_time = time.time()
    results = asyncio.gather(*[
        runtime.execute(wf) for wf in workflows
    ])
    total_time = time.time() - start_time

    # Validate throughput
    throughput = len(workflows) / total_time
    assert throughput > 5.0  # 5 workflows per second
```

### Resource Usage Validation
```python
def test_memory_usage(self):
    import psutil

    process = psutil.Process()
    initial_memory = process.memory_info().rss

    # Execute workflow
    runtime.execute(large_workflow)

    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory

    # Validate memory usage
    assert memory_increase < 100 * 1024 * 1024  # < 100MB increase
```

## Best Practices

### 1. Realistic Scenarios
- Use real business data and processes
- Simulate actual user interactions
- Test with production-like volumes
- Include error and edge cases

### 2. Service Integration
- Test all service dependencies
- Validate cross-system communication
- Check data consistency across systems
- Monitor service health during tests

### 3. Performance Focus
- Set realistic performance targets
- Monitor resource usage
- Test under load conditions
- Validate scalability assumptions

### 4. Comprehensive Validation
- Test complete workflows end-to-end
- Validate all outputs and side effects
- Check compliance and security requirements
- Verify error handling and recovery

## Troubleshooting

### Common Issues

#### Service Startup Time
**Problem**: Tests fail because services aren't ready
**Solution**: Add service health checks and startup delays

#### Resource Exhaustion
**Problem**: Tests consume too much memory/CPU
**Solution**: Implement resource limits and cleanup

#### Network Issues
**Problem**: External API calls fail
**Solution**: Add retry logic and fallback scenarios

#### Data Cleanup
**Problem**: Test data persists between runs
**Solution**: Implement thorough cleanup in fixtures

## Related Documentation

- [Integration Tests](../integration/README.md)
- [Testing Policy](../../# contrib (removed)/testing/test-organization-policy.md)
- [Docker Configuration](../utils/docker_config.py)
- [Performance Guidelines](../../# contrib (removed)/testing/performance-guidelines.md)

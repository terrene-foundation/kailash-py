# Production-Quality Testing Guide

*Comprehensive testing strategies for production-ready Kailash SDK applications*

## Overview

This guide covers production-quality testing standards for Kailash SDK applications, including unit, integration, and end-to-end testing with Docker integration and AI workflows.

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core concepts
- Completed [Workflows](02-workflows.md) - Workflow basics
- Docker installed for integration testing
- Understanding of pytest framework

## TODO-111 Testing Patterns

**Core SDK Architecture Testing**: Following the completion of TODO-111, the SDK now includes comprehensive testing patterns for critical infrastructure components:

### Critical Methods Testing
Based on TODO-111 implementation, always test these patterns:

```python
# CyclicWorkflowExecutor testing
def test_execute_dag_portion():
    """Test DAG execution with proper state management."""
    executor = CyclicWorkflowExecutor()
    # Test _execute_dag_portion method

def test_execute_cycle_groups():
    """Test cycle group execution in sequence."""
    executor = CyclicWorkflowExecutor()
    # Test _execute_cycle_groups method

def test_propagate_parameters():
    """Test parameter flow between iterations."""
    executor = CyclicWorkflowExecutor()
    # Test _propagate_parameters method
```

### Constructor Flexibility Testing
```python
# WorkflowVisualizer testing
def test_optional_workflow_constructor():
    """Test WorkflowVisualizer with optional workflow parameter."""
    visualizer = WorkflowVisualizer()  # No workflow required
    assert visualizer.workflow is None

    visualizer.workflow = mock_workflow
    assert visualizer.workflow is not None
```

### Event Handling Testing
```python
# ConnectionManager testing
def test_filter_events():
    """Test event filtering by session, user, type."""
    manager = ConnectionManager()
    # Test filter_events method

def test_process_event():
    """Test async event processing."""
    manager = ConnectionManager()
    # Test process_event method
```

## Testing Hierarchy

### 1. Unit Tests - Component Validation

**Purpose**: Fast, isolated testing of individual components
**Execution Time**: < 1 second per test
**Dependencies**: None (mocked external services)

```python
# Example: Node validation test
import pytest
from kailash.nodes.base import Node, NodeParameter

class TestCustomNode:
    def test_initialization(self):
        """Test node initializes with correct parameters."""
        from kailash.nodes.data import CSVReaderNode

        node = CSVReaderNode(
            name="test_reader",
            file_path="data.csv"
        )
        assert node._name == "test_reader"
        assert hasattr(node, 'file_path')

    def test_parameter_validation(self):
        """Test parameter validation works correctly."""
        from kailash.nodes.data import CSVReaderNode

        node = CSVReaderNode(name="reader")
        params = node.get_parameters()
        assert "file_path" in params
        assert params["file_path"].required is True
```

### 2. Integration Tests - Component Interaction

**Purpose**: Validate components work together correctly
**Execution Time**: 5-30 seconds per test
**Dependencies**: Docker services (PostgreSQL, Redis)

```python
# Example: Workflow integration test
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

@pytest.mark.integration
class TestWorkflowIntegration:
    def test_data_pipeline(self):
        """Test data processing workflow."""
        workflow = WorkflowBuilder()
        workflow.name = "test_pipeline"

        # Add data source
        workflow.add_node("PythonCodeNode", "data_source", {
            "code": "result = {'data': [1, 2, 3, 4, 5]}"
        })

        # Add processor
        workflow.add_node("PythonCodeNode", "processor", {
            "code": """
data_list = data  # From connection
result = {
    'count': len(data_list),
    'sum': sum(data_list),
    'average': sum(data_list) / len(data_list)
}
"""
        })

        # Connect nodes
        workflow.add_connection("data_source", "result.data", "processor", "data")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate results
        assert "processor" in results
        assert results["processor"]["result"]["count"] == 5  # PythonCodeNode wraps in 'result'
        assert results["processor"]["result"]["sum"] == 15
        assert results["processor"]["result"]["average"] == 3.0
```

### 3. End-to-End Tests - Complete Business Scenarios

**Purpose**: Validate entire user journeys and business processes
**Execution Time**: 1-5 minutes per test
**Dependencies**: Full Docker infrastructure

```python
# Example: Business scenario test
@pytest.mark.e2e
@pytest.mark.slow
class TestBusinessScenarios:
    async def test_data_processing_pipeline(self):
        """Test complete data processing journey."""

        # Create workflow with real components
        workflow = WorkflowBuilder()

        # Add CSV reader
        workflow.add_node("CSVReaderNode", "reader", {
            "file_path": "test_data.csv"
        })

        # Add data processor
        workflow.add_node("PythonCodeNode", "processor", {
            "code": """
# Process CSV data
processed = []
for row in csv_data:
    if float(row.get('value', 0)) > 100:
        processed.append(row)
result = {'filtered_data': processed, 'count': len(processed)}
"""
        })

        # Connect and execute
        workflow.add_connection("reader", "result", "processor", "csv_data")

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Validate business rules
        assert results["processor"]["result"]["count"] > 0  # Access via nested 'result' key
        assert all(float(row['value']) > 100 for row in results["processor"]["result"]["filtered_data"])
```

## Docker Infrastructure Testing

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

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
```

### Service Health Verification

```python
# Pytest fixture for Docker services
import socket
import time

def wait_for_service(host, port, timeout=30):
    """Wait for a service to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        time.sleep(1)
    return False

@pytest.fixture(scope="session")
def docker_services():
    """Ensure all Docker services are healthy."""
    services = {
        "postgres": ("localhost", 5433),
        "redis": ("localhost", 6379)
    }

    for service, (host, port) in services.items():
        assert wait_for_service(host, port), f"{service} not available"

    return services
```

## AI/LLM Testing Patterns

### AI Response Validation

```python
import json

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

# Example test using validation
def test_ai_processing():
    """Test AI response validation."""
    # Simulate AI response
    ai_response = '{"sentiment": "positive", "confidence": 0.85}'

    # Validate response
    result = validate_ai_response(ai_response, "json")
    assert result["sentiment"] in ["positive", "negative", "neutral"]
    assert 0 <= result["confidence"] <= 1
```

## Production Data Testing

### Realistic Test Data Generation

```python
import random
import uuid

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

# Use in tests
def test_with_realistic_data():
    """Test with production-like data."""
    customers = generate_test_customers(50)

    # Process customers through workflow
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": """
# Filter customers by preference
filtered = [c for c in customers if c['preferences']['newsletter']]
result = {'newsletter_subscribers': filtered, 'count': len(filtered)}
"""
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), parameters={
        "processor": {"customers": customers}
    })

    # Validate business logic
    assert results["processor"]["result"]["count"] > 0  # PythonCodeNode result nesting
    assert all(c['preferences']['newsletter'] for c in results["processor"]["result"]["newsletter_subscribers"])
```

## Test Utilities and Fixtures

### Common Test Fixtures

```python
@pytest.fixture
def sample_workflow():
    """Create a sample workflow for testing."""
    workflow = WorkflowBuilder()
    workflow.name = "test_workflow"

    workflow.add_node("PythonCodeNode", "source", {
        "code": "result = {'data': list(range(10))}"
    })

    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'processed': [x * 2 for x in data]}"
    })

    workflow.add_connection("source", "result.data", "processor", "data")

    return workflow

@pytest.fixture
def runtime():
    """Create LocalRuntime instance."""
    return LocalRuntime()

# Use fixtures in tests
def test_workflow_execution(sample_workflow, runtime):
    """Test workflow execution with fixtures."""
    results, run_id = runtime.execute(sample_workflow.build())

    assert results["processor"]["result"]["processed"] == [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]  # Nested result access
    assert run_id is not None
```

## Performance Testing

### Load Testing Pattern

```python
import asyncio
import time

async def test_concurrent_execution():
    """Test system performance under load."""
    workflow = WorkflowBuilder()

    # Simple workflow for load testing
    workflow.add_node("PythonCodeNode", "processor", {
        "code": """
import time
time.sleep(0.1)  # Simulate processing
result = {'processed': True, 'timestamp': time.time()}
"""
    })

    runtime = LocalRuntime()

    # Execute multiple workflows concurrently
    start_time = time.time()
    tasks = []

    for i in range(10):
        # Note: LocalRuntime.execute is synchronous
        # For async, use AsyncLocalRuntime
        task = asyncio.create_task(
            asyncio.to_thread(runtime.execute, workflow.build())
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    # Measure performance
    duration = time.time() - start_time
    assert duration < 5.0  # Should complete in under 5 seconds
    assert len(results) == 10
    assert all(r[0]["processor"]["processed"] for r in results)
```

## Best Practices

### 1. Test Structure Organization

```
tests/
├── unit/                    # Fast, isolated tests
│   ├── nodes/              # Individual node tests
│   ├── workflows/          # Workflow component tests
│   └── utils/              # Utility function tests
├── integration/            # Component interaction tests
│   ├── test_workflow_execution.py
│   └── test_node_connections.py
├── e2e/                    # Complete business scenarios
│   └── test_business_workflows.py
└── fixtures/               # Shared test utilities
    └── common.py
```

### 2. Test Naming Convention

```python
# Clear, descriptive test names
def test_csv_reader_handles_empty_file():
    """Test that CSVReaderNode handles empty files gracefully."""
    pass

def test_workflow_retry_on_transient_failure():
    """Test that workflow retries on transient failures."""
    pass

def test_parameter_validation_rejects_invalid_types():
    """Test that parameter validation rejects invalid types."""
    pass
```

### 3. Test Data Management

```python
# Use fixtures for test data
@pytest.fixture
def sample_csv_data():
    """Provide sample CSV data for tests."""
    return [
        {"id": "1", "name": "Alice", "value": "100"},
        {"id": "2", "name": "Bob", "value": "200"},
        {"id": "3", "name": "Charlie", "value": "300"}
    ]

# Use the fixture
def test_csv_processing(sample_csv_data):
    """Test CSV data processing."""
    # Test implementation
    pass
```

### 4. Error Testing

```python
def test_node_handles_invalid_input():
    """Test node error handling."""
    workflow = WorkflowBuilder()

    # Add node with invalid configuration
    workflow.add_node("CSVReaderNode", "reader", {
        "file_path": "/nonexistent/file.csv"
    })

    runtime = LocalRuntime()

    # Should handle error gracefully
    with pytest.raises(FileNotFoundError):
        runtime.execute(workflow.build())
```

## Running Tests

### Quick Start Commands

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit -v
pytest tests/integration -v
pytest tests/e2e -v

# Run with coverage
pytest --cov=kailash --cov-report=html

# Run specific test file
pytest tests/unit/test_nodes.py -v

# Run tests matching pattern
pytest -k "csv" -v
```

### Environment Setup

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Start Docker services
docker-compose -f docker-compose.test.yml up -d

# Run tests
pytest

# Stop Docker services
docker-compose -f docker-compose.test.yml down
```

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Workflow basics

**Advanced Topics:**
- [Production Deployment](04-production.md) - Production readiness
- [Troubleshooting](../validation/common-mistakes.md) - Common issues

---

**Build robust, well-tested Kailash SDK applications with comprehensive testing at every level!**

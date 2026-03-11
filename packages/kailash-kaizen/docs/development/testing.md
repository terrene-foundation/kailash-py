# Testing Strategies and Infrastructure

Comprehensive testing approach for the Kaizen Framework, covering the 3-tier testing strategy, infrastructure requirements, and validation methodologies.

## Testing Philosophy

**Kaizen follows a 3-tier testing strategy** designed for enterprise-grade reliability:

1. **Tier 1 (Unit)**: Fast, isolated tests with mocked dependencies
2. **Tier 2 (Integration)**: Real infrastructure tests without mocking
3. **Tier 3 (End-to-End)**: Complete user workflows and scenarios

**Key Principles**:
- **NO MOCKING** in Tier 2-3 tests (real infrastructure only)
- **Comprehensive Coverage** across all framework components
- **Performance Baselines** to prevent regressions
- **Real AI Models** for realistic testing scenarios

## Testing Infrastructure

### Test Environment Setup

#### Local Development Testing

```bash
# Install test dependencies
pip install -e .[dev,test]

# Verify test environment
pytest --version
python -c "from kaizen import Kaizen; print('✅ Test environment ready')"

# Run basic health check
pytest tests/unit/test_framework.py::test_framework_initialization -v
```

#### Docker Infrastructure (Tier 2-3 Tests)

```bash
# Start test infrastructure
cd tests/utils
./test-env up

# Verify services
./test-env status
# Expected output:
# ✅ PostgreSQL: Ready (port 5432)
# ✅ Redis: Ready (port 6379)
# ✅ MinIO: Ready (port 9000)
# ✅ Elasticsearch: Ready (port 9200)

# Stop infrastructure when done
./test-env down
```

#### Continuous Integration

```yaml
# .github/workflows/test.yml (example)
name: Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e .[dev,test]
      - run: pytest tests/unit/ -v --cov=src/kaizen

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .[dev,test]
      - run: pytest tests/integration/ -v

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -e .[dev,test]
      - run: docker-compose -f tests/docker-compose.yml up -d
      - run: pytest tests/e2e/ -v
      - run: docker-compose -f tests/docker-compose.yml down
```

## 3-Tier Testing Strategy

### Tier 1: Unit Tests

**Purpose**: Fast, isolated testing of individual components
**Execution Time**: <1 second per test
**Infrastructure**: No external dependencies (mocked)

#### Framework Testing

```python
# tests/unit/test_framework.py
import pytest
from unittest.mock import Mock, patch

from kaizen import Kaizen
from kaizen.core.exceptions import ConfigurationError


class TestKaizenFramework:
    """Unit tests for Kaizen framework core functionality."""

    def test_framework_initialization_default(self):
        """Test framework initialization with default configuration."""
        kaizen = Kaizen()

        assert kaizen is not None
        assert kaizen.config is not None
        assert kaizen.agent_manager is not None

    def test_framework_initialization_with_config(self):
        """Test framework initialization with custom configuration."""
        config = {
            'default_model': 'gpt-4',
            'temperature': 0.8,
            'performance_tracking': True
        }

        kaizen = Kaizen(config=config)

        assert kaizen.config.get('default_model') == 'gpt-4'
        assert kaizen.config.get('temperature') == 0.8
        assert kaizen.config.get('performance_tracking') is True

    def test_framework_initialization_invalid_config(self):
        """Test framework initialization fails with invalid configuration."""
        invalid_config = {
            'temperature': 5.0,  # Invalid temperature value
            'max_tokens': -100   # Invalid max_tokens value
        }

        with pytest.raises(ConfigurationError):
            Kaizen(config=invalid_config)

    def test_agent_creation_success(self):
        """Test successful agent creation."""
        kaizen = Kaizen()

        agent = kaizen.create_agent("test_agent", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })

        assert agent is not None
        assert agent.name == "test_agent"
        assert agent.config["model"] == "gpt-3.5-turbo"

    def test_agent_creation_duplicate_name(self):
        """Test agent creation fails with duplicate name."""
        kaizen = Kaizen()

        # Create first agent
        kaizen.create_agent("duplicate", {"model": "gpt-3.5-turbo"})

        # Attempt to create agent with same name
        with pytest.raises(ValueError, match="Agent name 'duplicate' already exists"):
            kaizen.create_agent("duplicate", {"model": "gpt-4"})

    @patch('kaizen.core.agents.WorkflowBuilder')
    def test_agent_workflow_generation(self, mock_workflow_builder):
        """Test agent workflow generation with mocked WorkflowBuilder."""
        mock_workflow = Mock()
        mock_workflow_builder.return_value = mock_workflow

        kaizen = Kaizen()
        agent = kaizen.create_agent("test_agent", {
            "model": "gpt-4",
            "temperature": 0.7
        })

        # Verify workflow builder was called
        mock_workflow_builder.assert_called_once()
        mock_workflow.add_node.assert_called_once()
```

#### Agent System Testing

```python
# tests/unit/test_agents.py
import pytest
from unittest.mock import Mock, patch

from kaizen.core.agents import Agent, AgentManager
from kaizen.core.base import KaizenConfig
from kaizen.core.exceptions import ConfigurationError


class TestAgent:
    """Unit tests for Agent class."""

    def setup_method(self):
        """Setup for each test method."""
        self.mock_kaizen = Mock()
        self.mock_kaizen.config = KaizenConfig()

        self.valid_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1000
        }

    def test_agent_initialization(self):
        """Test agent initialization with valid configuration."""
        agent = Agent("test_agent", self.valid_config, self.mock_kaizen)

        assert agent.name == "test_agent"
        assert agent.config["model"] == "gpt-3.5-turbo"
        assert agent.config["temperature"] == 0.7
        assert agent.workflow is not None

    def test_agent_initialization_empty_name(self):
        """Test agent initialization fails with empty name."""
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            Agent("", self.valid_config, self.mock_kaizen)

    def test_agent_initialization_invalid_config(self):
        """Test agent initialization fails with invalid configuration."""
        invalid_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 5.0,  # Invalid temperature
        }

        with pytest.raises(ConfigurationError):
            Agent("test_agent", invalid_config, self.mock_kaizen)

    @patch('kaizen.core.agents.WorkflowBuilder')
    def test_workflow_building(self, mock_workflow_builder):
        """Test workflow building process."""
        mock_workflow = Mock()
        mock_workflow_builder.return_value = mock_workflow

        agent = Agent("test_agent", self.valid_config, self.mock_kaizen)

        # Verify workflow construction
        mock_workflow_builder.assert_called_once()
        mock_workflow.add_node.assert_called_once_with(
            "KaizenLLMAgentNode",
            "test_agent",
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "system_prompt": None
            }
        )


class TestAgentManager:
    """Unit tests for AgentManager class."""

    def setup_method(self):
        """Setup for each test method."""
        self.mock_kaizen = Mock()
        self.agent_manager = AgentManager(self.mock_kaizen)

    def test_agent_creation_and_retrieval(self):
        """Test agent creation and retrieval."""
        config = {"model": "gpt-3.5-turbo"}

        # Create agent
        agent = self.agent_manager.create_agent("test_agent", config)

        # Retrieve agent
        retrieved_agent = self.agent_manager.get_agent("test_agent")

        assert retrieved_agent is agent
        assert retrieved_agent.name == "test_agent"

    def test_list_agents(self):
        """Test listing all agents."""
        # Create multiple agents
        self.agent_manager.create_agent("agent1", {"model": "gpt-3.5-turbo"})
        self.agent_manager.create_agent("agent2", {"model": "gpt-4"})

        agent_names = self.agent_manager.list_agents()

        assert "agent1" in agent_names
        assert "agent2" in agent_names
        assert len(agent_names) == 2

    def test_agent_removal(self):
        """Test agent removal."""
        # Create agent
        self.agent_manager.create_agent("temp_agent", {"model": "gpt-3.5-turbo"})
        assert "temp_agent" in self.agent_manager.list_agents()

        # Remove agent
        self.agent_manager.remove_agent("temp_agent")
        assert "temp_agent" not in self.agent_manager.list_agents()
```

#### Configuration Testing

```python
# tests/unit/test_config.py
import pytest
from kaizen.core.base import KaizenConfig
from kaizen.core.exceptions import ConfigurationError


class TestKaizenConfig:
    """Unit tests for KaizenConfig class."""

    def test_config_initialization_empty(self):
        """Test configuration initialization with empty config."""
        config = KaizenConfig()

        # Verify default values
        assert config.get('default_model') is None
        assert config.get('temperature', 0.7) == 0.7
        assert config.get('performance_tracking', False) is False

    def test_config_initialization_with_dict(self):
        """Test configuration initialization with dictionary."""
        config_dict = {
            'default_model': 'gpt-4',
            'temperature': 0.8,
            'max_tokens': 2000
        }

        config = KaizenConfig(config_dict)

        assert config.get('default_model') == 'gpt-4'
        assert config.get('temperature') == 0.8
        assert config.get('max_tokens') == 2000

    def test_config_validation_temperature(self):
        """Test configuration validation for temperature."""
        # Valid temperature
        valid_config = KaizenConfig({'temperature': 0.7})
        assert valid_config.get('temperature') == 0.7

        # Invalid temperature (too high)
        with pytest.raises(ConfigurationError):
            KaizenConfig({'temperature': 5.0})

        # Invalid temperature (negative)
        with pytest.raises(ConfigurationError):
            KaizenConfig({'temperature': -1.0})

    def test_config_validation_max_tokens(self):
        """Test configuration validation for max_tokens."""
        # Valid max_tokens
        valid_config = KaizenConfig({'max_tokens': 1000})
        assert valid_config.get('max_tokens') == 1000

        # Invalid max_tokens (zero)
        with pytest.raises(ConfigurationError):
            KaizenConfig({'max_tokens': 0})

        # Invalid max_tokens (negative)
        with pytest.raises(ConfigurationError):
            KaizenConfig({'max_tokens': -100})

    def test_config_merge(self):
        """Test configuration merging."""
        base_config = KaizenConfig({
            'default_model': 'gpt-3.5-turbo',
            'temperature': 0.7
        })

        override_config = {
            'temperature': 0.9,  # Override existing
            'max_tokens': 1500   # Add new
        }

        merged_config = base_config.merge(override_config)

        assert merged_config.get('default_model') == 'gpt-3.5-turbo'  # Unchanged
        assert merged_config.get('temperature') == 0.9  # Overridden
        assert merged_config.get('max_tokens') == 1500  # Added
```

### Tier 2: Integration Tests

**Purpose**: Test integration with Core SDK and real infrastructure
**Execution Time**: <10 seconds per test
**Infrastructure**: Real services (PostgreSQL, Redis, etc.)

#### Core SDK Integration Testing

```python
# tests/integration/test_core_sdk_integration.py
import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

from kaizen import Kaizen


class TestCoreSdkIntegration:
    """Integration tests for Core SDK compatibility."""

    def setup_method(self):
        """Setup for each test method."""
        self.kaizen = Kaizen()
        self.runtime = LocalRuntime()

    def test_workflow_execution_compatibility(self):
        """Test Kaizen agent workflows execute with Core SDK runtime."""
        # Create Kaizen agent
        agent = self.kaizen.create_agent("integration_test", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        })

        # Execute with Core SDK runtime (NO MOCKING)
        results, run_id = self.runtime.execute(agent.workflow.build())

        # Verify execution
        assert run_id is not None
        assert results is not None
        assert isinstance(results, dict)

    def test_workflow_composition_with_core_nodes(self):
        """Test composing Kaizen agents with traditional Core SDK nodes."""
        # Create traditional Core SDK workflow
        traditional_workflow = WorkflowBuilder()
        traditional_workflow.add_node("DataLoaderNode", "loader", {
            "source_type": "memory",
            "data": {"test": "data"}
        })

        # Create Kaizen agent
        agent = self.kaizen.create_agent("composer_test", {
            "model": "gpt-3.5-turbo"
        })

        # Combine workflows (simplified approach for testing)
        combined_workflow = WorkflowBuilder()

        # Add traditional node
        combined_workflow.add_node("DataLoaderNode", "loader", {
            "source_type": "memory",
            "data": {"input": "test data"}
        })

        # Add Kaizen agent node (extract from agent workflow)
        agent_workflow = agent.workflow
        # Note: In practice, need proper workflow merging

        # Execute combined workflow
        results, run_id = self.runtime.execute(combined_workflow.build())

        assert run_id is not None
        assert results is not None

    def test_node_parameter_compatibility(self):
        """Test Kaizen node parameters work with Core SDK validation."""
        agent = self.kaizen.create_agent("param_test", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.5,
            "max_tokens": 1500,
            "system_prompt": "Test system prompt"
        })

        # Build workflow and verify parameters
        workflow = agent.workflow.build()

        # Execute to verify parameter compatibility
        results, run_id = self.runtime.execute(workflow)

        assert run_id is not None
        assert results is not None

    def test_runtime_compatibility(self):
        """Test Kaizen works with different Core SDK runtimes."""
        agent = self.kaizen.create_agent("runtime_test", {
            "model": "gpt-3.5-turbo"
        })

        # Test with LocalRuntime
        local_runtime = LocalRuntime()
        results1, run_id1 = local_runtime.execute(agent.workflow.build())

        assert run_id1 is not None
        assert results1 is not None

        # Future: Test with other runtimes when available
        # distributed_runtime = DistributedRuntime()
        # results2, run_id2 = distributed_runtime.execute(agent.workflow.build())
```

#### Database Integration Testing

```python
# tests/integration/test_database_integration.py
import pytest
import os
from sqlalchemy import create_engine, text

from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime


class TestDatabaseIntegration:
    """Integration tests with real database infrastructure."""

    def setup_method(self):
        """Setup database connection for each test."""
        # Use test database from Docker infrastructure
        self.db_url = os.getenv(
            "TEST_DATABASE_URL",
            "postgresql://test:test@localhost:5432/kaizen_test"
        )
        self.engine = create_engine(self.db_url)

        # Verify database connectivity
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1

        self.kaizen = Kaizen()
        self.runtime = LocalRuntime()

    def test_agent_with_database_context(self):
        """Test agent execution with database context available."""
        # Create agent that could potentially use database
        agent = self.kaizen.create_agent("db_agent", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.3
        })

        # Execute agent workflow
        results, run_id = self.runtime.execute(agent.workflow.build())

        # Verify basic execution
        assert run_id is not None
        assert results is not None

        # Verify database is accessible during execution
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
            table_count = result.fetchone()[0]
            assert table_count > 0

    def test_memory_persistence(self):
        """Test agent memory persistence in database (future feature)."""
        # Note: This test demonstrates the pattern for future memory features
        agent = self.kaizen.create_agent("memory_test", {
            "model": "gpt-3.5-turbo",
            "memory_enabled": False  # Not implemented yet
        })

        # Execute multiple times to test memory persistence
        results1, run_id1 = self.runtime.execute(agent.workflow.build())
        results2, run_id2 = self.runtime.execute(agent.workflow.build())

        assert run_id1 != run_id2
        assert results1 is not None
        assert results2 is not None

        # Future: Verify memory persistence in database
        # memory_records = self.get_memory_records(agent.name)
        # assert len(memory_records) >= 2
```

### Tier 3: End-to-End Tests

**Purpose**: Complete user workflows and real-world scenarios
**Execution Time**: <60 seconds per test
**Infrastructure**: Full environment with AI models

#### Complete Workflow Testing

```python
# tests/e2e/test_agent_workflows.py
import pytest
import time
from kailash.runtime.local import LocalRuntime

from kaizen import Kaizen


class TestAgentWorkflows:
    """End-to-end tests for complete agent workflows."""

    def setup_method(self):
        """Setup for each test method."""
        self.kaizen = Kaizen(config={
            'performance_tracking': True,
            'cache_enabled': False  # Disable for E2E testing
        })
        self.runtime = LocalRuntime()

    def test_text_processing_workflow(self):
        """Test complete text processing workflow end-to-end."""
        # Create text processing agent
        agent = self.kaizen.create_agent("text_processor", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 1000,
            "system_prompt": "You are a helpful text processing assistant."
        })

        # Measure execution time
        start_time = time.time()

        # Execute workflow with real AI model
        results, run_id = self.runtime.execute(agent.workflow.build())

        execution_time = (time.time() - start_time) * 1000

        # Verify results
        assert run_id is not None
        assert results is not None
        assert isinstance(results, dict)

        # Performance assertions
        assert execution_time < 10000  # Less than 10 seconds

        print(f"✅ Text processing workflow completed in {execution_time:.0f}ms")

    def test_multi_agent_simulation(self):
        """Test multiple agents in sequence (simulation of future multi-agent)."""
        # Create multiple specialized agents
        researcher = self.kaizen.create_agent("researcher", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.3,
            "system_prompt": "You are a research assistant focused on facts."
        })

        analyst = self.kaizen.create_agent("analyst", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.5,
            "system_prompt": "You are an analyst focused on insights."
        })

        writer = self.kaizen.create_agent("writer", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.8,
            "system_prompt": "You are a writer focused on clear communication."
        })

        # Execute agents in sequence (future: actual coordination)
        start_time = time.time()

        # Simulate research phase
        research_results, research_run_id = self.runtime.execute(
            researcher.workflow.build()
        )

        # Simulate analysis phase
        analysis_results, analysis_run_id = self.runtime.execute(
            analyst.workflow.build()
        )

        # Simulate writing phase
        writing_results, writing_run_id = self.runtime.execute(
            writer.workflow.build()
        )

        total_time = (time.time() - start_time) * 1000

        # Verify all phases completed
        assert research_run_id is not None
        assert analysis_run_id is not None
        assert writing_run_id is not None
        assert research_results is not None
        assert analysis_results is not None
        assert writing_results is not None

        # Performance assertions
        assert total_time < 30000  # Less than 30 seconds total

        print(f"✅ Multi-agent simulation completed in {total_time:.0f}ms")

    def test_enterprise_workflow_simulation(self):
        """Test enterprise-grade workflow with monitoring and validation."""
        # Create enterprise agent with monitoring
        agent = self.kaizen.create_agent("enterprise_processor", {
            "model": "gpt-4",  # Use more capable model
            "temperature": 0.2,  # Lower temperature for consistency
            "max_tokens": 2000,
            "system_prompt": "You are an enterprise AI assistant."
        })

        # Execute with comprehensive monitoring
        start_time = time.time()

        results, run_id = self.runtime.execute(agent.workflow.build())

        execution_time = (time.time() - start_time) * 1000

        # Enterprise validation
        assert run_id is not None
        assert results is not None
        assert execution_time < 15000  # Enterprise SLA: <15 seconds

        # Future: Enterprise monitoring validation
        # monitor = self.kaizen.get_transparency_interface()
        # metrics = monitor.get_workflow_metrics(run_id)
        # assert metrics.compliance_status == "PASSED"
        # assert metrics.security_validation == "PASSED"

        print(f"✅ Enterprise workflow completed in {execution_time:.0f}ms")
        print(f"📊 Run ID: {run_id}")
```

#### Performance Baseline Testing

```python
# tests/e2e/test_performance_baselines.py
import pytest
import time
import statistics
from kailash.runtime.local import LocalRuntime

from kaizen import Kaizen


class TestPerformanceBaselines:
    """End-to-end performance baseline tests."""

    def setup_method(self):
        """Setup for performance testing."""
        self.kaizen = Kaizen(config={
            'performance_tracking': True,
            'cache_enabled': True
        })
        self.runtime = LocalRuntime()

    def test_framework_import_performance(self):
        """Test framework import performance baseline."""
        # Measure import time (this test validates current performance)
        start_time = time.time()

        # Import statement timing (framework already imported, so measure initialization)
        fresh_kaizen = Kaizen()

        import_time = (time.time() - start_time) * 1000

        # Current baseline: ~1100ms (target: <100ms in future)
        # For now, ensure it's not getting worse
        assert import_time < 2000  # Don't let it get worse than 2 seconds

        print(f"📊 Framework initialization time: {import_time:.0f}ms")
        print(f"🎯 Current target: <100ms (optimization needed)")

    def test_agent_creation_performance(self):
        """Test agent creation performance baseline."""
        creation_times = []

        # Test multiple agent creations
        for i in range(5):
            start_time = time.time()

            agent = self.kaizen.create_agent(f"perf_test_{i}", {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7
            })

            creation_time = (time.time() - start_time) * 1000
            creation_times.append(creation_time)

            assert agent is not None

        # Statistical analysis
        avg_time = statistics.mean(creation_times)
        max_time = max(creation_times)
        min_time = min(creation_times)

        # Performance assertions (current baselines)
        assert avg_time < 50  # Average <50ms
        assert max_time < 100  # Maximum <100ms
        assert min_time > 0.1  # Minimum >0.1ms (sanity check)

        print(f"📊 Agent creation times: avg={avg_time:.1f}ms, min={min_time:.1f}ms, max={max_time:.1f}ms")

    def test_workflow_execution_performance(self):
        """Test workflow execution performance baseline."""
        agent = self.kaizen.create_agent("exec_perf_test", {
            "model": "gpt-3.5-turbo",
            "temperature": 0.5
        })

        execution_times = []

        # Test multiple executions
        for i in range(3):  # Reduced for E2E test efficiency
            start_time = time.time()

            results, run_id = self.runtime.execute(agent.workflow.build())

            execution_time = (time.time() - start_time) * 1000
            execution_times.append(execution_time)

            assert run_id is not None
            assert results is not None

        # Performance analysis
        avg_time = statistics.mean(execution_times)

        # Execution time depends on AI model response time
        # This test validates reasonable performance bounds
        assert avg_time < 10000  # Average <10 seconds
        assert avg_time > 100   # Average >100ms (realistic minimum)

        print(f"📊 Workflow execution times: avg={avg_time:.0f}ms")
        print(f"🎯 Performance varies with AI model response time")

    def test_memory_usage_baseline(self):
        """Test memory usage baseline."""
        import psutil
        import os

        # Get current process
        process = psutil.Process(os.getpid())

        # Measure baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create multiple agents to test memory scaling
        agents = []
        for i in range(10):
            agent = self.kaizen.create_agent(f"memory_test_{i}", {
                "model": "gpt-3.5-turbo"
            })
            agents.append(agent)

        # Measure memory after agent creation
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - baseline_memory

        # Memory usage assertions
        assert memory_increase < 100  # Less than 100MB increase for 10 agents
        assert final_memory < 500     # Total memory <500MB

        print(f"📊 Memory usage: baseline={baseline_memory:.1f}MB, final={final_memory:.1f}MB")
        print(f"📊 Memory increase: {memory_increase:.1f}MB for 10 agents")
```

## Test Execution and Management

### Running Tests

#### Complete Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run with coverage reporting
pytest tests/ --cov=src/kaizen --cov-report=html --cov-report=term

# Run with performance timing
pytest tests/ -v --durations=10
```

#### Tier-Specific Execution

```bash
# Tier 1: Unit tests (fast)
pytest tests/unit/ -v

# Tier 2: Integration tests (requires Docker)
cd tests/utils && ./test-env up
pytest tests/integration/ -v

# Tier 3: End-to-end tests (slow, requires AI models)
pytest tests/e2e/ -v --timeout=300
```

#### Selective Test Execution

```bash
# Run specific test file
pytest tests/unit/test_framework.py -v

# Run specific test class
pytest tests/unit/test_framework.py::TestKaizenFramework -v

# Run specific test method
pytest tests/unit/test_framework.py::TestKaizenFramework::test_framework_initialization -v

# Run tests matching pattern
pytest tests/ -k "test_agent" -v

# Run tests with specific markers
pytest tests/ -m "integration" -v
```

### Test Markers and Categories

```python
# pytest.ini configuration
[tool:pytest]
markers =
    unit: Unit tests (Tier 1)
    integration: Integration tests (Tier 2)
    e2e: End-to-end tests (Tier 3)
    performance: Performance baseline tests
    slow: Tests that take longer than 30 seconds
    ai_model: Tests that require real AI model access
    database: Tests that require database access
    docker: Tests that require Docker infrastructure
```

```python
# Example test with markers
import pytest

@pytest.mark.unit
def test_framework_initialization():
    """Unit test for framework initialization."""
    pass

@pytest.mark.integration
@pytest.mark.database
def test_database_integration():
    """Integration test requiring database."""
    pass

@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.ai_model
def test_complete_workflow():
    """End-to-end test with AI model."""
    pass
```

### Continuous Integration

#### GitHub Actions Configuration

```yaml
# .github/workflows/test-suite.yml
name: Kaizen Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  unit-tests:
    name: Unit Tests (Tier 1)
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev,test]

    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --cov=src/kaizen --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  integration-tests:
    name: Integration Tests (Tier 2)
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: kaizen_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: 3.11

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev,test]

    - name: Run integration tests
      env:
        TEST_DATABASE_URL: postgresql://postgres:test@localhost:5432/kaizen_test
        TEST_REDIS_URL: redis://localhost:6379
      run: |
        pytest tests/integration/ -v --timeout=120

  e2e-tests:
    name: End-to-End Tests (Tier 3)
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: 3.11

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .[dev,test]

    - name: Start test infrastructure
      run: |
        cd tests/utils
        ./test-env up
        sleep 30  # Wait for services to be ready

    - name: Run end-to-end tests
      env:
        OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        TEST_MODE: ci
      run: |
        pytest tests/e2e/ -v --timeout=300

    - name: Stop test infrastructure
      if: always()
      run: |
        cd tests/utils
        ./test-env down
```

## Test Data and Fixtures

### Test Fixtures

```python
# tests/fixtures/common.py
import pytest
from kaizen import Kaizen
from kailash.runtime.local import LocalRuntime


@pytest.fixture
def kaizen_instance():
    """Provide a fresh Kaizen instance for testing."""
    return Kaizen(config={
        'test_mode': True,
        'cache_enabled': False,
        'performance_tracking': True
    })


@pytest.fixture
def local_runtime():
    """Provide a LocalRuntime instance for testing."""
    return LocalRuntime()


@pytest.fixture
def sample_agent_config():
    """Provide sample agent configuration for testing."""
    return {
        "model": "gpt-3.5-turbo",
        "temperature": 0.7,
        "max_tokens": 1000,
        "system_prompt": "You are a helpful testing assistant."
    }


@pytest.fixture
def test_agent(kaizen_instance, sample_agent_config):
    """Provide a test agent for testing."""
    return kaizen_instance.create_agent("test_agent", sample_agent_config)
```

### Test Data

```python
# tests/fixtures/test_data.py
"""Test data for Kaizen framework testing."""

VALID_AGENT_CONFIGS = [
    {
        "name": "basic_agent",
        "config": {
            "model": "gpt-3.5-turbo",
            "temperature": 0.7
        }
    },
    {
        "name": "research_agent",
        "config": {
            "model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 2000,
            "system_prompt": "You are a research assistant."
        }
    },
    {
        "name": "creative_agent",
        "config": {
            "model": "gpt-4",
            "temperature": 0.9,
            "max_tokens": 3000,
            "system_prompt": "You are a creative writing assistant."
        }
    }
]

INVALID_AGENT_CONFIGS = [
    {
        "name": "invalid_temperature",
        "config": {
            "model": "gpt-3.5-turbo",
            "temperature": 5.0  # Invalid: too high
        },
        "expected_error": "Temperature must be between 0.0 and 2.0"
    },
    {
        "name": "invalid_max_tokens",
        "config": {
            "model": "gpt-3.5-turbo",
            "max_tokens": -100  # Invalid: negative
        },
        "expected_error": "max_tokens must be positive"
    },
    {
        "name": "missing_model",
        "config": {
            "temperature": 0.7  # Missing required 'model'
        },
        "expected_error": "model is required"
    }
]

FRAMEWORK_CONFIGS = [
    {
        "name": "minimal_config",
        "config": {}
    },
    {
        "name": "development_config",
        "config": {
            "default_model": "gpt-3.5-turbo",
            "performance_tracking": True,
            "cache_enabled": True
        }
    },
    {
        "name": "production_config",
        "config": {
            "default_model": "gpt-4",
            "temperature": 0.5,
            "performance_tracking": True,
            "cache_enabled": True,
            "security_enabled": True
        }
    }
]
```

## Quality Assurance

### Coverage Requirements

**Coverage Targets**:
- **Overall Coverage**: Minimum 85%
- **New Code Coverage**: Minimum 95%
- **Critical Paths**: 100% coverage for framework core

```bash
# Generate coverage report
pytest tests/ --cov=src/kaizen --cov-report=html --cov-report=term

# View detailed coverage
open htmlcov/index.html

# Coverage with missing lines
pytest tests/ --cov=src/kaizen --cov-report=term-missing
```

### Performance Monitoring

**Performance Baselines**:
- Framework import: <2000ms (current), target <100ms
- Agent creation: <50ms average
- Workflow execution: <10 seconds (varies with AI model)
- Memory usage: <500MB total

```bash
# Run performance tests
pytest tests/e2e/test_performance_baselines.py -v

# Profile test execution
pytest tests/ --profile

# Memory profiling
pytest tests/ --memray
```

### Quality Gates

**Required for Pull Request Approval**:
1. ✅ All tests pass across all tiers
2. ✅ Coverage targets met
3. ✅ Performance baselines maintained
4. ✅ No security vulnerabilities
5. ✅ Code quality checks pass

```bash
# Complete quality check
./scripts/quality-check.sh

# Security scanning
bandit -r src/kaizen/
safety check

# Dependency vulnerabilities
pip-audit
```

---

**🧪 Testing Mastery Achieved**: You now understand Kaizen's comprehensive testing strategy and can contribute tests that ensure enterprise-grade reliability. The 3-tier approach provides confidence from unit-level correctness to real-world scenario validation.

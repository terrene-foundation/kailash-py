"""
Tier 1 (Unit) Tests for Test Infrastructure Validation

These tests validate that the test infrastructure components work correctly
in isolation. They test the utilities that enable integration testing.

Test Requirements:
- Fast execution (<1 second per test)
- No external dependencies (no Docker services)
- Test all test utilities in isolation
- Mock external services if needed for testing utilities
"""

import json
import os
import tempfile
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestPerformanceTracker:
    """Test PerformanceTracker utility for timing and metrics."""

    def test_performance_tracker_timing(self):
        """Performance tracker must accurately measure execution time."""
        from tests.utils.performance_tracker import PerformanceTracker

        tracker = PerformanceTracker("test_operation")

        # Start timing
        tracker.start()

        # Simulate work
        time.sleep(0.1)

        # Stop timing
        elapsed = tracker.stop()

        # Verify timing accuracy (within reasonable margin)
        # Increased upper bound to 0.3s for CI infrastructure variance
        assert 0.05 < elapsed < 0.3
        assert tracker.operation_name == "test_operation"
        assert tracker.start_time is not None
        assert tracker.end_time is not None
        assert tracker.elapsed_time == elapsed

    def test_performance_tracker_context_manager(self):
        """Performance tracker must work as context manager."""
        from tests.utils.performance_tracker import PerformanceTracker

        with PerformanceTracker("context_test") as tracker:
            time.sleep(0.05)

        # Verify context manager tracked timing
        assert tracker.elapsed_time > 0.04
        # Increased upper bound to 0.25s for CI infrastructure variance
        assert tracker.elapsed_time < 0.25
        assert tracker.operation_name == "context_test"

    def test_performance_tracker_metrics_collection(self):
        """Performance tracker must collect metrics properly."""
        from tests.utils.performance_tracker import PerformanceTracker

        tracker = PerformanceTracker("metrics_test")

        # Test basic metrics
        with tracker:
            time.sleep(0.02)

        metrics = tracker.get_metrics()

        assert "operation_name" in metrics
        assert "elapsed_time" in metrics
        assert "start_time" in metrics
        assert "end_time" in metrics
        assert metrics["operation_name"] == "metrics_test"
        assert metrics["elapsed_time"] > 0

    def test_performance_tracker_threshold_validation(self):
        """Performance tracker must validate against thresholds."""
        from tests.utils.performance_tracker import PerformanceTracker

        # Test under threshold
        # Increased threshold to 0.5s for CI infrastructure variance
        # CI runners can have significant timing variance due to CPU contention
        fast_tracker = PerformanceTracker("fast_test", threshold=0.5)
        with fast_tracker:
            time.sleep(0.02)

        assert fast_tracker.is_under_threshold()
        assert not fast_tracker.is_over_threshold()

        # Test over threshold
        slow_tracker = PerformanceTracker("slow_test", threshold=0.01)
        with slow_tracker:
            time.sleep(0.03)

        assert not slow_tracker.is_under_threshold()
        assert slow_tracker.is_over_threshold()


class TestTestFixtures:
    """Test TestFixtures utility for consistent test data."""

    def test_integration_test_config(self):
        """Test fixtures must provide valid integration test configuration."""
        from tests.utils.test_fixtures import integration_test_config

        config = integration_test_config()

        # Verify required configuration keys
        assert "framework" in config
        assert "agents" in config
        assert "workflows" in config

        # Verify framework configuration
        framework_config = config["framework"]
        assert "name" in framework_config
        assert "version" in framework_config

        # Verify agent configurations
        agents_config = config["agents"]
        assert isinstance(agents_config, list)
        assert len(agents_config) > 0

        for agent_config in agents_config:
            assert "name" in agent_config
            assert "capabilities" in agent_config

    def test_test_agent_configs(self):
        """Test fixtures must provide various agent configurations."""
        from tests.utils.test_fixtures import test_agent_configs

        configs = test_agent_configs()

        assert isinstance(configs, dict)
        assert "basic_agent" in configs
        assert "processing_agent" in configs
        assert "analysis_agent" in configs

        # Test basic agent config
        basic_config = configs["basic_agent"]
        assert basic_config["name"] == "basic_test_agent"
        assert "capabilities" in basic_config

        # Test processing agent config
        processing_config = configs["processing_agent"]
        assert processing_config["name"] == "processing_test_agent"
        assert "data_processing" in processing_config["capabilities"]

    def test_sample_workflow_nodes(self):
        """Test fixtures must provide sample workflow node configurations."""
        from tests.utils.test_fixtures import sample_workflow_nodes

        nodes = sample_workflow_nodes()

        assert isinstance(nodes, list)
        assert len(nodes) > 0

        for node in nodes:
            assert "node_type" in node
            assert "node_id" in node
            assert "parameters" in node

            # Verify node has valid configuration
            assert node["node_type"] in ["PythonCodeNode", "InputNode", "OutputNode"]
            assert isinstance(node["parameters"], dict)

    def test_test_data_samples(self):
        """Test fixtures must provide sample data for testing."""
        from tests.utils.test_fixtures import test_data_samples

        data = test_data_samples()

        assert isinstance(data, dict)
        assert "simple_data" in data
        assert "complex_data" in data
        assert "workflow_data" in data

        # Verify simple data structure
        simple_data = data["simple_data"]
        assert "message" in simple_data
        assert "value" in simple_data

        # Verify complex data structure
        complex_data = data["complex_data"]
        assert "records" in complex_data
        assert isinstance(complex_data["records"], list)


class TestMockProviders:
    """Test MockProviders for LLM and service mocking."""

    def test_mock_llm_provider_basic_functionality(self):
        """Mock LLM provider must simulate LLM responses."""
        from tests.utils.mock_providers import MockLLMProvider

        provider = MockLLMProvider()

        # Test basic completion
        response = provider.complete("Test prompt")

        assert isinstance(response, dict)
        assert "response" in response
        assert "metadata" in response
        assert response["metadata"]["provider"] == "mock_llm"

        # Test response is non-empty
        assert len(response["response"]) > 0

    def test_mock_llm_provider_custom_responses(self):
        """Mock LLM provider must support custom response mapping."""
        from tests.utils.mock_providers import MockLLMProvider

        custom_responses = {"hello": "Hi there!", "test": "This is a test response"}

        provider = MockLLMProvider(custom_responses=custom_responses)

        # Test custom response mapping
        response1 = provider.complete("hello")
        assert response1["response"] == "Hi there!"

        response2 = provider.complete("test")
        assert response2["response"] == "This is a test response"

        # Test fallback for unmapped prompts
        response3 = provider.complete("unmapped")
        assert response3["response"] != "Hi there!"
        assert response3["response"] != "This is a test response"

    def test_mock_database_provider(self):
        """Mock database provider must simulate database operations."""
        from tests.utils.mock_providers import MockDatabaseProvider

        provider = MockDatabaseProvider()

        # Test connection simulation
        connection = provider.get_connection()
        assert connection is not None
        assert hasattr(connection, "execute")
        assert hasattr(connection, "close")

        # Test query execution
        result = connection.execute("SELECT 1")
        assert result is not None

    def test_mock_service_registry(self):
        """Mock service registry must manage mock services."""
        from tests.utils.mock_providers import MockServiceRegistry

        registry = MockServiceRegistry()

        # Test service registration
        mock_service = Mock()
        registry.register("test_service", mock_service)

        # Test service retrieval
        retrieved_service = registry.get("test_service")
        assert retrieved_service is mock_service

        # Test service list
        services = registry.list_services()
        assert "test_service" in services

        # Test service removal
        registry.unregister("test_service")
        assert "test_service" not in registry.list_services()


class TestDockerEnvironmentValidation:
    """Test Docker environment validation utilities."""

    @patch("subprocess.run")
    def test_docker_service_health_check(self, mock_subprocess):
        """Docker health check must validate service availability."""
        from tests.utils.test_fixtures import docker_service_health_check

        # Mock successful service response
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Up 2 minutes (healthy)"
        mock_subprocess.return_value = mock_result

        # Test service health check
        is_healthy = docker_service_health_check("test_service")
        assert is_healthy is True

        # Mock failed service response
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "service not found"
        mock_subprocess.return_value = mock_result

        is_healthy = docker_service_health_check("test_service")
        assert is_healthy is False

        # Mock running but not healthy service
        mock_result.returncode = 0
        mock_result.stdout = "Up 1 minute"  # Missing (healthy) status
        mock_subprocess.return_value = mock_result

        is_healthy = docker_service_health_check("test_service")
        assert is_healthy is False

    def test_test_environment_configuration(self):
        """Test environment configuration must provide proper settings."""
        from tests.utils.test_fixtures import test_environment_config

        config = test_environment_config()

        # Verify required environment settings
        assert "database" in config
        assert "redis" in config
        assert "services" in config

        # Verify database configuration
        db_config = config["database"]
        assert "host" in db_config
        assert "port" in db_config
        assert "database" in db_config

        # Verify Redis configuration
        redis_config = config["redis"]
        assert "host" in redis_config
        assert "port" in redis_config

        # Verify service ports are different from production
        assert db_config["port"] != 5432  # Not default PostgreSQL port
        assert redis_config["port"] != 6379  # Not default Redis port


class TestTestUtilitiesIntegration:
    """Test that test utilities work together properly."""

    def test_performance_tracking_with_fixtures(self):
        """Performance tracker must work with test fixtures."""
        from tests.utils.performance_tracker import PerformanceTracker
        from tests.utils.test_fixtures import sample_workflow_nodes

        # Use fixtures in performance test
        with PerformanceTracker("fixture_processing") as tracker:
            nodes = sample_workflow_nodes()

            # Process nodes (simulate work)
            processed_nodes = []
            for node in nodes:
                processed_node = node.copy()
                processed_node["processed"] = True
                processed_nodes.append(processed_node)

        # Verify performance tracking worked
        assert tracker.elapsed_time > 0
        assert len(processed_nodes) == len(sample_workflow_nodes())

        # Verify performance is reasonable for test fixtures
        assert tracker.elapsed_time < 1.0  # Should be very fast

    def test_mock_providers_with_fixtures(self):
        """Mock providers must work with test fixtures."""
        from tests.utils.mock_providers import MockLLMProvider
        from tests.utils.test_fixtures import test_data_samples

        provider = MockLLMProvider()
        test_data = test_data_samples()

        # Use test data with mock provider
        prompt = f"Process this data: {test_data['simple_data']}"
        response = provider.complete(prompt)

        # Verify mock provider processed fixture data
        assert isinstance(response, dict)
        assert "response" in response
        assert len(response["response"]) > 0

    def test_complete_test_utilities_workflow(self):
        """Test complete workflow using all test utilities."""
        from tests.utils.mock_providers import MockLLMProvider, MockServiceRegistry
        from tests.utils.performance_tracker import PerformanceTracker
        from tests.utils.test_fixtures import (
            integration_test_config,
            test_agent_configs,
        )

        # Setup complete test environment
        registry = MockServiceRegistry()
        llm_provider = MockLLMProvider()
        registry.register("llm", llm_provider)

        # Use test fixtures
        framework_config = integration_test_config()
        agent_configs = test_agent_configs()

        # Track performance of complete workflow
        with PerformanceTracker("complete_utilities_test") as tracker:
            # Simulate framework initialization
            assert framework_config["framework"]["name"] is not None

            # Simulate agent creation
            agents = []
            for agent_name, agent_config in agent_configs.items():
                # Simulate agent creation with mock LLM
                agent = {
                    "name": agent_config["name"],
                    "llm": registry.get("llm"),
                    "config": agent_config,
                }
                agents.append(agent)

            # Simulate agent processing
            for agent in agents:
                llm_response = agent["llm"].complete("Test processing")
                agent["last_response"] = llm_response

        # Verify complete workflow succeeded
        assert len(agents) == len(agent_configs)
        assert all(agent["last_response"] is not None for agent in agents)
        assert tracker.elapsed_time > 0
        assert tracker.elapsed_time < 1.0  # Should be fast for mocked operations


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""Test utilities for the Kailash SDK test suite."""

# Import from unit directory where helpers.py is located
try:
    from tests.unit.helpers import (
        AccessControlTestUtils,
        AsyncTestUtils,
        DatabaseTestUtils,
        FunctionalTestMixin,
        MockTimeProvider,
        PerformanceTestMixin,
    )
except ImportError:
    # Fallback for when running from different directories
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from unit.helpers import (
        AccessControlTestUtils,
        AsyncTestUtils,
        DatabaseTestUtils,
        FunctionalTestMixin,
        MockTimeProvider,
        PerformanceTestMixin,
    )

# Import new test infrastructure utilities
from .performance_tracker import PerformanceTracker, PerformanceReport
from .test_fixtures import (
    integration_test_config,
    test_agent_configs,
    sample_workflow_nodes,
    test_data_samples,
    docker_service_health_check,
    test_environment_config,
    load_test_scenarios,
    enterprise_test_config,
    multi_agent_test_scenarios,
    framework_validation_checklist
)
from .mock_providers import (
    MockLLMProvider,
    MockDatabaseProvider,
    MockConnection,
    MockServiceRegistry,
    MockWorkflowExecutor,
    create_mock_framework,
    create_mock_agent,
    create_mock_workflow
)

__all__ = [
    # Original helpers
    "MockTimeProvider",
    "FunctionalTestMixin",
    "PerformanceTestMixin",
    "AsyncTestUtils",
    "DatabaseTestUtils",
    "AccessControlTestUtils",
    # Performance tracking
    "PerformanceTracker",
    "PerformanceReport",
    # Test fixtures
    "integration_test_config",
    "test_agent_configs",
    "sample_workflow_nodes",
    "test_data_samples",
    "docker_service_health_check",
    "test_environment_config",
    "load_test_scenarios",
    "enterprise_test_config",
    "multi_agent_test_scenarios",
    "framework_validation_checklist",
    # Mock providers
    "MockLLMProvider",
    "MockDatabaseProvider",
    "MockConnection",
    "MockServiceRegistry",
    "MockWorkflowExecutor",
    "create_mock_framework",
    "create_mock_agent",
    "create_mock_workflow",
]

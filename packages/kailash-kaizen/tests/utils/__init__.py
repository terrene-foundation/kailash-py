"""
Test utilities for Kaizen framework integration test infrastructure.

Provides comprehensive utilities for 3-tier testing strategy:
- Tier 1 (Unit): Mock providers for isolated testing
- Tier 2 (Integration): Real Core SDK services without mocking
- Tier 3 (E2E): Complete workflows with real infrastructure

Key Components:
- docker_config: Docker services management for enterprise testing
- performance_tracker: Performance measurement utilities
- test_fixtures: Test configurations and data fixtures
- integration_helpers: Integration test helper functions
- mock_providers: Mock providers for unit tests only

Based on Kailash Core SDK test infrastructure patterns.
"""

from .docker_config import DockerServicesManager, ensure_docker_services
from .integration_helpers import (
    IntegrationTestSuite,
    setup_test_environment,
    validate_workflow_execution,
)
from .mock_providers import MockLLMProvider, MockMemoryProvider
from .performance_tracker import PerformanceTracker, performance_tracker
from .test_fixtures import (
    KaizenTestDataManager,
    enterprise_test_config,
    integration_test_data,
    mock_llm_responses,
)

__all__ = [
    # Docker infrastructure
    "ensure_docker_services",
    "DockerServicesManager",
    # Performance testing
    "PerformanceTracker",
    "performance_tracker",
    # Test fixtures
    "KaizenTestDataManager",
    "enterprise_test_config",
    "integration_test_data",
    "mock_llm_responses",
    # Integration helpers
    "IntegrationTestSuite",
    "validate_workflow_execution",
    "setup_test_environment",
    # Mock providers (unit tests only)
    "MockLLMProvider",
    "MockMemoryProvider",
]

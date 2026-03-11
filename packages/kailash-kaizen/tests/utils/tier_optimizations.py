"""
Tier-Specific Test Optimizations for Kaizen Framework

This module provides tier-specific configurations, utilities, and optimizations
to ensure each test tier meets its performance and reliability requirements.

Tier Requirements:
- Tier 1 (Unit): <1s, isolated, mocking allowed
- Tier 2 (Integration): <5s, real services, NO MOCKING
- Tier 3 (E2E): <10s, complete workflows, NO MOCKING
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

import psutil
import pytest

try:
    import sys

    sys.path.append("./repos/projects/kailash_python_sdk/tests/utils")
    from docker_config import (
        is_ollama_available,
        is_postgres_available,
        is_redis_available,
    )

    INFRASTRUCTURE_AVAILABLE = True
except ImportError:
    INFRASTRUCTURE_AVAILABLE = False


class TestTier(Enum):
    """Test tier enumeration with performance requirements."""

    UNIT = ("unit", 1000, True)  # 1s limit, mocking allowed
    INTEGRATION = ("integration", 5000, False)  # 5s limit, no mocking
    E2E = ("e2e", 10000, False)  # 10s limit, no mocking

    def __init__(self, name: str, timeout_ms: int, mocking_allowed: bool):
        self.tier_name = name
        self.timeout_ms = timeout_ms
        self.mocking_allowed = mocking_allowed


@dataclass
class TierConfig:
    """Configuration for a specific test tier."""

    tier: TestTier
    max_memory_mb: int
    enable_profiling: bool
    required_services: List[str]
    optional_services: List[str]
    performance_thresholds: Dict[str, float]


class TierOptimizer:
    """Optimizes test configurations and execution for specific tiers."""

    def __init__(self):
        self.tier_configs = {
            TestTier.UNIT: TierConfig(
                tier=TestTier.UNIT,
                max_memory_mb=50,
                enable_profiling=True,
                required_services=[],
                optional_services=[],
                performance_thresholds={
                    "framework_init_ms": 50,
                    "agent_creation_ms": 25,
                    "signature_creation_ms": 5,
                    "workflow_build_ms": 50,
                },
            ),
            TestTier.INTEGRATION: TierConfig(
                tier=TestTier.INTEGRATION,
                max_memory_mb=200,
                enable_profiling=True,
                required_services=["postgres", "redis"],
                optional_services=["mysql", "ollama"],
                performance_thresholds={
                    "framework_init_ms": 100,
                    "agent_creation_ms": 100,
                    "database_connection_ms": 500,
                    "workflow_execution_ms": 3000,
                },
            ),
            TestTier.E2E: TierConfig(
                tier=TestTier.E2E,
                max_memory_mb=500,
                enable_profiling=True,
                required_services=["postgres", "redis"],
                optional_services=["mysql", "ollama"],
                performance_thresholds={
                    "framework_init_ms": 200,
                    "complete_workflow_ms": 8000,
                    "multi_agent_coordination_ms": 5000,
                    "audit_trail_generation_ms": 1000,
                },
            ),
        }

    def get_tier_config(self, tier: TestTier) -> TierConfig:
        """Get configuration for a specific tier."""
        return self.tier_configs[tier]

    def optimize_for_tier(self, tier: TestTier) -> Dict[str, Any]:
        """Generate optimized configuration for a tier."""
        config = self.get_tier_config(tier)

        optimization = {
            "tier": tier.tier_name,
            "timeout_ms": tier.timeout_ms,
            "mocking_allowed": tier.mocking_allowed,
            "max_memory_mb": config.max_memory_mb,
            "enable_profiling": config.enable_profiling,
            "performance_thresholds": config.performance_thresholds,
            "kaizen_config": self._get_kaizen_config(tier),
            "pytest_markers": self._get_pytest_markers(tier),
        }

        return optimization

    def _get_kaizen_config(self, tier: TestTier) -> Dict[str, Any]:
        """Get Kaizen configuration optimized for tier."""
        base_config = {"debug": True, "signature_validation": True}

        tier_specific = {
            TestTier.UNIT: {
                "memory_enabled": False,
                "optimization_enabled": False,
                "monitoring_enabled": False,
                "cache_enabled": False,
                "startup_timeout_seconds": 1,
                "max_concurrent_operations": 1,
                "lazy_loading": True,
            },
            TestTier.INTEGRATION: {
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": True,
                "cache_enabled": True,
                "startup_timeout_seconds": 5,
                "max_concurrent_operations": 3,
                "retry_attempts": 2,
            },
            TestTier.E2E: {
                "memory_enabled": True,
                "optimization_enabled": True,
                "monitoring_enabled": True,
                "cache_enabled": True,
                "audit_trail_enabled": True,
                "compliance_mode": "enterprise",
                "multi_agent_enabled": True,
                "startup_timeout_seconds": 10,
                "max_concurrent_operations": 5,
                "retry_attempts": 3,
            },
        }

        base_config.update(tier_specific[tier])
        return base_config

    def _get_pytest_markers(self, tier: TestTier) -> List[str]:
        """Get appropriate pytest markers for tier."""
        markers = [tier.tier_name]

        if tier == TestTier.UNIT:
            markers.extend(["fast", "isolated"])
        elif tier == TestTier.INTEGRATION:
            markers.extend(["requires_docker", "requires_postgres", "requires_redis"])
        elif tier == TestTier.E2E:
            markers.extend(
                ["requires_docker", "requires_postgres", "requires_redis", "slow"]
            )

        return markers


class TierPerformanceMonitor:
    """Monitors and enforces tier-specific performance requirements."""

    def __init__(self, tier: TestTier):
        self.tier = tier
        self.measurements = {}
        self.optimizer = TierOptimizer()
        self.thresholds = self.optimizer.get_tier_config(tier).performance_thresholds

    @contextmanager
    def measure_operation(self, operation: str):
        """Context manager to measure operation performance."""
        start_time = time.perf_counter()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        try:
            yield
        finally:
            end_time = time.perf_counter()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

            duration_ms = (end_time - start_time) * 1000
            memory_increase_mb = end_memory - start_memory

            self.measurements[operation] = {
                "duration_ms": duration_ms,
                "memory_increase_mb": memory_increase_mb,
                "timestamp": time.time(),
                "tier": self.tier.tier_name,
            }

    def assert_performance(self, operation: str):
        """Assert that operation meets tier performance requirements."""
        if operation not in self.measurements:
            raise ValueError(f"No measurement found for operation: {operation}")

        measurement = self.measurements[operation]
        duration_ms = measurement["duration_ms"]

        # Check against tier timeout
        assert duration_ms <= self.tier.timeout_ms, (
            f"Tier {self.tier.tier_name} operation '{operation}' took {duration_ms:.2f}ms, "
            f"exceeding tier limit of {self.tier.timeout_ms}ms"
        )

        # Check against specific operation threshold if available
        if operation in self.thresholds:
            threshold = self.thresholds[operation]
            assert duration_ms <= threshold, (
                f"Operation '{operation}' took {duration_ms:.2f}ms, "
                f"exceeding specific threshold of {threshold}ms"
            )

    def get_tier_report(self) -> Dict[str, Any]:
        """Generate performance report for this tier."""
        total_operations = len(self.measurements)
        if total_operations == 0:
            return {"tier": self.tier.tier_name, "operations": 0}

        total_time = sum(m["duration_ms"] for m in self.measurements.values())
        avg_time = total_time / total_operations
        max_time = max(m["duration_ms"] for m in self.measurements.values())

        violations = []
        for op, measurement in self.measurements.items():
            if measurement["duration_ms"] > self.tier.timeout_ms:
                violations.append(
                    {
                        "operation": op,
                        "duration_ms": measurement["duration_ms"],
                        "limit_ms": self.tier.timeout_ms,
                    }
                )

        return {
            "tier": self.tier.tier_name,
            "operations": total_operations,
            "total_time_ms": total_time,
            "average_time_ms": avg_time,
            "max_time_ms": max_time,
            "violations": violations,
            "within_tier_limits": len(violations) == 0,
        }


class TierServiceValidator:
    """Validates service availability for specific test tiers."""

    def __init__(self):
        self.optimizer = TierOptimizer()

    def validate_tier_requirements(self, tier: TestTier):
        """Validate that required services are available for tier."""
        if not INFRASTRUCTURE_AVAILABLE:
            if tier != TestTier.UNIT:
                pytest.skip("Infrastructure configuration not available")
            return

        config = self.optimizer.get_tier_config(tier)

        # Check required services
        for service in config.required_services:
            if not self._is_service_available(service):
                pytest.skip(
                    f"Required service '{service}' not available for {tier.tier_name} tests"
                )

        # Warn about optional services
        missing_optional = []
        for service in config.optional_services:
            if not self._is_service_available(service):
                missing_optional.append(service)

        if missing_optional:
            import warnings

            warnings.warn(
                f"Optional services not available: {missing_optional}. "
                f"Some {tier.tier_name} tests may be skipped."
            )

    def _is_service_available(self, service: str) -> bool:
        """Check if a specific service is available."""
        service_checkers = {
            "postgres": is_postgres_available,
            "redis": is_redis_available,
            "ollama": is_ollama_available,
        }

        checker = service_checkers.get(service)
        if checker:
            return checker()
        return False


# ============================================================================
# PYTEST FIXTURES AND DECORATORS
# ============================================================================


@pytest.fixture
def tier_optimizer():
    """Pytest fixture for tier optimizer."""
    return TierOptimizer()


@pytest.fixture
def tier_performance_monitor(request):
    """Pytest fixture for tier performance monitoring."""
    # Determine tier from test markers or path
    tier = TestTier.UNIT  # Default

    if hasattr(request, "node"):
        if "integration" in str(request.node.fspath):
            tier = TestTier.INTEGRATION
        elif "e2e" in str(request.node.fspath):
            tier = TestTier.E2E

        # Check markers
        for marker in request.node.iter_markers():
            if marker.name == "integration":
                tier = TestTier.INTEGRATION
            elif marker.name == "e2e":
                tier = TestTier.E2E

    return TierPerformanceMonitor(tier)


@pytest.fixture
def tier_service_validator():
    """Pytest fixture for service validation."""
    return TierServiceValidator()


def tier_optimized(tier: TestTier):
    """Decorator to optimize test for specific tier."""

    def decorator(func):
        # Add tier marker
        func = pytest.mark.__getattr__(tier.tier_name)(func)

        # Add timeout
        func = pytest.mark.timeout(tier.timeout_ms / 1000)(func)

        # Add service requirements
        optimizer = TierOptimizer()
        config = optimizer.get_tier_config(tier)

        for service in config.required_services:
            if service == "postgres":
                func = pytest.mark.requires_postgres(func)
            elif service == "redis":
                func = pytest.mark.requires_redis(func)
            elif service == "docker":
                func = pytest.mark.requires_docker(func)

        return func

    return decorator


def unit_test(func):
    """Decorator for unit tests with tier optimizations."""
    return tier_optimized(TestTier.UNIT)(func)


def integration_test(func):
    """Decorator for integration tests with tier optimizations."""
    return tier_optimized(TestTier.INTEGRATION)(func)


def e2e_test(func):
    """Decorator for E2E tests with tier optimizations."""
    return tier_optimized(TestTier.E2E)(func)


# ============================================================================
# PERFORMANCE ASSERTION HELPERS
# ============================================================================


def assert_unit_performance(duration_ms: float, operation: str = "operation"):
    """Assert operation meets unit test performance requirements."""
    assert duration_ms <= TestTier.UNIT.timeout_ms, (
        f"Unit test {operation} took {duration_ms:.2f}ms, "
        f"exceeding unit test limit of {TestTier.UNIT.timeout_ms}ms"
    )


def assert_integration_performance(duration_ms: float, operation: str = "operation"):
    """Assert operation meets integration test performance requirements."""
    assert duration_ms <= TestTier.INTEGRATION.timeout_ms, (
        f"Integration test {operation} took {duration_ms:.2f}ms, "
        f"exceeding integration test limit of {TestTier.INTEGRATION.timeout_ms}ms"
    )


def assert_e2e_performance(duration_ms: float, operation: str = "operation"):
    """Assert operation meets E2E test performance requirements."""
    assert duration_ms <= TestTier.E2E.timeout_ms, (
        f"E2E test {operation} took {duration_ms:.2f}ms, "
        f"exceeding E2E test limit of {TestTier.E2E.timeout_ms}ms"
    )


# Export main classes and functions
__all__ = [
    "TestTier",
    "TierConfig",
    "TierOptimizer",
    "TierPerformanceMonitor",
    "TierServiceValidator",
    "tier_optimized",
    "unit_test",
    "integration_test",
    "e2e_test",
    "assert_unit_performance",
    "assert_integration_performance",
    "assert_e2e_performance",
]

"""Test utilities for improved test architecture.

This module provides utilities for separating functional tests from
performance tests, with reliable timing and mocking capabilities.
"""

import asyncio
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, patch


class MockTimeProvider:
    """Mock time provider for predictable timing tests."""

    def __init__(self, start_time: float = 1000.0, time_step: float = 0.1):
        """Initialize mock time provider.

        Args:
            start_time: Starting timestamp
            time_step: Time increment for each call
        """
        self.current_time = start_time
        self.time_step = time_step
        self.call_count = 0

    def get_time(self) -> float:
        """Get current mock time."""
        current = self.current_time + (self.call_count * self.time_step)
        self.call_count += 1
        return current

    def reset(self, start_time: Optional[float] = None) -> None:
        """Reset the time provider."""
        if start_time is not None:
            self.current_time = start_time
        self.call_count = 0

    def advance(self, seconds: float) -> None:
        """Advance time by specified seconds."""
        self.current_time += seconds


class FunctionalTestMixin:
    """Mixin for functional tests that don't depend on timing."""

    def assert_functionality_only(self, result: Any, expected: Any) -> None:
        """Assert functional correctness without timing dependencies."""
        # Override in test classes for specific functionality checks
        assert result == expected

    def create_minimal_context(self, **overrides) -> Dict[str, Any]:
        """Create minimal test context with sensible defaults."""
        defaults = {
            "timeout": 1.0,  # Short but reasonable
            "retry_count": 0,  # No retries for faster tests
            "debug_mode": True,
        }
        defaults.update(overrides)
        return defaults


class PerformanceTestMixin:
    """Mixin for performance tests with controlled timing."""

    @property
    def mock_time(self):
        """Get or create mock time provider."""
        if not hasattr(self, "_mock_time"):
            self._mock_time = MockTimeProvider()
        return self._mock_time

    @contextmanager
    def controlled_time(self, duration: float = 0.1):
        """Context manager for controlled timing tests."""
        with patch("time.time", self.mock_time.get_time):
            self.mock_time.reset()
            # Set up time to show the expected duration
            original_call_count = self.mock_time.call_count
            yield
            # Ensure we've advanced time appropriately
            if self.mock_time.call_count == original_call_count:
                # Force time advancement if no calls were made
                self.mock_time.advance(duration)

    def assert_timing_within_range(
        self, actual_duration: float, expected_duration: float, tolerance: float = 0.05
    ) -> None:
        """Assert timing is within acceptable range."""
        min_duration = expected_duration - tolerance
        max_duration = expected_duration + tolerance
        assert (
            min_duration <= actual_duration <= max_duration
        ), f"Duration {actual_duration} not in range [{min_duration}, {max_duration}]"

    def assert_timing_positive(self, duration: float) -> None:
        """Assert timing is positive (for fast systems)."""
        assert duration >= 0.0, f"Duration should be non-negative, got {duration}"


class AsyncTestUtils:
    """Utilities for async testing."""

    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """Run coroutine with timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Async operation timed out after {timeout}s")

    @staticmethod
    async def mock_async_sleep(duration: float) -> None:
        """Mock async sleep that doesn't actually wait."""
        # For fast tests, we can simulate sleep without waiting
        pass

    @staticmethod
    def create_mock_async_context_manager(return_value: Any = None):
        """Create a mock async context manager."""

        class MockAsyncContextManager:
            def __init__(self, return_value=None):
                self.return_value = return_value or MagicMock()

            async def __aenter__(self):
                return self.return_value

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        return MockAsyncContextManager(return_value)


class DatabaseTestUtils:
    """Utilities for database testing."""

    @staticmethod
    def create_mock_query_result(
        data: List[Dict[str, Any]], columns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a mock database query result."""
        if not columns and data:
            columns = list(data[0].keys()) if data else []

        return {
            "data": data,
            "row_count": len(data),
            "columns": columns or [],
            "execution_time": 0.001,  # Fast but realistic
        }

    @staticmethod
    def create_mock_connection(query_results: Optional[List[Any]] = None):
        """Create a mock database connection."""
        mock_connection = MagicMock()

        if query_results:
            # Set up mock to return results in sequence
            mock_connection.execute.side_effect = query_results
        else:
            # Default empty result
            mock_connection.execute.return_value = []

        return mock_connection

    @staticmethod
    def create_test_user_context(
        user_id: str = "test_user",
        roles: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Create a test user context."""
        from kailash.access_control import UserContext

        return UserContext(
            user_id=user_id,
            tenant_id="test_tenant",
            email=f"{user_id}@test.com",
            roles=roles or ["test_role"],
            attributes=attributes or {},
        )


class AccessControlTestUtils:
    """Utilities for access control testing."""

    @staticmethod
    def create_test_permission_rule(
        rule_id: str,
        resource_type: str = "node",
        resource_id: str = "test_resource",
        permission: str = "execute",
        effect: str = "allow",
        **kwargs,
    ):
        """Create a test permission rule."""
        from kailash.access_control import (
            NodePermission,
            PermissionEffect,
            PermissionRule,
        )

        # Convert string values to enums
        effect_enum = (
            PermissionEffect.ALLOW if effect == "allow" else PermissionEffect.DENY
        )

        if resource_type == "node":
            permission_enum = getattr(NodePermission, permission.upper())
        else:
            from kailash.access_control import WorkflowPermission

            permission_enum = getattr(WorkflowPermission, permission.upper())

        return PermissionRule(
            id=rule_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission=permission_enum,
            effect=effect_enum,
            **kwargs,
        )

    @staticmethod
    def create_rbac_test_scenario():
        """Create a standard RBAC test scenario."""
        from kailash.access_control.managers import ComposableAccessControlManager

        manager = ComposableAccessControlManager(strategy="rbac")

        # Add some standard rules
        manager.add_rule(
            AccessControlTestUtils.create_test_permission_rule(
                "admin_all_access", effect="allow", role="admin"
            )
        )

        manager.add_rule(
            AccessControlTestUtils.create_test_permission_rule(
                "user_read_only", permission="read_output", effect="allow", role="user"
            )
        )

        return manager

    @staticmethod
    def create_abac_test_scenario():
        """Create a standard ABAC test scenario."""
        from kailash.access_control.managers import ComposableAccessControlManager

        manager = ComposableAccessControlManager(strategy="abac")

        # Add ABAC rule with conditions
        manager.add_rule(
            AccessControlTestUtils.create_test_permission_rule(
                "finance_department_access",
                effect="allow",
                conditions={
                    "type": "attribute_expression",
                    "value": {
                        "operator": "and",
                        "conditions": [
                            {
                                "attribute_path": "user.attributes.department",
                                "operator": "equals",
                                "value": "Finance",
                            }
                        ],
                    },
                },
            )
        )

        return manager


# Export utilities
__all__ = [
    "MockTimeProvider",
    "FunctionalTestMixin",
    "PerformanceTestMixin",
    "AsyncTestUtils",
    "DatabaseTestUtils",
    "AccessControlTestUtils",
]

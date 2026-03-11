"""Mock helpers for DataFlow testing.

This module contains mock classes for testing purposes.
These were moved from production code to test utilities in v0.7.0.
"""

import warnings
from typing import Any, Dict


class MockConnectionPool:
    """Mock connection pool for testing purposes.

    This class provides a mock implementation of a database connection pool
    for use in tests. It returns realistic-looking metrics without requiring
    an actual database connection.

    Warning:
        This is a test utility and should not be used in production code.
        If called from production code, a deprecation warning will be issued.
    """

    def __init__(self, connection_manager):
        """Initialize mock connection pool.

        Args:
            connection_manager: The ConnectionManager instance (or mock thereof)
        """
        self.connection_manager = connection_manager
        self.max_connections = getattr(connection_manager, "_connection_stats", {}).get(
            "pool_size", 10
        )

        # Check if being used from production code
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_file = frame.f_back.f_code.co_filename
            if "tests" not in caller_file:
                warnings.warn(
                    "MockConnectionPool is a test utility and should not be used "
                    "in production code. Please use real connection pooling instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )

    async def get_metrics(self) -> Dict[str, Any]:
        """Get connection pool metrics.

        Returns:
            Dictionary containing mock connection pool metrics
        """
        return {
            "connections_created": 1,
            "connections_reused": 5,
            "active_connections": 1,
            "total_connections": self.max_connections,
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """Get connection pool health status.

        Returns:
            Dictionary containing mock health status
        """
        return {
            "status": "healthy",
            "total_connections": self.max_connections,
            "active_connections": 1,
        }


# Backward compatibility - warn if imported from old location
def _check_import_location():
    """Check if MockConnectionPool is being imported from the correct location."""
    import inspect

    frame = inspect.currentframe()
    if frame and frame.f_back:
        caller_file = frame.f_back.f_code.co_filename
        if "engine.py" in caller_file or "engine_production.py" in caller_file:
            warnings.warn(
                "Importing MockConnectionPool from engine.py or engine_production.py "
                "is deprecated. Import from tests.fixtures.mock_helpers instead.",
                DeprecationWarning,
                stacklevel=3,
            )


_check_import_location()

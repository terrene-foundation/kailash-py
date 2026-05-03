"""Mock helpers for DataFlow testing.

This module provides mock infrastructure (e.g. `MockConnectionPool`) used by
`DataFlow.get_connection_pool()` and by integration-test fixtures. It lives
under `dataflow.testing` (a real package path) so production code can import
from it without violating `rules/dependencies.md` § "Declared = Imported"
(production source MUST NOT import from `tests.*`).

Relocated from `tests.fixtures.mock_helpers` in the dataflow-engine-pyright-cleanup
workspace (2026-05-04) to close pyright error E1 at engine.py:3437.
"""

from typing import Any, Dict


class MockConnectionPool:
    """Mock connection pool returned by `DataFlow.get_connection_pool()`.

    Provides a deterministic implementation of the connection-pool surface
    (`get_metrics`, `get_health_status`) for use by integration tests that
    inspect pool state without exercising real connection management.

    This class implements the `ConnectionPoolProtocol` (per `rules/testing.md`
    § "Protocol Adapters") and is therefore NOT a mock in the
    `unittest.mock`-BLOCKED sense — it is a deterministic protocol-satisfying
    adapter usable in Tier 2 integration tests.
    """

    def __init__(self, connection_manager: Any) -> None:
        """Initialize the mock connection pool.

        Args:
            connection_manager: A ConnectionManager instance (real or mock-like)
                whose `_connection_stats` dict the pool reads to size itself.
                If the attribute is missing, defaults to a 10-connection pool.
        """
        self.connection_manager = connection_manager
        self.max_connections: int = getattr(
            connection_manager, "_connection_stats", {}
        ).get("pool_size", 10)

    async def get_metrics(self) -> Dict[str, Any]:
        """Return deterministic connection-pool metrics for test assertions."""
        return {
            "connections_created": 1,
            "connections_reused": 5,
            "active_connections": 1,
            "total_connections": self.max_connections,
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """Return deterministic health status for test assertions."""
        return {
            "status": "healthy",
            "total_connections": self.max_connections,
            "active_connections": 1,
        }

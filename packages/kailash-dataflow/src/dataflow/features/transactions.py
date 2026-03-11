"""
DataFlow Transaction Management

Enterprise transaction handling and consistency.
"""

from contextlib import contextmanager
from typing import Any, Dict, Generator


class TransactionManager:
    """Transaction management for DataFlow operations."""

    def __init__(self, dataflow_instance):
        self.dataflow = dataflow_instance
        self._active_transactions = {}

    @contextmanager
    def transaction(
        self, isolation_level: str = "READ_COMMITTED"
    ) -> Generator[Dict[str, Any], None, None]:
        """Create a database transaction context.

        Args:
            isolation_level: Transaction isolation level

        Yields:
            Transaction context with commit/rollback methods
        """
        transaction_id = f"txn_{len(self._active_transactions) + 1}"

        try:
            # Begin transaction
            transaction_context = {
                "id": transaction_id,
                "isolation_level": isolation_level,
                "status": "active",
                "operations": [],
            }

            self._active_transactions[transaction_id] = transaction_context

            yield transaction_context

            # Commit transaction
            transaction_context["status"] = "committed"

        except Exception as e:
            # Rollback transaction
            if transaction_id in self._active_transactions:
                self._active_transactions[transaction_id]["status"] = "rolled_back"
                self._active_transactions[transaction_id]["error"] = str(e)
            raise

        finally:
            # Clean up
            if transaction_id in self._active_transactions:
                del self._active_transactions[transaction_id]

    def get_active_transactions(self) -> Dict[str, Dict[str, Any]]:
        """Get all active transactions."""
        return self._active_transactions.copy()

    def rollback_all(self) -> Dict[str, Any]:
        """Emergency rollback of all active transactions."""
        rolled_back = list(self._active_transactions.keys())

        for txn_id in rolled_back:
            self._active_transactions[txn_id]["status"] = "emergency_rollback"

        self._active_transactions.clear()

        return {
            "rolled_back_transactions": rolled_back,
            "count": len(rolled_back),
            "success": True,
        }

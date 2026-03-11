"""Transaction management nodes for DataFlow.

These nodes provide async transaction lifecycle management using real database
adapters (PostgreSQL, SQLite, MySQL). Each node extends AsyncNode and implements
async_run() to integrate with the adapter's transaction API.

Transaction flow:
    TransactionScopeNode  -> begins a transaction, stores it in workflow context
    TransactionCommitNode -> commits the active transaction from workflow context
    TransactionRollbackNode -> rolls back the active transaction
    TransactionSavepointNode -> creates a named savepoint within an active transaction
    TransactionRollbackToSavepointNode -> rolls back to a named savepoint
"""

import logging
import uuid
from typing import Any, Dict

from kailash.nodes.base import NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


def _get_adapter_from_context(node: AsyncNode):
    """Extract the database adapter from the DataFlow instance in workflow context.

    The DataFlow instance is expected to be stored under the 'dataflow_instance' key
    in the workflow context. The adapter is obtained by detecting the database type
    and creating/reusing the appropriate adapter via _get_cached_db_node().

    Args:
        node: The AsyncNode instance requesting the adapter.

    Returns:
        A database adapter (PostgreSQLAdapter, SQLiteAdapter, etc.) with transaction support.

    Raises:
        NodeExecutionError: If the DataFlow instance is missing or the adapter cannot be obtained.
    """
    dataflow_instance = node.get_workflow_context("dataflow_instance")
    if not dataflow_instance:
        raise NodeExecutionError(
            "DataFlow instance not found in workflow context. "
            "Ensure the workflow is executed with a DataFlow instance in context."
        )

    # Get the database type from the DataFlow config
    db_url = getattr(dataflow_instance.config.database, "url", None) or ""
    if "postgresql" in db_url or "postgres" in db_url:
        db_type = "postgresql"
    elif "mysql" in db_url:
        db_type = "mysql"
    else:
        db_type = "sqlite"

    # Use the DataFlow engine's cached db node to get the adapter
    db_node = dataflow_instance._get_cached_db_node(db_type)

    # The AsyncSQLDatabaseNode holds the adapter reference
    adapter = getattr(db_node, "adapter", None) or getattr(db_node, "_adapter", None)
    if adapter is None:
        raise NodeExecutionError(
            f"Could not obtain database adapter from cached db node for type '{db_type}'. "
            "Ensure the database connection has been initialized."
        )

    return adapter


class TransactionScopeNode(AsyncNode):
    """Node that begins a database transaction scope.

    Opens a real database transaction using the adapter's transaction() context manager.
    Stores the transaction object in workflow context for use by subsequent nodes
    (commit, rollback, savepoint).
    """

    def __init__(
        self,
        isolation_level: str = "READ_COMMITTED",
        timeout: int = 30,
        rollback_on_error: bool = True,
        **kwargs,
    ):
        self.isolation_level = isolation_level
        self.timeout = timeout
        self.rollback_on_error = rollback_on_error
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for transaction scope."""
        return {
            "isolation_level": NodeParameter(
                name="isolation_level",
                type=str,
                description="Transaction isolation level",
                default="READ_COMMITTED",
                required=False,
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                description="Transaction timeout in seconds",
                default=30,
                required=False,
            ),
            "rollback_on_error": NodeParameter(
                name="rollback_on_error",
                type=bool,
                description="Automatically rollback on error",
                default=True,
                required=False,
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Begin a transaction scope using the real database adapter."""
        isolation_level = kwargs.get("isolation_level", self.isolation_level)
        timeout = kwargs.get("timeout", self.timeout)
        rollback_on_error = kwargs.get("rollback_on_error", self.rollback_on_error)

        adapter = _get_adapter_from_context(self)
        transaction_id = f"tx_{uuid.uuid4().hex[:12]}"

        try:
            # Create the transaction context manager from the adapter
            txn_ctx = adapter.transaction()
            # Enter the async context manager to start the transaction
            txn = await txn_ctx.__aenter__()

            # Store the transaction and its context manager in workflow context
            # The context manager is needed for proper cleanup in __aexit__
            self.set_workflow_context("active_transaction", txn)
            self.set_workflow_context("transaction_context_manager", txn_ctx)
            self.set_workflow_context("transaction_id", transaction_id)
            self.set_workflow_context(
                "transaction_config",
                {
                    "isolation_level": isolation_level,
                    "timeout": timeout,
                    "rollback_on_error": rollback_on_error,
                },
            )
            self.set_workflow_context("savepoints", {})

            logger.info(
                f"Transaction {transaction_id} started "
                f"(isolation={isolation_level}, timeout={timeout}s)"
            )

            return {
                "status": "started",
                "transaction_id": transaction_id,
                "isolation_level": isolation_level,
                "timeout": timeout,
                "rollback_on_error": rollback_on_error,
            }

        except Exception as e:
            logger.error(f"Failed to begin transaction: {e}")
            raise NodeExecutionError(f"Failed to begin transaction: {e}") from e


class TransactionCommitNode(AsyncNode):
    """Node that commits the active database transaction.

    Retrieves the transaction object from workflow context and commits it.
    Properly exits the transaction context manager to release resources.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for transaction commit."""
        return {}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Commit the current transaction."""
        transaction = self.get_workflow_context("active_transaction")
        txn_ctx = self.get_workflow_context("transaction_context_manager")
        transaction_id = self.get_workflow_context("transaction_id", "unknown")

        if not transaction:
            raise NodeExecutionError("No active transaction found in workflow context")

        try:
            # Explicitly commit the transaction
            await transaction.commit()

            # Exit the context manager cleanly (no exception -> no auto-commit/rollback)
            if txn_ctx is not None:
                await txn_ctx.__aexit__(None, None, None)

            # Clear transaction state from workflow context
            self.set_workflow_context("active_transaction", None)
            self.set_workflow_context("transaction_context_manager", None)
            self.set_workflow_context("transaction_id", None)
            self.set_workflow_context("savepoints", None)

            logger.info(f"Transaction {transaction_id} committed successfully")

            return {
                "status": "committed",
                "transaction_id": transaction_id,
                "result": "Transaction committed successfully",
            }

        except Exception as e:
            logger.error(f"Failed to commit transaction {transaction_id}: {e}")
            # Attempt cleanup on commit failure
            try:
                if txn_ctx is not None:
                    await txn_ctx.__aexit__(type(e), e, e.__traceback__)
            except Exception as cleanup_err:
                logger.debug(
                    "Cleanup after commit failure also failed: %s",
                    type(cleanup_err).__name__,
                )
            self.set_workflow_context("active_transaction", None)
            self.set_workflow_context("transaction_context_manager", None)
            raise NodeExecutionError(f"Failed to commit transaction: {e}") from e


class TransactionRollbackNode(AsyncNode):
    """Node that rolls back the active database transaction.

    Retrieves the transaction object from workflow context and rolls it back.
    Properly exits the transaction context manager to release resources.
    """

    def __init__(self, reason: str = "Manual rollback", **kwargs):
        self.reason = reason
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for transaction rollback."""
        return {
            "reason": NodeParameter(
                name="reason",
                type=str,
                description="Reason for rollback",
                default="Manual rollback",
                required=False,
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Rollback the current transaction."""
        reason = kwargs.get("reason", self.reason)

        transaction = self.get_workflow_context("active_transaction")
        txn_ctx = self.get_workflow_context("transaction_context_manager")
        transaction_id = self.get_workflow_context("transaction_id", "unknown")

        if not transaction:
            raise NodeExecutionError("No active transaction found in workflow context")

        try:
            # Explicitly rollback the transaction
            await transaction.rollback()

            # Exit the context manager cleanly
            if txn_ctx is not None:
                await txn_ctx.__aexit__(None, None, None)

            # Clear transaction state from workflow context
            self.set_workflow_context("active_transaction", None)
            self.set_workflow_context("transaction_context_manager", None)
            self.set_workflow_context("transaction_id", None)
            self.set_workflow_context("savepoints", None)

            logger.info(f"Transaction {transaction_id} rolled back (reason: {reason})")

            return {
                "status": "rolled_back",
                "transaction_id": transaction_id,
                "reason": reason,
                "result": "Transaction rolled back successfully",
            }

        except Exception as e:
            logger.error(f"Failed to rollback transaction {transaction_id}: {e}")
            # Attempt cleanup
            try:
                if txn_ctx is not None:
                    await txn_ctx.__aexit__(type(e), e, e.__traceback__)
            except Exception as cleanup_err:
                logger.debug(
                    "Cleanup after rollback failure also failed: %s",
                    type(cleanup_err).__name__,
                )
            self.set_workflow_context("active_transaction", None)
            self.set_workflow_context("transaction_context_manager", None)
            raise NodeExecutionError(f"Failed to rollback transaction: {e}") from e


class TransactionSavepointNode(AsyncNode):
    """Node that creates a savepoint within an active transaction.

    Uses the database connection from the active transaction to execute
    a SAVEPOINT SQL statement. Tracks savepoints in workflow context.
    """

    def __init__(self, name: str = None, **kwargs):
        self.savepoint_name = name
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for savepoint creation."""
        return {
            "name": NodeParameter(
                name="name", type=str, description="Savepoint name", required=True
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Create a savepoint within the current transaction."""
        savepoint_name = kwargs.get("name", self.savepoint_name)
        if not savepoint_name:
            raise NodeExecutionError("Savepoint name is required")

        transaction = self.get_workflow_context("active_transaction")
        if not transaction:
            raise NodeExecutionError("No active transaction found in workflow context")

        # Get the underlying connection from the transaction object
        connection = getattr(transaction, "connection", None)
        if not connection:
            raise NodeExecutionError(
                "No database connection available on the active transaction"
            )

        # Validate savepoint name to prevent SQL injection
        import re

        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", savepoint_name):
            raise NodeExecutionError(
                f"Invalid savepoint name '{savepoint_name}': must be alphanumeric/underscores, "
                "start with a letter or underscore, and be 1-63 characters"
            )

        try:
            # Execute SAVEPOINT SQL on the transaction's connection
            await connection.execute(f'SAVEPOINT "{savepoint_name}"')

            # Track the savepoint in workflow context
            savepoints = self.get_workflow_context("savepoints") or {}
            savepoints[savepoint_name] = True
            self.set_workflow_context("savepoints", savepoints)

            transaction_id = self.get_workflow_context("transaction_id", "unknown")
            logger.info(
                f"Savepoint '{savepoint_name}' created in transaction {transaction_id}"
            )

            return {
                "status": "created",
                "savepoint": savepoint_name,
                "result": f"Savepoint '{savepoint_name}' created successfully",
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to create savepoint: {e}") from e


class TransactionRollbackToSavepointNode(AsyncNode):
    """Node that rolls back to a specific savepoint within an active transaction.

    Uses the database connection from the active transaction to execute
    a ROLLBACK TO SAVEPOINT SQL statement. Removes the savepoint and any
    savepoints created after it from tracking.
    """

    def __init__(self, savepoint: str = None, **kwargs):
        self.savepoint = savepoint
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for savepoint rollback."""
        return {
            "savepoint": NodeParameter(
                name="savepoint",
                type=str,
                description="Savepoint name to rollback to",
                required=True,
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Rollback to the specified savepoint."""
        savepoint_name = kwargs.get("savepoint", self.savepoint)
        if not savepoint_name:
            raise NodeExecutionError("Savepoint name is required")

        transaction = self.get_workflow_context("active_transaction")
        if not transaction:
            raise NodeExecutionError("No active transaction found in workflow context")

        # Verify savepoint exists
        savepoints = self.get_workflow_context("savepoints") or {}
        if savepoint_name not in savepoints:
            raise NodeExecutionError(f"Savepoint '{savepoint_name}' not found")

        # Get the underlying connection from the transaction object
        connection = getattr(transaction, "connection", None)
        if not connection:
            raise NodeExecutionError(
                "No database connection available on the active transaction"
            )

        # Validate savepoint name to prevent SQL injection
        import re

        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", savepoint_name):
            raise NodeExecutionError(
                f"Invalid savepoint name '{savepoint_name}': must be alphanumeric/underscores, "
                "start with a letter or underscore, and be 1-63 characters"
            )

        try:
            # Execute ROLLBACK TO SAVEPOINT SQL
            await connection.execute(f'ROLLBACK TO SAVEPOINT "{savepoint_name}"')

            # Remove this savepoint and any created after it
            # (Savepoints are implicitly released by rolling back past them)
            remaining = {}
            for sp_name in savepoints:
                if sp_name == savepoint_name:
                    break
                remaining[sp_name] = True
            self.set_workflow_context("savepoints", remaining)

            transaction_id = self.get_workflow_context("transaction_id", "unknown")
            logger.info(
                f"Rolled back to savepoint '{savepoint_name}' "
                f"in transaction {transaction_id}"
            )

            return {
                "status": "rolled_back_to_savepoint",
                "savepoint": savepoint_name,
                "result": f"Rolled back to savepoint '{savepoint_name}' successfully",
            }

        except Exception as e:
            raise NodeExecutionError(f"Failed to rollback to savepoint: {e}") from e

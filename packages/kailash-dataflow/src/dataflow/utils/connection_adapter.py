"""
ConnectionManagerAdapter for MigrationLockManager Integration

Bridges the gap between DataFlow's connection management system and
MigrationLockManager's expected interface, handling parameter format
conversion and result normalization.

Uses DataFlow's WorkflowBuilder pattern for actual query execution.
"""

import asyncio
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class ConnectionManagerAdapter:
    """
    Adapter that bridges DataFlow's connection manager interface
    to MigrationLockManager's expected database interface.

    Features:
    - Parameter placeholder conversion (%s to $1, $2, etc.)
    - DML result normalization (empty results → success indicator)
    - Transaction state tracking
    - Error handling and logging
    """

    def __init__(
        self, dataflow_instance, parameter_style: Optional[str] = None, runtime=None
    ):
        """
        Initialize connection manager adapter.

        Args:
            dataflow_instance: DataFlow instance with connection config
            parameter_style: Database parameter style (auto-detected if not provided)
            runtime: Optional shared runtime. If provided, the adapter acquires
                a reference (ref-count increment). If None, creates its own.
        """
        self.dataflow = dataflow_instance
        self._transaction_started = False
        # A single asyncpg connection held for the lifetime of an explicit
        # transaction. The non-transaction path spawns a per-call workflow
        # (each with its own pool), which is why BEGIN / COMMIT / ROLLBACK
        # through the workflow path does not actually scope an INSERT —
        # different connection every query. During a transaction we pin
        # all queries to this one asyncpg connection so BEGIN / COMMIT /
        # ROLLBACK are observed correctly.
        self._tx_connection = None

        # Auto-detect parameter style from database type if not provided
        if parameter_style:
            self._parameter_style = parameter_style
        else:
            from ..adapters.connection_parser import ConnectionParser

            db_url = dataflow_instance.config.database.url
            db_type = ConnectionParser.detect_database_type(db_url)
            self._parameter_style = db_type  # postgresql, mysql, or sqlite

        # Initialize runtime
        if runtime is not None:
            self._runtime = runtime.acquire()
            self._owns_runtime = False
            self._is_async = isinstance(runtime, AsyncLocalRuntime)
            logger.debug(
                "ConnectionManagerAdapter: Using injected runtime (ref_count=%d)",
                runtime.ref_count,
            )
        else:
            try:
                asyncio.get_running_loop()
                self._runtime = AsyncLocalRuntime()
                self._is_async = True
                logger.debug(
                    "ConnectionManagerAdapter: Detected async context, using AsyncLocalRuntime"
                )
            except RuntimeError:
                # Issue #478 — adapter-owned long-lived runtime.  Use the
                # public opt-out so Core SDK suppresses the ad-hoc-usage
                # deprecation warning AND skips atexit cleanup; the adapter
                # calls close() at its own shutdown.
                self._runtime = LocalRuntime().mark_externally_managed()
                self._is_async = False
                logger.debug(
                    "ConnectionManagerAdapter: Detected sync context, using LocalRuntime"
                )
            self._owns_runtime = True

        # Get connection details from DataFlow config
        self._connection_string = self.dataflow.config.database.get_connection_url(
            self.dataflow.config.environment
        )
        self._database_type = self._detect_database_type()

    async def execute_query(
        self, sql: str, params: Optional[List] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute query with parameter conversion and result normalization.

        Args:
            sql: SQL query string (may use %s placeholders)
            params: Query parameters

        Returns:
            List of result dictionaries, or success indicator for DML operations
        """
        try:
            # Convert parameter placeholders if needed
            converted_sql, converted_params = self._convert_parameters(sql, params)

            # If a transaction is open, route the query through the held
            # asyncpg connection so BEGIN / COMMIT / ROLLBACK actually scope
            # the operation. The workflow-based path spins up a fresh pool
            # per call, defeating transactionality.
            if self._transaction_started and self._tx_connection is not None:
                return await self._execute_on_tx_connection(
                    converted_sql, converted_params
                )

            # Use WorkflowBuilder pattern for query execution (DataFlow standard)
            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "query_execution",
                {
                    "connection_string": self._connection_string,
                    "database_type": self._database_type,
                    "query": converted_sql,
                    "params": converted_params,
                    "validate_queries": False,
                },
            )

            if self._is_async:
                results, _ = await self._runtime.execute_workflow_async(
                    workflow.build(), inputs={}
                )
            else:
                results, _ = self._runtime.execute(workflow.build())

            if "query_execution" not in results or results["query_execution"].get(
                "error"
            ):
                error_msg = results.get("query_execution", {}).get(
                    "error", "Unknown error"
                )
                raise RuntimeError(f"Query execution failed: {error_msg}")

            # Get the raw result
            raw_result = results["query_execution"].get("result", [])

            # Normalize results for MigrationLockManager expectations
            return self._normalize_result(raw_result, sql)

        except Exception as e:
            # SQL is a parameterized statement ($N / %s / ?); safe to log.
            # Raw params carry classified row values (PII, secrets) and MUST NOT
            # leak to aggregators. Log only arity. See rules/security.md §
            # "No secrets in logs" and rules/dataflow-classification.md.
            logger.error(
                "connection_adapter.connectionmanageradapter_query_execution_failed",
                extra={
                    "error": str(e),
                    "sql": sql,
                    "param_count": len(params) if params is not None else 0,
                },
            )
            raise

    async def _execute_on_tx_connection(
        self, sql: str, params: Optional[List]
    ) -> List[Dict[str, Any]]:
        """Execute a query on the held transaction connection.

        Only called when a transaction is active. PostgreSQL-only — MySQL
        and SQLite transaction routing is not yet implemented on this path
        and callers still go through the workflow path for those dialects.
        """
        conn = self._tx_connection
        sql_upper = sql.upper().strip()
        if any(
            sql_upper.startswith(dml)
            for dml in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]
        ):
            if params:
                status = await conn.execute(sql, *params)
            else:
                status = await conn.execute(sql)
            # asyncpg returns "INSERT 0 N", "UPDATE N", etc. — surface the N.
            rows_affected = 0
            if isinstance(status, str):
                parts = status.split()
                if parts and parts[-1].isdigit():
                    rows_affected = int(parts[-1])
            return [{"rows_affected": rows_affected}]
        if params:
            rows = await conn.fetch(sql, *params)
        else:
            rows = await conn.fetch(sql)
        return [dict(r) for r in rows]

    async def _get_tx_connection(self):
        """Open a dedicated asyncpg connection for the current transaction."""
        if self._database_type != "postgresql":
            # For MySQL / SQLite we fall back to the workflow path; those
            # dialects need their own drivers here and were not part of
            # the bug this path fixes.
            return None
        import asyncpg

        return await asyncpg.connect(self._connection_string)

    async def begin_transaction(self) -> None:
        """Begin database transaction on a dedicated held connection."""
        if self._transaction_started:
            raise RuntimeError(
                "begin_transaction called while a transaction is already "
                "active — call commit_transaction or rollback_transaction first"
            )
        try:
            self._tx_connection = await self._get_tx_connection()
            if self._tx_connection is not None:
                await self._tx_connection.execute("BEGIN")
            else:
                # Fallback path for non-postgresql dialects — the workflow
                # path cannot scope the transaction but we preserve the
                # existing (pre-fix) behavior so nothing regresses.
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "begin_transaction",
                    {
                        "connection_string": self._connection_string,
                        "database_type": self._database_type,
                        "query": "BEGIN",
                        "validate_queries": False,
                    },
                )
                if self._is_async:
                    await self._runtime.execute_workflow_async(
                        workflow.build(), inputs={}
                    )
                else:
                    self._runtime.execute(workflow.build())

            self._transaction_started = True
            logger.debug("Transaction started via ConnectionManagerAdapter")
        except Exception as e:
            logger.error(
                "connection_adapter.failed_to_begin_transaction",
                extra={"error": str(e)},
            )
            if self._tx_connection is not None:
                try:
                    await self._tx_connection.close()
                except Exception:
                    logger.debug("tx connection close failed during begin rollback")
                self._tx_connection = None
            raise

    async def commit_transaction(self) -> None:
        """Commit the active database transaction."""
        try:
            if self._tx_connection is not None:
                await self._tx_connection.execute("COMMIT")
                await self._tx_connection.close()
                self._tx_connection = None
            else:
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "commit_transaction",
                    {
                        "connection_string": self._connection_string,
                        "database_type": self._database_type,
                        "query": "COMMIT",
                        "validate_queries": False,
                    },
                )
                if self._is_async:
                    await self._runtime.execute_workflow_async(
                        workflow.build(), inputs={}
                    )
                else:
                    self._runtime.execute(workflow.build())
            self._transaction_started = False
            logger.debug("Transaction committed via ConnectionManagerAdapter")
        except Exception as e:
            logger.error(
                "connection_adapter.failed_to_commit_transaction",
                extra={"error": str(e)},
            )
            raise

    async def rollback_transaction(self) -> None:
        """Rollback the active database transaction."""
        try:
            if self._tx_connection is not None:
                await self._tx_connection.execute("ROLLBACK")
                await self._tx_connection.close()
                self._tx_connection = None
            else:
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    "rollback_transaction",
                    {
                        "connection_string": self._connection_string,
                        "database_type": self._database_type,
                        "query": "ROLLBACK",
                        "validate_queries": False,
                    },
                )
                if self._is_async:
                    await self._runtime.execute_workflow_async(
                        workflow.build(), inputs={}
                    )
                else:
                    self._runtime.execute(workflow.build())
            self._transaction_started = False
            logger.debug("Transaction rolled back via ConnectionManagerAdapter")
        except Exception as e:
            logger.error(
                "connection_adapter.failed_to_rollback_transaction",
                extra={"error": str(e)},
            )
            raise

    def close(self):
        """Release the runtime reference.

        Safe to call multiple times -- subsequent calls are no-ops.
        """
        if hasattr(self, "_runtime") and self._runtime is not None:
            self._runtime.release()
            self._runtime = None

    def __del__(self, _warnings=warnings):
        """Emit ResourceWarning if close() was not called explicitly."""
        if getattr(self, "_runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )
            try:
                self.close()
            except Exception:
                pass

    def _convert_parameters(
        self, sql: str, params: Optional[List]
    ) -> Tuple[str, Optional[List]]:
        """
        Convert parameter placeholders to database-specific format.

        Handles both:
        - %s format (neutral/MySQL format)
        - $1, $2, ... format (PostgreSQL format)

        Args:
            sql: SQL string with placeholders
            params: Parameter values

        Returns:
            Tuple of (converted_sql, params)
        """
        if not sql:
            return sql, params

        import re

        # Count placeholders to determine format
        pct_s_count = sql.count("%s")
        dollar_placeholders = re.findall(r"\$\d+", sql)
        dollar_count = len(dollar_placeholders)

        if pct_s_count == 0 and dollar_count == 0:
            return sql, params

        converted_sql = sql

        if self._parameter_style == "postgresql":
            if pct_s_count > 0:
                # Convert %s to $1, $2, $3, etc. for PostgreSQL
                for i in range(pct_s_count):
                    converted_sql = converted_sql.replace("%s", f"${i + 1}", 1)
            # If already $N format, no conversion needed
            return converted_sql, params

        elif self._parameter_style == "mysql":
            if dollar_count > 0:
                # Convert $1, $2, etc. to %s for MySQL
                converted_sql = re.sub(r"\$\d+", "%s", sql)
            # If already %s format, no conversion needed
            return converted_sql, params

        elif self._parameter_style == "sqlite":
            if pct_s_count > 0:
                # SQLite uses ? placeholders
                converted_sql = sql.replace("%s", "?")
            elif dollar_count > 0:
                # Convert $N to ? for SQLite
                converted_sql = re.sub(r"\$\d+", "?", sql)
            return converted_sql, params

        else:
            # Unknown parameter style - return as-is
            logger.warning(
                "connection_adapter.unknown_parameter_style",
                extra={"parameter_style": self._parameter_style},
            )
            return sql, params

    def _normalize_result(self, result: Any, original_sql: str) -> List[Dict[str, Any]]:
        """
        Normalize query results for MigrationLockManager compatibility.

        Args:
            result: Raw result from AsyncSQLDatabaseNode
            original_sql: Original SQL query for context

        Returns:
            Normalized result list
        """
        if result is None:
            return []

        # Handle AsyncSQLDatabaseNode result format
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            # Extract data from AsyncSQLDatabaseNode structured result
            node_result = result[0]
            if "data" in node_result:
                data = node_result["data"]
                if isinstance(data, list):
                    if len(data) == 0:
                        # Check if this was a DML operation that should indicate success
                        sql_upper = original_sql.upper().strip()
                        if any(
                            sql_upper.startswith(dml)
                            for dml in [
                                "INSERT",
                                "UPDATE",
                                "DELETE",
                                "CREATE",
                                "DROP",
                                "ALTER",
                            ]
                        ):
                            return [{"success": True}]
                        else:
                            return []
                    else:
                        # Convert dictionaries to tuples if needed for legacy compatibility
                        return self._convert_to_legacy_format(data, original_sql)
                else:
                    return [data] if data is not None else []
            else:
                # No 'data' field - might be a direct result
                return [node_result]

        elif isinstance(result, list):
            if len(result) == 0:
                # Check if this was a DML operation that should indicate success
                sql_upper = original_sql.upper().strip()
                if any(
                    sql_upper.startswith(dml)
                    for dml in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]
                ):
                    return [{"success": True}]
                else:
                    return []
            else:
                return result

        elif isinstance(result, dict):
            # AsyncSQLDatabaseNode returns {"data": [...], "row_count": N, ...}
            # Unwrap the envelope so callers see the data rows directly — otherwise
            # every SELECT looks truthy (the envelope dict is truthy even when
            # data=[]) and every INSERT looks indistinguishable from a NO-OP
            # caused by ON CONFLICT DO NOTHING.
            if "data" in result:
                data = result["data"]
                if isinstance(data, list):
                    if len(data) == 0:
                        sql_upper = original_sql.upper().strip()
                        if any(
                            sql_upper.startswith(dml)
                            for dml in [
                                "INSERT",
                                "UPDATE",
                                "DELETE",
                                "CREATE",
                                "DROP",
                                "ALTER",
                            ]
                        ):
                            # DML: surface row_count so callers can detect NO-OP
                            return [{"rows_affected": result.get("row_count", 0)}]
                        return []
                    return self._convert_to_legacy_format(data, original_sql)
                return [data] if data is not None else []
            # Single result - wrap in list
            return [result]

        else:
            # Unexpected result type - try to handle gracefully
            logger.warning(
                f"Unexpected result type from AsyncSQLDatabaseNode: {type(result)}"
            )
            logger.debug("connection_adapter.raw_result", extra={"result": result})
            return []

    def is_transaction_active(self) -> bool:
        """Check if a transaction is currently active."""
        return self._transaction_started

    def _detect_database_type(self) -> str:
        """Detect database type from connection string."""
        connection_lower = self._connection_string.lower()

        if (
            connection_lower.startswith("sqlite")
            or connection_lower == ":memory:"
            or connection_lower.endswith(".db")
            or connection_lower.endswith(".sqlite")
            or connection_lower.endswith(".sqlite3")
        ):
            return "sqlite"
        elif connection_lower.startswith("postgresql") or connection_lower.startswith(
            "postgres"
        ):
            return "postgresql"
        else:
            # Default to PostgreSQL
            return "postgresql"

    def _convert_to_legacy_format(
        self, data: List[Dict[str, Any]], original_sql: str
    ) -> List:
        """
        Convert dictionary results to tuple format for MigrationLockManager compatibility.

        The MigrationLockManager expects specific queries to return tuples, not dictionaries.
        This method detects those queries and converts the format accordingly.

        Args:
            data: List of dictionary results from AsyncSQLDatabaseNode
            original_sql: Original SQL query to detect expected format

        Returns:
            List in the format expected by MigrationLockManager
        """
        if not data or not isinstance(data, list):
            return data

        # Check if this is a MigrationLockManager query that expects tuples
        sql_lower = original_sql.lower().strip()

        # Lock status check query - expects tuples of (holder_process_id, acquired_at)
        if (
            "holder_process_id" in sql_lower
            and "acquired_at" in sql_lower
            and "select" in sql_lower
            and "from dataflow_migration_locks" in sql_lower
        ):
            tuple_results = []
            for row in data:
                if isinstance(row, dict):
                    tuple_results.append(
                        (row.get("holder_process_id"), row.get("acquired_at"))
                    )
                else:
                    tuple_results.append(row)
            return tuple_results

        # For other queries, return as-is
        return data

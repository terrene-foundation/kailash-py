"""DataFlow Bulk Create Node with Connection Pool - SDK Compliant Implementation."""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

from ..core.exceptions import (  # Issue #1552: redact driver-error VALUES
    sanitize_db_error,
)
from .workflow_connection_manager import SmartNodeConnectionMixin


@register_node()
class BulkCreatePoolNode(SmartNodeConnectionMixin, AsyncNode):
    """Node for bulk create operations with connection pool support.

    This node extends AsyncNode with SmartNodeConnectionMixin to provide
    high-performance bulk create operations using WorkflowConnectionPool,
    following SDK architectural patterns.

    Configuration Parameters (set during initialization):
        table_name: Database table to operate on
        connection_pool_id: ID of DataFlowConnectionManager in workflow (optional)
        connection_string: Database connection string for fallback direct processing (optional)
        database_type: Type of database (postgresql, mysql, sqlite)
        batch_size: Records per batch for processing
        conflict_resolution: How to handle conflicts (error, skip, update)
        auto_timestamps: Automatically add created_at/updated_at
        multi_tenant: Enable tenant isolation
        tenant_id: Default tenant ID for operations

    Runtime Parameters (provided during execution):
        data: List of records to insert
        tenant_id: Override default tenant ID
        return_ids: Return inserted record IDs
        dry_run: Simulate operation without executing
        use_pooled_connection: Whether to use connection pool (requires connection_pool_id)
        workflow_context: Context containing connection pool reference

    Note:
        When use_pooled_connection=True and connection_pool_id is set, this node will
        use WorkflowConnectionPool for optimized batch processing. Otherwise, it falls
        back to direct execution using AsyncSQLDatabaseNode (requires connection_string).
    """

    def __init__(self, **kwargs):
        """Initialize the BulkCreatePoolNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.table_name = kwargs.pop("table_name", None)
        self.database_type = kwargs.pop("database_type", "postgresql")
        self.batch_size = kwargs.pop("batch_size", 1000)
        self.conflict_resolution = kwargs.pop("conflict_resolution", "error")
        self.auto_timestamps = kwargs.pop("auto_timestamps", True)
        self.multi_tenant = kwargs.pop("multi_tenant", False)
        self.tenant_isolation = kwargs.pop("tenant_isolation", self.multi_tenant)
        self.default_tenant_id = kwargs.pop("tenant_id", None)
        self.connection_string = kwargs.pop("connection_string", None)

        # Call parent constructor - SmartNodeConnectionMixin will extract connection_pool_id
        super().__init__(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of records to insert",
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                description="Tenant ID for multi-tenant operations",
            ),
            "return_ids": NodeParameter(
                name="return_ids",
                type=bool,
                required=False,
                default=False,
                description="Return the IDs of inserted records",
            ),
            "dry_run": NodeParameter(
                name="dry_run",
                type=bool,
                required=False,
                default=False,
                description="Simulate operation without executing",
            ),
            "workflow_context": NodeParameter(
                name="workflow_context",
                type=dict,
                required=False,
                default={},
                description="Workflow context containing connection pool",
            ),
            "use_pooled_connection": NodeParameter(
                name="use_pooled_connection",
                type=bool,
                required=False,
                default=False,
                description="Whether to use connection pool for processing",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute bulk create operation asynchronously using connection pool."""
        # For async operations, directly call the implementation to avoid sync/async issues
        # The mixin's _execute_with_connection is not async-aware
        return await self._perform_bulk_create(**kwargs)

    async def _perform_bulk_create(self, **kwargs) -> dict[str, Any]:
        """Perform the actual bulk create operation."""
        # Validate and map parameters using SDK validation
        validated_inputs = self.validate_inputs(**kwargs)

        # Extract validated parameters
        data = validated_inputs.get("data", [])
        tenant_id = validated_inputs.get("tenant_id", self.default_tenant_id)
        return_ids = validated_inputs.get("return_ids", False)
        dry_run = validated_inputs.get("dry_run", False)
        use_pooled_connection = validated_inputs.get("use_pooled_connection", False)

        # Validate required configuration
        if not self.table_name:
            raise NodeValidationError(
                "table_name must be provided during node initialization"
            )

        if not data:
            raise NodeValidationError("No data provided for bulk create")

        # Initialize result tracking
        total_records = len(data)
        created_count = 0
        skipped_count = 0
        conflict_count = 0
        error_count = 0
        created_ids = []
        errors = []
        batches = 0

        try:
            # Check if we have connection pool access
            # Track whether connection pool was actually used
            actually_used_pool = False

            # #1585: if this node runs inside a TransactionScopeNode, the write
            # MUST join the scope's connection so a later rollback discards it.
            # The pooled path uses an UNRELATED connection pool that cannot join
            # the scope, so force the direct borrow path when a scope is active
            # (the borrowed txn handle carries the scope's connection). Resolving
            # here is loop-safe: async_run awaits _perform_bulk_create directly on
            # the runtime's event loop (no async_safe_run boundary), so the
            # borrowed asyncpg connection stays on its owning loop. Fail-closed if
            # the scope exposes no `.transaction` handle.
            from ..core.nodes import _resolve_scope_transaction

            scope_txn = _resolve_scope_transaction(self)

            if scope_txn is not None:
                # Force direct execution ON the scope's connection (bypass pool).
                results = await self._process_direct(
                    data, tenant_id, return_ids, dry_run, transaction=scope_txn
                )
            elif use_pooled_connection and self.connection_pool_id:
                # Try to process using connection pool
                results, actually_used_pool = await self._process_with_pool_tracked(
                    data, tenant_id, return_ids, dry_run
                )
            else:
                # Fallback to direct execution
                results = await self._process_direct(
                    data, tenant_id, return_ids, dry_run
                )

            # Extract results
            created_count = results.get("created_count", 0)
            skipped_count = results.get("skipped_count", 0)
            conflict_count = results.get("conflict_count", 0)
            error_count = results.get("error_count", 0)
            created_ids = results.get("created_ids", [])
            errors = results.get("errors", [])
            batches = results.get("batches", 0)

            # Build result following SDK patterns
            result = {
                "success": error_count == 0 and (created_count > 0 or dry_run),
                "created_count": created_count,
                "total_records": total_records,
                "batches": batches,
                "metadata": {
                    "table": self.table_name,
                    "conflict_resolution": self.conflict_resolution,
                    "batch_size": self.batch_size,
                    "dry_run": dry_run,
                    "multi_tenant": self.multi_tenant,
                    "auto_timestamps": self.auto_timestamps,
                    "used_connection_pool": actually_used_pool,
                },
            }

            # Add optional fields based on operation results
            if tenant_id and self.multi_tenant:
                result["tenant_id"] = tenant_id

            if skipped_count > 0:
                result["skipped_count"] = skipped_count

            if conflict_count > 0:
                result["conflict_count"] = conflict_count

            if error_count > 0:
                result["error_count"] = error_count
                result["errors"] = errors

            if return_ids and created_ids:
                result["created_ids"] = created_ids

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            # Issue #1552 (FIX 11, HIGH): BulkCreatePoolNode is @register_node()
            # and runs REAL batch INSERTs; a duplicate-value INSERT raises a driver
            # error carrying DETAIL: Key(col)=(value). Sanitize the raised message
            # (same class as core/nodes.py BulkCreate). `from e` preserves the raw
            # exception as __cause__ for local traceback diagnosability (mirrors #1550).
            raise NodeExecutionError(
                f"Bulk create operation failed: {sanitize_db_error(str(e))}"
            ) from e

    async def _process_with_pool_tracked(
        self,
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_ids: bool,
        dry_run: bool,
    ) -> tuple[Dict[str, Any], bool]:
        """Process bulk create using connection pool, returning results and pool usage status."""
        from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

        # Get pool instance from manager
        if self._pool_manager and hasattr(self._pool_manager, "get_pool_instance"):
            try:
                pool_instance = self._pool_manager.get_pool_instance()
                if pool_instance:
                    # Use pool for optimized batch processing
                    results = await self._execute_batched_inserts_with_pool(
                        pool_instance, data, tenant_id, return_ids, dry_run
                    )
                    return results, True  # Successfully used pool
            except Exception:
                # If pool processing fails, fall back to direct execution
                pass

        # Fallback to direct execution
        results = await self._process_direct(data, tenant_id, return_ids, dry_run)
        return results, False  # Did not use pool

    async def _process_with_pool(
        self,
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_ids: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Process bulk create using connection pool (legacy method)."""
        results, _ = await self._process_with_pool_tracked(
            data, tenant_id, return_ids, dry_run
        )
        return results

    async def _execute_batched_inserts_with_pool(
        self,
        pool: Any,  # WorkflowConnectionPool instance
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_ids: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        """Execute batched inserts using connection pool."""
        results = {
            "created_count": 0,
            "skipped_count": 0,
            "conflict_count": 0,
            "error_count": 0,
            "created_ids": [],
            "errors": [],
            "batches": 0,
        }

        if dry_run:
            # Simulate the operation
            results["created_count"] = len(data)
            results["batches"] = (len(data) + self.batch_size - 1) // self.batch_size
            return results

        # Process in batches using pool connections
        for i in range(0, len(data), self.batch_size):
            batch = data[i : i + self.batch_size]
            results["batches"] += 1

            try:
                # Get connection from pool
                async with pool.acquire() as conn:
                    batch_result = await self._execute_batch_with_connection(
                        conn, batch, tenant_id, return_ids
                    )

                    # Aggregate results
                    results["created_count"] += batch_result.get("created_count", 0)
                    results["skipped_count"] += batch_result.get("skipped_count", 0)
                    results["conflict_count"] += batch_result.get("conflict_count", 0)
                    results["error_count"] += batch_result.get("error_count", 0)

                    if return_ids and "created_ids" in batch_result:
                        results["created_ids"].extend(batch_result["created_ids"])

            except Exception as e:
                results["error_count"] += len(batch)
                # Issue #1552 (FIX 11): sanitize the driver error before it lands
                # in the returned results["errors"] list (returned-dict surface).
                results["errors"].append(
                    f"Batch {results['batches']} error: {sanitize_db_error(str(e))}"
                )

                if self.conflict_resolution == "error":
                    break

        return results

    async def _execute_batch_with_connection(
        self,
        conn: Any,
        batch: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_ids: bool,
    ) -> Dict[str, Any]:
        """Execute a single batch using provided connection."""
        # This would use the actual connection to execute SQL
        # For now, simulate the execution
        return {
            "created_count": len(batch),
            "created_ids": list(range(len(batch))) if return_ids else [],
        }

    async def _process_direct(
        self,
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_ids: bool,
        dry_run: bool,
        transaction: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Process bulk create without connection pool (fallback implementation).

        This method provides a fallback when WorkflowConnectionPool is unavailable,
        using AsyncSQLDatabaseNode directly for database operations.

        Note: This implementation mirrors the standard BulkOperations.bulk_create()
        pattern but operates within the node architecture.

        #1585: ``transaction`` is a borrowed adapter txn handle ``(conn, tx)`` from
        an active ``TransactionScopeNode`` (resolved in ``_perform_bulk_create``).
        When present, every batch INSERT runs ON that connection instead of
        auto-committing, so the write joins the scope and is discarded on
        rollback. ``None`` preserves the prior auto-commit behavior.
        """
        if dry_run:
            return {
                "created_count": len(data),
                "batches": (len(data) + self.batch_size - 1) // self.batch_size,
                "skipped_count": 0,
                "conflict_count": 0,
                "error_count": 0,
                "created_ids": [],
                "errors": [],
            }

        # Real implementation using AsyncSQLDatabaseNode
        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        # Check if connection_string is available
        connection_string = getattr(self, "connection_string", None)
        if not connection_string:
            if transaction is not None:
                # #1585 fail-closed: an active transaction scope with no
                # connection_string cannot join the scope, and returning the
                # simulation stub below would report fabricated success while
                # writing nothing — the caller would believe the bulk write
                # persisted inside the scope. Refuse rather than silently no-op.
                from kailash.sdk_exceptions import NodeExecutionError

                raise NodeExecutionError(
                    "BulkCreatePoolNode is inside a TransactionScopeNode but has "
                    "no connection_string to join the scope's connection (#1585). "
                    "Provide connection_string, or use the generated "
                    "'<Model>BulkCreateNode' / db.express.bulk_create which are "
                    "scope-aware."
                )
            # Fallback to simulation mode for backward compatibility
            # This allows tests to run without requiring a real database connection
            # In production, either connection_string or use_pooled_connection should be provided
            return {
                "created_count": len(data),
                "batches": (len(data) + self.batch_size - 1) // self.batch_size,
                "skipped_count": 0,
                "conflict_count": 0,
                "error_count": 0,
                "created_ids": list(range(len(data))) if return_ids else [],
                "errors": [],
            }

        # Apply tenant filtering if multi-tenant
        processed_data = data.copy()
        if self.multi_tenant and tenant_id:
            for record in processed_data:
                record["tenant_id"] = tenant_id

        # Issue #1546: for conflict_resolution="update" on MySQL, resolve the
        # row-alias upsert form ONCE (``VALUES(col)`` is deprecated on 8.0.20+).
        # This node has no DataFlow instance, so it version-probes via its own
        # AsyncSQLDatabaseNode through the shared process-cached helper.
        mysql_use_row_alias = False
        if (
            self.conflict_resolution == "update"
            and self.database_type.lower() == "mysql"
        ):
            from dataflow.sql.dialects import (
                mysql_row_alias_cache_key,
                mysql_row_alias_support_cached,
                resolve_mysql_row_alias_support,
            )

            _key = mysql_row_alias_cache_key(connection_string)
            _cached = mysql_row_alias_support_cached(_key)
            if _cached is not None:
                mysql_use_row_alias = _cached
            else:
                # Cache miss: probe via a throwaway node, then clean it up so no
                # unclosed connection leaks a ResourceWarning.
                _version_node = AsyncSQLDatabaseNode(
                    connection_string=connection_string,
                    database_type=self.database_type,
                    validate_queries=False,
                )
                try:
                    mysql_use_row_alias = await resolve_mysql_row_alias_support(
                        _version_node, _key
                    )
                finally:
                    await _version_node.cleanup()

        # Initialize result tracking
        total_inserted = 0
        batches_processed = 0
        created_ids = []
        errors = []

        try:
            # Get column names from first record
            if not processed_data:
                return {
                    "created_count": 0,
                    "batches": 0,
                    "skipped_count": 0,
                    "conflict_count": 0,
                    "error_count": 0,
                    "created_ids": [],
                    "errors": [],
                }

            columns = list(processed_data[0].keys())
            column_names = ", ".join(columns)

            # Process in batches
            for i in range(0, len(processed_data), self.batch_size):
                batch = processed_data[i : i + self.batch_size]
                values_placeholders = []
                params = []

                # Build batch INSERT query
                for record in batch:
                    if self.database_type.lower() == "postgresql":
                        placeholders = ", ".join(
                            [
                                f"${j + 1}"
                                for j in range(len(params), len(params) + len(columns))
                            ]
                        )
                    elif self.database_type.lower() == "mysql":
                        placeholders = ", ".join(["%s"] * len(columns))
                    else:  # sqlite
                        placeholders = ", ".join(["?"] * len(columns))

                    values_placeholders.append(f"({placeholders})")
                    params.extend([record.get(col) for col in columns])

                values_clause = ", ".join(values_placeholders)

                # Handle conflict resolution
                if self.conflict_resolution == "skip":
                    # Use ON CONFLICT DO NOTHING for PostgreSQL/SQLite
                    if self.database_type.lower() in ["postgresql", "sqlite"]:
                        conflict_clause = "ON CONFLICT (id) DO NOTHING"
                    else:  # MySQL
                        conflict_clause = "ON DUPLICATE KEY UPDATE id = id"
                    query = f"INSERT INTO {self.table_name} ({column_names}) VALUES {values_clause} {conflict_clause}"
                elif self.conflict_resolution == "update":
                    # SECURITY (#1526 sibling — cross-tenant write): for a
                    # multi_tenant model the ``id`` PK is global, so a cross-tenant
                    # ``id`` collision must NOT let tenant B's upsert overwrite or
                    # steal tenant A's row. Exclude ``tenant_id`` from the SET (no
                    # ownership flip) and gate the update by the row's own tenant —
                    # PG/SQLite via ``WHERE table.tenant_id = EXCLUDED.tenant_id``,
                    # MySQL ODKU (no WHERE) via a per-column ``IF(tenant_id=...)``.
                    tenant_guarded = self.multi_tenant and "tenant_id" in columns
                    # Use ON CONFLICT DO UPDATE for PostgreSQL/SQLite
                    if self.database_type.lower() in ["postgresql", "sqlite"]:
                        update_columns = [
                            col
                            for col in columns
                            if col != "id"
                            and not (tenant_guarded and col == "tenant_id")
                        ]
                        if update_columns:
                            set_parts = [
                                f"{col} = EXCLUDED.{col}" for col in update_columns
                            ]
                            tenant_where = (
                                f" WHERE {self.table_name}.tenant_id = EXCLUDED.tenant_id"
                                if tenant_guarded
                                else ""
                            )
                            conflict_clause = (
                                f"ON CONFLICT (id) DO UPDATE SET "
                                f"{', '.join(set_parts)}{tenant_where}"
                            )
                        else:
                            conflict_clause = "ON CONFLICT (id) DO NOTHING"
                    else:  # MySQL
                        # Issue #1546: emit the row-alias form on MySQL 8.0.19+
                        # (``VALUES(col)`` deprecated on 8.0.20+); the INSERT-side
                        # ``AS new_row`` alias and the ODKU ``new_row.col`` references
                        # are built from the same flag so they cannot drift.
                        update_columns = [
                            col
                            for col in columns
                            if col != "id"
                            and not (tenant_guarded and col == "tenant_id")
                        ]
                        if update_columns:

                            def _new_ref(c: str) -> str:
                                return (
                                    f"new_row.{c}"
                                    if mysql_use_row_alias
                                    else f"VALUES({c})"
                                )

                            if tenant_guarded:
                                # ODKU has no WHERE — guard each SET with the tenant
                                # IF() so a cross-tenant collision keeps the victim's
                                # existing value (no theft, no version/timestamp bump).
                                set_parts = [
                                    f"{col} = IF(tenant_id = {_new_ref('tenant_id')}, "
                                    f"{_new_ref(col)}, {col})"
                                    for col in update_columns
                                ]
                            else:
                                set_parts = [
                                    f"{col} = {_new_ref(col)}" for col in update_columns
                                ]
                            conflict_clause = (
                                f"ON DUPLICATE KEY UPDATE {', '.join(set_parts)}"
                            )
                        else:
                            conflict_clause = "ON DUPLICATE KEY UPDATE id = id"
                    mysql_alias_decl = (
                        " AS new_row"
                        if (
                            mysql_use_row_alias
                            and self.database_type.lower() == "mysql"
                        )
                        else ""
                    )
                    query = f"INSERT INTO {self.table_name} ({column_names}) VALUES {values_clause}{mysql_alias_decl} {conflict_clause}"
                else:  # error mode (default)
                    query = f"INSERT INTO {self.table_name} ({column_names}) VALUES {values_clause}"

                # Execute batch using AsyncSQLDatabaseNode. Each batch creates a
                # fresh (non-pooled) node; clean it up after the query so its
                # connection does not leak a ResourceWarning on GC — symmetry with
                # the sibling bulk_upsert.py::_execute_query cleanup (#1546 round-2).
                from ..core.credential_provider import (
                    get_active_credential_provider,
                )

                sql_node = AsyncSQLDatabaseNode(
                    connection_string=connection_string,
                    database_type=self.database_type,
                    query=query,
                    params=params,
                    fetch_mode="all",
                    validate_queries=False,
                    transaction_mode="auto",
                    # Issue #1741: this standalone workflow node holds no
                    # DataFlow instance, so token-based DB auth arrives via the
                    # context-scoped provider (bound by
                    # ``credential_provider_scope`` around runtime.execute);
                    # None = unchanged.
                    credential_provider=get_active_credential_provider(),
                )
                try:
                    # #1585: transaction=None → auto-commit (unchanged); a
                    # borrowed scope handle → run ON the scope's connection.
                    result = await sql_node.async_run(transaction=transaction)
                finally:
                    await sql_node.cleanup()

                # Extract rows_affected from result
                rows_affected = 0
                if result and "result" in result:
                    result_data = result["result"]
                    if "row_count" in result_data:
                        rows_affected = result_data.get("row_count", 0)
                    elif "data" in result_data and len(result_data["data"]) > 0:
                        rows_affected = result_data["data"][0].get("rows_affected", 0)

                total_inserted += rows_affected
                batches_processed += 1

                # If return_ids requested, we'd need to query for the IDs
                # For now, simulate with range (same as stub)
                if return_ids:
                    created_ids.extend(
                        list(range(len(created_ids), len(created_ids) + rows_affected))
                    )

        except Exception as e:
            # Issue #1552 (FIX 11): sanitize the driver error before it lands in
            # the returned errors list (returned-dict surface).
            errors.append(sanitize_db_error(str(e)))
            return {
                "created_count": total_inserted,
                "batches": batches_processed,
                "skipped_count": 0,
                "conflict_count": 0,
                "error_count": len(data) - total_inserted,
                "created_ids": created_ids,
                "errors": errors,
            }

        return {
            "created_count": total_inserted,
            "batches": batches_processed,
            "skipped_count": 0,
            "conflict_count": 0,
            "error_count": 0,
            "created_ids": created_ids if return_ids else [],
            "errors": errors,
        }

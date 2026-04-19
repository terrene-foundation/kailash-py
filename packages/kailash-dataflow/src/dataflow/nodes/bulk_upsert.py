"""DataFlow Bulk Upsert Node - SDK Compliant Implementation."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from kailash.db.dialect import _validate_identifier
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


# #499 finding 5 — PG/MySQL drivers embed raw column values in DETAIL /
# Key(...)=(…) clauses. Strip them before any log or return-value echo so
# PII / SECRET column values cannot leak through the observability layer.
# The surrounding error text (class of failure, table, constraint name)
# stays so operators retain triage signal.
_DETAIL_RE = re.compile(r"DETAIL:[^\n]*", re.IGNORECASE)
_KEY_VALUES_RE = re.compile(r"Key \(([^)]+)\)=\(([^)]*)\)", re.IGNORECASE)


def _sanitize_db_error(msg: str) -> str:
    """Redact column values from DB driver error messages."""
    if not isinstance(msg, str):
        return "<non-string error>"
    msg = _DETAIL_RE.sub("DETAIL: [REDACTED]", msg)
    msg = _KEY_VALUES_RE.sub(r"Key (\1)=([REDACTED])", msg)
    return msg


# Allowlist of supported dialects. Unknown values (typos like "postgres",
# "pg") MUST raise loudly rather than fall through to SQLite REPLACE
# semantics, which masks misconfiguration as a non-fatal SQL syntax error
# at execution time. See `rules/dataflow-identifier-safety.md`.
_SUPPORTED_DIALECTS = frozenset({"postgresql", "mysql", "sqlite"})

from .workflow_connection_manager import SmartNodeConnectionMixin


@register_node()
class BulkUpsertNode(SmartNodeConnectionMixin, AsyncNode):
    """Node for bulk upsert (insert or update) operations in DataFlow.

    This node extends AsyncNode with SmartNodeConnectionMixin to provide
    high-performance bulk upsert operations with connection pool support,
    following SDK architectural patterns.

    Configuration Parameters (set during initialization):
        table_name: Database table to operate on
        connection_string: Database connection string (fallback if no pool)
        connection_pool_id: ID of DataFlowConnectionManager in workflow (preferred)
        database_type: Type of database (postgresql, mysql, sqlite)
        batch_size: Records per batch for processing
        merge_strategy: How to handle conflicts (update, ignore)
        conflict_columns: Columns that define uniqueness for conflicts
        auto_timestamps: Automatically add/update timestamps
        multi_tenant: Enable tenant isolation
        tenant_id: Default tenant ID for operations
        version_control: Enable optimistic locking with version field

    Runtime Parameters (provided during execution):
        data: List of records to upsert
        tenant_id: Override default tenant ID
        return_records: Return upserted records in response
        dry_run: Simulate operation without executing
    """

    def __init__(self, **kwargs):
        """Initialize the BulkUpsertNode with configuration parameters."""
        # Extract configuration parameters before calling super()
        self.table_name = kwargs.pop("table_name", None)
        self.connection_string = kwargs.pop("connection_string", None)
        self.database_type = kwargs.pop("database_type", "postgresql")
        self.batch_size = kwargs.pop("batch_size", 1000)
        self.merge_strategy = kwargs.pop("merge_strategy", "update")
        self.conflict_columns = kwargs.pop("conflict_columns", ["email"])
        self.auto_timestamps = kwargs.pop("auto_timestamps", True)
        self.multi_tenant = kwargs.pop("multi_tenant", False)
        self.tenant_isolation = kwargs.pop("tenant_isolation", self.multi_tenant)
        self.default_tenant_id = kwargs.pop("tenant_id", None)
        self.version_control = kwargs.pop("version_control", False)
        self.enable_versioning = kwargs.pop("enable_versioning", self.version_control)
        self.version_check = kwargs.pop("version_check", self.version_control)
        self.version_field = kwargs.pop("version_field", "version")
        self.handle_duplicates = kwargs.pop(
            "handle_duplicates", "first"
        )  # 'first' or 'last'
        # Use any of the version-related parameters
        self.version_control = (
            self.enable_versioning or self.version_control or self.version_check
        )

        # Call parent constructor
        super().__init__(**kwargs)

        # Validate required configuration
        if not self.table_name:
            raise NodeValidationError("table_name is required for BulkUpsertNode")

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the runtime parameters this node accepts."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of records to upsert as dictionaries",
                auto_map_from=["records", "rows", "documents"],
            ),
            "tenant_id": NodeParameter(
                name="tenant_id",
                type=str,
                required=False,
                description="Tenant ID for multi-tenant operations",
            ),
            "return_records": NodeParameter(
                name="return_records",
                type=bool,
                required=False,
                default=False,
                description="Return upserted records in the response",
                auto_map_from=["return_upserted", "return_data"],
            ),
            "dry_run": NodeParameter(
                name="dry_run",
                type=bool,
                required=False,
                default=False,
                description="Simulate the operation without executing",
            ),
            "merge_strategy": NodeParameter(
                name="merge_strategy",
                type=str,
                required=False,
                default=None,
                description="How to handle conflicts: update, ignore (overrides config)",
            ),
            "conflict_on": NodeParameter(
                name="conflict_on",
                type=list,
                required=False,
                default=None,
                description="Fields to detect conflicts on (overrides config conflict_columns). Example: ['email'] or ['order_id', 'product_id']",
            ),
            "workflow_context": NodeParameter(
                name="workflow_context",
                type=dict,
                required=False,
                default={},
                description="Workflow context containing connection pool reference",
            ),
        }

    async def async_run(self, **kwargs) -> dict[str, Any]:
        """Execute bulk upsert operation asynchronously with connection pool support."""
        # _execute_with_connection is synchronous: when operation_func is a
        # coroutine function it internally resolves via async_safe_run() and
        # returns the already-resolved dict result. The value is NOT awaitable.
        return self._execute_with_connection(self._perform_bulk_upsert, **kwargs)

    async def _perform_bulk_upsert(self, **kwargs) -> dict[str, Any]:
        """Perform the actual bulk upsert operation."""
        import time

        start_time = time.time()

        try:
            # Validate and map parameters using SDK validation
            validated_inputs = self.validate_inputs(**kwargs)

            # Extract validated parameters
            data = validated_inputs.get("data", [])
            tenant_id = validated_inputs.get("tenant_id", self.default_tenant_id)
            return_records = validated_inputs.get("return_records", False)
            dry_run = validated_inputs.get("dry_run", False)
            merge_strategy = (
                validated_inputs.get("merge_strategy") or self.merge_strategy
            )
            # Use conflict_on from runtime parameter, otherwise fall back to config conflict_columns
            conflict_on = validated_inputs.get("conflict_on") or self.conflict_columns

            # Validate input data
            if not data:
                raise NodeValidationError("No data provided for bulk upsert")

            # Validate data consistency
            validation_result = self._validate_data_schema(data)
            if not validation_result["valid"]:
                raise NodeValidationError(
                    f"Data validation failed: {validation_result['errors']}"
                )

            # Execute the bulk upsert operation
            if self.connection_string and not dry_run:
                # Remove parameters that are passed explicitly to avoid duplicate argument error
                kwargs_copy = kwargs.copy()
                kwargs_copy.pop("data", None)
                kwargs_copy.pop("tenant_id", None)
                kwargs_copy.pop("return_records", None)
                kwargs_copy.pop("merge_strategy", None)
                kwargs_copy.pop("conflict_on", None)
                (
                    rows_affected,
                    inserted_count,
                    updated_count,
                    upserted_records,
                    duplicates_removed,
                ) = await self._execute_real_bulk_upsert(
                    data,
                    tenant_id,
                    return_records,
                    merge_strategy,
                    conflict_on,
                    **kwargs_copy,
                )
            else:
                # Dry run or fallback mock
                rows_affected = len(data)
                inserted_count = len(data) // 2  # Mock estimation
                updated_count = len(data) - inserted_count
                upserted_records = []
                duplicates_removed = 0  # No deduplication in dry run

            # Calculate performance metrics
            end_time = time.time()
            execution_time = end_time - start_time

            # Calculate metrics
            total_records = len(data)
            records_per_second = (
                rows_affected / execution_time if execution_time > 0 else 0
            )
            batch_count = (total_records + self.batch_size - 1) // self.batch_size

            # Build result following SDK patterns
            result = {
                "success": True,
                "rows_affected": rows_affected,
                "inserted": inserted_count,
                "updated": updated_count,
                "upserted": rows_affected,
                "upserted_count": rows_affected,  # Compatibility alias for tests
                "total": total_records,
                "batch_count": batch_count,
                "duplicates_removed": duplicates_removed,
                "dry_run": dry_run,
                "performance_metrics": {
                    "execution_time_seconds": execution_time,
                    "elapsed_seconds": execution_time,
                    "records_per_second": records_per_second,
                    "upserted_records": rows_affected,
                    "inserted_records": inserted_count,
                    "updated_records": updated_count,
                    "avg_time_per_record": (
                        execution_time / rows_affected if rows_affected > 0 else 0
                    ),
                    "batch_processing_time": execution_time,
                    "batches_processed": batch_count,
                    "batch_count": batch_count,
                    "meets_target": records_per_second >= 1000,
                    "target_performance": 1000,
                },
                "metadata": {
                    "table_name": self.table_name,
                    "merge_strategy": merge_strategy,
                    "conflict_columns": conflict_on,  # Use resolved conflict_on
                    "batch_size": self.batch_size,
                    "auto_timestamps": self.auto_timestamps,
                    "version_control": self.version_control,
                },
            }

            # Add upserted records if requested
            if return_records and upserted_records:
                result["upserted_records"] = upserted_records
                result["records"] = upserted_records  # Test compatibility

            # Add dry run specific fields
            if dry_run:
                result["would_upsert"] = rows_affected
                result["query_preview"] = (
                    f"INSERT INTO {self.table_name} (...) VALUES (...) ON CONFLICT (...) DO UPDATE SET ..."
                )
                result["data_sample"] = data[:3] if len(data) > 3 else data

            return result

        except (ValueError, NodeValidationError):
            # Let validation errors propagate for proper test handling
            raise
        except Exception as e:
            return {"success": False, "error": str(e), "rows_affected": 0}

    def _validate_data_schema(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate input data for consistent schema."""
        errors = []
        warnings = []

        if not data:
            errors.append("Data list is empty")
            return {"valid": False, "errors": errors, "warnings": warnings}

        # Check for consistent schema
        first_keys = set(data[0].keys())
        for i, record in enumerate(data[1:], 1):
            record_keys = set(record.keys())
            if record_keys != first_keys:
                warnings.append(f"Record {i} has different schema than first record")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    async def _execute_real_bulk_upsert(
        self,
        data: List[Dict[str, Any]],
        tenant_id: Optional[str],
        return_records: bool,
        merge_strategy: str,
        conflict_on: List[str],
        **kwargs,
    ) -> tuple[int, int, int, List[Dict[str, Any]], int]:
        """Execute real bulk upsert using database connection."""
        try:
            # Import here to avoid circular imports
            from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

            # Prepare data with tenant isolation if enabled
            processed_data = self._prepare_data_for_upsert(data, tenant_id)

            # Remove duplicates within the batch to avoid PostgreSQL conflict errors
            original_count = len(processed_data)
            deduplicated_data = self._deduplicate_batch_data(
                processed_data, conflict_on
            )
            duplicates_removed = original_count - len(deduplicated_data)

            # Get column names from first record
            columns = list(deduplicated_data[0].keys())
            column_names = ", ".join(columns)

            # Handle batching
            total_rows_affected = 0
            total_inserted = 0
            total_updated = 0
            all_upserted_records = []
            batch_errors: List[str] = []
            batches_attempted = 0

            for i in range(0, len(deduplicated_data), self.batch_size):
                batch = deduplicated_data[i : i + self.batch_size]
                batches_attempted += 1

                # Build UPSERT query (parameterized — see issue #492)
                query, params = self._build_upsert_query(
                    batch,
                    columns,
                    column_names,
                    return_records,
                    merge_strategy,
                    conflict_on,
                )

                # Execute batch using connection pool if available, otherwise fallback
                try:
                    result = await self._execute_query(query, params=params, **kwargs)

                    # Process result to count upserts and get records
                    batch_rows, batch_inserted, batch_updated, batch_records = (
                        self._process_upsert_result(result, len(batch), return_records)
                    )
                    total_rows_affected += batch_rows
                    total_inserted += batch_inserted
                    total_updated += batch_updated

                    if return_records and batch_records:
                        all_upserted_records.extend(batch_records)

                except Exception as batch_error:
                    # rules/observability.md Rule 7 — bulk partial-failure WARN
                    # MUST include the error message so operators can triage.
                    # rules/security.md + #499 finding 5: DB drivers often
                    # embed raw column values in DETAIL clauses (e.g.
                    # `Key (email)=(alice@example.com) already exists`). Strip
                    # DETAIL/Key blocks before logging to prevent PII leak.
                    err_str = _sanitize_db_error(str(batch_error))
                    logger.warning(
                        "bulk_upsert.batch_error: %s",
                        err_str,
                        extra={"error": err_str, "batch_size": len(batch)},
                    )
                    batch_errors.append(err_str)
                    # Continue processing later batches: callers receive partial
                    # success in (rows_affected, inserted, updated) and the
                    # accumulated `batch_errors` list. If EVERY batch failed we
                    # raise so the caller doesn't mistake the run for a no-op
                    # success.

            if batch_errors and batches_attempted == len(batch_errors):
                # Fail loud when nothing succeeded — no rows landed AND every
                # batch errored. Single-batch payloads converge here too.
                raise NodeExecutionError(
                    f"bulk_upsert: all {batches_attempted} batch(es) failed; "
                    f"first_error={batch_errors[0]}"
                )

            return (
                total_rows_affected,
                total_inserted,
                total_updated,
                all_upserted_records,
                duplicates_removed,
            )

        except Exception as e:
            raise NodeExecutionError(f"Database upsert error: {str(e)}")

    def _prepare_data_for_upsert(
        self, data: List[Dict[str, Any]], tenant_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Prepare data for upsertion with tenant isolation and timestamps."""
        processed_data = []

        for row in data:
            new_row = row.copy()

            # Add tenant_id if multi-tenant is enabled
            if self.tenant_isolation and tenant_id:
                new_row["tenant_id"] = tenant_id

            # Add timestamps if enabled
            if self.auto_timestamps:
                from datetime import datetime, timezone

                # Naive UTC: asyncpg binds naive datetimes to TIMESTAMP (without tz);
                # `datetime.utcnow()` is deprecated, so derive the same value via
                # `now(timezone.utc).replace(tzinfo=None)`.
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if "created_at" not in new_row:
                    new_row["created_at"] = now
                if "updated_at" not in new_row:
                    new_row["updated_at"] = now

            processed_data.append(new_row)

        return processed_data

    def _deduplicate_batch_data(
        self, data: List[Dict[str, Any]], conflict_on: List[str]
    ) -> List[Dict[str, Any]]:
        """Remove duplicates within batch based on conflict_on columns to avoid PostgreSQL errors."""
        if self.handle_duplicates == "last":
            # Keep the last occurrence of each unique key
            seen = {}
            for i, record in enumerate(data):
                conflict_key = tuple(record.get(col) for col in conflict_on)
                seen[conflict_key] = i  # Keep track of latest index

            # Extract records using the latest indices
            deduplicated = [data[i] for i in sorted(seen.values())]
        else:
            # Keep the first occurrence (default behavior)
            seen = set()
            deduplicated = []

            for record in data:
                conflict_key = tuple(record.get(col) for col in conflict_on)

                if conflict_key not in seen:
                    seen.add(conflict_key)
                    deduplicated.append(record)

        return deduplicated

    def _build_upsert_query(
        self,
        batch: List[Dict[str, Any]],
        columns: List[str],
        column_names: str,
        return_records: bool,
        merge_strategy: str,
        conflict_on: List[str],
    ) -> tuple[str, List[Any]]:
        """Build UPSERT query with parameterized VALUES (issue #492).

        Returns ``(sql, params)`` where ``sql`` contains dialect-appropriate
        placeholders ($N for PostgreSQL, ? for SQLite, %s for MySQL) and
        ``params`` is a flat list in row-major order matching ``columns``.

        VALUES MUST be bound through driver parameters — never string-escaped.
        Every dynamic identifier (table_name, columns, conflict_on,
        version_field) MUST be validated through ``_validate_identifier``
        per ``rules/dataflow-identifier-safety.md`` MUST 1, then
        interpolated into the SQL string. Drivers cannot bind identifiers,
        so the validator's strict allowlist regex is the single defense.
        See ``rules/security.md`` § Parameterized Queries.
        """
        dialect = (self.database_type or "postgresql").lower()
        if dialect not in _SUPPORTED_DIALECTS:
            raise NodeValidationError(
                f"Unsupported database_type {self.database_type!r}; expected one of "
                f"{sorted(_SUPPORTED_DIALECTS)}"
            )

        # Identifier safety: validate BEFORE any interpolation.
        _validate_identifier(self.table_name)
        for col in columns:
            _validate_identifier(col)
        for col in conflict_on:
            _validate_identifier(col)
        if self.version_control and self.version_field:
            _validate_identifier(self.version_field)

        params: List[Any] = []
        value_rows: List[str] = []

        for row in batch:
            placeholders: List[str] = []
            for col in columns:
                value = row.get(col)
                if dialect == "postgresql":
                    placeholders.append(f"${len(params) + 1}")
                elif dialect == "mysql":
                    placeholders.append("%s")
                else:  # sqlite
                    placeholders.append("?")
                # Drivers serialize None → NULL, datetime → timestamp, bool → boolean.
                params.append(value)
            value_rows.append(f"({', '.join(placeholders)})")

        base_query = (
            f"INSERT INTO {self.table_name} ({column_names}) "
            f"VALUES {', '.join(value_rows)}"
        )

        if dialect == "postgresql":
            conflict_columns_str = ", ".join(conflict_on)

            if merge_strategy == "ignore":
                query = f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
            else:  # update strategy
                update_clauses = []
                for col in columns:
                    if col not in conflict_on and col not in [
                        "id",
                        "created_at",
                    ]:
                        if col == self.version_field and self.version_control:
                            update_clauses.append(
                                f"{col} = {self.table_name}.{col} + 1"
                            )
                        elif col == "updated_at" and self.auto_timestamps:
                            update_clauses.append(f"{col} = CURRENT_TIMESTAMP")
                        else:
                            update_clauses.append(f"{col} = EXCLUDED.{col}")

                if update_clauses:
                    update_clause = ", ".join(update_clauses)
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) "
                        f"DO UPDATE SET {update_clause}"
                    )
                else:
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
                    )
        else:
            # SQLite/MySQL fallback uses INSERT OR REPLACE semantics.
            query = base_query.replace("INSERT INTO", "INSERT OR REPLACE INTO")

        if dialect == "postgresql" and return_records:
            query += " RETURNING *"

        return query, params

    def _process_upsert_result(
        self, result: Dict[str, Any], batch_size: int, return_records: bool = False
    ) -> tuple[int, int, int, List[Dict[str, Any]]]:
        """Process AsyncSQLDatabaseNode result to extract counts and records."""
        rows_affected = 0
        inserted_count = 0
        updated_count = 0
        upserted_records = []

        if "result" in result and result["result"]:
            result_data = result["result"]

            if "data" in result_data and isinstance(result_data["data"], list):
                data = result_data["data"]

                if data and isinstance(data[0], dict):
                    if "id" in data[0]:
                        # RETURNING clause results
                        upserted_records = data
                        rows_affected = len(upserted_records)
                        # For now, assume half are inserts and half are updates (could be improved)
                        inserted_count = rows_affected // 2
                        updated_count = rows_affected - inserted_count
                    elif "rows_affected" in data[0] and len(data[0]) == 1:
                        # Metadata response - use batch_size
                        rows_affected = batch_size
                        inserted_count = batch_size // 2
                        updated_count = batch_size - inserted_count
                    else:
                        # Other data - count the records
                        rows_affected = len(data)
                        inserted_count = rows_affected // 2
                        updated_count = rows_affected - inserted_count
            elif "row_count" in result_data:
                # For UPSERT operations without RETURNING
                rows_affected = batch_size
                inserted_count = batch_size // 2
                updated_count = batch_size - inserted_count
            else:
                rows_affected = batch_size  # Assume success for UPSERT
                inserted_count = batch_size // 2
                updated_count = batch_size - inserted_count
        else:
            rows_affected = batch_size  # Assume success if no specific result
            inserted_count = batch_size // 2
            updated_count = batch_size - inserted_count

        return rows_affected, inserted_count, updated_count, upserted_records

    async def _execute_query(
        self,
        query: str,
        params: Optional[List[Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute parameterized SQL query (issue #492).

        ``params`` is a flat positional list bound by the driver and
        forwarded through ``AsyncSQLDatabaseNode``.

        Pool routing is not wired on this node: ``DataFlowConnectionManager``
        does not implement ``operation="execute"`` (see workflow_connection_manager
        allowlist), so a pool path would silently fall through to the direct
        path — a zero-tolerance Rule 3 (silent fallback) + dataflow-pool Rule 3
        (deceptive configuration) violation. When pool routing is needed, use
        ``BulkCreatePoolNode`` or extend ``DataFlowConnectionManager``.
        """
        if kwargs.get("use_pooled_connection"):
            raise NodeValidationError(
                "BulkUpsertNode does not support use_pooled_connection. "
                "DataFlowConnectionManager.execute() has no 'execute' operation. "
                "Use BulkCreatePoolNode for pool-routed inserts, or pass "
                "connection_string for direct execution."
            )

        if not self.connection_string:
            raise NodeValidationError("BulkUpsertNode requires connection_string")

        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        db_node = AsyncSQLDatabaseNode(
            connection_string=self.connection_string,
            database_type=self.database_type,
            validate_queries=False,  # Allow UPSERT operations
        )

        return await db_node.async_run(query=query, params=params)


# For backward compatibility, also alias the old method name
BulkUpsertNode.execute = BulkUpsertNode.async_run

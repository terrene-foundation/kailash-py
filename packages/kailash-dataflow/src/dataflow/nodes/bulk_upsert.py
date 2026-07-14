"""DataFlow Bulk Upsert Node - SDK Compliant Implementation."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from kailash.db.dialect import _validate_identifier
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

# #499 finding 5 / #1519 — PG/MySQL drivers embed raw column values in DETAIL /
# Key(...)=(…) clauses. Strip them before any log or return-value echo so
# PII / SECRET column values cannot leak through the observability layer.
# The redactor is a single shared helper in ``core.exceptions`` so this node
# and the express bulk engine (``features/bulk.py``) scrub identically — one
# implementation, no drift (rules/security.md § Multi-Site Kwarg Plumbing).
from ..core.exceptions import (  # Issue #1519: typed conflict-target error
    BulkUpsertConflictTargetError,
    is_conflict_target_error,
)
from ..core.exceptions import sanitize_db_error as _sanitize_db_error

# Allowlist of supported dialects. Unknown values (typos like "postgres",
# "pg") MUST raise loudly rather than fall through to SQLite REPLACE
# semantics, which masks misconfiguration as a non-fatal SQL syntax error
# at execution time. See `rules/dataflow-identifier-safety.md`.
_SUPPORTED_DIALECTS = frozenset({"postgresql", "mysql", "sqlite"})

from .workflow_connection_manager import SmartNodeConnectionMixin


@register_node(alias="DataFlowBulkUpsertNode")
class DataFlowBulkUpsertNode(SmartNodeConnectionMixin, AsyncNode):
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
        """Initialize the DataFlowBulkUpsertNode with configuration parameters."""
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
            raise NodeValidationError(
                "table_name is required for DataFlowBulkUpsertNode"
            )

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
        # #1585: if this node runs inside a TransactionScopeNode, the upsert MUST
        # join the scope's connection so a rollback discards it. The scope's
        # asyncpg connection is bound to the runtime's event loop, but
        # _execute_with_connection resolves the coroutine via async_safe_run(),
        # which runs it on a SEPARATE loop/thread — a borrowed connection cannot
        # cross that boundary. So when a scope is active, await _perform_bulk_upsert
        # DIRECTLY on the runtime loop (where the borrowed connection lives) and
        # thread the borrowed transaction through to the fresh execution node.
        # Fail-closed if the scope exposes no `.transaction` handle.
        from ..core.nodes import _resolve_scope_transaction

        scope_txn = _resolve_scope_transaction(self)
        if scope_txn is not None:
            return await self._perform_bulk_upsert(
                _scope_transaction=scope_txn, **kwargs
            )

        # No scope: preserve the prior sync/async_safe_run execution path.
        # _execute_with_connection is synchronous: when operation_func is a
        # coroutine function it internally resolves via async_safe_run() and
        # returns the already-resolved dict result. The value is NOT awaitable.
        return self._execute_with_connection(self._perform_bulk_upsert, **kwargs)

    async def _perform_bulk_upsert(
        self, _scope_transaction: Optional[Any] = None, **kwargs
    ) -> dict[str, Any]:
        """Perform the actual bulk upsert operation.

        #1585: ``_scope_transaction`` is a borrowed adapter txn handle from an
        active ``TransactionScopeNode`` (threaded from ``async_run`` when a scope
        is present). It is forwarded to ``_execute_real_bulk_upsert`` →
        ``_execute_query`` so every UPSERT runs ON the scope's connection.
        """
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

            # #1585 fail-closed (symmetric with BulkCreatePoolNode): a standalone
            # upsert inside a TransactionScopeNode with no connection_string cannot
            # join the scope. Falling through to the dry-run-shaped else branch
            # below would report fabricated success (rows_affected=len(data)) while
            # writing nothing AND discarding the borrowed handle — the caller would
            # believe the upsert persisted inside the scope. Refuse rather than
            # silently no-op (the _execute_query guard fires too late; the else
            # branch short-circuits before any query runs).
            if (
                _scope_transaction is not None
                and not self.connection_string
                and not dry_run
            ):
                raise NodeExecutionError(
                    "DataFlowBulkUpsertNode is inside a TransactionScopeNode but "
                    "has no connection_string to join the scope's connection "
                    "(#1585). Provide connection_string, or use the generated "
                    "'<Model>BulkUpsertNode' / db.express.bulk_upsert which are "
                    "scope-aware."
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
                    _scope_transaction=_scope_transaction,  # #1585: join active scope
                    **kwargs_copy,
                )
            else:
                # Dry run: nothing is written, so no honest insert/update split
                # exists (issue #1519 — no fabricated `// 2`). ``would_upsert``
                # below reports the row count that WOULD be affected.
                rows_affected = len(data)
                inserted_count = 0
                updated_count = 0
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

        except (
            ValueError,
            NodeValidationError,
            NodeExecutionError,
            BulkUpsertConflictTargetError,
        ):
            # Issue #1519: a conflict-target error is a caller error, not a
            # transient DB failure — surface it as a typed raise (like ValueError
            # / NodeValidationError) instead of flattening it into a
            # {"success": False} dict a caller might treat as a soft outcome.
            # #1585: NodeExecutionError (the fail-closed scope guard above) is
            # likewise a caller/config error and MUST propagate as a raise, not be
            # flattened — a refused scope-join must be loud, matching the sibling
            # BulkCreatePoolNode's fail-closed raise.
            raise
        except Exception as e:
            # Issue #1552 (FIX 6 sweep): DataFlowBulkUpsertNode runs real upserts;
            # a constraint violation carries DETAIL: Key(col)=(value). Sanitize the
            # returned-dict error (mirrors the already-sanitized batch path at L410).
            return {
                "success": False,
                "error": _sanitize_db_error(str(e)),
                "rows_affected": 0,
            }

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
        _scope_transaction: Optional[Any] = None,
        **kwargs,
    ) -> tuple[int, int, int, List[Dict[str, Any]], int]:
        """Execute real bulk upsert using database connection.

        #1585: ``_scope_transaction`` (a borrowed adapter txn handle) is forwarded
        to every ``_execute_query`` call so the UPSERT runs ON the scope's
        connection and joins an active ``TransactionScopeNode``.
        """
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

            # Issue #1546: resolve the MySQL row-alias upsert form ONCE before the
            # batch loop. This node has no DataFlow instance (only connection_string
            # + database_type), so it version-probes via its own AsyncSQLDatabaseNode
            # through the shared process-cached helper — one SELECT VERSION() per
            # server per process. ``VALUES(col)`` is deprecated on MySQL 8.0.20+.
            mysql_use_row_alias = False
            if (self.database_type or "").lower() == "mysql" and self.connection_string:
                from dataflow.sql.dialects import (
                    mysql_row_alias_cache_key,
                    mysql_row_alias_support_cached,
                    resolve_mysql_row_alias_support,
                )

                _key = mysql_row_alias_cache_key(self.connection_string)
                _cached = mysql_row_alias_support_cached(_key)
                if _cached is not None:
                    mysql_use_row_alias = _cached
                else:
                    # Cache miss: probe via a throwaway node, then clean it up so no
                    # unclosed connection leaks a ResourceWarning.
                    _version_node = AsyncSQLDatabaseNode(
                        connection_string=self.connection_string,
                        database_type=self.database_type,
                        validate_queries=False,
                    )
                    try:
                        mysql_use_row_alias = await resolve_mysql_row_alias_support(
                            _version_node, _key
                        )
                    finally:
                        await _version_node.cleanup()

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
                    use_row_alias=mysql_use_row_alias,  # #1546
                )

                # Execute batch using connection pool if available, otherwise fallback
                try:
                    # Issue #1519: derive REAL insert/update counts from a
                    # pre-count of existing conflict-target keys (no fabricated
                    # `// 2`). The batch is already deduped on conflict_on, so
                    # each matching pre-existing key is exactly one UPDATE.
                    preexisting = await self._count_existing_conflicts(
                        batch,
                        conflict_on,
                        transaction=_scope_transaction,  # #1585: count on scope conn
                        **kwargs,
                    )
                    result = await self._execute_query(
                        query,
                        params=params,
                        transaction=_scope_transaction,  # #1585: join active scope
                        **kwargs,
                    )

                    # Process result to count upserts and get records
                    batch_rows, batch_inserted, batch_updated, batch_records = (
                        self._process_upsert_result(
                            result,
                            len(batch),
                            return_records,
                            merge_strategy,
                            preexisting,
                        )
                    )
                    total_rows_affected += batch_rows
                    total_inserted += batch_inserted
                    total_updated += batch_updated

                    if return_records and batch_records:
                        all_upserted_records.extend(batch_records)

                except BulkUpsertConflictTargetError:
                    # Issue #1519: an unmatched ON CONFLICT target is a caller
                    # error affecting EVERY batch — fail fast, don't accumulate
                    # it as a per-batch partial failure.
                    raise
                except Exception as batch_error:
                    if is_conflict_target_error(str(batch_error)):
                        raise BulkUpsertConflictTargetError(
                            conflict_on=conflict_on,
                            model_name=self.table_name,
                            original_error=batch_error,
                        ) from batch_error
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

        except BulkUpsertConflictTargetError:
            # Issue #1519: caller-actionable typed error MUST propagate as-is,
            # not be re-wrapped in a generic NodeExecutionError.
            raise
        except Exception as e:
            # Issue #1552 (FIX 6 sweep): sanitize the raised NodeExecutionError
            # message; `from e` preserves the raw exception as __cause__ for local
            # traceback diagnosability (mirrors #1550 / FIX 11).
            raise NodeExecutionError(
                f"Database upsert error: {_sanitize_db_error(str(e))}"
            ) from e

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
        use_row_alias: bool = False,
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
        # Issue #1546: declare the row alias on the INSERT (MySQL 8.0.19+ only).
        # Built from the SAME use_row_alias flag as the ODKU references below.
        mysql_alias_decl = " AS new_row" if use_row_alias else ""

        conflict_columns_str = ", ".join(conflict_on)

        # Cross-tenant WRITE breach fix (rules/tenant-isolation.md): a
        # tenant-scoped DO-UPDATE guard for multi_tenant models. tenant_id is
        # stamped into the batch upstream (``_prepare_data_for_upsert`` when
        # ``tenant_isolation`` is on), so it rides in ``columns``; the WHERE
        # (PG/SQLite) / IF() (MySQL, in _build_update_clauses) fires only when
        # the existing row belongs to the SAME tenant — a cross-tenant ``id``
        # collision leaves the row untouched (no theft, no tenant_id flip).
        tenant_guard = bool(self.tenant_isolation) and "tenant_id" in columns
        tenant_where = (
            f" WHERE {self.table_name}.tenant_id = excluded.tenant_id"
            if tenant_guard
            else ""
        )

        if dialect == "postgresql":
            if merge_strategy == "ignore":
                query = f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
            else:  # update strategy
                update_clauses = self._build_update_clauses(
                    columns, conflict_on, tenant_guard=tenant_guard
                )
                if update_clauses:
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) "
                        f"DO UPDATE SET {', '.join(update_clauses)}{tenant_where}"
                    )
                else:
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
                    )
            if return_records:
                query += " RETURNING *"
        elif dialect == "sqlite":
            # Issue #1519: SQLite honors conflict_on via native ON CONFLICT
            # (NOT INSERT OR REPLACE, which ignores conflict_on and replaces the
            # whole row, discarding un-supplied columns + firing FK cascades).
            if merge_strategy == "ignore":
                query = f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
            else:
                update_clauses = self._build_update_clauses(
                    columns, conflict_on, sqlite=True, tenant_guard=tenant_guard
                )
                if update_clauses:
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) "
                        f"DO UPDATE SET {', '.join(update_clauses)}{tenant_where}"
                    )
                else:
                    query = (
                        f"{base_query} ON CONFLICT ({conflict_columns_str}) DO NOTHING"
                    )
            if return_records:
                query += " RETURNING *"
        else:  # mysql
            # Issue #1519: MySQL uses ON DUPLICATE KEY UPDATE (INSERT OR REPLACE
            # is not valid MySQL syntax). MySQL auto-detects the violated unique
            # key, so conflict_on governs only which columns are excluded.
            # Issue #1546: mysql_alias_decl declares the row alias on the INSERT
            # when use_row_alias is set; the ODKU references match via
            # _build_update_clauses(use_row_alias=...). The noop self-assignment
            # references a table column, valid in both forms.
            if merge_strategy == "ignore":
                noop = conflict_on[0] if conflict_on else "id"
                query = (
                    f"{base_query}{mysql_alias_decl} "
                    f"ON DUPLICATE KEY UPDATE {noop} = {noop}"
                )
            else:
                update_clauses = self._build_update_clauses(
                    columns,
                    conflict_on,
                    mysql=True,
                    use_row_alias=use_row_alias,
                    tenant_guard=tenant_guard,
                )
                if update_clauses:
                    query = (
                        f"{base_query}{mysql_alias_decl} ON DUPLICATE KEY UPDATE "
                        f"{', '.join(update_clauses)}"
                    )
                else:
                    noop = conflict_on[0] if conflict_on else "id"
                    query = (
                        f"{base_query}{mysql_alias_decl} "
                        f"ON DUPLICATE KEY UPDATE {noop} = {noop}"
                    )

        return query, params

    def _build_update_clauses(
        self,
        columns: List[str],
        conflict_on: List[str],
        *,
        sqlite: bool = False,
        mysql: bool = False,
        use_row_alias: bool = False,
        tenant_guard: bool = False,
    ) -> List[str]:
        """Build the SET clauses for a DO UPDATE / ON DUPLICATE KEY UPDATE.

        Excludes conflict-target columns and the immutable ``id`` / ``created_at``
        columns. ``version_field`` increments; ``updated_at`` uses
        ``CURRENT_TIMESTAMP``; everything else copies the incoming value with the
        dialect-appropriate reference (``EXCLUDED.col`` on PG/SQLite,
        ``VALUES(col)`` on MySQL).

        Issue #1546: ``VALUES(col)`` is deprecated on MySQL 8.0.20+. When
        ``use_row_alias`` is True (MySQL >= 8.0.19, non-MariaDB) the MySQL branch
        references the INSERT row alias (``new_row.col``) instead. The alias is
        declared on the INSERT in ``_build_upsert_query`` — the two halves are set
        from the SAME ``use_row_alias`` flag so they cannot drift.

        Cross-tenant WRITE breach fix (``tenant_guard``, multi_tenant models):
        ``tenant_id`` is excluded from the SET (an upsert never re-owns a row),
        and the MySQL branch wraps each column in
        ``col = IF(tenant_id = <new_tenant>, <new>, col)`` (MySQL ODKU has no
        WHERE). PG/SQLite carry the ``WHERE {table}.tenant_id = excluded.tenant_id``
        guard in ``_build_upsert_query`` (rules/tenant-isolation.md).
        """

        def _new_ref(c: str) -> str:
            if mysql:
                return f"new_row.{c}" if use_row_alias else f"VALUES({c})"
            ref = "excluded" if sqlite else "EXCLUDED"
            return f"{ref}.{c}"

        clauses: List[str] = []
        for col in columns:
            if col in conflict_on or col in ("id", "created_at"):
                continue
            if tenant_guard and col == "tenant_id":
                continue  # never re-assign the owning tenant
            if col == self.version_field and self.version_control:
                if mysql and tenant_guard:
                    # PG/SQLite gate the version bump via the DO-UPDATE WHERE;
                    # MySQL's ODKU has no WHERE, so guard the optimistic-lock
                    # increment too — a cross-tenant id collision must NOT bump
                    # the victim tenant's version counter.
                    clauses.append(
                        f"{col} = IF(tenant_id = {_new_ref('tenant_id')}, "
                        f"{self.table_name}.{col} + 1, {col})"
                    )
                else:
                    clauses.append(f"{col} = {self.table_name}.{col} + 1")
            elif col == "updated_at" and self.auto_timestamps:
                if mysql and tenant_guard:
                    # PG/SQLite gate updated_at via the DO-UPDATE WHERE; MySQL's
                    # ODKU has no WHERE, so guard the timestamp bump too.
                    clauses.append(
                        f"{col} = IF(tenant_id = {_new_ref('tenant_id')}, "
                        f"CURRENT_TIMESTAMP, {col})"
                    )
                else:
                    clauses.append(f"{col} = CURRENT_TIMESTAMP")
            elif mysql and tenant_guard:
                # ODKU has no WHERE — guard each SET with the tenant IF().
                clauses.append(
                    f"{col} = IF(tenant_id = {_new_ref('tenant_id')}, "
                    f"{_new_ref(col)}, {col})"
                )
            else:
                clauses.append(f"{col} = {_new_ref(col)}")
        return clauses

    def _process_upsert_result(
        self,
        result: Dict[str, Any],
        batch_size: int,
        return_records: bool,
        merge_strategy: str,
        preexisting_count: int,
    ) -> tuple[int, int, int, List[Dict[str, Any]]]:
        """Process AsyncSQLDatabaseNode result to extract counts and records.

        Issue #1519: counts are DERIVED, not fabricated. The batch is deduped on
        conflict_on, so ``preexisting_count`` (rows whose conflict key already
        exists) IS the number of UPDATEs. There is no ``// 2`` heuristic.

        - ``update`` strategy: every batch row is inserted OR updated →
          updated = preexisting, inserted = batch_size - preexisting,
          rows_affected = batch_size.
        - ``ignore`` strategy: only new rows land →
          inserted = batch_size - preexisting, updated = 0,
          rows_affected = inserted.
        """
        upserted_records: List[Dict[str, Any]] = []
        if return_records and "result" in result and result["result"]:
            result_data = result["result"]
            data = result_data.get("data")
            if (
                isinstance(data, list)
                and data
                and isinstance(data[0], dict)
                and ("id" in data[0] or len(data[0]) > 1)
            ):
                upserted_records = data

        preexisting = max(0, min(preexisting_count, batch_size))
        if merge_strategy == "ignore":
            inserted_count = batch_size - preexisting
            updated_count = 0
            rows_affected = inserted_count
        else:  # update
            updated_count = preexisting
            inserted_count = batch_size - preexisting
            rows_affected = batch_size

        return rows_affected, inserted_count, updated_count, upserted_records

    async def _count_existing_conflicts(
        self, batch: List[Dict[str, Any]], conflict_on: List[str], **kwargs
    ) -> int:
        """Count rows already present matching the batch's conflict-target keys.

        Issue #1519: gives the real UPDATE count without relying on a per-row
        insert/update flag (which SQLite's RETURNING cannot provide). Uses
        OR-of-AND equality with dialect-appropriate placeholders. NULL conflict
        values never match a UNIQUE target and are skipped. Every conflict
        column is validated (``_validate_identifier``) before interpolation.
        """
        dialect = (self.database_type or "postgresql").lower()
        for col in conflict_on:
            _validate_identifier(col)

        clauses: List[str] = []
        params: List[Any] = []
        for record in batch:
            vals = [record.get(col) for col in conflict_on]
            if any(v is None for v in vals):
                continue
            conds = []
            for col in conflict_on:
                if dialect == "postgresql":
                    conds.append(f"{col} = ${len(params) + 1}")
                elif dialect == "mysql":
                    conds.append(f"{col} = %s")
                else:  # sqlite
                    conds.append(f"{col} = ?")
                params.append(record.get(col))
            clauses.append(f"({' AND '.join(conds)})")

        if not clauses:
            return 0

        query = (
            f"SELECT COUNT(*) AS match_count FROM {self.table_name} "
            f"WHERE {' OR '.join(clauses)}"
        )
        result = await self._execute_query(query, params=params, **kwargs)
        rows = []
        if result and "result" in result and result["result"]:
            rows = result["result"].get("data", []) or []
        if rows and isinstance(rows[0], dict):
            value = (
                rows[0].get("match_count")
                or rows[0].get("COUNT(*)")
                or rows[0].get("count")
                or 0
            )
            return int(value)
        return 0

    async def _execute_query(
        self,
        query: str,
        params: Optional[List[Any]] = None,
        transaction: Optional[Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute parameterized SQL query (issue #492).

        #1585: ``transaction`` is a borrowed adapter txn handle ``(conn, tx)`` from
        an active ``TransactionScopeNode``. When present the fresh execution node
        runs ON that connection (joins the scope); ``None`` = auto-commit.

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
                "DataFlowBulkUpsertNode does not support use_pooled_connection. "
                "DataFlowConnectionManager.execute() has no 'execute' operation. "
                "Use BulkCreatePoolNode for pool-routed inserts, or pass "
                "connection_string for direct execution."
            )

        if not self.connection_string:
            raise NodeValidationError(
                "DataFlowBulkUpsertNode requires connection_string"
            )

        from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

        from ..core.credential_provider import get_active_credential_provider

        db_node = AsyncSQLDatabaseNode(
            connection_string=self.connection_string,
            database_type=self.database_type,
            validate_queries=False,  # Allow UPSERT operations
            # Issue #1741: this standalone workflow node holds no DataFlow
            # instance, so token-based DB auth arrives via the context-scoped
            # provider (bound by ``credential_provider_scope`` around
            # runtime.execute); None = unchanged.
            credential_provider=get_active_credential_provider(),
        )

        # Each call creates a fresh (non-pooled) node; clean it up after the query
        # so its connection does not leak a ResourceWarning on GC. The result dict
        # is fully materialized by async_run, so cleanup after is safe.
        try:
            return await db_node.async_run(
                query=query, params=params, transaction=transaction
            )
        finally:
            await db_node.cleanup()


# For backward compatibility, also alias the old method name
DataFlowBulkUpsertNode.execute = DataFlowBulkUpsertNode.async_run

"""Bulk operations support for database nodes.

This module provides bulk CRUD operations for efficient data processing
in Kailash workflows. It extends the async SQL database capabilities
with optimized bulk operations for different databases.

Key Features:
- Database-specific bulk optimizations
- Chunking for large datasets
- Progress tracking and reporting
- Configurable error handling strategies
- Type validation for bulk data
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, DatabaseType
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

# Import List and Dict types if not already present
if "List" not in globals():
    from typing import List
if "Dict" not in globals():
    from typing import Dict

logger = logging.getLogger(__name__)


class BulkErrorStrategy(Enum):
    """Error handling strategies for bulk operations."""

    FAIL_FAST = "fail_fast"  # Stop on first error
    CONTINUE = "continue"  # Continue processing, collect errors
    ROLLBACK = "rollback"  # Rollback entire operation on any error


@dataclass
class BulkOperationResult:
    """Result of a bulk operation."""

    total_records: int
    successful_records: int
    failed_records: int
    errors: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_records == 0:
            return 0.0
        return (self.successful_records / self.total_records) * 100


class BulkOperationMixin:
    """Mixin for bulk operations support."""

    def setup_bulk_operations(self, config: Dict[str, Any]):
        """Setup bulk operation configuration."""
        self.chunk_size: int = config.get("chunk_size", 1000)
        self.error_strategy: BulkErrorStrategy = BulkErrorStrategy(
            config.get("error_strategy", "fail_fast")
        )
        self.report_progress: bool = config.get("report_progress", True)
        self.progress_interval: int = config.get("progress_interval", 100)

    def validate_bulk_data(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate records before bulk operation.

        Args:
            records: List of records to validate

        Returns:
            Validated records

        Raises:
            NodeValidationError: If validation fails
        """
        if not records:
            raise NodeValidationError("No records provided for bulk operation")

        if not isinstance(records, list):
            raise NodeValidationError("Records must be a list")

        # Validate each record is a dictionary
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                raise NodeValidationError(f"Record at index {i} must be a dictionary")

        return records

    def chunk_records(
        self, records: List[Dict[str, Any]], chunk_size: Optional[int] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Chunk large datasets for processing.

        Args:
            records: List of records to chunk
            chunk_size: Size of each chunk (defaults to self.chunk_size)

        Yields:
            Chunks of records
        """
        size = chunk_size or self.chunk_size
        for i in range(0, len(records), size):
            yield records[i : i + size]

    async def report_progress_async(self, current: int, total: int, operation: str):
        """Report progress of bulk operation.

        Args:
            current: Current record number
            total: Total number of records
            operation: Operation being performed
        """
        if self.report_progress and current % self.progress_interval == 0:
            percentage = (current / total) * 100 if total > 0 else 0
            logger.info(
                f"Bulk {operation} progress: {current}/{total} ({percentage:.1f}%)"
            )


@register_node()
class BulkCreateNode(AsyncSQLDatabaseNode, BulkOperationMixin):
    """Bulk insert operations with database-specific optimizations."""

    def __init__(self, **config):
        """Initialize bulk create node."""
        # Initialize parent class
        super().__init__(**config)

        # Setup bulk operations
        self.setup_bulk_operations(config)

        # Table and columns configuration
        self.table_name = config.get("table_name")
        self.columns = config.get("columns", [])
        self.returning_columns = config.get("returning_columns", ["id"])

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        params = super().get_parameters().copy()
        bulk_params = {
            "records": NodeParameter(
                name="records",
                type=list,
                description="List of records to insert",
                required=True,
            ),
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                description="Target table name",
                required=True,
            ),
            "columns": NodeParameter(
                name="columns",
                type=list,
                description="Column names (auto-detected if not provided)",
                required=False,
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                description="Number of records per chunk",
                required=False,
                default_value=1000,
            ),
            "error_strategy": NodeParameter(
                name="error_strategy",
                type=str,
                description="Error handling strategy: fail_fast, continue, rollback",
                required=False,
                default_value="fail_fast",
            ),
            "returning_columns": NodeParameter(
                name="returning_columns",
                type=list,
                description="Columns to return after insert",
                required=False,
                default_value=["id"],
            ),
        }
        params.update(bulk_params)
        # Remove query requirement for bulk operations
        if "query" in params:
            params["query"].required = False
        return params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute bulk insert operation."""
        start_time = datetime.now()

        # Get records from parameters
        records = kwargs.get("records", [])
        records = self.validate_bulk_data(records)

        # Auto-detect columns if not provided
        if not self.columns and records:
            self.columns = list(records[0].keys())

        # Use table name from kwargs if provided
        table_name = kwargs.get("table_name", self.table_name)
        if not table_name:
            raise NodeValidationError("table_name is required")
        self.table_name = table_name

        # Get adapter
        adapter = await self._get_adapter()

        # Determine database type for optimization
        db_type = DatabaseType(self.config.get("database_type", "postgresql").lower())

        result = BulkOperationResult(
            total_records=len(records), successful_records=0, failed_records=0
        )

        try:
            if db_type == DatabaseType.POSTGRESQL:
                await self._bulk_insert_postgresql(adapter, records, result)
            elif db_type == DatabaseType.MYSQL:
                await self._bulk_insert_mysql(adapter, records, result)
            else:
                await self._bulk_insert_generic(adapter, records, result)

        except Exception as e:
            if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                raise NodeExecutionError(f"Bulk insert failed: {str(e)}")
            else:
                result.errors.append({"error": str(e), "type": "general_error"})

        # Calculate execution time
        result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "status": "success" if result.failed_records == 0 else "partial_success",
            "total_records": result.total_records,
            "successful_records": result.successful_records,
            "failed_records": result.failed_records,
            "success_rate": result.success_rate,
            "execution_time_ms": result.execution_time_ms,
            "errors": (
                result.errors[:10] if result.errors else []
            ),  # Limit errors returned
        }

    async def _bulk_insert_postgresql(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """PostgreSQL-optimized bulk insert using COPY."""
        # For very large datasets, use COPY command
        if len(records) > 10000:
            # TODO: Implement COPY FROM for maximum performance
            # For now, fall back to multi-row INSERT
            pass

        # Use multi-row INSERT with RETURNING
        for chunk in self.chunk_records(records):
            try:
                # Build multi-row INSERT query
                placeholders = []
                values = []
                for i, record in enumerate(chunk):
                    row_placeholders = []
                    for col in self.columns:
                        param_num = i * len(self.columns) + self.columns.index(col) + 1
                        row_placeholders.append(f"${param_num}")
                        values.append(record.get(col))
                    placeholders.append(f"({', '.join(row_placeholders)})")

                query = f"""
                    INSERT INTO {self.table_name} ({', '.join(self.columns)})
                    VALUES {', '.join(placeholders)}
                    RETURNING {', '.join(self.returning_columns)}
                """

                rows = await adapter.fetch_all(query, *values)
                result.successful_records += len(chunk)

                # Report progress
                await self.report_progress_async(
                    result.successful_records, result.total_records, "insert"
                )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += len(chunk)
                result.errors.append(
                    {
                        "chunk_start": result.successful_records
                        + result.failed_records
                        - len(chunk),
                        "chunk_size": len(chunk),
                        "error": str(e),
                    }
                )

    async def _bulk_insert_mysql(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """MySQL-optimized bulk insert."""
        # MySQL supports multi-row INSERT efficiently
        for chunk in self.chunk_records(records):
            try:
                # Build multi-row INSERT query
                placeholders = []
                values = []
                for record in chunk:
                    row_placeholders = []
                    for col in self.columns:
                        row_placeholders.append("%s")
                        values.append(record.get(col))
                    placeholders.append(f"({', '.join(row_placeholders)})")

                query = f"""
                    INSERT INTO {self.table_name} ({', '.join(self.columns)})
                    VALUES {', '.join(placeholders)}
                """

                await adapter.execute(query, *values)
                result.successful_records += len(chunk)

                # Report progress
                await self.report_progress_async(
                    result.successful_records, result.total_records, "insert"
                )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += len(chunk)
                result.errors.append(
                    {
                        "chunk_start": result.successful_records
                        + result.failed_records
                        - len(chunk),
                        "chunk_size": len(chunk),
                        "error": str(e),
                    }
                )

    async def _bulk_insert_generic(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """Generic bulk insert for other databases."""
        # Fall back to individual inserts for SQLite and others
        for i, record in enumerate(records):
            try:
                placeholders = ", ".join(["?" for _ in self.columns])
                values = [record.get(col) for col in self.columns]

                query = f"""
                    INSERT INTO {self.table_name} ({', '.join(self.columns)})
                    VALUES ({placeholders})
                """

                await adapter.execute(query, *values)
                result.successful_records += 1

                # Report progress
                if (i + 1) % self.progress_interval == 0:
                    await self.report_progress_async(
                        i + 1, result.total_records, "insert"
                    )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += 1
                result.errors.append({"record_index": i, "error": str(e)})


@register_node()
class BulkUpdateNode(AsyncSQLDatabaseNode, BulkOperationMixin):
    """Bulk update operations with efficient strategies."""

    def __init__(self, **config):
        """Initialize bulk update node."""
        super().__init__(**config)

        # Setup bulk operations
        self.setup_bulk_operations(config)

        # Configuration
        self.table_name = config.get("table_name")
        self.update_strategy = config.get(
            "update_strategy", "case"
        )  # case, temp_table, individual

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        params = super().get_parameters().copy()
        bulk_params = {
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                description="Target table name",
                required=True,
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                description="Filter conditions for records to update",
                required=False,
            ),
            "updates": NodeParameter(
                name="updates",
                type=dict,
                description="Update values or expressions",
                required=True,
            ),
            "update_strategy": NodeParameter(
                name="update_strategy",
                type=str,
                description="Update strategy: case, temp_table, individual",
                required=False,
                default_value="case",
            ),
        }
        params.update(bulk_params)
        # Remove query requirement for bulk operations
        if "query" in params:
            params["query"].required = False
        return params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute bulk update operation."""
        start_time = datetime.now()

        # Get parameters
        table_name = kwargs.get("table_name", self.table_name)
        filter_conditions = kwargs.get("filter", {})
        updates = kwargs.get("updates", {})

        if not updates:
            raise NodeValidationError("No update values provided")

        # Get adapter
        adapter = await self._get_adapter()

        result = BulkOperationResult(
            total_records=0, successful_records=0, failed_records=0
        )

        try:
            # Build and execute update query
            query, params = self._build_update_query(
                table_name, filter_conditions, updates
            )

            # Execute update
            affected_rows = await adapter.execute(query, *params)
            result.successful_records = affected_rows
            result.total_records = affected_rows

        except Exception as e:
            if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                raise NodeExecutionError(f"Bulk update failed: {str(e)}")
            result.errors.append({"error": str(e), "type": "update_error"})

        # Calculate execution time
        result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "status": "success" if result.failed_records == 0 else "failed",
            "updated_count": result.successful_records,
            "execution_time_ms": result.execution_time_ms,
            "errors": result.errors,
        }

    def _build_update_query(
        self, table_name: str, filter_conditions: Dict, updates: Dict
    ) -> Tuple[str, List]:
        """Build UPDATE query with parameters."""
        # Build SET clause
        set_clauses = []
        params = []
        param_count = 1

        for column, value in updates.items():
            if isinstance(value, str) and any(
                op in value for op in ["+", "-", "*", "/"]
            ):
                # Expression (e.g., "stock - 1")
                set_clauses.append(f"{column} = {value}")
            else:
                # Direct value
                set_clauses.append(f"{column} = ${param_count}")
                params.append(value)
                param_count += 1

        # Build WHERE clause from filter
        where_clauses = []
        for column, condition in filter_conditions.items():
            if isinstance(condition, dict):
                # Complex condition (e.g., {"$gte": 100})
                for op, value in condition.items():
                    sql_op = self._get_sql_operator(op)
                    where_clauses.append(f"{column} {sql_op} ${param_count}")
                    params.append(value)
                    param_count += 1
            else:
                # Simple equality
                where_clauses.append(f"{column} = ${param_count}")
                params.append(condition)
                param_count += 1

        # Build final query
        query = f"UPDATE {table_name} SET {', '.join(set_clauses)}"
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"

        return query, params

    def _get_sql_operator(self, mongo_op: str) -> str:
        """Convert MongoDB-style operator to SQL."""
        operator_map = {
            "$eq": "=",
            "$ne": "!=",
            "$lt": "<",
            "$lte": "<=",
            "$gt": ">",
            "$gte": ">=",
            "$in": "IN",
            "$nin": "NOT IN",
        }
        return operator_map.get(mongo_op, "=")


@register_node()
class BulkDeleteNode(AsyncSQLDatabaseNode, BulkOperationMixin):
    """Bulk delete operations with safety checks."""

    def __init__(self, **config):
        """Initialize bulk delete node."""
        super().__init__(**config)

        # Setup bulk operations
        self.setup_bulk_operations(config)

        # Configuration
        self.table_name = config.get("table_name")
        self.soft_delete = config.get("soft_delete", False)
        self.require_filter = config.get("require_filter", True)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        params = super().get_parameters().copy()
        bulk_params = {
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                description="Target table name",
                required=True,
            ),
            "filter": NodeParameter(
                name="filter",
                type=dict,
                description="Filter conditions for records to delete",
                required=False,
            ),
            "soft_delete": NodeParameter(
                name="soft_delete",
                type=bool,
                description="Use soft delete (set deleted_at)",
                required=False,
                default_value=False,
            ),
            "require_filter": NodeParameter(
                name="require_filter",
                type=bool,
                description="Require filter to prevent accidental full table deletion",
                required=False,
                default_value=True,
            ),
        }
        params.update(bulk_params)
        # Remove query requirement for bulk operations
        if "query" in params:
            params["query"].required = False
        return params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute bulk delete operation."""
        start_time = datetime.now()

        # Get parameters
        table_name = kwargs.get("table_name", self.table_name)
        filter_conditions = kwargs.get("filter", {})

        # Safety check
        if self.require_filter and not filter_conditions:
            raise NodeValidationError(
                "Filter required for bulk delete. Set require_filter=False to delete all records."
            )

        # Get adapter
        adapter = await self._get_adapter()

        result = BulkOperationResult(
            total_records=0, successful_records=0, failed_records=0
        )

        try:
            if self.soft_delete:
                # Update with deleted_at timestamp
                query = f"UPDATE {table_name} SET deleted_at = CURRENT_TIMESTAMP"
            else:
                # Hard delete
                query = f"DELETE FROM {table_name}"

            # Add WHERE clause
            params = []
            if filter_conditions:
                where_clause, params = self._build_where_clause(filter_conditions)
                query += f" WHERE {where_clause}"

            # Execute delete
            affected_rows = await adapter.execute(query, *params)
            result.successful_records = affected_rows
            result.total_records = affected_rows

        except Exception as e:
            if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                raise NodeExecutionError(f"Bulk delete failed: {str(e)}")
            result.errors.append({"error": str(e), "type": "delete_error"})

        # Calculate execution time
        result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "status": "success" if result.failed_records == 0 else "failed",
            "deleted_count": result.successful_records,
            "soft_delete": self.soft_delete,
            "execution_time_ms": result.execution_time_ms,
            "errors": result.errors,
        }

    def _build_where_clause(self, filter_conditions: Dict) -> Tuple[str, List]:
        """Build WHERE clause from filter conditions."""
        where_clauses = []
        params = []
        param_count = 1

        for column, condition in filter_conditions.items():
            if isinstance(condition, dict):
                # Complex condition
                for op, value in condition.items():
                    sql_op = self._get_sql_operator(op)
                    if op in ["$in", "$nin"]:
                        placeholders = ", ".join(
                            [
                                f"${i}"
                                for i in range(param_count, param_count + len(value))
                            ]
                        )
                        where_clauses.append(f"{column} {sql_op} ({placeholders})")
                        params.extend(value)
                        param_count += len(value)
                    else:
                        where_clauses.append(f"{column} {sql_op} ${param_count}")
                        params.append(value)
                        param_count += 1
            else:
                # Simple equality
                where_clauses.append(f"{column} = ${param_count}")
                params.append(condition)
                param_count += 1

        return " AND ".join(where_clauses), params

    def _get_sql_operator(self, mongo_op: str) -> str:
        """Convert MongoDB-style operator to SQL."""
        operator_map = {
            "$eq": "=",
            "$ne": "!=",
            "$lt": "<",
            "$lte": "<=",
            "$gt": ">",
            "$gte": ">=",
            "$in": "IN",
            "$nin": "NOT IN",
        }
        return operator_map.get(mongo_op, "=")


@register_node()
class BulkUpsertNode(AsyncSQLDatabaseNode, BulkOperationMixin):
    """Bulk insert or update (upsert) operations."""

    def __init__(self, **config):
        """Initialize bulk upsert node."""
        super().__init__(**config)

        # Setup bulk operations
        self.setup_bulk_operations(config)

        # Configuration
        self.table_name = config.get("table_name")
        self.conflict_columns = config.get("conflict_columns", [])
        self.update_columns = config.get("update_columns", [])

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        params = super().get_parameters().copy()
        bulk_params = {
            "records": NodeParameter(
                name="records",
                type=list,
                description="List of records to upsert",
                required=True,
            ),
            "table_name": NodeParameter(
                name="table_name",
                type=str,
                description="Target table name",
                required=True,
            ),
            "conflict_columns": NodeParameter(
                name="conflict_columns",
                type=list,
                description="Columns that determine uniqueness",
                required=True,
            ),
            "update_columns": NodeParameter(
                name="update_columns",
                type=list,
                description="Columns to update on conflict",
                required=False,
            ),
        }
        params.update(bulk_params)
        # Remove query requirement for bulk operations
        if "query" in params:
            params["query"].required = False
        return params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute bulk upsert operation."""
        start_time = datetime.now()

        # Get parameters
        records = kwargs.get("records", [])
        records = self.validate_bulk_data(records)

        # Auto-detect columns
        if records:
            all_columns = list(records[0].keys())
            if not self.update_columns:
                # Update all columns except conflict columns
                self.update_columns = [
                    col for col in all_columns if col not in self.conflict_columns
                ]

        # Get adapter and database type
        adapter = await self._get_adapter()
        db_type = DatabaseType(self.config["database_type"].lower())

        result = BulkOperationResult(
            total_records=len(records), successful_records=0, failed_records=0
        )

        try:
            if db_type == DatabaseType.POSTGRESQL:
                await self._upsert_postgresql(adapter, records, result)
            elif db_type == DatabaseType.MYSQL:
                await self._upsert_mysql(adapter, records, result)
            else:
                # SQLite doesn't have native upsert, use INSERT OR REPLACE
                await self._upsert_sqlite(adapter, records, result)

        except Exception as e:
            if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                raise NodeExecutionError(f"Bulk upsert failed: {str(e)}")
            result.errors.append({"error": str(e), "type": "upsert_error"})

        # Calculate execution time
        result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "status": "success" if result.failed_records == 0 else "partial_success",
            "total_records": result.total_records,
            "successful_records": result.successful_records,
            "failed_records": result.failed_records,
            "success_rate": result.success_rate,
            "execution_time_ms": result.execution_time_ms,
            "errors": result.errors[:10] if result.errors else [],
        }

    async def _upsert_postgresql(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """PostgreSQL UPSERT using INSERT ... ON CONFLICT."""
        all_columns = list(records[0].keys()) if records else []

        for chunk in self.chunk_records(records):
            try:
                # Build INSERT ... ON CONFLICT query
                placeholders = []
                values = []
                for i, record in enumerate(chunk):
                    row_placeholders = []
                    for col in all_columns:
                        param_num = i * len(all_columns) + all_columns.index(col) + 1
                        row_placeholders.append(f"${param_num}")
                        values.append(record.get(col))
                    placeholders.append(f"({', '.join(row_placeholders)})")

                # Build update clause
                update_clauses = []
                for col in self.update_columns:
                    update_clauses.append(f"{col} = EXCLUDED.{col}")

                query = f"""
                    INSERT INTO {self.table_name} ({', '.join(all_columns)})
                    VALUES {', '.join(placeholders)}
                    ON CONFLICT ({', '.join(self.conflict_columns)})
                    DO UPDATE SET {', '.join(update_clauses)}
                """

                await adapter.execute(query, *values)
                result.successful_records += len(chunk)

                # Report progress
                await self.report_progress_async(
                    result.successful_records, result.total_records, "upsert"
                )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += len(chunk)
                result.errors.append(
                    {
                        "chunk_start": result.successful_records
                        + result.failed_records
                        - len(chunk),
                        "chunk_size": len(chunk),
                        "error": str(e),
                    }
                )

    async def _upsert_mysql(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """MySQL UPSERT using INSERT ... ON DUPLICATE KEY UPDATE."""
        all_columns = list(records[0].keys()) if records else []

        for chunk in self.chunk_records(records):
            try:
                # Build INSERT ... ON DUPLICATE KEY UPDATE query
                placeholders = []
                values = []
                for record in chunk:
                    row_placeholders = []
                    for col in all_columns:
                        row_placeholders.append("%s")
                        values.append(record.get(col))
                    placeholders.append(f"({', '.join(row_placeholders)})")

                # Build update clause
                update_clauses = []
                for col in self.update_columns:
                    update_clauses.append(f"{col} = VALUES({col})")

                query = f"""
                    INSERT INTO {self.table_name} ({', '.join(all_columns)})
                    VALUES {', '.join(placeholders)}
                    ON DUPLICATE KEY UPDATE {', '.join(update_clauses)}
                """

                await adapter.execute(query, *values)
                result.successful_records += len(chunk)

                # Report progress
                await self.report_progress_async(
                    result.successful_records, result.total_records, "upsert"
                )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += len(chunk)
                result.errors.append(
                    {
                        "chunk_start": result.successful_records
                        + result.failed_records
                        - len(chunk),
                        "chunk_size": len(chunk),
                        "error": str(e),
                    }
                )

    async def _upsert_sqlite(
        self, adapter, records: List[Dict], result: BulkOperationResult
    ):
        """SQLite UPSERT using INSERT OR REPLACE."""
        all_columns = list(records[0].keys()) if records else []

        for record in records:
            try:
                placeholders = ", ".join(["?" for _ in all_columns])
                values = [record.get(col) for col in all_columns]

                query = f"""
                    INSERT OR REPLACE INTO {self.table_name} ({', '.join(all_columns)})
                    VALUES ({placeholders})
                """

                await adapter.execute(query, *values)
                result.successful_records += 1

                # Report progress
                if result.successful_records % self.progress_interval == 0:
                    await self.report_progress_async(
                        result.successful_records, result.total_records, "upsert"
                    )

            except Exception as e:
                if self.error_strategy == BulkErrorStrategy.FAIL_FAST:
                    raise
                result.failed_records += 1
                result.errors.append(
                    {
                        "record_index": result.successful_records
                        + result.failed_records
                        - 1,
                        "error": str(e),
                    }
                )

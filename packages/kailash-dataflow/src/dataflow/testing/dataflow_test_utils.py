"""
DataFlow Test Utilities

Provides utilities for testing DataFlow applications without relying on
external command-line tools like psql. Uses DataFlow's built-in capabilities
and migration system for all database operations.
"""

import asyncio
import logging
import re
import warnings
from datetime import datetime
from typing import Any, Dict, List, Optional

from dataflow import DataFlow
from dataflow.core.async_utils import async_safe_run
from dataflow.migrations.visual_migration_builder import (
    ColumnType,
    VisualMigrationBuilder,
)
from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class DataFlowTestUtils:
    """Utilities for DataFlow testing using built-in components."""

    def __init__(self, database_url: str, runtime=None):
        """Initialize test utilities with database connection.

        Args:
            database_url: Database connection string
            runtime: Optional shared runtime. If provided, the utils acquire
                a reference (ref-count increment). If None, creates its own.
        """
        self.database_url = database_url
        self.dataflow = DataFlow(database_url=database_url)
        # AutoMigrationSystem needs a connection, not a URL
        # For now, we'll skip it and use the visual migration builder directly

        # Initialize runtime
        if runtime is not None:
            self.runtime = runtime.acquire()
            self._owns_runtime = False
            self._is_async = isinstance(runtime, AsyncLocalRuntime)
            logger.debug(
                "DataFlowTestUtils: Using injected runtime (ref_count=%d)",
                runtime.ref_count,
            )
        else:
            try:
                asyncio.get_running_loop()
                self.runtime = AsyncLocalRuntime()
                self._is_async = True
                logger.debug(
                    "DataFlowTestUtils: Detected async context, using AsyncLocalRuntime"
                )
            except RuntimeError:
                self.runtime = LocalRuntime()
                self._is_async = False
                logger.debug(
                    "DataFlowTestUtils: Detected sync context, using LocalRuntime"
                )
            self._owns_runtime = True

    def drop_all_tables(self) -> None:
        """Drop all tables in the database using DataFlow migrations."""
        logger.info("Dropping all tables using DataFlow migrations...")

        # Get current schema
        current_schema = self.dataflow.discover_schema()

        # Create migration to drop all tables
        migration_builder = VisualMigrationBuilder("cleanup_test_tables")

        for table_name in current_schema.keys():
            migration_builder.drop_table(table_name)

        # Apply the migration
        migration = migration_builder.build()
        if migration.operations:
            for operation in migration.operations:
                logger.info(
                    "dataflow_test_utils.executing",
                    extra={"description": operation.description},
                )
                # Execute the SQL using DataFlow's connection
                self._execute_sql(operation.sql_up)

    def create_schema(self) -> None:
        """Create a new public schema after dropping tables."""
        logger.info("Creating fresh schema...")

        # PostgreSQL specific - create schema if it doesn't exist
        self._execute_sql("CREATE SCHEMA IF NOT EXISTS public")

    def cleanup_database(self) -> None:
        """Complete database cleanup using DataFlow components."""
        # Drop all tables
        self.drop_all_tables()

        # Recreate schema
        self.create_schema()

    def _execute_sql(self, sql: str) -> None:
        """Execute raw SQL using DataFlow's connection manager."""
        # Use DataFlow's connection manager to execute SQL
        # This is a temporary solution until DataFlow has built-in drop_tables

        # For now, we'll use a workflow to execute the SQL
        workflow = WorkflowBuilder()

        # Use AsyncSQLDatabaseNode to execute the SQL
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "execute_sql",
            {
                "connection_string": self.database_url,
                "query": sql,
                "fetch_mode": "all",  # Changed from "none" to "all"
                "validate_queries": False,
            },
        )

        # Execute the workflow
        try:
            results, _ = self.runtime.execute(workflow.build())
            logger.info(
                "dataflow_test_utils.sql_executed_successfully", extra={"sql": sql[:50]}
            )
        except Exception as e:
            logger.error(
                "dataflow_test_utils.failed_to_execute_sql", extra={"error": str(e)}
            )
            raise

    def setup_test_models(self, models: List[type]) -> DataFlow:
        """Setup test models using DataFlow's model decorator."""
        db = DataFlow(database_url=self.database_url)

        # Register models
        for model in models:
            # Apply the @db.model decorator
            decorated_model = db.model(model)

        # Create tables
        db.create_tables()

        return db

    def bulk_insert_test_data(
        self, model_name: str, data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk insert test data using DataFlow bulk nodes."""
        workflow = WorkflowBuilder()

        # Use bulk create node
        workflow.add_node(
            f"{model_name}BulkCreateNode",
            "bulk_insert",
            {
                "data": data,
                "batch_size": min(1000, len(data)),
                "conflict_resolution": "skip",
            },
        )

        # Execute workflow
        results, _ = self.runtime.execute(workflow.build())
        return results["bulk_insert"]

    def query_data(
        self, model_name: str, filter: Optional[Dict[str, Any]] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query data using DataFlow list nodes."""
        workflow = WorkflowBuilder()

        # Use list node
        workflow.add_node(
            f"{model_name}ListNode", "query", {"filter": filter or {}, "limit": limit}
        )

        # Execute workflow
        results, _ = self.runtime.execute(workflow.build())
        return results["query"]["records"]

    def update_data(
        self, model_name: str, id: int, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update data using DataFlow update nodes."""
        workflow = WorkflowBuilder()

        # Use update node
        workflow.add_node(f"{model_name}UpdateNode", "update", {"id": id, **updates})

        # Execute workflow
        results, _ = self.runtime.execute(workflow.build())
        return results["update"]

    def delete_data(self, model_name: str, id: int) -> Dict[str, Any]:
        """Delete data using DataFlow delete nodes."""
        workflow = WorkflowBuilder()

        # Use delete node
        workflow.add_node(f"{model_name}DeleteNode", "delete", {"id": id})

        # Execute workflow
        results, _ = self.runtime.execute(workflow.build())
        return results["delete"]

    def execute_transaction(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run DataFlow node operations in order on one database transaction.

        Generated DataFlow nodes borrow the scope's pinned connection through
        workflow context. The adapter owns commit/rollback, including when a
        node raises before a commit node could run. Results are keyed by op_N.
        """
        workflows = []
        for idx, op in enumerate(operations):
            workflow = WorkflowBuilder()
            node_id = f"op_{idx}"
            workflow.add_node(op["node_type"], node_id, op["parameters"])
            built = workflow.build()
            node = built.get_node(node_id)
            owner = getattr(node, "dataflow_instance", None)
            if (
                not isinstance(owner, DataFlow)
                or owner.config.database.url != self.database_url
                or type(node) not in owner._nodes.values()
                or getattr(node, "model_name", None) not in owner._models
            ):
                raise ValueError(
                    "Transactions require DataFlow nodes for this database"
                )
            workflows.append(built)

        async def execute():
            # Finish lazy schema/registry initialization before holding a write
            # transaction; its separate DDL connection cannot join this scope.
            if not await self.dataflow.initialize():
                raise RuntimeError("DataFlow initialization failed before transaction")
            sql_node = self.dataflow._get_or_create_async_sql_node(
                self.dataflow._detect_database_type()
            )
            adapter = await sql_node._get_adapter()
            results = {}
            async with adapter.transaction() as scope:
                context = {
                    "dataflow_instance": self.dataflow,
                    "active_transaction": scope,
                }
                for workflow in workflows:
                    if isinstance(self.runtime, AsyncLocalRuntime):
                        for node_id in workflow.nodes:
                            node = workflow.get_node(node_id)
                            for key, value in context.items():
                                node.set_workflow_context(key, value)
                        result, _ = await self.runtime.execute_workflow_async(
                            workflow, inputs={}
                        )
                    else:
                        result, _ = await self.runtime.execute_async(
                            workflow, parameters={"workflow_context": context}
                        )
                    results.update(result)
            return results

        return async_safe_run(execute())

    @staticmethod
    def _migration_column(builder, column):
        """Configure a supported fluent column from the utility's dict API."""
        allowed = {
            "name",
            "type",
            "nullable",
            "primary_key",
            "default",
            "unique",
            "references",
            "check",
            "comment",
            "auto_increment",
        }
        if column.keys() - allowed:
            raise ValueError("Unsupported migration column option")
        for option in ("nullable", "primary_key", "unique", "auto_increment"):
            if option in column and type(column[option]) is not bool:
                raise ValueError(
                    f"Migration column option {option!r} must be a boolean"
                )
        declared = column["type"]
        if isinstance(declared, ColumnType):
            kind, size = declared, None
        else:
            match = re.fullmatch(
                r"([A-Za-z]+)(?:\((\d+)(?:\s*,\s*(\d+))?\))?", declared
            )
            if match is None:
                raise ValueError("Unsupported migration column type")
            name, length, scale = match.groups()
            kind = ColumnType("INTEGER" if name.upper() == "SERIAL" else name.upper())
            size = (length, scale)
        result = builder(column["name"], kind)
        if size and size[0]:
            if kind in (ColumnType.VARCHAR, ColumnType.CHAR) and size[1] is None:
                result.length(int(size[0]))
            elif kind == ColumnType.DECIMAL:
                result.decimal(int(size[0]), int(size[1] or 0))
            else:
                raise ValueError("Column size is unsupported for this type")
        if isinstance(declared, str) and declared.upper() == "SERIAL":
            result.auto_increment()
        if not column.get("nullable", True):
            result.not_null()
        if column.get("primary_key", False):
            result.primary_key()
        if "default" in column:
            result.default_value(column["default"])
        if column.get("unique", False):
            result.unique()
        if column.get("auto_increment", False):
            result.auto_increment()
        for key, method in (
            ("references", result.references),
            ("check", result.check),
            ("comment", result.comment),
        ):
            if key in column:
                method(column[key])
        return result

    def run_migration(self, migration_operations: List[Dict[str, Any]]) -> None:
        """Run database migrations using DataFlow's migration system."""
        migration_name = f"test_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        migration_builder = VisualMigrationBuilder(
            migration_name, dialect=self.dataflow._detect_database_type()
        )

        allowed_options = {
            "create_table": {"type", "name", "columns"},
            "add_column": {"type", "table", "column"},
            "drop_table": {"type", "name", "force_drop"},
            "drop_column": {"type", "table", "column", "force_drop"},
        }
        for op in migration_operations:
            op_type = op["type"]
            allowed = allowed_options.get(op_type)
            if allowed is not None and op.keys() - allowed:
                raise ValueError("Unsupported migration operation option")

            if op_type == "create_table":
                table_builder = migration_builder.create_table(op["name"])
                for col in op["columns"]:
                    self._migration_column(table_builder.add_column, col)

            elif op_type == "drop_table":
                migration_builder.drop_table(
                    op["name"], force_drop=op.get("force_drop", False)
                )

            elif op_type == "add_column":
                self._migration_column(
                    lambda name, kind: migration_builder.add_column(
                        op["table"], name, kind
                    ),
                    op["column"],
                )

            elif op_type == "drop_column":
                migration_builder.drop_column(
                    op["table"], op["column"], force_drop=op.get("force_drop", False)
                )
            else:
                raise ValueError(f"Unsupported migration operation: {op_type!r}")

        # Apply migration
        migration = migration_builder.build()
        with self.dataflow.transactions_sync.begin() as transaction:
            for operation in migration.operations:
                transaction.execute_raw(operation.sql_up)

    def close(self):
        """Release the runtime reference and close the owned DataFlow instance.

        Safe to call multiple times -- subsequent calls are no-ops.
        """
        if hasattr(self, "runtime") and self.runtime is not None:
            try:
                self.runtime.release()
            finally:
                self.runtime = None
                self.dataflow.close()

    def __del__(self, _warnings=warnings):
        """Emit ResourceWarning if close() was not called explicitly.

        Per ``rules/patterns.md`` § Async Resource Cleanup, ``__del__``
        MUST NOT invoke ``close()`` itself — see issue #1000.
        """
        if getattr(self, "runtime", None) is not None:
            _warnings.warn(
                f"Unclosed {self.__class__.__name__}. Call close() explicitly.",
                ResourceWarning,
                source=self,
            )

    def verify_schema(self, expected_tables: List[str]) -> bool:
        """Verify that expected tables exist using DataFlow schema discovery."""
        current_schema = self.dataflow.discover_schema()
        actual_tables = set(current_schema.keys())
        expected_set = set(expected_tables)

        missing = expected_set - actual_tables
        extra = actual_tables - expected_set

        if missing:
            logger.error(
                "dataflow_test_utils.missing_tables", extra={"missing": missing}
            )
        if extra:
            logger.warning(
                "dataflow_test_utils.extra_tables_found", extra={"extra": extra}
            )

        return len(missing) == 0

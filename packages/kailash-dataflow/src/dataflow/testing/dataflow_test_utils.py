"""
DataFlow Test Utilities

Provides utilities for testing DataFlow applications without relying on
external command-line tools like psql. Uses DataFlow's built-in capabilities
and migration system for all database operations.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from dataflow.migrations.visual_migration_builder import VisualMigrationBuilder

logger = logging.getLogger(__name__)


class DataFlowTestUtils:
    """Utilities for DataFlow testing using built-in components."""

    def __init__(self, database_url: str):
        """Initialize test utilities with database connection."""
        self.database_url = database_url
        self.dataflow = DataFlow(database_url=database_url)
        # AutoMigrationSystem needs a connection, not a URL
        # For now, we'll skip it and use the visual migration builder directly

        # ✅ FIX: Detect async context and use appropriate runtime
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "DataFlowTestUtils: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug("DataFlowTestUtils: Detected sync context, using LocalRuntime")

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
                logger.info(f"Executing: {operation.description}")
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
            # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())
            logger.info(f"SQL executed successfully: {sql[:50]}...")
        except Exception as e:
            logger.error(f"Failed to execute SQL: {e}")
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
        # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
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
        # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        return results["query"]["records"]

    def update_data(
        self, model_name: str, id: int, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update data using DataFlow update nodes."""
        workflow = WorkflowBuilder()

        # Use update node
        workflow.add_node(f"{model_name}UpdateNode", "update", {"id": id, **updates})

        # Execute workflow
        # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        return results["update"]

    def delete_data(self, model_name: str, id: int) -> Dict[str, Any]:
        """Delete data using DataFlow delete nodes."""
        workflow = WorkflowBuilder()

        # Use delete node
        workflow.add_node(f"{model_name}DeleteNode", "delete", {"id": id})

        # Execute workflow
        # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        return results["delete"]

    def execute_transaction(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple operations in a transaction using DataFlow."""
        workflow = WorkflowBuilder()

        # Start transaction
        workflow.add_node(
            "TransactionScopeNode",
            "begin_txn",
            {
                "isolation_level": "READ_COMMITTED",
                "timeout": 30,
                "rollback_on_error": True,
            },
        )

        # Add operations
        prev_node = "begin_txn"
        for idx, op in enumerate(operations):
            node_id = f"op_{idx}"
            workflow.add_node(op["node_type"], node_id, op["parameters"])
            workflow.add_connection(prev_node, node_id)
            prev_node = node_id

        # Commit transaction
        workflow.add_node("TransactionCommitNode", "commit_txn", {})
        workflow.add_connection(prev_node, "commit_txn")

        # Execute workflow
        # ✅ FIX: Use LocalRuntime for test operations to avoid async context issues
        init_runtime = LocalRuntime()
        results, _ = init_runtime.execute(workflow.build())
        return results

    def run_migration(self, migration_operations: List[Dict[str, Any]]) -> None:
        """Run database migrations using DataFlow's migration system."""
        migration_name = f"test_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        migration_builder = VisualMigrationBuilder(migration_name)

        for op in migration_operations:
            op_type = op["type"]

            if op_type == "create_table":
                table_builder = migration_builder.create_table(op["name"])
                for col in op["columns"]:
                    table_builder.add_column(
                        name=col["name"],
                        type=col["type"],
                        nullable=col.get("nullable", True),
                        default=col.get("default"),
                        primary_key=col.get("primary_key", False),
                    )
                table_builder.build()

            elif op_type == "drop_table":
                migration_builder.drop_table(op["name"])

            elif op_type == "add_column":
                migration_builder.add_column(
                    table_name=op["table"],
                    column_name=op["column"]["name"],
                    column_type=op["column"]["type"],
                    nullable=op["column"].get("nullable", True),
                )

            elif op_type == "drop_column":
                migration_builder.drop_column(op["table"], op["column"])

        # Apply migration
        migration = migration_builder.build()
        for operation in migration.operations:
            logger.info(f"Running migration: {operation.description}")
            self._execute_sql(operation.sql_up)

    def verify_schema(self, expected_tables: List[str]) -> bool:
        """Verify that expected tables exist using DataFlow schema discovery."""
        current_schema = self.dataflow.discover_schema()
        actual_tables = set(current_schema.keys())
        expected_set = set(expected_tables)

        missing = expected_set - actual_tables
        extra = actual_tables - expected_set

        if missing:
            logger.error(f"Missing tables: {missing}")
        if extra:
            logger.warning(f"Extra tables found: {extra}")

        return len(missing) == 0

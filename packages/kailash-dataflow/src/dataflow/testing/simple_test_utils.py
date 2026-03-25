"""
Simple DataFlow Test Utilities

Provides simplified utilities for testing DataFlow applications without
relying on external tools. Focuses on using DataFlow's own capabilities.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)

_TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def drop_tables_if_exist(database_url: str, table_names: List[str]) -> None:
    """Drop tables if they exist using DataFlow components."""
    try:
        asyncio.get_running_loop()
        runtime = AsyncLocalRuntime()
        logger.debug(
            "drop_tables_if_exist: Detected async context, using AsyncLocalRuntime"
        )
    except RuntimeError:
        runtime = LocalRuntime()
        logger.debug("drop_tables_if_exist: Detected sync context, using LocalRuntime")

    try:
        for table_name in table_names:
            if not _TABLE_NAME_RE.match(table_name):
                logger.warning(f"Skipping invalid table name: {table_name!r}")
                continue
            workflow = WorkflowBuilder()
            drop_query = f"DROP TABLE IF EXISTS {table_name} CASCADE"

            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "drop_table",
                {
                    "connection_string": database_url,
                    "query": drop_query,
                    "fetch_mode": "all",
                    "validate_queries": False,
                },
            )

            try:
                runtime.execute(workflow.build())
                logger.info(f"Dropped table: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to drop table {table_name}: {e}")
    finally:
        runtime.close()


def clean_test_database(database_url: str) -> None:
    """Clean test database by dropping common test tables."""
    common_test_tables = [
        # E-commerce tables
        "customers",
        "products",
        "carts",
        "cart_items",
        "orders",
        "order_items",
        "inventories",
        # Blog tables
        "blog_users",
        "blog_posts",
        "comments",
        # User management
        "users",
        "posts",
        "migrations",
        # Features
        "postgres_features",
        # Test models
        "test_models",
        "checklist_tests",
        "perf_tests",
    ]

    drop_tables_if_exist(database_url, common_test_tables)


def create_test_data(
    model_name: str, data: List[Dict[str, Any]], use_bulk: bool = True
) -> Dict[str, Any]:
    """Create test data using DataFlow nodes."""
    try:
        asyncio.get_running_loop()
        runtime = AsyncLocalRuntime()
        logger.debug(
            "create_test_data: Detected async context, using AsyncLocalRuntime"
        )
    except RuntimeError:
        runtime = LocalRuntime()
        logger.debug("create_test_data: Detected sync context, using LocalRuntime")

    try:
        workflow = WorkflowBuilder()

        if use_bulk and len(data) > 1:
            workflow.add_node(
                f"{model_name}BulkCreateNode",
                "bulk_create",
                {"data": data, "batch_size": min(1000, len(data))},
            )
            results, _ = runtime.execute(workflow.build())
            return results["bulk_create"]
        else:
            for idx, record in enumerate(data):
                workflow.add_node(f"{model_name}CreateNode", f"create_{idx}", record)

                if idx > 0:
                    workflow.add_connection(f"create_{idx - 1}", f"create_{idx}")

            results, _ = runtime.execute(workflow.build())
            return results
    finally:
        runtime.close()

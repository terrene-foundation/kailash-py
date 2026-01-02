"""
Workflow Helper Functions for E2E Tests

This module provides helper functions to create common workflow patterns
that work reliably in E2E test environments.
"""

from typing import Any, Dict, Optional

from kailash.workflow.builder import WorkflowBuilder

from tests.e2e.config import E2ETestConfig


class WorkflowHelpers:
    """Helper methods for creating test workflows."""

    @staticmethod
    def add_db_fetch_node(
        workflow: WorkflowBuilder,
        node_id: str,
        query: str,
        params: Optional[list] = None,
        fetch_mode: str = "all",
    ):
        """Add a node that fetches data from database."""
        params_code = f"params = {params}" if params else "params = []"

        fetch_code = {
            "all": "rows = await conn.fetch(query, *params)",
            "one": "row = await conn.fetchrow(query, *params)",
            "val": "value = await conn.fetchval(query, *params)",
        }[fetch_mode]

        result_code = {
            "all": """
    result = []
    for row in rows:
        result.append(dict(row))
""",
            "one": "result = dict(row) if row else None",
            "val": "result = value",
        }[fetch_mode]

        code = f'''
import asyncpg

# Connect to database
conn = await asyncpg.connect(
    host="{E2ETestConfig.DATABASE['host']}",
    port={E2ETestConfig.DATABASE['port']},
    database="{E2ETestConfig.DATABASE['database']}",
    user="{E2ETestConfig.DATABASE['user']}",
    password="{E2ETestConfig.DATABASE['password']}"
)

try:
    query = """{query}"""
    {params_code}

    {fetch_code}
    {result_code}
finally:
    await conn.close()
'''

        workflow.add_node("AsyncPythonCodeNode", node_id, {"code": code})

    @staticmethod
    def add_db_execute_node(
        workflow: WorkflowBuilder, node_id: str, query: str, params_expr: str = "[]"
    ):
        """Add a node that executes a database command."""
        code = f'''
import asyncpg

# Connect to database
conn = await asyncpg.connect(
    host="{E2ETestConfig.DATABASE['host']}",
    port={E2ETestConfig.DATABASE['port']},
    database="{E2ETestConfig.DATABASE['database']}",
    user="{E2ETestConfig.DATABASE['user']}",
    password="{E2ETestConfig.DATABASE['password']}"
)

try:
    query = """{query}"""
    params = {params_expr}

    await conn.execute(query, *params)
    result = {{"success": True}}
finally:
    await conn.close()
'''

        workflow.add_node("AsyncPythonCodeNode", node_id, {"code": code})

    @staticmethod
    def add_db_transaction_node(
        workflow: WorkflowBuilder, node_id: str, operations: list
    ):
        """Add a node that performs multiple database operations in a transaction."""
        ops_code = "\n    ".join(
            [
                f'await conn.execute("""{op["query"]}""", *{op.get("params", [])})'
                for op in operations
            ]
        )

        code = f"""
import asyncpg

# Connect to database
conn = await asyncpg.connect(
    host="{E2ETestConfig.DATABASE['host']}",
    port={E2ETestConfig.DATABASE['port']},
    database="{E2ETestConfig.DATABASE['database']}",
    user="{E2ETestConfig.DATABASE['user']}",
    password="{E2ETestConfig.DATABASE['password']}"
)

try:
    # Start transaction
    async with conn.transaction():
        {ops_code}

    result = {{"success": True, "operations": {len(operations)}}}
finally:
    await conn.close()
"""

        workflow.add_node("AsyncPythonCodeNode", node_id, {"code": code})

    @staticmethod
    def create_standard_connections(workflow: WorkflowBuilder, node_pairs: list):
        """Create standard node connections with result wrapping."""
        for source, target in node_pairs:
            workflow.add_connection(source, "result", target, "input_data")

    @staticmethod
    def create_validation_node(
        workflow: WorkflowBuilder,
        node_id: str,
        required_fields: list,
        validation_rules: Optional[Dict[str, str]] = None,
    ):
        """Create a validation node."""
        rules_code = ""
        if validation_rules:
            for field, rule in validation_rules.items():
                rules_code += f"""
    if "{field}" in data and not ({rule}):
        errors.append(f"{field} validation failed: {rule}")
"""

        code = f"""
# Validate input data
data = locals().get('input_data', {{}})
errors = []

# Check required fields
required_fields = {required_fields}
for field in required_fields:
    if field not in data or data[field] is None:
        errors.append(f"Missing required field: {{field}}")

# Additional validation rules
{rules_code}

# Return result
if errors:
    result = {{"valid": False, "errors": errors}}
else:
    result = {{"valid": True, "data": data}}
"""

        workflow.add_node("PythonCodeNode", node_id, {"code": code})

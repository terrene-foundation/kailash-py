"""
Test workflow for validation audit tool.

This workflow has various connection patterns to test the audit functionality.
"""

from kailash.workflow.builder import WorkflowBuilder

# Create workflow with various connection patterns
workflow_builder = WorkflowBuilder()

# Add nodes
workflow_builder.add_node(
    "PythonCodeNode",
    "data_source",
    {
        "code": "result = {'count': 123, 'name': 'test', 'query': \"SELECT * FROM users\"}"
    },
)

workflow_builder.add_node(
    "PythonCodeNode",
    "processor",
    {"code": "result = {'processed': len(data)}"},  # Expects string/list
)

workflow_builder.add_node("CSVReaderNode", "csv_reader", {})

workflow_builder.add_node(
    "PythonCodeNode",
    "sql_consumer",
    {"code": "result = execute_query(query)"},  # Potential SQL injection
)

# Add connections - some will pass, some will fail
# This will pass - valid connection
workflow_builder.add_connection("data_source", "result.name", "processor", "data")

# This might fail - type mismatch (int to file_path)
workflow_builder.add_connection(
    "data_source", "result.count", "csv_reader", "file_path"
)

# This might trigger security warning - SQL query passed directly
workflow_builder.add_connection("data_source", "result.query", "sql_consumer", "query")

# Build workflow
workflow = workflow_builder.build()

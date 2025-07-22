"""
Suggestion engine for generating actionable guidance from validation errors.

Provides specific, actionable suggestions for fixing connection validation
errors based on error category, node type, and connection context.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .connection_context import ConnectionContext
from .error_categorizer import ErrorCategory


@dataclass
class ValidationSuggestion:
    """Actionable suggestion for fixing a validation error."""

    message: str
    """Human-readable suggestion message"""

    code_example: Optional[str] = None
    """Code example showing how to fix the issue"""

    documentation_link: Optional[str] = None
    """Link to relevant documentation"""

    alternative_approaches: Optional[List[str]] = None
    """List of alternative approaches to consider"""


class ValidationSuggestionEngine:
    """Generates actionable suggestions for connection validation errors."""

    def __init__(self):
        self._suggestion_templates = self._initialize_suggestion_templates()

    def generate_suggestion(
        self,
        error_category: ErrorCategory,
        node_type: str,
        connection_context: ConnectionContext,
        original_error: str,
    ) -> Optional[ValidationSuggestion]:
        """Generate actionable suggestion for a validation error.

        Args:
            error_category: Categorized error type
            node_type: Type of target node (e.g., 'CSVWriterNode')
            connection_context: Context about the failing connection
            original_error: Original error message

        Returns:
            ValidationSuggestion with actionable guidance, or None if no suggestion available
        """
        # Get base suggestion template for error category
        template = self._suggestion_templates.get(error_category)
        if not template:
            return None

        # Customize suggestion based on node type and context
        return self._customize_suggestion(
            template, node_type, connection_context, original_error
        )

    def _initialize_suggestion_templates(self) -> Dict[ErrorCategory, Dict]:
        """Initialize suggestion templates for each error category."""
        return {
            ErrorCategory.TYPE_MISMATCH: {
                "message": "The parameter type doesn't match what the node expects. Check the data types being passed through the connection.",
                "code_template": '# Check the output type from source node\n# Expected: {expected_type}\n# Got: {actual_type}\nworkflow.add_connection("{source}", "{source_port}", "{target}", "{target_port}")',
                "doc_link": "sdk-users/2-core-concepts/validation/common-mistakes.md#type-mismatch",
                "alternatives": [
                    "Add a data transformation node between source and target",
                    "Check if you're connecting to the correct output port",
                    "Verify the source node produces the expected data type",
                ],
            },
            ErrorCategory.MISSING_PARAMETER: {
                "message": "A required parameter is missing. Make sure all required parameters are provided via connections or node configuration.",
                "code_template": '# Add the missing parameter connection:\nworkflow.add_connection("{source}", "{source_port}", "{target}", "{missing_param}")\n\n# Or provide it directly in node configuration:\nworkflow.add_node("{node_type}", "{target}", {{"{missing_param}": "value"}})',
                "doc_link": "sdk-users/2-core-concepts/validation/common-mistakes.md#missing-parameters",
                "alternatives": [
                    "Provide the parameter directly in node configuration",
                    "Create a PythonCodeNode to generate the required parameter",
                    "Check if another node output can provide this parameter",
                ],
            },
            ErrorCategory.CONSTRAINT_VIOLATION: {
                "message": "The parameter value violates validation constraints. Check the parameter requirements for this node type.",
                "code_template": '# Ensure parameter meets requirements:\n# {constraint_details}\nworkflow.add_connection("{source}", "{source_port}", "{target}", "{target_port}")\n\n# Or add validation in source node:\nworkflow.add_node("PythonCodeNode", "validator", {{"code": "result = max(0, input_value)"}})',
                "doc_link": "sdk-users/6-reference/nodes/node-selection-guide.md#parameter-validation",
                "alternatives": [
                    "Add data validation/transformation before the target node",
                    "Check the node documentation for parameter requirements",
                    "Use a different node that accepts your data format",
                ],
            },
            ErrorCategory.SECURITY_VIOLATION: {
                "message": "Potential security issue detected in parameter value. This could indicate SQL injection, script injection, or other security vulnerabilities.",
                "code_template": '# Use parameterized/sanitized approach:\n# For SQL operations:\nworkflow.add_node("SQLDatabaseNode", "safe_query", {{\n    "query": "SELECT * FROM table WHERE id = $1",\n    "params": ["user_input"]\n}})\n\n# For user input, add validation:\nworkflow.add_node("PythonCodeNode", "sanitizer", {{"code": "result = sanitize_input(user_data)"}})',
                "doc_link": "sdk-users/5-enterprise/security-patterns.md#input-validation",
                "alternatives": [
                    "Use parameterized queries instead of string concatenation",
                    "Add input sanitization/validation nodes",
                    "Review the data source for potential security issues",
                    "Use whitelisting instead of blacklisting for allowed values",
                ],
            },
            ErrorCategory.UNKNOWN: {
                "message": "An unexpected validation error occurred. Check the error details and node documentation.",
                "code_template": '# General troubleshooting:\n# 1. Check node documentation for parameter requirements\n# 2. Verify data types and formats\n# 3. Test with simpler data first\nworkflow.add_connection("{source}", "{source_port}", "{target}", "{target_port}")',
                "doc_link": "sdk-users/3-development/guides/troubleshooting.md",
                "alternatives": [
                    "Check the node documentation for specific requirements",
                    "Test with simplified data to isolate the issue",
                    "Add debug logging to inspect the data flow",
                    "Review similar examples in the documentation",
                ],
            },
        }

    def _customize_suggestion(
        self,
        template: Dict,
        node_type: str,
        connection_context: ConnectionContext,
        original_error: str,
    ) -> ValidationSuggestion:
        """Customize suggestion template with specific context."""
        # Extract context information
        source = connection_context.source_node
        source_port = connection_context.source_port or "result"
        target = connection_context.target_node
        target_port = connection_context.target_port

        # Customize code example
        code_example = template["code_template"].format(
            source=source,
            source_port=source_port,
            target=target,
            target_port=target_port,
            node_type=node_type,
            expected_type="<check_node_docs>",
            actual_type="<check_source_output>",
            missing_param=target_port,
            constraint_details="See node documentation for valid ranges/formats",
        )

        # Add node-specific customizations
        message = template["message"]
        if (
            "DataFlow" in node_type
            or node_type.endswith("CreateNode")
            or node_type.endswith("UpdateNode")
        ):
            message += " For DataFlow nodes, ensure the data matches your model schema."

        if "SQL" in node_type or "Database" in node_type:
            message += " For database nodes, verify connection strings and SQL syntax."

        if "LLM" in node_type or "Agent" in node_type:
            message += " For AI nodes, check prompt formatting and model parameters."

        return ValidationSuggestion(
            message=message,
            code_example=code_example,
            documentation_link=template["doc_link"],
            alternative_approaches=template["alternatives"],
        )

    def get_dataflow_specific_suggestion(
        self, error_category: ErrorCategory, connection_context: ConnectionContext
    ) -> Optional[str]:
        """Get DataFlow-specific suggestions for common issues."""
        dataflow_suggestions = {
            ErrorCategory.TYPE_MISMATCH: (
                "For DataFlow models, ensure the connected data matches your model field types. "
                "Check your @db.model class definition for expected types."
            ),
            ErrorCategory.SECURITY_VIOLATION: (
                "DataFlow automatically sanitizes SQL parameters, but connection-level validation "
                "caught a potential issue. Review the data source for SQL injection attempts."
            ),
            ErrorCategory.MISSING_PARAMETER: (
                "DataFlow nodes require all model fields to be provided. Check your model definition "
                "and ensure all required fields have connections or default values."
            ),
        }
        return dataflow_suggestions.get(error_category)

    def get_common_connection_patterns(self, node_type: str) -> List[str]:
        """Get common connection patterns for specific node types."""
        patterns = {
            "CSVReaderNode": [
                "workflow.add_connection('reader', 'data', 'processor', 'input_data')",
                "workflow.add_connection('reader', 'metadata.rows', 'counter', 'count')",
            ],
            "HTTPRequestNode": [
                "workflow.add_connection('api', 'response.data', 'processor', 'json_data')",
                "workflow.add_connection('api', 'status_code', 'checker', 'status')",
            ],
            "LLMAgentNode": [
                "workflow.add_connection('input', 'text', 'llm', 'prompt')",
                "workflow.add_connection('llm', 'result', 'output', 'analysis')",
            ],
            "SQLDatabaseNode": [
                "workflow.add_connection('data', 'records', 'db', 'data')",
                "workflow.add_connection('config', 'table_name', 'db', 'table')",
            ],
        }
        return patterns.get(node_type, [])

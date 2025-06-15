"""Node validation framework with context-aware error suggestions.

This module provides validation utilities that enhance error messages with
helpful suggestions, code examples, and documentation links.
"""

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from kailash.nodes.base import Node, NodeParameter


@dataclass
class ValidationSuggestion:
    """Suggestion for fixing a validation error."""

    message: str
    code_example: Optional[str] = None
    doc_link: Optional[str] = None
    alternative_nodes: Optional[List[str]] = None


class NodeValidator:
    """Enhanced node validation with helpful error messages."""

    # Common parameter mistakes and their fixes
    PARAMETER_PATTERNS = {
        # PythonCodeNode common mistakes
        r"return\s+(?!.*\{.*result.*\})": ValidationSuggestion(
            message="PythonCodeNode must return data wrapped in {'result': ...}",
            code_example='return {"result": your_data}  # Not: return your_data',
            doc_link="sdk-users/developer/07-troubleshooting.md#pythoncodenode-output",
        ),
        # File path mistakes
        r"^(?!/).*\.(csv|json|txt)$": ValidationSuggestion(
            message="File paths should be absolute, not relative",
            code_example='file_path="/data/inputs/file.csv"  # Not: file_path="file.csv"',
            doc_link="sdk-users/developer/QUICK_REFERENCE.md#file-paths",
        ),
        # Node naming mistakes
        r"Node$": ValidationSuggestion(
            message="Node names should describe their purpose, not end with 'Node'",
            code_example='workflow.add_node("read_data", CSVReaderNode)  # Not: "csv_reader_node"',
            alternative_nodes=[
                "Consider using descriptive names like 'load_config', 'process_data', 'save_results'"
            ],
        ),
        # SQL injection risks
        r"f['\"].*SELECT.*\{": ValidationSuggestion(
            message="Avoid f-strings in SQL queries - use parameterized queries",
            code_example='query="SELECT * FROM users WHERE id = %s", params=[user_id]',
            doc_link="sdk-users/security/sql-best-practices.md",
        ),
        # Missing required fields
        r"TypeError.*missing.*required": ValidationSuggestion(
            message="Required parameter missing",
            code_example="Check node documentation for required parameters",
            doc_link="sdk-users/nodes/comprehensive-node-catalog.md",
        ),
    }

    # Node-specific validations
    NODE_VALIDATIONS: Dict[str, List[Callable]] = {
        "PythonCodeNode": [
            lambda config: "code" in config or "func" in config,
            lambda config: not (
                config.get("code", "").strip().startswith("import ")
                and len(config.get("code", "").split("\n")) == 1
            ),
        ],
        "SQLDatabaseNode": [
            lambda config: "query" in config or "queries" in config,
            lambda config: not re.search(
                r"DROP|DELETE|TRUNCATE", config.get("query", ""), re.I
            )
            or config.get("allow_destructive", False),
        ],
        "HTTPRequestNode": [
            lambda config: "url" in config,
            lambda config: config.get("url", "").startswith(("http://", "https://")),
        ],
    }

    # Alternative node suggestions
    ALTERNATIVE_NODES = {
        "csv_processing": ["CSVReaderNode", "PandasNode", "DataTransformerNode"],
        "api_calls": ["HTTPRequestNode", "RESTClientNode", "GraphQLClientNode"],
        "data_storage": ["SQLDatabaseNode", "VectorDatabaseNode", "JSONWriterNode"],
        "llm_tasks": ["LLMAgentNode", "A2AAgentNode", "MCPAgentNode"],
        "authentication": ["OAuth2Node", "CredentialManagerNode", "BasicAuthNode"],
    }

    @classmethod
    def validate_node_config(
        cls,
        node_type: str,
        config: Dict[str, Any],
        node_instance: Optional[Node] = None,
    ) -> List[ValidationSuggestion]:
        """Validate node configuration and return suggestions."""
        suggestions = []

        # Check node-specific validations
        if node_type in cls.NODE_VALIDATIONS:
            for validation in cls.NODE_VALIDATIONS[node_type]:
                try:
                    if not validation(config):
                        suggestions.append(cls._get_node_suggestion(node_type, config))
                except Exception:
                    pass

        # Check parameter patterns
        config_str = str(config)
        for pattern, suggestion in cls.PARAMETER_PATTERNS.items():
            if re.search(pattern, config_str):
                suggestions.append(suggestion)

        # Check for common type mismatches
        if node_instance:
            suggestions.extend(cls._validate_parameter_types(node_instance, config))

        return suggestions

    @classmethod
    def _validate_parameter_types(
        cls, node: Node, config: Dict[str, Any]
    ) -> List[ValidationSuggestion]:
        """Validate parameter types match expected types."""
        suggestions = []

        try:
            params = node.get_parameters()
            for param_name, param_def in params.items():
                if param_name in config:
                    value = config[param_name]
                    expected_type = param_def.type

                    # Type checking
                    if expected_type and not cls._check_type(value, expected_type):
                        suggestions.append(
                            ValidationSuggestion(
                                message=f"Parameter '{param_name}' expects {expected_type.__name__}, got {type(value).__name__}",
                                code_example=f"{param_name}={cls._get_type_example(expected_type)}",
                                doc_link=f"sdk-users/nodes/{node.__class__.__name__.lower()}.md",
                            )
                        )
        except Exception:
            pass

        return suggestions

    @classmethod
    def _check_type(cls, value: Any, expected_type: Type) -> bool:
        """Check if value matches expected type."""
        # Handle Optional types
        if hasattr(expected_type, "__origin__"):
            if expected_type.__origin__ is type(Optional):
                if value is None:
                    return True
                expected_type = expected_type.__args__[0]

        # Direct type check
        return isinstance(value, expected_type)

    @classmethod
    def _get_type_example(cls, type_hint: Type) -> str:
        """Get example value for a type."""
        examples = {
            str: '"example_string"',
            int: "42",
            float: "3.14",
            bool: "True",
            list: '["item1", "item2"]',
            dict: '{"key": "value"}',
        }
        return examples.get(type_hint, f"<{type_hint.__name__} value>")

    @classmethod
    def _get_node_suggestion(
        cls, node_type: str, config: Dict[str, Any]
    ) -> ValidationSuggestion:
        """Get node-specific suggestion."""
        suggestions_map = {
            "PythonCodeNode": ValidationSuggestion(
                message="PythonCodeNode requires 'code' or use .from_function()",
                code_example="""
# Option 1: Inline code
PythonCodeNode(code='return {"result": data}')

# Option 2: From function (recommended)
def process(data):
    return {"result": data}
PythonCodeNode.from_function("processor", process)
""",
                alternative_nodes=["DataTransformerNode", "FilterNode", "MapNode"],
            ),
            "SQLDatabaseNode": ValidationSuggestion(
                message="SQLDatabaseNode requires 'query' parameter",
                code_example='SQLDatabaseNode(query="SELECT * FROM table", connection_string="...")',
                alternative_nodes=["AsyncSQLDatabaseNode", "VectorDatabaseNode"],
            ),
            "HTTPRequestNode": ValidationSuggestion(
                message="HTTPRequestNode requires valid 'url' parameter",
                code_example='HTTPRequestNode(url="https://api.example.com/data", method="GET")',
                alternative_nodes=[
                    "RESTClientNode",
                    "GraphQLClientNode",
                    "WebhookNode",
                ],
            ),
        }
        return suggestions_map.get(
            node_type,
            ValidationSuggestion(message=f"Invalid configuration for {node_type}"),
        )

    @classmethod
    def suggest_alternative_nodes(cls, use_case: str) -> List[str]:
        """Suggest alternative nodes for a use case."""
        # Fuzzy match use case
        for key, nodes in cls.ALTERNATIVE_NODES.items():
            if key in use_case.lower() or use_case.lower() in key:
                return nodes
        return []

    @classmethod
    def format_error_with_suggestions(
        cls,
        error: Exception,
        node_type: str,
        config: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format error message with helpful suggestions."""
        suggestions = cls.validate_node_config(node_type, config)

        # Build formatted error message
        lines = [f"❌ Error in {node_type}: {str(error)}", ""]

        if suggestions:
            lines.append("💡 Suggestions:")
            for i, suggestion in enumerate(suggestions, 1):
                lines.append(f"\n{i}. {suggestion.message}")

                if suggestion.code_example:
                    lines.append(f"\n   Example:\n   {suggestion.code_example}")

                if suggestion.alternative_nodes:
                    lines.append(
                        f"\n   Alternative nodes: {', '.join(suggestion.alternative_nodes)}"
                    )

                if suggestion.doc_link:
                    lines.append(f"\n   📚 Documentation: {suggestion.doc_link}")

        # Add context if provided
        if context:
            lines.extend(
                [
                    "",
                    "📋 Context:",
                    f"   Workflow: {context.get('workflow_name', 'Unknown')}",
                    f"   Node ID: {context.get('node_id', 'Unknown')}",
                    f"   Previous Node: {context.get('previous_node', 'None')}",
                ]
            )

        # Add generic help
        lines.extend(
            [
                "",
                "🔗 Resources:",
                "   - Node Catalog: sdk-users/nodes/comprehensive-node-catalog.md",
                "   - Quick Reference: sdk-users/developer/QUICK_REFERENCE.md",
                "   - Troubleshooting: sdk-users/developer/07-troubleshooting.md",
            ]
        )

        return "\n".join(lines)


def validate_node_decorator(node_class: Type[Node]) -> Type[Node]:
    """Decorator to add validation to node classes."""

    original_init = node_class.__init__
    original_run = node_class.run

    def new_init(self, *args, **kwargs):
        """Enhanced init with validation."""
        try:
            original_init(self, *args, **kwargs)
        except Exception as e:
            # Enhance error with suggestions
            error_msg = NodeValidator.format_error_with_suggestions(
                e, node_class.__name__, kwargs, {"node_id": kwargs.get("id", "unknown")}
            )
            raise type(e)(error_msg) from e

    def new_run(self, **inputs):
        """Enhanced run with validation."""
        try:
            return original_run(self, **inputs)
        except Exception as e:
            # Enhance error with runtime context
            error_msg = NodeValidator.format_error_with_suggestions(
                e,
                node_class.__name__,
                inputs,
                {
                    "node_id": getattr(self, "id", "unknown"),
                    "inputs": list(inputs.keys()),
                },
            )
            raise type(e)(error_msg) from e

    node_class.__init__ = new_init
    node_class.run = new_run

    return node_class

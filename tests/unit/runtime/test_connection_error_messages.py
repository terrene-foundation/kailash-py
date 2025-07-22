"""
Unit tests for enhanced connection validation error messages.

Tests Task 1.4: Improved Error Messages
- ConnectionContext tracking for connection path reconstruction
- Error categorization and classification
- ValidationSuggestionEngine for actionable guidance
- Enhanced error message formatting
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import Mock, patch

import pytest

# Will be implemented
from kailash.runtime.validation.connection_context import ConnectionContext
from kailash.runtime.validation.enhanced_error_formatter import EnhancedErrorFormatter
from kailash.runtime.validation.error_categorizer import ErrorCategorizer, ErrorCategory
from kailash.runtime.validation.suggestion_engine import (
    ValidationSuggestion,
    ValidationSuggestionEngine,
)
from kailash.sdk_exceptions import NodeValidationError, WorkflowValidationError


class TestConnectionContext:
    """Test connection context tracking for error messages."""

    def test_connection_context_creation(self):
        """Test basic ConnectionContext creation and properties."""
        context = ConnectionContext(
            source_node="data_source",
            source_port="csv_data",
            target_node="processor",
            target_port="input_data",
            parameter_value={"test": "data"},
            validation_mode="strict",
        )

        assert context.source_node == "data_source"
        assert context.source_port == "csv_data"
        assert context.target_node == "processor"
        assert context.target_port == "input_data"
        assert context.parameter_value == {"test": "data"}
        assert context.validation_mode == "strict"

    def test_connection_path_string(self):
        """Test connection path string generation."""
        context = ConnectionContext(
            source_node="api_client",
            source_port="response.data",
            target_node="transformer",
            target_port="raw_data",
            parameter_value="test",
            validation_mode="warn",
        )

        expected_path = "api_client.response.data → transformer.raw_data"
        assert context.get_connection_path() == expected_path

    def test_connection_context_with_missing_data(self):
        """Test ConnectionContext with missing/None values."""
        context = ConnectionContext(
            source_node="source",
            source_port=None,  # Missing port info
            target_node="target",
            target_port="input",
            parameter_value=None,  # Missing value
            validation_mode="strict",
        )

        # Should handle missing data gracefully
        path = context.get_connection_path()
        assert "source" in path
        assert "target" in path
        assert "input" in path


class TestErrorCategorizer:
    """Test error categorization for connection validation failures."""

    def test_type_mismatch_categorization(self):
        """Test categorization of type validation errors."""
        categorizer = ErrorCategorizer()

        # Type error from node validation
        type_error = TypeError("expected str but got int for parameter 'name'")
        category = categorizer.categorize_error(type_error, "UserCreateNode")

        assert category == ErrorCategory.TYPE_MISMATCH

    def test_security_violation_categorization(self):
        """Test categorization of security validation errors."""
        categorizer = ErrorCategorizer()

        # SQL injection error
        security_error = ValueError(
            "SQL injection detected in parameter 'query': DROP TABLE"
        )
        category = categorizer.categorize_error(security_error, "SQLDatabaseNode")

        assert category == ErrorCategory.SECURITY_VIOLATION

    def test_missing_parameter_categorization(self):
        """Test categorization of missing required parameter errors."""
        categorizer = ErrorCategorizer()

        # Missing parameter error
        missing_error = ValueError("Missing required parameter: 'file_path'")
        category = categorizer.categorize_error(missing_error, "CSVReaderNode")

        assert category == ErrorCategory.MISSING_PARAMETER

    def test_constraint_violation_categorization(self):
        """Test categorization of parameter constraint violations."""
        categorizer = ErrorCategorizer()

        # Constraint violation
        constraint_error = ValueError("Parameter 'batch_size' must be positive, got -1")
        category = categorizer.categorize_error(constraint_error, "DataProcessorNode")

        assert category == ErrorCategory.CONSTRAINT_VIOLATION

    def test_unknown_error_categorization(self):
        """Test categorization of unknown error types."""
        categorizer = ErrorCategorizer()

        # Unknown error type
        unknown_error = RuntimeError("Something unexpected happened")
        category = categorizer.categorize_error(unknown_error, "CustomNode")

        assert category == ErrorCategory.UNKNOWN


class TestValidationSuggestionEngine:
    """Test actionable suggestion generation for validation errors."""

    def test_type_mismatch_suggestion(self):
        """Test suggestion generation for type mismatch errors."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="api_client",
            source_port="response",
            target_node="csv_writer",
            target_port="data",
            parameter_value={"records": []},  # dict instead of expected list
            validation_mode="strict",
        )

        suggestion = engine.generate_suggestion(
            ErrorCategory.TYPE_MISMATCH,
            "CSVWriterNode",
            context,
            original_error="expected list but got dict for parameter 'data'",
        )

        assert suggestion is not None
        assert (
            "type" in suggestion.message.lower()
            and "match" in suggestion.message.lower()
        )
        assert suggestion.code_example is not None
        assert "workflow.add_connection" in suggestion.code_example
        assert suggestion.documentation_link is not None

    def test_security_violation_suggestion(self):
        """Test suggestion generation for security violations."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="user_input",
            source_port="query",
            target_node="database",
            target_port="sql_query",
            parameter_value="'; DROP TABLE users; --",
            validation_mode="strict",
        )

        suggestion = engine.generate_suggestion(
            ErrorCategory.SECURITY_VIOLATION,
            "SQLDatabaseNode",
            context,
            original_error="SQL injection detected in parameter 'sql_query'",
        )

        assert "security" in suggestion.message.lower()
        assert "sql injection" in suggestion.message.lower()
        assert suggestion.code_example is not None
        # Check that the code example mentions parameterized approach or sanitization
        assert (
            "parameterized" in suggestion.code_example.lower()
            or "sanitize" in suggestion.code_example.lower()
        )

    def test_missing_parameter_suggestion(self):
        """Test suggestion generation for missing parameters."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="data_source",
            source_port="output",
            target_node="file_writer",
            target_port="content",
            parameter_value=None,
            validation_mode="strict",
        )

        suggestion = engine.generate_suggestion(
            ErrorCategory.MISSING_PARAMETER,
            "CSVWriterNode",
            context,
            original_error="Missing required parameter: 'file_path'",
        )

        assert "missing" in suggestion.message.lower()
        assert "required" in suggestion.message.lower()
        assert suggestion.code_example is not None
        assert "add_connection" in suggestion.code_example

    def test_dataflow_specific_suggestions(self):
        """Test DataFlow-specific error suggestions."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="user_form",
            source_port="form_data.name",
            target_node="user_create",
            target_port="name",
            parameter_value="'; DROP TABLE users; --",
            validation_mode="strict",
        )

        suggestion = engine.generate_suggestion(
            ErrorCategory.SECURITY_VIOLATION,
            "UserCreateNode",  # DataFlow-generated node
            context,
            original_error="SQL injection detected",
        )

        # Should include DataFlow-specific guidance
        assert suggestion is not None
        assert (
            "dataflow" in suggestion.message.lower()
            or "model" in suggestion.message.lower()
        )


class TestEnhancedErrorFormatter:
    """Test enhanced error message formatting."""

    def test_structured_error_message_format(self):
        """Test that error messages follow structured format."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="api_client",
            source_port="response.data",
            target_node="processor",
            target_port="input_data",
            parameter_value={"invalid": "data"},
            validation_mode="strict",
        )

        suggestion = ValidationSuggestion(
            message="Type mismatch detected",
            code_example="workflow.add_connection('api_client', 'response.data', 'processor', 'input_data')",
            documentation_link="sdk-users/2-core-concepts/validation/common-mistakes.md#type-mismatch",
        )

        error_msg = formatter.format_enhanced_error(
            original_error="expected list but got dict",
            error_category=ErrorCategory.TYPE_MISMATCH,
            connection_context=context,
            suggestion=suggestion,
        )

        # Verify structured format
        assert "Problem:" in error_msg
        assert "Connection:" in error_msg
        assert "api_client.response.data → processor.input_data" in error_msg
        assert "Suggestion:" in error_msg
        assert "Example:" in error_msg
        assert "Documentation:" in error_msg

    def test_security_error_value_sanitization(self):
        """Test that sensitive values are sanitized in error messages."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="user_input",
            source_port="query",
            target_node="database",
            target_port="sql_query",
            parameter_value="'; DROP TABLE users; SELECT * FROM secrets; --",  # Sensitive
            validation_mode="strict",
        )

        suggestion = ValidationSuggestion(
            message="SQL injection detected",
            code_example="Use parameterized queries",
            documentation_link="sdk-users/5-enterprise/security-patterns.md#sql-injection",
        )

        error_msg = formatter.format_enhanced_error(
            original_error="SQL injection detected in parameter 'sql_query'",
            error_category=ErrorCategory.SECURITY_VIOLATION,
            connection_context=context,
            suggestion=suggestion,
        )

        # Should not leak the actual malicious SQL
        assert "DROP TABLE" not in error_msg
        assert "SELECT * FROM secrets" not in error_msg
        assert "**SANITIZED**" in error_msg or "**REDACTED**" in error_msg

    def test_error_message_with_missing_context(self):
        """Test error formatting with incomplete context."""
        formatter = EnhancedErrorFormatter()

        # Minimal context
        context = ConnectionContext(
            source_node="unknown",
            source_port=None,
            target_node="target",
            target_port="input",
            parameter_value=None,
            validation_mode="warn",
        )

        suggestion = None  # No suggestion available

        error_msg = formatter.format_enhanced_error(
            original_error="Validation failed",
            error_category=ErrorCategory.UNKNOWN,
            connection_context=context,
            suggestion=suggestion,
        )

        # Should handle gracefully without crashing
        assert error_msg is not None
        assert "unknown" in error_msg.lower()
        assert "target" in error_msg.lower()

    def test_multiple_lines_formatting(self):
        """Test proper formatting of multi-line code examples."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="reader",
            source_port="data",
            target_node="processor",
            target_port="input",
            parameter_value="test",
            validation_mode="strict",
        )

        multiline_example = """workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("DataProcessorNode", "processor", {"operation": "transform"})
workflow.add_connection("reader", "data", "processor", "input")"""

        suggestion = ValidationSuggestion(
            message="Connection setup required",
            code_example=multiline_example,
            documentation_link="sdk-users/2-core-concepts/patterns/connection-patterns.md",
        )

        error_msg = formatter.format_enhanced_error(
            original_error="Invalid connection",
            error_category=ErrorCategory.MISSING_PARAMETER,
            connection_context=context,
            suggestion=suggestion,
        )

        # Should properly indent multi-line code
        assert "    workflow.add_node" in error_msg  # Indented
        assert "CSVReaderNode" in error_msg
        assert "add_connection" in error_msg


class TestEnhancedErrorFormatterAdditional:
    """Additional tests to improve coverage of EnhancedErrorFormatter."""

    def test_format_simple_error(self):
        """Test simple error formatting for warn mode."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="api",
            source_port="data",
            target_node="processor",
            target_port="input",
            parameter_value="test_value",
            validation_mode="warn",
        )

        error_msg = formatter.format_simple_error("Type mismatch error", context)

        assert "Connection validation warning" in error_msg
        assert "api.data → processor.input" in error_msg
        assert "Type mismatch error" in error_msg

    def test_format_security_error_comprehensive(self):
        """Test comprehensive security error formatting."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="user_input",
            source_port="form_data",
            target_node="database",
            target_port="query",
            parameter_value="'; DROP TABLE users; --",
            validation_mode="strict",
        )

        suggestion = ValidationSuggestion(
            message="Use parameterized queries to prevent SQL injection",
            code_example="db.execute('SELECT * FROM users WHERE id = ?', [user_id])",
            documentation_link="sdk-users/5-enterprise/security-patterns.md#sql-injection",
        )

        error_msg = formatter.format_security_error(
            "SQL injection detected", context, suggestion
        )

        # Check all sections are present
        assert "SECURITY ALERT" in error_msg
        assert "Security Issue:" in error_msg
        assert "Affected Connection:" in error_msg
        assert "user_input.form_data → database.query" in error_msg
        assert "**REDACTED**" in error_msg  # Value should be redacted
        assert "Security Recommendation:" in error_msg
        assert "Secure Example:" in error_msg
        assert "Immediate Actions:" in error_msg
        assert "Security Checklist:" in error_msg

    def test_get_error_summary(self):
        """Test error summary generation for logging."""
        formatter = EnhancedErrorFormatter()

        context = ConnectionContext(
            source_node="reader",
            source_port="output",
            target_node="writer",
            target_port="data",
            parameter_value=None,
            validation_mode="strict",
        )

        summary = formatter.get_error_summary(ErrorCategory.MISSING_PARAMETER, context)

        assert "Missing Required Parameter" in summary
        assert "reader.output → writer.data" in summary

    def test_indent_lines_internal_method(self):
        """Test the internal _indent_lines method."""
        formatter = EnhancedErrorFormatter()

        multi_line_text = "First line\nSecond line\nThird line"
        indented = formatter._indent_lines(multi_line_text, "  ")

        expected = "  First line\n  Second line\n  Third line"
        assert indented == expected


class TestValidationSuggestionEngineAdditional:
    """Additional tests to improve coverage of ValidationSuggestionEngine."""

    def test_get_dataflow_specific_suggestion(self):
        """Test DataFlow-specific suggestion generation."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="api",
            source_port="response",
            target_node="UserCreateNode",  # DataFlow node
            target_port="name",
            parameter_value=123,
            validation_mode="strict",
        )

        # Test type mismatch suggestion
        suggestion = engine.get_dataflow_specific_suggestion(
            ErrorCategory.TYPE_MISMATCH, context
        )
        assert suggestion is not None
        assert "DataFlow models" in suggestion
        assert "model field types" in suggestion

        # Test security violation suggestion
        suggestion = engine.get_dataflow_specific_suggestion(
            ErrorCategory.SECURITY_VIOLATION, context
        )
        assert suggestion is not None
        assert "DataFlow automatically sanitizes" in suggestion

        # Test missing parameter suggestion
        suggestion = engine.get_dataflow_specific_suggestion(
            ErrorCategory.MISSING_PARAMETER, context
        )
        assert suggestion is not None
        assert "model fields" in suggestion

    def test_get_common_connection_patterns(self):
        """Test retrieval of common connection patterns."""
        engine = ValidationSuggestionEngine()

        # Test CSVReaderNode patterns
        patterns = engine.get_common_connection_patterns("CSVReaderNode")
        assert len(patterns) == 2
        assert any("reader" in p and "data" in p for p in patterns)
        assert any("metadata.rows" in p for p in patterns)

        # Test HTTPRequestNode patterns
        patterns = engine.get_common_connection_patterns("HTTPRequestNode")
        assert len(patterns) == 2
        assert any("response.data" in p for p in patterns)
        assert any("status_code" in p for p in patterns)

        # Test LLMAgentNode patterns
        patterns = engine.get_common_connection_patterns("LLMAgentNode")
        assert len(patterns) == 2
        assert any("prompt" in p for p in patterns)
        assert any("result" in p for p in patterns)

        # Test SQLDatabaseNode patterns
        patterns = engine.get_common_connection_patterns("SQLDatabaseNode")
        assert len(patterns) == 2
        assert any("records" in p for p in patterns)
        assert any("table_name" in p for p in patterns)

        # Test unknown node type
        patterns = engine.get_common_connection_patterns("UnknownNode")
        assert patterns == []

    def test_suggestion_for_unknown_category_returns_none(self):
        """Test that unknown error categories still get suggestions."""
        engine = ValidationSuggestionEngine()

        context = ConnectionContext(
            source_node="source",
            source_port="output",
            target_node="target",
            target_port="input",
            parameter_value="test",
            validation_mode="strict",
        )

        # The engine should have templates for UNKNOWN category
        suggestion = engine.generate_suggestion(
            ErrorCategory.UNKNOWN, "SomeNode", context, "Unknown error occurred"
        )

        assert suggestion is not None
        assert "unexpected validation error" in suggestion.message


class TestConnectionContextAdditional:
    """Additional tests to improve coverage of ConnectionContext."""

    def test_sanitize_sql_injection_patterns(self):
        """Test sanitization of various SQL injection patterns."""
        # Test the specific line that was missed
        context = ConnectionContext(
            source_node="input",
            source_port="query",
            target_node="db",
            target_port="sql",
            parameter_value="UNION SELECT * FROM passwords",
            validation_mode="strict",
        )

        sanitized = context.get_sanitized_value()
        assert sanitized == "**SANITIZED**"


class TestConnectionErrorIntegration:
    """Integration tests for connection error message enhancement."""

    def test_complete_error_enhancement_flow(self):
        """Test the complete flow from error to enhanced message."""
        # This will test the integration once components are implemented
        categorizer = ErrorCategorizer()
        suggestion_engine = ValidationSuggestionEngine()
        formatter = EnhancedErrorFormatter()

        # Simulate a connection validation error
        original_error = TypeError("expected str but got int for parameter 'name'")

        context = ConnectionContext(
            source_node="data_source",
            source_port="user_info.name",
            target_node="user_create",
            target_port="name",
            parameter_value=123,  # Wrong type
            validation_mode="strict",
        )

        # Categorize error
        category = categorizer.categorize_error(original_error, "UserCreateNode")
        assert category == ErrorCategory.TYPE_MISMATCH

        # Generate suggestion
        suggestion = suggestion_engine.generate_suggestion(
            category, "UserCreateNode", context, str(original_error)
        )
        assert suggestion is not None

        # Format enhanced error
        enhanced_msg = formatter.format_enhanced_error(
            str(original_error), category, context, suggestion
        )

        # Verify complete enhanced message
        assert "data_source.user_info.name → user_create.name" in enhanced_msg
        assert (
            "Type Mismatch" in enhanced_msg
        )  # Check for exact format from error categorizer
        assert len(enhanced_msg.split("\n")) >= 4  # Multi-line structured message

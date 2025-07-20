"""
Enhanced error message formatting for connection validation errors.

Formats validation errors into structured, readable messages with
connection paths, categorization, suggestions, and examples.
"""

from typing import Optional

from .connection_context import ConnectionContext
from .error_categorizer import ErrorCategorizer, ErrorCategory
from .suggestion_engine import ValidationSuggestion


class EnhancedErrorFormatter:
    """Formats validation errors into enhanced, actionable error messages."""

    def __init__(self):
        self.categorizer = ErrorCategorizer()

    def format_enhanced_error(
        self,
        original_error: str,
        error_category: ErrorCategory,
        connection_context: ConnectionContext,
        suggestion: Optional[ValidationSuggestion] = None,
    ) -> str:
        """Format a comprehensive error message with all enhancement details.

        Args:
            original_error: Original validation error message
            error_category: Categorized error type
            connection_context: Context about the failing connection
            suggestion: Optional actionable suggestion

        Returns:
            Formatted error message with structured sections
        """
        sections = []

        # Header with error category
        category_desc = self.categorizer.get_category_description(error_category)
        severity = self.categorizer.get_severity_level(error_category)

        sections.append(f"🚨 Connection Validation Error: {category_desc} [{severity}]")
        sections.append("=" * 60)

        # Problem section
        sections.append("\n📋 Problem:")
        sections.append(f"    {original_error}")

        # Connection path section
        sections.append("\n🔗 Connection:")
        connection_path = connection_context.get_connection_path()
        sections.append(f"    {connection_path}")

        # Parameter details (sanitized)
        if not connection_context.is_security_sensitive():
            value_repr = connection_context.get_sanitized_value()
            sections.append(f"    Value: {value_repr}")
        else:
            sections.append("    Value: **REDACTED** (security-sensitive)")

        sections.append(f"    Validation Mode: {connection_context.validation_mode}")

        # Suggestion section
        if suggestion:
            sections.append("\n💡 Suggestion:")
            sections.append(f"    {suggestion.message}")

            # Code example
            if suggestion.code_example:
                sections.append("\n📝 Example:")
                example_lines = suggestion.code_example.split("\n")
                for line in example_lines:
                    sections.append(f"    {line}")

            # Alternative approaches
            if suggestion.alternative_approaches:
                sections.append("\n🔄 Alternatives:")
                for i, alt in enumerate(suggestion.alternative_approaches, 1):
                    sections.append(f"    {i}. {alt}")

            # Documentation link
            if suggestion.documentation_link:
                sections.append("\n📚 Documentation:")
                sections.append(f"    {suggestion.documentation_link}")
        else:
            sections.append("\n💡 Suggestion:")
            sections.append("    Check node documentation for parameter requirements.")
            sections.append("    Verify data types and connection mapping.")

        # Troubleshooting tips
        sections.append("\n🛠️  Quick Troubleshooting:")
        sections.append("    1. Check the source node output format")
        sections.append("    2. Verify target node parameter requirements")
        sections.append("    3. Test with simplified data first")
        sections.append(
            "    4. Review connection syntax: workflow.add_connection(source, source_port, target, target_port)"
        )

        return "\n".join(sections)

    def format_simple_error(
        self, original_error: str, connection_context: ConnectionContext
    ) -> str:
        """Format a simple enhanced error message for warn mode.

        Args:
            original_error: Original validation error message
            connection_context: Context about the failing connection

        Returns:
            Simple formatted error message
        """
        connection_path = connection_context.get_connection_path()
        return f"Connection validation warning: {connection_path} - {original_error}"

    def format_security_error(
        self,
        original_error: str,
        connection_context: ConnectionContext,
        suggestion: Optional[ValidationSuggestion] = None,
    ) -> str:
        """Format security-specific error message with appropriate warnings.

        Args:
            original_error: Original security error message
            connection_context: Context about the failing connection
            suggestion: Optional security-specific suggestion

        Returns:
            Security-focused error message
        """
        sections = []

        sections.append("🔒 SECURITY ALERT: Potential Security Vulnerability")
        sections.append("=" * 60)

        sections.append("\n⚠️  Security Issue:")
        sections.append(f"    {original_error}")

        sections.append("\n🔗 Affected Connection:")
        connection_path = connection_context.get_connection_path()
        sections.append(f"    {connection_path}")

        # Always redact security-sensitive values
        sections.append("    Value: **REDACTED** (potential security risk)")

        if suggestion:
            sections.append("\n🛡️  Security Recommendation:")
            sections.append(f"    {suggestion.message}")

            if suggestion.code_example:
                sections.append("\n🔐 Secure Example:")
                example_lines = suggestion.code_example.split("\n")
                for line in example_lines:
                    sections.append(f"    {line}")

        sections.append("\n🚨 Immediate Actions:")
        sections.append("    1. Review the data source for potential attacks")
        sections.append("    2. Implement input validation and sanitization")
        sections.append("    3. Use parameterized queries for database operations")
        sections.append("    4. Consider implementing rate limiting")

        sections.append("\n📋 Security Checklist:")
        sections.append("    □ Input validation implemented")
        sections.append("    □ Output encoding applied")
        sections.append("    □ Parameterized queries used")
        sections.append("    □ Access controls verified")

        return "\n".join(sections)

    def get_error_summary(
        self, error_category: ErrorCategory, connection_context: ConnectionContext
    ) -> str:
        """Get a brief summary of the error for logging.

        Args:
            error_category: Categorized error type
            connection_context: Context about the failing connection

        Returns:
            Brief error summary
        """
        category_desc = self.categorizer.get_category_description(error_category)
        connection_path = connection_context.get_connection_path()

        return f"{category_desc}: {connection_path}"

    def _indent_lines(self, text: str, indent: str = "    ") -> str:
        """Indent all lines in text with the given prefix.

        Args:
            text: Text to indent
            indent: Indentation string

        Returns:
            Indented text
        """
        lines = text.split("\n")
        return "\n".join(f"{indent}{line}" for line in lines)

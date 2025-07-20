"""
Connection context tracking for enhanced error messages.

Provides detailed information about connection sources and targets
to enable precise error message generation with connection paths.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ConnectionContext:
    """Context information for a specific parameter connection.

    Tracks the source and target of a connection to enable detailed
    error message generation with connection path reconstruction.
    """

    source_node: str
    """Source node ID in the workflow"""

    source_port: Optional[str]
    """Output port/parameter from source node (e.g., 'result.data')"""

    target_node: str
    """Target node ID in the workflow"""

    target_port: str
    """Input parameter on target node"""

    parameter_value: Any
    """The actual parameter value being passed through connection"""

    validation_mode: str
    """Validation mode: 'off', 'warn', or 'strict'"""

    def get_connection_path(self) -> str:
        """Generate human-readable connection path string.

        Returns:
            Connection path in format: source_node.source_port → target_node.target_port
        """
        source_part = self.source_node
        if self.source_port:
            source_part = f"{self.source_node}.{self.source_port}"

        target_part = f"{self.target_node}.{self.target_port}"

        return f"{source_part} → {target_part}"

    def get_sanitized_value(self) -> str:
        """Get sanitized representation of parameter value for error messages.

        Sanitizes sensitive information like SQL injection attempts, passwords, etc.

        Returns:
            Safe string representation of the parameter value
        """
        if self.parameter_value is None:
            return "None"

        value_str = str(self.parameter_value)

        # Detect and sanitize potential security issues
        security_patterns = [
            "drop table",
            "delete from",
            "insert into",
            "update set",
            "union select",
            "exec(",
            "eval(",
            "script>",
            "password",
            "secret",
            "token",
            "key",
        ]

        for pattern in security_patterns:
            if pattern.lower() in value_str.lower():
                return "**SANITIZED**"

        # Truncate very long values
        if len(value_str) > 100:
            return f"{value_str[:97]}..."

        return value_str

    def is_security_sensitive(self) -> bool:
        """Check if the parameter value contains security-sensitive data.

        Returns:
            True if the value appears to contain sensitive information
        """
        if self.parameter_value is None:
            return False

        value_str = str(self.parameter_value).lower()

        sensitive_indicators = [
            "password",
            "secret",
            "token",
            "key",
            "auth",
            "drop",
            "delete",
            "insert",
            "update",
            "exec",
            "union",
            "select",
            "script",
            "eval",
        ]

        return any(indicator in value_str for indicator in sensitive_indicators)

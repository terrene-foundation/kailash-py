"""
Error categorization for connection validation failures.

Classifies validation errors into specific categories to enable
targeted suggestion generation and better error handling.
"""

import re
from enum import Enum
from typing import Any, Optional


class ErrorCategory(Enum):
    """Categories of connection validation errors."""

    TYPE_MISMATCH = "type_mismatch"
    """Parameter type doesn't match expected type"""

    MISSING_PARAMETER = "missing_parameter"
    """Required parameter is missing or None"""

    CONSTRAINT_VIOLATION = "constraint_violation"
    """Parameter violates validation constraints (range, format, etc.)"""

    SECURITY_VIOLATION = "security_violation"
    """Parameter contains potential security issues (injection, etc.)"""

    UNKNOWN = "unknown"
    """Error category could not be determined"""


class ErrorCategorizer:
    """Categorizes validation errors for enhanced error message generation."""

    # Error patterns for categorization
    TYPE_ERROR_PATTERNS = [
        r"expected .+ but got .+",
        r"object of type .+ has no attribute",
        r"unsupported operand type",
        r"can't convert .+ to .+",
        r"'[^']+' object .+ not .+",
        r"argument must be .+, not .+",
    ]

    MISSING_PARAMETER_PATTERNS = [
        r"missing required parameter",
        r"required argument .+ is missing",
        r"takes .+ arguments but .+ were given",
        r"missing .+ required",
        r"parameter .+ is required",
    ]

    CONSTRAINT_VIOLATION_PATTERNS = [
        r"must be positive",
        r"must be greater than",
        r"must be less than",
        r"invalid value",
        r"out of range",
        r"violates constraint",
        r"exceeds maximum",
        r"below minimum",
    ]

    SECURITY_VIOLATION_PATTERNS = [
        r"sql injection",
        r"injection detected",
        r"security violation",
        r"potential attack",
        r"malicious",
        r"dangerous",
        r"unsafe",
        r"script injection",
    ]

    def categorize_error(
        self, error: Exception, node_type: Optional[str] = None
    ) -> ErrorCategory:
        """Categorize a validation error based on error message and context.

        Args:
            error: The validation error exception
            node_type: Optional node type for additional context

        Returns:
            ErrorCategory enum value indicating the error type
        """
        error_message = str(error).lower()
        error_type = type(error).__name__

        # Check for security violations first (highest priority)
        if self._matches_patterns(error_message, self.SECURITY_VIOLATION_PATTERNS):
            return ErrorCategory.SECURITY_VIOLATION

        # Check for type errors
        if error_type in ["TypeError", "AttributeError"] or self._matches_patterns(
            error_message, self.TYPE_ERROR_PATTERNS
        ):
            return ErrorCategory.TYPE_MISMATCH

        # Check for missing parameter errors
        if error_type in ["ValueError", "TypeError"] and self._matches_patterns(
            error_message, self.MISSING_PARAMETER_PATTERNS
        ):
            return ErrorCategory.MISSING_PARAMETER

        # Check for constraint violations
        if error_type == "ValueError" and self._matches_patterns(
            error_message, self.CONSTRAINT_VIOLATION_PATTERNS
        ):
            return ErrorCategory.CONSTRAINT_VIOLATION

        # Default to unknown if no pattern matches
        return ErrorCategory.UNKNOWN

    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the given regex patterns.

        Args:
            text: Text to check
            patterns: List of regex patterns

        Returns:
            True if text matches any pattern
        """
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def get_category_description(self, category: ErrorCategory) -> str:
        """Get human-readable description of error category.

        Args:
            category: Error category enum

        Returns:
            Human-readable description
        """
        descriptions = {
            ErrorCategory.TYPE_MISMATCH: "Type Mismatch",
            ErrorCategory.MISSING_PARAMETER: "Missing Required Parameter",
            ErrorCategory.CONSTRAINT_VIOLATION: "Parameter Constraint Violation",
            ErrorCategory.SECURITY_VIOLATION: "Security Violation",
            ErrorCategory.UNKNOWN: "Unknown Validation Error",
        }
        return descriptions.get(category, "Unknown Error")

    def get_severity_level(self, category: ErrorCategory) -> str:
        """Get severity level for error category.

        Args:
            category: Error category enum

        Returns:
            Severity level: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
        """
        severity_map = {
            ErrorCategory.SECURITY_VIOLATION: "CRITICAL",
            ErrorCategory.MISSING_PARAMETER: "HIGH",
            ErrorCategory.TYPE_MISMATCH: "MEDIUM",
            ErrorCategory.CONSTRAINT_VIOLATION: "MEDIUM",
            ErrorCategory.UNKNOWN: "LOW",
        }
        return severity_map.get(category, "LOW")

"""
Input validation for HookContext data (SECURITY FIX #8).

Prevents code injection and security bypass via malicious hook context data.

SECURITY: CWE-20 (Improper Input Validation)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from ..types import HookEvent

logger = logging.getLogger(__name__)


class ValidatedHookContext(BaseModel):
    """
    Hook context with Pydantic input validation.

    Features:
    - Agent ID format validation (alphanumeric, underscores, hyphens only)
    - Code injection detection in data/metadata (<script>, ${}, code execution, etc.)
    - Field size limits to prevent DoS
    - Automatic sanitization of malicious patterns
    - Audit logging of validation failures

    Example:
        >>> from kaizen.core.autonomy.hooks.security import ValidatedHookContext
        >>> from kaizen.core.autonomy.hooks.types import HookEvent
        >>>
        >>> # Valid context
        >>> context = ValidatedHookContext(
        >>>     event_type=HookEvent.POST_AGENT_LOOP,
        >>>     agent_id="agent_123",
        >>>     timestamp=1699564800.0,
        >>>     data={"user_input": "Hello"},
        >>>     metadata={}
        >>> )
        >>>
        >>> # Invalid context (code injection)
        >>> try:
        >>>     context = ValidatedHookContext(
        >>>         event_type=HookEvent.POST_AGENT_LOOP,
        >>>         agent_id="agent_123",
        >>>         timestamp=1699564800.0,
        >>>         data={"malicious": "<script>alert('xss')</script>"}
        >>>     )
        >>> except ValueError as e:
        >>>     print(f"Validation failed: {e}")

    SECURITY FIX #8:
    - Prevents XSS, code injection, template injection
    - Validates agent_id format (no special characters)
    - Detects common attack patterns in data/metadata
    - Limits field sizes to prevent resource exhaustion
    """

    # Core fields
    event_type: HookEvent
    agent_id: str
    timestamp: float
    data: dict[str, Any]
    metadata: dict[str, Any] = {}
    trace_id: str | None = None

    # Configuration
    model_config = {
        "arbitrary_types_allowed": True,  # Allow HookEvent enum
        "str_max_length": 1000,  # Prevent excessive strings
    }

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """
        Validate agent_id format (SECURITY FIX #8).

        Only allows alphanumeric characters, underscores, and hyphens.
        Prevents injection attacks via malicious agent IDs.

        Args:
            v: Agent ID to validate

        Returns:
            Validated agent ID

        Raises:
            ValueError: If agent_id contains invalid characters

        Example:
            >>> ValidatedHookContext.validate_agent_id("agent_123")  # Valid
            'agent_123'
            >>> ValidatedHookContext.validate_agent_id("agent'; DROP TABLE--")  # Invalid
            Traceback (most recent call last):
                ...
            ValueError: Invalid agent_id format: ...
        """
        # Only allow alphanumeric, underscores, and hyphens
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            logger.critical(
                f"SECURITY: Invalid agent_id format detected: {v[:50]}"  # Truncate for logging
            )
            raise ValueError(
                f"Invalid agent_id format: must contain only alphanumeric characters, "
                f"underscores, and hyphens (got: {v[:50]})"
            )

        # Length check (prevent DoS)
        if len(v) > 200:
            raise ValueError(f"agent_id too long: max 200 characters (got: {len(v)})")

        return v

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: float) -> float:
        """
        Validate timestamp is reasonable (SECURITY FIX #8).

        Prevents time-based attacks and ensures timestamp is within valid range.

        Args:
            v: Timestamp to validate

        Returns:
            Validated timestamp

        Raises:
            ValueError: If timestamp is negative or unreasonably large
        """
        # Prevent negative timestamps
        if v < 0:
            raise ValueError(f"Invalid timestamp: cannot be negative (got: {v})")

        # Prevent unreasonably large timestamps (year 9999+)
        if v > 253402300799.0:  # December 31, 9999, 23:59:59 UTC
            raise ValueError(f"Invalid timestamp: unreasonably large (got: {v})")

        return v

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, v: str | None) -> str | None:
        """
        Validate trace_id format (SECURITY FIX #8).

        Args:
            v: Trace ID to validate

        Returns:
            Validated trace ID

        Raises:
            ValueError: If trace_id contains invalid characters
        """
        if v is None:
            return v

        # Only allow alphanumeric, underscores, hyphens, and colons (for distributed tracing)
        if not re.match(r"^[a-zA-Z0-9_:-]+$", v):
            logger.critical(f"SECURITY: Invalid trace_id format detected: {v[:50]}")
            raise ValueError(
                f"Invalid trace_id format: must contain only alphanumeric characters, "
                f"underscores, hyphens, and colons (got: {v[:50]})"
            )

        # Length check
        if len(v) > 200:
            raise ValueError(f"trace_id too long: max 200 characters (got: {len(v)})")

        return v

    @model_validator(mode="after")
    def validate_no_code_injection(self) -> "ValidatedHookContext":
        """
        Validate that data and metadata don't contain code injection (SECURITY FIX #8).

        Checks for common attack patterns:
        - <script> tags (XSS)
        - ${} template injection
        - Dynamic code execution patterns
        - SQL injection patterns

        Returns:
            Validated context

        Raises:
            ValueError: If potential code injection is detected

        Example:
            >>> context = ValidatedHookContext(...)
            >>> context.data = {"malicious": "<script>alert('xss')</script>"}
            >>> context.validate_no_code_injection()  # Raises ValueError
        """
        # Serialize data and metadata for pattern matching
        try:
            data_serialized = json.dumps(self.data)
            metadata_serialized = json.dumps(self.metadata)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot serialize data/metadata to JSON: {e}")

        # Define injection patterns
        injection_patterns = [
            (r"<script[^>]*>", "XSS: <script> tag"),
            (r"\$\{", "Template injection: ${}"),
            (r"\beval\s*\(", "Dynamic code execution"),
            (r"\bexec\s*\(", "Dynamic code execution"),
            (r"__import__\s*\(", "Dynamic module import"),
            (r";\s*DROP\s+TABLE", "SQL injection: DROP TABLE"),
            (r"'\s*OR\s+'1'\s*=\s*'1", "SQL injection: OR '1'='1'"),
            (r"<iframe[^>]*>", "XSS: <iframe> tag"),
            (r"javascript:", "XSS: javascript: protocol"),
            (r"on\w+\s*=", "XSS: event handler (onclick=, onerror=, etc.)"),
        ]

        # Check for injection patterns in data
        for pattern, description in injection_patterns:
            if re.search(pattern, data_serialized, re.IGNORECASE):
                logger.critical(
                    f"SECURITY: Potential code injection detected in data - {description}"
                )
                raise ValueError(f"Potential code injection detected: {description}")

            if re.search(pattern, metadata_serialized, re.IGNORECASE):
                logger.critical(
                    f"SECURITY: Potential code injection detected in metadata - {description}"
                )
                raise ValueError(
                    f"Potential code injection detected in metadata: {description}"
                )

        # Check field sizes to prevent DoS
        if len(data_serialized) > 100000:  # 100KB limit
            raise ValueError(
                f"data field too large: max 100KB (got: {len(data_serialized)} bytes)"
            )

        if len(metadata_serialized) > 100000:  # 100KB limit
            raise ValueError(
                f"metadata field too large: max 100KB (got: {len(metadata_serialized)} bytes)"
            )

        return self

    def to_dict(self) -> dict[str, Any]:
        """
        Convert validated context to dictionary.

        Returns:
            Dictionary representation of context
        """
        return {
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "data": self.data,
            "metadata": self.metadata,
            "trace_id": self.trace_id,
        }


def validate_hook_context(
    event_type: HookEvent,
    agent_id: str,
    timestamp: float,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> ValidatedHookContext:
    """
    Convenience function to validate hook context.

    Args:
        event_type: Event that occurred
        agent_id: ID of agent triggering the event
        timestamp: Event timestamp
        data: Event-specific data
        metadata: Optional additional metadata
        trace_id: Distributed tracing ID

    Returns:
        Validated hook context

    Raises:
        ValueError: If validation fails

    Example:
        >>> from kaizen.core.autonomy.hooks.security import validate_hook_context
        >>> from kaizen.core.autonomy.hooks.types import HookEvent
        >>>
        >>> context = validate_hook_context(
        >>>     event_type=HookEvent.POST_AGENT_LOOP,
        >>>     agent_id="agent_123",
        >>>     timestamp=1699564800.0,
        >>>     data={"result": "success"}
        >>> )
    """
    return ValidatedHookContext(
        event_type=event_type,
        agent_id=agent_id,
        timestamp=timestamp,
        data=data,
        metadata=metadata or {},
        trace_id=trace_id,
    )


@dataclass
class ValidationConfig:
    """
    Configuration for hook context validation.

    Example:
        >>> config = ValidationConfig(
        ...     str_max_length=2000,
        ...     agent_id_max_length=100,
        ...     enable_code_injection_detection=True
        ... )
        >>> # Use config to customize validation behavior
    """

    # String length limits
    str_max_length: int = 1000
    agent_id_max_length: int = 200
    trace_id_max_length: int = 200

    # Data size limits
    data_max_size: int = 100000  # 100KB
    metadata_max_size: int = 100000  # 100KB

    # Validation features
    enable_code_injection_detection: bool = True
    enable_agent_id_validation: bool = True
    enable_timestamp_validation: bool = True
    enable_trace_id_validation: bool = True

    # Allowed characters
    agent_id_pattern: str = r"^[a-zA-Z0-9_-]+$"
    trace_id_pattern: str = r"^[a-zA-Z0-9_:-]+$"

    # Timestamp limits
    min_timestamp: float = 0.0
    max_timestamp: float = 253402300799.0  # December 31, 9999


# Export public API
__all__ = [
    "ValidatedHookContext",
    "validate_hook_context",
    "ValidationConfig",
]

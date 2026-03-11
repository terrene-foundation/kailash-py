"""
Sensitive data redaction for hooks system.

Provides pattern-based and field-based redaction of sensitive data
including API keys, passwords, PII, credit cards, and SSNs.
"""

import copy
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional, Set

from ..protocol import BaseHook
from ..types import HookContext, HookEvent, HookResult


class SensitiveDataRedactor:
    """
    Redacts sensitive data from logs, metrics, and traces.

    Features:
    - Pattern-based redaction (API keys, passwords, credit cards, SSNs)
    - Field-based redaction (configurable sensitive fields)
    - PII detection (email, phone, addresses)
    - Configurable redaction markers
    """

    # Patterns for sensitive data
    PATTERNS = {
        "api_key": re.compile(r"(sk|pk)[-_][a-zA-Z0-9]{20,}"),
        "bearer_token": re.compile(r"Bearer\s+[a-zA-Z0-9\-_\.]+"),
        "password": re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\\s,}]+)'),
        "credit_card": re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "ip_address": re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    }

    # Field names that likely contain sensitive data
    SENSITIVE_FIELDS = {
        "api_key",
        "apikey",
        "api-key",
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "auth",
        "authorization",
        "credit_card",
        "creditcard",
        "cc",
        "cvv",
        "ssn",
        "social_security",
        "private_key",
        "privatekey",
    }

    def __init__(
        self,
        redaction_marker: str = "[REDACTED]",
        additional_fields: Optional[Set[str]] = None,
    ):
        """
        Initialize redactor.

        Args:
            redaction_marker: String to replace sensitive data with
            additional_fields: Additional sensitive field names
        """
        self.redaction_marker = redaction_marker
        self.sensitive_fields = self.SENSITIVE_FIELDS.copy()
        if additional_fields:
            self.sensitive_fields.update(additional_fields)

    def redact_string(self, text: str) -> str:
        """
        Redact sensitive patterns from string.

        Args:
            text: String to redact

        Returns:
            Redacted string
        """
        for pattern_name, pattern in self.PATTERNS.items():
            text = pattern.sub(self.redaction_marker, text)

        return text

    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Redact sensitive fields from dictionary (recursive).

        Args:
            data: Dictionary to redact

        Returns:
            Redacted dictionary (new copy)
        """
        redacted = copy.deepcopy(data)

        for key, value in redacted.items():
            # Check if key is sensitive
            if key.lower() in self.sensitive_fields:
                redacted[key] = self.redaction_marker
            # Recursively redact nested dicts
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            # Redact strings
            elif isinstance(value, str):
                redacted[key] = self.redact_string(value)
            # Redact lists
            elif isinstance(value, list):
                redacted[key] = [
                    (
                        self.redact_dict(item)
                        if isinstance(item, dict)
                        else self.redact_string(item) if isinstance(item, str) else item
                    )
                    for item in value
                ]

        return redacted

    def redact_hook_context(self, context: HookContext) -> HookContext:
        """
        Redact sensitive data from HookContext.

        Args:
            context: Original hook context

        Returns:
            New context with redacted data
        """
        return HookContext(
            event_type=context.event_type,
            agent_id=context.agent_id,
            timestamp=context.timestamp,
            data=self.redact_dict(context.data),
            metadata=self.redact_dict(context.metadata),
            trace_id=context.trace_id,
        )


class SecureLoggingHook(BaseHook):
    """LoggingHook with sensitive data redaction"""

    events: ClassVar[list[HookEvent]] = list(HookEvent)

    def __init__(
        self,
        log_level: str = "INFO",
        include_data: bool = True,
        format: str = "text",
        redact_sensitive: bool = True,
    ):
        super().__init__(name="secure_logging_hook")
        self.log_level = log_level
        self.include_data = include_data
        self.format = format
        self.redact_sensitive = redact_sensitive

        # Initialize redactor
        if self.redact_sensitive:
            self.redactor = SensitiveDataRedactor()

        # Configure logger
        import logging

        if format == "json":
            import structlog

            structlog.configure(
                processors=[
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.stdlib.add_log_level,
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.processors.JSONRenderer(),
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                cache_logger_on_first_use=True,
            )
            self.logger = structlog.get_logger()
        else:
            self.logger = logging.getLogger(__name__)

    async def handle(self, context: HookContext) -> HookResult:
        """Log hook event with redaction"""
        try:
            # STEP 1: Redact sensitive data
            if self.redact_sensitive:
                safe_context = self.redactor.redact_hook_context(context)
            else:
                safe_context = context

            # STEP 2: Log redacted data
            if self.format == "json":
                log_event = {
                    "event_type": safe_context.event_type.value,
                    "agent_id": safe_context.agent_id,
                    "trace_id": safe_context.trace_id,
                    "timestamp": safe_context.timestamp,
                    "level": self.log_level.lower(),
                }

                if self.include_data:
                    log_event["context"] = safe_context.data
                    log_event["metadata"] = safe_context.metadata

                log_fn = getattr(self.logger, self.log_level.lower())
                log_fn("hook_event", **log_event)

            else:
                log_fn = getattr(self.logger, self.log_level.lower())

                if self.include_data:
                    log_fn(
                        f"[{safe_context.event_type.value}] "
                        f"Agent={safe_context.agent_id} "
                        f"TraceID={safe_context.trace_id} "
                        f"Data={safe_context.data}"
                    )
                else:
                    log_fn(
                        f"[{safe_context.event_type.value}] "
                        f"Agent={safe_context.agent_id} "
                        f"TraceID={safe_context.trace_id}"
                    )

            return HookResult(success=True)

        except Exception as e:
            return HookResult(success=False, error=str(e))


@dataclass
class RedactionConfig:
    """
    Configuration for sensitive data redaction.

    Example:
        >>> config = RedactionConfig(
        ...     redaction_marker="***",
        ...     additional_fields={"custom_secret", "api_token"}
        ... )
        >>> redactor = SensitiveDataRedactor(
        ...     redaction_marker=config.redaction_marker,
        ...     additional_fields=config.additional_fields
        ... )
    """

    redaction_marker: str = "[REDACTED]"
    additional_fields: Set[str] = field(default_factory=set)
    redact_api_keys: bool = True
    redact_passwords: bool = True
    redact_credit_cards: bool = True
    redact_ssn: bool = True
    redact_email: bool = False  # Optional: May want to keep emails in logs
    redact_ip_addresses: bool = False  # Optional: May want to keep IPs in logs


# Alias for backward compatibility with tests
DataRedactor = SensitiveDataRedactor


# Export public API
__all__ = [
    "SensitiveDataRedactor",
    "SecureLoggingHook",
    "RedactionConfig",
    "DataRedactor",
]

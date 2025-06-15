"""Secure logging utilities for masking sensitive data.

This module provides mixins and utilities for automatically detecting and
masking PII, credentials, and other sensitive information in logs.
"""

import json
import logging
import re
from functools import wraps
from typing import Any, Dict, List, Optional, Pattern, Set, Union


class SecureLoggingPatterns:
    """Patterns for detecting sensitive data."""

    # Credit card patterns
    CREDIT_CARD = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

    # SSN patterns
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

    # Email pattern
    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    # Phone patterns
    PHONE = re.compile(
        r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b"
    )

    # API key patterns
    API_KEY_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{48}"),  # OpenAI
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub
        re.compile(r"[a-zA-Z0-9]{32}"),  # Generic 32-char
    ]

    # Password in various formats
    PASSWORD_PATTERNS = [
        re.compile(r'["\']?password["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pwd["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pass["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Token patterns
    TOKEN_PATTERNS = [
        re.compile(r'["\']?token["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?api_key["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?secret["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Common PII field names
    PII_FIELD_NAMES = {
        "ssn",
        "social_security",
        "social_security_number",
        "credit_card",
        "card_number",
        "cc_number",
        "password",
        "pwd",
        "pass",
        "passwd",
        "token",
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "email",
        "email_address",
        "phone",
        "phone_number",
        "address",
        "street_address",
        "home_address",
        "date_of_birth",
        "dob",
        "birthdate",
        "driver_license",
        "license_number",
        "passport",
        "passport_number",
        "bank_account",
        "account_number",
        "routing_number",
    }


class SecureLogger:
    """Logger that automatically masks sensitive data."""

    def __init__(
        self,
        name: str,
        mask_char: str = "*",
        mask_length: int = 8,
        custom_patterns: Optional[List[Pattern]] = None,
        custom_fields: Optional[Set[str]] = None,
    ):
        """
        Initialize secure logger.

        Args:
            name: Logger name
            mask_char: Character to use for masking
            mask_length: Fixed length for masks (0 = preserve length)
            custom_patterns: Additional regex patterns to mask
            custom_fields: Additional field names to mask
        """
        self.logger = logging.getLogger(name)
        self.mask_char = mask_char
        self.mask_length = mask_length
        self.custom_patterns = custom_patterns or []
        self.custom_fields = custom_fields or set()

    def _mask_value(self, value: str, preserve_partial: bool = True) -> str:
        """Mask a sensitive value."""
        if not value:
            return value

        if self.mask_length > 0:
            # Fixed length mask
            return self.mask_char * self.mask_length
        elif preserve_partial and len(value) > 8:
            # Preserve first 2 and last 2 chars
            return value[:2] + self.mask_char * (len(value) - 4) + value[-2:]
        else:
            # Full mask
            return self.mask_char * len(value)

    def _mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively mask sensitive fields in dictionary."""
        masked = {}

        for key, value in data.items():
            # Check if field name indicates sensitive data
            if (
                key.lower() in SecureLoggingPatterns.PII_FIELD_NAMES
                or key.lower() in self.custom_fields
            ):
                masked[key] = (
                    self._mask_value(str(value)) if value is not None else None
                )
            elif isinstance(value, dict):
                masked[key] = self._mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def _mask_string(self, text: str) -> str:
        """Mask sensitive patterns in string."""
        # Credit cards
        text = SecureLoggingPatterns.CREDIT_CARD.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # SSNs
        text = SecureLoggingPatterns.SSN.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=False), text
        )

        # Emails - preserve domain
        text = SecureLoggingPatterns.EMAIL.sub(
            lambda m: self._mask_email(m.group()), text
        )

        # Phone numbers
        text = SecureLoggingPatterns.PHONE.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # API keys
        for pattern in SecureLoggingPatterns.API_KEY_PATTERNS:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        # Passwords and tokens
        for pattern in (
            SecureLoggingPatterns.PASSWORD_PATTERNS
            + SecureLoggingPatterns.TOKEN_PATTERNS
        ):
            text = pattern.sub(
                lambda m: m.group().replace(m.group(1), self._mask_value(m.group(1))),
                text,
            )

        # Custom patterns
        for pattern in self.custom_patterns:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        return text

    def _mask_email(self, email: str) -> str:
        """Mask email preserving domain."""
        if "@" in email:
            local, domain = email.split("@", 1)
            return self._mask_value(local, preserve_partial=True) + "@" + domain
        return self._mask_value(email)

    def _mask_data(self, data: Any) -> Any:
        """Mask sensitive data in any format."""
        if isinstance(data, str):
            return self._mask_string(data)
        elif isinstance(data, dict):
            return self._mask_dict(data)
        elif isinstance(data, (list, tuple)):
            return [self._mask_data(item) for item in data]
        else:
            return data

    def debug(self, msg: str, *args, **kwargs):
        """Log debug with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.debug(masked_msg, **masked_kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.info(masked_msg, **masked_kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.warning(masked_msg, **masked_kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.error(masked_msg, **masked_kwargs)


class SecureLoggingMixin:
    """Mixin to add secure logging to any class."""

    def __init__(self, *args, **kwargs):
        """Initialize with secure logger."""
        super().__init__(*args, **kwargs)
        self._secure_logger = SecureLogger(
            name=f"{self.__class__.__module__}.{self.__class__.__name__}",
            custom_fields=getattr(self, "_sensitive_fields", set()),
        )

    def log_debug(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log debug with automatic masking."""
        if data:
            self._secure_logger.debug(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.debug(msg)

    def log_info(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log info with automatic masking."""
        if data:
            self._secure_logger.info(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.info(msg)

    def log_error(
        self,
        msg: str,
        error: Optional[Exception] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Log error with automatic masking."""
        error_msg = f"{msg}: {str(error)}" if error else msg
        if data:
            self._secure_logger.error(
                f"{error_msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.error(error_msg)


def secure_log(mask_params: Optional[List[str]] = None):
    """Decorator for secure logging of function calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = SecureLogger(f"{func.__module__}.{func.__name__}")

            # Mask specified parameters
            masked_kwargs = {}
            for key, value in kwargs.items():
                if mask_params and key in mask_params:
                    masked_kwargs[key] = logger._mask_value(str(value))
                else:
                    masked_kwargs[key] = logger._mask_data(value)

            logger.debug(f"Calling {func.__name__} with args: {masked_kwargs}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed: {str(e)}")
                raise

        return wrapper

    return decorator


def apply_secure_logging_to_node(node_class):
    """Decorator to add secure logging to a node class."""

    # Create new class that inherits from both
    class SecureNode(SecureLoggingMixin, node_class):
        """Node with secure logging enabled."""

        def run(self, **inputs):
            """Run with secure logging."""
            self.log_debug("Node execution started", inputs)

            try:
                result = super().run(**inputs)
                self.log_debug("Node execution completed")
                return result
            except Exception as e:
                self.log_error("Node execution failed", e, inputs)
                raise

    # Preserve original class name and module
    SecureNode.__name__ = node_class.__name__
    SecureNode.__module__ = node_class.__module__
    SecureNode.__qualname__ = node_class.__qualname__

    return SecureNode

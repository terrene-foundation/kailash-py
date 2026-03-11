"""Audit logging configuration (TODO-310F).

Defines AuditConfig dataclass for configuring audit logging behavior,
backends, exclusions, and PII filtering.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union


@dataclass
class AuditConfig:
    """Configuration for audit logging.

    Attributes:
        enabled: Whether audit logging is enabled (default: True)
        backend: Storage backend - "logging", "dataflow", or custom callable
        dataflow_model_name: Model name for DataFlow backend
        log_level: Log level for logging backend
        log_request_body: Whether to log request bodies (default: False)
        log_response_body: Whether to log response bodies (default: False)
        max_body_log_size: Maximum body size to log in bytes (default: 10KB)
        include_query_params: Whether to include query params in metadata
        include_request_headers: Whether to include request headers in metadata
        exclude_paths: Paths to exclude from audit logging
        exclude_methods: HTTP methods to exclude
        redact_headers: Header names to redact
        redact_fields: Field names to redact in bodies
        redact_replacement: Replacement string for redacted values
    """

    enabled: bool = True

    # Backend configuration
    backend: Union[str, Callable] = "logging"
    dataflow_model_name: str = "AuditRecord"
    log_level: str = "INFO"

    # What to log
    log_request_body: bool = False
    log_response_body: bool = False
    max_body_log_size: int = 10 * 1024  # 10KB
    include_query_params: bool = True
    include_request_headers: bool = False

    # Exclusions
    exclude_paths: List[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/docs", "/openapi.json"]
    )
    exclude_methods: List[str] = field(default_factory=lambda: ["OPTIONS"])

    # PII filtering
    redact_headers: List[str] = field(
        default_factory=lambda: [
            "Authorization",
            "Cookie",
            "Set-Cookie",
            "X-API-Key",
            "X-Auth-Token",
            "X-Session-ID",
        ]
    )
    redact_fields: List[str] = field(
        default_factory=lambda: [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credit_card",
            "card_number",
            "cvv",
            "ssn",
            "social_security",
            "access_token",
            "refresh_token",
        ]
    )
    redact_replacement: str = "[REDACTED]"

    # Proxy trust configuration
    # SECURITY: Only trust proxy headers (X-Forwarded-For, X-Real-IP) when
    # the application is deployed behind a trusted reverse proxy.
    # When False, client IP is taken from the direct TCP connection only.
    trust_proxy_headers: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if self.max_body_log_size < 0:
            raise ValueError("max_body_log_size cannot be negative")
        if self.log_level.upper() not in (
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ):
            raise ValueError(
                f"Invalid log_level: {self.log_level}. "
                "Must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
            )

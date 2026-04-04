# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Fabric configuration types — typed dataclasses for source and product config.

All configs use eager validation: env vars are checked at construction time,
URL formats are validated, and required fields are enforced. Secrets are
NEVER stored — only env var names are kept, and values are read per-request.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "AuthConfig",
    "BearerAuth",
    "ApiKeyAuth",
    "OAuth2Auth",
    "BasicAuth",
    "BaseSourceConfig",
    "RestSourceConfig",
    "FileSourceConfig",
    "CloudSourceConfig",
    "DatabaseSourceConfig",
    "StreamSourceConfig",
    "StalenessPolicy",
    "CircuitBreakerConfig",
    "RateLimit",
    "WebhookConfig",
    "ProductMode",
]


# ---------------------------------------------------------------------------
# Auth types (doc 08, lines 43-48; doc 04, Resolution 8)
# ---------------------------------------------------------------------------


class AuthConfig:
    """Base class for authentication configurations."""

    pass


@dataclass(frozen=True)
class BearerAuth(AuthConfig):
    """Bearer token auth — reads env var per-request, never cached."""

    token_env: str

    def __post_init__(self) -> None:
        if not self.token_env:
            raise ValueError("BearerAuth.token_env must not be empty")

    def get_token(self) -> str:
        """Read token from environment at call time."""
        val = os.environ.get(self.token_env)
        if not val:
            raise ValueError(
                f"Environment variable '{self.token_env}' is not set or empty"
            )
        return val


@dataclass(frozen=True)
class ApiKeyAuth(AuthConfig):
    """API key auth — reads env var per-request."""

    key_env: str
    header: str = "X-API-Key"

    def __post_init__(self) -> None:
        if not self.key_env:
            raise ValueError("ApiKeyAuth.key_env must not be empty")

    def get_key(self) -> str:
        val = os.environ.get(self.key_env)
        if not val:
            raise ValueError(
                f"Environment variable '{self.key_env}' is not set or empty"
            )
        return val


@dataclass(frozen=True)
class OAuth2Auth(AuthConfig):
    """OAuth2 client credentials — auto-refresh lifecycle.

    Client ID and secret are re-read from env at refresh time (doc 04,
    Resolution 8). Token is cached in-memory only (never Redis, never
    disk — doc 01-redteam H5).
    """

    client_id_env: str
    client_secret_env: str
    token_url: str
    scopes: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not self.client_id_env:
            raise ValueError("OAuth2Auth.client_id_env must not be empty")
        if not self.client_secret_env:
            raise ValueError("OAuth2Auth.client_secret_env must not be empty")
        if not self.token_url:
            raise ValueError("OAuth2Auth.token_url must not be empty")


@dataclass(frozen=True)
class BasicAuth(AuthConfig):
    """HTTP Basic auth — reads env vars per-request."""

    username_env: str
    password_env: str

    def __post_init__(self) -> None:
        if not self.username_env:
            raise ValueError("BasicAuth.username_env must not be empty")
        if not self.password_env:
            raise ValueError("BasicAuth.password_env must not be empty")

    def get_credentials(self) -> tuple[str, str]:
        username = os.environ.get(self.username_env, "")
        password = os.environ.get(self.password_env, "")
        if not username:
            raise ValueError(
                f"Environment variable '{self.username_env}' is not set or empty"
            )
        if not password:
            raise ValueError(
                f"Environment variable '{self.password_env}' is not set or empty"
            )
        return username, password


# ---------------------------------------------------------------------------
# Shared config types
# ---------------------------------------------------------------------------


class ProductMode(str, Enum):
    """Product execution mode."""

    MATERIALIZED = "materialized"
    PARAMETERIZED = "parameterized"
    VIRTUAL = "virtual"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration for source adapters."""

    failure_threshold: int = 3
    probe_interval: float = 30.0
    success_threshold: int = 1


@dataclass
class StalenessPolicy:
    """Staleness handling for product data."""

    max_age: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    on_stale: str = "serve"  # "serve" | "error"
    on_source_error: str = "serve_stale"  # "serve_stale" | "error"


@dataclass
class RateLimit:
    """Rate limiting configuration for products."""

    max_requests: int = 100  # per client per minute
    max_unique_params: int = 50  # max distinct parameter combos cached


@dataclass
class WebhookConfig:
    """Webhook configuration for push-based sources."""

    path: str
    secret_env: str
    events: Sequence[str] = ()

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("WebhookConfig.path must not be empty")
        if not self.secret_env:
            raise ValueError("WebhookConfig.secret_env must not be empty")


# ---------------------------------------------------------------------------
# Source config types
# ---------------------------------------------------------------------------

_URL_PATTERN = re.compile(r"^https?://")


@dataclass
class BaseSourceConfig:
    """Base configuration for all source types."""

    poll_interval: float = 60.0  # seconds
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    staleness: StalenessPolicy = field(default_factory=StalenessPolicy)

    def validate(self) -> None:
        """Validate configuration. Override in subclasses for specific checks."""
        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")


@dataclass
class RestSourceConfig(BaseSourceConfig):
    """Configuration for REST API sources."""

    url: str = ""
    auth: Optional[AuthConfig] = None
    endpoints: Dict[str, str] = field(default_factory=dict)
    webhook: Optional[WebhookConfig] = None
    timeout: float = 30.0
    headers: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        super().validate()
        if not self.url:
            raise ValueError("RestSourceConfig.url must not be empty")
        if not _URL_PATTERN.match(self.url):
            raise ValueError(
                f"RestSourceConfig.url must start with http:// or https://, "
                f"got: {self.url[:50]}"
            )
        if self.timeout <= 0:
            raise ValueError("RestSourceConfig.timeout must be positive")
        # Validate auth env vars exist (eager validation)
        if isinstance(self.auth, BearerAuth):
            if not os.environ.get(self.auth.token_env):
                logger.warning(
                    "BearerAuth env var '%s' is not set — will fail at fetch time",
                    self.auth.token_env,
                )
        elif isinstance(self.auth, ApiKeyAuth):
            if not os.environ.get(self.auth.key_env):
                logger.warning(
                    "ApiKeyAuth env var '%s' is not set — will fail at fetch time",
                    self.auth.key_env,
                )


@dataclass
class FileSourceConfig(BaseSourceConfig):
    """Configuration for local file sources.

    Supports two modes:

    - **Single file** (``path`` set): reads and watches one specific file.
    - **Directory scanning** (``directory`` + ``pattern`` set): scans a
      directory for files matching a glob pattern and selects the latest
      by name (lexicographic) or modification time.

    Exactly one of ``path`` or ``directory`` must be set.
    """

    path: str = ""
    directory: str = ""
    pattern: str = ""
    selection: str = "latest_name"  # "latest_name" | "latest_mtime"
    watch: bool = True
    parser: Optional[str] = None  # "json" | "yaml" | "csv" | "xlsx" | auto-detect

    def validate(self) -> None:
        super().validate()
        has_path = bool(self.path)
        has_directory = bool(self.directory)

        if has_path and has_directory:
            raise ValueError(
                "FileSourceConfig: set either 'path' or 'directory', not both"
            )
        if not has_path and not has_directory:
            raise ValueError(
                "FileSourceConfig: either 'path' or 'directory' must be set"
            )
        if has_directory and not self.pattern:
            raise ValueError(
                "FileSourceConfig: 'pattern' is required when using 'directory' mode"
            )
        if self.selection not in ("latest_name", "latest_mtime"):
            raise ValueError(
                f"FileSourceConfig.selection must be 'latest_name' or "
                f"'latest_mtime', got: {self.selection!r}"
            )


@dataclass
class CloudSourceConfig(BaseSourceConfig):
    """Configuration for cloud storage sources (S3, GCS, Azure Blob)."""

    bucket: str = ""
    provider: str = "s3"  # "s3" | "gcs" | "azure"
    prefix: str = ""

    def validate(self) -> None:
        super().validate()
        if not self.bucket:
            raise ValueError("CloudSourceConfig.bucket must not be empty")
        if self.provider not in ("s3", "gcs", "azure"):
            raise ValueError(
                f"CloudSourceConfig.provider must be 's3', 'gcs', or 'azure', "
                f"got: {self.provider}"
            )


@dataclass
class DatabaseSourceConfig(BaseSourceConfig):
    """Configuration for external database sources."""

    url: str = ""
    tables: Sequence[str] = ()
    read_only: bool = True

    def validate(self) -> None:
        super().validate()
        if not self.url:
            raise ValueError("DatabaseSourceConfig.url must not be empty")


@dataclass
class StreamSourceConfig(BaseSourceConfig):
    """Configuration for streaming sources (Kafka, WebSocket)."""

    broker: str = ""
    topic: str = ""
    group_id: str = ""

    def validate(self) -> None:
        super().validate()
        if not self.broker:
            raise ValueError("StreamSourceConfig.broker must not be empty")
        if not self.topic:
            raise ValueError("StreamSourceConfig.topic must not be empty")

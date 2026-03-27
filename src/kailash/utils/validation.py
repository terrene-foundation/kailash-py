# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared validation utilities for the Kailash SDK.

This module provides security-critical validation functions used across
multiple subsystems (cache, MCP server, trust governance, etc.).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

__all__ = ["validate_redis_url"]

logger = logging.getLogger(__name__)


def validate_redis_url(url: str) -> str:
    """Validate and return a Redis URL.

    Only ``redis://`` and ``rediss://`` (TLS) schemes are accepted.
    The URL must include a hostname.

    Args:
        url: Redis connection URL to validate.

    Returns:
        The validated URL (unchanged).

    Raises:
        ValueError: If the URL scheme is not ``redis`` or ``rediss``,
            or if the hostname is missing.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("redis", "rediss"):
        raise ValueError(
            f"Invalid Redis URL scheme '{parsed.scheme}'. "
            "Must be 'redis' or 'rediss'."
        )
    if not parsed.hostname:
        raise ValueError("Redis URL must include a hostname.")
    return url

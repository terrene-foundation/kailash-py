from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Manifest error hierarchy.

All manifest errors inherit from ManifestError, which carries a
``details`` dict for structured error context.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

__all__ = ["ManifestError", "ManifestParseError", "ManifestValidationError"]


class ManifestError(ValueError):
    """Base error for all manifest operations.

    Inherits from ``ValueError`` (not ``Exception``) so that callers which
    forward validation-style errors to untrusted clients — e.g. the MCP
    catalog server's ``_dispatch_tool`` (see
    ``kaizen/mcp/catalog_server/server.py``), which only relays real error
    messages for ``(ValueError, KeyError, TypeError)`` — surface the
    module's real validation message instead of an opaque "Internal tool
    error".
    """

    def __init__(self, message: str, details: Dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class ManifestValidationError(ManifestError):
    """Raised when manifest data fails validation.

    Examples include missing required fields (name, module, class_name)
    or unsupported manifest_version values.
    """


class ManifestParseError(ManifestError):
    """Raised when TOML parsing fails.

    This covers both syntactically invalid TOML and structurally
    invalid manifest files (e.g., missing ``[agent]`` section).
    """

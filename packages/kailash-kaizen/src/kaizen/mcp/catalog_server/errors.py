from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Catalog MCP server error hierarchy.

All catalog errors inherit from CatalogError, which carries a
``details`` dict for structured error context.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["CatalogError", "AgentNotFoundError", "CatalogValidationError"]


class CatalogError(Exception):
    """Base error for all catalog server operations.

    Attributes:
        details: Structured error context for debugging and logging.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details: Dict[str, Any] = details or {}


class AgentNotFoundError(CatalogError):
    """Raised when a requested agent is not found in the catalog.

    Attributes:
        agent_name: The name of the agent that was not found.
    """

    def __init__(
        self,
        agent_name: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details: Dict[str, Any] = {"agent_name": agent_name}
        if details:
            merged_details.update(details)
        super().__init__(
            f"Agent {agent_name!r} not found in catalog",
            details=merged_details,
        )
        self.agent_name = agent_name


class CatalogValidationError(CatalogError):
    """Raised when catalog input data fails validation.

    Covers invalid agent names, malformed manifests, missing required
    fields, and other structural issues in catalog operations.
    """

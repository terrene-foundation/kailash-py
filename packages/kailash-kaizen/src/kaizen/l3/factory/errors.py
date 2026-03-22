# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Factory error types for agent instantiation and registry operations.

All errors carry structured .details dicts for programmatic inspection
and use factory-method constructors per the L3 error pattern.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "EnvelopeNotTighter",
    "FactoryError",
    "InsufficientBudget",
    "InstanceNotFound",
    "MaxChildrenExceeded",
    "MaxDepthExceeded",
    "RegistryError",
    "RequiredContextMissing",
    "ToolNotInParent",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base error
# ---------------------------------------------------------------------------


class FactoryError(Exception):
    """Base error for all AgentFactory operations.

    Variants are concrete subclasses. Every variant carries a structured
    .details dict for programmatic inspection and audit logging.
    """

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.details: dict[str, Any] = details or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Envelope / budget errors
# ---------------------------------------------------------------------------


class EnvelopeNotTighter(FactoryError):
    """Child envelope is not tighter than parent on a given dimension."""

    def __init__(self, dimension: str, parent_value: str, child_value: str) -> None:
        super().__init__(
            f"Child envelope is not tighter than parent on dimension "
            f"'{dimension}': parent={parent_value}, child={child_value}",
            details={
                "dimension": dimension,
                "parent_value": parent_value,
                "child_value": child_value,
            },
        )


class InsufficientBudget(FactoryError):
    """Parent does not have enough remaining budget for child allocation."""

    def __init__(self, dimension: str, required: str, available: str) -> None:
        super().__init__(
            f"Insufficient budget on dimension '{dimension}': "
            f"required={required}, available={available}",
            details={
                "dimension": dimension,
                "required": required,
                "available": available,
            },
        )


# ---------------------------------------------------------------------------
# Hierarchy limit errors
# ---------------------------------------------------------------------------


class MaxChildrenExceeded(FactoryError):
    """Parent has reached its maximum number of direct children."""

    def __init__(self, parent_id: str, limit: int, current: int) -> None:
        super().__init__(
            f"Parent '{parent_id}' has reached max_children limit: "
            f"limit={limit}, current={current}",
            details={
                "parent_id": parent_id,
                "limit": limit,
                "current": current,
            },
        )


class MaxDepthExceeded(FactoryError):
    """Delegation depth would exceed an ancestor's max_depth limit."""

    def __init__(self, parent_id: str, depth_limit: int, current_depth: int) -> None:
        super().__init__(
            f"Spawning under '{parent_id}' would exceed max_depth: "
            f"limit={depth_limit}, current_depth={current_depth}",
            details={
                "parent_id": parent_id,
                "depth_limit": depth_limit,
                "current_depth": current_depth,
            },
        )


# ---------------------------------------------------------------------------
# Tool / context errors
# ---------------------------------------------------------------------------


class ToolNotInParent(FactoryError):
    """Child requests a tool that the parent does not have."""

    def __init__(self, tool_id: str) -> None:
        super().__init__(
            f"Tool '{tool_id}' is not in the parent's allowed tool set",
            details={"tool_id": tool_id},
        )


class RequiredContextMissing(FactoryError):
    """Required context keys are not available at spawn time."""

    def __init__(self, keys: list[str]) -> None:
        super().__init__(
            f"Required context keys missing: {keys}",
            details={"missing_keys": keys},
        )


# ---------------------------------------------------------------------------
# Registry errors
# ---------------------------------------------------------------------------


class InstanceNotFound(FactoryError):
    """No instance with the given ID exists in the registry."""

    def __init__(self, instance_id: str) -> None:
        super().__init__(
            f"Instance '{instance_id}' not found in registry",
            details={"instance_id": instance_id},
        )


class RegistryError(FactoryError):
    """General registry operation error (e.g., duplicate ID, non-terminal deregister)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Registry error: {detail}",
            details={"detail": detail},
        )

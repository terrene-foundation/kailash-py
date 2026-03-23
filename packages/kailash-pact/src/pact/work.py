# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Work types for PactEngine -- submission and result dataclasses.

WorkSubmission captures the intent to execute work under governance.
WorkResult captures the outcome of that execution, including cost tracking
and event history.

Both are frozen dataclasses (immutable after construction) following EATP SDK
conventions (to_dict / from_dict roundtrip).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["WorkSubmission", "WorkResult"]


def _validated_cost(value: float) -> float:
    """Validate cost is finite. NaN/Inf bypass budget checks (pact-governance.md rule 6)."""
    if not math.isfinite(value):
        raise ValueError(f"cost_usd must be finite, got {value!r}")
    return value


@dataclass(frozen=True)
class WorkSubmission:
    """A request to execute work under PACT governance.

    Attributes:
        objective: Natural-language description of the work to perform.
        role: The D/T/R address of the role submitting the work.
        context: Additional context dict passed to the execution layer.
        budget_usd: Optional per-submission budget override.
    """

    objective: str
    role: str
    context: dict[str, Any] = field(default_factory=dict)
    budget_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "objective": self.objective,
            "role": self.role,
            "context": self.context,
            "budget_usd": self.budget_usd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkSubmission:
        """Reconstruct from a dict."""
        return cls(
            objective=data["objective"],
            role=data["role"],
            context=data.get("context", {}),
            budget_usd=data.get("budget_usd"),
        )


@dataclass(frozen=True)
class WorkResult:
    """The outcome of a PactEngine.submit() execution.

    Frozen to prevent post-construction mutation.

    Attributes:
        success: True if the work completed successfully.
        results: Mapping of output keys to values from execution.
        cost_usd: Total cost consumed during execution.
        events: List of event dicts emitted during execution.
        error: Human-readable error message if success is False, or None.
    """

    success: bool
    results: dict[str, Any] = field(default_factory=dict)
    cost_usd: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for transport or storage.

        Returns:
            A dict with all fields serialized to JSON-safe types.
        """
        return {
            "success": self.success,
            "results": self.results,
            "cost_usd": self.cost_usd,
            "events": list(self.events),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkResult:
        """Reconstruct a WorkResult from a dict.

        Args:
            data: A dict as produced by to_dict().

        Returns:
            A new WorkResult instance.

        Raises:
            KeyError: If required field 'success' is missing.
        """
        return cls(
            success=data["success"],
            results=data.get("results", {}),
            cost_usd=_validated_cost(float(data.get("cost_usd", 0.0))),
            events=list(data.get("events", [])),
            error=data.get("error"),
        )

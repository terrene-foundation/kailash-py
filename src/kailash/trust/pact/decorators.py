# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Governance decorators -- @governed_tool for marking functions as governance-aware.

The @governed_tool decorator marks a function with governance metadata
(action name, cost, resource) so that PactGovernedAgent and MockGovernedAgent
can auto-register the tool and route it through governance verification.

Decorated functions remain callable -- the decorator does NOT intercept
execution. Governance enforcement is performed by PactGovernedAgent.execute_tool().
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

__all__ = ["governed_tool"]

F = TypeVar("F", bound=Callable[..., Any])


def governed_tool(
    action_name: str,
    *,
    cost: float = 0.0,
    resource: str | None = None,
) -> Callable[[F], F]:
    """Decorator marking a function as governance-aware.

    Attaches governance metadata to the function:
    - _governed: True
    - _governance_action: str (the action name for governance checks)
    - _governance_cost: float (cost for financial envelope checks)
    - _governance_resource: str | None (resource for knowledge checks)

    The decorated function is still directly callable. Governance
    enforcement is performed when the tool is executed through
    PactGovernedAgent.execute_tool(), not by this decorator.

    Args:
        action_name: The governance action name (e.g., "read", "write_report").
        cost: Cost of this tool execution for financial constraint checks.
            Defaults to 0.0 (no financial impact).
        resource: Optional resource identifier for knowledge access checks.
            Defaults to None (no knowledge check required).

    Returns:
        A decorator that attaches governance metadata to the wrapped function.

    Example::

        @governed_tool("write_report", cost=50.0)
        def write_report(content: str) -> str:
            return f"Report: {content}"

        # Metadata is available:
        assert write_report._governed is True
        assert write_report._governance_action == "write_report"
        assert write_report._governance_cost == 50.0
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        # Attach governance metadata
        wrapper._governed = True  # type: ignore[attr-defined]
        wrapper._governance_action = action_name  # type: ignore[attr-defined]
        wrapper._governance_cost = cost  # type: ignore[attr-defined]
        wrapper._governance_resource = resource  # type: ignore[attr-defined]

        return wrapper  # type: ignore[return-value]

    return decorator

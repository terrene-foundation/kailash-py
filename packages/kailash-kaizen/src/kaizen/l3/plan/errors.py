# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plan DAG error types.

Structured errors with variant tags and .details dicts for all plan
operations: validation, execution, and modification.
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "ExecutionError",
    "ModificationError",
    "PlanError",
    "ValidationError",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PlanError (base)
# ---------------------------------------------------------------------------


class PlanError(Exception):
    """Base error for all plan operations.

    Carries structured .details dict for programmatic consumption.
    """

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.details = details or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


class ValidationError(PlanError):
    """Error during plan validation.

    Carries a list of all validation errors found (not just the first).
    Each error is a string describing the violation.
    """

    def __init__(
        self,
        message: str,
        *,
        errors: list[str],
        details: dict[str, Any] | None = None,
    ) -> None:
        self.errors = errors
        super().__init__(
            message,
            details={**(details or {}), "errors": errors},
        )


# ---------------------------------------------------------------------------
# ExecutionError
# ---------------------------------------------------------------------------


class ExecutionError(PlanError):
    """Error during plan execution.

    Raised when preconditions are violated (wrong state) or when
    execution encounters an unrecoverable issue.
    """

    pass


# ---------------------------------------------------------------------------
# ModificationError
# ---------------------------------------------------------------------------


class ModificationError(PlanError):
    """Error during plan modification.

    Raised when a modification would violate structural or envelope
    invariants, or when preconditions are not met (e.g., modifying
    a running node).
    """

    pass

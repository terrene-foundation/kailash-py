# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
DataFlow Core Exceptions

Engine-layer exceptions raised by the DataFlow core engine when DDL,
migration, or model-registration paths fail in ways the caller MUST act
on. These complement (do not replace) the broader exception hierarchy in
``dataflow/exceptions.py``.

Origin: GitHub issue #696 — auto_migrate fail-fast circuit breaker
(workspaces/dataflow-prod-incident, 2026-04-28). The DDL retry storm
that saturated Azure Postgres was the canonical "silent fallback +
no lifecycle bound" failure (workspaces/.../journal/0001-DISCOVERY).
``DDLFailedError`` is the typed surface that converts the silent retry
loop into a single, loud, fail-fast error at the next access.
"""

from __future__ import annotations

from typing import Optional

# Re-export the public DataFlow base error so callers can `except
# DataFlowError` to catch both legacy and new exception types without
# tracking which module each lives in.
from dataflow.exceptions import DataFlowError


class DDLFailedError(DataFlowError):
    """Raised when an auto-migrate DDL execution failed and the failure
    has been recorded in DataFlow's failed-DDL state.

    The first failed CREATE TABLE / ALTER TABLE under
    ``auto_migrate=True`` records a ``FailedDDLRecord`` on the DataFlow
    instance and emits a single ERROR log + metric. Every subsequent
    access to the same model raises this exception WITHOUT re-firing
    the DDL — the circuit breaker for the issue #696 retry storm.

    Operators recover by:

    1. Inspecting the structured error (``model_name``, ``original_error``,
       ``statement_preview``) to diagnose the DDL failure.
    2. Fixing the root cause (FK ordering, role permissions, column-type
       mismatch, missing parent table, etc.).
    3. Restarting the application — the next ``DataFlow.__init__``
       runs with a fresh ``_failed_table_creations`` map, which retries
       the DDL once and either succeeds or fails-fast again.

    Attributes:
        model_name: The model whose CREATE TABLE / ALTER TABLE failed.
        original_error: The underlying exception from the DDL execution.
        statement_preview: First 200 characters of the failed DDL
            statement (truncated to avoid leaking large schemas through
            error chains).

    Example:
        >>> try:
        ...     await db.express.list("Order")
        ... except DDLFailedError as e:
        ...     logger.error(
        ...         "ddl.fail_fast",
        ...         extra={
        ...             "model": e.model_name,
        ...             "original": str(e.original_error),
        ...             "preview": e.statement_preview,
        ...         },
        ...     )
        ...     raise

    See Also:
        - ``rules/zero-tolerance.md`` Rule 3 (silent fallbacks BLOCKED)
        - ``rules/dataflow-pool.md`` Rule 2 (fail-fast at startup)
        - ``rules/observability.md`` Rule 7 (structured failure logs)
        - GitHub #696 (origin issue)
    """

    def __init__(
        self,
        model_name: str,
        original_error: Optional[BaseException] = None,
        statement_preview: str = "",
    ) -> None:
        self.model_name = model_name
        self.original_error = original_error
        # Bound the preview length: error chains are shipped to log
        # aggregators and may surface in API responses; large DDL bodies
        # blow up payloads and risk leaking schema details.
        self.statement_preview = (statement_preview or "")[:200]

        # Build a deterministic, operator-actionable message. The original
        # error class+message is included so operators don't need to chain
        # __cause__ to diagnose. Statement preview is included only when
        # non-empty so the message stays compact for trivial failures.
        original_repr = (
            f"{type(original_error).__name__}: {original_error}"
            if original_error is not None
            else "unknown"
        )
        parts = [
            f"DDL execution failed for model '{model_name}' under auto_migrate=True",
            f"original_error={original_repr}",
        ]
        if self.statement_preview:
            parts.append(f"statement_preview={self.statement_preview!r}")
        parts.append(
            "Subsequent access to this model will fail-fast without "
            "re-firing the DDL. Diagnose the root cause, then restart "
            "the application to retry. Use auto_migrate='warn' (legacy) "
            "to opt into log-and-continue behavior instead of fail-fast."
        )
        super().__init__(" — ".join(parts))


__all__ = ["DDLFailedError", "DataFlowError"]

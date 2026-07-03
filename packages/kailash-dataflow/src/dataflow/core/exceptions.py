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

import re
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


class BulkUpsertConflictTargetError(DataFlowError):
    """Raised when a bulk upsert's ``conflict_on`` target is not backed by a
    PRIMARY KEY or UNIQUE constraint.

    Native single-statement upsert (``INSERT ... ON CONFLICT (cols) DO UPDATE``
    on PostgreSQL/SQLite, ``ON DUPLICATE KEY UPDATE`` on MySQL) requires the
    conflict-target columns to be a PK or UNIQUE key. When they are not, the
    database rejects the statement ("ON CONFLICT clause does not match any
    PRIMARY KEY or UNIQUE constraint" / "there is no unique or exclusion
    constraint matching the ON CONFLICT specification"). DataFlow converts that
    opaque driver error into this actionable typed error rather than silently
    falling back to ``ON CONFLICT (id)`` (which would ignore the caller's intent
    and land duplicate rows).

    Attributes:
        conflict_on: The conflict-target columns the caller requested.
        model_name: The model the upsert targeted (best-effort; may be None).
        original_error: The underlying driver exception, if any.

    Recovery:

    1. Declare the field(s) ``unique=True`` on the model (or add a UNIQUE
       index / constraint) so the conflict target is enforceable.
    2. On **SQLite only**, for genuinely non-unique keys, use single-record
       ``db.express.upsert`` which does a WHERE-precheck instead of a native
       ON CONFLICT clause (issue #1508) — bulk upsert on a non-unique key is
       ambiguous when the batch itself contains duplicate keys. This fallback
       does NOT exist on PostgreSQL: PG's single-record upsert also uses an
       atomic ON CONFLICT and raises :class:`UpsertConflictTargetError` on a
       non-unique target (issue #1520), so the conflict target MUST be a
       PK/UNIQUE key there.
    """

    def __init__(
        self,
        conflict_on: Optional[list] = None,
        model_name: Optional[str] = None,
        original_error: Optional[BaseException] = None,
    ) -> None:
        self.conflict_on = list(conflict_on or [])
        self.model_name = model_name
        self.original_error = original_error

        cols = ", ".join(self.conflict_on) or "<none>"
        model_part = f" on model '{model_name}'" if model_name else ""
        super().__init__(
            f"bulk_upsert conflict_on={self.conflict_on!r}{model_part} does not "
            f"match any PRIMARY KEY or UNIQUE constraint. Native bulk upsert "
            f"requires the conflict-target column(s) ({cols}) to be backed by a "
            f"PK or UNIQUE key. Remediation: declare the field(s) unique=True "
            f"(or add a UNIQUE index), OR — on SQLite, for genuinely non-unique "
            f"keys — use single-record db.express.upsert (WHERE-precheck) "
            f"instead of bulk upsert, which is ambiguous when a batch contains "
            f"duplicate keys. (On PostgreSQL single-record upsert also requires "
            f"the unique constraint — see UpsertConflictTargetError / #1520.)"
        )


class UpsertConflictTargetError(DataFlowError):
    """Raised when a single-record upsert's ``conflict_on`` target is not backed
    by a PRIMARY KEY or UNIQUE constraint (issue #1520).

    On PostgreSQL a native ``INSERT ... ON CONFLICT (cols) DO UPDATE`` requires
    the conflict-target columns to be a PK or UNIQUE key, and the statement is
    atomic — DataFlow cannot substitute a WHERE-precheck without a TOCTOU race
    under concurrency (unlike SQLite, whose single-record upsert path #1508 DOES
    use a precheck and therefore never reaches this error). When the target is
    not unique, PostgreSQL rejects the statement with the opaque driver message
    "there is no unique or exclusion constraint matching the ON CONFLICT
    specification". DataFlow converts that into this actionable typed error
    rather than surfacing the raw driver text (which never names ``conflict_on``,
    the offending field, or the remedy).

    This is the single-record sibling of :class:`BulkUpsertConflictTargetError`.

    Attributes:
        conflict_on: The conflict-target columns the caller requested.
        model_name: The model the upsert targeted (best-effort; may be None).
        original_error: The underlying driver exception, if any.

    Recovery (PostgreSQL — the conflict target MUST be enforceable):

    1. Declare the field(s) ``unique=True`` on the model so DataFlow's migration
       creates the backing UNIQUE constraint.
    2. Or add a UNIQUE index / constraint via a migration
       (``CREATE UNIQUE INDEX ... ON {table} ({cols})``).

    DataFlow does NOT auto-create the index at runtime: runtime DDL is blocked
    per ``schema-migration.md`` Rule 1, and it would fail anyway on a column that
    already holds duplicate values.
    """

    def __init__(
        self,
        conflict_on: Optional[list] = None,
        model_name: Optional[str] = None,
        original_error: Optional[BaseException] = None,
    ) -> None:
        self.conflict_on = list(conflict_on or [])
        self.model_name = model_name
        self.original_error = original_error

        cols = ", ".join(self.conflict_on) or "<none>"
        model_part = f" on model '{model_name}'" if model_name else ""
        super().__init__(
            f"upsert conflict_on={self.conflict_on!r}{model_part} does not match "
            f"any PRIMARY KEY or UNIQUE constraint. Native PostgreSQL upsert "
            f"(INSERT ... ON CONFLICT) requires the conflict-target column(s) "
            f"({cols}) to be backed by a PK or UNIQUE key. Remediation: declare "
            f"the field(s) unique=True on the model (or add a UNIQUE index via a "
            f"migration). DataFlow does not auto-create the index (blocked by "
            f"schema-migration policy; it would also fail on existing duplicate "
            f"values)."
        )


def is_conflict_target_error(message: str) -> bool:
    """True iff a driver error signals an unmatched ON CONFLICT target (#1519).

    SQLite emits "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE
    constraint"; PostgreSQL emits "there is no unique or exclusion constraint
    matching the ON CONFLICT specification". Shared by the express bulk engine
    (``features/bulk.py``) and the workflow node (``nodes/bulk_upsert.py``) so
    both convert the opaque driver message into
    :class:`BulkUpsertConflictTargetError` rather than a silent fallback.
    """
    m = (message or "").lower()
    return (
        "does not match any primary key or unique constraint" in m
        or "no unique or exclusion constraint matching the on conflict" in m
    )


# DB driver errors embed column VALUES in "DETAIL: Key (col)=(value) already
# exists" clauses. Those values may be user data / PII; they MUST be redacted
# before a driver message is logged or returned to a caller. Shared by the
# express bulk engine (``features/bulk.py``) and the workflow node
# (``nodes/bulk_upsert.py``) so both surfaces scrub identically — one helper,
# no drift (rules/security.md § Multi-Site Kwarg Plumbing; rules/observability.md
# Rule 8).
_DETAIL_RE = re.compile(r"DETAIL:[^\n]*", re.IGNORECASE)
_KEY_VALUES_RE = re.compile(r"Key \(([^)]+)\)=\(([^)]*)\)", re.IGNORECASE)


def sanitize_db_error(msg: str) -> str:
    """Redact column VALUES from a DB driver error message.

    Preserves the diagnostic SHAPE (the constraint/column names in
    ``Key (col)=...`` and the presence of a ``DETAIL:`` clause) while
    replacing the value payload with ``[REDACTED]`` so a unique-violation
    on a column OTHER than the conflict target cannot leak user data into
    logs or the returned error string.
    """
    if not isinstance(msg, str):
        return "<non-string error>"
    msg = _DETAIL_RE.sub("DETAIL: [REDACTED]", msg)
    msg = _KEY_VALUES_RE.sub(r"Key (\1)=([REDACTED])", msg)
    return msg


__all__ = [
    "DDLFailedError",
    "BulkUpsertConflictTargetError",
    "UpsertConflictTargetError",
    "is_conflict_target_error",
    "sanitize_db_error",
    "DataFlowError",
]

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
from typing import Optional, Sequence

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
            On the auto-migrate DDL paths this is a SANITIZED wrapper
            (``RuntimeError`` whose text has been passed through
            ``sanitize_db_error``), so both ``str(self)`` and
            ``str(self.original_error)`` are safe to log.
        statement_preview: First 200 characters of the failed DDL
            statement (truncated to avoid leaking large schemas through
            error chains).

    Security note (issue #1550): the RAW driver exception is preserved as
    ``__cause__`` (via ``raise ... from error``) for local traceback
    diagnosability. Its ``str()`` may still carry a value-bearing
    ``DETAIL: Key(col)=(value)`` / ``Duplicate entry 'value' ...`` clause.
    The user-facing message (``str(self)``) and ``original_error`` are
    redacted, but callers MUST NOT log this exception with ``exc_info=True``
    / ``logger.exception(...)`` on a log-aggregator surface — that emits the
    ``__cause__`` chain and re-leaks the raw value. Log ``e.model_name`` +
    ``str(e.original_error)`` instead (see Example).

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


class MigrationNotAppliedError(DataFlowError):
    """Raised when the async migration system completed WITHOUT applying the
    schema (``auto_migrate`` returned ``success=False``) but did NOT itself
    raise.

    Origin: GitHub issue #1548 — silent write loss. The async lazy-DDL path
    (``ensure_table_exists`` → ``_execute_postgresql_migration_system_async``)
    treated ``auto_migrate`` returning ``success=False`` (a genuine
    not-applied outcome under connection-pool exhaustion / process-state
    accumulation) as merely a ``logger.warning`` and returned normally. The
    outer ``ensure_table_exists`` handler then marked the table ensured and
    returned ``True`` while the table physically did not exist — subsequent
    CRUD "succeeded" via read-your-writes on a pooled connection but the row
    was never durable.

    This typed error converts that not-applied outcome into a real failure
    signal that propagates to the outer ``ensure_table_exists`` handler. That
    handler makes PHYSICAL EXISTENCE the arbiter: it verifies the table against
    committed state on a fresh connection and

      * if the table is ABSENT — records the failed-DDL state and raises
        :class:`DDLFailedError` so the caller sees a loud failure and the next
        access self-heals (the genuine #1548 silent-write-loss);
      * if the table is PRESENT — treats the not-applied outcome as a benign
        false-negative (the migration system diffs a single-table target
        against the whole DB and can refuse a spurious cross-table DROP even
        though this table exists) and marks it ensured.

    Note: ``auto_migrate`` returning ``(True, [])`` for "already applied" /
    "no changes needed" is SUCCESS, not failure — those paths are non-raising
    and never construct this error.

    Attributes:
        model_name: The model whose migration did not apply.

    See Also:
        - ``rules/zero-tolerance.md`` Rule 3 (silent fallbacks BLOCKED)
        - GitHub #1548 (origin issue)
    """

    def __init__(self, model_name: str, detail: str = "") -> None:
        self.model_name = model_name
        self.detail = detail
        message = (
            f"Migration for model '{model_name}' completed without applying "
            f"the schema (auto_migrate returned success=False)"
        )
        if detail:
            message += f": {detail}"
        super().__init__(message)


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
        conflict_on: Optional[list[str]] = None,
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
    by a PRIMARY KEY or UNIQUE constraint (PostgreSQL #1520 / MySQL #1537).

    On PostgreSQL a native ``INSERT ... ON CONFLICT (cols) DO UPDATE`` requires
    the conflict-target columns to be a PK or UNIQUE key, and the statement is
    atomic — DataFlow cannot substitute a WHERE-precheck without a TOCTOU race
    under concurrency (unlike SQLite, whose single-record upsert path #1508 DOES
    use a precheck and therefore never reaches this error). When the target is
    not unique, PostgreSQL rejects the statement with the opaque driver message
    "there is no unique or exclusion constraint matching the ON CONFLICT
    specification"; DataFlow converts that REACTIVELY into this actionable typed
    error rather than surfacing the raw driver text (which never names
    ``conflict_on``, the offending field, or the remedy).

    On MySQL the same requirement holds but the failure mode differs: MySQL's
    ``INSERT ... ON DUPLICATE KEY UPDATE`` has no explicit conflict target and
    auto-detects whichever UNIQUE/PRIMARY key a row violates. A
    ``conflict_on=[non_unique_field]`` upsert therefore raises NO driver error —
    it silently falls through to a plain INSERT on the fresh ``id`` PK and lands
    a duplicate row. Because there is no error to catch, DataFlow raises this
    error PROACTIVELY: before executing the upsert it queries
    ``information_schema.statistics`` for a UNIQUE/PRIMARY index whose column set
    exactly matches ``conflict_on`` and raises here when none exists (#1537).
    MySQL has no WHERE-precheck fallback (unlike SQLite) — the conflict target
    MUST be a real unique key.

    This is the single-record sibling of :class:`BulkUpsertConflictTargetError`.

    Attributes:
        conflict_on: The conflict-target columns the caller requested.
        model_name: The model the upsert targeted (best-effort; may be None).
        original_error: The underlying driver exception, if any (PostgreSQL
            only; the MySQL proactive precheck has no driver error to attach).

    Recovery (PostgreSQL AND MySQL — the conflict target MUST be enforceable):

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
        conflict_on: Optional[list[str]] = None,
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


def format_tenant_natural_key_collision_message(
    model_name: str,
    tenant_id: str,
    colliding_ids: Sequence[object],
) -> str:
    """Build the actionable cross-tenant natural-key collision message (#1526).

    Single source of truth shared by BOTH the single-record raise path
    (:class:`TenantNaturalKeyCollisionError`, which passes a one-element
    sequence so its message is byte-identical to the original literal) AND
    the bulk partial-failure-dict path (``ExpressDataFlow`` bulk_create /
    bulk_upsert, which passes the caller's own candidate ids). Sharing the
    builder guarantees the two surfaces never drift and there is no parallel
    error hierarchy (``framework-first.md``).

    The message names ONLY the CALLER's own ``tenant_id`` + the CALLER's own
    supplied ``id``(s) — never another tenant's id or row data — so tenant
    isolation is preserved (``rules/tenant-isolation.md``, ``security.md``).
    A single id renders the exact-attribution singular form; multiple
    candidate ids render an at-least-one plural form (the bulk path cannot
    pinpoint which of the caller's supplied ids collided without a
    cross-tenant read, which is forbidden).
    """
    ids = list(colliding_ids)
    if len(ids) == 1:
        subject = (
            f"cannot write id={ids[0]!r} because that primary-key value is "
            f"already owned by another tenant."
        )
    else:
        subject = (
            f"cannot write ids {ids!r} because one or more of those "
            f"primary-key values are already owned by another tenant."
        )
    return (
        f"Cross-tenant natural-key collision on multi_tenant model "
        f"'{model_name}': tenant '{tenant_id}' {subject} "
        f"multi_tenant=True models keep the DEFAULT single-column primary key "
        f"'id' (NOT a composite of (tenant_id, id)), so under the default "
        f"row-level tenant strategy the 'id' is a GLOBALLY-UNIQUE surrogate — "
        f"two tenants cannot share the same natural-key id. Remediation: "
        f"(1) use globally-unique ids (e.g. UUIDs) so tenants never collide; "
        f"OR (2) for tenant-LOCAL natural keys, use the schema-per-tenant "
        f"isolation strategy "
        f"(dataflow.core.multi_tenancy.IsolationStrategy.SCHEMA / "
        f"SchemaIsolationStrategy.create_tenant_table), which gives each "
        f"tenant its own table so identical natural keys do not collide."
    )


class TenantNaturalKeyCollisionError(DataFlowError):
    """Raised when a ``multi_tenant=True`` write collides on the natural-key
    primary key with a row another tenant already owns (issue #1526).

    A ``multi_tenant=True`` DataFlow model keeps the DEFAULT single-column
    primary key ``id`` — the schema is NOT a composite ``(tenant_id, id)``.
    Under the default row-level tenant strategy (``QueryInterceptor`` appends a
    ``tenant_id`` filter on reads), the ``id`` column is therefore a GLOBALLY
    UNIQUE surrogate id: two tenants cannot both write the same natural-key
    ``id``. When tenant B inserts an ``id`` tenant A already owns, the database
    rejects it on the PK UNIQUE constraint (SQLite ``UNIQUE constraint failed:
    <table>.id``; PostgreSQL ``duplicate key value violates unique constraint
    "<table>_pkey"``; MySQL ``Duplicate entry ... for key 'PRIMARY'``).

    This is fail-closed and SAFE — no cross-tenant data is exposed (the write is
    rejected, not merged into another tenant's row) — but the raw driver message
    never explains the surrogate-id design, so DataFlow converts it into this
    actionable typed error.

    The message names ONLY the CALLER's own values — the active ``tenant_id`` and
    the ``id`` the caller supplied — never the other tenant's row data, so it
    does not weaken tenant isolation (``rules/tenant-isolation.md``).

    Attributes:
        model_name: The multi_tenant model whose write collided.
        tenant_id: The CALLER's active tenant (the one attempting the write).
        colliding_id: The natural-key ``id`` the CALLER supplied.
        original_error: The underlying driver exception / error string, kept for
            local diagnosability. It is NOT interpolated into ``str(self)`` (it
            may carry the raw driver value); attach it as ``__cause__`` via
            ``raise ... from`` only on non-log-aggregator surfaces (see #1550).

    Remediation (two supported paths — both cite real DataFlow API):

    1. Use GLOBALLY-UNIQUE ids (e.g. UUIDs) so each tenant's ids never collide;
       the surrogate-id contract then holds naturally.
    2. For tenant-LOCAL natural keys (each tenant reuses the same id space), use
       the schema-per-tenant isolation strategy —
       ``dataflow.core.multi_tenancy.IsolationStrategy.SCHEMA`` /
       ``SchemaIsolationStrategy.create_tenant_table`` — which gives each tenant
       its own table, so identical natural keys live in separate schemas and do
       not collide on one shared PK.
    """

    def __init__(
        self,
        model_name: str,
        tenant_id: str,
        colliding_id: object,
        original_error: Optional[BaseException] = None,
    ) -> None:
        self.model_name = model_name
        self.tenant_id = tenant_id
        self.colliding_id = colliding_id
        self.original_error = original_error

        # Single source of truth for the actionable message (shared with the
        # bulk partial-failure-dict path). A one-element sequence renders the
        # exact-attribution singular form, byte-identical to the original.
        super().__init__(
            format_tenant_natural_key_collision_message(
                model_name, tenant_id, [colliding_id]
            )
        )


def is_pk_unique_violation(message: str, table_name: str) -> bool:
    """True iff a driver error is a UNIQUE violation on the PRIMARY KEY ``id``
    of ``table_name`` (issue #1526).

    Detection is intentionally narrow — it matches ONLY the primary-key column
    ``id``, never a sibling UNIQUE column (e.g. ``<table>.idempotency_key``), so
    the caller does NOT broaden the actionable tenant-collision error onto
    unrelated unique violations. Returns ``False`` (caller keeps the original
    error path) for every non-PK unique violation and every other error class.

    Dialect shapes matched (both raw and post-:func:`sanitize_db_error`):

    * **SQLite** — ``UNIQUE constraint failed: <table>.id`` (word-bounded so
      ``<table>.idempotency_key`` does NOT match; the clause carries no value so
      it survives sanitization unchanged).
    * **PostgreSQL** — ``duplicate key value violates unique constraint`` plus
      the default PK constraint name ``<table>_pkey`` OR the ``Key (id)=`` DETAIL
      column name (the value is redacted by ``sanitize_db_error`` but the ``id``
      column name is preserved).
    * **MySQL/MariaDB** — ``Duplicate entry ... for key 'PRIMARY'`` (or the
      MySQL 8.0.19+ ``for key '<table>.PRIMARY'`` form); the ``PRIMARY`` key name
      is preserved by ``sanitize_db_error``.
    """
    if not message or not table_name:
        return False
    m = message.lower()
    t = table_name.lower()
    # SQLite: word-bounded so a sibling unique column (``<table>.id_token``,
    # ``<table>.idempotency_key``) that contains ``<table>.id`` as a prefix does
    # NOT match — only the exact ``<table>.id`` PK column.
    if "unique constraint failed:" in m and re.search(rf"\b{re.escape(t)}\.id\b", m):
        return True
    # PostgreSQL: the PK constraint (default name ``<table>_pkey``) or the
    # ``Key (id)=`` DETAIL naming the ``id`` column.
    if "duplicate key value violates unique constraint" in m and (
        f"{t}_pkey" in m or "key (id)=" in m
    ):
        return True
    # MySQL/MariaDB: the auto-named ``PRIMARY`` key.
    if "duplicate entry" in m and (
        "for key 'primary'" in m or f"for key '{t}.primary'" in m
    ):
        return True
    return False


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
# Issue #1552 (FIX 7): redact the ENTIRE ``DETAIL:`` clause, including any
# continuation lines, up to the next PG structured-field marker at line-start
# (HINT/CONTEXT/QUERY/…) OR end-of-string. The old single-line ``DETAIL:[^\n]*``
# leaked value-bearing DETAIL content that spanned a newline in TWO shapes:
#   (MED-1) a ``Key (col)=(value)`` value containing an embedded ``)`` AND a
#           newline — ``_KEY_VALUES_RE``'s ``[^)]*`` stops at the ``)``, and the
#           single-line ``DETAIL:`` collapsed only to the newline → tail leaked;
#   (MED-2) PG ``DETAIL: Failing row contains (…)`` (CHECK / NOT-NULL / exclusion
#           violations dump the WHOLE row) spanning a newline — ``_KEY_VALUES_RE``
#           never matches it and single-line ``DETAIL:`` missed the continuation.
# Block redaction is fail-closed: it redacts the whole DETAIL body while
# PRESERVING any trailing HINT/CONTEXT/etc. structured fields. For a single-line
# ``DETAIL: … already exists.`` with nothing after, ``.*?`` expands to EOS →
# ``DETAIL: [REDACTED]`` (BYTE-IDENTICAL to the pre-FIX-7 single-line output);
# with a trailing ``\nHINT:`` it stops before HINT (also identical to before).
_DETAIL_RE = re.compile(
    r"DETAIL:.*?(?=\n(?:HINT|CONTEXT|QUERY|WHERE|STATEMENT|LINE|LOCATION|"
    r"SCHEMA NAME|TABLE NAME|COLUMN NAME|CONSTRAINT NAME|DATATYPE NAME):|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# _KEY_VALUES_RE runs FIRST (belt-and-suspenders for a ``Key (col)=(value)`` clause
# that appears OUTSIDE a DETAIL: line); the block _DETAIL_RE then owns everything
# inside the DETAIL clause. Its value class ``[^)]*`` spans newlines.
_KEY_VALUES_RE = re.compile(r"Key \(([^)]+)\)=\(([^)]*)\)", re.IGNORECASE)
# MySQL/MariaDB duplicate-key (errno 1062): ``Duplicate entry 'value' for key
# 'name'``. This carries the offending column VALUE but has NEITHER a ``DETAIL:``
# clause NOR the PostgreSQL ``Key (col)=(value)`` form, so the two regexes above
# miss it entirely (issue #1550 red-team). Redact the entry value, keep the key
# name (schema shape, matching the PG ``Key (col)`` treatment).
#
# Issue #1557 fix: the value class is GREEDY (``.*``) and the redaction anchors on
# the FINAL ``' for key '<name>'`` structured suffix, NOT the first ``' for key``.
# The prior lazy ``.*?`` anchored on the FIRST occurrence, so a value that
# literally CONTAINS the substring ``' for key`` (e.g. ``x' for key 'y``) left its
# tail un-redacted. Greedy-to-final-suffix folds any embedded ``' for key`` into
# the redacted value while STILL preserving the trailing key NAME (the ``([^']*)``
# capture group, re-emitted via the replacement fn). The keyname group is OPTIONAL
# so a truncated ``Duplicate entry 'v' for key`` (no ``'<name>'``) still redacts
# rather than leaking. ``re.DOTALL`` is REQUIRED (issue #1556 red-team): a column
# VALUE containing a literal newline (a TEXT column with an embedded LF) would
# otherwise pin ``.*`` to the first line, the ``' for key`` anchor would sit on a
# later line, the match would FAIL, and the value would leak un-redacted. DOTALL
# lets greedy ``.*`` span the newline to the final suffix (fail-closed — the input
# is a SINGLE driver error's ``str(e)``, so spanning newlines cannot over-match
# across unrelated errors). The benign errno-1061 ``Duplicate key name
# 'idx_email'`` shape lacks the ``Duplicate entry '`` prefix, so it never matches —
# the #1550 keyname-tolerance contract is preserved.
_MYSQL_DUP_ENTRY_RE = re.compile(
    r"Duplicate entry '.*' for key(?: '([^']*)')?", re.IGNORECASE | re.DOTALL
)


def _redact_mysql_dup_entry(match: "re.Match[str]") -> str:
    """Replacement fn for ``_MYSQL_DUP_ENTRY_RE`` — redact the value, preserve the
    trailing key NAME when present (issue #1557)."""
    keyname = match.group(1)
    if keyname is not None:
        return f"Duplicate entry '[REDACTED]' for key '{keyname}'"
    return "Duplicate entry '[REDACTED]' for key"


# MongoDB duplicate-key (E11000): ``... dup key: { field: "value" }``. pymongo
# renders this via ``str(e)`` on the insert/bulk-insert/update paths. The offending
# VALUE lives in a ``{ field: "value" }`` payload none of the SQL regexes above
# target (no ``DETAIL:``, no ``Key (col)=``, no ``Duplicate entry``), so it survives
# unredacted (issue #1556, NoSQL sibling of #1552). Redact the whole ``dup key: {
# ... }`` brace payload while PRESERVING the ``collection:``/``index:`` names before
# it. Greedy ``.*`` anchors to the FINAL ``}`` on the line, so a pymongo ``, full
# error: {...}`` suffix (which echoes the same value inside ``errmsg``/``keyValue``)
# AND a value that embeds a literal ``}`` both collapse into the redaction
# (fail-closed). ``re.DOTALL`` is REQUIRED (issue #1556 red-team): a real pymongo
# ``DuplicateKeyError`` renders an embedded newline in the value LITERALLY, which
# without DOTALL would pin ``.*`` to the first line, leave the closing ``}`` on a
# later line, fail the match, and leak the value. DOTALL lets greedy ``.*`` span
# the newline to the final ``}`` (fail-closed — a single driver error's ``str(e)``).
_MONGO_DUP_KEY_RE = re.compile(r"dup key:\s*\{.*\}", re.IGNORECASE | re.DOTALL)

# Issue #1569: value-bearing NON-dup-key driver errors. The four regexes above
# cover only the duplicate-key/constraint shapes; ANY OTHER driver error that
# echoes a user VALUE (a malformed date, a non-UTF8 string, an out-of-range
# number, a failed type cast) rendered that value VERBATIM into logs / node-return
# dicts — the same PII-to-logs boundary #1552 closed for dup-key, re-opened for
# every type/format violation. Surfaced as an adjacent gap in the #1567 red-team.
#
# FAIL-CLOSED DESIGN DECISION (issue #1569 AC #3) — DIALECT-SCOPED FAMILY redaction,
# NOT per-errno whack-a-mole AND NOT a blanket quoted-literal sweep:
#   * Per-errno shapes (add a regex per errno) would leave the NEXT value-bearing
#     errno leaking until someone files it — the whack-a-mole the issue rejects.
#   * A blanket "redact every quoted literal" would ALSO strip the diagnostic
#     schema names (column / key / constraint names) the dup-key redactors above
#     deliberately PRESERVE, and over-redact benign quoted identifiers.
#   The chosen middle ground: one regex per DIALECT covering its whole value-
#   echoing FAMILY, anchored on the error-text preamble so the value is redacted
#   while the type word + trailing "for column '<col>'" schema name survive.
#
# Covered families (value is echoed → redacted):
#   * MySQL errno 1292 ER_TRUNCATED_WRONG_VALUE — "Incorrect <type> value: '<v>'"
#     AND "Truncated incorrect <TYPE> value: '<v>'" (datetime/integer/decimal/
#     double/…); errno 1366 ER_TRUNCATED_WRONG_VALUE_FOR_FIELD — "Incorrect string
#     value: '<v>' for column '<c>' at row <n>". One family regex covers all.
#   * PostgreSQL, value AFTER a colon — "invalid input syntax for [type] <t>:
#     \"<v>\"", "invalid input value for [enum] <t>: \"<v>\"", "date/time field
#     value out of range: \"<v>\"", "time zone displacement out of range: \"<v>\"",
#     "malformed (array|range) literal: \"<v>\"" (all empirically confirmed).
#   * PostgreSQL, value BEFORE the descriptor — "value \"<v>\" is out of range for
#     type <t>" (numeric overflow, errcode 22003; empirically confirmed against PG
#     — the value is BETWEEN ``value `` and `` is out of range``, NOT after a
#     trailing colon, so the colon-anchored family regex above cannot reach it).
#   PG echoes the value DOUBLE-quoted in the PRIMARY message (not a DETAIL: clause,
#   so _DETAIL_RE never reached it).
# Explicitly NOT redacted (documented — these errno shapes echo only the COLUMN
# name, no user value, so the schema name is preserved by design, matching the
# dup-key keyname treatment): MySQL 1264 "Out of range value for column '<c>'",
# 1406 "Data too long for column '<c>'", 1265 "Data truncated for column '<c>'";
# PG "value too long for type character varying(N)".
#
# _MYSQL_INCORRECT_VALUE_RE: greedy value ('.*') with DOTALL, bounded by a
# LOOKAHEAD so the closing "'" sits just before an optional " for column '<c>' at
# row <n>" suffix OR the message terminator ('"', ')', whitespace, EOS/newline) —
# the #1557 greedy-to-final-suffix discipline. The suffix + terminators live in
# the lookahead, so they are NOT consumed and the column NAME is preserved. DOTALL
# lets a value with an embedded quote/newline (a TEXT column) span to the final
# suffix (fail-closed — the input is one driver error's str(e)).
_MYSQL_INCORRECT_VALUE_RE = re.compile(
    r"((?:Truncated incorrect|Incorrect) (?:\w+ )?value): '.*'"
    r"(?=(?: for column '[^'\n]*' at row \d+)?[\"')\s]*(?:$|\n))",
    re.IGNORECASE | re.DOTALL,
)
# _PG_QUOTED_VALUE_RE: PG echoes the offending value DOUBLE-quoted at the tail of
# the primary message. Anchored on the known value-echoing PG phrase lead-ins so
# benign quoted identifiers elsewhere are untouched; greedy value bounded by a
# lookahead requiring only closing chars ()/./whitespace) before EOS/newline (so
# a trailing "\nHINT: …" continuation is preserved). Value redacted, phrase +
# the type-name preserved.
_PG_QUOTED_VALUE_RE = re.compile(
    r'((?:invalid input syntax for (?:type )?[^\n:"]*'
    r'|invalid input value for (?:enum )?[^\n:"]*'
    r"|date/time field value out of range"
    r"|time zone displacement out of range"
    r"|malformed (?:array|range) literal)): \"(?:.*)\""
    r"(?=[)\s.]*(?:$|\n))",
    re.IGNORECASE | re.DOTALL,
)
# _PG_VALUE_OUT_OF_RANGE_RE (issue #1569 red-team): the PG numeric-overflow shape
# ``value "<v>" is out of range for type <t>`` (errcode 22003) puts the value
# BEFORE the descriptor, so _PG_QUOTED_VALUE_RE's colon-anchored family cannot
# reach it. Empirically confirmed emitted by PG for int/smallint/bigint casts.
# Redact the double-quoted value, preserve the ``type <t>`` name. Greedy value
# anchored to the required `` is out of range for type <t>`` suffix (#1557
# greedy-to-final-suffix discipline; DOTALL for a value with an embedded newline).
_PG_VALUE_OUT_OF_RANGE_RE = re.compile(
    r'(value) "(?:.*)"( is out of range for type \w+)',
    re.IGNORECASE | re.DOTALL,
)

# _URL_CREDENTIALS_RE (issue #1737): redact the PASSWORD in a connection-string
# userinfo (``scheme://user:password@host``). A driver connect-failure exception
# CAN embed the credentialed DSN; every create_pool failure path routes through
# sanitize_db_error() calling it "defense-in-depth" against exactly that leak, so
# the sanitizer MUST actually cover it (the other regexes only redact constraint
# VALUES, not URL credentials). Username class excludes ``:`` (anchors to the
# user:pass separator) and ``@`` (no overreach when there is no password); the
# password class ``[^@\s]*`` captures any password up to the ``@`` host delimiter,
# including embedded colons. Password never spans whitespace/newline.
_URL_CREDENTIALS_RE = re.compile(r"(://[^:/?#\s@]+:)[^@\s]*(@)")
# Issue #1741: the discrete-kwargs asyncpg pools (DatabaseRegistry, staging)
# build create_pool from ``host=..., password=...`` — a connect-failure driver
# error can embed the credential in ``password=<value>`` / ``pgpassword=<value>``
# KEYWORD form, which the URL regex above does NOT match. Redact the keyword
# form too (quoted or bare) so the shape survives but the secret does not.
_KEYWORD_CREDENTIALS_RE = re.compile(
    r"(?i)\b((?:pg)?password\s*=\s*)('[^']*'|\"[^\"]*\"|[^\s'\";,)]+)"
)


def sanitize_db_error(msg: str) -> str:
    """Redact column VALUES from a DB driver error message.

    Preserves the diagnostic SHAPE (the constraint/column names in
    ``Key (col)=...`` and the presence of a ``DETAIL:`` clause) while
    replacing the value payload with ``[REDACTED]`` so a unique-violation
    on a column OTHER than the conflict target cannot leak user data into
    logs or the returned error string.

    Covers PostgreSQL (``DETAIL:`` clauses, ``Key (col)=(value)``,
    ``invalid input syntax/value for …: "<v>"``, ``… value out of range: "<v>"``)
    AND MySQL/MariaDB (``Duplicate entry 'value' for key 'name'``,
    ``Incorrect <type> value: '<v>'`` / ``Truncated incorrect <TYPE> value:
    '<v>'`` errno 1292/1366) driver-error shapes — dup-key AND the value-bearing
    non-dup-key families (issue #1569); SQLite ``UNIQUE constraint failed:
    table.col`` carries no value. Column-name-only shapes (MySQL ``Out of range
    value for column``, ``Data too long for column``) are preserved unredacted.
    """
    if not isinstance(msg, str):
        return "<non-string error>"
    # Issue #1737: redact connection-string credentials FIRST so a driver
    # connect-failure exception that embeds the credentialed DSN cannot leak
    # the password into a log line or a raised ConnectionError. Disjoint from
    # the constraint-value families below, so ordering is otherwise irrelevant.
    msg = _URL_CREDENTIALS_RE.sub(r"\1[REDACTED]\2", msg)
    # Issue #1741: also redact the ``password=<value>`` keyword form emitted by
    # discrete-kwargs connect paths (the URL regex above only matches ``://u:pw@``).
    msg = _KEYWORD_CREDENTIALS_RE.sub(r"\1[REDACTED]", msg)
    # Issue #1552 (FIX 2 + FIX 7): _KEY_VALUES_RE runs FIRST to catch any
    # ``Key (col)=(value)`` clause OUTSIDE a DETAIL: line (its ``[^)]*`` value
    # class spans newlines). Then the BLOCK _DETAIL_RE (FIX 7) redacts the ENTIRE
    # DETAIL clause including continuation lines up to the next PG structured-field
    # marker or EOS — closing the newline-truncation residuals (embedded-``)`` +
    # newline; ``Failing row contains (…)`` multi-line) the old single-line
    # ``DETAIL:[^\n]*`` leaked. _MYSQL_DUP_ENTRY_RE stays last.
    msg = _KEY_VALUES_RE.sub(r"Key (\1)=([REDACTED])", msg)
    msg = _DETAIL_RE.sub("DETAIL: [REDACTED]", msg)
    # Issue #1557: greedy anchor to the final ``' for key '<name>'`` suffix,
    # preserving the key name via the replacement fn.
    msg = _MYSQL_DUP_ENTRY_RE.sub(_redact_mysql_dup_entry, msg)
    # Issue #1556: MongoDB E11000 ``dup key: { field: "value" }`` payload.
    msg = _MONGO_DUP_KEY_RE.sub("dup key: { [REDACTED] }", msg)
    # Issue #1569: value-bearing NON-dup-key families. MySQL ``Incorrect <type>
    # value: '<v>'`` / ``Truncated incorrect <TYPE> value: '<v>'`` (errno
    # 1292/1366) and PostgreSQL ``invalid input syntax/value for …: "<v>"`` /
    # ``… value out of range: "<v>"``. Redact the value, preserve the type word +
    # any trailing ``for column '<c>'`` schema name. Disjoint preambles from the
    # dup-key subs above, so ordering is irrelevant.
    msg = _MYSQL_INCORRECT_VALUE_RE.sub(r"\1: '[REDACTED]'", msg)
    msg = _PG_QUOTED_VALUE_RE.sub(r'\1: "[REDACTED]"', msg)
    # Issue #1569 red-team: PG numeric-overflow ``value "<v>" is out of range for
    # <t>`` where ``<t>`` is a type name (value BEFORE the descriptor — the
    # colon-anchored sub above misses it).
    msg = _PG_VALUE_OUT_OF_RANGE_RE.sub(r'\1 "[REDACTED]"\2', msg)
    return msg


__all__ = [
    "DDLFailedError",
    "MigrationNotAppliedError",
    "BulkUpsertConflictTargetError",
    "UpsertConflictTargetError",
    "TenantNaturalKeyCollisionError",
    "format_tenant_natural_key_collision_message",
    "is_pk_unique_violation",
    "is_conflict_target_error",
    "sanitize_db_error",
    "DataFlowError",
]

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""QueryDialect strategy pattern for cross-database SQL generation.

Provides an abstract base class ``QueryDialect`` and concrete implementations
for PostgreSQL, MySQL, and SQLite.  The canonical placeholder is ``?``
(SQLite style); ``translate_query`` converts to the dialect's native format.

This module has **zero** external dependencies — it generates SQL strings only.
"""

from __future__ import annotations

import logging
import sys
import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from kailash.utils.url_credentials import mask_url

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseType",
    "IdentifierError",
    "QueryDialect",
    "PostgresDialect",
    "MySQLDialect",
    "SQLiteDialect",
    "detect_dialect",
    "POSTGRES_MAX_IDENTIFIER_LENGTH",
    "MYSQL_MAX_IDENTIFIER_LENGTH",
    "SQLITE_MAX_IDENTIFIER_LENGTH",
    "DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH",
]

# ---------------------------------------------------------------------------
# Per-dialect identifier length limits — SINGLE SOURCE OF TRUTH (issue #1971)
# ---------------------------------------------------------------------------
# These are the canonical values for the whole platform. DataFlow's
# ``dataflow.adapters.dialect`` imports them rather than restating the
# integers, so the two live dialect hierarchies (core SDK ``QueryDialect``
# for kailash.tracking/kailash.trust, DataFlow ``SQLDialect`` for the
# generated CRUD nodes) can never drift on the value that decides whether an
# identifier is legal.
POSTGRES_MAX_IDENTIFIER_LENGTH = 63  # PostgreSQL NAMEDATALEN - 1
MYSQL_MAX_IDENTIFIER_LENGTH = 64  # MySQL identifier length limit
SQLITE_MAX_IDENTIFIER_LENGTH = 128  # SQLite practical limit


#: Budget for call sites that have **no dialect bound** at validation time.
#:
#: This is the LOOSEST supported budget (SQLite's 128) and it is deliberately
#: NOT a safe default — it is the *explicit, greppable* marker of a call site
#: that could not name its target engine. A site passing this accepts an
#: identifier PostgreSQL would truncate server-side at 63 (issue #1971:
#: server-side truncation silently ALIASES two models onto one physical
#: table). Every site using it is a standing invitation to wire the real
#: budget: ``grep -rn DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH`` enumerates the
#: remaining work.
#:
#: Code that HAS a dialect MUST pass that dialect's own budget instead —
#: ``QueryDialect._validate_identifier`` does this automatically.
class _UnknownBudget(int):
    """Sentinel budget: numerically SQLite's, but IDENTITY-distinguishable.

    The unknown-dialect budget deliberately EQUALS SQLite's (128) — that is the
    loosest real budget and the intended fail-open value. But the warn trigger
    used to be a VALUE comparison (`max_length == DIALECT_UNKNOWN_...`), and
    since the two are the same number a caller that had CORRECTLY bound itself
    to SQLite was indistinguishable from one that had bound nothing at all, and
    warned spuriously on every identifier.

    SQLite is this ecosystem's default store, so that false positive fired on
    the most common configuration — and a warning that fires when nothing is
    wrong is the fastest way to train operators to filter the channel, which
    then hides the real unbound case it exists to surface.

    Subclassing `int` keeps every numeric use working unchanged (`len(name) >
    max_length`, `%d` formatting, comparisons); only the TRIGGER switches from
    equality to an isinstance check, which is what makes it discriminate.
    """

    __slots__ = ()


DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH = _UnknownBudget(SQLITE_MAX_IDENTIFIER_LENGTH)

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_JSON_PATH_RE = re.compile(r"^[a-zA-Z0-9_.]+$")


class IdentifierError(ValueError):
    """Raised when a SQL identifier fails safety validation.

    Subclasses ``ValueError`` so existing call sites that catch
    ``ValueError`` (e.g. `_validate_identifier` raisers) continue to
    work. Error messages NEVER echo the raw input verbatim — they
    use a fingerprint hash (`hash(name) & 0xFFFF:04x`) to prevent
    log poisoning / stored-XSS-via-error-message.

    Per ``rules/dataflow-identifier-safety.md`` MUST Rule 2, the
    quote-identifier contract requires distinct typed error surfaces
    so DDL-layer callers can distinguish identifier-validation
    failures from unrelated ``ValueError`` raises in surrounding
    code.
    """

    pass


def _identifier_fingerprint(name: object) -> str:
    """Return a 4-hex-digit fingerprint of *name* safe on unhashable inputs.

    The fingerprint is a stable, non-reversible tag that lets operators
    correlate errors in logs without echoing the raw (possibly malicious)
    payload. Unhashable inputs (``dict``, ``list``, ``set``) that would
    otherwise crash ``hash()`` are fingerprinted as ``"____"`` so the
    caller can still raise a typed ``ValueError`` with a useful marker.
    """
    try:
        return f"{hash(name) & 0xFFFF:04x}"
    except TypeError:
        return "____"


#: Call sites that have already been warned about the unknown-dialect budget,
#: keyed by ``(filename, lineno)`` so each site warns exactly once per process.
_UNKNOWN_BUDGET_WARNED_SITES: set = set()


def _warn_unknown_identifier_budget_once() -> None:
    """Emit a one-time WARN naming the call site using the unknown budget.

    ``DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH`` is the LOOSEST budget (SQLite's
    128) and is deliberately NOT safe — a site passing it accepts an identifier
    PostgreSQL truncates server-side at 63, silently ALIASING two models onto
    one physical table (#1971).

    Before this, that hazard was documented ONLY in a source comment, which is
    invisible at runtime. Per ``rules/security.md`` § "Secure-Default For A New
    Security Feature", a control whose default makes it inert MUST fail closed
    OR emit a loud one-time WARN naming the unprotected surface and its wiring.
    Failing closed is not available here — the unbound budget is load-bearing
    for genuinely dialect-less callers — so the WARN is the required half.

    Once per SITE, not once per call: a migration validating 400 identifiers
    from one loop must not emit 400 lines, but two different unbound call sites
    are two different findings and both need to be visible.
    """
    try:
        # Walk out of this module to attribute the warning to the real caller
        # rather than to the internal validator that forwarded the budget.
        frame = sys._getframe(1)
        this_file = __file__
        while frame is not None and frame.f_code.co_filename == this_file:
            frame = frame.f_back
        site = (frame.f_code.co_filename, frame.f_lineno) if frame else ("<unknown>", 0)
    except Exception:  # pragma: no cover - frame introspection is best-effort
        site = ("<unknown>", 0)

    if site in _UNKNOWN_BUDGET_WARNED_SITES:
        return
    _UNKNOWN_BUDGET_WARNED_SITES.add(site)

    logger.warning(
        "identifier.unknown_dialect_budget: %s:%s validated an identifier "
        "against DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH (%d, SQLite's — the "
        "LOOSEST). If this path can reach PostgreSQL, an identifier of "
        "64-%d chars passes validation here and is TRUNCATED server-side at "
        "63, which can alias two models onto one table (#1971). Bind the "
        "target dialect and pass its budget "
        "(dialect._MAX_IDENTIFIER_LENGTH) instead.",
        site[0],
        site[1],
        DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
        DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
    )


def _validate_identifier(name: str, *, max_length: int) -> None:
    """Validate a SQL identifier (table or column name).

    This is the validate-only primitive for sites that interpolate
    an identifier into SQL WITHOUT wrapping it in dialect quotes —
    for example, `upsert` column lists where the SET clause embeds
    bare column names (`col = EXCLUDED.col`), or hardcoded-identifier
    lists that defense-in-depth validate per
    ``rules/dataflow-identifier-safety.md`` Rule 5.

    DDL paths that interpolate dynamic identifiers into statements
    like ``CREATE INDEX``, ``CREATE TABLE``, ``ALTER TABLE``, or
    ``DROP`` MUST use ``dialect.quote_identifier(name)`` instead —
    which both validates AND wraps in dialect-appropriate quotes
    (per ``rules/dataflow-identifier-safety.md`` MUST Rule 1).

    ``max_length`` is REQUIRED — it has no default, deliberately.
    An identifier budget is a property of the TARGET ENGINE, and this
    free function cannot know the engine. Both candidate defaults are
    wrong in opposite directions:

    * **128 (SQLite, the loosest)** — the pre-fix default — is
      fail-OPEN. It let ``PostgresDialect.upsert()`` accept a 100-char
      identifier that the SAME object's ``quote_identifier()``
      rejected, then interpolate the bare name into SQL. PostgreSQL
      truncates server-side at 63, silently ALIASING two distinct
      models onto one physical table (issue #1971 verified this
      against real PostgreSQL 15.18).
    * **63 (PostgreSQL, the tightest)** would reject identifiers that
      are perfectly legal on SQLite; the codebase demonstrably
      generates names in the 64..128 band for SQLite connections.

    There is no correct default, so there is none. Callers holding a
    dialect MUST use :meth:`QueryDialect._validate_identifier`, which
    binds the budget to ``self``. Callers with genuinely no dialect in
    hand pass :data:`DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH` so the
    gap is explicit and greppable rather than silently inherited.

    Parameters
    ----------
    name
        The identifier to validate.
    max_length
        Maximum allowed length. REQUIRED (see above). PostgreSQL 63,
        MySQL 64, SQLite 128.

    Raises
    ------
    IdentifierError
        (``ValueError`` subclass) if *name* is not a string,
        exceeds the length limit, or contains characters that
        could enable SQL injection. Unhashable non-string inputs
        (``dict``, ``list``, ``set``) raise ``IdentifierError`` —
        NOT ``TypeError`` — because the fingerprint helper is
        safe on unhashable values.
    """
    # isinstance, NOT equality: the unknown budget is numerically identical to
    # SQLite's, so `==` cannot tell an unbound caller from a correctly-bound
    # SQLite one. See _UnknownBudget.
    if isinstance(max_length, _UnknownBudget):
        _warn_unknown_identifier_budget_once()
    if not isinstance(name, str):
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            f"must be a string, got {type(name).__name__}"
        )
    if len(name) > max_length:
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            f"exceeds {max_length}-char limit (len={len(name)})"
        )
    if not _IDENTIFIER_RE.match(name):
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            "must match [a-zA-Z_][a-zA-Z0-9_]*"
        )


def _quote_identifier_impl(
    name: str,
    *,
    max_length: int,
    quote_char: str,
) -> str:
    """Validate *name* against the allowlist regex AND wrap it in
    *quote_char* for dialect-appropriate identifier quoting.

    Contract per ``rules/dataflow-identifier-safety.md`` MUST Rule 2:

    1. **Validate** against ``^[a-zA-Z_][a-zA-Z0-9_]*$`` (baseline).
    2. **Reject** — the raise does NOT echo the raw input; only a
       fingerprint hash is emitted for forensic correlation.
    3. **Check length** against *max_length* (PG 63 / MySQL 64 /
       SQLite 128).
    4. **Quote** with *quote_char* (``"`` for PG/SQLite, ``\u0060``
       for MySQL).
    5. **Do NOT escape** embedded quote characters — invalid
       inputs are rejected outright.
    """
    if not isinstance(name, str):
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            f"must be a string, got {type(name).__name__}"
        )
    if len(name) > max_length:
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            f"exceeds {max_length}-char limit (len={len(name)})"
        )
    if not _IDENTIFIER_RE.match(name):
        raise IdentifierError(
            f"Invalid SQL identifier "
            f"(fingerprint={_identifier_fingerprint(name)}): "
            "must match [a-zA-Z_][a-zA-Z0-9_]*"
        )
    return f"{quote_char}{name}{quote_char}"


def _validate_json_path(path: str) -> None:
    """Validate a JSON extraction path.

    Raises
    ------
    ValueError
        If *path* contains characters that could enable SQL injection.
    """
    if not _JSON_PATH_RE.match(path):
        raise ValueError(
            f"Invalid JSON path "
            f"(fingerprint={hash(path) & 0xFFFF:04x}): "
            "must match [a-zA-Z0-9_.]+"
        )


# ---------------------------------------------------------------------------
# DatabaseType enum
# ---------------------------------------------------------------------------
class DatabaseType(Enum):
    """Supported database engine types."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class QueryDialect(ABC):
    """Abstract base for database dialect translation.

    Subclasses implement SQL generation methods that produce dialect-specific
    SQL strings.  The canonical placeholder character is ``?``.
    """

    #: Maximum identifier length for this dialect. Every concrete subclass
    #: binds this to the canonical per-dialect constant defined at the top of
    #: this module. Declared here so that inherited concrete methods (e.g.
    #: :meth:`insert_ignore`) can resolve ``self._MAX_IDENTIFIER_LENGTH``.
    _MAX_IDENTIFIER_LENGTH: int

    @property
    def max_identifier_length(self) -> int:
        """Maximum identifier length this dialect accepts.

        Public accessor for the per-dialect budget, mirroring DataFlow's
        ``SQLDialect.max_identifier_length`` so callers that GENERATE
        identifiers can fit them ahead of validation instead of discovering
        the limit as an :class:`IdentifierError` at query time.
        """
        return self._MAX_IDENTIFIER_LENGTH

    def _validate_identifier(self, name: str) -> None:
        """Validate *name* against **this dialect's own** length budget.

        Every SQL-generating method on this class MUST validate through
        this bound method rather than the module-level
        :func:`_validate_identifier` free function. The binding to
        ``self._MAX_IDENTIFIER_LENGTH`` is the structural defense against
        the defect this method exists to prevent: a validator reachable
        from a dialect object MUST NOT be able to apply a DIFFERENT
        dialect's budget.

        Before this method existed, all 21 in-class call sites invoked the
        free function with no ``max_length``, silently inheriting a 128-char
        (SQLite) budget. The observable consequence was that
        ``PostgresDialect.upsert()`` ACCEPTED a 100-char identifier that the
        same object's ``quote_identifier()`` REJECTED — two validators on one
        object disagreeing — and then interpolated the unvalidated bare name
        into SQL. Identifiers cannot be parameter-bound, so this validation
        IS the injection defense for that path (``rules/security.md``
        § Parameterized Queries).

        Raises:
            IdentifierError: If *name* is not a string, exceeds this
                dialect's budget, or fails the allowlist regex.
        """
        _validate_identifier(name, max_length=self._MAX_IDENTIFIER_LENGTH)

    @property
    @abstractmethod
    def database_type(self) -> DatabaseType:
        """Return the :class:`DatabaseType` for this dialect."""

    @abstractmethod
    def placeholder(self, index: int) -> str:
        """Return the parameter placeholder for the given 0-based *index*.

        PostgreSQL: ``$1``, ``$2``, ...
        MySQL: ``%s``
        SQLite: ``?``
        """

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """Validate *name* and return it wrapped in dialect-appropriate
        identifier quotes.

        This is the canonical helper for every DDL path that
        interpolates a dynamic identifier — ``CREATE TABLE``,
        ``CREATE INDEX``, ``ALTER TABLE``, ``DROP`` — per
        ``rules/dataflow-identifier-safety.md`` MUST Rule 1.

        Contract per MUST Rule 2:

        - PostgreSQL / SQLite: wraps in ``"``; max length 63 / 128.
        - MySQL: wraps in ``\u0060`` (backtick); max length 64.
        - Raises :class:`IdentifierError` on invalid input; error
          message does NOT echo the raw identifier.
        """

    def translate_query(self, query: str) -> str:
        """Translate a query with ``?`` placeholders to dialect-specific form.

        The default implementation calls :meth:`placeholder` for each ``?``
        found in *query*.  Subclasses that use ``?`` natively (SQLite) can
        override with a no-op for efficiency.
        """
        counter = 0

        def _replace(match: "re.Match[str]") -> str:
            nonlocal counter
            result = self.placeholder(counter)
            counter += 1
            return result

        return re.sub(r"\?", _replace, query)

    @abstractmethod
    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        """Generate an upsert statement.

        Parameters
        ----------
        table:
            Target table name.
        columns:
            All columns being inserted (including conflict keys).
        conflict_keys:
            Columns that form the unique constraint.
        update_columns:
            Columns to update on conflict.  Defaults to all *columns* that
            are **not** in *conflict_keys*.

        Returns
        -------
        tuple[str, list[str]]
            ``(sql_template, param_columns)`` where *sql_template* uses
            dialect-specific placeholders and *param_columns* lists the
            column names in parameter-binding order.
        """

    def insert_ignore(
        self, table: str, columns: List[str], conflict_keys: List[str]
    ) -> str:
        """Generate INSERT ... ignore-on-conflict statement.

        PostgreSQL/SQLite: ``INSERT INTO ... ON CONFLICT (keys) DO NOTHING``
        MySQL: ``INSERT IGNORE INTO ...``

        Returns SQL with ``?`` placeholders.
        """
        self._validate_identifier(table)
        for col in columns:
            self._validate_identifier(col)
        for key in conflict_keys:
            self._validate_identifier(key)
        cols = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        conflict = ", ".join(conflict_keys)
        return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT ({conflict}) DO NOTHING"

    def auto_id_column(self) -> str:
        """Return the auto-incrementing primary key column DDL fragment.

        PostgreSQL: ``id SERIAL PRIMARY KEY``
        MySQL: ``id INTEGER PRIMARY KEY AUTO_INCREMENT``
        SQLite: ``id INTEGER PRIMARY KEY``
        """
        return "id INTEGER PRIMARY KEY"

    def text_column(self, indexed: bool = False) -> str:
        """Return the text column type.

        For indexed columns, MySQL requires ``VARCHAR(255)`` instead of
        ``TEXT`` because MySQL cannot index ``TEXT`` without a key length.

        Parameters
        ----------
        indexed:
            If ``True``, returns a type suitable for use in indexes/unique
            constraints.  Default ``False`` returns unbounded ``TEXT``.
        """
        return "TEXT"

    def boolean_default(self, value: bool) -> str:
        """Return a boolean default expression.

        PostgreSQL: ``DEFAULT TRUE`` / ``DEFAULT FALSE``
        MySQL/SQLite: ``DEFAULT 1`` / ``DEFAULT 0``
        """
        return f"DEFAULT {1 if value else 0}"

    def blob_type(self) -> str:
        """Return the binary data column type.

        PostgreSQL: ``BYTEA``, MySQL/SQLite: ``BLOB``.
        """
        return "BLOB"

    def double_precision_type(self) -> str:
        """Return the 8-byte (IEEE 754 double-precision) float column type.

        Required for storing ``time.time()`` values without truncation:
        Python's ``time.time()`` returns a 64-bit double, but PostgreSQL
        ``REAL`` is a 4-byte single-precision float and silently truncates
        current epoch values by ~50 seconds.  Anything storing a Unix
        timestamp via ``time.time()`` MUST use this type.

        - PostgreSQL: ``DOUBLE PRECISION`` (8 bytes)
        - MySQL: ``DOUBLE`` (8 bytes)
        - SQLite: ``REAL`` (8 bytes per SQLite docs — REAL IS double-
          precision in SQLite, despite the name overlap with Postgres'
          4-byte REAL)

        See ``rules/infrastructure-sql.md`` § 4 ("dialect.blob_type() not
        hardcoded BLOB") — same dialect-portability discipline.
        """
        return "DOUBLE PRECISION"

    @abstractmethod
    def json_column_type(self) -> str:
        """Return the native JSON column type.

        PostgreSQL: ``JSONB``, MySQL: ``JSON``, SQLite: ``TEXT``.
        """

    @abstractmethod
    def json_extract(self, column: str, path: str) -> str:
        """Generate a JSON field extraction expression.

        PostgreSQL: ``column->>'path'``
        MySQL: ``JSON_EXTRACT(column, '$.path')``
        SQLite: ``json_extract(column, '$.path')``
        """

    @abstractmethod
    def for_update_skip_locked(self) -> str:
        """Return the row-level locking clause for task-queue dequeue.

        PostgreSQL/MySQL: ``FOR UPDATE SKIP LOCKED``
        SQLite: ``""`` (use ``BEGIN IMMEDIATE`` instead)
        """

    def for_update(self) -> str:
        """Return the row-level *blocking* lock clause for ``SELECT``.

        Unlike :meth:`for_update_skip_locked` (which skips already-locked
        rows for queue dequeue), this clause makes a concurrent acquirer
        BLOCK until the row lock is released — the serialization primitive
        the distributed-lock acquire path needs so two acquirers of the same
        key cannot both read-then-write an expired row.

        - PostgreSQL / MySQL: ``FOR UPDATE`` (row lock; under READ COMMITTED
          the lock-holder's commit is re-read by the blocked waiter, so the
          steal-if-expired check is serialized correctly).
        - SQLite: ``""`` — SQLite serializes writers via ``BEGIN IMMEDIATE``
          (acquired by ``ConnectionManager.transaction()``), so no per-row
          clause is needed or supported.
        """
        return "FOR UPDATE"

    @abstractmethod
    def timestamp_now(self) -> str:
        """Return the current-timestamp expression.

        PostgreSQL/MySQL: ``NOW()``
        SQLite: ``datetime('now')``
        """


# ---------------------------------------------------------------------------
# PostgresDialect
# ---------------------------------------------------------------------------
class PostgresDialect(QueryDialect):
    """PostgreSQL dialect — uses ``$1, $2, ...`` numbered placeholders."""

    _MAX_IDENTIFIER_LENGTH = POSTGRES_MAX_IDENTIFIER_LENGTH
    _QUOTE_CHAR = '"'

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.POSTGRESQL

    def placeholder(self, index: int) -> str:
        return f"${index + 1}"

    def quote_identifier(self, name: str) -> str:
        return _quote_identifier_impl(
            name,
            max_length=self._MAX_IDENTIFIER_LENGTH,
            quote_char=self._QUOTE_CHAR,
        )

    # translate_query inherited from base — replaces ? with $N

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        self._validate_identifier(table)
        for col in columns:
            self._validate_identifier(col)
        for key in conflict_keys:
            self._validate_identifier(key)
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]
        for col in update_columns:
            self._validate_identifier(col)

        placeholders = ", ".join(self.placeholder(i) for i in range(len(columns)))
        col_list = ", ".join(columns)
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )
        return sql, list(columns)

    def auto_id_column(self) -> str:
        return "id SERIAL PRIMARY KEY"

    def boolean_default(self, value: bool) -> str:
        return f"DEFAULT {'TRUE' if value else 'FALSE'}"

    def blob_type(self) -> str:
        return "BYTEA"

    def json_column_type(self) -> str:
        return "JSONB"

    def json_extract(self, column: str, path: str) -> str:
        self._validate_identifier(column)
        _validate_json_path(path)
        return f"{column}->>'{path}'"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    def timestamp_now(self) -> str:
        return "NOW()"


# ---------------------------------------------------------------------------
# MySQLDialect
# ---------------------------------------------------------------------------
class MySQLDialect(QueryDialect):
    """MySQL dialect — uses ``%s`` positional placeholders."""

    _MAX_IDENTIFIER_LENGTH = MYSQL_MAX_IDENTIFIER_LENGTH
    _QUOTE_CHAR = "`"

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.MYSQL

    def placeholder(self, index: int) -> str:
        return "%s"

    def quote_identifier(self, name: str) -> str:
        return _quote_identifier_impl(
            name,
            max_length=self._MAX_IDENTIFIER_LENGTH,
            quote_char=self._QUOTE_CHAR,
        )

    # translate_query inherited from base — replaces ? with %s

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        self._validate_identifier(table)
        for col in columns:
            self._validate_identifier(col)
        for key in conflict_keys:
            self._validate_identifier(key)
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]
        for col in update_columns:
            self._validate_identifier(col)

        placeholders = ", ".join(self.placeholder(i) for i in range(len(columns)))
        col_list = ", ".join(columns)
        update_set = ", ".join(f"{c} = VALUES({c})" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_set}"
        )
        return sql, list(columns)

    def insert_ignore(
        self, table: str, columns: List[str], conflict_keys: List[str]
    ) -> str:
        self._validate_identifier(table)
        for col in columns:
            self._validate_identifier(col)
        for key in conflict_keys:
            self._validate_identifier(key)
        cols = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        return f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})"

    def auto_id_column(self) -> str:
        return "id INTEGER PRIMARY KEY AUTO_INCREMENT"

    def text_column(self, indexed: bool = False) -> str:
        return "VARCHAR(255)" if indexed else "TEXT"

    def blob_type(self) -> str:
        return "LONGBLOB"

    def double_precision_type(self) -> str:
        """MySQL: ``DOUBLE`` (8-byte IEEE 754 float).

        ``DOUBLE PRECISION`` is also valid in MySQL but is an alias for
        ``DOUBLE``; we emit the canonical short form.  See base
        :meth:`QueryDialect.double_precision_type` for the rationale.
        """
        return "DOUBLE"

    def create_index_prefix(self) -> str:
        """Return the CREATE INDEX statement prefix.

        MySQL does not support ``IF NOT EXISTS`` on ``CREATE INDEX``.
        """
        return "CREATE INDEX"

    def json_column_type(self) -> str:
        return "JSON"

    def json_extract(self, column: str, path: str) -> str:
        self._validate_identifier(column)
        _validate_json_path(path)
        return f"JSON_EXTRACT({column}, '$.{path}')"

    def for_update_skip_locked(self) -> str:
        return "FOR UPDATE SKIP LOCKED"

    def timestamp_now(self) -> str:
        return "NOW()"


# ---------------------------------------------------------------------------
# SQLiteDialect
# ---------------------------------------------------------------------------
class SQLiteDialect(QueryDialect):
    """SQLite dialect — uses ``?`` positional placeholders (canonical)."""

    _MAX_IDENTIFIER_LENGTH = SQLITE_MAX_IDENTIFIER_LENGTH
    _QUOTE_CHAR = '"'

    @property
    def database_type(self) -> DatabaseType:
        return DatabaseType.SQLITE

    def placeholder(self, index: int) -> str:
        return "?"

    def quote_identifier(self, name: str) -> str:
        return _quote_identifier_impl(
            name,
            max_length=self._MAX_IDENTIFIER_LENGTH,
            quote_char=self._QUOTE_CHAR,
        )

    def translate_query(self, query: str) -> str:
        """SQLite uses ``?`` natively — identity translation."""
        return query

    def upsert(
        self,
        table: str,
        columns: List[str],
        conflict_keys: List[str],
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[str]]:
        self._validate_identifier(table)
        for col in columns:
            self._validate_identifier(col)
        for key in conflict_keys:
            self._validate_identifier(key)
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_keys]
        for col in update_columns:
            self._validate_identifier(col)

        placeholders = ", ".join("?" for _ in columns)
        col_list = ", ".join(columns)
        conflict_list = ", ".join(conflict_keys)
        update_set = ", ".join(f"{c} = excluded.{c}" for c in update_columns)

        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_list}) DO UPDATE SET {update_set}"
        )
        return sql, list(columns)

    def json_column_type(self) -> str:
        return "TEXT"

    def double_precision_type(self) -> str:
        """SQLite: ``REAL`` (8-byte IEEE 754 float per SQLite docs).

        Note the dialect difference: SQLite's ``REAL`` IS double-precision
        (8 bytes) per the SQLite type-affinity rules, while PostgreSQL's
        ``REAL`` is single-precision (4 bytes) and would truncate
        ``time.time()`` values.  This override emits the SQLite-native
        spelling; PostgreSQL/MySQL use the base/MySQL overrides.
        """
        return "REAL"

    def json_extract(self, column: str, path: str) -> str:
        self._validate_identifier(column)
        _validate_json_path(path)
        return f"json_extract({column}, '$.{path}')"

    def for_update_skip_locked(self) -> str:
        return ""

    def for_update(self) -> str:
        """SQLite: no per-row clause — ``BEGIN IMMEDIATE`` serializes writers."""
        return ""

    def timestamp_now(self) -> str:
        return "datetime('now')"


# ---------------------------------------------------------------------------
# detect_dialect()
# ---------------------------------------------------------------------------
def detect_dialect(url: str) -> QueryDialect:
    """Auto-detect the appropriate dialect from a database URL.

    Parameters
    ----------
    url:
        A database connection URL.  Supported schemes:

        * ``postgresql://`` or ``postgres://`` (including ``+asyncpg`` driver)
        * ``mysql://`` (including ``+aiomysql`` driver)
        * ``sqlite:///`` (including ``:///:memory:``)
        * A plain file path (treated as SQLite)

    Returns
    -------
    QueryDialect
        The dialect instance for the detected database.

    Raises
    ------
    ValueError
        If *url* is empty or uses an unsupported scheme.
    TypeError
        If *url* is not a string.
    """
    if not isinstance(url, str):
        raise TypeError(f"Database URL must be a string, got {type(url).__name__}")

    if not url.strip():
        raise ValueError(
            "Database URL must not be empty. Set KAILASH_DATABASE_URL or "
            "DATABASE_URL, or pass a URL explicitly."
        )

    url_lower = url.lower()

    # Resolve the BASE driver of a SQLAlchemy-style scheme — everything
    # before the first "+" — so every driver variant maps uniformly.
    # Pre-fix this used a per-prefix test list that covered
    # ``postgresql+`` but NOT ``postgres+``, so the ordinary
    # ``postgres+asyncpg://`` / ``postgres+psycopg2://`` DSNs raised
    # "Unsupported scheme", as did every ``mariadb`` form. Matching on the
    # base keeps this surface in parity with DataFlow's
    # ``ConnectionParser.detect_database_type``
    # (``rules/security.md`` § Enforcement-Surface Parity).
    if "://" in url_lower:
        base_scheme = url_lower.split("://", 1)[0].split("+", 1)[0]

        # PostgreSQL and its aliases
        if base_scheme in ("postgresql", "postgres", "pgsql"):
            logger.debug("Detected PostgreSQL dialect from URL: %s", mask_url(url))
            return PostgresDialect()

        # MySQL and wire-compatible forks. MariaDB speaks the MySQL
        # protocol and shares MySQL's 64-char identifier budget.
        if base_scheme in ("mysql", "mariadb"):
            logger.debug("Detected MySQL dialect from URL: %s", mask_url(url))
            return MySQLDialect()

        # SQLite
        if base_scheme == "sqlite":
            logger.debug("Detected SQLite dialect from URL: %s", mask_url(url))
            return SQLiteDialect()

    # Plain file path (relative or absolute) -> SQLite
    if url.startswith(("/", "./", "../")) or not re.match(
        r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url
    ):
        logger.debug(
            "No scheme detected; treating as SQLite file path: %s", mask_url(url)
        )
        return SQLiteDialect()

    # Unknown scheme
    scheme = url.split("://", 1)[0]
    raise ValueError(
        f"Unsupported database URL scheme '{scheme}'. "
        f"Supported: postgresql, mysql, sqlite, or a file path for SQLite."
    )

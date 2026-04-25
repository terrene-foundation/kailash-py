"""Builder for PostgreSQL ``SECURITY DEFINER`` pre-auth read helpers.

Pre-auth database read paths (login lookup, password-reset lookup,
invite-accept lookup) cannot be served by a normal RLS-scoped policy
because there is no authenticated session yet — the
``app.user_id`` GUC is still unset. The established mitigation is a
narrow ``SECURITY DEFINER`` function that runs as the function owner,
bypasses the policy on the user table, and returns a minimum-disclosure
row shape.

``SECURITY DEFINER`` functions have four load-bearing invariants that
are easy to get wrong when authored by hand:

1. **Pinned ``search_path``** — defeats CVE-2018-1058-class function-
   resolution attacks where an attacker creates an operator in the
   ``pg_temp`` schema that shadows a built-in.
2. **``REVOKE ALL FROM PUBLIC`` + ``GRANT EXECUTE TO <authenticator>``** —
   without this, every role inherits ``EXECUTE`` on the function.
3. **Timing-close dummy bcrypt compute when the user doesn't exist** —
   the caller's ~10-100ms bcrypt on a found row + 0ms on a missing row
   distinguishes "user exists" from "doesn't exist" via latency. The
   helper's own 0-row response is constant-time; the caller is
   responsible for running a ``bcrypt(candidate, DUMMY_HASH)`` on the
   0-row branch. This builder's emitted ``COMMENT`` reminds them.
4. **Multi-tenant filter inside the function body** — without
   ``AND tenant_id = p_tenant_id`` in the ``WHERE``, a caller with a
   valid session in tenant A who passes ``p_id = <user_id_from_tenant_B>``
   gets tenant B's row back (``SECURITY DEFINER`` bypasses RLS).

This builder emits all four invariants together. Callers pass the
resulting ``list[str]`` into a numbered migration's ``upgrade()``
sequence — the builder only constructs SQL; it does not execute it.

Identifier safety
-----------------

Every user-supplied identifier (function name, schema, role, table,
column, parameter name) is validated AND quoted via
:meth:`PostgreSQLDialect.quote_identifier`. Payloads like
``'"; DROP TABLE users; --'`` are rejected with
:class:`SecurityDefinerBuilderError`. PostgreSQL type strings (``text``,
``bigint``, etc.) cannot be quoted because they are type keywords, not
identifiers — they are validated against
:data:`ALLOWED_PG_TYPES` instead.

This module enforces ``rules/dataflow-identifier-safety.md`` MUST Rule
1 (every dynamic DDL identifier routes through ``quote_identifier``)
and the cross-SDK byte-shape contract pinned by
``esperie-enterprise/kailash-rs`` PR #579 / #590 — the SQL emitted by
the same builder chain is byte-identical across both SDKs.

Example
-------

.. code-block:: python

    from dataflow.migration import SecurityDefinerBuilder

    stmts = (
        SecurityDefinerBuilder("resolve_user_by_email")
        .search_path("app")
        .authenticator_role("app_role")
        .user_table("users")
        .password_column("password_hash")
        .tenant_column("tenant_id")
        .active_column("is_active")
        .param("p_email", "text")
        .param("p_tenant_id", "bigint")
        .return_column("id", "bigint")
        .return_column("email", "text")
        .return_column("password_hash", "text")
        .return_column("is_active", "boolean")
        .build()
    )
    # stmts is a list of 4 strings: CREATE FUNCTION, COMMENT, REVOKE, GRANT
    for stmt in stmts:
        await dataflow.execute_raw(stmt)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from dataflow.adapters.dialect import PostgreSQLDialect
from dataflow.adapters.exceptions import InvalidIdentifierError

__all__ = [
    "ALLOWED_PG_TYPES",
    "FunctionParam",
    "ReturnColumn",
    "SecurityDefinerBuilder",
    "SecurityDefinerBuilderError",
]


# ----------------------------------------------------------------------
# Allowlist of PostgreSQL parameter / return type strings.
#
# PostgreSQL type names appear verbatim in the emitted CREATE FUNCTION
# signature; they cannot be quote_identifier-quoted because types are
# not identifiers. Instead we reject anything outside this allowlist.
#
# The allowlist deliberately excludes user-defined entries and domain
# definitions; extend the list with explicit additions reviewed under
# `rules/dataflow-identifier-safety.md`.
#
# Cross-SDK parity — MUST stay byte-identical with the Rust crate at
# `esperie-enterprise/kailash-rs/crates/kailash-dataflow/src/migration/
# security_definer.rs::ALLOWED_PG_TYPES`. PR #583 (Rust) added
# `smallserial`, `inet`, `cidr`, `citext`, `interval` to the baseline.
# ----------------------------------------------------------------------
ALLOWED_PG_TYPES: tuple[str, ...] = (
    "bigint",
    "int",
    "integer",
    "smallint",
    "smallserial",
    "serial",
    "bigserial",
    "text",
    "varchar",
    "char",
    "citext",
    "boolean",
    "bool",
    "real",
    "double precision",
    "numeric",
    "decimal",
    "timestamp",
    "timestamptz",
    "timestamp with time zone",
    "timestamp without time zone",
    "date",
    "time",
    "interval",
    "uuid",
    "inet",
    "cidr",
    "bytea",
    "jsonb",
    "json",
)


class SecurityDefinerBuilderError(ValueError):
    """Raised when :class:`SecurityDefinerBuilder` cannot produce safe SQL.

    The error message NEVER echoes a raw, unvalidated identifier — only
    a fingerprint hash is emitted, mirroring
    :class:`InvalidIdentifierError`'s contract. This prevents log
    poisoning and stored XSS via error-message paths
    (``rules/dataflow-identifier-safety.md`` MUST Rule 2).
    """


def _normalize_pg_type(ty: str) -> str:
    """Normalize a caller-supplied PG type string.

    ``" BIGINT "`` -> ``"bigint"`` so the stored form interpolated into
    the emitted SQL matches the allowlist entry byte-for-byte. Called
    by :meth:`SecurityDefinerBuilder.param` and
    :meth:`SecurityDefinerBuilder.return_column` at insert time;
    :func:`_validate_pg_type` later re-validates the normalized form
    against :data:`ALLOWED_PG_TYPES`.

    The normalization is idempotent: calling it twice produces the
    same output. The output preserves significant internal whitespace
    (``"double precision"``, ``"timestamp with time zone"``) because
    those are legitimate multi-word PG type names.
    """
    return ty.strip().lower()


def _validate_pg_type(ty: str) -> None:
    """Validate that *ty* matches an entry in :data:`ALLOWED_PG_TYPES`."""
    for allowed in ALLOWED_PG_TYPES:
        if allowed.lower() == ty.lower():
            return
    # Build a fingerprint that does NOT echo the raw input verbatim —
    # an attacker-controlled type string could otherwise be reflected
    # into application logs.
    fingerprint = hash(ty) & 0xFFFF
    raise SecurityDefinerBuilderError(
        f"unsupported PostgreSQL type in SECURITY DEFINER signature "
        f"(fingerprint={fingerprint:04x}); "
        f"allowed types: {', '.join(ALLOWED_PG_TYPES)}"
    )


@dataclass(frozen=True)
class FunctionParam:
    """A function parameter for a SECURITY DEFINER helper.

    :ivar name: Parameter name (``p_email``, ``p_tenant_id``, ...).
    :ivar pg_type: PostgreSQL type string (``text``, ``bigint``, ...).
        Must appear in :data:`ALLOWED_PG_TYPES`.
    """

    name: str
    pg_type: str


@dataclass(frozen=True)
class ReturnColumn:
    """A return column in the ``RETURNS TABLE(...)`` clause.

    :ivar name: Column name as it appears in BOTH the
        ``RETURNS TABLE(...)`` clause AND the ``SELECT`` column list
        inside the function body.
    :ivar pg_type: PostgreSQL type string.
    """

    name: str
    pg_type: str


@dataclass
class SecurityDefinerBuilder:
    """Builder for ``SECURITY DEFINER`` pre-auth read helper migrations.

    See module docstring for the four invariants emitted and the
    rationale.

    The builder is fluent: every ``with_*`` / ``param`` /
    ``return_column`` call returns ``self``, so chains compose:

    .. code-block:: python

        stmts = (
            SecurityDefinerBuilder("resolve_user_by_email")
            .search_path("app")
            .authenticator_role("app_role")
            .user_table("users")
            .password_column("password_hash")
            .param("p_email", "text")
            .return_column("id", "bigint")
            .build()
        )

    The constructor takes an optional ``function_name`` argument so
    the canonical ``SecurityDefinerBuilder("foo")`` shape works; the
    setter form ``SecurityDefinerBuilder().function_name("foo")``
    is intentionally NOT exposed to keep the surface narrow.
    """

    _function_name: Optional[str] = None
    _search_path_schema: Optional[str] = None
    _authenticator_role: Optional[str] = None
    _user_table: Optional[str] = None
    _password_column: Optional[str] = None
    _tenant_column: Optional[str] = None
    _primary_lookup_column: Optional[str] = None
    _active_column: Optional[str] = None
    _params: List[FunctionParam] = field(default_factory=list)
    _return_columns: List[ReturnColumn] = field(default_factory=list)

    def __init__(self, function_name: Optional[str] = None) -> None:
        """Create a new builder, optionally with the function name pre-set."""
        self._function_name = function_name
        self._search_path_schema = None
        self._authenticator_role = None
        self._user_table = None
        self._password_column = None
        self._tenant_column = None
        self._primary_lookup_column = None
        self._active_column = None
        self._params = []
        self._return_columns = []

    # ------------------------------------------------------------------
    # Fluent setters
    # ------------------------------------------------------------------

    def search_path(self, schema: str) -> "SecurityDefinerBuilder":
        """Set the schema to pin in ``SET search_path = <schema>, pg_temp``."""
        self._search_path_schema = schema
        return self

    def authenticator_role(self, role: str) -> "SecurityDefinerBuilder":
        """Set the role that will receive ``GRANT EXECUTE``.

        Every other role (including ``PUBLIC``) is revoked.
        """
        self._authenticator_role = role
        return self

    def user_table(self, table: str) -> "SecurityDefinerBuilder":
        """Set the user table the helper reads from."""
        self._user_table = table
        return self

    def password_column(self, column: str) -> "SecurityDefinerBuilder":
        """Set the password column.

        Used by the emitted ``COMMENT`` to remind the caller they are
        responsible for the timing-close dummy bcrypt compare on the
        0-row branch (T7 mitigation).
        """
        self._password_column = column
        return self

    def tenant_column(self, column: str) -> "SecurityDefinerBuilder":
        """Set the tenant column for multi-tenant deployments.

        When set, the helper body includes
        ``AND <tenant_column> = p_tenant_id`` and a matching
        ``p_tenant_id`` parameter MUST be declared via :meth:`param`.
        Single-tenant deployments simply omit this call.
        """
        self._tenant_column = column
        return self

    def primary_lookup_column(self, column: str) -> "SecurityDefinerBuilder":
        """Explicitly set the primary lookup column for the emitted ``WHERE``.

        When omitted, the builder derives the column name by stripping
        the ``p_`` prefix from the first param (``p_email`` ->
        ``email``). This default works for the canonical recipe but
        breaks in two cases:

        1. The param does not start with ``p_`` (e.g.
           ``.param("email", "text")`` yields
           ``WHERE "email" = email``, where the unqualified RHS
           ``email`` collides with the column name and Postgres raises
           "column reference is ambiguous").
        2. The param name and lookup column name diverge (e.g. a REST
           handler accepts ``p_user_email`` but the schema column is
           ``email``).

        In either case call this method to pin the column name
        explicitly. The value is validated AND quoted before
        interpolation.
        """
        self._primary_lookup_column = column
        return self

    def active_column(self, column: str) -> "SecurityDefinerBuilder":
        """Enable an activity-flag guard in the emitted ``WHERE`` clause.

        When set, the builder appends ``AND "<column>" = true`` to the
        ``WHERE`` predicate. When omitted, no activity guard is emitted
        — callers with schemas that do not have a boolean activity
        column (e.g. ``status`` text columns, soft-delete
        ``deleted_at IS NULL`` semantics) simply skip this call and
        compose the guard themselves in the return path.

        The column name is validated AND quoted before interpolation.
        """
        self._active_column = column
        return self

    def param(self, name: str, pg_type: str) -> "SecurityDefinerBuilder":
        """Add an input parameter to the function signature."""
        self._params.append(
            FunctionParam(name=name, pg_type=_normalize_pg_type(pg_type))
        )
        return self

    def return_column(self, name: str, pg_type: str) -> "SecurityDefinerBuilder":
        """Add a return column to the ``RETURNS TABLE(...)`` clause."""
        self._return_columns.append(
            ReturnColumn(name=name, pg_type=_normalize_pg_type(pg_type))
        )
        return self

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self) -> List[str]:
        """Validate all builder inputs and emit the SQL statements.

        The returned list contains, in order:

        1. ``CREATE OR REPLACE FUNCTION ... SECURITY DEFINER ...``
        2. ``COMMENT ON FUNCTION ... IS '...'`` (with timing-note)
        3. ``REVOKE ALL ON FUNCTION ... FROM PUBLIC``
        4. ``GRANT EXECUTE ON FUNCTION ... TO <authenticator>``

        Callers embed these in a numbered migration's ``upgrade()`` —
        this builder does not execute SQL.

        :raises SecurityDefinerBuilderError: if any required field
            (function name, search path, authenticator role, user
            table, password column) is unset, OR any identifier fails
            validation, OR any PG type is not in
            :data:`ALLOWED_PG_TYPES`, OR ``tenant_column`` is set
            but ``p_tenant_id`` is not declared as a param, OR
            ``return_columns`` is empty, OR ``params`` is empty.
        """
        if self._function_name is None:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: function_name is required"
            )
        if self._search_path_schema is None:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: search_path is required"
            )
        if self._authenticator_role is None:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: authenticator_role is required"
            )
        if self._user_table is None:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: user_table is required"
            )
        if self._password_column is None:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: password_column is required"
            )

        if not self._return_columns:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: at least one return_column is required"
            )
        if not self._params:
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: at least one param is required"
            )

        # Multi-tenant filter consistency: if tenant_column is set,
        # p_tenant_id MUST be declared as a param (otherwise the body
        # references an undefined variable). This mirrors the Rust T8
        # check.
        if self._tenant_column is not None and not any(
            p.name == "p_tenant_id" for p in self._params
        ):
            raise SecurityDefinerBuilderError(
                "SecurityDefinerBuilder: tenant_column set but p_tenant_id "
                'param missing — add .param("p_tenant_id", "bigint") '
                "(or the matching type) to the builder"
            )

        # Validate every PG type before any quoting (loud error before
        # the dialect call so the error message is owned by THIS class
        # for cross-SDK error-shape parity).
        for p in self._params:
            _validate_pg_type(p.pg_type)
        for c in self._return_columns:
            _validate_pg_type(c.pg_type)

        # SECURITY DEFINER is a PG-only feature; SQLite + MySQL have
        # no equivalent. Use the PostgreSQL dialect for identifier
        # quoting; map InvalidIdentifierError -> SecurityDefinerBuilderError
        # so the caller's exception story is consistent.
        dialect = PostgreSQLDialect()

        def _quote(name: str) -> str:
            try:
                return dialect.quote_identifier(name)
            except InvalidIdentifierError as exc:
                # Re-raise as our own error type WITHOUT echoing raw
                # input — InvalidIdentifierError already uses a
                # fingerprint, but we layer our own marker so callers
                # can `except SecurityDefinerBuilderError`.
                raise SecurityDefinerBuilderError(
                    f"invalid identifier in SECURITY DEFINER signature: {exc}"
                ) from exc

        qfn = _quote(self._function_name)
        qschema_id = _quote(self._search_path_schema)
        qrole = _quote(self._authenticator_role)
        qtable = _quote(self._user_table)
        # password_column / tenant_column / active_column are validated
        # via _quote() defense-in-depth even when only the comment text
        # references them, so a malformed column name fails at build()
        # time rather than at apply time.
        _quote(self._password_column)
        if self._tenant_column is not None:
            _quote(self._tenant_column)

        # Param names + return-column names are routed through
        # quote_identifier so reserved words (user, order, etc.) and
        # mixed-case identifiers survive the round-trip; types stay
        # unquoted (they are type keywords, not identifiers).
        signature_parts: List[str] = []
        for p in self._params:
            qp = _quote(p.name)
            signature_parts.append(f"{qp} {p.pg_type}")
        signature = ", ".join(signature_parts)

        # The type-only argument list used by REVOKE / GRANT /
        # COMMENT ON FUNCTION ... (text, bigint, ...).
        type_list = ", ".join(p.pg_type for p in self._params)

        returns_parts: List[str] = []
        for c in self._return_columns:
            qc = _quote(c.name)
            returns_parts.append(f"{qc} {c.pg_type}")
        returns_cols = ", ".join(returns_parts)

        # SELECT column list inside the function body. Bare column
        # names that already live in the schema; quoted for
        # defense-in-depth against future model-name injection.
        select_cols = ", ".join(_quote(c.name) for c in self._return_columns)

        # WHERE predicate: the primary lookup column drives the main
        # predicate. Precedence: explicit primary_lookup_column wins;
        # otherwise derive by stripping the ``p_`` prefix from the
        # first param (backward-compatible default). The derivation
        # has footguns (see primary_lookup_column docstring), so
        # callers whose param names do not follow the ``p_<col>``
        # convention MUST set the override explicitly.
        primary_param = self._params[0]
        derived_primary_col = (
            primary_param.name[2:]
            if primary_param.name.startswith("p_")
            else primary_param.name
        )
        primary_col_name = self._primary_lookup_column or derived_primary_col
        qprimary_col = _quote(primary_col_name)
        where_clauses: List[str] = [f"{qprimary_col} = {primary_param.name}"]
        if self._tenant_column is not None:
            qtc = _quote(self._tenant_column)
            where_clauses.append(f"{qtc} = p_tenant_id")
        # Activity-flag guard is OPT-IN via active_column(col).
        # Omitting the method produces no activity predicate, which
        # accommodates schemas whose activity signal is not a boolean
        # column (text status, soft-delete timestamp, or no activity
        # flag at all).
        if self._active_column is not None:
            qac = _quote(self._active_column)
            where_clauses.append(f"{qac} = true")
        where_sql = "\n    AND ".join(where_clauses)

        # search_path body uses the unquoted schema identifier — the
        # SET search_path = ... directive takes a comma-separated
        # name list, not quoted identifiers. The schema name has
        # already been validated by _quote() above (we discard the
        # quoted return value, the validation side-effect is what
        # matters).
        create_fn = (
            f"CREATE OR REPLACE FUNCTION {qschema_id}.{qfn}({signature})\n"
            f"RETURNS TABLE ({returns_cols})\n"
            f"LANGUAGE sql\n"
            f"SECURITY DEFINER\n"
            f"SET search_path = {self._search_path_schema}, pg_temp\n"
            f"STABLE STRICT\n"
            f"AS $$\n  "
            f"SELECT {select_cols}\n  "
            f"FROM {qschema_id}.{qtable}\n  "
            f"WHERE {where_sql}\n  "
            f"LIMIT 1;\n"
            f"$$"
        )

        tenant_note = (
            " Multi-tenant filter inside body prevents T8 cross-tenant reads."
            if self._tenant_column is not None
            else ""
        )
        comment_body = (
            f"Pre-auth read helper emitted by SecurityDefinerBuilder. "
            f"SECURITY DEFINER bypasses RLS on the user table; pinned "
            f"search_path defeats CVE-2018-1058-class attacks; PUBLIC is "
            f"revoked and only {self._authenticator_role} has EXECUTE. "
            f"CALLER MUST run a dummy bcrypt compare on 0-row results "
            f"(column {self._password_column}) to close the T7 "
            f"email-enumeration timing side-channel.{tenant_note}"
        )
        comment_sql = (
            f"COMMENT ON FUNCTION {qschema_id}.{qfn}({type_list}) IS "
            f"'{comment_body.replace(chr(39), chr(39) * 2)}'"
        )

        revoke_sql = (
            f"REVOKE ALL ON FUNCTION {qschema_id}.{qfn}({type_list}) FROM PUBLIC"
        )
        grant_sql = (
            f"GRANT EXECUTE ON FUNCTION {qschema_id}.{qfn}({type_list}) TO {qrole}"
        )

        return [create_fn, comment_sql, revoke_sql, grant_sql]

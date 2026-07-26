# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests: a validator reachable from a dialect object MUST apply
THAT dialect's identifier budget — never another dialect's.

Follow-up to issue #1971, which designated ``kailash.db.dialect`` the single
source of truth for per-dialect identifier limits. A redteam lens then found
#1971's EXACT bug shape sitting inside that very file.

THE BUG
-------
``_validate_identifier(name, *, max_length=128)`` defaulted to the **SQLite**
budget, and all 21 call sites inside ``dialect.py`` passed nothing. So every
dialect's ``upsert`` / ``insert_ignore`` / ``json_extract`` validated against
128 regardless of engine. Reproduced verbatim pre-fix::

    >>> PostgresDialect().quote_identifier("a" * 100)
    IdentifierError: exceeds 63-char limit (len=100)
    >>> PostgresDialect().upsert("a" * 100, ["id"], ["id"])
    ('INSERT INTO aaaa...aaa (id) VALUES ($1) ON CONFLICT ...', ['id'])

Two validators on the SAME object disagreeing about the SAME identifier, and
``upsert`` interpolates the bare (unquoted) name straight into SQL.

WHY THIS IS SECURITY-RELEVANT, NOT MERELY A CORRECTNESS NIT
-----------------------------------------------------------
Identifiers cannot be parameter-bound — drivers bind VALUES, not table or
column names. So identifier VALIDATION is the only defense on that path
(``rules/security.md`` § Parameterized Queries). ``upsert`` embeds bare
column names in the SET clause (``col = EXCLUDED.col``), so the validator
IS the gate.

Beyond injection, the length half is a data-integrity gate: #1971 verified
against real PostgreSQL 15.18 that a >63-char ``CREATE TABLE`` is stored
under the server-TRUNCATED 63-char prefix, a second table sharing that
prefix raises ``DuplicateTableError``, and ``SELECT`` through the second
name returns the FIRST model's rows. Accepting an over-budget identifier is
therefore silent cross-model data aliasing.

WHY ``max_length`` HAS NO DEFAULT
---------------------------------
Both candidate defaults are wrong in opposite directions:

* 128 (SQLite, loosest) is fail-OPEN — the bug above.
* 63 (PostgreSQL, tightest) would reject identifiers that are legal on
  SQLite; this codebase demonstrably generates names in the 64..128 band for
  SQLite connections (see ``test_sqlite_still_accepts_names_above_postgres_budget``).

An identifier budget is a property of the TARGET ENGINE, so a function that
cannot know the engine MUST NOT invent one. The default was removed;
``QueryDialect._validate_identifier`` binds the budget to ``self``.

TEETH
-----
Each test below fails if the fix is reverted:

* restore ``max_length: int = 128`` and change the 21 bound calls back to
  the free function -> ``test_postgres_upsert_rejects_over_budget_identifier``
  and ``test_upsert_and_quote_identifier_agree_at_the_boundary`` fail;
* restore the default alone -> ``test_free_function_has_no_max_length_default``
  fails;
* route any single dialect method back to the free function ->
  ``test_no_dialect_method_uses_the_unbound_validator`` fails (AST sweep, so
  it catches a call the other tests do not reach).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

import ast
import inspect
import pathlib

import pytest

from kailash.db import dialect as dialect_module
from kailash.db.dialect import (
    MYSQL_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
    IdentifierError,
    MySQLDialect,
    PostgresDialect,
    QueryDialect,
    SQLiteDialect,
    detect_dialect,
)

pytestmark = pytest.mark.regression

DIALECT_SOURCE = pathlib.Path(dialect_module.__file__)

ALL_DIALECTS = [
    (PostgresDialect, POSTGRES_MAX_IDENTIFIER_LENGTH),
    (MySQLDialect, MYSQL_MAX_IDENTIFIER_LENGTH),
    (SQLiteDialect, SQLITE_MAX_IDENTIFIER_LENGTH),
]


# ---------------------------------------------------------------------------
# The reported defect, reproduced as an assertion
# ---------------------------------------------------------------------------


def test_postgres_upsert_rejects_over_budget_identifier():
    """The verbatim reported defect: upsert accepted what quote_identifier rejected."""
    dialect = PostgresDialect()
    name = "a" * 100

    # quote_identifier has always rejected this.
    with pytest.raises(IdentifierError, match="63-char"):
        dialect.quote_identifier(name)

    # Pre-fix, THIS returned a SQL string. It must now raise, with the
    # PostgreSQL budget named — not SQLite's 128.
    with pytest.raises(IdentifierError, match="63-char"):
        dialect.upsert(name, ["id", "value"], ["id"])


def test_postgres_upsert_rejects_over_budget_column_name():
    """The SET clause embeds bare column names, so columns need the same gate."""
    dialect = PostgresDialect()
    over_budget_column = "c" * 100

    with pytest.raises(IdentifierError, match="63-char"):
        dialect.upsert("users", ["id", over_budget_column], ["id"])


@pytest.mark.parametrize("dialect_cls,limit", ALL_DIALECTS)
def test_upsert_and_quote_identifier_agree_at_the_boundary(dialect_cls, limit):
    """Two validators on one object MUST NOT disagree about one identifier.

    Checked exactly at the budget edge, which is where a wrong-dialect
    default hides: with the 128 default, Postgres accepted everything up to
    128 through upsert while rejecting anything over 63 through
    quote_identifier.
    """
    dialect = dialect_cls()
    at_limit = "a" * limit
    over_limit = "a" * (limit + 1)

    # At the limit: BOTH accept.
    dialect.quote_identifier(at_limit)
    dialect.upsert(at_limit, ["id"], ["id"])
    dialect.insert_ignore(at_limit, ["id"], ["id"])
    dialect.json_extract(at_limit, "field")

    # One over: BOTH reject, and every SQL-generating surface agrees.
    with pytest.raises(IdentifierError):
        dialect.quote_identifier(over_limit)
    with pytest.raises(IdentifierError):
        dialect.upsert(over_limit, ["id"], ["id"])
    with pytest.raises(IdentifierError):
        dialect.insert_ignore(over_limit, ["id"], ["id"])
    with pytest.raises(IdentifierError):
        dialect.json_extract(over_limit, "field")


@pytest.mark.parametrize("dialect_cls,limit", ALL_DIALECTS)
def test_error_message_names_this_dialects_budget(dialect_cls, limit):
    """The raise must name the dialect's OWN limit, so triage is not misled."""
    dialect = dialect_cls()
    with pytest.raises(IdentifierError, match=rf"exceeds {limit}-char limit"):
        dialect.upsert("a" * (limit + 1), ["id"], ["id"])


def test_sqlite_still_accepts_names_above_postgres_budget():
    """Guard against OVER-tightening — the opposite-direction regression.

    Fixing the fail-open default by hardcoding 63 everywhere would break
    SQLite, whose real budget is 128. A 100-char name is legal on SQLite and
    MUST keep working.
    """
    dialect = SQLiteDialect()
    name = "a" * 100
    assert POSTGRES_MAX_IDENTIFIER_LENGTH < len(name) <= SQLITE_MAX_IDENTIFIER_LENGTH

    dialect.quote_identifier(name)
    sql, params = dialect.upsert(name, ["id", "value"], ["id"])
    assert name in sql
    assert params == ["id", "value"]


# ---------------------------------------------------------------------------
# Structural invariants — these catch a revert the behavioural tests miss
# ---------------------------------------------------------------------------


def test_free_function_has_no_max_length_default():
    """``max_length`` MUST stay required. Re-adding ANY default reopens the bug."""
    signature = inspect.signature(dialect_module._validate_identifier)
    max_length = signature.parameters["max_length"]

    assert max_length.default is inspect.Parameter.empty, (
        "kailash.db.dialect._validate_identifier grew a max_length default "
        f"({max_length.default!r}). An identifier budget is a property of the "
        "TARGET ENGINE; a function that cannot know the engine MUST NOT invent "
        "one. 128 is fail-open (Postgres accepts what it must reject); 63 "
        "breaks legal SQLite names. Pass the budget explicitly instead."
    )
    assert max_length.kind is inspect.Parameter.KEYWORD_ONLY


def test_no_dialect_method_uses_the_unbound_validator():
    """AST sweep: no method in dialect.py may reach the free function bare.

    This is the tripwire that survives refactors the behavioural tests do
    not exercise. Every call inside ``dialect.py`` MUST be either
    ``self._validate_identifier(...)`` (budget bound to the instance) or an
    explicit ``max_length=`` call.
    """
    tree = ast.parse(DIALECT_SOURCE.read_text())

    offenders = []
    bound_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "_validate_identifier":
            if not any(kw.arg == "max_length" for kw in node.keywords):
                offenders.append(node.lineno)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "_validate_identifier"
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            bound_calls += 1

    assert not offenders, (
        f"{DIALECT_SOURCE.name} lines {offenders} call the module-level "
        "_validate_identifier without an explicit max_length. A dialect "
        "method MUST use self._validate_identifier(name) so the budget comes "
        "from self._MAX_IDENTIFIER_LENGTH — otherwise Postgres/MySQL "
        "identifiers get validated against another dialect's limit (#1971)."
    )
    assert bound_calls >= 21, (
        f"expected >=21 self._validate_identifier call sites, found "
        f"{bound_calls} — a dialect method lost its identifier validation"
    )


@pytest.mark.parametrize("dialect_cls,limit", ALL_DIALECTS)
def test_bound_validator_uses_this_dialects_budget(dialect_cls, limit):
    """``self._validate_identifier`` resolves to this dialect's own budget."""
    dialect = dialect_cls()
    assert dialect._MAX_IDENTIFIER_LENGTH == limit
    assert dialect.max_identifier_length == limit

    dialect._validate_identifier("a" * limit)
    with pytest.raises(IdentifierError, match=rf"exceeds {limit}-char limit"):
        dialect._validate_identifier("a" * (limit + 1))


def test_every_concrete_dialect_binds_a_budget():
    """A subclass without ``_MAX_IDENTIFIER_LENGTH`` would AttributeError at runtime."""
    for subclass in (PostgresDialect, MySQLDialect, SQLiteDialect):
        assert isinstance(getattr(subclass, "_MAX_IDENTIFIER_LENGTH", None), int)
    assert "_MAX_IDENTIFIER_LENGTH" in QueryDialect.__annotations__


def test_injection_payloads_still_rejected_by_every_dialect():
    """The length fix must not weaken the allowlist half of the contract."""
    payloads = [
        'users"; DROP TABLE customers; --',
        "name WITH DATA",
        "123_starts_with_digit",
        "idx; DROP TABLE users; --",
        "invalid name",
    ]
    for dialect_cls, _ in ALL_DIALECTS:
        dialect = dialect_cls()
        for payload in payloads:
            with pytest.raises(IdentifierError):
                dialect.upsert(payload, ["id"], ["id"])
            with pytest.raises(IdentifierError):
                dialect.quote_identifier(payload)


def test_identifier_error_never_echoes_raw_payload():
    """Error messages stay fingerprint-only (no log poisoning via the raise)."""
    payload = 'evil"; DROP TABLE users; --' + "z" * 200
    for dialect_cls, _ in ALL_DIALECTS:
        with pytest.raises(IdentifierError) as excinfo:
            dialect_cls().upsert(payload, ["id"], ["id"])
        assert payload not in str(excinfo.value)


# ---------------------------------------------------------------------------
# detect_dialect: real SQLAlchemy DSN forms, and unknown schemes fail closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected,expected_limit",
    [
        ("postgresql://u:p@h/d", PostgresDialect, POSTGRES_MAX_IDENTIFIER_LENGTH),
        ("postgres://u:p@h/d", PostgresDialect, POSTGRES_MAX_IDENTIFIER_LENGTH),
        (
            "postgresql+asyncpg://u:p@h/d",
            PostgresDialect,
            POSTGRES_MAX_IDENTIFIER_LENGTH,
        ),
        # These two raised "Unsupported scheme" pre-fix: the prefix ladder
        # tested "postgresql+" but never "postgres+".
        ("postgres+asyncpg://u:p@h/d", PostgresDialect, POSTGRES_MAX_IDENTIFIER_LENGTH),
        (
            "postgres+psycopg2://u:p@h/d",
            PostgresDialect,
            POSTGRES_MAX_IDENTIFIER_LENGTH,
        ),
        ("mysql://u:p@h/d", MySQLDialect, MYSQL_MAX_IDENTIFIER_LENGTH),
        ("mysql+aiomysql://u:p@h/d", MySQLDialect, MYSQL_MAX_IDENTIFIER_LENGTH),
        # MariaDB speaks the MySQL protocol and shares its 64-char budget.
        ("mariadb://u:p@h/d", MySQLDialect, MYSQL_MAX_IDENTIFIER_LENGTH),
        ("mariadb+pymysql://u:p@h/d", MySQLDialect, MYSQL_MAX_IDENTIFIER_LENGTH),
        ("sqlite:///app.db", SQLiteDialect, SQLITE_MAX_IDENTIFIER_LENGTH),
        ("/var/lib/app.db", SQLiteDialect, SQLITE_MAX_IDENTIFIER_LENGTH),
    ],
)
def test_detect_dialect_resolves_real_dsn_forms(url, expected, expected_limit):
    dialect = detect_dialect(url)
    assert isinstance(dialect, expected)
    assert dialect.max_identifier_length == expected_limit


@pytest.mark.parametrize(
    "url", ["cockroachdb://u:p@h/d", "oracle://u:p@h/d", "gibberish://u:p@h/d"]
)
def test_detect_dialect_fails_closed_on_unknown_scheme(url):
    """An unknown scheme MUST raise — never silently resolve to a dialect."""
    with pytest.raises(ValueError, match="Unsupported database URL scheme"):
        detect_dialect(url)

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests: database-type detection MUST fail CLOSED, and identifier
truncation MUST stay collision-resistant.

Follow-up to issue #1971. #1971 made DataFlow fit GENERATED identifiers to the
connection's dialect budget. These tests cover the two ways the *input* to
that fitting was wrong.

DEFECT 1 — ``ConnectionParser.detect_database_type`` failed OPEN
---------------------------------------------------------------
The deliberate ``raise AdapterError(f"Unsupported database scheme: {scheme}")``
sat INSIDE a ``try`` whose ``except Exception:`` caught it and returned
``"sqlite"`` — the silent-fallback shape ``rules/zero-tolerance.md`` Rule 3
blocks. Verbatim pre-fix behaviour::

    >>> ConnectionParser.detect_database_type("postgres+asyncpg://u:p@h/d")
    'sqlite'
    >>> ConnectionParser.detect_database_type("mariadb://u:p@h/d")
    'sqlite'
    >>> ConnectionParser.detect_database_type("gibberish://u:p@h/d")
    'sqlite'

``postgres+asyncpg://``, ``postgres+psycopg2://``, ``mariadb://`` and
``mariadb+pymysql://`` are ordinary SQLAlchemy DSNs. The prefix ladder tested
``startswith("postgresql+")`` but never ``postgres+``, and had no MariaDB
branch at all.

The blast radius is the #1971 bug itself: this answer selects the identifier
budget. ``sqlite`` grants 128 where PostgreSQL allows 63, so generated names
sail past validation, PostgreSQL truncates them server-side at 63, and two
distinct models silently ALIAS onto one physical table (#1971 verified this
against real PostgreSQL 15.18). The only signal was a ``logger.debug``.

RAISING is the fix rather than "fall back to the tightest budget" because
this function returns an ENGINE SELECTOR, not a length: it picks the adapter,
the dialect, the placeholder syntax and the DDL types. Answering ``sqlite``
opens a local file named after the DSN (writes land in the wrong database
entirely); answering ``postgresql`` emits PostgreSQL-only DDL at a server
that rejects it. There is no safe guess.

DEFECT 2 — ``StagingUtilities`` truncated with no digest
--------------------------------------------------------
``sanitize_database_identifier`` and ``generate_staging_database_name`` cut
over-budget names with a bare prefix slice, so two identifiers sharing the
first N characters resolved to ONE database/table name — the same aliasing
#1971 fixed for generated table names, in a helper that never got the fix.

TEETH
-----
* Restore the ``except Exception: return "sqlite"`` swallow ->
  ``test_unknown_scheme_raises_instead_of_defaulting_to_sqlite`` and
  ``test_sqlalchemy_driver_dsns_resolve_to_the_right_engine`` fail.
* Restore ``sanitized = sanitized[:max_length]`` ->
  ``test_sanitize_identifier_truncation_is_collision_resistant`` fails.
* Restore the ``AutoMigrationSystem`` prefix ladder ->
  ``test_auto_migration_system_detection_matches_connection_parser`` fails
  on ``mariadb://`` (it answered ``"postgresql"``).

Tier 1: pure functions, no infrastructure, no mocks.
Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

import ast
import pathlib

import pytest
from kailash.db.dialect import (
    MYSQL_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
)

from dataflow.adapters import connection_parser as connection_parser_module
from dataflow.adapters.connection_parser import ConnectionParser
from dataflow.adapters.exceptions import AdapterError
from dataflow.migrations.staging_utilities import StagingUtilities

pytestmark = pytest.mark.regression

# The budget each detected engine grants. This is the chain that made the
# fail-open default a data-integrity bug rather than a cosmetic one.
BUDGET_FOR = {
    "postgresql": POSTGRES_MAX_IDENTIFIER_LENGTH,
    "mysql": MYSQL_MAX_IDENTIFIER_LENGTH,
    "sqlite": SQLITE_MAX_IDENTIFIER_LENGTH,
}

# Every DSN form that returned "sqlite" pre-fix, with the engine it must
# actually resolve to.
FAIL_OPEN_DSNS = [
    ("postgres+asyncpg://u:p@h/d", "postgresql"),
    ("postgres+psycopg2://u:p@h/d", "postgresql"),
    ("postgres+psycopg://u:p@h/d", "postgresql"),
    ("mariadb://u:p@h/d", "mysql"),
    ("mariadb+pymysql://u:p@h/d", "mysql"),
    ("mariadb+mariadbconnector://u:p@h/d", "mysql"),
]

ALREADY_WORKING_DSNS = [
    ("postgresql://u:p@h/d", "postgresql"),
    ("postgres://u:p@h/d", "postgresql"),
    ("postgresql+asyncpg://u:p@h/d", "postgresql"),
    ("postgresql+psycopg2://u:p@h/d", "postgresql"),
    ("mysql://u:p@h/d", "mysql"),
    ("mysql+pymysql://u:p@h/d", "mysql"),
    ("mysql+aiomysql://u:p@h/d", "mysql"),
    ("sqlite:///app.db", "sqlite"),
    ("sqlite:///:memory:", "sqlite"),
]


# ---------------------------------------------------------------------------
# Defect 1: fail-closed detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dsn,expected", FAIL_OPEN_DSNS)
def test_sqlalchemy_driver_dsns_resolve_to_the_right_engine(dsn, expected):
    """These ordinary DSNs all returned "sqlite" pre-fix."""
    assert ConnectionParser.detect_database_type(dsn) == expected


@pytest.mark.parametrize("dsn,expected", ALREADY_WORKING_DSNS)
def test_previously_working_dsns_still_resolve(dsn, expected):
    """Guard the forms that already worked — no regression from the rewrite."""
    assert ConnectionParser.detect_database_type(dsn) == expected


@pytest.mark.parametrize("dsn,expected", FAIL_OPEN_DSNS + ALREADY_WORKING_DSNS)
def test_detected_engine_grants_the_right_identifier_budget(dsn, expected):
    """The consequence that made this a data-integrity bug, asserted directly.

    A wrong answer here is not just a mislabelled engine: it hands the
    identifier generator the wrong budget. Pre-fix every FAIL_OPEN_DSN got
    128 instead of 63/64.
    """
    detected = ConnectionParser.detect_database_type(dsn)
    assert BUDGET_FOR[detected] == BUDGET_FOR[expected]

    if expected != "sqlite":
        assert BUDGET_FOR[detected] < SQLITE_MAX_IDENTIFIER_LENGTH, (
            f"{dsn} resolved to a budget of {BUDGET_FOR[detected]}; the "
            "SQLite budget (128) would let generated names exceed the real "
            "server limit and alias two models onto one table (#1971)"
        )


@pytest.mark.parametrize(
    "dsn",
    [
        "cockroachdb://u:p@h/d",
        "oracle://u:p@h/d",
        "mssql+pyodbc://u:p@h/d",
        "redshift+psycopg2://u:p@h/d",
        "gibberish://u:p@h/d",
    ],
)
def test_unknown_scheme_raises_instead_of_defaulting_to_sqlite(dsn):
    """An unrecognised scheme MUST raise. It returned "sqlite" pre-fix."""
    with pytest.raises(AdapterError, match="Unsupported database scheme"):
        ConnectionParser.detect_database_type(dsn)


def test_unknown_scheme_error_names_the_scheme_and_refuses_to_guess():
    """The raise must be actionable, not a bare failure."""
    with pytest.raises(AdapterError) as excinfo:
        ConnectionParser.detect_database_type("cockroachdb://u:p@h/d")
    message = str(excinfo.value)
    assert "cockroachdb" in message
    assert "postgresql" in message  # lists supported schemes
    assert "Refusing to guess" in message


def test_no_except_clause_swallows_the_unsupported_scheme_raise():
    """Structural tripwire: the deliberate raise must not sit inside a swallow.

    The behavioural tests above catch today's swallow. This catches a future
    refactor that reintroduces a broad ``except`` around the mapping — the
    exact shape that made the original raise unreachable-as-an-error.
    """
    source = pathlib.Path(connection_parser_module.__file__).read_text()
    tree = ast.parse(source)

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "detect_database_type":
            target = node
            break
    assert target is not None, "detect_database_type not found"

    # Locate the deliberate unsupported-scheme raise.
    unsupported_raises = [
        node
        for node in ast.walk(target)
        if isinstance(node, ast.Raise)
        and "Unsupported database scheme" in ast.dump(node)
    ]
    assert unsupported_raises, "the unsupported-scheme raise disappeared"

    # No `try` inside this function may enclose it.
    for node in ast.walk(target):
        if not isinstance(node, ast.Try):
            continue
        enclosed = {id(n) for stmt in node.body for n in ast.walk(stmt)}
        for raise_node in unsupported_raises:
            assert id(raise_node) not in enclosed, (
                "the 'Unsupported database scheme' raise is enclosed by a try "
                "block again — an except clause there swallows it and the "
                "function silently returns a default engine "
                "(rules/zero-tolerance.md Rule 3)"
            )


def test_none_and_non_string_inputs_raise():
    with pytest.raises(AdapterError):
        ConnectionParser.detect_database_type(None)
    with pytest.raises(AdapterError):
        ConnectionParser.detect_database_type(12345)


@pytest.mark.parametrize(
    "path", [":memory:", "app.db", "data.sqlite", "data.sqlite3", "/var/lib/app.db"]
)
def test_file_paths_still_resolve_to_sqlite(path):
    """SQLite file paths are a RECOGNISED case, not a fallback — keep working."""
    assert ConnectionParser.detect_database_type(path) == "sqlite"


def test_mongodb_uris_still_detected():
    assert ConnectionParser.detect_database_type("mongodb://h:27017/d") == "mongodb"
    assert (
        ConnectionParser.detect_database_type("mongodb+srv://u:p@cluster/d")
        == "mongodb"
    )


# ---------------------------------------------------------------------------
# Defect 1b: fail-CLOSED must not reject SQLite's own URI-filename form
# ---------------------------------------------------------------------------
#
# The fail-closed rewrite above replaced a swallow-everything default with an
# explicit allowlist — and the allowlist was built from DSN forms alone. It
# never learned ``file:``, SQLite's documented URI-filename scheme
# (https://sqlite.org/uri.html), which is the form issue #1502 injects for a
# bare ``:memory:`` instance: ``file:df_mem_<id>?mode=memory&cache=shared``.
#
# Verbatim post-#1971 / pre-fix behaviour::
#
#     >>> ConnectionParser.detect_database_type(
#     ...     "file:df_mem_10c4a8?mode=memory&cache=shared")
#     AdapterError: Unsupported database scheme: file. ...
#
# So every DataFlow(":memory:") instance raised the moment any path consulted
# the detector — ``SyncDDLExecutor.__init__`` on ``create_tables_async``, and
# ``ModelRegistry.initialize()`` (which caught it and returned False, so the
# registry table was never created). Six sibling surfaces
# (``sync_ddl_executor._get_sqlite_connection``, ``adapters/sqlite.py``,
# ``migration_connection_manager``, ``migration_test_framework``, core
# ``nodes/data/sql.py`` and ``nodes/data/async_sql.py``) already opened this
# exact form with ``uri=True``; only the single source of truth they consult
# had never learned it — an enforcement-surface-parity gap
# (``rules/security.md`` § Enforcement-Surface Parity).
#
# The fix is a POSITIVE allowlist entry, NOT a permissive fallback: the
# fail-closed tests above still pass unchanged.

SQLITE_URI_FORMS = [
    # The exact shape DataFlow(":memory:") builds (engine.py `_memory_db_uri`).
    "file:df_mem_10c4a8?mode=memory&cache=shared",
    # A user-supplied shared-cache in-memory DB.
    "file:memdb1?mode=memory&cache=shared",
    # URI-only options that have no `sqlite:///` spelling.
    "file:/var/lib/app.db?mode=ro",
    "file:/var/lib/app.db?immutable=1",
    # A plain relative/absolute URI filename.
    "file:app.db",
    "file:/var/lib/app.db",
]


@pytest.mark.parametrize("uri", SQLITE_URI_FORMS)
def test_sqlite_file_uri_form_detects_as_sqlite(uri):
    """SQLite's ``file:`` URI-filename form MUST resolve to sqlite.

    Pre-fix every one of these raised ``AdapterError: Unsupported database
    scheme: file``, which took out DataFlow(":memory:") entirely (#1502).
    """
    assert ConnectionParser.detect_database_type(uri) == "sqlite"


@pytest.mark.parametrize("uri", SQLITE_URI_FORMS)
def test_sqlite_file_uri_form_grants_the_sqlite_identifier_budget(uri):
    """A ``file:`` URI opens a SQLite database, so it MUST get SQLite's budget.

    Guards the #1971 chain from the other direction: the allowlist entry must
    map to the engine that is actually opened, not merely to *some* engine
    that stops the raise.
    """
    detected = ConnectionParser.detect_database_type(uri)
    assert BUDGET_FOR[detected] == SQLITE_MAX_IDENTIFIER_LENGTH


@pytest.mark.parametrize("uri", SQLITE_URI_FORMS)
def test_engine_url_validator_accepts_the_sqlite_file_uri_form(uri):
    """Enforcement-surface parity: ``DataFlow.__init__``'s gate agrees.

    ``_is_valid_database_url`` is a SECOND, independent validator (engine.py),
    consulted at ``DataFlow(database_url)`` before the detector is ever
    reached. It matched on ``"://"``, which a ``file:`` URI does not carry, so
    it fell through to a bare-path heuristic and rejected every form above —
    ``DataFlow("file:/var/lib/app.db?mode=ro")`` raised
    ``INVALID_DATABASE_URL``. Both validators MUST recognise the same set of
    legitimate SQLite forms or the parity gap re-opens on the other surface.
    """
    from dataflow.core.engine import DataFlow

    validator = DataFlow.__new__(DataFlow)
    assert validator._is_valid_database_url(uri) is True


@pytest.mark.parametrize(
    "url",
    [
        "gibberish://u:p@h/d",
        "oracle://u:p@h/d",
        "cockroachdb://u:p@h/d",
    ],
)
def test_engine_url_validator_still_rejects_unknown_schemes(url):
    """The ``file:`` allowlist entry MUST NOT widen the validator.

    Teeth for the fix itself: had ``file:`` been added as a permissive
    fallback (accept-anything-unrecognised) rather than a positive allowlist
    entry, this test would fail.
    """
    from dataflow.core.engine import DataFlow

    validator = DataFlow.__new__(DataFlow)
    assert validator._is_valid_database_url(url) is False


def test_sqlite_file_uri_reaches_the_sync_ddl_executor():
    """End-to-end: the surface that actually broke on the shared-cache URI.

    ``SyncDDLExecutor.__init__`` calls ``_detect_db_type`` eagerly, so the
    detector raise surfaced as a constructor failure on every
    ``create_tables_async()`` for a bare ``:memory:`` instance. This asserts
    the executor both constructs AND routes to the SQLite branch.
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    executor = SyncDDLExecutor("file:df_mem_deadbeef?mode=memory&cache=shared")
    assert executor._db_type == "sqlite"


def test_sync_ddl_executor_still_fails_closed_on_unknown_scheme():
    """The executor's fail-closed contract survives the allowlist addition."""
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    with pytest.raises(AdapterError, match="Unsupported database scheme"):
        SyncDDLExecutor("oracle://u:p@h/d")


# ---------------------------------------------------------------------------
# Enforcement-surface parity: the sibling detector must agree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dsn,expected",
    FAIL_OPEN_DSNS + ALREADY_WORKING_DSNS,
)
def test_auto_migration_system_detection_matches_connection_parser(dsn, expected):
    """``AutoMigrationSystem`` maintained a third, divergent scheme ladder.

    Its fallback was ``if "://" in connection_string: return "postgresql"``,
    so ``mariadb://`` was reported as PostgreSQL and the legacy migration
    path emitted Postgres-only DDL against MariaDB — the same failure mode
    issue #1559 fixed for ``mysql://``.
    """
    from dataflow.migrations.auto_migration_system import AutoMigrationSystem

    detected = AutoMigrationSystem._detect_database_type(
        AutoMigrationSystem.__new__(AutoMigrationSystem), dsn
    )
    assert detected == expected
    assert detected == ConnectionParser.detect_database_type(dsn)


def test_auto_migration_system_fails_closed_on_unknown_scheme():
    from dataflow.migrations.auto_migration_system import AutoMigrationSystem

    with pytest.raises(AdapterError, match="Unsupported database scheme"):
        AutoMigrationSystem._detect_database_type(
            AutoMigrationSystem.__new__(AutoMigrationSystem), "oracle://u:p@h/d"
        )


# ---------------------------------------------------------------------------
# Defect 2: truncation must not alias two names onto one
# ---------------------------------------------------------------------------


def test_sanitize_identifier_truncation_is_collision_resistant():
    """Two names sharing a 63-char prefix MUST NOT collapse to one identifier."""
    shared_prefix = "customer_events_archive_" + "x" * 45
    first = shared_prefix + "_alpha"
    second = shared_prefix + "_beta"
    assert first[:63] == second[:63], "fixture must share the truncation prefix"

    got_first = StagingUtilities.sanitize_database_identifier(first)
    got_second = StagingUtilities.sanitize_database_identifier(second)

    assert len(got_first) <= 63
    assert len(got_second) <= 63
    assert got_first != got_second, (
        "sanitize_database_identifier truncated without a digest: two "
        "distinct identifiers resolved to the same name, so the second "
        "silently operates on the first's data (#1971 aliasing)"
    )


def test_sanitize_identifier_truncation_is_deterministic():
    """Same input -> same output, across processes (SHA-256, not builtin hash())."""
    name = "y" * 200
    assert StagingUtilities.sanitize_database_identifier(
        name
    ) == StagingUtilities.sanitize_database_identifier(name)


def test_sanitize_identifier_leaves_in_budget_names_byte_identical():
    """The digest must apply ONLY on overflow — no churn for normal names."""
    for name in ("users", "customer_events", "a" * 63):
        assert StagingUtilities.sanitize_database_identifier(name) == name


def test_sanitize_identifier_output_still_passes_the_allowlist():
    """Truncation must not produce something the identifier regex rejects."""
    import re

    result = StagingUtilities.sanitize_database_identifier("Z-" * 200)
    assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", result), result
    assert len(result) <= 63


def test_staging_database_name_truncation_is_collision_resistant():
    """The staging-name generator shares the defect and the fix."""
    shared = "p" * 55
    first = StagingUtilities.generate_staging_database_name(
        shared + "_alpha", timestamp_suffix=False
    )
    second = StagingUtilities.generate_staging_database_name(
        shared + "_beta", timestamp_suffix=False
    )

    assert len(first) <= 63 and len(second) <= 63
    assert first != second, (
        "two production databases sharing a name prefix generated the SAME "
        "staging database name — the second would operate on the first's data"
    )


def test_staging_database_name_with_timestamp_is_collision_resistant():
    """The timestamped branch truncated the base with a bare slice too."""
    shared = "q" * 60
    first = StagingUtilities.generate_staging_database_name(
        shared + "_alpha", timestamp_suffix=True
    )
    second = StagingUtilities.generate_staging_database_name(
        shared + "_beta", timestamp_suffix=True
    )

    assert len(first) <= 63 and len(second) <= 63
    # Strip the shared timestamp tail before comparing the bases.
    assert first[:-16] != second[:-16] or first != second


def test_staging_database_name_leaves_in_budget_names_unchanged():
    assert (
        StagingUtilities.generate_staging_database_name(
            "app_production", timestamp_suffix=False
        )
        == "staging_app_production"
    )

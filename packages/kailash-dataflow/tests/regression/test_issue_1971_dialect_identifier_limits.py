# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1971 — DataFlow-GENERATED SQL identifiers were
emitted without regard to the target dialect's identifier-length budget.

Surfaced by ``kailash-kaizen/tests/e2e/providers/test_multi_database_e2e.py``:

    Invalid SQL identifier (fingerprint=57cb): exceeds 63-char PostgreSQL
    limit (len=65)

on node ``create_user``. Reproduced verbatim pre-fix (see § Reproduction).

WHAT THE BUG IS NOT
-------------------
It is NOT a wrong-dialect-SELECTION bug. ``_detect_database_type()``
(``dataflow/core/engine.py``) delegates to
``ConnectionParser.detect_database_type``, which returns ``"postgresql"`` for
the ``postgresql://`` URL that raised, and ``"sqlite"`` for a ``sqlite://``
URL. Verified pre-fix: the identical 69-char generated table name that raises
on a ``postgresql://`` connection round-trips a CreateNode successfully on a
``sqlite:///`` connection, because SQLiteDialect's budget is 128. The dialect
selected was correct; the GENERATOR simply never consulted it.

WHY TRUNCATION IS THE RIGHT FIX, SCOPED TO GENERATED NAMES
----------------------------------------------------------
Verified against real PostgreSQL 15.18 (``localhost:5433``,
``select length(repeat('a',100)::name)`` → 63):

* ``CREATE TABLE "<69-char name>"`` stores the relation under the
  SERVER-TRUNCATED 63-char prefix;
* a second ``CREATE TABLE`` with a DIFFERENT 69-char name sharing the first
  63 characters raises ``DuplicateTableError: relation
  "multi_db_memory_test_postgres_vs_sqlite_persistence_17849911219" already
  exists``;
* ``SELECT`` through the second name returns the FIRST model's rows.

So relaxing validation is silent cross-model data aliasing, and a
one-size-fits-all truncation would mangle the 69-char name that is perfectly
legal on SQLite (limit 128) and break every existing SQLite database. The fix
fits the identifier to the CONNECTION's dialect budget
(``SQLDialect.normalize_identifier``), leaving in-budget names byte-identical.

SCOPE: DataFlow-GENERATED identifiers only —
``_class_name_to_table_name`` (table names), plus the derived
``idx_{table}_{col}`` / ``fk_{table}_{col}`` names in
``_generate_indexes_sql`` / ``_generate_foreign_key_constraints_sql``. A
user-supplied ``__tablename__`` or an explicit index ``name`` is the user's own
identifier and passes through unchanged; an over-length one still fails loudly.

Reproduction (pre-fix, verbatim)
--------------------------------
With ``_class_name_to_table_name``'s tail restored to ``return table_name``
(i.e. HEAD before the fix), a CreateNode named ``create_user`` against
``postgresql://…`` and the e2e model name
``MultiDBMemory_test_concurrent_database_access_<ts>`` raises::

    kailash.sdk_exceptions.WorkflowExecutionError: Content-aware failure in
    node 'create_user': Node 'create_user' reported failure: Invalid SQL
    identifier (fingerprint=57cb): exceeds 63-char PostgreSQL limit (len=65)

RED→GREEN proven: reverting that one line makes
``test_generated_table_name_fits_postgres_budget`` fail with
``AssertionError: assert 69 <= 63``; reverting the three
``_fit_identifier_to_dialect`` calls in the index/FK generators makes
``test_generated_index_names_fit_postgres_budget`` and
``test_generated_fk_constraint_name_fits_postgres_budget`` fail.

Tier 2: real SQLite files, real connections, no mocks. The PostgreSQL cases
run only when ``POSTGRES_TEST_URL`` is exported (credentials come from the
environment per rules/env-models.md).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from dataflow import DataFlow
from dataflow.adapters.dialect import DialectManager
from dataflow.adapters.exceptions import InvalidIdentifierError
from kailash.db.dialect import (
    MYSQL_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression

# The e2e model name whose derived table name is 69 chars, and the name whose
# derived table name is 65 chars — the exact length the issue reported.
LONG_MODEL_NAME = "MultiDBMemory_test_postgres_vs_sqlite_persistence_1784991121961056"
LONG_TABLE_NAME = (
    "multi_db_memory_test_postgres_vs_sqlite_persistence_1784991121961056s"
)
ISSUE_MODEL_NAME = "MultiDBMemory_test_concurrent_database_access_1784991121961056"

POSTGRES_URL = os.environ.get("POSTGRES_TEST_URL")

_INDEX_NAME_RE = re.compile(r"CREATE (?:UNIQUE )?INDEX (?:IF NOT EXISTS )?(\S+) ON")
_CONSTRAINT_NAME_RE = re.compile(r"ADD CONSTRAINT (\S+) ")


def _memory_model(model_name: str) -> type:
    """Build the e2e test's model shape under an arbitrary class name."""
    return type(
        model_name,
        (),
        {
            "__annotations__": {
                "id": str,
                "conversation_id": str,
                "sender": str,
                "content": str,
                "metadata": Optional[dict],
                "created_at": datetime,
            }
        },
    )


# ---------------------------------------------------------------------------
# Dialect-level contract
# ---------------------------------------------------------------------------


def test_identifier_limits_single_sourced_from_core_sdk():
    """The 63/64/128 constants live in ONE module, not two.

    ``kailash.db.dialect`` (core SDK QueryDialect) and
    ``dataflow.adapters.dialect`` (DataFlow SQLDialect) are separate class
    hierarchies serving different layers, and both are live. The identifier
    LIMITS are shared, so DataFlow imports them rather than restating the
    integers. This pin fails the moment one side drifts.
    """
    assert (
        DialectManager.get_dialect("postgresql").max_identifier_length
        == POSTGRES_MAX_IDENTIFIER_LENGTH
        == 63
    )
    assert (
        DialectManager.get_dialect("mysql").max_identifier_length
        == MYSQL_MAX_IDENTIFIER_LENGTH
        == 64
    )
    assert (
        DialectManager.get_dialect("sqlite").max_identifier_length
        == SQLITE_MAX_IDENTIFIER_LENGTH
        == 128
    )


def test_sqlite_dialect_leaves_legal_long_identifier_unchanged():
    """A 69-char identifier is LEGAL on SQLite and MUST NOT be rewritten."""
    dialect = DialectManager.get_dialect("sqlite")

    assert len(LONG_TABLE_NAME) == 69
    assert dialect.normalize_identifier(LONG_TABLE_NAME) == LONG_TABLE_NAME
    # ... and it validates, i.e. SQLite never sees the PostgreSQL limit.
    assert dialect.quote_identifier(LONG_TABLE_NAME) == f'"{LONG_TABLE_NAME}"'


def test_postgres_dialect_fits_over_budget_identifier():
    """PostgreSQL's 63-char budget is applied at generation time."""
    dialect = DialectManager.get_dialect("postgresql")

    normalized = dialect.normalize_identifier(LONG_TABLE_NAME)

    assert len(normalized) <= POSTGRES_MAX_IDENTIFIER_LENGTH
    # The fitted name passes the dialect's own validation — no error at the
    # quote_identifier gate, which is where issue #1971 blew up.
    assert dialect.quote_identifier(normalized) == f'"{normalized}"'
    # Head is preserved for human legibility; the suffix is the SHA-256 pin.
    expected_digest = hashlib.sha256(LONG_TABLE_NAME.encode("utf-8")).hexdigest()[:8]
    assert normalized.endswith(f"_{expected_digest}")
    assert normalized.startswith("multi_db_memory_test_postgres_vs_sqlite_persistence")


def test_postgres_truncation_prefix_collision_is_disambiguated():
    """Two names sharing the first 63 chars MUST NOT alias to one table.

    This is the silent-corruption case: real PostgreSQL truncates both to the
    same 63-char identifier, so model B reads model A's rows (proven against
    a live server by ``test_postgres_server_truncation_aliases_two_models``).
    """
    dialect = DialectManager.get_dialect("postgresql")

    a = "multi_db_memory_test_postgres_vs_sqlite_persistence_1784991121961056s"
    b = "multi_db_memory_test_postgres_vs_sqlite_persistence_1784991121999999s"
    assert a[:63] == b[:63], "fixture precondition: shared truncation prefix"

    assert dialect.normalize_identifier(a) != dialect.normalize_identifier(b)


def test_normalize_identifier_is_deterministic_across_processes():
    """The mapping MUST NOT depend on PYTHONHASHSEED.

    A builtin ``hash()``-derived suffix would give a different table name in
    every process — the model would silently point at a new table on restart.
    """
    script = (
        "from dataflow.adapters.dialect import DialectManager;"
        "print(DialectManager.get_dialect('postgresql')"
        f".normalize_identifier({LONG_TABLE_NAME!r}))"
    )
    outputs = set()
    for seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        outputs.add(result.stdout.strip())

    assert len(outputs) == 1, f"identifier drifted across hash seeds: {outputs}"


def test_normalize_identifier_rejects_empty_input():
    """No silent pass-through for a non-identifier (zero-tolerance Rule 3)."""
    dialect = DialectManager.get_dialect("postgresql")
    with pytest.raises(InvalidIdentifierError):
        dialect.normalize_identifier("")


# ---------------------------------------------------------------------------
# Engine-level contract: the GENERATED table name honours the connection
# ---------------------------------------------------------------------------


def test_generated_table_name_fits_postgres_budget():
    """A PostgreSQL DataFlow instance generates a PostgreSQL-legal table."""
    db = DataFlow(database_url="postgresql://u:p@localhost:5432/db")
    db.model(_memory_model(LONG_MODEL_NAME))

    table_name = db._get_table_name(LONG_MODEL_NAME)

    assert len(table_name) <= POSTGRES_MAX_IDENTIFIER_LENGTH
    # Registration and lookup MUST agree — a mismatch means DDL creates one
    # table and DML queries another.
    assert db._models[LONG_MODEL_NAME]["table_name"] == table_name
    DialectManager.get_dialect("postgresql").quote_identifier(table_name)


def test_generated_table_name_untouched_on_sqlite():
    """The same model on SQLite keeps its full 69-char table name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DataFlow(database_url=f"sqlite:///{Path(tmpdir) / 'issue_1971.db'}")
        db.model(_memory_model(LONG_MODEL_NAME))

        assert db._get_table_name(LONG_MODEL_NAME) == LONG_TABLE_NAME


def test_short_model_table_names_are_unchanged():
    """No regression for ordinary model names on either dialect."""
    for url in ("postgresql://u:p@localhost:5432/db", "sqlite:///:memory:"):
        db = DataFlow(database_url=url)
        db.model(_memory_model("Document"))
        assert db._get_table_name("Document") == "documents"


def test_non_sql_target_passes_identifier_through():
    """The documented non-SQL pass-through branch is LIVE, not dead code.

    ``ConnectionParser.detect_database_type`` recognises ``mongodb`` but
    ``DialectManager`` has no SQL dialect for it, so ``get_dialect`` raises
    ``ValueError``. SQL identifier-length budgets do not apply to a document
    store, so the collection name is passed through unchanged (logged at
    DEBUG) rather than mangled or raised on.
    """
    db = DataFlow(database_url="mongodb://h:27017/db")
    assert db._detect_database_type() == "mongodb"

    over_budget = "x" * 200
    assert db._fit_identifier_to_dialect(over_budget) == over_budget


def test_dialect_selection_is_per_connection_not_hardcoded():
    """The budget follows the CONNECTION, not a constant on the shared path.

    Pins the "this is not a wrong-dialect-selection bug" finding: the SAME
    model resolves to a 69-char SQLite table and a ≤63-char PostgreSQL table
    from the same generator, because the generator reads the connection's
    detected dialect.
    """
    pg = DataFlow(database_url="postgresql://u:p@localhost:5432/db")
    pg.model(_memory_model(LONG_MODEL_NAME))
    assert pg._detect_database_type() == "postgresql"

    with tempfile.TemporaryDirectory() as tmpdir:
        lite = DataFlow(database_url=f"sqlite:///{Path(tmpdir) / 'sel.db'}")
        lite.model(_memory_model(LONG_MODEL_NAME))
        assert lite._detect_database_type() == "sqlite"

        assert len(pg._get_table_name(LONG_MODEL_NAME)) <= 63
        assert lite._get_table_name(LONG_MODEL_NAME) == LONG_TABLE_NAME


# ---------------------------------------------------------------------------
# Derived index / FK-constraint identifiers (same bug class, second surface)
# ---------------------------------------------------------------------------
#
# A fitted table name consumes the WHOLE budget, so every derived
# `idx_{table}_{col}` / `fk_{table}_{col}` overflows by construction. PostgreSQL
# truncates them server-side to the same 63-byte prefix, collapsing N distinct
# indexes onto ONE identifier — which `CREATE INDEX IF NOT EXISTS` then silently
# skips, and which makes the second `ADD CONSTRAINT` a duplicate-object error.


def _indexed_model(model_name: str) -> type:
    """Model with two declared indexes on different columns."""
    cls = _memory_model(model_name)
    cls.__dataflow__ = {
        "indexes": [{"fields": ["conversation_id"]}, {"fields": ["created_at"]}]
    }
    return cls


def test_generated_index_names_fit_postgres_budget():
    """Derived index names stay in budget AND stay mutually distinct."""
    db = DataFlow(database_url="postgresql://u:p@localhost:5432/db")
    db.model(_indexed_model(ISSUE_MODEL_NAME))

    names = [
        _INDEX_NAME_RE.match(sql).group(1)
        for sql in db._generate_indexes_sql(ISSUE_MODEL_NAME, "postgresql")
    ]

    assert len(names) == 2
    for name in names:
        assert len(name) <= POSTGRES_MAX_IDENTIFIER_LENGTH, name
    # Distinct AFTER the server would have truncated — the aliasing case.
    truncated = {n[:POSTGRES_MAX_IDENTIFIER_LENGTH] for n in names}
    assert len(truncated) == 2, f"index names alias after truncation: {names}"


def test_generated_index_names_untouched_on_sqlite():
    """SQLite's 128-char budget leaves the derived index names verbatim."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DataFlow(database_url=f"sqlite:///{Path(tmpdir) / 'idx.db'}")
        db.model(_indexed_model(ISSUE_MODEL_NAME))

        table = db._get_table_name(ISSUE_MODEL_NAME)
        names = [
            _INDEX_NAME_RE.match(sql).group(1)
            for sql in db._generate_indexes_sql(ISSUE_MODEL_NAME, "sqlite")
        ]

        assert names == [f"idx_{table}_conversation_id", f"idx_{table}_created_at"]


def test_explicit_index_name_is_not_rewritten():
    """A user-supplied index ``name`` is the user's identifier, untouched."""
    cls = _memory_model(ISSUE_MODEL_NAME)
    cls.__dataflow__ = {
        "indexes": [{"name": "my_own_index", "fields": ["conversation_id"]}]
    }
    db = DataFlow(database_url="postgresql://u:p@localhost:5432/db")
    db.model(cls)

    sql = db._generate_indexes_sql(ISSUE_MODEL_NAME, "postgresql")[0]
    assert _INDEX_NAME_RE.match(sql).group(1) == "my_own_index"


def test_explicitly_empty_index_name_still_fails_loudly():
    """An explicit empty ``name`` MUST NOT be silently replaced.

    Pre-#1971 the derived default came from ``dict.get("name", default)``,
    so an explicitly-supplied ``""`` reached ``validate_identifier`` and
    raised. The fitted-default branch keys on ``is None``, not truthiness, so
    that loud failure is preserved (zero-tolerance Rule 3).
    """
    cls = _memory_model(ISSUE_MODEL_NAME)
    cls.__dataflow__ = {"indexes": [{"name": "", "fields": ["conversation_id"]}]}
    db = DataFlow(database_url="postgresql://u:p@localhost:5432/db")
    db.model(cls)

    with pytest.raises(ValueError, match="must not be empty"):
        db._generate_indexes_sql(ISSUE_MODEL_NAME, "postgresql")


def test_generated_fk_constraint_name_fits_postgres_budget():
    """Derived ``fk_{table}_{col}`` constraint names stay in budget."""
    db = DataFlow(database_url="postgresql://u:p@localhost:5432/db")

    db.model(_memory_model(ISSUE_MODEL_NAME))
    # A belongs_to relationship is what drives the FK / auto-index generators.
    # ``get_relationships`` keys ``_relationships`` by
    # ``_class_name_to_table_name(model_name)`` — store under the SAME key so
    # the lookup finds it (the #1541 regression test's established pattern).
    if not hasattr(db, "_relationships"):
        db._relationships = {}
    db._relationships[db._class_name_to_table_name(ISSUE_MODEL_NAME)] = {
        "conversation": {
            "type": "belongs_to",
            "foreign_key": "conversation_id",
            "target_table": "conversations",
            "target_key": "id",
        }
    }

    fk_sql = db._generate_foreign_key_constraints_sql(ISSUE_MODEL_NAME, "postgresql")
    assert fk_sql, "fixture precondition: a belongs_to relationship yields FK DDL"
    for sql in fk_sql:
        name = _CONSTRAINT_NAME_RE.search(sql).group(1)
        assert len(name) <= POSTGRES_MAX_IDENTIFIER_LENGTH, name

    # The auto-index the same relationship generates is fitted too.
    for sql in db._generate_indexes_sql(ISSUE_MODEL_NAME, "postgresql"):
        name = _INDEX_NAME_RE.match(sql).group(1)
        assert len(name) <= POSTGRES_MAX_IDENTIFIER_LENGTH, name


# ---------------------------------------------------------------------------
# Sibling generators outside core/engine.py (same bug class, swept per
# rules/security.md § Multi-Site Kwarg Plumbing / scanner-surface symmetry)
# ---------------------------------------------------------------------------

# A table name already fitted to PostgreSQL's whole 63-char budget — the state
# every long-model table is in AFTER the primary fix. Any name DERIVED from it
# overflows by construction, which is why each generator below needed its own
# fit call rather than inheriting safety from the table-name fix.
FITTED_TABLE_63 = "multi_db_memory_test_concurrent_database_access_178499_57cbd7b6"

_CREATE_INDEX_NAME_RE = re.compile(
    r'CREATE (?:UNIQUE )?INDEX (?:CONCURRENTLY )?(?:IF NOT EXISTS )?("?[^"`\s]+"?) ON'
)


@pytest.mark.integration
@pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_URL not set; PostgreSQL instance unavailable",
)
@pytest.mark.parametrize(
    "handler_name", ["ColumnOnlyBackupHandler", "TableSnapshotBackupHandler"]
)
def test_column_removal_backup_handlers_fit_backup_table_name(handler_name):
    """The backup HANDLERS themselves must produce an in-budget name.

    ``column_removal_manager`` is PostgreSQL-only and quotes the generated
    ``*_backup_<ts>`` name through the module-level dialect, so an over-budget
    name raised ``InvalidIdentifierError`` and the column-removal migration
    hard-failed for exactly the long-named tables the primary fix produces.

    Calls the real handler against a real PostgreSQL table (Tier 2, no mocks)
    so the assertion covers the HANDLER's call to the fit helper — not merely
    that the helper works in isolation.
    """
    import asyncio

    import asyncpg

    import dataflow.migrations.column_removal_manager as crm

    handler = getattr(crm, handler_name)()
    assert len(FITTED_TABLE_63) == POSTGRES_MAX_IDENTIFIER_LENGTH

    async def _run() -> str:
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            await conn.execute(f'DROP TABLE IF EXISTS "{FITTED_TABLE_63}"')
            await conn.execute(
                f'CREATE TABLE "{FITTED_TABLE_63}" '
                f"(id text primary key, conversation_id text)"
            )
            await conn.execute(
                f"""INSERT INTO "{FITTED_TABLE_63}" VALUES ('r1', 'c1')"""
            )
            info = await handler.create_backup(FITTED_TABLE_63, "conversation_id", conn)
            return info.backup_location
        finally:
            await conn.close()

    backup_table = asyncio.run(_run())

    try:
        assert len(backup_table) <= POSTGRES_MAX_IDENTIFIER_LENGTH, backup_table
        # The server created the table under exactly this name — proof the
        # handler's DDL round-tripped rather than raising or being truncated.
        assert backup_table in _postgres_public_tables(POSTGRES_URL)
    finally:
        _postgres_drop_table(POSTGRES_URL, backup_table)
        _postgres_drop_table(POSTGRES_URL, FITTED_TABLE_63)


def test_recommended_index_names_fit_dialect_budget():
    """The advisory CREATE INDEX statements stay emittable on PostgreSQL.

    Pre-fix, ``_quote_for`` raised on every derived name for a table at the
    budget — so the recommendation engine produced NO advice for precisely the
    tables whose long names it should still be able to index.
    """
    from dataflow.optimization.index_recommendation_engine import (
        IndexRecommendationEngine,
        IndexType,
    )
    from dataflow.optimization.sql_query_optimizer import SQLDialect

    engine = IndexRecommendationEngine(dialect=SQLDialect.POSTGRESQL)
    statements = (
        engine._generate_create_statement(
            FITTED_TABLE_63, ["sender", "created_at"], IndexType.BTREE
        ),
        engine._generate_partial_index_statement(FITTED_TABLE_63, "sender", 0.1),
        engine._generate_covering_index_statement(
            FITTED_TABLE_63, ["sender"], ["content"]
        ),
    )
    names = {_CREATE_INDEX_NAME_RE.search(s).group(1).strip('"') for s in statements}

    assert len(names) == 3, f"recommended index names collided: {names}"
    for name in names:
        assert len(name) <= POSTGRES_MAX_IDENTIFIER_LENGTH, name


def test_recommended_index_names_untouched_on_sqlite():
    """SQLite's 128-char budget leaves the recommended names verbatim."""
    from dataflow.optimization.index_recommendation_engine import (
        IndexRecommendationEngine,
        IndexType,
    )
    from dataflow.optimization.sql_query_optimizer import SQLDialect

    engine = IndexRecommendationEngine(dialect=SQLDialect.SQLITE)
    sql = engine._generate_create_statement(
        FITTED_TABLE_63, ["sender", "created_at"], IndexType.BTREE
    )
    name = _CREATE_INDEX_NAME_RE.search(sql).group(1).strip('"')

    assert name == f"idx_{FITTED_TABLE_63}_sender_created_at"
    assert POSTGRES_MAX_IDENTIFIER_LENGTH < len(name) <= SQLITE_MAX_IDENTIFIER_LENGTH


# ---------------------------------------------------------------------------
# Tier 2 end-to-end: real database, real CRUD through the generated node
# ---------------------------------------------------------------------------


def _postgres_public_tables(url: str) -> set:
    """Read the server's own table catalog, out-of-band from DataFlow."""
    import asyncio

    import asyncpg

    async def _fetch() -> set:
        conn = await asyncpg.connect(url)
        try:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            return {row["tablename"] for row in rows}
        finally:
            await conn.close()

    return asyncio.run(_fetch())


def _postgres_drop_table(url: str, table_name: str) -> None:
    """Tear down the test table; the identifier is dialect-quoted."""
    import asyncio

    import asyncpg

    quoted = DialectManager.get_dialect("postgresql").quote_identifier(table_name)

    async def _drop() -> None:
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(f"DROP TABLE IF EXISTS {quoted}")
        finally:
            await conn.close()

    asyncio.run(_drop())


def _create_and_read(db: DataFlow, model_name: str) -> dict:
    """Run the failing e2e shape: a CreateNode against a long model name."""
    workflow = WorkflowBuilder()
    workflow.add_node(
        f"{model_name}CreateNode",
        "create_user",
        {
            "id": "msg_issue1971",
            "conversation_id": "issue_1971_session",
            "sender": "user",
            "content": "identifier length is dialect-owned",
            "metadata": {},
            "created_at": datetime.now().isoformat(),
        },
    )
    with LocalRuntime() as runtime:
        results, _run_id = runtime.execute(workflow.build())
    return results["create_user"]


@pytest.mark.integration
def test_sqlite_end_to_end_long_model_name():
    """Real SQLite file: the 66-char model round-trips a create."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "issue_1971_sqlite.db"
        db = DataFlow(database_url=f"sqlite:///{db_path}", auto_migrate=True)
        db.model(_memory_model(LONG_MODEL_NAME))

        created = _create_and_read(db, LONG_MODEL_NAME)

        assert created["id"] == "msg_issue1971"
        assert db._get_table_name(LONG_MODEL_NAME) == LONG_TABLE_NAME


@pytest.mark.integration
@pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_URL not set; PostgreSQL instance unavailable",
)
def test_postgres_end_to_end_long_model_name():
    """Real PostgreSQL: the same model creates and queries ONE table.

    Pre-fix this raised ``InvalidIdentifierError: exceeds 63-char PostgreSQL
    limit (len=69)`` at the CreateNode — the literal issue #1971 failure.
    """
    db = DataFlow(database_url=POSTGRES_URL, auto_migrate=True)
    db.model(_memory_model(LONG_MODEL_NAME))
    table_name = db._get_table_name(LONG_MODEL_NAME)
    assert len(table_name) <= POSTGRES_MAX_IDENTIFIER_LENGTH

    try:
        created = _create_and_read(db, LONG_MODEL_NAME)
        assert created["id"] == "msg_issue1971"

        # The server stored the table under exactly the name DataFlow uses —
        # no silent NAMEDATALEN truncation between DDL and DML. Read the
        # catalog out-of-band (the driver, not DataFlow) so the assertion is
        # independent of the code under test.
        assert table_name in _postgres_public_tables(POSTGRES_URL)
    finally:
        _postgres_drop_table(POSTGRES_URL, table_name)


@pytest.mark.integration
@pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_URL not set; PostgreSQL instance unavailable",
)
def test_postgres_server_truncation_aliases_two_models():
    """Pins WHY relaxing validation is not an option.

    Two 69-char names sharing the first 63 characters are the SAME relation to
    the server: the second CREATE raises, and a SELECT through the second name
    returns the first model's rows. This is the silent data-aliasing the fix
    exists to prevent; it runs against the real server so the claim in this
    module's docstring is evidence, not assertion.
    """
    import asyncio

    import asyncpg

    a = "multi_db_memory_issue1971_alias_probe_aaaaaaaaaaaaaaaaaaaaaaaaaaa_A"
    b = "multi_db_memory_issue1971_alias_probe_aaaaaaaaaaaaaaaaaaaaaaaaaaa_B"
    assert len(a) == len(b) > POSTGRES_MAX_IDENTIFIER_LENGTH
    assert a[:POSTGRES_MAX_IDENTIFIER_LENGTH] == b[:POSTGRES_MAX_IDENTIFIER_LENGTH]

    async def _probe() -> tuple:
        conn = await asyncpg.connect(POSTGRES_URL)
        try:
            await conn.execute(f'DROP TABLE IF EXISTS "{a}"')
            await conn.execute(f'DROP TABLE IF EXISTS "{b}"')
            await conn.execute(f'CREATE TABLE "{a}" (id text primary key, marker text)')
            await conn.execute(f"""INSERT INTO "{a}" VALUES ('r1', 'FROM_MODEL_A')""")

            duplicate_raised = False
            try:
                await conn.execute(
                    f'CREATE TABLE "{b}" (id text primary key, marker text)'
                )
            except asyncpg.exceptions.DuplicateTableError:
                duplicate_raised = True

            rows = await conn.fetch(f'SELECT marker FROM "{b}"')
            return duplicate_raised, [r["marker"] for r in rows]
        finally:
            await conn.execute(f'DROP TABLE IF EXISTS "{a}"')
            await conn.execute(f'DROP TABLE IF EXISTS "{b}"')
            await conn.close()

    duplicate_raised, markers = asyncio.run(_probe())

    assert duplicate_raised, "server did not treat the two names as one relation"
    assert markers == ["FROM_MODEL_A"], (
        "SELECT through name B did not return model A's rows — the aliasing "
        "premise of this fix no longer holds on this server version"
    )

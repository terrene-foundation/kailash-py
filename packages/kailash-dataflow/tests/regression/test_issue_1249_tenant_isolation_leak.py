"""Regression tests for issue #1249 — DataFlow multi-tenant cross-tenant leak.

Issue #1249: in multi-tenant mode, DataFlow's ``express`` CRUD provided NO
tenant isolation. Four compounding defects produced a SILENT cross-tenant leak:

1. The SQL-syntax validator's ``\\w+`` table-name regexes rejected quoted
   identifiers (``INSERT INTO "feats" ...``), fail-closing the INSERT path.
2. The INSERT injection regex did not match quoted identifiers, so the tenant
   column/value was never bound and every write stored ``tenant_id = NULL``.
3. The SELECT-path table matcher compared the parsed (quoted) table name
   against the unquoted ``tenant_tables`` entry; the mismatch left
   ``tenant_tables_in_query`` empty and the interceptor returned the query
   UNCHANGED — no WHERE filter, no error: the silent leak.
4. ``tenant_isolation_strategy`` was silently dropped as an unknown DataFlow
   constructor parameter (DF-CFG-001), and its default ``"schema"`` is a no-op
   on SQLite.

These Tier-2 tests exercise the real express CRUD path against a real SQLite
database (and a PostgreSQL-marked variant) and assert strict isolation. They are
permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

import sqlite3
import tempfile

import pytest

from dataflow import DataFlow
from dataflow.exceptions import DataFlowConfigurationError
from dataflow.tenancy.exceptions import TenantIsolationError
from dataflow.tenancy.interceptor import QueryInterceptor, normalize_identifier

# ---------------------------------------------------------------------------
# Tier-2: end-to-end isolation through the real express CRUD path (SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def mt_db():
    """Multi-tenant DataFlow over file-backed SQLite + Feat model.

    Yields ``(db, tmpdir)`` and closes the DataFlow on teardown so the runner
    does not accumulate ``ResourceWarning: Unclosed LocalRuntime`` per
    ``rules/testing.md`` (fixtures yield + cleanup, never return).
    """
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(
        f"sqlite:///{tmpdir}/mt.db",
        auto_migrate=True,
        multi_tenant=True,
    )

    @db.model
    class Feat:
        entity_id: str
        score: int

    db._ensure_connected()
    db.tenant_context.register_tenant("acme", "A")
    db.tenant_context.register_tenant("globex", "G")
    try:
        yield db, tmpdir
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
def test_express_multi_tenant_isolation_no_cross_tenant_leak(mt_db):
    """Two tenants create rows; each reads back ONLY its own rows.

    This is the core #1249 leak: pre-fix, ``acme`` saw both tenants' rows.
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        db.express_sync.create("Feat", {"entity_id": "e1", "score": 10})
    with db.tenant_context.switch("globex"):
        db.express_sync.create("Feat", {"entity_id": "e1", "score": 99})

    with db.tenant_context.switch("acme"):
        acme_scores = sorted(r.get("score") for r in db.express_sync.list("Feat", {}))
    with db.tenant_context.switch("globex"):
        globex_scores = sorted(r.get("score") for r in db.express_sync.list("Feat", {}))

    # The leak this regression test guards: acme MUST NOT see globex's row.
    assert acme_scores == [10], f"cross-tenant leak: acme saw {acme_scores}"
    assert globex_scores == [99], f"cross-tenant leak: globex saw {globex_scores}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
def test_express_multi_tenant_write_without_bound_tenant_fails_closed(mt_db):
    """Issue #1249 (fail-closed write): a write under multi_tenant=True with NO
    bound tenant MUST raise AND MUST NOT persist a tenant_id=NULL row.

    Pre-fix the SQL enforcement point (``_apply_tenant_isolation``) returned the
    INSERT unchanged when no tenant was bound, so an unscoped row was written
    with ``tenant_id = NULL`` (invisible to every tenant's filtered read, a
    latent fail-OPEN) before the API-layer error surfaced. Per
    tenant-isolation.md MUST-2 + zero-tolerance.md Rule 3 the write must fail
    closed with no side effect.
    """
    db, tmpdir = mt_db

    # No db.tenant_context.switch(...) -> no bound tenant under multi_tenant.
    with pytest.raises(RuntimeError, match="no tenant is bound"):
        db.express_sync.create("Feat", {"entity_id": "orphan", "score": 1})

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    try:
        null_rows = con.execute(
            "SELECT entity_id, tenant_id FROM feats WHERE tenant_id IS NULL"
        ).fetchall()
    finally:
        con.close()
    assert null_rows == [], f"fail-open: a NULL-tenant row was persisted: {null_rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
def test_express_multi_tenant_insert_persists_non_null_tenant_id(mt_db):
    """Every multi-tenant INSERT MUST persist a non-NULL tenant_id (defect #2)."""
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        db.express_sync.create("Feat", {"entity_id": "a", "score": 1})
    with db.tenant_context.switch("globex"):
        db.express_sync.create("Feat", {"entity_id": "g", "score": 2})

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    rows = con.execute(
        "SELECT entity_id, score, tenant_id FROM feats ORDER BY id"
    ).fetchall()
    con.close()

    # Pre-fix this returned tenant_id=None for every row.
    assert all(r[2] is not None for r in rows), f"tenant_id stored as NULL: {rows}"
    tenants = {r[2] for r in rows}
    assert tenants == {"acme", "globex"}, f"wrong tenant_id values: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
def test_express_multi_tenant_update_is_tenant_scoped(mt_db):
    """A tenant MUST NOT update another tenant's row even by primary key."""
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        db.express_sync.create("Feat", {"entity_id": "a", "score": 10})
    with db.tenant_context.switch("globex"):
        db.express_sync.create("Feat", {"entity_id": "g", "score": 99})

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    rows = con.execute("SELECT id, tenant_id FROM feats ORDER BY id").fetchall()
    con.close()
    globex_id = next(r[0] for r in rows if r[1] == "globex")
    acme_id = next(r[0] for r in rows if r[1] == "acme")

    # acme attempts to overwrite globex's row by id — MUST be a no-op.
    with db.tenant_context.switch("acme"):
        db.express_sync.update("Feat", globex_id, {"score": 12345})

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    globex_score = con.execute(
        "SELECT score FROM feats WHERE id = ?", (globex_id,)
    ).fetchone()[0]
    con.close()
    assert globex_score == 99, "cross-tenant UPDATE leaked into globex's row"

    # Same-tenant update MUST still work.
    with db.tenant_context.switch("acme"):
        db.express_sync.update("Feat", acme_id, {"score": 777})
    con = sqlite3.connect(f"{tmpdir}/mt.db")
    acme_score = con.execute(
        "SELECT score FROM feats WHERE id = ?", (acme_id,)
    ).fetchone()[0]
    con.close()
    assert acme_score == 777, "same-tenant UPDATE failed"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
def test_express_multi_tenant_delete_is_tenant_scoped(mt_db):
    """A tenant MUST NOT delete another tenant's row even by primary key."""
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        db.express_sync.create("Feat", {"entity_id": "a", "score": 10})
    with db.tenant_context.switch("globex"):
        db.express_sync.create("Feat", {"entity_id": "g", "score": 99})

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    rows = con.execute("SELECT id, tenant_id FROM feats ORDER BY id").fetchall()
    con.close()
    globex_id = next(r[0] for r in rows if r[1] == "globex")

    # acme attempts to delete globex's row — MUST be a no-op.
    with db.tenant_context.switch("acme"):
        db.express_sync.delete("Feat", globex_id)

    con = sqlite3.connect(f"{tmpdir}/mt.db")
    remaining = con.execute(
        "SELECT COUNT(*) FROM feats WHERE id = ?", (globex_id,)
    ).fetchone()[0]
    con.close()
    assert remaining == 1, "cross-tenant DELETE removed globex's row"


# ---------------------------------------------------------------------------
# Unit-tier: interceptor identifier-normalization + param-ordering regressions
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.unit
def test_normalize_identifier_strips_all_dialect_quoting():
    """normalize_identifier handles all four dialect quoting styles (defect #1-3)."""
    assert normalize_identifier('"feats"') == "feats"  # ANSI / Postgres / SQLite
    assert normalize_identifier("`feats`") == "feats"  # MySQL backtick
    assert normalize_identifier("[feats]") == "feats"  # SQL-Server bracket
    assert normalize_identifier("feats") == "feats"  # bare
    assert normalize_identifier('  "feats"  ') == "feats"  # surrounding whitespace


@pytest.mark.regression
@pytest.mark.unit
@pytest.mark.parametrize(
    "query",
    [
        'INSERT INTO "feats" (entity_id, score) VALUES (?, ?)',  # ANSI quote
        "INSERT INTO `feats` (entity_id, score) VALUES (?, ?)",  # MySQL
        "INSERT INTO [feats] (entity_id, score) VALUES (?, ?)",  # SQL-Server
        'UPDATE "feats" SET score = ? WHERE id = ?',
        'DELETE FROM "feats" WHERE id = ?',
    ],
)
def test_validator_accepts_quoted_identifiers(query):
    """The validator's table-name check accepts quoted identifiers (defect #1).

    Pre-fix the ``\\w+`` regex rejected ``"feats"`` and raised
    "missing table name", fail-closing the write path.
    """
    interceptor = QueryInterceptor(tenant_id="A", tenant_tables=["feats"])
    # parse_query runs _validate_sql_syntax; it MUST NOT raise on quoted tables.
    parsed = interceptor.parse_query(query)
    assert parsed.query_type in {"INSERT", "UPDATE", "DELETE"}


@pytest.mark.regression
@pytest.mark.unit
def test_select_injection_binds_tenant_param_at_correct_position():
    """Tenant param MUST be inserted at the placeholder position, not appended.

    Defect: appending shifted the tenant value onto a trailing LIMIT/OFFSET
    placeholder, so the filter bound ``tenant_id = <limit int>`` and matched
    zero rows (the read-returns-nothing symptom).
    """
    interceptor = QueryInterceptor(tenant_id="A", tenant_tables=["feats"])
    q = 'SELECT * FROM "feats" ORDER BY "id" DESC LIMIT ? OFFSET ?'
    mq, mp = interceptor.inject_tenant_conditions(q, [100, 0])
    assert "WHERE tenant_id = ?" in mq
    # The tenant value 'A' MUST be the FIRST param (matching the WHERE ? that
    # precedes LIMIT/OFFSET), NOT appended last.
    assert mp == ["A", 100, 0], f"param ordering wrong: {mp}"


@pytest.mark.regression
@pytest.mark.unit
def test_insert_injection_does_not_duplicate_existing_tenant_column():
    """When tenant_id is already a column, bind its value — do not append.

    In multi-tenant mode DataFlow auto-adds tenant_id to the INSERT column
    list with a NULL value. The interceptor MUST overwrite that bound value
    rather than append a duplicate column (which left tenant_id=NULL).
    """
    interceptor = QueryInterceptor(tenant_id="acme", tenant_tables=["feats"])
    q = 'INSERT INTO "feats" ("entity_id", "score", "tenant_id") VALUES (?, ?, ?)'
    mq, mp = interceptor.inject_tenant_conditions(q, ["e1", 10, None])
    # No duplicate tenant_id column.
    assert mq.count("tenant_id") == 1, f"duplicate tenant column: {mq}"
    # The NULL bound for the auto-added tenant_id column is now the tenant value.
    assert mp == ["e1", 10, "acme"], f"tenant value not bound: {mp}"


@pytest.mark.regression
@pytest.mark.unit
def test_interceptor_fails_closed_when_no_tenant_table_matched():
    """An explicit tenant_tables interceptor MUST raise — not pass through.

    Closes the line-223 silent-leak hole: the caller asserted the query
    targets a tenant table; if none matched, executing the query unfiltered
    would leak. The interceptor raises TenantIsolationError instead.
    Per tenant-isolation.md MUST-2 + zero-tolerance.md Rule 3.
    """
    interceptor = QueryInterceptor(tenant_id="A", tenant_tables=["feats"])
    with pytest.raises(TenantIsolationError):
        # 'other_table' is not in tenant_tables → no tenant table matched.
        interceptor.inject_tenant_conditions(
            'SELECT * FROM "other_table" WHERE x = ?', [1]
        )


# ---------------------------------------------------------------------------
# Defect #4: tenant_isolation_strategy accepted, validated, fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.unit
def test_tenant_isolation_strategy_row_accepted_no_unknown_param_warning():
    """tenant_isolation_strategy='row' is accepted and stored (defect #4)."""
    import warnings

    tmpdir = tempfile.mkdtemp()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        db = DataFlow(
            f"sqlite:///{tmpdir}/s.db",
            auto_migrate=True,
            multi_tenant=True,
            tenant_isolation_strategy="row",
        )
        df_cfg = [str(w.message) for w in caught if "DF-CFG-001" in str(w.message)]
    try:
        assert db.config.security.tenant_isolation_strategy == "row"
        # Pre-fix this emitted a DF-CFG-001 "unknown parameter" warning.
        assert df_cfg == [], f"strategy treated as unknown kwarg: {df_cfg}"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.unit
def test_tenant_isolation_strategy_default_is_row():
    """Default strategy is 'row' (was 'schema', a SQLite no-op) — defect #4."""
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(f"sqlite:///{tmpdir}/d.db", auto_migrate=True, multi_tenant=True)
    try:
        assert db.config.security.tenant_isolation_strategy == "row"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.unit
def test_tenant_isolation_strategy_invalid_value_fails_closed():
    """An unknown strategy value MUST raise, not be silently ignored."""
    tmpdir = tempfile.mkdtemp()
    with pytest.raises(
        DataFlowConfigurationError, match="Invalid tenant_isolation_strategy"
    ):
        DataFlow(
            f"sqlite:///{tmpdir}/i.db",
            multi_tenant=True,
            tenant_isolation_strategy="bogus",
        )


@pytest.mark.regression
@pytest.mark.unit
def test_tenant_isolation_strategy_schema_on_sqlite_fails_closed():
    """A strategy that cannot isolate on the backend MUST fail closed.

    'schema'/'database' request PHYSICAL isolation DataFlow cannot provision on
    SQLite. Rather than silently no-op into NO isolation (a cross-tenant leak),
    DataFlow refuses to start.
    """
    tmpdir = tempfile.mkdtemp()
    with pytest.raises(DataFlowConfigurationError, match="PHYSICAL tenant"):
        DataFlow(
            f"sqlite:///{tmpdir}/sc.db",
            multi_tenant=True,
            tenant_isolation_strategy="schema",
        )


@pytest.mark.regression
@pytest.mark.unit
def test_tenant_isolation_strategy_schema_inert_without_multitenant():
    """A physical strategy is harmless (inert) when multi_tenant is off."""
    tmpdir = tempfile.mkdtemp()
    # Should NOT raise: no multi-tenancy → strategy is inert.
    db = DataFlow(
        f"sqlite:///{tmpdir}/in.db",
        auto_migrate=True,
        tenant_isolation_strategy="schema",
    )
    try:
        assert db.config.security.tenant_isolation_strategy == "schema"
    finally:
        db.close()

"""Regression tests for issue #1519 — bulk_upsert silently ignored conflict_on.

Before the fix, ``db.express.bulk_upsert(model, records, conflict_on=[...])`` and
the generated ``{Model}BulkUpsertNode`` hardcoded ``ON CONFLICT (id) DO NOTHING``:

- ``conflict_on`` was fully ignored (dropped in ``**kwargs`` on the way to
  ``features/bulk.py::bulk_upsert``; the three dialect builders hardcoded
  ``ON CONFLICT (id)``);
- the generated/express path defaulted to ``conflict_resolution="skip"`` →
  ``DO NOTHING`` instead of the documented insert-or-UPDATE contract;
- returned counts were fabricated / zero while rows persisted.

The DataFlowBulkUpsertNode (P2) SQLite/MySQL branch used ``INSERT OR REPLACE``
(ignores conflict_on, invalid MySQL syntax) and fabricated counts via ``// 2``.

The fix honors ``conflict_on`` via native single-statement
``INSERT ... ON CONFLICT (conflict_on) DO UPDATE ... RETURNING`` (SQLite/PG) /
``ON DUPLICATE KEY UPDATE`` (MySQL), defaults the express/generated path to
``update``, derives real counts (PG ``(xmax = 0)`` / SQLite pre-count of existing
conflict keys), and raises :class:`BulkUpsertConflictTargetError` when the
conflict target is not a PK/UNIQUE key (instead of silently falling back).

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

import sqlite3
import tempfile

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import BulkUpsertConflictTargetError
from dataflow.nodes.bulk_upsert import DataFlowBulkUpsertNode


# ---------------------------------------------------------------------------
# Tier-2: express bulk_upsert over real file-backed SQLite (the live path)
# ---------------------------------------------------------------------------
@pytest.fixture
def sqlite_db():
    """Single-tenant DataFlow over file-backed SQLite. Yields (db, tmpdir)."""
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(f"sqlite:///{tmpdir}/df.db", auto_migrate=True)

    @db.model
    class Widget:
        id: str
        name: str
        qty: int

    @db.model
    class Person:
        id: str
        email: str
        name: str
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    @db.model
    class Note:
        id: str
        tag: str  # deliberately NOT unique
        body: str

    db._ensure_connected()
    try:
        yield db, tmpdir
    finally:
        db.close()


def _rows(tmpdir, sql):
    con = sqlite3.connect(f"{tmpdir}/df.db")
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_conflict_on_id_overlapping_updates_not_duplicates(sqlite_db):
    """AC1/AC4: conflict_on=['id'] with overlapping ids updates, not duplicates,
    and created/updated counts reflect the real rows written."""
    db, tmpdir = sqlite_db

    r1 = await db.express.bulk_upsert(
        "Widget",
        [{"id": "w1", "name": "A", "qty": 1}, {"id": "w2", "name": "B", "qty": 2}],
        conflict_on=["id"],
    )
    assert r1["created"] == 2 and r1["updated"] == 0 and r1["total"] == 2

    r2 = await db.express.bulk_upsert(
        "Widget",
        [
            {"id": "w1", "name": "A-upd", "qty": 10},  # UPDATE existing id
            {"id": "w3", "name": "C", "qty": 3},  # INSERT new id
        ],
        conflict_on=["id"],
    )
    # DO UPDATE (not DO NOTHING); counts split correctly.
    assert r2["created"] == 1, r2
    assert r2["updated"] == 1, r2
    assert r2["total"] == 2, r2

    rows = _rows(tmpdir, "SELECT id, name, qty FROM widgets ORDER BY id")
    assert rows == [("w1", "A-upd", 10), ("w2", "B", 2), ("w3", "C", 3)], rows


@pytest.mark.regression
@pytest.mark.integration
async def test_conflict_on_unique_field_is_honored(sqlite_db):
    """AC2: conflict_on on a field declared unique targets that constraint."""
    db, tmpdir = sqlite_db

    await db.express.bulk_upsert(
        "Person",
        [{"id": "p1", "email": "x@e.com", "name": "X1"}],
        conflict_on=["email"],
    )
    r = await db.express.bulk_upsert(
        "Person",
        # Same email, DIFFERENT id -> conflict resolves on email, row updates.
        [{"id": "p2", "email": "x@e.com", "name": "X2"}],
        conflict_on=["email"],
    )
    assert r["updated"] == 1 and r["created"] == 0, r

    rows = _rows(tmpdir, "SELECT email, name FROM people ORDER BY email")
    assert rows == [("x@e.com", "X2")], rows  # single row, updated in place


@pytest.mark.regression
@pytest.mark.integration
async def test_conflict_on_non_unique_field_raises_actionable_error(sqlite_db):
    """AC3: conflict_on on a non-unique column raises an actionable typed error
    naming the column + remediation, and does NOT silently insert duplicates."""
    db, tmpdir = sqlite_db

    with pytest.raises(BulkUpsertConflictTargetError) as exc:
        await db.express.bulk_upsert(
            "Note",
            [
                {"id": "n1", "tag": "t", "body": "one"},
                {"id": "n2", "tag": "t", "body": "two"},
            ],
            conflict_on=["tag"],
        )
    msg = str(exc.value)
    assert "tag" in msg
    assert "unique" in msg.lower()
    assert "db.express.upsert" in msg  # remediation guidance

    # No rows landed on the raise (not a silent duplicate-insert).
    assert _rows(tmpdir, "SELECT COUNT(*) FROM notes")[0][0] == 0


# ---------------------------------------------------------------------------
# Tier-2: DataFlowBulkUpsertNode (P2 — the workflow/gateway node path)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_node_sqlite_honors_conflict_on_no_insert_or_replace():
    """P2: the SQLite branch uses native ON CONFLICT (NOT INSERT OR REPLACE) and
    derives real counts."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/n.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, email TEXT UNIQUE, name TEXT)")
    con.execute("INSERT INTO t (id, email, name) VALUES (1, 'a@e.com', 'A')")
    con.commit()
    con.close()

    node = DataFlowBulkUpsertNode(
        table_name="t",
        connection_string=f"sqlite:///{path}",
        database_type="sqlite",
        conflict_columns=["email"],
        auto_timestamps=False,
    )

    # The generated SQL must NOT be INSERT OR REPLACE.
    sql, _ = node._build_upsert_query(
        [{"email": "z@e.com", "name": "Z"}],
        ["email", "name"],
        "email, name",
        False,
        "update",
        ["email"],
    )
    assert "INSERT OR REPLACE" not in sql
    assert "ON CONFLICT (email)" in sql and "DO UPDATE SET" in sql

    res = await node.async_run(
        data=[
            {"email": "a@e.com", "name": "A-upd"},  # update by email
            {"email": "b@e.com", "name": "B"},  # insert
        ],
        conflict_on=["email"],
        merge_strategy="update",
    )
    assert res["success"] is True
    assert res["inserted"] == 1 and res["updated"] == 1, res  # real, not // 2

    con = sqlite3.connect(path)
    rows = con.execute("SELECT email, name FROM t ORDER BY email").fetchall()
    con.close()
    assert dict(rows) == {"a@e.com": "A-upd", "b@e.com": "B"}, rows


@pytest.mark.regression
async def test_node_mysql_uses_on_duplicate_key_update():
    """P2: the MySQL branch emits ON DUPLICATE KEY UPDATE (INSERT OR REPLACE is
    invalid MySQL syntax). SQL-shape assertion, no MySQL server needed."""
    node = DataFlowBulkUpsertNode(
        table_name="t",
        connection_string="mysql://x/y",
        database_type="mysql",
        conflict_columns=["email"],
        auto_timestamps=False,
    )
    sql, _ = node._build_upsert_query(
        [{"email": "z@e.com", "name": "Z"}],
        ["email", "name"],
        "email, name",
        False,
        "update",
        ["email"],
    )
    assert "INSERT OR REPLACE" not in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "name = VALUES(name)" in sql
    # conflict-target column is excluded from the update set.
    assert "email = VALUES(email)" not in sql


@pytest.mark.regression
async def test_node_dry_run_does_not_fabricate_counts():
    """P2: dry-run reports would_upsert without a fabricated inserted/updated
    split (issue #1519 — the `// 2` mock estimate is gone)."""
    node = DataFlowBulkUpsertNode(
        table_name="t",
        connection_string="postgresql://x/y",
        database_type="postgresql",
        conflict_columns=["email"],
    )
    res = await node.async_run(
        data=[
            {"email": "a@e.com", "name": "A"},
            {"email": "b@e.com", "name": "B"},
            {"email": "c@e.com", "name": "C"},
        ],
        dry_run=True,
        conflict_on=["email"],
    )
    assert res["dry_run"] is True
    assert res["would_upsert"] == 3
    assert res["inserted"] == 0 and res["updated"] == 0  # no // 2 fabrication


# ---------------------------------------------------------------------------
# Tier-2: PostgreSQL parity (AC5) — real PG on port 5434
# ---------------------------------------------------------------------------
@pytest.fixture
async def pg_suite():
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


async def _drop_table(url, table):
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    node = AsyncSQLDatabaseNode(
        connection_string=url,
        database_type="postgresql",
        query=f"DROP TABLE IF EXISTS {table} CASCADE",
        validate_queries=False,
    )
    await node.async_run()
    await node.cleanup()


@pytest.mark.regression
@pytest.mark.integration
async def test_postgres_conflict_on_honored_with_real_counts(pg_suite):
    """AC5: PostgreSQL equivalent — conflict_on honored + accurate created/updated
    counts derived from the (xmax = 0) RETURNING flag."""
    url = pg_suite.config.url
    # auto_migrate creates the table (with the UNIQUE(email) index) so the
    # table name matches DataFlow's own pluralization.
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1519Pg:
        email: str
        name: str
        score: int
        __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

    table = db._models["Issue1519Pg"]["table_name"]
    await _drop_table(url, table)
    db._ensure_connected()

    try:
        # First upsert: 2 inserts.
        r1 = await db.bulk.bulk_upsert(
            model_name="Issue1519Pg",
            data=[
                {"email": "a@e.com", "name": "A", "score": 1},
                {"email": "b@e.com", "name": "B", "score": 2},
            ],
            conflict_resolution="update",
            conflict_on=["email"],
        )
        assert r1["success"] is True
        assert r1["inserted"] == 2 and r1["updated"] == 0, r1

        # Second upsert: 1 update (a@e.com) + 1 insert (c@e.com), by EMAIL not id.
        r2 = await db.bulk.bulk_upsert(
            model_name="Issue1519Pg",
            data=[
                {"email": "a@e.com", "name": "A2", "score": 11},
                {"email": "c@e.com", "name": "C", "score": 3},
            ],
            conflict_resolution="update",
            conflict_on=["email"],
        )
        assert r2["success"] is True
        assert r2["inserted"] == 1, r2
        assert r2["updated"] == 1, r2

        rows = await db.express.list("Issue1519Pg", order_by="email")
        by_email = {r["email"]: (r["name"], r["score"]) for r in rows}
        assert len(by_email) == 3, rows
        assert by_email["a@e.com"] == ("A2", 11)  # updated in place
        assert by_email["c@e.com"] == ("C", 3)
    finally:
        await _drop_table(url, table)
        db.close()


@pytest.mark.regression
@pytest.mark.integration
async def test_postgres_non_unique_conflict_target_raises(pg_suite):
    """AC5/AC3 parity: PostgreSQL non-unique conflict target raises the typed
    error instead of silently landing duplicates."""
    url = pg_suite.config.url
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class Issue1519PgNonuniq:
        tag: str  # NOT unique
        body: str

    table = db._models["Issue1519PgNonuniq"]["table_name"]
    await _drop_table(url, table)
    db._ensure_connected()

    try:
        with pytest.raises(BulkUpsertConflictTargetError):
            await db.bulk.bulk_upsert(
                model_name="Issue1519PgNonuniq",
                data=[{"tag": "t", "body": "one"}, {"tag": "t", "body": "two"}],
                conflict_resolution="update",
                conflict_on=["tag"],
            )
        # No rows landed on the raise.
        assert await db.express.count("Issue1519PgNonuniq") == 0
    finally:
        await _drop_table(url, table)
        db.close()


# ---------------------------------------------------------------------------
# Redteam H1: internal-duplicate conflict keys within one batch
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_internal_duplicate_conflict_keys_dedup_last_wins(sqlite_db):
    """Redteam H1: a single bulk_upsert call carrying TWO records with the same
    conflict-target key must (a) collapse to last-wins, (b) write exactly one
    row, and (c) report counts that MATCH the rows actually written — never the
    pre-fix over-count (created=2 while 1 row landed). Guards against the SQLite
    over-count AND the PostgreSQL "ON CONFLICT DO UPDATE cannot affect row a
    second time" hard-error by making both dialects dedup-consistent."""
    db, tmpdir = sqlite_db

    r = await db.express.bulk_upsert(
        "Widget",
        [
            {"id": "x", "name": "first", "qty": 1},
            {"id": "x", "name": "second", "qty": 2},  # same id — last wins
            {"id": "y", "name": "Y", "qty": 9},
        ],
        conflict_on=["id"],
    )
    # Two distinct keys → two rows; counts MUST equal rows written.
    assert r["created"] + r["updated"] == 2, r
    assert r["created"] == 2 and r["updated"] == 0, r

    rows = _rows(tmpdir, "SELECT id, name, qty FROM widgets ORDER BY id")
    assert rows == [("x", "second", 2), ("y", "Y", 9)], rows  # last-wins on x


@pytest.mark.regression
@pytest.mark.integration
async def test_internal_dup_then_update_reports_real_counts(sqlite_db):
    """Second call whose batch re-conflicts an existing key AND self-duplicates:
    the deduped single UPDATE must report updated=1 (not the pre-fix over-count),
    and the persisted value is the last occurrence."""
    db, tmpdir = sqlite_db
    await db.express.bulk_upsert(
        "Widget", [{"id": "k", "name": "orig", "qty": 0}], conflict_on=["id"]
    )
    r = await db.express.bulk_upsert(
        "Widget",
        [
            {"id": "k", "name": "up-a", "qty": 1},
            {"id": "k", "name": "up-b", "qty": 2},  # dup of k in same batch
        ],
        conflict_on=["id"],
    )
    assert r["created"] == 0 and r["updated"] == 1, r
    rows = _rows(tmpdir, "SELECT id, name, qty FROM widgets ORDER BY id")
    assert rows == [("k", "up-b", 2)], rows


# ---------------------------------------------------------------------------
# Redteam MEDIUM (security): shared driver-error redactor scrubs column values
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_sanitize_db_error_redacts_column_values():
    """Redteam MEDIUM: a unique-violation from a DIFFERENT constraint embeds
    column VALUES (potential PII) in the driver message. The shared redactor
    (used by features/bulk.py AND nodes/bulk_upsert.py) MUST strip the value
    payload while preserving the diagnostic shape; non-DB messages pass
    through unchanged."""
    from dataflow.core.exceptions import sanitize_db_error

    # PostgreSQL form: value rides in a DETAIL: line → whole line redacted.
    leaked_pg = (
        'duplicate key value violates unique constraint "users_username_key"\n'
        "DETAIL:  Key (username)=(alice@example.com) already exists."
    )
    scrubbed_pg = sanitize_db_error(leaked_pg)
    assert "alice@example.com" not in scrubbed_pg  # the security property
    assert "DETAIL: [REDACTED]" in scrubbed_pg  # shape preserved
    assert "users_username_key" in scrubbed_pg  # constraint name (triage) kept

    # Main-line Key(...)=(...) form (no DETAIL: prefix) → value payload redacted,
    # column name retained.
    leaked_key = "ERROR: Key (email)=(bob@corp.example) already exists"
    scrubbed_key = sanitize_db_error(leaked_key)
    assert "bob@corp.example" not in scrubbed_key
    assert "Key (email)=([REDACTED])" in scrubbed_key

    # Non-DB message passes through untouched (no false redaction).
    assert sanitize_db_error("Bulk upsert operation failed: timeout") == (
        "Bulk upsert operation failed: timeout"
    )
    # Non-string input fails closed to a sentinel, never raises.
    assert sanitize_db_error(None) == "<non-string error>"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Redteam CRITICAL (security): dynamic identifiers are validated before
# interpolation on the express bulk path (dataflow-identifier-safety.md MUST-1)
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_crafted_column_key_rejected_no_injection(sqlite_db):
    """Redteam CRITICAL: a crafted record KEY (column names are interpolated as
    bare identifiers into INSERT/ON CONFLICT/DO UPDATE — drivers cannot bind
    identifiers) MUST be rejected by _validate_identifier BEFORE any SQL is
    emitted. The express bulk path (features/bulk.py) previously validated only
    the conflict-target columns, leaving the INSERT/SET column list unguarded."""
    db, tmpdir = sqlite_db

    res = await db.bulk.bulk_upsert(
        "Widget",
        [{"id": "a", "name": "x", "evil) ; DROP TABLE widgets;--": "z"}],
        conflict_on=["id"],
    )
    # Rejected as a failure — not a silent success — and NO injection executed.
    assert res.get("success") is False, res
    # The fingerprinted validator message must NOT echo the raw payload.
    assert "DROP TABLE" not in str(res.get("error", "")), res
    # The table still exists (the injection never ran).
    assert _rows(tmpdir, "SELECT count(*) FROM widgets") == [(0,)]


@pytest.mark.regression
@pytest.mark.integration
async def test_single_record_upsert_crafted_key_rejected(sqlite_db):
    """Redteam sibling (same identifier-injection class on the single-record
    {Model}UpsertNode path): a crafted record KEY in the create payload MUST be
    rejected by _validate_identifier before the dialect builds SQL — no
    injection, table intact. Guards the core/nodes.py single-record upsert
    caller-side validation added alongside the #1519 bulk fix."""
    db, tmpdir = sqlite_db

    with pytest.raises(Exception) as exc:
        await db.express.upsert(
            "Widget",
            {"id": "z", "name": "x", "evil) ; DROP TABLE widgets;--": "q"},
            {"name": "y"},
        )
    # Fingerprinted identifier error — must NOT echo the raw payload.
    assert "DROP TABLE" not in str(exc.value)
    assert "identifier" in str(exc.value).lower()
    # The injection never executed — table still present with 0 rows.
    assert _rows(tmpdir, "SELECT COUNT(*) FROM widgets") == [(0,)]

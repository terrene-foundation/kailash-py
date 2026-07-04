"""Regression for issue #1550 — eager batch-DDL executor leaks raw driver
error text (``DETAIL: Key(col)=(value)``) into logs + ``DDLFailedError``.

Follow-up to #1548, which closed the async *lazy* table-creation path
(``ensure_table_exists`` → ``_execute_*_migration_system_async``) by routing
every surfaced error through ``sanitize_db_error``. The sibling **eager**
batch-DDL executors were a different, pre-existing code path the #1548 fix
never touched:

* ``_execute_ddl``            (sync eager batch)      → ``engine.ddl_failed``
* ``_execute_ddl_async``      (async eager batch)     → ``engine.ddl_async_failed``
* ``create_tables_sync``      (sync per-statement)    → ``engine.sync_ddl_failed``
* ``create_table_for_model``  (sync single-model)     → ``engine.sync_ddl_failed_for_model``
* the ``_create_tables_batch`` fallback               → ``engine.batch_ddl_failed``

Each rendered the raw driver error at its DIRECT per-statement log site AND at
its DIRECT first-access ``DDLFailedError`` raise. A ``CREATE UNIQUE INDEX`` on a
column holding duplicate values makes PostgreSQL emit
``DETAIL: Key (col)=(value) is duplicated``, whose ``(value)`` is a real column
value (potential PII). Log aggregators typically have broader access than the
DB (``observability.md`` Rule 8; ``security.md`` § no-secrets-in-logs), so the
raw value MUST NOT reach the log line or the raised exception message.

The fix routes every direct render through ``self._sanitize_db_error(...)`` and
wraps the direct ``DDLFailedError`` raises' ``original_error`` in
``RuntimeError(sanitized_text)`` — mirroring the #1548 lazy-path first-access
raise at ``engine.py`` ``ensure_table_exists``. The raw exception is preserved
as ``__cause__`` (traceback-only, not user-facing) via ``from error``.

Three tiers:

* **Part A (Tier-2, requires_postgres):** real PostgreSQL, a genuine
  duplicate-value ``CREATE UNIQUE INDEX`` failure driven through the sync
  ``_execute_ddl`` and async ``_execute_ddl_async`` eager batch executors — the
  logged ``error`` field MUST NOT contain the duplicated value. This is the
  issue's acceptance-criterion test; the database is never mocked.
* **Part B (Tier-1, deterministic):** the ``_sanitize_db_error`` call is
  load-bearing — a crafted value-bearing driver error (injected at the sole
  permitted seam, the ``SyncDDLExecutor`` batch result) MUST render as
  ``[REDACTED]`` in BOTH the log field AND the ``DDLFailedError`` message,
  proving the redaction ran rather than passing vacuously because a particular
  driver happened to omit the value.
* **Part C (structural invariant):** no eager-batch DDL-failure site renders
  raw driver text — a source-level guard that fails loudly if a future edit
  re-inlines a raw ``err_text`` / ``original_error=error`` render.
"""

import logging
import uuid
from pathlib import Path

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import DDLFailedError

# Distinctive so its ABSENCE from any log/exception surface is unambiguous.
SECRET_VALUE = "p11-secret-value-DO-NOT-LEAK-7f3a9c"

_ENGINE_LOGGER = "dataflow.core.engine"


def _rendered(records) -> str:
    """Flatten captured log records into one searchable string, including the
    structured ``extra`` fields (where the DDL error text lives)."""
    parts = []
    for r in records:
        parts.append(r.getMessage())
        for attr in ("error", "error_message", "statement"):
            val = getattr(r, attr, None)
            if isinstance(val, str):
                parts.append(val)
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Part A — Tier-2, real PostgreSQL (acceptance criterion)
# --------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra)."""
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


async def _seed_duplicate_rows(test_suite, table: str) -> None:
    """Create ``table`` with two rows sharing ``SECRET_VALUE`` so a subsequent
    ``CREATE UNIQUE INDEX`` genuinely fails with a value-bearing DETAIL."""
    async with test_suite.get_connection() as conn:
        await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        await conn.execute(f'CREATE TABLE "{table}" (val TEXT)')
        await conn.execute(
            f'INSERT INTO "{table}" (val) VALUES ($1), ($1)', SECRET_VALUE
        )


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_execute_ddl_sync_does_not_leak_duplicate_value_in_log(
    test_suite, caplog
):
    """Sync eager batch executor (`_execute_ddl` → `engine.ddl_failed`): a real
    duplicate-value ``CREATE UNIQUE INDEX`` failure MUST NOT surface the value.

    Pre-fix this FAILS (the raw ``DETAIL: Key (val)=(<value>)`` reaches the ERROR
    log); post-fix it PASSES (redacted to ``[REDACTED]``).
    """
    table = f"leak_probe_s_{uuid.uuid4().hex[:8]}"
    idx = f"idx_{table}"
    await _seed_duplicate_rows(test_suite, table)

    db = DataFlow(test_suite.config.url, auto_migrate=True)
    schema_sql = {
        "tables": [],
        "indexes": [f'CREATE UNIQUE INDEX "{idx}" ON "{table}" (val)'],
        "foreign_keys": [],
    }
    try:
        with caplog.at_level(logging.ERROR, logger=_ENGINE_LOGGER):
            # Index (not CREATE TABLE) failure → logged + recorded, not raised.
            db._execute_ddl(schema_sql)

        blob = _rendered(caplog.records)
        assert any(
            r.getMessage() == "engine.ddl_failed" for r in caplog.records
        ), "expected the sync eager-batch executor to log engine.ddl_failed"
        assert SECRET_VALUE not in blob, (
            "issue #1550: duplicate column value leaked into the ERROR log via "
            "the sync eager batch DDL executor"
        )
        assert (
            "[REDACTED]" in blob
        ), "sanitize_db_error did not run on the sync eager-batch log path"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_execute_ddl_async_does_not_leak_duplicate_value_in_log(
    test_suite, caplog
):
    """Async eager batch executor (`_execute_ddl_async` → `engine.ddl_async_failed`):
    same contract as the sync path, exercised through the async surface."""
    table = f"leak_probe_a_{uuid.uuid4().hex[:8]}"
    idx = f"idx_{table}"
    await _seed_duplicate_rows(test_suite, table)

    db = DataFlow(test_suite.config.url, auto_migrate=True)
    schema_sql = {
        "tables": [],
        "indexes": [f'CREATE UNIQUE INDEX "{idx}" ON "{table}" (val)'],
        "foreign_keys": [],
    }
    try:
        with caplog.at_level(logging.ERROR, logger=_ENGINE_LOGGER):
            await db._execute_ddl_async(schema_sql)

        blob = _rendered(caplog.records)
        assert any(
            r.getMessage() == "engine.ddl_async_failed" for r in caplog.records
        ), "expected the async eager-batch executor to log engine.ddl_async_failed"
        assert SECRET_VALUE not in blob, (
            "issue #1550: duplicate column value leaked into the ERROR log via "
            "the async eager batch DDL executor"
        )
        assert (
            "[REDACTED]" in blob
        ), "sanitize_db_error did not run on the async eager-batch log path"
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


# --------------------------------------------------------------------------
# Part B — Tier-1, deterministic injected driver error (sanitize is load-bearing)
# --------------------------------------------------------------------------
#
# The value-DETAIL leak on the RAISE path fires only for CREATE TABLE failures,
# which do not naturally carry a duplicate-value DETAIL on a real backend. The
# ONLY injection permitted (mirroring #1548's fault-injection contract) is the
# driver-error STRING returned by the batch executor — the database itself is
# never mocked; we are exercising the engine's error-rendering branch with a
# controlled value-bearing input.

_VALUE_BEARING_ERROR = (
    "could not create unique index\n"
    f"DETAIL:  Key (val)=({SECRET_VALUE}) is duplicated."
)


def _patch_executor_result(monkeypatch, crafted):
    """Force ``SyncDDLExecutor.execute_ddl_batch_per_statement`` (imported
    locally by both eager executors) to return ``crafted`` regardless of input."""
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    monkeypatch.setattr(
        SyncDDLExecutor,
        "execute_ddl_batch_per_statement",
        lambda self, statements: crafted,
    )


@pytest.mark.regression
def test_injected_index_failure_log_is_sanitized(tmp_path, monkeypatch, caplog):
    """The direct ``engine.ddl_failed`` log render routes the value-bearing
    driver error through ``sanitize_db_error`` → ``[REDACTED]``, value gone."""
    crafted = [
        {
            "sql": "CREATE UNIQUE INDEX idx_leak ON leak_probe (val)",
            "success": False,
            "error": _VALUE_BEARING_ERROR,
        }
    ]
    _patch_executor_result(monkeypatch, crafted)

    db = DataFlow(f"sqlite:///{tmp_path}/leak_b_log.db", auto_migrate=True)
    with caplog.at_level(logging.ERROR, logger=_ENGINE_LOGGER):
        db._execute_ddl(
            {"tables": [], "indexes": [crafted[0]["sql"]], "foreign_keys": []}
        )

    rec = next(
        (r for r in caplog.records if r.getMessage() == "engine.ddl_failed"), None
    )
    assert rec is not None, "engine.ddl_failed was not logged"
    error_field = getattr(rec, "error", "")
    assert SECRET_VALUE not in error_field
    assert (
        "[REDACTED]" in error_field
    ), "the injected DETAIL value was not redacted — sanitize is not load-bearing"


@pytest.mark.regression
def test_injected_create_table_failure_raise_is_sanitized(tmp_path, monkeypatch):
    """The direct ``DDLFailedError`` raise wraps ``original_error`` in a
    sanitized ``RuntimeError`` — the user-facing message carries ``[REDACTED]``,
    never the raw value; the raw exception survives only as ``__cause__``."""
    crafted = [
        {
            "sql": "CREATE TABLE leak_probe (val TEXT)",
            "success": False,
            "error": _VALUE_BEARING_ERROR,
        }
    ]
    _patch_executor_result(monkeypatch, crafted)

    db = DataFlow(f"sqlite:///{tmp_path}/leak_b_raise.db", auto_migrate=True)

    with pytest.raises(DDLFailedError) as exc_info:
        db._execute_ddl(
            {"tables": [crafted[0]["sql"]], "indexes": [], "foreign_keys": []}
        )

    message = str(exc_info.value)
    assert SECRET_VALUE not in message, (
        "issue #1550: the raw duplicate value leaked into the DDLFailedError "
        "message on the eager batch raise path"
    )
    assert (
        "[REDACTED]" in message
    ), "the injected DETAIL value was not redacted in the DDLFailedError message"
    # The original exception is preserved for traceback-only diagnosability
    # (matches the #1548 lazy-path design) — it is NOT part of the user-facing
    # message, which is the leak surface this fix closes.
    assert exc_info.value.__cause__ is not None


# --------------------------------------------------------------------------
# Part C — structural invariant (guards against a future re-inline regression)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_no_eager_batch_ddl_site_renders_raw_error_text():
    """Every DDL-failure error render in engine.py routes through
    ``_sanitize_db_error`` / a wrapped ``RuntimeError``. A raw
    ``original_error=error`` or ``"error": err_text`` render is the exact
    #1550 leak shape — assert none remain, so a future edit that re-inlines a
    raw render fails this test loudly (``refactor-invariants.md``)."""
    engine_src = (
        Path(__file__).resolve().parents[2] / "src" / "dataflow" / "core" / "engine.py"
    ).read_text()

    # Raw exception passed directly as original_error (pre-#1550 raise shape).
    assert "original_error=error," not in engine_src, (
        "engine.py raises DDLFailedError with a RAW original_error — re-inlined "
        "the #1550 leak; wrap in RuntimeError(self._sanitize_db_error(...))"
    )
    # Raw err_text / error rendered into a DDL-failure log's error field.
    for raw in ('"error": err_text}', '"error": error}'):
        assert raw not in engine_src, (
            f"engine.py logs a DDL error with a raw {raw!r} field — re-inlined "
            "the #1550 leak; wrap in self._sanitize_db_error(...)"
        )


# --------------------------------------------------------------------------
# Part D — MySQL redaction root fix + executor-layer coverage (red-team round 2)
# --------------------------------------------------------------------------
#
# Round-1 red team found the leak class is not closed at the engine layer alone:
# (a) `sanitize_db_error` missed the MySQL `Duplicate entry 'value' for key`
#     shape (errno 1062) — the value survives on MySQL; and
# (b) `SyncDDLExecutor` logs the raw driver error at ERROR *before* returning to
#     engine.py, so the sync single-statement paths (`create_tables_sync`,
#     `_create_table_sync`, the `_create_tables_batch` fallback) leaked one layer
#     below the engine fix. Both are now closed at the shared helper / executor.


@pytest.mark.regression
def test_mysql_duplicate_entry_shape_is_redacted():
    """`sanitize_db_error` redacts the MySQL/MariaDB ``Duplicate entry 'value'
    for key 'name'`` shape (errno 1062) — which carries the offending column
    value but has neither a ``DETAIL:`` clause nor the PG ``Key(col)=(value)``
    form the other two regexes match. Without this the #1550 fix still leaks on
    MySQL for the most common value-bearing DDL failure (CREATE UNIQUE INDEX
    over duplicate data)."""
    from dataflow.core.exceptions import sanitize_db_error

    raw = "(1062, \"Duplicate entry 'alice@corp.example' for key 'users.idx_email'\")"
    out = sanitize_db_error(raw)
    assert "alice@corp.example" not in out, "MySQL duplicate-entry value leaked"
    assert "[REDACTED]" in out

    # A value containing a literal quote (O'Brien) still fully redacts (lazy
    # match to the `' for key` anchor).
    assert "Brien" not in sanitize_db_error("Duplicate entry 'O'Brien' for key 'k'")

    # Benign MySQL 1061 carries an index NAME, not a value — MUST NOT be
    # over-redacted (the diagnostic key name is preserved, like PG Key(col)).
    assert "idx_email" in sanitize_db_error(
        "(1061, \"Duplicate key name 'idx_email'\")"
    )


@pytest.mark.regression
def test_sync_ddl_executor_sanitizes_at_source():
    """Structural invariant: ``sync_ddl_executor.py`` redacts the driver error
    at assignment in BOTH failing methods, so neither its ERROR log nor the
    returned ``error`` dict carries the raw value (the executor is the lowest
    layer touching the raw driver exception; engine-layer sanitization alone
    left this raw — round-2 red-team HIGH finding)."""
    exec_src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "migrations"
        / "sync_ddl_executor.py"
    ).read_text()
    assert (
        "from dataflow.core.exceptions import sanitize_db_error" in exec_src
    ), "sync_ddl_executor.py must import the shared redactor"
    assert exec_src.count("error_str = sanitize_db_error(str(e))") >= 2, (
        "both execute_ddl and execute_ddl_batch must redact the driver error at "
        "the source (#1550 executor-layer leak)"
    )


async def _executor_leak_check(test_suite, caplog, *, batch: bool):
    """Drive a real duplicate-value CREATE UNIQUE INDEX through SyncDDLExecutor
    and assert the value reaches neither the executor's ERROR log nor its
    returned error dict."""
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    kind = "b" if batch else "s"
    table = f"leak_exec_{kind}_{uuid.uuid4().hex[:8]}"
    idx = f"idx_{table}"
    await _seed_duplicate_rows(test_suite, table)
    stmt = f'CREATE UNIQUE INDEX "{idx}" ON "{table}" (val)'
    executor = SyncDDLExecutor(test_suite.config.url)
    expected_msg = (
        "sync_ddl_executor.ddl_batch_execution_failed_at_statement"
        if batch
        else "sync_ddl_executor.ddl_execution_failed"
    )
    try:
        with caplog.at_level(
            logging.ERROR, logger="dataflow.migrations.sync_ddl_executor"
        ):
            result = (
                executor.execute_ddl_batch([stmt])
                if batch
                else executor.execute_ddl(stmt)
            )

        assert result["success"] is False
        assert SECRET_VALUE not in (
            result.get("error") or ""
        ), "the executor's RETURNED error dict leaked the duplicate value"
        assert any(
            r.getMessage() == expected_msg for r in caplog.records
        ), f"expected the executor to log {expected_msg} at ERROR"
        blob = _rendered(caplog.records)
        assert SECRET_VALUE not in blob, (
            "issue #1550: the executor ERROR log leaked the duplicate value one "
            "layer below the engine fix"
        )
        assert "[REDACTED]" in blob
    finally:
        async with test_suite.get_connection() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_sync_ddl_executor_execute_ddl_does_not_leak(test_suite, caplog):
    """`SyncDDLExecutor.execute_ddl` (single-statement) — the raw-logging site
    reached by `create_tables_sync` / `_create_table_sync` — MUST NOT leak."""
    await _executor_leak_check(test_suite, caplog, batch=False)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_sync_ddl_executor_execute_ddl_batch_does_not_leak(test_suite, caplog):
    """`SyncDDLExecutor.execute_ddl_batch` — the batch sibling of the same
    raw-logging leak class — MUST NOT leak."""
    await _executor_leak_check(test_suite, caplog, batch=True)

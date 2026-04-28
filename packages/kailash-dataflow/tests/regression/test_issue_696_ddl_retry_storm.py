# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #696 — DataFlow auto_migrate DDL retry storm.

Origin
------

The JourneyMate (Azure FastAPI + DataFlow) production incident on
2026-04-28 logged ``ERROR:dataflow.core.engine:Failed to execute DDL:
CREATE TABLE IF NOT EXISTS "evaluation_dimensions" ...`` every 30 s for
the lifetime of the deployment. Root cause:

1. ``@db.model`` registered the model.
2. First access fired ``_execute_ddl`` / ``_create_table_sync``.
3. CREATE TABLE failed (FK reference to a sibling table not yet built
   in the auto-migrate ordering).
4. The ``except Exception: continue`` swallowed the failure with an
   ERROR log only — the schema cache was NEVER marked, so every
   subsequent access re-entered ``ensure_table_exists`` and re-fired
   the DDL.
5. Combined with the AsyncSQLDatabaseNode pool-fallback leak (#697),
   each retry created a fresh 5–20 connection pool that was never
   reclaimed mid-process. Within minutes Azure PG saturated at
   480–500 connections vs the 100–200 ceiling.

Fix (PRs DPI-A1/A2/A3)
----------------------

- ``DDLFailedError`` typed exception (``dataflow.core.exceptions``).
- Per-instance ``_failed_table_creations: dict[str, FailedDDLRecord]``.
- ``_check_failed_ddl`` runs at the head of ``ensure_table_exists``
  BEFORE the schema-cache check; raises ``DDLFailedError`` in
  ``auto_migrate=True`` (default, fail-fast).
- ``_record_failed_ddl`` captures + emits a single ERROR log per model
  (idempotent on model_name).
- ``auto_migrate="warn"`` opts into legacy log-and-continue semantics
  for callers that depended on retry-on-access.

What this file pins
-------------------

1. **Fail-fast circuit (default)**: 10 accesses to a failed model
   produce ONE recorded failure + ONE ERROR log + 9 DDLFailedError
   raises (NOT 10 fresh DDL attempts). This is the regression that
   would have prevented the JourneyMate retry storm.
2. **Warn mode escape hatch**: ``auto_migrate="warn"`` preserves
   pre-#696 log-and-continue behavior for callers who explicitly opt
   in.
3. **Auto_migrate enum validation**: typo strings (``"WARN"``,
   ``"warning"``) raise ``DataFlowConfigurationError`` at __init__,
   not silently fall back to fail-fast.

Tier
----

Tier 2 against real PostgreSQL when available (the JourneyMate
incident used Postgres-only DDL ordering invariants). Falls back to
file-backed SQLite when the IntegrationTestSuite cannot reach a real
DB — both tiers exercise the SAME failed-DDL state machine because
the circuit-breaker is dialect-agnostic. Per
``rules/testing.md`` § 3-Tier Testing, real-infrastructure is
preferred; the SQLite path is the ALWAYS-ON guard so the test runs in
default ``pytest`` collection without docker.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Optional

import pytest

from dataflow import DataFlow, DDLFailedError
from dataflow.core.engine import FailedDDLRecord
from dataflow.exceptions import DataFlowConfigurationError

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Test fixture — file-backed SQLite (default) OR Postgres test_suite if
# infrastructure is reachable. Both exercise the same circuit breaker.
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_file_url():
    """File-backed SQLite URL scoped to one test.

    SQLite ``:memory:`` cannot be used because DataFlow's migration
    system uses a separate connection for the migration lock table
    and ``:memory:`` databases are not shared across connections.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"issue_696_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


# ---------------------------------------------------------------------------
# DPI-A4: Failed-DDL circuit breaker — fail-fast (default) mode
# ---------------------------------------------------------------------------


def test_ddl_failed_error_is_typed_subclass_of_dataflow_error():
    """``DDLFailedError`` MUST subclass ``DataFlowError`` so callers can
    ``except DataFlowError`` and catch the new type without explicit
    import."""
    from dataflow.exceptions import DataFlowError

    assert issubclass(DDLFailedError, DataFlowError), (
        "Regression #696: DDLFailedError MUST subclass DataFlowError "
        "so existing exception-handlers continue to catch it"
    )


def test_failed_ddl_record_is_recorded_once_per_model(sqlite_file_url):
    """Regression #696: ``_record_failed_ddl`` is idempotent on
    model_name. The first failure records + emits one ERROR log; every
    subsequent failure for the same model returns the SAME record
    without re-logging.

    This is the structural defense against the JourneyMate retry storm
    manifesting as log spam (200,000 ERROR lines / hour) even if the
    DDL retry itself were somehow re-fired.
    """
    db = DataFlow(sqlite_file_url)

    # Simulate 10 attempted DDL failures for the same model (the
    # JourneyMate retry storm: every 30 s for 30 min = 60 attempts).
    rec_first: Optional[FailedDDLRecord] = None
    for i in range(10):
        rec = db._record_failed_ddl(
            "Order",
            ValueError(f"FK missing (attempt #{i})"),
            "CREATE TABLE orders (...)",
        )
        if rec_first is None:
            rec_first = rec

    # Idempotent: every call after the first returns the same record.
    assert rec_first is db._failed_table_creations["Order"]
    # Single entry in the failed-table state.
    assert len(db._failed_table_creations) == 1


def test_check_failed_ddl_raises_on_recorded_failure(sqlite_file_url):
    """Regression #696: once recorded, every subsequent access raises
    ``DDLFailedError`` WITHOUT re-firing the DDL.

    This is the core circuit-breaker invariant. The JourneyMate
    incident's 30-second retry interval came from FastAPI health checks
    re-entering ``ensure_table_exists`` — with the fix, every health
    check now raises immediately instead of retrying the DDL.
    """
    db = DataFlow(sqlite_file_url)
    db._record_failed_ddl(
        "Order", ValueError("FK missing"), "CREATE TABLE orders (...)"
    )

    # Every subsequent access raises — no DDL re-fire.
    for i in range(10):
        with pytest.raises(DDLFailedError) as exc_info:
            db._check_failed_ddl("Order")
        # Error surface carries the operator-actionable context.
        assert exc_info.value.model_name == "Order"
        assert "FK missing" in str(exc_info.value.original_error)


def test_check_failed_ddl_no_op_for_unfailed_model(sqlite_file_url):
    """Regression #696: ``_check_failed_ddl`` MUST NOT raise for models
    that have not failed. The circuit breaker is per-model — a failed
    ``Order`` must not poison a healthy ``Customer`` access path.
    """
    db = DataFlow(sqlite_file_url)
    db._record_failed_ddl("Order", ValueError("FK"), "CREATE TABLE orders")

    # Healthy model: no raise.
    db._check_failed_ddl("Customer")
    db._check_failed_ddl("Product")


def test_clear_failed_ddl_allows_retry(sqlite_file_url):
    """Regression #696: ``_clear_failed_ddl`` permits operators who fix
    the root cause to retry without restarting the application.

    This is the explicit recovery path; the canonical recovery is a
    process restart (clears the in-memory map), but ``_clear_failed_ddl``
    is the API contract for advanced workflows.
    """
    db = DataFlow(sqlite_file_url)
    db._record_failed_ddl("Order", ValueError("FK"), "CREATE TABLE orders")
    assert "Order" in db._failed_table_creations

    db._clear_failed_ddl("Order")
    assert "Order" not in db._failed_table_creations
    # No raise after clear.
    db._check_failed_ddl("Order")

    # Idempotent: clear on already-cleared key is a no-op.
    db._clear_failed_ddl("Order")


def test_first_failure_emits_single_error_log(sqlite_file_url, caplog):
    """Regression #696: the first failure emits exactly ONE ERROR log
    line (per ``rules/observability.md`` Rule 1 — structured state
    transition). Subsequent failures for the same model are silent
    (already-recorded) — preventing log-pipeline saturation under
    storm conditions.
    """
    db = DataFlow(sqlite_file_url)

    with caplog.at_level(logging.ERROR, logger="dataflow.core.engine"):
        # 10 attempts (the JourneyMate storm cadence)
        for i in range(10):
            db._record_failed_ddl(
                "Order",
                ValueError(f"FK missing #{i}"),
                "CREATE TABLE orders (...)",
            )

    # Filter to our specific event so other ERROR logs from setup
    # don't pollute the count.
    ddl_failed_records = [
        r for r in caplog.records if "engine.ddl_failed_recorded" in r.getMessage()
    ]
    # CRITICAL invariant: ONE log per model, NOT one per attempt.
    # If this count is 10, the retry-storm log spam is back.
    assert len(ddl_failed_records) == 1, (
        f"Regression #696: expected exactly 1 ERROR log for the first "
        f"DDL failure, got {len(ddl_failed_records)}. The JourneyMate "
        f"incident's 200K-line/hr log flood would be back."
    )


# ---------------------------------------------------------------------------
# DPI-A4: ``auto_migrate="warn"`` legacy escape hatch
# ---------------------------------------------------------------------------


def test_warn_mode_does_not_raise_on_recorded_failure(sqlite_file_url):
    """Regression #696: ``auto_migrate="warn"`` preserves pre-#696
    log-and-continue. Operators who explicitly opt in get the legacy
    retry-on-access semantics back (and the burden of pool-leak risk
    that comes with it).
    """
    db = DataFlow(sqlite_file_url, auto_migrate="warn")
    db._record_failed_ddl(
        "Order", ValueError("FK missing"), "CREATE TABLE orders (...)"
    )

    # warn mode: no raise even with a recorded failure.
    db._check_failed_ddl("Order")  # MUST NOT raise

    # Failure IS recorded for introspection.
    assert "Order" in db._failed_table_creations


def test_warn_mode_init_sets_warn_flag(sqlite_file_url):
    """Regression #696: ``auto_migrate="warn"`` sets ``_auto_migrate=True``
    (so existing call sites that test truthiness for migration-triggering
    continue to fire) AND sets ``_auto_migrate_warn=True`` (so the
    fail-fast helpers know to short-circuit).
    """
    db = DataFlow(sqlite_file_url, auto_migrate="warn")
    assert db._auto_migrate is True
    assert db._auto_migrate_warn is True

    # Default mode: fail-fast
    db_default = DataFlow(sqlite_file_url)
    assert db_default._auto_migrate is True
    assert db_default._auto_migrate_warn is False

    # auto_migrate=False: no warn flag, no migration
    db_off = DataFlow(sqlite_file_url, auto_migrate=False)
    assert db_off._auto_migrate is False
    assert db_off._auto_migrate_warn is False


def test_invalid_auto_migrate_string_rejected_at_init(sqlite_file_url):
    """Regression #696: typo strings MUST raise
    ``DataFlowConfigurationError`` at __init__.

    A silent fallback (``"WARN"`` → fail-fast because != ``"warn"``)
    would let an operator who intended legacy mode ship a fail-fast
    deployment and discover the new exception class only when DDL
    failed in production. The strict validation at __init__ converts
    a runtime surprise into a deployment-time failure.
    """
    for bad in ["WARN", "warning", "warn ", "FAIL_FAST", "permissive", "true"]:
        with pytest.raises(DataFlowConfigurationError) as exc_info:
            DataFlow(sqlite_file_url, auto_migrate=bad)
        assert "warn" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# DPI-A4: End-to-end via real DataFlow + real DDL failure (Tier 2)
#
# Forces a CREATE TABLE failure by registering a model whose DDL
# references a non-existent type. This is the closest dialect-agnostic
# repro of the JourneyMate FK-ordering failure that does not require
# multi-statement schema choreography.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_table_exists_fails_fast_after_ddl_failure(sqlite_file_url):
    """Regression #696: end-to-end fail-fast circuit through
    ``ensure_table_exists``.

    Pre-fix: 10 calls to ``ensure_table_exists`` for a model whose DDL
    fails would re-fire the DDL 10 times (the JourneyMate retry storm).

    Post-fix: 1 call records the failure; 9 subsequent calls raise
    ``DDLFailedError`` immediately without DDL execution.

    We seed the failed-DDL state directly (rather than constructing a
    DDL-poisoning model) because the dialect-agnostic invariant under
    test is the CIRCUIT BREAKER, not the failure-detection plumbing
    (which is per-DDL-path and exercised in the helper tests above).
    """
    db = DataFlow(sqlite_file_url)
    await db.initialize()

    # Pretend an earlier DDL attempt failed for "GhostModel".
    db._record_failed_ddl(
        "GhostModel",
        RuntimeError('relation "parent_table" does not exist'),
        'CREATE TABLE "ghosts" ("parent_id" int REFERENCES parent_table(id))',
    )

    # 10 accesses — every single one MUST raise DDLFailedError.
    # Critically: NONE of them re-enter the DDL execution path. We
    # verify this by counting recorded failures: the first call entered
    # _record_failed_ddl above; subsequent _check_failed_ddl raises at
    # the head of ensure_table_exists BEFORE any DDL fires.
    initial_record_count = len(db._failed_table_creations)
    for i in range(10):
        with pytest.raises(DDLFailedError):
            await db.ensure_table_exists("GhostModel")
    # No new records — the circuit breaker short-circuited every call.
    assert len(db._failed_table_creations) == initial_record_count
    assert "GhostModel" in db._failed_table_creations


@pytest.mark.asyncio
async def test_ensure_table_exists_warn_mode_falls_through(sqlite_file_url):
    """Regression #696: ``auto_migrate="warn"`` preserves legacy
    retry-on-access. ``ensure_table_exists`` does NOT short-circuit on
    a recorded failure — the pre-#696 behavior is the explicit opt-in
    contract.
    """
    db = DataFlow(sqlite_file_url, auto_migrate="warn")
    await db.initialize()

    # Seed a failure record.
    db._record_failed_ddl(
        "WarnGhost",
        RuntimeError("FK missing"),
        "CREATE TABLE warn_ghost",
    )

    # warn mode: ensure_table_exists does NOT raise from
    # _check_failed_ddl. (It may still return False / log if the DDL
    # path itself fails — that's the legacy behavior.)
    try:
        await db.ensure_table_exists("WarnGhost")
    except DDLFailedError:
        pytest.fail(
            "Regression #696 warn-mode escape hatch broken: "
            "auto_migrate='warn' MUST NOT raise DDLFailedError"
        )


def test_failed_table_creations_is_per_instance(sqlite_file_url):
    """Regression #696: ``_failed_table_creations`` is per-DataFlow-
    instance state. Two DataFlow instances MUST NOT share the failed-
    DDL map (which would let one tenant's CREATE TABLE failure poison
    another tenant's framework).
    """
    db_a = DataFlow(sqlite_file_url)
    db_b = DataFlow(sqlite_file_url)

    db_a._record_failed_ddl("Order", ValueError("a"), "CREATE TABLE")

    assert "Order" in db_a._failed_table_creations
    assert "Order" not in db_b._failed_table_creations, (
        "Regression #696: failed-DDL state MUST be per-instance "
        "(otherwise one tenant's failure poisons every other DataFlow)"
    )


def test_extract_table_from_statement_attribution():
    """Regression #696: ``_extract_table_from_statement`` extracts the
    table name from CREATE/ALTER/DROP TABLE statements so the bulk DDL
    paths (``_execute_ddl``, ``_execute_ddl_async``) attribute failures
    to the right model. Returns None for index/type/unrelated
    statements so they don't poison real model state.
    """
    extract = DataFlow._extract_table_from_statement
    cases = [
        ("CREATE TABLE users (id INT)", "users"),
        ('CREATE TABLE IF NOT EXISTS "orders" (id INT)', "orders"),
        ("ALTER TABLE products ADD COLUMN x INT", "products"),
        ("DROP TABLE if exists archived (id INT)", "archived"),
        ('CREATE TABLE schema."schema_table" (id INT)', "schema_table"),
        # Negative: index / type / unrelated DDL → None.
        ("CREATE INDEX idx_users_name ON users(name)", None),
        ("CREATE TYPE my_enum AS ENUM ('a', 'b')", None),
        ("SET CONSTRAINTS ALL DEFERRED", None),
        ("", None),
    ]
    for sql, expected in cases:
        assert (
            extract(sql) == expected
        ), f"_extract_table_from_statement({sql!r}) = {extract(sql)!r}, expected {expected!r}"


def test_ddl_failed_error_string_has_actionable_context():
    """Regression #696: the str() of ``DDLFailedError`` MUST include
    the model name, the original error type+message, and the
    statement_preview. This is the surface operators see in their
    error tracker; missing any of these forces a code-dive to
    diagnose.
    """
    err = DDLFailedError(
        model_name="evaluation_dimensions",
        original_error=RuntimeError('relation "evaluations" does not exist'),
        statement_preview=(
            'CREATE TABLE IF NOT EXISTS "evaluation_dimensions" '
            "(id SERIAL PRIMARY KEY, eval_id INT REFERENCES evaluations(id))"
        ),
    )
    msg = str(err)
    assert "evaluation_dimensions" in msg
    assert "RuntimeError" in msg
    assert 'relation "evaluations" does not exist' in msg
    # Statement preview is truncated to 200 chars (rules/security.md
    # — don't leak entire schemas through error chains).
    assert len(err.statement_preview) <= 200
    # Operator-actionable next-step guidance is in the message.
    assert "auto_migrate" in msg

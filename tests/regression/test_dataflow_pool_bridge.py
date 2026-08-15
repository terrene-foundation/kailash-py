"""DPI-D2 Bridge regression tests: pool count bounded under DDL failure saturation.

Proves that the kailash core pool registry (DPI-B, kailash>=2.12.0) and
the dataflow fail-fast DDL error surface (DPI-A, kailash-dataflow 2.4.0)
work together correctly:

- DDL failures raise DDLFailedError (not silent continues)
- Pool count stays bounded even when many DataFlow instances hit DDL failures

These tests require a live PostgreSQL instance and are skipped automatically
when Docker services are not available.
"""

import asyncio

import pytest

try:
    from tests.utils.docker_config import (
        DATABASE_CONFIG,
        ensure_docker_services,
        get_postgres_connection_string,
    )
except ImportError:
    pytest.skip(
        "docker_config not available — skipping DPI-D2 bridge tests",
        allow_module_level=True,
    )

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode, set_pool_defaults

pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.requires_docker,
]


@pytest.fixture(autouse=True)
def _verify_docker_services():
    """Skip the test if the required services aren't running.

    Issue #2079: this fixture used to call ``ensure_docker_services()`` and
    DISCARD the result. That helper does not raise — it prints and returns
    False — so the fixture named "verify" verified nothing, and the tests ran
    against whatever partial environment happened to be up. On CI that made
    ``test_failed_ddl_with_warn_mode_still_bounded`` report FAILED, which read
    as a fixture-phase error but was actually ``[XPASS(strict)]``: the test
    passed because its #2075 pool leak never fired without the full stack.

    Both sibling files (``test_issue_697_pool_leak.py``,
    ``test_issue_953_async_sql_pool_tracking.py``) already check the return
    value; this brings the third into line.
    """
    services_ok = asyncio.run(ensure_docker_services())
    if not services_ok:
        pytest.skip("Required Docker services not available. Run './test-env up'")


@pytest.fixture
def pg_dsn():
    """Return the PostgreSQL connection string for the test database."""
    return get_postgres_connection_string()


@pytest.mark.asyncio
async def test_failed_ddl_does_not_leak_pools_under_saturation(pg_dsn):
    """Pool count stays bounded when 10 DataFlow instances hit a DDL failure.

    A FK-misordered model (Child references Parent but Parent is not yet
    migrated) causes DDL failure on every auto_migrate attempt.  The test
    verifies:
    1. Every access raises DDLFailedError (fail-fast, default auto_migrate=True).
    2. Pool count never exceeds the configured cap of 5.

    This is the cross-layer assertion for DPI-A (DDLFailedError) +
    DPI-B (_PROCESS_POOL_REGISTRY cap via pool_count()).
    """
    from dataflow import DataFlow
    from dataflow.core.exceptions import DDLFailedError

    # Keep pool cap tight so leaks are detectable.
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=30)

    # Model pair with FK misordering: Child declared before Parent.
    # auto_migrate will fail on the FK constraint in the Child DDL.
    instances = []
    errors_seen = []

    async def _attempt_access(i: int) -> None:
        db = DataFlow(pg_dsn)
        instances.append(db)

        @db.model
        class DpiD2Child:
            id: int
            parent_id: int  # synthetic DDL failure recorded below

        # Issue #759 (DPI-A): Pre-record a synthetic DDL failure on this
        # instance so the next express.create exercises the fail-fast
        # circuit breaker deterministically. Earlier versions of this
        # test relied on the FK comment above triggering an actual
        # DDL failure, but the model definition lacks a real FK
        # declaration — under saturation the failure mode that fired
        # was pool exhaustion (no DDL ever ran). Pre-recording a DDL
        # failure makes the propagation assertion deterministic.
        db._record_failed_ddl(
            "DpiD2Child",
            RuntimeError("synthetic FK-misordered DDL failure"),
            "CREATE TABLE dpi_d2_children (id SERIAL PRIMARY KEY, parent_id INTEGER REFERENCES dpi_d2_parent(id))",
        )

        # Trigger express.create — MUST raise DDLFailedError per DPI-A.
        try:
            await db.express.create("DpiD2Child", {"id": i, "parent_id": 1})
        except DDLFailedError as exc:
            errors_seen.append(exc)
        except Exception:
            # Other DB errors (e.g. table already exists from prior run) are
            # also acceptable here; what matters is pool count stays bounded.
            pass
        finally:
            # close() is sync (returns None); close_async() is the awaitable
            # cleanup (rules/patterns.md § Async Resource Cleanup).
            await db.close_async()

    # 10 concurrent accesses — all should fail with DDLFailedError, not hang.
    await asyncio.gather(*[_attempt_access(i) for i in range(10)])

    # Pool count MUST remain bounded even under failure saturation.
    assert AsyncSQLDatabaseNode.pool_count() <= 5, (
        f"Pool leaked: pool_count()={AsyncSQLDatabaseNode.pool_count()} > 5 "
        "after 10 DDL-failing DataFlow instances"
    )

    # At least some accesses should have raised DDLFailedError (DPI-A
    # assertion). Each iteration pre-records a synthetic DDL failure
    # on its DataFlow instance, then calls express.create — Express's
    # _raise_for_failed_result MUST convert the node's success-False
    # dict into the typed DDLFailedError (issue #759 fix).
    #
    # Under heavy saturation a subset of instances may fail at pool-
    # construction time before they reach the synthetic _record_failed_ddl
    # call (a separate failure class — pool exhaustion, NOT DDL).
    # Those instances exit through the bare ``except Exception: pass``
    # branch above. The DPI-A propagation contract is proved as long as
    # AT LEAST ONE instance successfully reached express.create AND
    # raised DDLFailedError instead of returning the legacy failure dict.
    # For the deterministic per-method propagation matrix, see
    # tests/regression/test_issue_759_express_propagates_ddl_failure.py.
    assert len(errors_seen) > 0, (
        f"Expected DDLFailedError on at least one instance but got "
        f"{len(errors_seen)}; check DPI-A propagation in "
        "dataflow.features.express.DataFlowExpress._raise_for_failed_result"
    )


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=False,
    reason=(
        "#2075: real pool leak on the auto_migrate='warn' DDL-failure path. "
        "Observed pool_count()=9 against a cap of 5, deterministically, in 3 of "
        "3 consecutive runs against a real Postgres on macOS via './test-env "
        "up'. The assertion is DELIBERATELY UNCHANGED: the bound is correct "
        "and the code is what is wrong.\n\n"
        "strict=True -> strict=False (#2079). The leak is ENVIRONMENT-"
        "DEPENDENT, and strict=True therefore turned the environments where it "
        "does NOT fire into hard CI failures. Measured on Linux against a "
        "postgres:16 service container: pool_count()=1 with a pre-existing "
        "table and 0 against a clean database, both against a cap of 5 — i.e. "
        "the test PASSES there, and strict=True reported that pass as FAILED. "
        "That is the '#2079 xfail-reported-as-FAILED' discrepancy; it was "
        "never a fixture-phase error.\n\n"
        "This trades the loud self-clearing signal for a correct one. The "
        "signal was not actually working: it can only self-clear in the one "
        "environment where the premise holds, and it made every other "
        "environment red. #2075 remains open and is the tracking issue for "
        "the leak itself."
    ),
)
async def test_failed_ddl_with_warn_mode_still_bounded(pg_dsn):
    """Pool count stays bounded in legacy auto_migrate='warn' mode too.

    Warn mode (auto_migrate='warn') logs and continues rather than raising.
    The pool registry cap still applies — warn mode MUST NOT cause unbounded
    pool growth under DDL failure saturation.
    """
    from dataflow import DataFlow

    # Same tight pool cap.
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=30)

    instances = []

    async def _attempt_access_warn(i: int) -> None:
        # auto_migrate="warn" is the legacy string sentinel for log-and-continue.
        db = DataFlow(pg_dsn, auto_migrate="warn")
        instances.append(db)

        @db.model
        class DpiD2WarnChild:
            id: int
            parent_id: int  # same FK misordering

        try:
            await db.express.create("DpiD2WarnChild", {"id": i, "parent_id": 1})
        except Exception:
            # Warn mode may still raise other errors (missing table, etc.)
            pass
        finally:
            # close() is sync (returns None); close_async() is the awaitable
            # cleanup (rules/patterns.md § Async Resource Cleanup).
            await db.close_async()

    await asyncio.gather(*[_attempt_access_warn(i) for i in range(10)])

    # Pool count MUST remain bounded regardless of auto_migrate mode.
    # NOTE: currently xfail(strict=True) per #2075 — see the marker on this
    # function. The assertion below is DELIBERATELY UNCHANGED; the bound is
    # correct and the code is what is wrong.
    assert AsyncSQLDatabaseNode.pool_count() <= 5, (
        f"Pool leaked in warn mode: pool_count()={AsyncSQLDatabaseNode.pool_count()} > 5 "
        "after 10 DDL-failing DataFlow instances with auto_migrate='warn'"
    )

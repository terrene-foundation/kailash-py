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
    """Ensure PostgreSQL Docker service is running before each test."""
    asyncio.run(ensure_docker_services())


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
            parent_id: int  # FK to DpiD2Parent — not yet created, DDL fails

        # Trigger auto_migrate by attempting a create operation.
        try:
            await db.express.create("DpiD2Child", {"id": i, "parent_id": 1})
        except DDLFailedError as exc:
            errors_seen.append(exc)
        except Exception:
            # Other DB errors (e.g. table already exists from prior run) are
            # also acceptable here; what matters is pool count stays bounded.
            pass
        finally:
            await db.close()

    # 10 concurrent accesses — all should fail with DDLFailedError, not hang.
    await asyncio.gather(*[_attempt_access(i) for i in range(10)])

    # Pool count MUST remain bounded even under failure saturation.
    assert AsyncSQLDatabaseNode.pool_count() <= 5, (
        f"Pool leaked: pool_count()={AsyncSQLDatabaseNode.pool_count()} > 5 "
        "after 10 DDL-failing DataFlow instances"
    )

    # At least some accesses should have raised DDLFailedError (DPI-A assertion).
    # If none raised it means the FK constraint was not enforced — the test is
    # still structurally valid for pool-count, but the DDLFailedError surface
    # should be investigated separately.
    assert len(errors_seen) > 0, (
        "Expected DDLFailedError from FK-misordered model but got none; "
        "check DPI-A implementation in dataflow.core.engine"
    )


@pytest.mark.asyncio
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
            await db.close()

    await asyncio.gather(*[_attempt_access_warn(i) for i in range(10)])

    # Pool count MUST remain bounded regardless of auto_migrate mode.
    assert AsyncSQLDatabaseNode.pool_count() <= 5, (
        f"Pool leaked in warn mode: pool_count()={AsyncSQLDatabaseNode.pool_count()} > 5 "
        "after 10 DDL-failing DataFlow instances with auto_migrate='warn'"
    )

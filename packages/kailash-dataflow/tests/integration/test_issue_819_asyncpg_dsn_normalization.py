"""Regression tests for issue #819.

`DataFlow.get_connection()` raised ``ValueError: invalid dsn: invalid
connection option "asyncpg"`` when the configured database URL carried
the SQLAlchemy ``+asyncpg`` driver suffix — the form many docker-compose
stacks and ``DATABASE_URL`` env-vars use:

    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

The root cause was that ``DatabaseConfig.get_connection_url()`` returned
the URL verbatim. The engine's ``connection_context()`` handed that
string straight to ``asyncpg.connect()``, which rejects any scheme other
than ``postgresql://`` or ``postgres://``.

Fix: ``DatabaseConfig.get_connection_url()`` now normalizes the URL via
``dataflow.core.config._strip_asyncpg_driver_suffix`` so every caller
(the engine's ``get_connection()`` context manager, ``pool_utils``,
migrations, model registry) receives the bare scheme.

These tests run against real PostgreSQL (Tier 2 / NO MOCKING) so they
exercise the same asyncpg code path a user hits in production.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest

from dataflow import DataFlow
from dataflow.core.config import (
    DatabaseConfig,
    Environment,
    _strip_asyncpg_driver_suffix,
)
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Standard real-Postgres test suite (Tier 2)."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


def _swap_scheme(plain_url: str, new_scheme: str) -> str:
    """Replace the URL scheme while preserving userinfo / host / port / path.

    Used to derive ``postgresql+asyncpg://...`` and ``postgres+asyncpg://...``
    forms from the harness's plain ``postgresql://`` URL without re-deriving
    credentials from environment variables.
    """
    parsed = urlparse(plain_url)
    return urlunparse(parsed._replace(scheme=new_scheme))


# ---------------------------------------------------------------------------
# Pure-helper coverage (no DB required) — run in any environment, fast.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_strip_asyncpg_driver_suffix_postgresql_asyncpg() -> None:
    """``postgresql+asyncpg://`` becomes ``postgresql://`` byte-for-byte."""
    src = "postgresql+asyncpg://user:p%40ss@host:5432/db?sslmode=require"
    expected = "postgresql://user:p%40ss@host:5432/db?sslmode=require"
    assert _strip_asyncpg_driver_suffix(src) == expected


@pytest.mark.regression
def test_strip_asyncpg_driver_suffix_postgres_asyncpg() -> None:
    """``postgres+asyncpg://`` becomes ``postgres://`` byte-for-byte."""
    src = "postgres+asyncpg://u:p@h:5432/d"
    assert _strip_asyncpg_driver_suffix(src) == "postgres://u:p@h:5432/d"


@pytest.mark.regression
def test_strip_asyncpg_driver_suffix_psycopg2() -> None:
    """``postgresql+psycopg2://`` becomes ``postgresql://`` byte-for-byte."""
    src = "postgresql+psycopg2://u:p@h:5432/d"
    assert _strip_asyncpg_driver_suffix(src) == "postgresql://u:p@h:5432/d"


@pytest.mark.regression
def test_strip_asyncpg_driver_suffix_passthrough_plain_postgresql() -> None:
    """Plain ``postgresql://`` passes through unchanged (no false positives)."""
    src = "postgresql://u:p@h:5432/d"
    assert _strip_asyncpg_driver_suffix(src) is not None
    assert _strip_asyncpg_driver_suffix(src) == src


@pytest.mark.regression
def test_strip_asyncpg_driver_suffix_passthrough_sqlite() -> None:
    """Non-Postgres URLs pass through unchanged."""
    assert _strip_asyncpg_driver_suffix("sqlite:///dev.db") == "sqlite:///dev.db"
    assert _strip_asyncpg_driver_suffix("mysql://u:p@h/d") == "mysql://u:p@h/d"


@pytest.mark.regression
def test_database_config_get_connection_url_strips_asyncpg_suffix() -> None:
    """``DatabaseConfig.get_connection_url`` returns the stripped form.

    Behavioral assertion on the canonical accessor — every caller in
    DataFlow / pool_utils / migrations / model_registry routes through
    this method. Pinning its output is the structural defense.
    """
    cfg = DatabaseConfig(url="postgresql+asyncpg://user:pass@host:5432/db")
    assert (
        cfg.get_connection_url(Environment.PRODUCTION)
        == "postgresql://user:pass@host:5432/db"
    )

    cfg2 = DatabaseConfig(url="postgres+asyncpg://user:pass@host:5432/db")
    assert (
        cfg2.get_connection_url(Environment.PRODUCTION)
        == "postgres://user:pass@host:5432/db"
    )

    cfg3 = DatabaseConfig(url="postgresql://user:pass@host:5432/db")
    assert (
        cfg3.get_connection_url(Environment.PRODUCTION)
        == "postgresql://user:pass@host:5432/db"
    )


# ---------------------------------------------------------------------------
# Tier 2 — real Postgres via IntegrationTestSuite (NO MOCKING).
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
async def test_get_connection_succeeds_with_postgresql_asyncpg_dsn(
    test_suite: IntegrationTestSuite,
) -> None:
    """``DataFlow.get_connection()`` succeeds against a ``+asyncpg`` DSN.

    This is the user-reported failure mode: docker-compose stacks set
    ``DATABASE_URL=postgresql+asyncpg://...`` and the SDK's ``async with
    db.get_connection()`` raised at ``asyncpg.connect()``.
    """
    asyncpg_url = _swap_scheme(test_suite.config.url, "postgresql+asyncpg")
    db = DataFlow(asyncpg_url, auto_migrate=False)

    # Critical contract: get_connection() must round-trip a real query.
    async with db.get_connection() as conn:
        row = await conn.fetchrow("SELECT 1 AS ok")
        assert row is not None
        assert row["ok"] == 1


@pytest.mark.integration
@pytest.mark.regression
async def test_get_connection_succeeds_with_plain_postgresql_dsn(
    test_suite: IntegrationTestSuite,
) -> None:
    """Plain ``postgresql://`` continues to work (regression guard)."""
    db = DataFlow(test_suite.config.url, auto_migrate=False)

    async with db.get_connection() as conn:
        row = await conn.fetchrow("SELECT 1 AS ok")
        assert row is not None
        assert row["ok"] == 1


@pytest.mark.integration
@pytest.mark.regression
async def test_get_connection_succeeds_with_postgres_asyncpg_dsn(
    test_suite: IntegrationTestSuite,
) -> None:
    """``postgres+asyncpg://`` (alternative bare scheme) also succeeds."""
    asyncpg_url = _swap_scheme(test_suite.config.url, "postgres+asyncpg")
    db = DataFlow(asyncpg_url, auto_migrate=False)

    async with db.get_connection() as conn:
        row = await conn.fetchrow("SELECT 1 AS ok")
        assert row is not None
        assert row["ok"] == 1


@pytest.mark.integration
@pytest.mark.regression
async def test_dataflow_config_returns_stripped_form_for_all_three_inputs(
    test_suite: IntegrationTestSuite,
) -> None:
    """Round-trip through ``DataFlow.config.database.get_connection_url()``.

    Asserts the canonical accessor returns the bare scheme for both
    ``+asyncpg`` forms AND passes the plain form through unchanged.
    """
    plain = test_suite.config.url

    # +asyncpg → bare postgresql
    db1 = DataFlow(_swap_scheme(plain, "postgresql+asyncpg"), auto_migrate=False)
    url1 = db1.config.database.get_connection_url(db1.config.environment)
    assert url1.startswith("postgresql://"), url1
    assert "+asyncpg" not in url1

    # postgres+asyncpg → bare postgres
    db2 = DataFlow(_swap_scheme(plain, "postgres+asyncpg"), auto_migrate=False)
    url2 = db2.config.database.get_connection_url(db2.config.environment)
    assert url2.startswith("postgres://"), url2
    assert "+asyncpg" not in url2

    # plain postgresql → unchanged
    db3 = DataFlow(plain, auto_migrate=False)
    url3 = db3.config.database.get_connection_url(db3.config.environment)
    assert url3.startswith("postgresql://"), url3
    assert "+asyncpg" not in url3

    # All three forms must connect successfully via raw asyncpg too —
    # belt-and-suspenders that the stripped URL is consumable by asyncpg.
    for url in (url1, url2, url3):
        conn = await asyncpg.connect(url)
        try:
            row = await conn.fetchrow("SELECT 1 AS ok")
            assert row["ok"] == 1
        finally:
            await conn.close()

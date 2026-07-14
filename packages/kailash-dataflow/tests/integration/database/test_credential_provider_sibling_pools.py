#!/usr/bin/env python3
"""
Integration tests: credential_provider wiring on the sibling asyncpg pools
(issue #1737 follow-up) — ``LightweightPool`` (health checks) and
``PostgreSQLEventStore`` (audit-trail persistence). Both are long-lived
pools that run for the app's runtime, so they hit the same token-expiry
failure mode as the main ``PostgreSQLAdapter`` pool; both now delegate to
the SAME shared ``dataflow.core.credential_provider.build_asyncpg_credential_connect``
helper already covered exhaustively by
``tests/unit/adapters/test_postgresql_credential_provider.py`` — these
tests verify the WIRING (constructor -> initialize()'s create_pool kwargs),
not the shared helper's own contract.

Real PostgreSQL only — NO MOCKING (rules/testing.md Tier 2).
"""

from __future__ import annotations

import pytest

from dataflow.core.event_stores.postgresql import PostgreSQLEventStore
from dataflow.core.pool_lightweight import LightweightPool
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider — NOT a
    MagicMock."""

    def __init__(self, token: str):
        self._token = token
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        return self._token


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
@pytest.mark.regression
class TestLightweightPoolCredentialProvider:
    @pytest.mark.asyncio
    async def test_credential_provider_invoked_on_initialize(self, test_suite):
        provider = RotatingTokenProvider(token=test_suite.config.password)
        # Static URL password deliberately WRONG — proves the fresh
        # credential from the provider is what actually authenticates.
        url = (
            f"postgresql://{test_suite.config.user}:WRONG-STATIC"
            f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
        )
        pool = LightweightPool(url, pool_size=2, credential_provider=provider)
        try:
            await pool.initialize()
            assert pool.is_initialized
            assert provider.call_count >= 1
            rows = await pool.execute_raw("SELECT 1")
            assert rows[0][0] == 1
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_absent_credential_provider_behavior_unchanged(self, test_suite):
        pool = LightweightPool(test_suite.config.url, pool_size=2)
        assert pool.credential_provider is None
        try:
            await pool.initialize()
            assert pool.is_initialized
            rows = await pool.execute_raw("SELECT 1")
            assert rows[0][0] == 1
        finally:
            await pool.close()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
@pytest.mark.regression
class TestPostgreSQLEventStoreCredentialProvider:
    @pytest.mark.asyncio
    async def test_credential_provider_invoked_on_initialize(self, test_suite):
        provider = RotatingTokenProvider(token=test_suite.config.password)
        url = (
            f"postgresql://{test_suite.config.user}:WRONG-STATIC"
            f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
        )
        store = PostgreSQLEventStore(
            database_url=url,
            pool_min_size=1,
            pool_max_size=1,
            credential_provider=provider,
        )
        try:
            await store.initialize()
            assert provider.call_count >= 1
            assert store._pool is not None
            async with store._pool.acquire() as conn:
                assert await conn.fetchval("SELECT 1") == 1
        finally:
            if store._pool is not None:
                await store._pool.close()

    @pytest.mark.asyncio
    async def test_absent_credential_provider_behavior_unchanged(self, test_suite):
        store = PostgreSQLEventStore(
            database_url=test_suite.config.url, pool_min_size=1, pool_max_size=1
        )
        assert store.credential_provider is None
        try:
            await store.initialize()
            assert store._pool is not None
            async with store._pool.acquire() as conn:
                assert await conn.fetchval("SELECT 1") == 1
        finally:
            if store._pool is not None:
                await store._pool.close()

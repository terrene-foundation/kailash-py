#!/usr/bin/env python3
"""
Integration test for the CRUD HOT-PATH credential callback (issue #1741 —
follow-up to #1737).

#1737 wired credential_provider into three DataFlow-package pools (the adapter
probe, the health-check LightweightPool, and the audit-trail
PostgreSQLEventStore). It did NOT reach the pool the token-auth user's ACTUAL
``db.express`` / ``db.transactions`` / bulk CRUD queries open — the CORE-SDK
``AsyncSQLDatabaseNode`` pool (kailash.nodes.data.async_sql). This test proves
the headline user flow end-to-end: a ``DataFlow(url, credential_provider=...)``
whose URL carries a DELIBERATELY WRONG static password authenticates its CRUD
pool with the FRESH token from the provider — the create+read round-trips only
because the minted credential (not the stale URL password) is what connected.

Real PostgreSQL only — NO MOCKING (rules/testing.md Tier 2). Marked
@pytest.mark.requires_postgres (pytest.ini's default addopts skip it unless run
explicitly):

    pytest tests/integration/database/test_credential_provider_crud_hotpath_1741.py -m requires_postgres
"""

from __future__ import annotations

from typing import List

import pytest

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider — NOT a
    MagicMock. Returns the current token and counts invocations so the test
    can assert the CRUD pool actually minted via the callback."""

    def __init__(self, initial_token: str):
        self._token = initial_token
        self.call_count = 0
        self.returned_tokens: List[str] = []

    def rotate(self, new_token: str) -> None:
        self._token = new_token

    def __call__(self) -> str:
        self.call_count += 1
        self.returned_tokens.append(self._token)
        return self._token


def _wrong_static_password_url(test_suite) -> str:
    """The real user/host/db, but a DELIBERATELY WRONG static password. If the
    core CRUD pool used this static value it would fail authentication; a
    successful query proves the credential_provider token authenticated it."""
    c = test_suite.config
    return (
        f"postgresql://{c.user}:WRONG-STATIC-PASSWORD-1741"
        f"@{c.host}:{c.port}/{c.database}"
    )


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(60)
@pytest.mark.regression
class TestCredentialProviderCrudHotPath:
    @pytest.mark.asyncio
    async def test_express_create_read_authenticates_via_provider_token(
        self, test_suite
    ):
        # Correct credential comes ONLY from the provider; the URL's static
        # password is wrong on purpose.
        provider = RotatingTokenProvider(initial_token=test_suite.config.password)
        db = DataFlow(
            _wrong_static_password_url(test_suite),
            credential_provider=provider,
            auto_migrate=True,
        )

        @db.model
        class Widget1741:
            name: str
            qty: int

        await db.initialize()

        # These CRUD ops open the CORE AsyncSQLDatabaseNode pool. If the pool
        # authenticated with the WRONG static URL password they would raise an
        # asyncpg auth error; success proves the provider token connected it.
        created = await db.express.create("Widget1741", {"name": "alpha", "qty": 3})
        fetched = await db.express.read("Widget1741", created["id"])

        assert fetched["name"] == "alpha"
        assert fetched["qty"] == 3
        # The core CRUD pool minted at least one physical connection via the
        # callback (initial fill).
        assert provider.call_count >= 1

    @pytest.mark.asyncio
    async def test_absent_provider_still_works_with_correct_static_password(
        self, test_suite
    ):
        # Control: no provider, correct static URL password — behavior
        # unchanged from before #1741.
        db = DataFlow(test_suite.config.url, auto_migrate=True)

        @db.model
        class Widget1741Ctl:
            name: str

        await db.initialize()
        created = await db.express.create("Widget1741Ctl", {"name": "beta"})
        fetched = await db.express.read("Widget1741Ctl", created["id"])
        assert fetched["name"] == "beta"

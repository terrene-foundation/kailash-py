#!/usr/bin/env python3
"""
Integration tests for the per-physical-connection credential callback
(issue #1737 — token-based DB auth for Azure AD / AWS IAM parity with the
Rust SDK's rs#1810).

Real PostgreSQL only — NO MOCKING (rules/testing.md Tier 2). A dedicated,
disposable Postgres ROLE is created per rotation test so "the token expired
mid-run" is a REAL authentication event (ALTER ROLE ... PASSWORD), not a
simulation: the stale credential genuinely stops authenticating and the
fresh one genuinely starts.

All tests require real PostgreSQL (test_suite.config) — marked
@pytest.mark.requires_postgres per pytest.ini's default `-m "not
(requires_postgres or ...)"` addopts. Run explicitly with:
    pytest tests/integration/database/test_credential_provider.py -m requires_postgres
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

import asyncpg
import pytest

from dataflow.adapters.postgresql import PostgreSQLAdapter
from dataflow.exceptions import DataFlowConnectionError
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with real infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider — NOT a
    MagicMock. Holds a mutable "current token"; ``rotate()`` simulates an
    external token source (Azure AD / AWS IAM) issuing a fresh credential.
    Satisfies ``Callable[[], str]`` structurally.
    """

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


class FailAfterNCallsProvider:
    """Deterministic provider: returns ``token`` for the first
    ``succeed_calls`` invocations, then raises on every subsequent call —
    simulating a credential source that starts failing (e.g. an IAM role
    revoked, a token endpoint outage)."""

    def __init__(self, token: str, succeed_calls: int):
        self._token = token
        self._succeed_calls = succeed_calls
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        if self.call_count <= self._succeed_calls:
            return self._token
        raise RuntimeError("credential source unavailable (simulated)")


def _make_role_name() -> str:
    # Restricted charset (hex only) — test-generated, never user input.
    return f"cred1737_{uuid.uuid4().hex[:12]}"


class _DisposableRole:
    """Creates a disposable, password-authenticated PostgreSQL role for the
    duration of a test and guarantees teardown. Uses the test_suite's own
    superuser admin connection (test_user) — real infra, no mocking."""

    def __init__(self, admin_conn: asyncpg.Connection, role: str, password: str):
        self._admin = admin_conn
        self.role = role
        self._password = password

    async def create(self) -> None:
        await self._admin.execute(f'DROP ROLE IF EXISTS "{self.role}"')
        await self._admin.execute(
            f"CREATE ROLE \"{self.role}\" LOGIN PASSWORD '{self._password}'"
        )

    async def rotate_password(self, new_password: str) -> None:
        await self._admin.execute(
            f"ALTER ROLE \"{self.role}\" PASSWORD '{new_password}'"
        )

    async def drop(self) -> None:
        await self._admin.execute(f'DROP ROLE IF EXISTS "{self.role}"')


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
class TestCredentialProviderInvocationCount:
    """AC: the pool invokes credential_provider for EVERY physical
    connection (initial/recycled/overflow/reconnect)."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_provider_invoked_for_initial_and_overflow_physical_connections(
        self, test_suite
    ):
        provider = RotatingTokenProvider(initial_token=test_suite.config.password)
        # Static password field is deliberately WRONG — proves the
        # connect-wrapper's fresh credential is what actually authenticates,
        # not the static value captured at pool construction.
        url = (
            f"postgresql://{test_suite.config.user}:WRONG-STATIC-PASSWORD"
            f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
        )
        adapter = PostgreSQLAdapter(
            url, pool_size=1, max_overflow=2, credential_provider=provider
        )
        try:
            await adapter.create_connection_pool()
            # min_size == pool_size == 1: one physical connection opened
            # eagerly during pool creation.
            assert provider.call_count == 1

            async with adapter.connection_pool.acquire() as conn1:
                # A second, concurrently-held connection forces asyncpg to
                # open a NEW (overflow) physical connection.
                async with adapter.connection_pool.acquire() as conn2:
                    assert await conn1.fetchval("SELECT 1") == 1
                    assert await conn2.fetchval("SELECT 1") == 1
            assert provider.call_count == 2
        finally:
            await adapter.close_connection_pool()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
class TestCredentialProviderRotation:
    """AC (the flagship scenario): a pool whose token "expires" mid-run
    establishes a NEW connection post-expiry successfully via the
    callback."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_pool_reconnects_successfully_after_real_token_rotation(
        self, test_suite
    ):
        role = _make_role_name()
        token_v1 = f"tok1_{uuid.uuid4().hex[:10]}"
        token_v2 = f"tok2_{uuid.uuid4().hex[:10]}"

        admin_conn = await asyncpg.connect(test_suite.config.url)
        disposable_role = _DisposableRole(admin_conn, role, token_v1)
        try:
            await disposable_role.create()

            provider = RotatingTokenProvider(initial_token=token_v1)
            url = (
                f"postgresql://{role}:IGNORED-STATIC"
                f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
            )
            adapter = PostgreSQLAdapter(
                url, pool_size=1, max_overflow=0, credential_provider=provider
            )
            try:
                await adapter.create_connection_pool()
                assert provider.call_count == 1  # initial connect minted with token-v1

                async with adapter.connection_pool.acquire() as conn:
                    assert await conn.fetchval("SELECT 1") == 1

                # Simulate a real Azure AD / AWS IAM token expiry: rotate
                # the ACTUAL database credential — the SAME event shape an
                # external token source produces.
                await disposable_role.rotate_password(token_v2)
                provider.rotate(token_v2)

                # Force asyncpg to treat pooled connections as expired — the
                # NEXT acquire() opens a brand-new PHYSICAL connection (the
                # same primitive a long-running pool hits naturally via
                # max_inactive_connection_lifetime or a dropped socket).
                await adapter.connection_pool.expire_connections()

                async with adapter.connection_pool.acquire() as conn:
                    # AC: a physical connection opened AFTER the original
                    # token would have expired authenticates SUCCESSFULLY
                    # with the fresh value.
                    assert await conn.fetchval("SELECT 1") == 1

                assert provider.call_count == 2
                assert provider.returned_tokens == [token_v1, token_v2]
            finally:
                await adapter.close_connection_pool()
        finally:
            await disposable_role.drop()
            await admin_conn.close()

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_stale_token_no_longer_authenticates_after_rotation(self, test_suite):
        """Negative control proving the rotation test above is not
        vacuous: the OLD token genuinely stops working once rotated."""
        role = _make_role_name()
        token_v1 = f"tok1_{uuid.uuid4().hex[:10]}"
        token_v2 = f"tok2_{uuid.uuid4().hex[:10]}"

        admin_conn = await asyncpg.connect(test_suite.config.url)
        disposable_role = _DisposableRole(admin_conn, role, token_v1)
        try:
            await disposable_role.create()
            await disposable_role.rotate_password(token_v2)

            with pytest.raises(asyncpg.InvalidPasswordError):
                await asyncpg.connect(
                    host=test_suite.config.host,
                    port=test_suite.config.port,
                    database=test_suite.config.database,
                    user=role,
                    password=token_v1,
                )
        finally:
            await disposable_role.drop()
            await admin_conn.close()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
class TestCredentialProviderFailsClosed:
    """AC: callback error fails closed (raises typed error, no stale-token
    reuse)."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_provider_failure_on_new_connection_raises_and_does_not_reuse_stale_token(
        self, test_suite
    ):
        role = _make_role_name()
        token_v1 = f"tok1_{uuid.uuid4().hex[:10]}"

        admin_conn = await asyncpg.connect(test_suite.config.url)
        disposable_role = _DisposableRole(admin_conn, role, token_v1)
        try:
            await disposable_role.create()

            # Succeeds once (the initial pool-fill connect), then the
            # credential source starts failing on every subsequent call.
            provider = FailAfterNCallsProvider(token=token_v1, succeed_calls=1)
            url = (
                f"postgresql://{role}:IGNORED-STATIC"
                f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
            )
            adapter = PostgreSQLAdapter(
                url, pool_size=1, max_overflow=0, credential_provider=provider
            )
            try:
                await adapter.create_connection_pool()
                assert provider.call_count == 1

                # Force a reconnect on next acquire — the provider will now
                # raise (simulated credential-source outage).
                await adapter.connection_pool.expire_connections()

                with pytest.raises(DataFlowConnectionError):
                    async with adapter.connection_pool.acquire():
                        pass  # pragma: no cover — must not reach here

                # Fail-closed: no silent fallback to the (still technically
                # valid) token-v1 was attempted for this failing call.
                assert provider.call_count == 2
            finally:
                await adapter.close_connection_pool()
        finally:
            await disposable_role.drop()
            await admin_conn.close()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
class TestCredentialProviderNeverLogsToken:
    """AC: the token value never appears in any log/repr."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_token_value_absent_from_logs_across_success_rotation_and_failure(
        self, test_suite, caplog
    ):
        role = _make_role_name()
        token_v1 = f"tok1_{uuid.uuid4().hex[:10]}"
        token_v2 = f"tok2_{uuid.uuid4().hex[:10]}"
        secret_marker = f"SECRET-MARKER-{uuid.uuid4().hex[:12]}"

        admin_conn = await asyncpg.connect(test_suite.config.url)
        disposable_role = _DisposableRole(admin_conn, role, token_v1)
        try:
            await disposable_role.create()

            provider = RotatingTokenProvider(initial_token=token_v1)
            url = (
                f"postgresql://{role}:IGNORED-STATIC"
                f"@{test_suite.config.host}:{test_suite.config.port}/{test_suite.config.database}"
            )
            adapter = PostgreSQLAdapter(
                url, pool_size=1, max_overflow=0, credential_provider=provider
            )

            with caplog.at_level(logging.DEBUG):
                try:
                    await adapter.create_connection_pool()
                    async with adapter.connection_pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")

                    await disposable_role.rotate_password(token_v2)
                    provider.rotate(token_v2)
                    await adapter.connection_pool.expire_connections()
                    async with adapter.connection_pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                finally:
                    await adapter.close_connection_pool()

                # Trigger the fail-closed path too, with a marker that WOULD
                # leak if the wrapper interpolated str(exc). A fresh
                # adapter/pool is required: the connect-wrapper binds the
                # credential_provider it was built with at pool-creation
                # time (see _make_credential_provider_connect), so swapping
                # adapter.credential_provider post-hoc would not affect an
                # already-created pool's connect callable. The provider
                # succeeds once (the initial pool-fill connect) so the
                # failure happens on a POST-creation reconnect — raised
                # directly as DataFlowConnectionError from acquire(),
                # not wrapped by create_connection_pool()'s own
                # except-and-rewrap block.
                class _SucceedsOnceThenRaisesWithMarker:
                    def __init__(self):
                        self.call_count = 0

                    def __call__(self) -> str:
                        self.call_count += 1
                        if self.call_count == 1:
                            return token_v2
                        raise RuntimeError(f"leak-check {secret_marker}")

                marker_adapter = PostgreSQLAdapter(
                    url,
                    pool_size=1,
                    max_overflow=0,
                    credential_provider=_SucceedsOnceThenRaisesWithMarker(),
                )
                try:
                    await marker_adapter.create_connection_pool()
                    await marker_adapter.connection_pool.expire_connections()
                    with pytest.raises(DataFlowConnectionError):
                        async with marker_adapter.connection_pool.acquire():
                            pass  # pragma: no cover
                finally:
                    await marker_adapter.close_connection_pool()

            log_text = caplog.text
            assert token_v1 not in log_text
            assert token_v2 not in log_text
            assert secret_marker not in log_text
        finally:
            await disposable_role.drop()
            await admin_conn.close()


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.timeout(30)
class TestCredentialProviderAbsentBehaviorUnchanged:
    """AC: absent the callback, behavior is unchanged (static-string
    path — regression-tested)."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_pool_connects_with_static_password_when_no_provider_configured(
        self, test_suite
    ):
        adapter = PostgreSQLAdapter(test_suite.config.url, pool_size=1, max_overflow=1)
        assert adapter.credential_provider is None
        try:
            await adapter.create_connection_pool()
            async with adapter.connection_pool.acquire() as conn:
                assert await conn.fetchval("SELECT 1") == 1
        finally:
            await adapter.close_connection_pool()

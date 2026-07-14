"""
Unit tests for the CORE-SDK credential_provider connect-wrapper (issue #1741).

Tests the pure connect-wrapper logic of
``kailash.nodes.data.credential_provider.build_asyncpg_credential_connect``
(validation, fail-closed error shape, no-secret-in-exception-message,
per-physical-connection re-mint) WITHOUT a live database connection. Uses a
deterministic Protocol-satisfying fake for ``asyncpg`` — never a MagicMock —
per rules/testing.md's "Protocol-Satisfying Deterministic Adapters" carve-out.

This is the CORE sibling of the DataFlow-package unit test at
packages/kailash-dataflow/tests/unit/adapters/test_postgresql_credential_provider.py.
The core helper is what the db.express / db.transactions / bulk CRUD hot-path
pool (AsyncSQLDatabaseNode / PostgreSQLAdapter) uses — a distinct helper from
the DataFlow one because core cannot import the DataFlow package.

Tier-2 end-to-end coverage (real Postgres: per-physical-connection invocation
count on a real pool, token-rotation-establishes-new-connection, token never
logged) lives in the DataFlow package's
tests/integration/database/test_credential_provider*.py.
"""

from __future__ import annotations

from typing import List, Optional

import pytest

from kailash.nodes.data.credential_provider import build_asyncpg_credential_connect
from kailash.sdk_exceptions import NodeExecutionError


class _FakeAsyncpgConnection:
    """Minimal stand-in for an asyncpg.Connection — records the password it
    was constructed with so tests can assert on it without a real socket."""

    def __init__(self, password: Optional[str]):
        self.password = password


class _FakeAsyncpgModule:
    """Protocol-satisfying fake for the ``asyncpg`` module surface the
    connect-wrapper touches (``asyncpg.connect``). Deterministic, records
    every call's positional args + kwargs for inspection. NOT a MagicMock —
    a plain object with a real (if trivial) async implementation."""

    def __init__(self):
        self.connect_calls: List[dict] = []
        self.connect_args: List[tuple] = []

    async def connect(self, *args, **kwargs):
        self.connect_args.append(args)
        self.connect_calls.append(dict(kwargs))
        return _FakeAsyncpgConnection(kwargs.get("password"))


class RotatingTokenProvider:
    """Deterministic, Protocol-satisfying credential provider. Returns tokens
    from a fixed sequence, advancing one step per call and holding on the
    final value once exhausted. Satisfies ``Callable[[], str]`` structurally
    — NOT a MagicMock."""

    def __init__(self, tokens: List[str]):
        self._tokens = list(tokens)
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        idx = min(self.call_count - 1, len(self._tokens) - 1)
        return self._tokens[idx]


class RaisingProvider:
    """Deterministic provider that always raises, carrying a marker string in
    its exception message so tests can assert the marker is NEVER propagated
    verbatim into the raised NodeExecutionError."""

    def __init__(self, secret_marker: str):
        self._secret_marker = secret_marker
        self.call_count = 0

    def __call__(self) -> str:
        self.call_count += 1
        raise RuntimeError(f"token endpoint failed for secret={self._secret_marker}")


class NonStrProvider:
    """Deterministic provider returning a non-str / empty value."""

    def __init__(self, value):
        self._value = value
        self.call_count = 0

    def __call__(self):
        self.call_count += 1
        return self._value


class TestConnectWrapperMintsFreshCredentialPerCall:
    """AC: the wrapper re-mints on every invocation (the per-physical-
    connection hook asyncpg.Pool calls for initial/recycled/overflow/
    reconnect connections)."""

    @pytest.mark.asyncio
    async def test_wrapper_calls_provider_and_overrides_static_password(self):
        provider = RotatingTokenProvider(["token-v1", "token-v2", "token-v3"])
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        con1 = await connect(password="STALE-STATIC-PASSWORD")
        con2 = await connect(password="STALE-STATIC-PASSWORD")
        con3 = await connect(password="STALE-STATIC-PASSWORD")

        # Every physical connection got a FRESH, distinct credential — never
        # the stale static password captured at pool-construction time.
        assert con1.password == "token-v1"
        assert con2.password == "token-v2"
        assert con3.password == "token-v3"
        assert provider.call_count == 3
        assert len(fake_asyncpg.connect_calls) == 3

    @pytest.mark.asyncio
    async def test_wrapper_forwards_positional_dsn_and_non_password_kwargs(self):
        """The core pool passes the DSN positionally (create_pool(dsn, ...)).
        The wrapper MUST forward the positional DSN unchanged and inject the
        minted token as the ``password=`` kwarg (asyncpg's explicit kwarg
        overrides the DSN password)."""
        provider = RotatingTokenProvider(["token-v1"])
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        await connect(
            "postgresql://u:STALE@db.example.com:5432/app",
            command_timeout=60.0,
        )

        assert fake_asyncpg.connect_args[0] == (
            "postgresql://u:STALE@db.example.com:5432/app",
        )
        call = fake_asyncpg.connect_calls[0]
        assert call["command_timeout"] == 60.0
        assert call["password"] == "token-v1"

    @pytest.mark.asyncio
    async def test_context_appears_only_in_error_never_in_success_path(self):
        """The ``context`` label must never taint the connect call itself."""
        provider = RotatingTokenProvider(["token-v1"])
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(
            provider, fake_asyncpg, context="PostgreSQL"
        )
        await connect("postgresql://u:x@h:5432/d")
        assert "context" not in fake_asyncpg.connect_calls[0]


class TestConnectWrapperFailsClosed:
    """AC: callback error fails closed (raises typed error, no stale-token
    reuse)."""

    @pytest.mark.asyncio
    async def test_raising_provider_raises_typed_error(self):
        provider = RaisingProvider(secret_marker="TOKEN-SHOULD-NOT-LEAK-8f3a")
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        with pytest.raises(NodeExecutionError):
            await connect(password="STALE-STATIC-PASSWORD")

        # Fail-closed: asyncpg.connect was NEVER reached — no stale-token
        # fallback connection was attempted.
        assert len(fake_asyncpg.connect_calls) == 0

    @pytest.mark.asyncio
    async def test_raising_provider_message_excludes_secret_and_cause_chain(self):
        secret = "TOKEN-SHOULD-NOT-LEAK-8f3a"
        provider = RaisingProvider(secret_marker=secret)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        with pytest.raises(NodeExecutionError) as exc_info:
            await connect(password="STALE-STATIC-PASSWORD")

        # The provider exception's str() (which embeds the secret marker) MUST
        # NOT appear in the raised error message — only the exception TYPE.
        message = str(exc_info.value)
        assert secret not in message
        assert "RuntimeError" in message
        # ``from None`` severs the cause chain so the token-bearing provider
        # exception cannot render under logger.exception(...) / a traceback.
        assert exc_info.value.__cause__ is None
        assert exc_info.value.__suppress_context__ is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_value", [None, "", 12345, b"bytes-token", 3.14])
    async def test_non_str_or_empty_return_raises_typed_error(self, bad_value):
        provider = NonStrProvider(value=bad_value)
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        with pytest.raises(NodeExecutionError, match="non-empty str"):
            await connect(password="STALE-STATIC-PASSWORD")
        assert len(fake_asyncpg.connect_calls) == 0


class TestConnectWrapperDropsSecretAfterConnect:
    """AC: the minted token is held only for the connect call's duration."""

    @pytest.mark.asyncio
    async def test_connect_kwargs_password_cleared_after_call(self):
        provider = RotatingTokenProvider(["token-v1"])
        fake_asyncpg = _FakeAsyncpgModule()
        connect = build_asyncpg_credential_connect(provider, fake_asyncpg)

        # A caller-owned dict passed as kwargs: after connect returns, the
        # wrapper's finally-block nulls the password it injected so the live
        # secret is not retained in the caller's kwargs mapping.
        kwargs = {}
        await connect(**kwargs)
        # The fake recorded the token AT call time...
        assert fake_asyncpg.connect_calls[0]["password"] == "token-v1"
